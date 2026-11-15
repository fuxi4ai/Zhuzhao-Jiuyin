"""日报「隔日关注」栏渲染（tools/gen_daily_report.py · integration_section）。

2026-11-14 栏目美化后，渲染端会把摘录正文重排成账目行（拆「；」「 / 」、展开句尾括注清单）。
本测试守住三件事：
  ① 只重排不改字——历史全部摘录条目（docs/daily_integration_*.json）与构造样例：
     页面上每一格文字都必须是原文里逐字连续的一段，各格按原文顺序排列，
     格与格之间在原文里只允许隔着分隔符（空白 ；，/ ： —— 与被拆开的那层括号）；
  ② 数字不拆坏、不误导——正负号跟着数字走、区间算一个数、指数名的尾数不被吞、
     门槛与旧值不当要点数、并列分组不压平、拿不准的整行照原文；
     另有分格通则（CellRules）：凡排成账目行的，名目不得以正负号/横线结尾、附注不得以「区间号+数字」开头、
     要点数必须是白名单形态——用历史条目、构造样例和一万多条组合写法一起压；
  ③ 约定不丢——着色只读标注（无标题也看得见）、非法标注忽略、转义、今日无、固定槽位恒显、持仓命中提示、页脚来源与 as_of。
只截取栏目代码段执行（不 import 整个生成器，不连库、不写任何文件）。
2026-11-14 两轮独立复验（未参与实施的审核者）报出的反例已逐条收进 Regress 类。
"""
import glob, html, json, os, re, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "tools", "gen_daily_report.py")
_START, _END = "# ── 体系提炼摘录栏目", "def _font_face"


def _load():
    with open(SRC, encoding="utf-8") as fh:
        lines = fh.read().split("\n")
    a = [i for i, l in enumerate(lines) if l.startswith(_START)]
    b = [i for i, l in enumerate(lines) if l.startswith(_END)]
    assert len(a) == 1 and len(b) == 1 and a[0] < b[0], "栏目代码段的起止标记不唯一"
    ns = {"re": re}
    exec(compile("\n".join(lines[a[0]:b[0]]), SRC, "exec"), ns)
    return ns


