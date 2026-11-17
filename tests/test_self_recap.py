"""自复盘三件套的测试（PRD「烛照九阴自复盘取代课件」R3、R4、N1、N2、X1 · 2026-11-17）。

覆盖：记录校验器的正例与负例；输入包的超额算法、美股时钟、缺数不补值、外部工具失败即报错；
逐日对照的计数、退役行排除、NULL 状态保留、重跑保留人工栏；
以及静态约束——输入与校验两个脚本不读任何课件派生表。
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
        "schema_version": 1, "trade_date": "20261116", "observed_at": "2026-11-17T08:00:00+00:00",
        "session": "盘后", "inputs_sha256": "0" * 64,
        "records": [{
            "id": "r1", "theme": None,
            "object": "光通信链条", "main_issue": "海外同业连续走弱，本地是否跟随",
            "anchor": {"name": "LITE", "card": "卡一", "role": "同向印证"},
            "evidence": [{"kind": "market_data", "ref": "market_data.db:us_anchor_daily:LITE:20261113",
                          "asof": "20261113", "value": -4.49}],
            "change": {"baseline": "上一交易日的 20 日超额", "delta": "继续走低"},
            "direction": "宜减",
            "local_confirmation": {"status": "已确认", "basis": "本地主线 5 日与 20 日超额同为负"},
            "priced_in": "本地已连续回落，部分已反映",
            "invalidation": "海外同业 20 日超额转正且本地 5 日超额转正",
            "next_check": "下一交易日盘前看海外同业收盘",
        }],
    }


class ValidateTest(unittest.TestCase):
    def errs(self, mutate):
        d = good_doc()
        mutate(d)
        return val.validate(d, {"机器人"})

    def test_good_passes(self):
        self.assertEqual(val.validate(good_doc(), {"机器人"}), [])

    def test_banned_wording_rejected(self):
        for bad in ("跌破 MA60 则撤", "降到三成", "站回 60 日均线", "成交额低于 1.5 万亿", "三天不涨则退", "出现涨停再看"):
            e = self.errs(lambda d: d["records"][0].__setitem__("invalidation", bad))
            self.assertTrue(any("已舍弃" in x for x in e), bad)

    def test_ordinary_words_not_misfired(self):
        for ok in ("订单完成交付后重判", "板块形成共识", "两成交量相近的标的不比较"):
            e = self.errs(lambda d: d["records"][0].__setitem__("invalidation", ok))
            self.assertFalse(any("已舍弃" in x for x in e), ok)

    def test_lesson_reference_rejected(self):
        e = self.errs(lambda d: d["records"][0]["evidence"][0].__setitem__("ref", "recap.db:industry_signals:123"))
        self.assertTrue(any("课件" in x for x in e))
        e = self.errs(lambda d: d["records"][0].__setitem__("main_issue", "小鲍提到的光通信"))
        self.assertTrue(any("课件" in x for x in e))

    def test_direction_vocabulary(self):
        e = self.errs(lambda d: d["records"][0].__setitem__("direction", "加到六成"))
        self.assertTrue(any("direction" in x for x in e))

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

    def test_empty_records_need_note(self):
        e = self.errs(lambda d: d.__setitem__("records", []))
        self.assertTrue(any("no_change_note" in x for x in e))
        d = good_doc(); d["records"] = []; d["no_change_note"] = "当日外部读数与本地主线都没有新变化"
        self.assertEqual(val.validate(d, set()), [])

    def test_unknown_theme_rejected(self):
        e = self.errs(lambda d: d["records"][0].__setitem__("theme", "不存在的主线"))
        self.assertTrue(any("theme" in x for x in e))

    def test_inputs_sha_binding(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "inputs.json"
            p.write_text("{}", encoding="utf-8")
            d = good_doc()
            self.assertTrue(any("校验值" in x for x in val.validate(d, None, p)))
            d["inputs_sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
            self.assertEqual(val.validate(d, None, p), [])


def make_market_db(path, a_dates, us_dates, theme_code, us_ticker, drop_etf_day=None):
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE daily_market(trade_date TEXT, sh_close REAL, sh_pct_chg REAL, sz_pct_chg REAL, "
              "cyb_pct_chg REAL, volume_trillion REAL)")
    c.execute("CREATE TABLE theme_etf_daily(trade_date TEXT, etf_code TEXT, close REAL, pct_chg REAL, is_benchmark INT)")
    c.execute("CREATE TABLE us_anchor_daily(trade_date TEXT, ticker TEXT, close_adj REAL, pct_chg REAL, is_benchmark INT)")
    for d in a_dates:
        c.execute("INSERT INTO daily_market VALUES(?,?,?,?,?,?)", (d, 3000.0, 0.1, 0.1, 0.1, 1.0))
        c.execute("INSERT INTO theme_etf_daily VALUES(?,?,?,?,1)", (d, inp.BENCHMARK, 1.0, 0.5))
        if d != drop_etf_day:
            c.execute("INSERT INTO theme_etf_daily VALUES(?,?,?,?,0)", (d, theme_code, 1.0, 1.5))
    for d in us_dates:
        c.execute("INSERT INTO us_anchor_daily VALUES(?,?,?,?,1)", (d, inp.BENCHMARK_US, 1.0, 0.2))
        c.execute("INSERT INTO us_anchor_daily VALUES(?,?,?,?,0)", (d, us_ticker, 1.0, 1.2))
    c.commit(); c.close()


class InputsTest(unittest.TestCase):
    def setUp(self):
        self.theme = next(t for t in inp.THEME_ETF if t in inp.THEME_US)
        self.code = inp.THEME_ETF[self.theme][0]
        self.ticker = inp.THEME_US[self.theme][0]
        self.a_dates = [f"202611{d:02d}" for d in range(1, 26)]          # 25 个「交易日」
        self.td = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.td.name, "m.db")

    def tearDown(self):
        self.td.cleanup()

    def theme_row(self, block):
        return next(t for t in block["themes"] if t["theme"] == self.theme)

    def test_excess_math_and_units(self):
        make_market_db(self.db, self.a_dates, self.a_dates, self.code, self.ticker)
        date, block, gaps = inp.local_block(self.db)
        self.assertEqual(date, "20261125")
        t = self.theme_row(block)
        self.assertEqual(t["e5"], 5.0)      # 每日超额 1.0 个百分点 × 5
        self.assertEqual(t["e20"], 20.0)
        self.assertEqual(block["market"]["amount_trillion"], 1.0)

    def test_us_rows_on_or_after_trade_date_excluded(self):
        make_market_db(self.db, self.a_dates, self.a_dates + ["20261126"], self.code, self.ticker)
        _, block, _ = inp.local_block(self.db, "20261125")
        self.assertEqual(self.theme_row(block)["us_anchor"]["last_date"], "20261124")

    def test_missing_day_gives_gap_not_zero(self):
        make_market_db(self.db, self.a_dates, self.a_dates, self.code, self.ticker, drop_etf_day="20261120")
        _, block, gaps = inp.local_block(self.db, "20261125")
        t = self.theme_row(block)
        self.assertIsNone(t["e20"])
        self.assertTrue(any(self.theme in g and "excess_unavailable" in g for g in gaps))

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
        c.execute("CREATE TABLE industry_signals(date TEXT, etf_anchor TEXT, status TEXT)")
        c.executemany("INSERT INTO industry_signals VALUES(?,?,?)", [
            ("2026-11-16", "机器人", "new"), ("2026-11-16", "机器人", None), ("2026-11-16", "光伏", "new"),
            ("2026-11-16", "", "new"), ("2026-11-16", "军工", "retired"), ("2026-11-15", "有色金属", "new")])
        c.commit(); c.close()

    def tearDown(self):
        self.td.cleanup()

    def doc(self, themes):
        d = good_doc()
        base = d["records"][0]
        d["records"] = [dict(copy.deepcopy(base), id=f"r{i}", theme=t) for i, t in enumerate(themes)]
        return d

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

    def test_upsert_keeps_manual_columns(self):
        p = Path(self.td.name) / "compare.csv"
        row = cmp_.compare(self.doc(["机器人"]), self.db)
        self.assertEqual(cmp_.upsert(p, dict(row)), 1)
        self.assertNotIn(b"\r", p.read_bytes())               # 行尾只用 \n，否则过不了 git diff --check
        with p.open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        rows[0]["opposite"] = "1"; rows[0]["opposite_note"] = "机器人：两边方向相反"
        with p.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cmp_.FIELDS, lineterminator="\n"); w.writeheader(); w.writerows(rows)
        self.assertEqual(cmp_.upsert(p, dict(row)), 1)           # 同日重跑不增行
        with p.open(encoding="utf-8") as f:
            again = list(csv.DictReader(f))[0]
        self.assertEqual((again["opposite"], again["opposite_note"]), ("1", "机器人：两边方向相反"))


class StaticTest(unittest.TestCase):
    LESSON_TABLES = re.compile(r"industry_signals|dim[1234]p?_|recap_daily|recap_guide|recap_summary|processed_kejian")

    def test_inputs_and_validator_never_query_lesson_tables(self):
        src = (ROOT / "tools" / "self_recap_inputs.py").read_text(encoding="utf-8")
        sqls = re.findall(r'"(SELECT[^"]*)"', src)
        self.assertTrue(sqls)
        for s in sqls:
            self.assertIsNone(self.LESSON_TABLES.search(s), s)
        vsrc = (ROOT / "tools" / "self_recap_validate.py").read_text(encoding="utf-8")
        self.assertNotIn("sqlite3", vsrc)                        # 校验器不连任何库

    def test_compare_reads_only_industry_signals(self):
        src = (ROOT / "tools" / "self_recap_compare.py").read_text(encoding="utf-8")
        froms = set(re.findall(r"FROM (\w+)", src))
        self.assertEqual(froms, {"industry_signals"})


if __name__ == "__main__":
    unittest.main(verbosity=1)
