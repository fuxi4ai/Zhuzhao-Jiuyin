"""日报 R5 四处加强（tools/gen_daily_report_r5.py · 生成器副本）。

PRD：brain/logs/checkpoints/2026-11-17_烛照九阴自复盘取代课件_PRD.md 的 R5 与 X1。
守四件事：
  一、锚背离补反向提示——同向锚强而 A 股主线弱时出黄色风险；没有同向锚、温度计类锚、缺数都不出；
  二、「确认走强」候选写明何时移出本栏——只有同向锚的主线才写锚那一项，不含买卖动作；
  三、事件日历——议息会次读日历文件里全部年份的键；交割日按第三个周五推算、遇休市顺延、窗口之外不显示；
  四、盘前读数的角色标签——归属照风险温度带的现行配置取，温度带不读的读数不加标签。
另守 X1：副本相对原件新增的行里不出现已裁定舍弃的词。
从副本模块导入；只调用不连库的函数，不生成日报、不写任何文件（议息日历用临时目录里的构造文件）。
"""
import datetime, difflib, importlib, json, os, re, sys, tempfile, types, unittest, warnings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
SRC = os.path.join(TOOLS, "gen_daily_report_r5.py")
ORIG = os.path.join(TOOLS, "gen_daily_report.py")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)
G = importlib.import_module("gen_daily_report_r5")

ECHO = {"tkr": "LITE", "kind": "echo", "ex20": 12.3}
THERMO = {"tkr": "TSM", "kind": "thermo", "ex20": 12.3}
ACTION_WORDS = ("买入", "卖出", "加仓", "减仓", "清仓", "止损", "止盈")


def _src():
    with open(SRC, encoding="utf-8") as fh:
        return fh.read()


class AnchorLead(unittest.TestCase):
    """一、反向背离。"""

    def test_triggers_on_constructed_input(self):
        r = G.anchor_lead_risk("光模块", -6.2, ECHO)
        self.assertEqual(r["lvl"], "黄")
        self.assertEqual(r["txt"], "锚强而本地未跟：光模块 锚 LITE 20日超额 +12.3%，"
                                   "A股20日超额 -6.2%（本地资金未认，观察）")

    def test_no_anchor_no_risk(self):
        self.assertIsNone(G.anchor_lead_risk("白酒", -8.0, None))

    def test_thermo_anchor_no_risk(self):
        self.assertIsNone(G.anchor_lead_risk("半导体", -8.0, THERMO))

    def test_missing_numbers_no_risk(self):
        self.assertIsNone(G.anchor_lead_risk("光模块", None, ECHO))
        self.assertIsNone(G.anchor_lead_risk("光模块", -8.0, {"tkr": "LITE", "kind": "echo"}))

    def test_boundaries_are_strict(self):
        at_us = dict(ECHO, ex20=G.ANCHOR_LEAD_US_EX20)
        self.assertIsNone(G.anchor_lead_risk("光模块", -8.0, at_us))             # 锚恰在阈值上：不出
        self.assertIsNone(G.anchor_lead_risk("光模块", G.ANCHOR_LEAD_CN_E20, ECHO))
        self.assertIsNone(G.anchor_lead_risk("光模块", 3.0, ECHO))          # A 股也强：不算背离
        self.assertIsNone(G.anchor_lead_risk("光模块", -2.1, ECHO))         # A 股只是略弱（零到阈值之间）：不出
        self.assertIsNone(G.anchor_lead_risk("光模块", -8.0, dict(ECHO, ex20=4.0)))

    def test_thresholds_are_named_constants(self):
        # Doctor 2026-11-17 裁定：锚高于 +10、A 股低于 -5
        self.assertEqual((G.ANCHOR_LEAD_US_EX20, G.ANCHOR_LEAD_CN_E20), (10.0, -5.0))
        old = G.ANCHOR_LEAD_CN_E20
        try:
            G.ANCHOR_LEAD_CN_E20 = 0.0                                     # 换成另一组候选阈值，判定随常量变
            self.assertIsNotNone(G.anchor_lead_risk("光模块", -2.1, ECHO))
            self.assertIsNone(G.anchor_lead_risk("光模块", 0.5, ECHO))
        finally:
            G.ANCHOR_LEAD_CN_E20 = old

    def test_never_overlaps_red_divergence(self):
        # 红色背离要锚 20 日超额低于 ANCHOR_BREAK_US_EX20；反向提示要高于 ANCHOR_LEAD_US_EX20，两者不会同时成立
        self.assertLess(G.ANCHOR_BREAK_US_EX20, G.ANCHOR_LEAD_US_EX20)
        self.assertIsNone(G.anchor_lead_risk("光模块", 8.0, dict(ECHO, ex20=-12.0)))

    def test_wired_into_risks_without_touching_entry_logic(self):
        s = _src()
        self.assertIn('_lead = anchor_lead_risk(t["short"], t["e20"], t["us"])', s)
        self.assertIn("risks.append(_lead)", s)
        # 入栏闸与红色背离的写法仍在，且共用同一个常量
        self.assertIn('anchor_ok = not (t["us"] and t["us"]["kind"] == "echo" '
                      'and t["us"]["ex20"] < ANCHOR_BREAK_US_EX20)', s)
        self.assertIn('u["ex20"] < ANCHOR_BREAK_US_EX20 and t["e20"] > 5', s)
        self.assertEqual(G.ANCHOR_BREAK_US_EX20, -10.0)


