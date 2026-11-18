"""自复盘三件套的测试（PRD「烛照九阴自复盘取代课件」R3、R4、N1、N2、X1 · 2026-11-17）。

覆盖：记录校验器的正例与负例；输入包的超额算法、美股时钟、缺数不补值、外部工具失败即报错；
逐日对照的计数、退役行排除、NULL 状态保留、人工栏随两侧版本走；
以及静态约束——输入与校验两个脚本不读任何课件派生表。

2026-11-17 V.V. 复核后补的负例（EAL 工作日志同日条）：缺基准日或缺篮子成员时不得悄悄改窗口或权重；
舍弃词在任何文字字段里都要拦（含小写、全角、证据备注、local_only、no_change_note）；
课件派生表与复盘库的引用在任何位置都要拦；日期、时刻、数值、输入包身份要是真的；
对照里人工填的方向结论，两侧内容变过就标待复核。
"""
import copy, csv, hashlib, json, os, re, sqlite3, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools import self_recap_inputs as inp
from tools import self_recap_validate as val
from tools import self_recap_compare as cmp_


def good_doc():
    return {
        "schema_version": 2, "trade_date": "20261116", "observed_at": "2026-11-17T08:00:00+00:00",
        "session": "盘后", "inputs_sha256": "0" * 64, "blind": True,
        "records": [{
            "id": "r1", "theme": None,
            "object": "光通信链条", "main_issue": "海外同业连续走弱，本地是否跟随",
            "anchor": {"name": "LITE", "card": "卡一", "role": "同向印证"},
            "evidence": [{"kind": "market_data", "ref": "market_data.db:us_anchor_daily:LITE:20261113",
                          "asof": "20261113", "value": -4.49}],
            "transmission": {"chain": "海外光器件需求 → 订单 → 本地光通信链的收入",
                             "exposure": "本地这条链对海外客户的收入占比未核", "status": "未核"},
            "change": {"baseline": "上一交易日的 20 日超额", "delta": "继续走低"},
            "direction": "宜减",
            "stage": "条件草案", "stage_basis": "锚的 20 日超额为负且本地确认；传导与商业暴露还没核",
            "prior": {"ref": None, "carry": "上一期没有这个对象的记录"},
            "local_confirmation": {"status": "已确认", "basis": "本地主线 5 日与 20 日超额同为负"},
            "priced_in": "本地已连续回落，部分已反映",
            "invalidation": "海外同业 20 日超额转正且本地 5 日超额转正",
            "next_check": "下一交易日盘前看海外同业收盘",
        }],
    }


URL_EV = {"kind": "url", "ref": "https://example.com/markets/2026/11/16/some-story", "asof": "2026-11-16T20:58Z",
          "body_read": "仅标题", "first_public_at": "未核"}


