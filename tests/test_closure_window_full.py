"""兑现引擎「观察期满」的文字与计数（tools/closure_engine.py、tools/gen_daily_report.py · 2026-11-17）。

来由：brain/烛照九阴/GOTCHAS.md 的 ERR-20261117-006。观察窗口（WINDOW 个交易日）走完后引擎不再往后算，
原先文字照旧写「兑现中」「现 +x%」。Doctor 裁定保留窗口，窗口满时改文字标期满、条数分开数。
守五件事：
  一、窗口没走完的信号，文字与改动前一字不差；
  二、窗口走完的信号，文字以「观察期满（截至 窗口末日）·」开头，「现」改成「期末」，之后行情再多也不变；
  三、状态、累计、峰值、各日期这些数值字段与改动前相同（只动文字）；
  四、原有阶段用词（逾期、兑现初期、暗态）原样保留，日报生成器按字眼做的判断不变；
  五、日报生成器对期满信号的状态名与兑现度卡不再用「兑现中」「仍需观察」的说法，未期满的输出不变。
只调用纯函数，不连库、不写文件。
"""
import datetime, importlib, importlib.machinery, importlib.util, os, re, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
for p in (ROOT, TOOLS):
    if p not in sys.path:
        sys.path.insert(0, p)
CE = importlib.import_module("closure_engine")
G = importlib.import_module("gen_daily_report")
# 改动前的引擎。备份不入版本库，只在本机；不在时逐字段比对跳过
ORIG = os.path.join(TOOLS, "_bak", "closure_engine.py.bak_2026-11-17_观察期满改前")

W = CE.WINDOW
DISC = "20250101"


def _dates(n):
    """发现日之后连续 n 个「交易日」（工作日即可，只要求递增且唯一）。"""
    out, d = [], datetime.date(2025, 1, 1)
    while len(out) < n:
        d += datetime.timedelta(days=1)
        if d.weekday() < 5:
            out.append(d.strftime("%Y%m%d"))
    return out


def _run(xs, engine=CE):
    """xs：发现日之后逐日的超额收益（小数）。"""
    ds = _dates(len(xs))
    return engine.run_machine(dict(zip(ds, xs)), ds, DISC), ds


def _iso(d):
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}"


# 几条有代表性的走势，长度都严格等于 n（不足补 0，超出截断）
def _fit(xs, n):
    return (list(xs) + [0.0] * n)[:n]


def flat_down(n):            # 一直不启动 → open
    return [-0.001] * n