class OppExit(unittest.TestCase):
    """二、何时移出本栏。"""

    def test_echo_anchor_gets_anchor_clause(self):
        t = G.opp_exit_text({"tkr": "NVDA", "kind": "echo", "ex20": 3.0}, 5)
        self.assertIn("20日或5日超额不再为正", t)
        self.assertIn("排位跌出容量上限（当日上限为前 5 强，本栏至多列 4 条）", t)
        self.assertIn("同向锚 NVDA 的20日超额低于 -10%", t)

    def test_no_echo_anchor_no_anchor_clause(self):
        for us in (None, {"tkr": "TSM", "kind": "thermo", "ex20": -20.0}):
            self.assertNotIn("同向锚", G.opp_exit_text(us, 5))

    def test_unknown_capacity(self):
        t = G.opp_exit_text(None, None)
        self.assertIn("当日上限未知", t)
        self.assertNotIn("None", t)

    def test_only_says_when_removed(self):
        t = G.opp_exit_text({"tkr": "NVDA", "kind": "echo", "ex20": 3.0}, 5)
        self.assertTrue(t.startswith("出现以下任一情况即移出本栏："))
        for w in ACTION_WORDS:
            self.assertNotIn(w, t)

    def test_rendered_on_each_candidate_card(self):
        s = _src()
        self.assertIn('"exit": opp_exit_text(t["us"], budget)', s)
        self.assertIn('<span class="dk">何时移出本栏</span>', s)
        self.assertIn("D[\"opps\"] = opps[:OPP_MAX_ROWS]", s)
        self.assertEqual(G.OPP_MAX_ROWS, 4)