class ValidateTest(unittest.TestCase):
    def errs(self, mutate):
        d = good_doc()
        mutate(d)
        return val.validate(d, {"机器人"})

    def set_rec(self, key, value):
        return self.errs(lambda d: d["records"][0].__setitem__(key, value))

    def test_good_passes(self):
        self.assertEqual(val.validate(good_doc(), {"机器人"}), [])

    def test_banned_wording_rejected(self):
        for bad in ("跌破 MA60 则撤", "降到三成", "站回 60 日均线", "成交额低于 1.5 万亿", "三天不涨则退", "出现涨停再看"):
            self.assertTrue(any("已舍弃" in x for x in self.set_rec("invalidation", bad)), bad)

    def test_banned_wording_variants_rejected(self):
        # V.V. 复核给出的漏口：小写、全角、固定天数、亿元阈值、仓位百分比
        for bad in ("跌破 ma60 则退出", "跌破ＭＡ６０即撤", "两日不涨则止损", "成交额低于15000亿元则退出",
                    "10 个交易日内不收回则离场", "半仓观察"):
            self.assertTrue(any("已舍弃" in x for x in self.set_rec("invalidation", bad)), bad)
        self.assertTrue(any("已舍弃" in x for x in self.set_rec("next_check", "仓位增加10%")))

    def test_banned_wording_rejected_in_every_text_field(self):
        cases = [
            lambda d: d.update(records=[], no_change_note="MA60线上维持三成"),
            lambda d: d.__setitem__("local_only", [{"theme": "机器人", "note": "站上均线再看"}]),
            lambda d: d["records"][0]["evidence"][0].__setitem__("note", "跌破MA60即止损"),
            lambda d: d.__setitem__("data_notes", ["三天不涨则退"]),
            lambda d: d["records"][0]["change"].__setitem__("delta", "加仓两成"),
        ]
        for m in cases:
            self.assertTrue(any("已舍弃" in x for x in self.errs(m)))

    def test_evidence_may_state_turnover_as_fact(self):
        def m(d):
            d["records"][0]["evidence"][0]["note"] = "两市成交额 1.9 万亿，高于前一日的 1.8 万亿"
        self.assertEqual(self.errs(m), [])
        # 同一句话放进判断文字就是阈值，照拦
        self.assertTrue(any("已舍弃" in x for x in self.set_rec("priced_in", "两市成交额 1.9 万亿，高于前一日")))

    def test_ordinary_words_not_misfired(self):
        for ok in ("订单完成交付后重判", "板块形成共识", "两成交量相近的标的不比较",
                   "海外同业 20 日超额转正且本地 5 日超额转正则撤回判断", "下一交易日若继续走弱则撤",
                   "11月16日收盘后再看是否退出观察", "近 20 日涨幅回吐则撤", "仓储物流板块跌 3%"):
            self.assertFalse(any("已舍弃" in x for x in self.set_rec("invalidation", ok)), ok)

    def test_lesson_reference_rejected(self):
        e = self.errs(lambda d: d["records"][0]["evidence"][0].__setitem__("ref", "recap.db:industry_signals:123"))
        self.assertTrue(any("课件" in x for x in e))
        self.assertTrue(any("课件" in x for x in self.set_rec("main_issue", "小鲍提到的光通信")))

    def test_lesson_derived_tables_and_recap_db_rejected_anywhere(self):
        for ref in ("recap.db:information_gap:1", "recap.db:cycle_comparison:1", "recap.db:emotion_cycle:20261116",
                    "market_data.db:hot_sectors:1"):
            e = self.errs(lambda d: d["records"][0]["evidence"][0].__setitem__("ref", ref))
            self.assertTrue(e, ref)
        e = self.errs(lambda d: d.__setitem__("local_only", [{"theme": "机器人", "ref": "recap.db:industry_signals:123"}]))
        self.assertTrue(any("课件" in x for x in e))
        # 盲写说明里要提到课件，这一处不算引用
        d = good_doc(); d["blind"] = False; d["blind_note"] = "写之前已经看过当日课件，本期只验证流程"
        self.assertEqual(val.validate(d, None), [])

    def test_market_data_ref_must_name_an_allowed_table(self):
        for ref in ("market_data.db:limit_list_daily:20261116", "某个库:us_anchor_daily:LITE", "us_anchor_daily:LITE"):
            e = self.errs(lambda d: d["records"][0]["evidence"][0].__setitem__("ref", ref))
            self.assertTrue(any("行情表" in x for x in e), ref)
        e = self.errs(lambda d: d["records"][0]["evidence"][0].update(kind="inputs", ref="local.themes[机器人]"))
        self.assertTrue(any("inputs.json" in x for x in e))

    def test_direction_vocabulary(self):
        self.assertTrue(any("direction" in x for x in self.set_rec("direction", "加到六成")))

    def test_role_vocabulary(self):
        ok = self.errs(lambda d: d["records"][0]["anchor"].__setitem__("role", "事件或预期"))
        self.assertEqual(ok, [])
        bad = self.errs(lambda d: d["records"][0]["anchor"].__setitem__("role", "本地确认的测试"))
        self.assertTrue(any("role" in x for x in bad))

    def test_add_requires_local_confirmation(self):
        def m(d):
            d["records"][0]["direction"] = "可加"
            d["records"][0]["local_confirmation"]["status"] = "待确认"
        self.assertTrue(any("本地未确认" in x for x in self.errs(m)))

    def test_evidence_needs_asof_and_valid_kind(self):
        e = self.errs(lambda d: d["records"][0]["evidence"][0].pop("asof"))
        self.assertTrue(any("asof" in x for x in e))
        e = self.errs(lambda d: d["records"][0]["evidence"][0].__setitem__("kind", "memory"))
        self.assertTrue(any("kind" in x for x in e))
        e = self.errs(lambda d: d["records"][0]["evidence"][0].update(kind="url", ref="某篇文章"))
        self.assertTrue(any("网址" in x for x in e))

    def test_url_evidence_declares_body_read_and_first_public_time(self):
        def with_url(**kw):
            def m(d):
                d["records"][0]["evidence"].append(dict(URL_EV, **kw))
            return self.errs(m)
        self.assertEqual(with_url(), [])
        self.assertEqual(with_url(body_read="已读正文", first_public_at="2026-11-16T20:58:00+00:00"), [])
        self.assertTrue(any("body_read" in x for x in with_url(body_read="看过")))
        self.assertTrue(any("first_public_at" in x for x in with_url(first_public_at="周末")))
        self.assertTrue(any("first_public_at" in x for x in with_url(first_public_at="2026-11-16")))     # 没有时区的日期不算时刻
        self.assertTrue(any("first_public_at" in x for x in with_url(first_public_at="2026-11-18T00:00:00+00:00")))
        # 只有站点首页、文章路径被截掉的网址不算
        self.assertTrue(any("网址" in x for x in with_url(ref="https://www.reuters.com/")))
        self.assertTrue(any("网址" in x for x in with_url(ref="https://www.reuters.com")))

    def test_dates_times_and_numbers_must_be_real(self):
        self.assertTrue(self.errs(lambda d: d.__setitem__("schema_version", 999)))
        self.assertTrue(self.errs(lambda d: d.__setitem__("schema_version", 1)))
        self.assertTrue(any("observed_at" in x for x in self.errs(lambda d: d.__setitem__("observed_at", "unknown"))))
        self.assertTrue(any("observed_at" in x for x in self.errs(lambda d: d.__setitem__("observed_at", "2026-11-17T08:00:00"))))
        self.assertTrue(any("session" in x for x in self.errs(lambda d: d.__setitem__("session", "盘前"))))
        self.assertTrue(any("trade_date" in x for x in self.errs(lambda d: d.__setitem__("trade_date", "20261399"))))
        self.assertTrue(any("observed_at" in x for x in self.errs(lambda d: d.__setitem__("observed_at", "2026-11-10T08:00:00+00:00"))))
        e = self.errs(lambda d: d["records"][0]["evidence"][0].__setitem__("asof", "20991231"))
        self.assertTrue(any("晚于写记录的时刻" in x for x in e))
        e = self.errs(lambda d: d["records"][0]["evidence"][0].__setitem__("asof", "上周"))
        self.assertTrue(any("asof" in x for x in e))
        e = self.errs(lambda d: d["records"][0]["evidence"][0].__setitem__("value", float("nan")))
        self.assertTrue(any("有限数" in x for x in e))
        e = self.errs(lambda d: d["records"][0]["evidence"][0].__setitem__("value", float("inf")))
        self.assertTrue(any("有限数" in x for x in e))
        self.assertTrue(any("blind" in x for x in self.errs(lambda d: d.pop("blind"))))
        self.assertTrue(any("blind" in x for x in self.errs(lambda d: d.__setitem__("blind", "是"))))
        self.assertTrue(any("blind_note" in x for x in self.errs(lambda d: d.__setitem__("blind", False))))

    def test_transmission_required_and_consistent(self):
        self.assertTrue(any("transmission" in x for x in self.errs(lambda d: d["records"][0].pop("transmission"))))
        for bad in ({"chain": "", "exposure": "x", "status": "未核"}, {"chain": "x", "exposure": "x", "status": "大概"},
                    {"chain": "x", "status": "已核"}, "锚涨所以它涨"):
            self.assertTrue(any("transmission" in x for x in self.set_rec("transmission", bad)), bad)
        # 「不适用」只给温度计
        e = self.errs(lambda d: d["records"][0]["transmission"].__setitem__("status", "不适用"))
        self.assertTrue(any("不适用" in x for x in e))

        def thermo(d):
            d["records"][0]["anchor"]["role"] = "温度计"
            d["records"][0]["transmission"] = {"chain": "无直接商业关系，只读环境", "exposure": "不适用", "status": "不适用"}
        self.assertEqual(self.errs(thermo), [])

        # 传导没核，不得给「可加」
        def add(d, status):
            r = d["records"][0]
            r["direction"] = "可加"; r["transmission"]["status"] = status
        self.assertTrue(any("传导" in x and "可加" in x for x in self.errs(lambda d: add(d, "未核"))))
        self.assertEqual(self.errs(lambda d: add(d, "部分已核")), [])

    def test_stage_matches_direction(self):
        self.assertTrue(any("stage" in x for x in self.errs(lambda d: d["records"][0].pop("stage"))))
        self.assertTrue(any("stage" in x for x in self.set_rec("stage", "具备执行条件")))     # 自复盘没有这一档
        self.assertTrue(any("不是观察" in x for x in self.set_rec("stage", "观察")))            # 宜减却写观察
        self.assertTrue(any("stage_basis" in x for x in self.errs(lambda d: d["records"][0].pop("stage_basis"))))

        def watch(d, stage):
            d["records"][0]["direction"] = "观察"; d["records"][0]["stage"] = stage
        self.assertEqual(self.errs(lambda d: watch(d, "观察")), [])
        self.assertTrue(any("stage" in x for x in self.errs(lambda d: watch(d, "条件草案"))))

        def hold(d, stage):
            d["records"][0]["direction"] = "不动"; d["records"][0]["stage"] = stage
        self.assertEqual(self.errs(lambda d: hold(d, "观察")), [])
        self.assertEqual(self.errs(lambda d: hold(d, "条件草案")), [])

    def test_prior_shape(self):
        self.assertTrue(any("prior" in x for x in self.errs(lambda d: d["records"][0].pop("prior"))))
        self.assertTrue(any("prior" in x for x in self.set_rec("prior", {"ref": None})))
        self.assertTrue(any("prior" in x for x in self.set_rec("prior", {"carry": "接着看"})))
        self.assertTrue(any("carried_over" in x for x in self.errs(
            lambda d: d.__setitem__("carried_over", [{"ref": "20261113-01", "outcome": "不管了", "note": "x"}]))))
        self.assertTrue(any("carried_over" in x for x in self.errs(
            lambda d: d.__setitem__("carried_over", [{"ref": "20261113-01", "outcome": "已结"}]))))

    def test_empty_records_need_note(self):
        e = self.errs(lambda d: d.__setitem__("records", []))
        self.assertTrue(any("no_change_note" in x for x in e))
        d = good_doc(); d["records"] = []; d["no_change_note"] = "当日外部读数与本地主线都没有新变化"
        self.assertEqual(val.validate(d, set()), [])

    def test_unknown_theme_rejected(self):
        self.assertTrue(any("theme" in x for x in self.set_rec("theme", "不存在的主线")))

    def test_inputs_binding(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "inputs.json"

            def bind(pack):
                p.write_text(json.dumps(pack, ensure_ascii=False), encoding="utf-8")
                d = good_doc()
                d["inputs_sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
                return val.validate(d, None, p)

            ok = {"kind": "self_recap_inputs", "schema_version": 2, "trade_date": "20261116"}
            self.assertEqual(bind(ok), [])
            self.assertEqual(bind(dict(ok, schema_version=1)), [])                      # 复核前生成的输入包照认
            self.assertTrue(any("校验值" in x for x in val.validate(good_doc(), None, p)))  # 校验值不符
            self.assertTrue(any("不一致" in x for x in bind(dict(ok, trade_date="20261117"))))   # 别的交易日的输入包
            self.assertTrue(any("不是自复盘输入包" in x for x in bind({})))
            self.assertTrue(any("schema_version" in x for x in bind(dict(ok, schema_version=9))))
            self.assertTrue(any("找不到" in x for x in val.validate(good_doc(), None, Path(td) / "没有.json")))


class CarryTest(unittest.TestCase):
    """上一期的每条记录都要有去向（V.V. 复核第 11 条；Doctor 2026-11-17 裁定补这一项）。"""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)

    def tearDown(self):
        self.td.cleanup()

    def put(self, day, ids, raw=None):
        d = self.root / day
        d.mkdir()
        (d / "records.json").write_text(
            raw if raw is not None else json.dumps({"schema_version": 1, "records": [{"id": i} for i in ids]}),
            encoding="utf-8")

    def run_doc(self, mutate=None):
        d = good_doc()
        if mutate:
            mutate(d)
        cur = self.root / d["trade_date"]
        cur.mkdir(exist_ok=True)
        p = cur / "inputs.json"
        p.write_text(json.dumps({"kind": "self_recap_inputs", "schema_version": 2, "trade_date": d["trade_date"]}),
                     encoding="utf-8")
        d["inputs_sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
        return val.validate(d, None, p)

    def test_first_period_needs_no_reference(self):
        self.assertEqual(self.run_doc(), [])

    def test_reference_to_nonexistent_record_rejected(self):
        e = self.run_doc(lambda d: d["records"][0]["prior"].__setitem__("ref", "20261113-01"))
        self.assertTrue(any("不存在" in x for x in e))

    def test_every_previous_record_needs_a_destination(self):
        self.put("20261113", ["20261113-01", "20261113-02"])
        self.put("20261112", ["20261112-01"])                      # 更早的一期不用管，只接上一期
        e = self.run_doc()
        self.assertEqual(sum("没有去向" in x for x in e), 2)

        def link(d):
            d["records"][0]["prior"] = {"ref": "20261113-01", "carry": "上一期说看锚的收盘：锚继续走弱"}
        e = self.run_doc(link)
        self.assertEqual([x for x in e if "没有去向" in x], ["doc: 上一期 20261113 的记录 20261113-02 没有去向——用某条记录的 prior.ref 接上，或写进 carried_over"])

        def link_and_close(d):
            link(d)
            d["carried_over"] = [{"ref": "20261113-02", "outcome": "搁置", "note": "当日没有新读数，下一期再看"}]
        self.assertEqual(self.run_doc(link_and_close), [])

    def test_cannot_both_continue_and_close(self):
        self.put("20261113", ["20261113-01"])

        def m(d):
            d["records"][0]["prior"] = {"ref": "20261113-01", "carry": "接着看"}
            d["carried_over"] = [{"ref": "20261113-01", "outcome": "已结", "note": "条件已失效"}]
        self.assertTrue(any("不要再列" in x for x in self.run_doc(m)))

    def test_reference_must_be_from_the_previous_period(self):
        self.put("20261113", ["20261113-01"])
        self.put("20261112", ["20261112-01"])

        def m(d):
            d["records"][0]["prior"] = {"ref": "20261112-01", "carry": "接两期前的"}
            d["carried_over"] = [{"ref": "20261113-01", "outcome": "已结", "note": "已失效"}]
        self.assertTrue(any("20261112-01 不存在" in x for x in self.run_doc(m)))

    def test_later_or_same_day_periods_ignored(self):
        self.put("20261117", ["20261117-01"])                      # 晚于本期，不算上一期
        self.assertEqual(self.run_doc(), [])

    def test_unreadable_previous_period_is_an_error(self):
        self.put("20261113", [], raw="{坏的")
        self.assertTrue(any("读不出来" in x for x in self.run_doc()))


def make_market_db(path, a_dates, us_dates, theme_code, us_ticker, drop_etf_day=None, drop=(), extra_etf=None,
                   closed=()):
    """a_dates：交易日历上的开市日，也是各 ETF 有行情的日子。drop：{(表, 代码, 日期)} 这些行不写。
    extra_etf：{代码: 日涨幅}，另加的篮子成员。closed：日历上标为休市的日子（没有行情）。"""
    drop = set(drop)
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE daily_market(trade_date TEXT, sh_close REAL, sh_pct_chg REAL, sz_pct_chg REAL, "
              "cyb_pct_chg REAL, volume_trillion REAL)")
    c.execute("CREATE TABLE theme_etf_daily(trade_date TEXT, etf_code TEXT, close REAL, pct_chg REAL, is_benchmark INT)")
    c.execute("CREATE TABLE us_anchor_daily(trade_date TEXT, ticker TEXT, close_adj REAL, pct_chg REAL, is_benchmark INT)")
    c.execute("CREATE TABLE trade_cal(cal_date TEXT, is_open INT)")
    for d in closed:
        c.execute("INSERT INTO trade_cal VALUES(?,0)", (d,))
    for d in a_dates:
        c.execute("INSERT INTO trade_cal VALUES(?,1)", (d,))
        c.execute("INSERT INTO daily_market VALUES(?,?,?,?,?,?)", (d, 3000.0, 0.1, 0.1, 0.1, 1.0))
        if ("etf", inp.BENCHMARK, d) not in drop:
            c.execute("INSERT INTO theme_etf_daily VALUES(?,?,?,?,1)", (d, inp.BENCHMARK, 1.0, 0.5))
        if d != drop_etf_day and ("etf", theme_code, d) not in drop:
            c.execute("INSERT INTO theme_etf_daily VALUES(?,?,?,?,0)", (d, theme_code, 1.0, 1.5))
        for code, pct in (extra_etf or {}).items():
            if ("etf", code, d) not in drop:
                c.execute("INSERT INTO theme_etf_daily VALUES(?,?,?,?,0)", (d, code, 1.0, pct))
    for d in us_dates:
        if ("us", inp.BENCHMARK_US, d) not in drop:
            c.execute("INSERT INTO us_anchor_daily VALUES(?,?,?,?,1)", (d, inp.BENCHMARK_US, 1.0, 0.2))
        if ("us", us_ticker, d) not in drop:
            c.execute("INSERT INTO us_anchor_daily VALUES(?,?,?,?,0)", (d, us_ticker, 1.0, 1.2))
    c.commit(); c.close()


class InputsTest(unittest.TestCase):
    def setUp(self):
        self.theme = next(t for t in inp.THEME_ETF if t in inp.THEME_US and len(inp.THEME_ETF[t]) == 1)
        self.code = inp.THEME_ETF[self.theme][0]
        self.ticker = inp.THEME_US[self.theme][0]
        self.a_dates = [f"202611{d:02d}" for d in range(1, 26)]          # 25 个「交易日」（算法夹具，不是真日历）
        self.td = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.td.name, "m.db")

    def tearDown(self):
        self.td.cleanup()

    def theme_row(self, block, theme=None):
        return next(t for t in block["themes"] if t["theme"] == (theme or self.theme))

    def test_excess_math_and_units(self):
        make_market_db(self.db, self.a_dates, self.a_dates, self.code, self.ticker)
        date, block, gaps = inp.local_block(self.db)
        self.assertEqual(date, "20261125")
        t = self.theme_row(block)
        self.assertEqual(t["e5"], 5.0)      # 每日超额 1.0 个百分点 × 5
        self.assertEqual(t["e20"], 20.0)
        self.assertEqual(t["pct_chg"], 1.5)
        self.assertEqual(t["us_anchor"]["ex20"], 20.0)
        self.assertEqual(block["market"]["amount_trillion"], 1.0)
        self.assertEqual(block["windows"], {"a5": ["20261121", "20261125"], "a20": ["20261106", "20261125"],
                                            "us20": ["20261105", "20261124"]})
        self.assertFalse([g for g in gaps if self.theme in g or self.ticker in g or inp.BENCHMARK in g])

    def test_us_rows_on_or_after_trade_date_excluded(self):
        make_market_db(self.db, self.a_dates, self.a_dates + ["20261126"], self.code, self.ticker)
        _, block, _ = inp.local_block(self.db, "20261125")
        a = self.theme_row(block)["us_anchor"]
        self.assertEqual((a["last_date"], a["window_end"]), ("20261124", "20261124"))

    def test_missing_day_gives_gap_not_zero(self):
        make_market_db(self.db, self.a_dates, self.a_dates, self.code, self.ticker, drop_etf_day="20261120")
        _, block, gaps = inp.local_block(self.db, "20261125")
        t = self.theme_row(block)
        self.assertIsNone(t["e20"])
        self.assertEqual(t["e5"], 5.0)                 # 5 日窗口（21 至 25 日）是齐的，照出
        self.assertTrue(any(self.theme in g and "excess_unavailable:e20" in g and "20261120" in g for g in gaps))

    def test_missing_benchmark_day_does_not_shrink_window(self):
        # V.V. 复核：删掉基准 20261120 一行，原实现仍输出 e20=20.0 且没有缺口
        make_market_db(self.db, self.a_dates, self.a_dates, self.code, self.ticker,
                       drop={("etf", inp.BENCHMARK, "20261120")})
        _, block, gaps = inp.local_block(self.db, "20261125")
        t = self.theme_row(block)
        self.assertIsNone(t["e20"])
        self.assertEqual(t["e5"], 5.0)
        self.assertIn(f"theme_etf_daily:{inp.BENCHMARK}:20261120:missing", gaps)
        self.assertEqual(block["windows"]["a20"], ["20261106", "20261125"])     # 窗口没有往前挪

    def test_missing_us_benchmark_day_does_not_shift_window(self):
        # V.V. 复核：删掉美股基准最新一日，原实现用截至前一日的窗口，却仍挂最新日期
        make_market_db(self.db, self.a_dates, self.a_dates, self.code, self.ticker,
                       drop={("us", inp.BENCHMARK_US, "20261124")})
        _, block, gaps = inp.local_block(self.db, "20261125")
        a = self.theme_row(block)["us_anchor"]
        self.assertIsNone(a["ex20"])
        self.assertEqual(a["window_end"], "20261124")
        self.assertIn(f"us_anchor_daily:{inp.BENCHMARK_US}:20261124:missing", gaps)
        self.assertTrue(any(g.startswith(f"us_anchor_daily:{self.ticker}:ex20_unavailable") and "20261124" in g
                            for g in gaps))

    def test_missing_us_anchor_day_is_a_gap(self):
        make_market_db(self.db, self.a_dates, self.a_dates, self.code, self.ticker,
                       drop={("us", self.ticker, "20261118")})
        _, block, gaps = inp.local_block(self.db, "20261125")
        self.assertIsNone(self.theme_row(block)["us_anchor"]["ex20"])
        self.assertTrue(any(self.ticker in g and "20261118" in g for g in gaps))

    def test_basket_member_missing_does_not_change_weights(self):
        # V.V. 复核：两只 ETF 日超额 1 与 2，完整篮子 e5/e20=7.5/30.0；只删第二只 20261120，
        # 原实现变成 5.0/20.0 且没有缺口
        theme = next(t for t in inp.THEME_ETF if len(inp.THEME_ETF[t]) == 2)
        c1, c2 = inp.THEME_ETF[theme]
        make_market_db(self.db, self.a_dates, self.a_dates, c1, self.ticker, extra_etf={c2: 2.5})
        _, block, gaps = inp.local_block(self.db, "20261125")
        t = self.theme_row(block, theme)
        self.assertEqual((t["e5"], t["e20"], t["pct_chg"]), (7.5, 30.0, 2.0))
        self.assertEqual(t["pct_chg_members"], {c1: 1.5, c2: 2.5})
        os.remove(self.db)
        make_market_db(self.db, self.a_dates, self.a_dates, c1, self.ticker, extra_etf={c2: 2.5},
                       drop={("etf", c2, "20261120")})
        _, block, gaps = inp.local_block(self.db, "20261125")
        t = self.theme_row(block, theme)
        self.assertIsNone(t["e20"])                    # 不拿剩下的一只冒充原篮子
        self.assertEqual(t["e5"], 7.5)                 # 5 日窗口两只都齐，权重不变
        self.assertTrue(any(theme in g and "excess_unavailable:e20" in g and c2 in g and "20261120" in g for g in gaps))
        os.remove(self.db)
        make_market_db(self.db, self.a_dates, self.a_dates, c1, self.ticker, extra_etf={c2: 2.5},
                       drop={("etf", c2, "20261125")})
        _, block, gaps = inp.local_block(self.db, "20261125")
        t = self.theme_row(block, theme)
        self.assertIsNone(t["pct_chg"])                # 当日缺一只，单日涨跌也不出
        self.assertEqual(t["pct_chg_members"], {c1: 1.5, c2: None})
        self.assertTrue(any(theme in g and "pct_chg_unavailable" in g and c2 in g for g in gaps))

    def test_window_follows_calendar_not_rows(self):
        # 日历上 20261110 是开市日，行情表却整天没有：不能当成「那天不存在」
        make_market_db(self.db, self.a_dates, self.a_dates, self.code, self.ticker,
                       drop={("etf", inp.BENCHMARK, "20261110"), ("etf", self.code, "20261110")})
        _, block, gaps = inp.local_block(self.db, "20261125")
        self.assertIsNone(self.theme_row(block)["e20"])
        self.assertIn(f"theme_etf_daily:{inp.BENCHMARK}:20261110:missing", gaps)

    def test_no_calendar_means_no_window(self):
        make_market_db(self.db, self.a_dates, self.a_dates, self.code, self.ticker)
        c = sqlite3.connect(self.db); c.execute("DROP TABLE trade_cal"); c.commit(); c.close()
        _, block, gaps = inp.local_block(self.db, "20261125")
        t = self.theme_row(block)
        self.assertEqual((t["e5"], t["e20"]), (None, None))
        self.assertIn("trade_cal:20261125:window_unavailable", gaps)
        self.assertIsNone(block["windows"]["a20"])

    def test_closed_days_are_not_counted(self):
        make_market_db(self.db, self.a_dates, self.a_dates, self.code, self.ticker, closed=["20261126", "20261031"])
        _, block, _ = inp.local_block(self.db, "20261125")
        self.assertEqual(self.theme_row(block)["e20"], 20.0)

    def test_no_market_row_fails(self):
        make_market_db(self.db, self.a_dates, self.a_dates, self.code, self.ticker)
        with self.assertRaises(inp.InputError):
            inp.local_block(self.db, "20270101")

    def test_external_tool_failure_is_error(self):
        with self.assertRaises(inp.InputError):
            inp.run_vv_tool(Path(self.td.name) / "不存在.py")
        bad = Path(self.td.name) / "bad.py"
        bad.write_text("import sys; print('{\"status\":\"failed\"}'); sys.exit(2)\n", encoding="utf-8")
        with self.assertRaises(inp.InputError):
            inp.run_vv_tool(bad)
        dep = Path(self.td.name) / "dep.py"
        dep.write_text("print('{\"lesson_dependency\": true}')\n", encoding="utf-8")
        with self.assertRaises(inp.InputError):
            inp.run_vv_tool(dep)
        ok = Path(self.td.name) / "ok.py"
        ok.write_text("print('{\"lesson_dependency\": false, \"gaps\": []}')\n", encoding="utf-8")
        self.assertEqual(inp.run_vv_tool(ok)["lesson_dependency"], False)


class CompareTest(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.td.name, "r.db")
        c = sqlite3.connect(self.db)
        c.execute("CREATE TABLE industry_signals(date TEXT, etf_anchor TEXT, status TEXT, keyword TEXT, signal_content TEXT)")
        c.executemany("INSERT INTO industry_signals VALUES(?,?,?,?,?)", [
            ("2026-11-16", "机器人", "new", "机器人", "订单"), ("2026-11-16", "机器人", None, "机器人", "量产"),
            ("2026-11-16", "光伏", "new", "光伏", "排产"), ("2026-11-16", "", "new", "情绪", "无主线"),
            ("2026-11-16", "军工", "retired", "军工", "旧"), ("2026-11-15", "有色金属", "new", "铜", "涨价")])
        c.commit(); c.close()

    def tearDown(self):
        self.td.cleanup()

    def doc(self, themes):
        d = good_doc()
        base = d["records"][0]
        d["records"] = [dict(copy.deepcopy(base), id=f"r{i}", theme=t) for i, t in enumerate(themes)]
        return d

    def read(self, p):
        with p.open(encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def write(self, p, rows, fields=None):
        with p.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields or cmp_.FIELDS, lineterminator="\n", extrasaction="ignore")
            w.writeheader(); w.writerows(rows)

    def test_counts(self):
        row = cmp_.compare(self.doc(["机器人", "白酒/消费", None]), self.db)
        self.assertEqual((row["kejian_rows"], row["kejian_rows_no_theme"], row["kejian_themes"]), (4, 1, 2))
        self.assertEqual((row["self_records"], row["self_records_no_theme"], row["self_themes"]), (3, 1, 2))
        self.assertEqual((row["overlap"], row["only_kejian"], row["only_self"]), (1, 1, 1))
        self.assertEqual(row["only_kejian_list"], "光伏")
        self.assertNotIn("军工", row["only_kejian_list"])      # 退役行不算

    def test_no_lesson_day(self):
        d = self.doc(["机器人"]); d["trade_date"] = "20261117"
        row = cmp_.compare(d, self.db)
        self.assertEqual(row["kejian_rows"], 0)
        self.assertEqual(row["note"], "当日无课件入库")

    def test_blind_status_travels_with_the_row(self):
        d = self.doc(["机器人"])
        self.assertEqual((cmp_.compare(d, self.db)["blind"], cmp_.compare(d, self.db)["note"]), ("是", ""))
        d["blind"] = False; d["blind_note"] = "写之前看过"
        row = cmp_.compare(d, self.db)
        self.assertEqual(row["blind"], "否")
        self.assertIn("非盲写", row["note"])

    def test_upsert_keeps_manual_columns_when_nothing_changed(self):
        p = Path(self.td.name) / "compare.csv"
        row = cmp_.compare(self.doc(["机器人"]), self.db)
        self.assertEqual(cmp_.upsert(p, dict(row)), 1)
        self.assertNotIn(b"\r", p.read_bytes())               # 行尾只用 \n，否则过不了 git diff --check
        rows = self.read(p)
        rows[0]["opposite"] = "1"; rows[0]["opposite_note"] = "机器人：两边方向相反"
        self.write(p, rows)
        self.assertEqual(cmp_.upsert(p, dict(row)), 1)           # 同日重跑不增行
        again = self.read(p)[0]
        self.assertEqual((again["opposite"], again["opposite_note"], again["opposite_review"]),
                         ("1", "机器人：两边方向相反", ""))

    def test_manual_columns_flagged_when_self_side_changes(self):
        # V.V. 复核：先填「机器人：方向相反」，再把同日自复盘改成只含光伏，原实现照样保留旧结论
        p = Path(self.td.name) / "compare.csv"
        cmp_.upsert(p, cmp_.compare(self.doc(["机器人"]), self.db))
        rows = self.read(p)
        rows[0]["opposite"] = "1"; rows[0]["opposite_note"] = "机器人：方向相反"
        self.write(p, rows)
        cmp_.upsert(p, cmp_.compare(self.doc(["光伏"]), self.db))
        again = self.read(p)[0]
        self.assertEqual(again["opposite_note"], "机器人：方向相反")          # 内容照留，供重读
        self.assertEqual(again["opposite_review"], "待复核：填写后自复盘记录变过")
        cmp_.upsert(p, cmp_.compare(self.doc(["光伏"]), self.db))           # 再跑一次，标记不会自己消失
        self.assertEqual(self.read(p)[0]["opposite_review"], "待复核：填写后自复盘记录变过")

    def test_manual_columns_flagged_when_lesson_side_changes(self):
        p = Path(self.td.name) / "compare.csv"
        cmp_.upsert(p, cmp_.compare(self.doc(["机器人"]), self.db))
        rows = self.read(p)
        rows[0]["opposite"] = "0"; rows[0]["opposite_note"] = "没有相反的"
        self.write(p, rows)
        c = sqlite3.connect(self.db)
        c.execute("UPDATE industry_signals SET signal_content='改过的正文' WHERE date='2026-11-16' AND etf_anchor='光伏'")
        c.commit(); c.close()
        cmp_.upsert(p, cmp_.compare(self.doc(["机器人"]), self.db))
        self.assertEqual(self.read(p)[0]["opposite_review"], "待复核：填写后课件信号变过")

    def test_rows_written_before_version_binding(self):
        # 旧表没有版本列：已填的人工结论标待复核，没填的不标；别的交易日的行原样留着
        p = Path(self.td.name) / "compare.csv"
        old_fields = [f for f in cmp_.FIELDS if f not in ("opposite_review", "blind", "self_sha256", "kejian_sha256")]
        row = cmp_.compare(self.doc(["机器人"]), self.db)
        self.write(p, [dict(row, trade_date="20261113", opposite="", opposite_note=""),
                       dict(row, opposite="0", opposite_note="同向不同强度")], old_fields)
        cmp_.upsert(p, dict(row))
        rows = {r["trade_date"]: r for r in self.read(p)}
        self.assertEqual(rows["20261116"]["opposite_review"], "待复核：填写时没有记下两侧版本")
        self.assertEqual(rows["20261116"]["opposite_note"], "同向不同强度")
        self.assertEqual((rows["20261113"]["opposite_review"], rows["20261113"]["self_sha256"]), ("", ""))


class StaticTest(unittest.TestCase):
    LESSON_TABLES = re.compile(r"industry_signals|dim[1234]p?_|recap_daily|recap_guide|recap_summary|processed_kejian|"
                               r"hot_sectors|information_gap|cycle_comparison|recap\.db|RECAP_DB")

    def test_inputs_and_validator_never_query_lesson_tables(self):
        src = (ROOT / "tools" / "self_recap_inputs.py").read_text(encoding="utf-8")
        sqls = re.findall(r'"(SELECT[^"]*)"', src)
        self.assertTrue(sqls)
        for s in sqls:
            self.assertIsNone(self.LESSON_TABLES.search(s), s)
        self.assertNotIn("RECAP_DB", src)                        # 输入包脚本不碰复盘库
        vsrc = (ROOT / "tools" / "self_recap_validate.py").read_text(encoding="utf-8")
        self.assertNotIn("sqlite3", vsrc)                        # 校验器不连任何库

    def test_compare_reads_only_industry_signals(self):
        src = (ROOT / "tools" / "self_recap_compare.py").read_text(encoding="utf-8")
        froms = set(re.findall(r"FROM (\w+)", src))
        self.assertEqual(froms, {"industry_signals"})


if __name__ == "__main__":
    unittest.main(verbosity=1)