def rise_then_hold(n):       # 早早启动后小幅震荡 → closing
    return _fit([0.03] + [0.0005, -0.0005] * (n // 2), n)


def rise_then_dip(n):        # 启动后回撤 3 到 5 个点之间 → closing·回撤近警戒
    return _fit([0.08] + [0.0] * max(n - 2, 0) + [-0.04], n)


def rise_then_crash(n):      # 启动后回撤超过 5 个点 → dormant
    return _fit([0.08, -0.07], n)


def late_start(n):           # 窗口最后 3 天才启动 → closing·兑现初期
    return _fit([0.0] * max(n - 3, 0) + [0.03, 0.001, 0.001], n)


# 会点亮的走势（生产里期满信号大多点亮过）：启动 → 回撤转暗态 → 连涨 4 天点亮回二段
_RELIT = [0.08, -0.06, 0.025, 0.025, 0.025, 0.025]


def relit_strong(n):         # 点亮后维持 → closing·二段主升
    return _fit(_RELIT, n)


def relit_steady(n):         # 点亮后小幅回落 → closing·二段兑现进行
    return _fit(_RELIT + [-0.025], n)


def relit_then_dormant(n):   # 点亮后再回撤 → dormant·已点亮 1 次
    return _fit(_RELIT + [-0.06], n)


SHAPES = (flat_down, rise_then_hold, rise_then_dip, rise_then_crash, late_start,
          relit_strong, relit_steady, relit_then_dormant)


class NotFull(unittest.TestCase):
    """一、窗口没走完：不加任何标记。"""

    def test_no_tag_before_window_ends(self):
        for shape in SHAPES:
            for n in (1, 11, 40, W - 1):
                r, _ = _run(shape(n))
                self.assertFalse(r["window_full"], (shape.__name__, n))
                self.assertIsNone(r["window_end"])
                self.assertNotIn(CE.WINDOW_FULL_TAG, r["gap_desc"])
                self.assertNotIn("期末", r["gap_desc"])

    def test_text_equals_describe_output(self):
        r, _ = _run(rise_then_dip(60))
        self.assertEqual(r["gap_desc"], "兑现中·回撤近警戒（峰值+8.0%→现+4.0%）")
        r, _ = _run(flat_down(40))
        self.assertEqual(r["gap_desc"], "⚠️逾期未启动（40日，累计-4.0%）——逻辑存疑或锚不对")


class Full(unittest.TestCase):
    """二、窗口走完：标期满、带截止日、不再用「现」。"""

    def test_tag_and_end_date_on_the_day_window_fills(self):
        for shape in SHAPES:
            r, ds = _run(shape(W))
            self.assertTrue(r["window_full"], shape.__name__)
            self.assertEqual(r["window_end"], ds[W - 1])
            self.assertTrue(r["gap_desc"].startswith(f"观察期满（截至 {_iso(ds[W - 1])}）·"), r["gap_desc"])
            self.assertIsNone(re.search(r"现[+-]", r["gap_desc"]), r["gap_desc"])   # 「兑现」里的现字不算

    def test_frozen_after_window(self):
        for shape in SHAPES:
            base, ds = _run(shape(W))
            for extra in (1, 30):
                xs = shape(W) + [0.05] * extra          # 窗口之后行情大涨也不影响
                r, _ = _run(xs)
                self.assertEqual(r, base, (shape.__name__, extra))

    def test_exact_texts(self):
        end = _iso(_dates(W)[-1])
        r, _ = _run(rise_then_dip(W))
        self.assertEqual(r["gap_desc"], f"观察期满（截至 {end}）·兑现中·回撤近警戒（峰值+8.0%→期末+4.0%）")
        r, _ = _run(flat_down(W))
        self.assertEqual(r["gap_desc"], f"观察期满（截至 {end}）·⚠️逾期未启动（{W}日，累计-12.0%）——逻辑存疑或锚不对")
        r, _ = _run(rise_then_crash(W))
        self.assertEqual(r["gap_desc"], f"观察期满（截至 {end}）·暗态·深回吐候二段（峰值+8.0%→期末+1.0%）")

    def test_exact_texts_after_relight(self):
        end = _iso(_dates(W)[-1])
        r, _ = _run(relit_strong(W))
        self.assertEqual((r["gap_status"], r["relit_count"]), ("closing", 1))
        self.assertEqual(r["gap_desc"], f"观察期满（截至 {end}）·二段主升兑现中（{W}日，累计+12.0%，峰值+12.0%）")
        r, _ = _run(relit_steady(W))
        self.assertEqual(r["gap_desc"], f"观察期满（截至 {end}）·二段兑现进行（{W}日，累计+9.5%）")
        r, _ = _run(relit_then_dormant(W))
        self.assertEqual((r["gap_status"], r["relit_count"]), ("dormant", 1))
        self.assertEqual(r["gap_desc"], f"观察期满（截至 {end}）·暗态·已兑现候二段（峰值+12.0%→期末+6.0%）·已点亮1次")

    def test_mark_is_pure_prefix_plus_one_replacement(self):
        for shape in SHAPES:
            r, ds = _run(shape(W))
            plain = CE.describe(r["gap_status"], W, W, _days_run(r, ds), r["excess_cum"], r["excess_peak"],
                                r["relit_count"])
            self.assertEqual(r["gap_desc"], f"观察期满（截至 {_iso(ds[W - 1])}）·" + plain.replace("→现", "→期末"))


def _days_run(r, ds):
    return sum(1 for d in ds[:W] if r["date_realized"] and d >= r["date_realized"])


class KeywordsKept(unittest.TestCase):
    """四、下游按字眼做判断的词原样保留。"""

    def test_overdue_kept(self):
        r, _ = _run(flat_down(W))
        self.assertEqual(r["gap_status"], "open")
        self.assertIn("逾期", r["gap_desc"])

    def test_early_stage_kept(self):
        r, _ = _run(late_start(W))
        self.assertEqual(r["gap_status"], "closing")
        self.assertIn("兑现初期", r["gap_desc"])

    def test_dormant_kept(self):
        r, _ = _run(rise_then_crash(W))
        self.assertEqual(r["gap_status"], "dormant")
        self.assertIn("暗态", r["gap_desc"])

    def test_day_count_regex_does_not_hit_the_date(self):
        # 生成器用 (\d+)日 取天数：截止日写成 2025-06-18 这种形式，不会被当成天数
        r, _ = _run(flat_down(W))
        self.assertEqual(re.search(r"(\d+)日", r["gap_desc"]).group(1), str(W))
        r, _ = _run(rise_then_dip(W))
        self.assertIsNone(re.search(r"(\d+)日", r["gap_desc"]))


class Counts(unittest.TestCase):
    """期满条数按最终写进库的文字数。"""

    def test_counts_by_status(self):
        rows = [_run(shape(W))[0] for shape in SHAPES] + [_run(flat_down(40))[0]]
        self.assertEqual(CE.window_full_counts(rows), {"open": 1, "closing": 5, "dormant": 2})

    def test_rewritten_short_signals_not_counted(self):
        # 方向为空的信号，文字会被后处理改写成不带期满标记的说法：不计入
        r, _ = _run(rise_then_dip(W))
        short = dict(r, gap_desc="空头风险信号·不正向追踪")
        flip = dict(r, gap_desc="买入转卖出·空头风险·观察中")
        self.assertEqual(CE.window_full_counts([short, flip]), {})
        self.assertEqual(CE.window_full_counts([short, r]), {"closing": 1})

    def test_rows_without_text_are_safe(self):
        rows = [{"gap_status": "no_anchor", "gap_desc": "无锚未跟踪（情绪周期类或覆盖洞）"},
                {"gap_status": "no_data", "gap_desc": None}, {}]
        self.assertEqual(CE.window_full_counts(rows), {})


@unittest.skipUnless(os.path.exists(ORIG), "改动前的引擎备份不在本机")
class SameNumbersAsBefore(unittest.TestCase):
    """三、与改动前逐字段相同，只有期满信号的文字不同。"""

    @classmethod
    def setUpClass(cls):
        # 备份文件名不以 .py 结尾，要指明按源码装载
        loader = importlib.machinery.SourceFileLoader("closure_engine_orig", ORIG)
        spec = importlib.util.spec_from_loader("closure_engine_orig", loader)
        cls.OLD = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.OLD)

    def test_fields_equal(self):
        for shape in SHAPES:
            for n in (1, 11, 40, W - 1, W, W + 1, W + 40):
                new, ds = _run(shape(n))
                old, _ = _run(shape(n), self.OLD)
                for k in old:
                    if k == "gap_desc":
                        continue
                    self.assertEqual(new[k], old[k], (shape.__name__, n, k))
                if n < W:
                    self.assertEqual(new["gap_desc"], old["gap_desc"], (shape.__name__, n))
                else:
                    self.assertEqual(new["gap_desc"],
                                     f"观察期满（截至 {_iso(ds[W - 1])}）·" + old["gap_desc"].replace("→现", "→期末"))
                self.assertEqual(set(new) - set(old), {"window_full", "window_end"})


class ReportWording(unittest.TestCase):
    """五、日报生成器的状态名与兑现度卡。"""

    FULL_CLOSING = "观察期满（截至 2026-07-30）·二段兑现中·回撤近警戒（峰值+19.3%→期末+7.0%）"
    FULL_CLOSING_DAYS = "观察期满（截至 2026-10-29）·二段兑现进行（118日，累计+9.5%）"
    FULL_OPEN = "观察期满（截至 2026-11-05）·⚠️逾期未启动（120日，累计-13.7%）——逻辑存疑或锚不对"

    def test_tags_agree(self):
        self.assertEqual(G.WINDOW_FULL_TAG, CE.WINDOW_FULL_TAG)

    def test_status_name(self):
        self.assertEqual(G.status_zh("closing", self.FULL_CLOSING), "观察期满")
        self.assertEqual(G.status_zh("open", self.FULL_OPEN), "观察期满")
        # 暗态、无锚等其它状态不改名；没有文字或未期满的照旧
        self.assertEqual(G.status_zh("dormant", "观察期满（截至 2026-07-30）·暗态·已兑现候二段（峰值+9.0%→期末+5.0%）"), "暗态")
        self.assertEqual(G.status_zh("closing", "兑现进行（20日，累计+3.0%）"), "兑现中")
        self.assertEqual(G.status_zh("open", ""), "观察中")
        self.assertEqual(G.status_zh("no_anchor"), "无锚点")
        self.assertEqual(G.status_zh("未知状态"), "未知状态")

    def test_fulfill_card_for_full_window(self):
        f = G.fulfill_of("closing", self.FULL_CLOSING, 0.0701)
        self.assertEqual(f["v"], "观察期满")
        self.assertEqual(f["d"], "观察期满 · 期末累计+7.0%")
        self.assertEqual(f["sent"], "观察窗口已走完，期末累计 +7.0%；数值停在窗口末日，不再更新。")
        f = G.fulfill_of("closing", self.FULL_CLOSING_DAYS, 0.095)
        self.assertEqual(f["d"], "观察期满 · 期末累计+9.5%")
        f = G.fulfill_of("closing", self.FULL_CLOSING, None)
        self.assertEqual((f["d"], f["sent"]), ("观察期满", "观察窗口已走完；数值停在窗口末日，不再更新。"))
        f = G.fulfill_of("open", self.FULL_OPEN, -0.137)
        self.assertEqual((f["v"], f["d"]), ("未启动", "观察期满 · 未启动"))
        for f in (G.fulfill_of("closing", self.FULL_CLOSING, 0.07), G.fulfill_of("open", self.FULL_OPEN, -0.1)):
            for word in ("仍需观察", "继续观察"):
                self.assertNotIn(word, f["d"] + f["sent"])
            self.assertIsNone(re.search(r"现[+-]|→现", f["d"] + f["sent"]))

    def test_fulfill_card_unchanged_when_not_full(self):
        self.assertEqual(G.fulfill_of("closing", "二段兑现进行（118日，累计+9.5%）", 0.095),
                         dict(v="兑现中", d="118日 · 累计+9.5%", w=52, sent="跟踪 118 日，累计 +9.5%，仍需观察持续性。"))
        self.assertEqual(G.fulfill_of("closing", "兑现中·回撤近警戒（峰值+19.3%→现+7.0%）", 0.07),
                         dict(v="兑现中", d="兑现中 · 口径待补", w=52, sent="已进入价格兑现，数值口径待补。"))
        self.assertEqual(G.fulfill_of("open", "未启动（20日，累计-1.0%）", -0.01),
                         dict(v="未启动", d="潜伏期 · 出现20日", w=12, sent="价格兑现尚未展开，继续观察锚点是否出现。"))
        self.assertEqual(G.fulfill_of("dormant", "观察期满（截至 2026-07-30）·暗态·已兑现候二段（峰值+9.0%→期末+5.0%）")["v"], "暗态")


if __name__ == "__main__":
    unittest.main()