class FomcCalendar(unittest.TestCase):
    """三（上）、议息会次读全部年份。"""

    CAL = {"_source": "x", "_usage": "y", "meetings_note": "不是列表，跳过",
           "meetings_2031": [{"start": "20310128", "end": "20310129", "sep": None}],
           "meetings_2030": [{"start": "20301210", "end": "20301211", "sep": True},
                             {"start": "20300129", "end": "20300130", "sep": False},
                             {"start": "", "end": "20300501"}]}

    def test_reads_every_year_key_sorted(self):
        ms = G.fomc_meetings(self.CAL)
        self.assertEqual([m["start"] for m in ms], ["20300129", "20301210", "20310128"])

    def test_empty_inputs(self):
        self.assertEqual(G.fomc_meetings({}), [])
        self.assertEqual(G.fomc_meetings(None), [])

    def _note(self, data_day):
        with tempfile.TemporaryDirectory() as tmp:
            os.mkdir(os.path.join(tmp, "config"))
            with open(os.path.join(tmp, "config", "fomc_calendar.json"), "w", encoding="utf-8") as fh:
                json.dump(self.CAL, fh)
            real = G.config
            G.config = types.SimpleNamespace(PROJECT_ROOT=__import__("pathlib").Path(tmp))
            try:
                with warnings.catch_warnings():          # 生成器原有写法 json.load(open(...)) 不关文件，与本测试无关
                    warnings.simplefilter("ignore", ResourceWarning)
                    return G.fomc_note({"data_day": data_day})
            finally:
                G.config = real

    def test_note_reads_extra_year_key(self):
        n = self._note("20310122")                       # 距 2031-01-28 六天，只有 meetings_2031 里有
        self.assertIn("FOMC 1/28-29 · 会前 6 天", n)
        self.assertIn("FOMC 12/10-11·含点阵图 · 决议窗", self._note("20301211"))

    def test_note_outside_window_is_empty(self):
        self.assertEqual(self._note("20300601"), "")

    def test_no_hardcoded_year_in_code(self):
        s = _src()
        self.assertNotIn('cal.get("meetings_2026"', s)
        self.assertIn("for m in fomc_meetings(cal):", s)

    def test_real_calendar_file(self):
        with open(os.path.join(ROOT, "config", "fomc_calendar.json"), encoding="utf-8") as fh:
            cal = json.load(fh)
        # 既有的 2026 年会次不得被改动
        self.assertEqual([(m["start"], m["end"], m["sep"]) for m in cal["meetings_2026"]], [
            ("20260127", "20260128", False), ("20260317", "20260318", True),
            ("20260428", "20260429", False), ("20260616", "20260617", True),
            ("20260728", "20260729", False), ("20260915", "20260916", True),
            ("20261027", "20261028", False), ("20261208", "20261209", True)])
        ms = G.fomc_meetings(cal)
        self.assertGreaterEqual(len(ms), 8)
        for m in ms:
            s = datetime.datetime.strptime(m["start"], "%Y%m%d").date()
            e = datetime.datetime.strptime(m["end"], "%Y%m%d").date()
            self.assertEqual((e - s).days, 1, m)
        for k, v in cal.items():
            if k.startswith("meetings_"):
                self.assertTrue(all(m["start"][:4] == k[-4:] for m in v), k)