NS = _load()
ESC = lambda s: (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
_GAP = re.compile(r"^[\s；，/：—（）()]*$")     # 格与格之间，原文里允许被拿掉的字符


def card(note):
    return NS["_intg_card"](1, note, ESC)


def fragments(card_html):
    """卡片里属于原文的各格文字（标题、副题、名目、要点数、附注、通栏行、脚注），按出现顺序"""
    h = card_html[:card_html.index('<div class="ig-meta">')]
    h = re.sub(r'<span class="ig-seal[^>]*>.*?</span>', "\0", h, flags=re.S)
    h = re.sub(r'<span class="ig-tag[^>]*>[^<]*</span>', "\0", h)
    h = re.sub(r'<span class="ig-fill">[^<]*</span>', "", h)                  # 成对读数补的单位不是原文
    h = re.sub(r'<b class="ig-big">([^<]*)</b>', "\0\\1\0", h)
    h = re.sub(r'</?b(?: class="ig-n")?>', "", h)                              # 行内加粗不算分格
    h = re.sub(r'<span class="ig-par">(.*?)</span>', r"\1", h, flags=re.S)     # 括注小字不算分格
    h = re.sub(r"<[^>]+>", "\0", h)
    return [html.unescape(x).strip() for x in h.split("\0") if x.strip()]


def mismatch(raw, card_html):
    """对账：不一致返回说明文字，一致返回 ''"""
    pos = 0
    for f in fragments(card_html):
        k = raw.find(f, pos)
        if k < 0:
            return "这一格不是原文里连续的一段（或顺序不对）：%r" % f
        if not _GAP.match(raw[pos:k]):
            return "原文里这段没有上页面：%r" % raw[pos:k]
        pos = k + len(f)
    if not _GAP.match(raw[pos:]):
        return "原文结尾这段没有上页面：%r" % raw[pos:]
    return ""


def cells(card_html):
    """[(名目, 要点数, 附注)]，去标签"""
    strip = lambda x: html.unescape(re.sub(r"<[^>]+>", "", re.sub(r'<span class="ig-tag[^>]*>[^<]*</span>', "", x)))
    return [tuple(strip(x) for x in m) for m in re.findall(
        r'<span class="ig-l">(.*?)</span><b class="ig-big">(.*?)</b><span class="ig-r">(.*?)</span></div>', card_html, flags=re.S)]


_SG = "+\\-−－＋±–"
_N = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
_U = r"\s*(?:%|bp|pp)"
_NUM_OK = re.compile(                                   # 要点数白名单
    "^(?:[%s]?%s%s"                                     # 单个数，可带号
    "|[%s]?%s(?:%s)?\\s*[~～]\\s*[%s]?%s%s"              # 波浪号区间，两端可带号
    "|%s(?:%s)?[\\-–]%s%s"                               # 横杠区间
    "|(?:[%s]?%s%s\\s*/\\s*)+[%s]?%s%s)$"                  # 成对读数（补齐单位后每段都带单位）
    % (_SG, _N, _U, _SG, _N, _U, _SG, _N, _U, _N, _U, _N, _U, _SG, _N, _U, _SG, _N, _U))
_LABEL_BAD_END = re.compile(r"[+\-−－＋±–—―‐‑‒﹣﹘~～]\s*$")
_NOTE_BAD_START = re.compile(r"^\s*[~～\-–—―‐‑‒﹣﹘至到]\s*[+\-−－＋±–]?\d")


def cell_violations(raw, card_html):
    """分格通则：返回违例说明列表"""
    out = []
    for lab, num, note in cells(card_html):
        if not _NUM_OK.match(num):
            out.append("要点数不是白名单形态：%r" % num)
        m = re.match("^(%s)(?:%s)?[\\-–](%s)" % (_N, _U, _N), num)
        if m and not float(m.group(1).replace(",", "")) < float(m.group(2).replace(",", "")):
            out.append("横杠区间不是前小后大：%r" % num)
        if _LABEL_BAD_END.search(lab):
            out.append("名目以正负号/横线结尾：%r｜%r" % (lab, num))
        if _NOTE_BAD_START.match(note):
            out.append("附注以区间号+数字开头：%r｜%r" % (num, note))
        if lab and (lab[-1].isdigit() or lab[-1] in ".,") and num[0] not in "+-−－＋±–" and (lab + num) in raw:
            out.append("数字被从中间拆开：%r｜%r" % (lab, num))
        if lab and (lab + num) in raw and not lab[-1].isspace() and not (lab[-1].isdigit() and num[0] in "+-−－＋±–") \
                and re.search(r"\d", re.search(r"[^\s\u3000\u4e00-\u9fff（(〔\[「『《\"'“‘，、；;。：＝=→|·]*$", lab).group(0)):
            out.append("紧贴的名目尾词里有数字（数被从中间拆开）：%r｜%r" % (lab, num))
        if note and (note[0].isdigit() or note[0] == "%") and (num + note) in raw:
            out.append("数字后半截落进附注：%r｜%r" % (num, note))
    return out


def bigs(card_html):
    return [c[1] for c in cells(card_html)]


def text_rows(card_html):
    return [html.unescape(re.sub(r"<[^>]+>", "", x)) for x in re.findall(
        r'<div class="ig-row (?:ig-lead|ig-tx)[^"]*"><span>(.*?)</span></div>', card_html, flags=re.S)]


def one(text, **kw):
    return card(dict({"text": text, "source": "EAL"}, **kw))


SYNTH = [
    "FOMC 市场隐含预期（12/8-9 会次）：hike 100%（+25bp 84.7~87% / +50bp 13~15.3%）/ hold 0% / cut 0%——两源转述，非官方页直读；+50bp 档较 11-12（9.2~11.6%）抬升",
    "仓位四态信号 hold：000688.SH V2.5-ET双波（T 无需减仓，模型名义档位 100%〔档 4〕，实际权重 93.14%；下一交易日 2026-11-16；模型账非真实持仓）",
    "无冒号的一句纯文字，涨跌家数 765 / 4748，比值不拆",
    "A&B <b>x</b>：x 5% & y——脚注一——脚注二",
    "传导：纳指-1.38% → 沪深300低开-1.40%；镨钕 yoy+42.4%；区间 3-5% 不拆；利差 +25bp 76.1% 仍为主流",
    "（整句都在括号里；连分号也在）",
    "：冒号在最前",
    "观星读数（注：模型候选）：hike 25.4% / hold 74.6%",
    "FOMC 预期（口径：CME 转述）hold 80% / hike 20%",
    "P(hike)：25%；其它",
    "传导：沪深300-1.40%；科创50-2.1%；中证1000+0.5%；黄金 yoy －7.5% 均线下；原油 yoy - 3.8%；涨幅 3%-5%；波动 10%~15%；涨幅3-5%；两市 1,234.5% 增",
    "哨兵：原油SC yoy +29.3% 仍 above（较 11-09 的 +37.0% 回落；周线仍强）；由 72.8% 升至 78.0%",
    "FOMC：12 月会定价 hold 28% / hike 72% / cut 0%（双源对拍通过），1 月累计 +25bp 58.4%——加息预期高位维持",
    "FOMC：下一场 hold 18.8% / hike 81.2% / cut 0%（「小非农」前读数）；1 月累计 +25bp 65.5% / hold 14% / +50bp 20.5%",
    "标题带六角括号〔试验〕：内容 5%",
    "区间：回撤 -5~-3%；波动 +3~+5%；yoy −5~−3%；回撤 -5%~-3%；yoy -2%~+3%；波动 +3%~+5%；利差 3%至5%；波幅 3%—5%",
    "横线：白银 yoy —3%；铂 yoy ‑3%；钯 yoy ﹣3%；镍 yoy -3%",
    "旧值：原油 yoy 较 11-09 的 +37.0% 回落至 +29.3%；铜 yoy 前值 +22.8%，现值 +20.1%；hike 概率较前日 81.5% 回落 8.7pp 至 72.8%",
]


def history():
    out, files = [], sorted(glob.glob(os.path.join(ROOT, "docs", "daily_integration_*.json")))
    for f in files:
        try:
            with open(f, encoding="utf-8") as fh:
                d = json.load(fh)
        except Exception:
            continue
        out += [n for n in (d.get("notes") or []) if isinstance(n, dict) and (n.get("text") or "").strip()]
    return out, len(files)


class Fidelity(unittest.TestCase):
    def test_synthetic_samples(self):
        bad = [(t, mismatch(t.strip(), one(t))) for t in SYNTH]
        self.assertEqual([b for b in bad if b[1]], [])

    def test_history_corpus(self):
        notes, nfiles = history()
        if not notes:
            self.skipTest("docs/ 下没有历史摘录文件（daily_integration_*.json），历史对账未跑")
        bad = [(n["text"], mismatch(n["text"].strip(), card(n))) for n in notes]
        bad = [b for b in bad if b[1]]
        self.assertEqual(bad, [], "渲染后文字与原文不一致（%d 条 / 共 %d 条 · %d 个历史文件）" % (len(bad), len(notes), nfiles))

    def test_checker_has_teeth(self):
        raw = SYNTH[0]
        c = one(raw)
        self.assertEqual(mismatch(raw, c), "")
        for name, broken in (
            ("少一行", re.sub(r'<div class="ig-row ig-kv"><span class="ig-l">cut.*?</div>', "", c, count=1, flags=re.S)),
            ("改一个数", c.replace("100%", "99%", 1)),
            ("删斜杠", c.replace("12/8-9", "128-9")),
            ("删格内空白", c.replace("档较 11-12", "档较11-12")),
            ("逗号改分号", c.replace("两源转述，非官方页直读", "两源转述；非官方页直读")),
            ("括注去括号", c.replace("（9.2~11.6%）", "9.2~11.6%")),
            ("两行对调", re.sub(r'(<div class="ig-row ig-kv"><span class="ig-l">hold.*?</div>)(<div class="ig-row ig-kv"><span class="ig-l">cut.*?</div>)', r"\2\1", c, flags=re.S)),
        ):
            self.assertNotEqual(broken, c, "夹具没改到：" + name)
            self.assertNotEqual(mismatch(raw, broken), "", "对账没逮到：" + name)

    def test_footer_shows_source_and_as_of(self):
        c = card({"text": "x：y", "source": "风险日报·fomc_market_exp", "as_of": "2026-11-13"})
        meta = c[c.index('<div class="ig-meta">'):]
        self.assertIn('<span class="ig-src">fomc_market_exp</span>', meta)
        self.assertIn('<span class="ig-asof">as_of 2026-11-13</span>', meta)
        self.assertIn('title="来源：风险日报·fomc_market_exp"', c)
        c2 = card({"text": "x：y"})
        self.assertIn('<span class="ig-src">—</span>', c2)
        self.assertIn("as_of —", c2)


class Numbers(unittest.TestCase):
    def test_sign_stays_with_number(self):
        c = one(SYNTH[4])
        self.assertIn(("纳指", "-1.38%", "→ 沪深300低开-1.40%"), cells(c))
        self.assertIn(("镨钕 yoy", "+42.4%", ""), cells(c))

    def test_range_is_one_number(self):
        self.assertIn(("区间", "3-5%", "不拆"), cells(one(SYNTH[4])))
        c = one(SYNTH[10])
        self.assertIn(("涨幅", "3%-5%", ""), cells(c))
        self.assertIn(("波动", "10%~15%", ""), cells(c))

    def test_percent_preferred_over_bp(self):
        self.assertIn(("利差 +25bp", "76.1%", "仍为主流"), cells(one(SYNTH[4])))

    def test_threshold_and_old_value_are_not_key_numbers(self):
        c = one("周报：稀土连续22周>20%·结构性确认（yoy+42.4%）；原油连续10周>20%·市场确认+19.4%；回撤 ≤ 5% 达标；由 72.8% 升至 78.0%")
        self.assertEqual(bigs(c), ["+19.4%", "78.0%"])

    def test_first_item_of_a_list_is_not_singled_out(self):
        c = one("哨兵：碳酸锂 +22.1%、铜 +26.8% 均 above；黄金 -7.5% below")
        self.assertEqual(cells(c), [("黄金", "-7.5%", "below")])
        self.assertIn("碳酸锂 +22.1%、铜 +26.8% 均 above", text_rows(c))

    def test_latin_token_tail_is_not_a_number(self):
        self.assertEqual(bigs(one("口径：V2.5% 与 tier4% 不是数字")), [])

    def test_slash_split_only_for_labelled_numbers(self):
        c = one(SYNTH[0])
        self.assertEqual(bigs(c), ["100%", "0%", "0%"])
        c2 = one(SYNTH[2])
        self.assertEqual(c2.count('class="ig-row'), 1)
        self.assertIn("765 / 4748", c2)
        self.assertIn("12/8-9 会次", c)


class Regress(unittest.TestCase):
    """2026-11-14 独立复验报出的反例"""

    def test_colon_inside_paren_does_not_cut_the_title(self):
        c = one(SYNTH[7])
        self.assertIn('<div class="ig-head">观星读数 <span class="ig-hsub">注：模型候选</span></div>', c)
        self.assertEqual(bigs(c), ["25.4%", "74.6%"])
        c2 = one(SYNTH[8])
        self.assertNotIn("ig-head", c2)
        self.assertEqual(cells(c2)[0], ("FOMC 预期（口径：CME 转述）hold", "80%", ""))

    def test_halfwidth_paren_in_title_is_part_of_the_name(self):
        self.assertIn('<div class="ig-head">P(hike)</div>', one(SYNTH[9]))
        self.assertIn('<div class="ig-head">标题带六角括号〔试验〕</div>', one(SYNTH[14]))

    def test_index_name_digits_are_not_swallowed(self):
        c = one(SYNTH[10])
        for want in (("沪深300", "-1.40%", ""), ("科创50", "-2.1%", ""), ("中证1000", "+0.5%", ""),
                     ("黄金 yoy", "－7.5%", "均线下"), ("两市", "1,234.5%", "增")):
            self.assertIn(want, cells(c))

    def test_ambiguous_numbers_are_left_inline(self):
        c = one(SYNTH[10])
        self.assertIn("原油 yoy - 3.8%", text_rows(c))
        self.assertIn("涨幅3-5%", text_rows(c))
        self.assertNotIn("3.8%", bigs(c))
        self.assertNotIn("5%", bigs(c))

    def test_paren_list_is_not_unwrapped_when_the_lead_has_its_own_number(self):
        c = one(SYNTH[11])
        self.assertEqual(cells(c)[0], ("原油SC yoy", "+29.3%", "仍 above（较 11-09 的 +37.0% 回落；周线仍强）"))
        self.assertNotIn("+37.0%", bigs(c))

    def test_trailing_clause_gets_its_own_row(self):
        c = one(SYNTH[12])
        self.assertEqual(cells(c), [("12 月会定价 hold", "28%", ""), ("hike", "72%", ""), ("cut", "0%", ""),
                                    ("1 月累计 +25bp", "58.4%", "")])
        self.assertIn("（双源对拍通过）", text_rows(c))
        self.assertIn('ig-tx ig-after', c)

    def test_groups_separated_by_semicolon_are_not_flattened(self):
        c = one(SYNTH[13])
        self.assertEqual(c.count("ig-gap"), 1)
        self.assertIn('<div class="ig-row ig-kv ig-gap"><span class="ig-l">1 月累计 <b class="ig-n">+25bp</b></span>', c)

    def test_signed_ranges_are_one_number(self):
        c = one(SYNTH[15])
        got = cells(c)
        for want in (("回撤", "-5~-3%", ""), ("波动", "+3~+5%", ""), ("yoy", "−5~−3%", ""),
                     ("回撤", "-5%~-3%", ""), ("yoy", "-2%~+3%", ""), ("波动", "+3%~+5%", "")):
            self.assertIn(want, got)
        self.assertEqual(len(got), 6)
        self.assertIn("利差 3%至5%", text_rows(c))
        self.assertIn("波幅 3%—5%", text_rows(c))

    def test_number_glued_to_a_digit_word_is_left_inline(self):
        # 三轮复验（2026-11-14）：科学计数、斜杠成对读数、箭头前后两读数——紧贴的左侧词里有数字即不排表
        for t in ("x：误差 1e-3%", "x：1.2e-3% 误差", "x：误差 2.5E-2% 内", "x：步长 1.0e+2bp",
                  "x：多空比 55/45% 偏多", "x：+25bp/+50bp 88.5/11.5%", "x：a/b/c 28/72%", "x：Q3/Q4 5/6%", "x：H20/B30 5/6%",
                  "x：多空比 55:45%", "x：降息概率 28/ 72%", "x：多空比 55: 45%"):
            c = one(t)
            self.assertEqual(cells(c), [], "%s 不应排成账目行：%r" % (t, cells(c)))

    def test_label_separators_and_arrows_still_lay_out(self):
        # 四轮前再修（2026-11-14 Doctor 令）：名目分隔与箭头不该让整行退回原文；箭头前是旧值、取箭头后的新值
        for t, want in (("x：Q3：5%", ("Q3：", "5%", "")), ("x：Top10：45%", ("Top10：", "45%", "")),
                        ("x：H20=5%", ("H20=", "5%", "")), ("x：Q3|5%", ("Q3|", "5%", "")),
                        ("x：hike 72%→81%", ("hike 72%→", "81%", "")),
                        ("x：hike 72% → 81% 定价", ("hike 72% →", "81%", "定价")),
                        ("x：yoy -12.7%→-9.9%", ("yoy -12.7%→", "-9.9%", "")),
                        ("x：1%→2%→3%", ("1%→2%→", "3%", "")),
                        ("x：（截至11-13）3.2%", ("（截至11-13）", "3.2%", "")),
                        ("x：Q3·5%", ("Q3·", "5%", "")),
                        ("x：hike 72% -> 81%", ("hike 72% ->", "81%", "")),
                        ("x：hike 72%->81%", ("hike 72%->", "81%", "")),
                        ("x：hike 72% --> 81%", ("hike 72% -->", "81%", "")),
                        ("x：hike 72% ⇒ 81%", ("hike 72% ⇒", "81%", "")),
                        ("x：hike 72% ➜ 81%", ("hike 72% ➜", "81%", "")),
                        ("x：hike 72%⟶81%", ("hike 72%⟶", "81%", "")),
                        # 五轮复验：箭头按区段与拼法认，不再逐个列举
                        ("x：hike 72% ➡ 81%", ("hike 72% ➡", "81%", "")),
                        ("x：hike 72% ---> 81%", ("hike 72% --->", "81%", "")),
                        ("x：hike 72% ⇢ 81%", ("hike 72% ⇢", "81%", "")),
                        ("x：hike 72% →→ 81%", ("hike 72% →→", "81%", "")),
                        ("x：hike 72% ~> 81%", ("hike 72% ~>", "81%", "")),
                        ("x：hike 72% - > 81%", ("hike 72% - >", "81%", "")),
                        ("x：hike 72% ⮕ 81%", ("hike 72% ⮕", "81%", "")),
                        ("x：72%➡81%", ("72%➡", "81%", "")),
                        ("x：hike 72% ⟹ 81%", ("hike 72% ⟹", "81%", "")),
                        ("x：hike 72% ⤳ 81%", ("hike 72% ⤳", "81%", "")),
                        ("x：hike 72% → 约 81%", ("hike 72% → 约", "81%", ""))):
            c = one(t)
            self.assertEqual(cells(c), [want], t)

    def test_symmetric_slash_pairs_become_one_cell_with_full_units(self):
        # Doctor 2026-11-14 裁：名目对称（带斜杠、段数相同）才把成对读数合成一格，两边都补齐单位
        for t, want in (("FOMC：hold/hike 28/72%", ("hold/hike", "28%/72%", "")),
                        ("x：hold/hike 28 / 72%", ("hold/hike", "28% / 72%", "")),
                        ("x：hold/hike 28%/72%", ("hold/hike", "28%/72%", "")),
                        ("x：cut/hold/hike 10/30/60%", ("cut/hold/hike", "10%/30%/60%", "")),
                        ("x：hold/hike 28/72bp 定价", ("hold/hike", "28bp/72bp", "定价")),
                        ("x：FOMC 12 月 hold/hike -28/+72% 偏鹰", ("FOMC 12 月 hold/hike", "-28%/+72%", "偏鹰"))):
            c = one(t)
            self.assertEqual(cells(c), [want], t)
            self.assertEqual(mismatch(t.strip(), c), "", t)
            self.assertEqual(cell_violations(t, c), [], t)
        self.assertIn('28<span class="ig-fill">%</span>/72%', one("x：hold/hike 28/72%"))

    def test_bare_number_before_spaced_slash_splits_rows(self):
        # 「tier 4 / 1.0% 仓位」名目不对称：拆成两行，不再挂悬空斜杠
        c = one("科创50 信号：hold，tier 4 / 1.0% 仓位，无待执行单")
        self.assertEqual([x for x in cells(c) if "/" in x[0]], [])
        rows = text_rows(c)
        self.assertIn("tier 4", rows)
        self.assertIn("1.0% 仓位", rows)

    def test_only_rightward_arrows_mean_old_to_new(self):
        # 六轮复验：涨跌标记、左向、双向、斜向箭头不是「旧值 → 新值」
        for t, want in (("x：CPI 3.2% ↓0.1pp", [("CPI", "3.2%", "↓0.1pp")]),
                        ("x：铜 yoy +21.9% ↑0.5pp", [("铜 yoy", "+21.9%", "↑0.5pp")]),
                        ("x：收益 1.2% ↑ 0.3%", [("收益", "1.2%", "↑ 0.3%")]),
                        ("x：hike 72% ← 81%", [("hike", "72%", "← 81%")]),
                        ("x：hike 72% ⟵ 81%", [("hike", "72%", "⟵ 81%")]),
                        ("x：区间 3% ⟷ 5%", [("区间", "3%", "⟷ 5%")]),
                        ("x：利差 3%↕5%", []),
                        ("x：hike 72% ↗ 81%", [("hike", "72%", "↗ 81%")]),
                        ("x：hike 72% ⭐ 81%", [("hike", "72%", "⭐ 81%")])):
            self.assertEqual(cells(one(t)), want, t)
        for ch in "←↔⟷↑↓↕⬆⬇⤴⤵↗⇐⬛⭐":
            self.assertNotIn(ch, NS["_intg_right_arrows"](), ch)

    def test_negated_and_relational_arrows_are_not_old_to_new(self):
        # 七轮复验：带划线（不→）、穿 X、叠关系符、端点修饰的右箭头不是「旧值 → 新值」
        for ch in "↛⇏⇸⇻⤀⤁⤃⤔⤕⤗⤘⥇⥱⥲⥴⥵⥸⥹⭃⭇⭈⭌⥅↦⇥↪↬↣⤞":
            self.assertEqual(cells(one("x：hike 72% " + ch + " 81%")), [("hike", "72%", ch + " 81%")], ch)
        self.assertEqual(cells(one("x：hike 72% → → 81%")), [("hike 72% → →", "81%", "")])
        self.assertEqual(NS["_intg_right_arrows"](),
                         "→↝↠⇉⇒⇛⇝⇢⇨⇶⇾⟶⟹⟿⤍⤏⤐⤳⭢⭬⮆⮕⮚⮞➔➙➛➜➝➞➟➠➡➢➣➤➧➨➩➫➬➭➯➳➵➸➺➻➼➽➾")

    def test_old_value_before_paren_then_arrow_or_move_verb(self):
        # 七轮复验：旧值后先跟括注再接「→ 新值」；以及「升至/回落至」等文字写法
        for t, big in (("FOMC：hike 概率 72.8%（非农前）→ 78.0%（非农后）", "78.0%"),
                       ("FOMC：hike 72.8%（11-06）→ 78.0%（11-09）", "78.0%"),
                       ("哨兵：碳酸锂 yoy +15.4%（11-06）→ +6.3%（11-09）", "+6.3%"),
                       ("FOMC：hike 72.8%（CME）-> 78.0%", "78.0%"),
                       ("FOMC：hike 74.9% 升至 81.2%", "81.2%"),
                       ("x：利差 120bp 收窄至 95bp", "95bp"),
                       ("x：PMI 景气 51.2% 回落至 49.8%（荣枯线下）", "49.8%"),
                       ("x：hike 72.8%（11-06），hold 27.2%", "72.8%")):
            self.assertEqual(bigs(one(t))[:1], [big], t)
            self.assertEqual(mismatch(t.strip(), one(t)), "", t)

    def test_move_verbs_from_the_list(self):
        # Doctor 2026-11-14：「至」字动词按词表补齐八轮漏网的 8 个，不改通则（免得卷进「截至」这类词）
        for v in ("提高至", "降低至", "增至", "放缓至", "上修至", "下修至", "抬升至", "调至", "升到", "降到", "回升至", "下调至"):
            t = "x：增速 4.8% " + v + " 5.2%"
            self.assertEqual(bigs(one(t)), ["5.2%"], t)
            self.assertEqual(mismatch(t.strip(), one(t)), "", t)
        for t, want in (("x：区间 84.7% 至 87%", []),                         # 区间：至前无动词
                        ("x：hike 72% 甚至 80%", ["72%"]),
                        ("x：hike 72% 截至 11-13", ["72%"]),
                        ("x：hike 72% 升至 11 月以来高位", ["72%"]),           # 后接无单位的数
                        ("x：hike 72% 升至 80", ["72%"]),
                        ("x：hike 72% 大幅提升至 80%", ["80%"]),               # 动词前带副词也认（Doctor 2026-11-15）
                        ("x：hike 72% 一度升至 81%", ["81%"]),
                        ("x：hike 72% 进一步升至 81%", ["81%"]),
                        ("x：hike 72% 预计进一步升至 81%", ["81%"]),
                        ("x：hike 72% 再度回落至 65%（非农后）", ["65%"]),
                        # 十一轮复验：中间夹的是另一项，不是副词——前一项仍是当期读数
                        ("复盘：美股AI链四连涨 +21% 而创业板跌至 -14%", ["+21%"]),
                        ("x：纳指 -1.38% 而恒指回落至 -0.5%", ["-1.38%"]),
                        ("x：加息 72% 而降息升至 28%", ["72%"]),
                        ("x：CPI 同比 3.2% 环比升至 0.5%", ["3.2%"]),
                        ("x：出口 5% 进口回落至 2%", ["5%"]),
                        ("x：CPI 3.2% 核心升至 3.5%", ["3.2%"]),
                        ("x：营收 +12% 净利润升至 +20%", ["+12%"]),
                        ("x：hike 72% 预计至 80%", ["72%"]),                   # 不在词表
                        ("x：hike 72% 累计至 80%", ["72%"])):
            self.assertEqual(bigs(one(t)), want, t)

    def test_fat_arrow_is_neither_arrow_nor_threshold(self):
        # Doctor 2026-11-14 裁：「=>」「==>」不按箭头读，也不按门槛 ≥ 读——普通符号，其后的数照常参与选要点数
        self.assertEqual(cells(one("x：hike 72% => 81%")), [("hike", "72%", "=> 81%")])
        self.assertEqual(cells(one("x：hike 72% ==> 81%")), [("hike", "72%", "==> 81%")])
        self.assertEqual(cells(one("x：门槛 =>5% 持续")), [("门槛 =>", "5%", "持续")])
        self.assertEqual(cells(one("x：门槛 ==> 5%")), [("门槛 ==>", "5%", "")])
        self.assertEqual(cells(one("x：门槛 >=5% 持续")), [])            # 「>=」仍是门槛

    def test_odd_dash_characters_are_left_inline(self):
        c = one(SYNTH[16])
        self.assertEqual(cells(c), [("镍 yoy", "-3%", "")])
        for t in ("白银 yoy —3%", "铂 yoy ‑3%", "钯 yoy ﹣3%"):
            self.assertIn(t, text_rows(c))

    def test_top_level_old_values_are_not_key_numbers(self):
        c = one(SYNTH[17])
        self.assertEqual(cells(c)[0], ("原油 yoy 较 11-09 的 +37.0% 回落至", "+29.3%", ""))
        self.assertEqual(cells(c)[1], ("铜 yoy 前值 +22.8%，现值", "+20.1%", ""))
        self.assertEqual(len(cells(c)), 2)
        # 「8.7pp 至 72.8%」分不清是区间还是「降到」，整行照原文
        self.assertIn("hike 概率较前日 81.5% 回落 8.7pp 至 72.8%", text_rows(c))

    def test_two_marks_in_one_segment_both_apply(self):
        c = one("FOMC：hike 100% / hold 0% / cut 0%",
                marks=[{"match": "hike 100%", "pol": "bear"}, {"match": "hold 0%", "pol": "bull"}])
        self.assertIn('<div class="ig-row ig-kv ig-bear"><span class="ig-l">hike<span class="ig-tag ig-tag-bear">利空</span>', c)
        self.assertIn('<div class="ig-row ig-kv ig-bull"><span class="ig-l">hold<span class="ig-tag ig-tag-bull">利好</span>', c)
        self.assertIn('<div class="ig-row ig-kv"><span class="ig-l">cut</span>', c)

    def test_non_string_fields_do_not_break_the_section(self):
        D = {"integration": {"notes": ["x", None, {"text": 5, "source": 7, "as_of": 8, "marks": [{"match": 3, "pol": "bull"}]},
                                       {"text": "铜：+5% 强", "source": None}]},
             "integration_slots": {"eal": "坏", "starry_ne": {"text": "   ", "source": 1, "as_of": 2, "note": 3}},
             "holdings": ["x", {"name": 5, "code": None}]}
        h = NS["integration_section"](D)
        self.assertEqual(h.count('class="ig-note"'), 2)
        self.assertIn("无（槽位未计算）", h)
        self.assertIn('<div class="ig-slot-v na">无</div>', h)
        self.assertIn("今日无", NS["integration_section"]({"integration": ["x"]}))

    def test_polarity_is_visible_without_a_title(self):
        c = one("没有标题的一句话", polarity="bear", polarity_why="w", source="no_seal_source_name")
        self.assertNotIn("ig-seal", c)
        self.assertIn('class="ig-note ig-bear"', c)
        self.assertIn('<div class="ig-top"><span class="ig-tag ig-tag-bear" title="w">利空</span></div>', c)
        style = NS["_INTG_STYLE"]
        self.assertIn(".ig-note.ig-bear{box-shadow", style)
        self.assertIn(".ig-note.ig-bull{box-shadow", style)

    def test_tag_colour_follows_the_tag_not_the_card(self):
        c = one("哨兵：铜 yoy +20.1% 强", polarity="bear", marks=[{"match": "铜 yoy", "pol": "bull"}])
        self.assertIn('<span class="ig-tag ig-tag-bull">利好</span>', c)
        self.assertNotIn(".ig-bear .ig-tag", NS["_INTG_STYLE"])
        self.assertNotIn(".ig-bull .ig-tag", NS["_INTG_STYLE"])

    def test_holdings_names_are_escaped(self):
        D = {"integration": {"notes": [{"text": "仓位：<b>X</b> 维持", "source": "剑酒青丘"}]},
             "holdings": [{"name": "<b>X</b>", "code": ""}]}
        h = NS["integration_section"](D)
        self.assertIn("⚠ 摘录命中持仓标的（&lt;b&gt;X&lt;/b&gt;）", h)
        self.assertNotIn("<b>X</b>", h)


class CellRules(unittest.TestCase):
    """分格通则——不靠逐例断言，凡排成账目行的都得守"""

    def _check(self, texts):
        bad = []
        for t in texts:
            c = one(t)
            v = cell_violations(t, c)
            mm = mismatch(t.strip(), c)
            if v or mm:
                bad.append((t, v, mm))
        return bad

    def test_synthetic_and_history(self):
        notes, _ = history()
        self.assertEqual(self._check(SYNTH + [n["text"] for n in notes]), [])

    def test_combinations(self):
        pre = ["铜 yoy ", "沪深300", "科创50", "回撤 ", "yoy", "涨幅", "仓位", "P(hike) ", "中证1000", "较前日 ", "A股"]
        sign = ["", "+", "-", "−", "－", "＋", "±", "–", "—", "‑", "- ", "+ ", "— "]
        first = ["3", "5.5", "300", "1,234.5"]
        mid = ["", "~5", "~-3", "~+8", "-5", "-700", "–7", "%-5", "%~8", "%~-2", "%~+9", "%至9", "%—9", "~ 9", "--5", "-5-7"]
        unit = ["%", "bp"]
        suf = ["", " 回落", "，现值 +2.1%"]
        texts = ["标题：%s%s%s%s%s%s" % (a, b, c, d, e, f)
                 for a in pre for b in sign for c in first for d in mid for e in unit for f in suf]
        self.assertGreater(len(texts), 10000)
        bad = self._check(texts)
        self.assertEqual(bad[:5], [], "共 %d 条违例（列前 5）" % len(bad))

    def test_rules_have_teeth(self):
        fake = ('<div class="ig-row ig-kv"><span class="ig-l">%s</span><b class="ig-big">%s</b>'
                '<span class="ig-r">%s</span></div><div class="ig-meta">')
        for lab, num, note, raw in (
            ("回撤 -5~", "-3%", "", "回撤 -5~-3%"),
            ("回撤", "-5%", "~-3%", "回撤 -5%~-3%"),
            ("沪深", "300-1.40%", "", "沪深300-1.40%"),
            ("黄金 yoy －", "7.5%", "", "黄金 yoy －7.5%"),
            ("两市 1,", "234.5%", "", "两市 1,234.5%"),
            ("涨幅", "3%", "-5%", "涨幅 3%-5%"),
            ("白银 yoy —", "3%", "", "白银 yoy —3%"),
            ("误差 1e", "-3%", "", "误差 1e-3%"),
            ("hold/hike 28/", "72%", "", "hold/hike 28/72%"),
            ("多空比 55:", "45%", "", "多空比 55:45%"),
        ):
            self.assertNotEqual(cell_violations(raw, fake % (lab, num, note)), [], "通则没逮到：%s｜%s｜%s" % (lab, num, note))


class Layout(unittest.TestCase):
    def test_trailing_list_paren_is_unwrapped(self):
        c = card({"text": SYNTH[1], "source": "剑酒青丘·x"})
        self.assertIn('<div class="ig-row ig-lead"><span>000688.SH V2.5-ET双波</span></div>', c)
        self.assertEqual(cells(c), [("模型名义档位", "100%", "〔档 4〕"), ("实际权重", "93.14%", "")])
        self.assertIn("下一交易日 2026-11-16", text_rows(c))

    def test_plain_paren_stays_a_note(self):
        c = one("仓位四态信号 hold：000688.SH V2.5-ET双波（剑酒青丘仓位模型）")
        self.assertNotIn("ig-lead", c)
        self.assertIn('<span class="ig-par">（剑酒青丘仓位模型）</span>', c)

    def test_escape(self):
        c = card({"text": SYNTH[3], "source": 'a"b<c>·d', "as_of": "<x>",
                  "polarity": "bull", "polarity_why": '"><i>',
                  "marks": [{"match": "x 5%", "pol": "bear", "why": "<u>'\""}]})
        for bad in ("<b>x</b>", "<c>", "<x>", "<i>", "<u>"):
            self.assertNotIn(bad, c)
        self.assertIn("A&amp;B &lt;b&gt;x&lt;/b&gt;", c)
        self.assertNotIn('""', c)
        c2 = card({"text": "x：y", "source": '风险日报·a"b<c>'})
        self.assertIn('title="来源：风险日报·a&quot;b&lt;c&gt;"', c2)
        self.assertIn('<span class="ig-src">a&quot;b&lt;c&gt;</span>', c2)

    def test_slot_fields_are_escaped(self):
        bad = '<script>x</script>"&'
        D = {"integration": None, "integration_slots": {
            "eal": {"text": bad, "source": bad, "as_of": bad, "note": bad}}}
        h = NS["integration_section"](D)
        h = h[h.index('<div class="ig-slots">'):]
        self.assertNotIn("<script>", h)
        self.assertEqual(h.count("&lt;script&gt;x&lt;/script&gt;"), 4)

    def test_seal(self):
        seal = NS["_intg_seal"]
        self.assertIn('class="ig-seal c2"', seal("风险日报·fomc_market_exp")[0])
        self.assertEqual(seal("风险日报·fomc_market_exp")[1], "fomc_market_exp")
        self.assertIn('class="ig-seal c2"', seal("剑酒青丘 v25_et_position_signal.json")[0])
        self.assertIn('class="ig-seal la"', seal("EAL")[0])
        self.assertIn('class="ig-seal la"', seal("X Board")[0])
        self.assertEqual(seal("some_long_source_name")[0], "")
        self.assertEqual(seal("some_long_source_name")[1], "some_long_source_name")
        self.assertEqual(seal("")[1], "—")


class Marks(unittest.TestCase):
    T = "白泽哨兵：铜 yoy +20.1% 仍处均线上方；黄金 yoy -12.7% 均线下"

    def test_row_mark(self):
        c = one(self.T, marks=[{"match": "黄金 yoy", "pol": "bear", "why": 'a"b'}])
        self.assertEqual(c.count("ig-row ig-kv ig-bear"), 1)
        self.assertNotIn("ig-bull", c)
        self.assertIn('title="a&quot;b"', c)
        self.assertIn("利空", c)

    def test_invalid_marks_ignored(self):
        c = one(self.T, polarity="up",
                marks=[{"match": "铜", "pol": "good"}, {"match": "不存在的子串", "pol": "bull"}, "x", {"pol": "bull"}])
        for bad in ("ig-bull", "ig-bear", "ig-tag"):
            self.assertNotIn(bad, c)

    def test_card_polarity(self):
        c = one(self.T, polarity="bull", polarity_why="w")
        self.assertIn('class="ig-note ig-bull" title="w"', c)
        self.assertIn('<span class="ig-tag ig-tag-bull" title="w">利好</span></div>', c)

    def test_mark_spanning_rows_colours_the_whole_segment(self):
        c = one("FOMC：hike 100% / hold 0% / cut 0%；其它 5% 不染", marks=[{"match": "hike 100% / hold 0%", "pol": "bear"}])
        self.assertEqual(c.count("ig-kv ig-bear"), 3)
        self.assertIn(("其它", "5%", "不染"), cells(c))
        self.assertEqual(c.count("利空"), 3)


class Section(unittest.TestCase):
    SLOT = {"eal": {"text": "无", "source": "EAL·x", "as_of": "2026-11-13"}}

    def test_empty_says_none_and_keeps_slots(self):
        for D in ({}, {"integration": None}, {"integration": {"notes": [{"text": "  "}]}}):
            h = NS["integration_section"](D)
            self.assertIn("今日无", h)
            self.assertNotIn('class="ig-cols"', h)
            self.assertEqual(h.count('class="ig-slot"'), 2)
            self.assertIn("无（槽位未计算）", h)
            self.assertIn('id="sec-intg"', h)

    def test_slots_and_holdings_hit(self):
        D = {"integration": {"notes": [{"text": "仓位：000688.SH 维持", "source": "剑酒青丘"}]},
             "integration_slots": self.SLOT, "holdings": [{"name": "科创50ETF", "code": "000688.SH"}]}
        h = NS["integration_section"](D)
        self.assertIn("⚠ 摘录命中持仓标的（科创50ETF）", h)
        self.assertLess(h.index('class="ig-cols"'), h.index('class="ig-hit"'))
        self.assertLess(h.index('class="ig-hit"'), h.index('class="ig-slots"'))
        self.assertIn('<div class="ig-slot-v na">无</div>', h)
        D["holdings"] = []
        self.assertNotIn('class="ig-hit"', NS["integration_section"](D))

    def test_at_most_eight_notes(self):
        D = {"integration": {"notes": [{"text": "n%d：x" % i, "source": "EAL"} for i in range(12)]}}
        self.assertEqual(NS["integration_section"](D).count('class="ig-note"'), 8)


if __name__ == "__main__":
    unittest.main()