class Delivery(unittest.TestCase):
    """三（下）、股指期货交割日。"""

    def test_third_friday(self):
        self.assertEqual(G.third_friday(2026, 11), datetime.date(2026, 11, 20))
        self.assertEqual(G.third_friday(2026, 12), datetime.date(2026, 12, 18))
        self.assertEqual(G.third_friday(2027, 1), datetime.date(2027, 1, 15))
        self.assertEqual(G.third_friday(2027, 10), datetime.date(2027, 10, 15))   # 当月 1 日就是周五
        for y in (2026, 2027, 2028):
            for m in range(1, 13):
                d = G.third_friday(y, m)
                self.assertEqual(d.weekday(), 4)
                self.assertTrue(15 <= d.day <= 21)

    def test_open_day_is_checked(self):
        self.assertEqual(G.delivery_day(2026, 11, {"20261120": True}),
                         (datetime.date(2026, 11, 20), True))

    def test_holiday_rolls_to_next_trading_day(self):
        cal = {"20261120": False, "20261121": False, "20261122": False, "20261123": True}
        self.assertEqual(G.delivery_day(2026, 11, cal), (datetime.date(2026, 11, 23), True))

    def test_calendar_miss_falls_back_to_third_friday(self):
        self.assertEqual(G.delivery_day(2026, 11, {}), (datetime.date(2026, 11, 20), False))
        self.assertEqual(G.delivery_day(2026, 11, None), (datetime.date(2026, 11, 20), False))
        # 查到休市、但后面的日子日历里没有：不猜，退回第三个周五并标未核对
        self.assertEqual(G.delivery_day(2026, 11, {"20261120": False, "20261121": False}),
                         (datetime.date(2026, 11, 20), False))

    def test_text_inside_window(self):
        self.assertEqual(G.delivery_note_text("20261116", {"20261120": True}),
                         "股指期货交割日前 4 天（2026-11-20）")
        self.assertEqual(G.delivery_note_text("20261116", {}),
                         "股指期货交割日前 4 天（2026-11-20）·按第三个周五推算")
        self.assertEqual(G.delivery_note_text("20261113", {}),
                         "股指期货交割日前 7 天（2026-11-20）·按第三个周五推算")

    def test_text_on_the_day(self):
        self.assertEqual(G.delivery_note_text("20261120", {"20261120": True}), "股指期货交割日（2026-11-20）")

    def test_text_outside_window_is_empty(self):
        self.assertEqual(G.delivery_note_text("20261112", {}), "")        # 距交割日 8 天
        self.assertEqual(G.delivery_note_text("20261123", {}), "")        # 当月已过，下月还远
        self.assertEqual(G.delivery_note_text("", {}), "")
        self.assertEqual(G.delivery_note_text(None, {}), "")
        self.assertEqual(G.delivery_note_text("2026-11", {}), "")

    def test_text_follows_rolled_date(self):
        cal = {"20261119": True, "20261120": False, "20261121": False, "20261122": False, "20261123": True}
        self.assertEqual(G.delivery_note_text("20261119", cal), "股指期货交割日前 4 天（2026-11-23）")
        self.assertEqual(G.delivery_note_text("20261123", cal), "股指期货交割日（2026-11-23）")

    def test_text_crosses_year(self):
        self.assertEqual(G.delivery_note_text("20270111", {}),
                         "股指期货交割日前 4 天（2027-01-15）·按第三个周五推算")
        self.assertEqual(G.delivery_note_text("20261228", {}), "")        # 12 月的已过，1 月的还远

    def test_text_gives_date_only(self):
        for day in ("20261116", "20261120", "20270111"):
            t = G.delivery_note_text(day, {})
            for w in ACTION_WORDS:
                self.assertNotIn(w, t)

    def test_html_wrapper(self):
        h = G.delivery_note({"data_day": "20261116", "trade_cal": {}})
        self.assertIn('class="rr-fomc"', h)
        self.assertIn("股指期货交割日前 4 天（2026-11-20）·按第三个周五推算", h)
        self.assertEqual(G.delivery_note({"data_day": "20261112", "trade_cal": {}}), "")
        self.assertEqual(G.delivery_note({}), "")

    def test_placed_next_to_fomc_note(self):
        self.assertIn("fomc_chunk = fomc_note(D) + delivery_note(D)", _src())


class PremarketRole(unittest.TestCase):
    """四、盘前读数的角色标签。"""

    CFG = {"_meta": {"function_version": "s2"},
           "f1": {"semi_codes": ["NASDAQ", "NVDA"], "asia_codes": ["JP_FUT"]},
           "f5": {"bond_scoring": False}}

    def test_follows_config(self):
        r = lambda c: G.premarket_role(c, self.CFG)
        self.assertEqual([r("NASDAQ"), r("NVDA"), r("JP_FUT")], ["环境层"] * 3)
        self.assertEqual(r("CNH"), "触发层")
        self.assertEqual(r("US10Y"), "信息层")
        self.assertEqual([r("AVGO"), r("SPCX"), r("US30Y"), r("KR_PROXY")], [""] * 4)   # 配置里没有 → 不标

    def test_bond_leg_follows_bond_scoring(self):
        cfg = dict(self.CFG, f5={"bond_scoring": True})
        self.assertEqual(G.premarket_role("US10Y", cfg), "触发层")

    def test_other_function_version_gets_no_label(self):
        cfg = dict(self.CFG, _meta={"function_version": "v1"})
        for c in ("NASDAQ", "CNH", "US10Y"):
            self.assertEqual(G.premarket_role(c, cfg), "")
        self.assertEqual(G.premarket_role("NASDAQ", None), "")

    def test_current_config_table(self):
        """现行 config/risk_factors.json 下，盘前区每项读数的归属。配置改了这里会红，提示复核标签。"""
        want = {"CNH": "触发层", "US10Y": "信息层", "NASDAQ": "环境层", "NVDA": "环境层", "AVGO": "环境层",
                "LITE": "环境层", "SPCX": "", "JP_FUT": "环境层", "KR_SAMSUNG": "环境层", "KR_HYNIX": "环境层"}
        self.assertEqual({c: G.premarket_role(c, G.RISK_CFG) for c in want}, want)

    def test_layers_still_match_thermometer_code(self):
        s = _src()
        self.assertIn('_ENV_IDS = ("F1", "A6", "B6")', s)                  # 环境层含 F1
        self.assertIn('_f45 = [f for f in F if f.get("id") in ("F4", "F5")]', s)   # 触发层是 F4/F5
        self.assertIn('+ ("" if _bond_scoring else "·信息层"))', s)          # 美债腿不计温时是信息层

    def test_rendered_next_to_each_reading(self):
        row = lambda code, pct: {"code": code, "symbol": code, "name": code, "kind": "us_stock",
                                 "date": "20261113", "close": 100.0, "pct": pct, "note": ""}
        intl = {c: row(c, 1.0) for c in ("NASDAQ", "NVDA", "AVGO", "LITE", "SPCX", "JP_FUT",
                                         "KR_SAMSUNG", "KR_HYNIX", "US10Y", "US30Y")}
        D = {"intl": intl, "fred": {},
             "fx": {"cur": 7.1, "prev": 7.09, "series": [("11-12", 7.08), ("11-13", 7.1)], "src": "测试"}}
        h = G.external_pricing_section(D)
        tag = lambda r: f'<span class="thermo" title="在风险温度带里属于{r}">{r}</span>'
        self.assertIn("美元兑离岸人民币(USD/CNH)" + tag("触发层"), h)
        self.assertIn('^TNX ▸</span>' + tag("信息层"), h)
        self.assertEqual(h.count(tag("环境层")), 7)       # 纳指、英伟达、博通、Lumentum、日经期货、三星、海力士
        self.assertEqual(h.count(tag("触发层")), 1)
        self.assertEqual(h.count(tag("信息层")), 1)
        spcx = h[h.index("SpaceX"):h.index("SpaceX") + 120]
        self.assertNotIn("thermo", spcx)                  # 温度带不读 SpaceX → 不加标签

    def test_rendered_when_reading_missing(self):
        h = G.external_pricing_section({"intl": {}, "fred": {}, "fx": {}})
        self.assertIn('<span class="ext-rn">英伟达<span class="thermo"', h)
        self.assertIn('^TNX</span><span class="thermo"', h)
        self.assertNotIn('<span class="ext-rn">SpaceX<span class="thermo"', h)


class X1Words(unittest.TestCase):
    """X1：副本相对原件新增的行里，不出现已裁定舍弃的内容。原件不在（副本已转正）时跳过。"""

    BANNED = ("MA60", "60日均线", "60 日均线", "成仓", "成交额", "止损", "掉期", "情绪周期", "涨停", "连板")
    TENTHS = re.compile(r"[一二两三四五六七八九十半\d]\s*成(?!交|立|为|功|本|员|分|熟|果|长|一)")

    def _added(self):
        with open(ORIG, encoding="utf-8") as fh:
            a = fh.read().split("\n")
        b = _src().split("\n")
        return [l[1:] for l in difflib.unified_diff(a, b, n=0, lineterm="")
                if l.startswith("+") and not l.startswith("+++")]

    @unittest.skipUnless(os.path.exists(ORIG), "原件不在，无从比对新增行")
    def test_added_lines_are_clean(self):
        added = self._added()
        self.assertGreater(len(added), 50)
        for line in added:
            for w in self.BANNED:
                self.assertNotIn(w, line)
            self.assertIsNone(self.TENTHS.search(line), line)

    def test_new_texts_are_clean(self):
        texts = [G.anchor_lead_risk("光模块", -6.2, ECHO)["txt"],
                 G.opp_exit_text({"tkr": "NVDA", "kind": "echo", "ex20": 3.0}, 5),
                 G.opp_exit_text(None, None),
                 G.delivery_note_text("20261116", {}), G.delivery_note_text("20261120", {"20261120": True})]
        for t in texts:
            for w in self.BANNED:
                self.assertNotIn(w, t)
            self.assertIsNone(self.TENTHS.search(t), t)


if __name__ == "__main__":
    unittest.main()
