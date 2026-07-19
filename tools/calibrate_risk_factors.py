#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""五因风险温度 · 回测校准（point-in-time 重建 · 只读）
（CC 2026-07-17；Doctor 同意的「五因阈值统一回测校准」。**只读 DB、只写 docs/ 报告，绝不改 config**）

方法：
  对每个 A 股交易日 D，**只用 D 当日可得的数据**重建 F1~F5 的触发态（外盘严格取 trade_date < D＝真隔夜，
  两融取完整日 ≤ D，IPO 取滚动 20 日历日 ≤ D，情绪/汇率取 ≤ D），再与**前向结果**对照。
  前向标签「冰点」= 未来 3 个交易日创业板指累计跌幅 ≤ ICE_TH（默认 -5%），并另报 fwd1/fwd3 均值。

指标：触发率、基准冰点率、P(冰点|触发)、lift(=P(冰点|触发)/基准)、假阳性率(FPR)、触发日 fwd3 均值。
  lift>1 才说明该因子有区分力；lift≈1 = 噪声；触发率过低 = 样本不足不可信。

用法：
  python3 tools/calibrate_risk_factors.py                 # 全样本，出报告到 docs/
  python3 tools/calibrate_risk_factors.py --ice-th -4     # 改冰点阈值
  python3 tools/calibrate_risk_factors.py --no-write      # 只打印不落文件
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from lib.logger import get_logger
logger = get_logger(__name__)
import sqlite3, argparse, json, datetime, statistics as st
import config

MIN_N = 20          # 触发样本低于此数 → 标「样本不足·不可信」。★卡的是**独立事件数**，不是触发日数（见下）

# ── 独立事件切分（2026-07-19 立 · Doctor 批）─────────────────────────────
# 为什么必须区分「触发日数」与「独立事件数」：
#   F4 用滚动 20 日历日窗口，一轮 IPO 潮会连续点亮十几个交易日 → 33 个触发日实为 **3 轮**
#   （20250707–0725 / 20251205–1210 / 20260622–0710），高度自相关，不是 33 个独立观测。
#   F5 油价腿是单日冲击，12 个触发日 ≈ 9 次独立事件，几乎无膨胀。
#   拿同一个 MIN_N=20 去卡两者的**日数**，等于用同一把尺量两种单位——
#   结果就是引擎判 F4「有区分力」(33日)、F5「样本不足」(12日)，而按事件算排序完全颠倒。
#   → [[通用教训]] G-X75（相减/比较前先确认两边可比）
# EPISODE_GAP 的取值是工程约定、非实证：相邻触发日在交易日序列上间隔 ≤ 此数即视为同一轮。
#   方向稳健（带滚动窗的因子怎么切都会大幅塌缩，单日冲击型怎么切都不敏感），
#   但具体事件数依赖此参数——报告里会把它显式打出来，别当成客观常数。
EPISODE_GAP = 3


def episodes(trigger_days, idx, gap=EPISODE_GAP):
    """把触发日列表按交易日间隔切成独立事件。返回 [[d,...], ...]。"""
    t = sorted(d for d in trigger_days if d in idx)
    if not t:
        return []
    out, cur = [], [t[0]]
    for a, b in zip(t, t[1:]):
        if idx[b] - idx[a] <= gap:
            cur.append(b)
        else:
            out.append(cur)
            cur = [b]
    out.append(cur)
    return out


def _iso2c(d):      # '2026-07-17' → '20260717'
    return d.replace("-", "")


def load_cfg():
    try:
        with open(config.PROJECT_ROOT / "config" / "risk_factors.json", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"risk_factors.json 未加载({e})，用内置默认")
        return {"f1": {"semi_codes": ["NASDAQ", "AVGO", "NVDA", "LITE"],
                       "asia_codes": ["JP_FUT", "KR_SAMSUNG", "KR_HYNIX"],
                       "semi_th": -2.0, "asia_th": -2.0},
                "f2": {"pctrank_th": 80}, "f3": {"rzye_5d_th": -400.0, "rzye_1d_th": -300.0},
                "f4": {"funds_win_th": 300.0, "win_days": 20},
                "f5": {"cnh_daily_th": 0.05, "cnh_7d_th": 0.10, "oil_daily_th": 3.0, "bond_bp_th": 8.0}}


def load_data():
    md = sqlite3.connect(f"file:{config.MARKET_DB}?mode=ro", uri=True)
    rc = sqlite3.connect(f"file:{config.RECAP_DB}?mode=ro", uri=True)
    D = {}
    # A 股交易日 + 创业板日涨跌（标签用）
    D["days"] = [(r[0], r[1]) for r in md.execute(
        "SELECT trade_date, cyb_pct_chg FROM daily_market "
        "WHERE cyb_pct_chg IS NOT NULL ORDER BY trade_date")]
    # 外盘（按码分序列）
    D["intl"] = {}
    for code, td, close, pct in md.execute(
            "SELECT code,trade_date,close,pct_chg FROM intl_index_daily ORDER BY trade_date"):
        D["intl"].setdefault(code, []).append((td, close, pct))
    # 两融（完整日）
    D["margin"] = [(r[0], r[1]) for r in md.execute(
        "SELECT trade_date,total_rzye FROM margin_daily "
        "WHERE szse_rzrqye IS NOT NULL ORDER BY trade_date")]
    # IPO
    D["ipo"] = dict(md.execute("SELECT trade_date,funds_yi FROM ipo_daily"))
    # 情绪
    D["emo"] = [(_iso2c(r[0]), r[1]) for r in rc.execute(
        "SELECT date,emotion_score FROM emotion_cycle WHERE emotion_score IS NOT NULL ORDER BY date")]
    # 离岸人民币
    try:
        D["fx"] = [(r[0], r[1]) for r in rc.execute(
            "SELECT trade_date,close FROM fx_cnh_daily WHERE close IS NOT NULL ORDER BY trade_date")]
    except sqlite3.OperationalError:
        D["fx"] = []
    return D


def _latest_before(seq, d, strict=True):
    """seq=[(date,...)] 升序；返回严格早于/不晚于 d 的最后一项索引，无则 None"""
    lo, out = 0, None
    for i, row in enumerate(seq):
        if (row[0] < d) if strict else (row[0] <= d):
            out = i
        else:
            break
    return out


def eval_day(d, DATA, cfg):
    """按时点重建 D 日五因触发态。返回 {fid: True/False/None}（None=当日无数据不可评）"""
    out = {}
    c = cfg
    # —— F1 外盘（严格 < d ＝真隔夜）——
    worst_semi = worst_asia = None
    for code in c["f1"]["semi_codes"]:
        seq = DATA["intl"].get(code) or []
        i = _latest_before(seq, d, strict=True)
        if i is not None and seq[i][2] is not None:
            worst_semi = seq[i][2] if worst_semi is None else min(worst_semi, seq[i][2])
    for code in c["f1"]["asia_codes"]:
        seq = DATA["intl"].get(code) or []
        i = _latest_before(seq, d, strict=True)
        if i is not None and seq[i][2] is not None:
            worst_asia = seq[i][2] if worst_asia is None else min(worst_asia, seq[i][2])
    if worst_semi is None and worst_asia is None:
        out["F1"] = None
    else:
        out["F1"] = bool((worst_semi is not None and worst_semi <= c["f1"]["semi_th"])
                         or (worst_asia is not None and worst_asia <= c["f1"]["asia_th"]))
    # —— F2 情绪（容量腿无法按时点重建，仅评情绪腿：高分位且下行）——
    emo = DATA["emo"]
    i = _latest_before(emo, d, strict=False)
    if i is None or i < 6:
        out["F2"] = None
    else:
        vals = [v for _, v in emo[max(0, i - 49):i + 1]]
        pr = 100 * sum(1 for v in vals if v <= vals[-1]) / len(vals)
        ma_now = st.fmean([v for _, v in emo[max(0, i - 4):i + 1]])
        ma_prev = st.fmean([v for _, v in emo[max(0, i - 5):i]])
        out["F2"] = bool(pr >= c["f2"]["pctrank_th"] and ma_now < ma_prev)
    # —— F3 两融（完整日 ≤ d）——
    mg = DATA["margin"]
    i = _latest_before(mg, d, strict=False)
    if i is None or i < 5:
        out["F3"] = None
    else:
        chg1 = mg[i][1] - mg[i - 1][1]
        chg5 = mg[i][1] - mg[i - 5][1]
        out["F3"] = bool(chg5 <= c["f3"]["rzye_5d_th"] or chg1 <= c["f3"]["rzye_1d_th"])
    # —— F4 IPO（滚动 win_days 日历日 ≤ d）——
    wd = int(c["f4"].get("win_days", 20))
    dt = datetime.date(int(d[:4]), int(d[4:6]), int(d[6:]))
    lo = (dt - datetime.timedelta(days=wd)).strftime("%Y%m%d")
    # ERR-20260719-002：原写法只在**整张 ipo 表为空**时判「不可评」，一旦表非空就把
    # 每一天都当可评——而 ipo_daily 实际只覆盖 20240102+，2020–2023 约 970 个交易日
    # 无数据、滚动和恒为 0 → 被静默记成「未触发」。后果：可评日 1581(应~610)、
    # 触发率 2.1%(应~5.4%)、lift 因基准用全样本 3.9% 而被**低估**(应~1.70)。
    # 「无数据」≠「未触发」——同 [[通用教训]] G-X75。F1/F3/F5 本来就是对的，只 F4 这支漏了。
    # 正解：按 F5 的写法，看**本窗口内**有没有真实覆盖，没有则 None(不可评)。
    ipo = DATA["ipo"]
    if not ipo:
        out["F4"] = None
    else:
        _lo_cov, _hi_cov = min(ipo), max(ipo)
        # 窗口 (lo, d] 与 ipo 数据覆盖区间无交集 → 该日不可评
        if d <= _lo_cov or lo >= _hi_cov:
            out["F4"] = None
        else:
            s = sum(v for k, v in ipo.items() if lo < k <= d)
            out["F4"] = bool(s >= c["f4"]["funds_win_th"])
    # —— F5 外部（CNH ≤ d；油价/美债严格 < d）——
    trig5, any5 = False, False
    fx = DATA["fx"]
    i = _latest_before(fx, d, strict=False)
    if i is not None and i >= 1:
        any5 = True
        chg = fx[i][1] - fx[i - 1][1]
        net7 = fx[i][1] - fx[max(0, i - 6)][1]
        trig5 |= (chg >= c["f5"]["cnh_daily_th"] or net7 >= c["f5"]["cnh_7d_th"])
    for code, key, th in (("BRENT", "pct", c["f5"].get("oil_daily_th", 3.0)),):
        seq = DATA["intl"].get(code) or []
        j = _latest_before(seq, d, strict=True)
        if j is not None and seq[j][2] is not None:
            any5 = True
            trig5 |= (seq[j][2] >= th)
    # 2026-07-19：债腿降信息层后，回测口径必须与生产一致——否则校准报告会拿一个
    # 生产里已不存在的判据出数（G-X73 同族：口径不匹配的相减）。开关同 config。
    if c["f5"].get("bond_scoring", True):
        seq = DATA["intl"].get("US10Y") or []
        j = _latest_before(seq, d, strict=True)
        if j is not None and seq[j][1] is not None and seq[j][2] is not None:
            any5 = True
            try:
                prev = seq[j][1] / (1 + seq[j][2] / 100.0)
                trig5 |= ((seq[j][1] - prev) * 100.0 >= c["f5"].get("bond_bp_th", 8.0))
            except ZeroDivisionError:
                pass
    out["F5"] = trig5 if any5 else None
    return out


def run(ice_th, write):
    cfg = load_cfg()
    DATA = load_data()
    days = DATA["days"]
    idx = {d: i for i, (d, _) in enumerate(days)}
    rows = []
    for i, (d, _) in enumerate(days):
        if i + 3 >= len(days):
            break
        fwd1 = days[i + 1][1]
        fwd3 = sum(days[i + k][1] for k in (1, 2, 3))
        rows.append({"d": d, "fwd1": fwd1, "fwd3": fwd3, "ice": fwd3 <= ice_th,
                     **eval_day(d, DATA, cfg)})
    base = [r for r in rows if r["ice"]]
    base_rate = len(base) / len(rows) if rows else 0
    lines = []
    lines.append(f"# 五因风险温度 · 回测校准报告（{datetime.date.today().isoformat()}）\n")
    lines.append(f"- 样本：{len(rows)} 个交易日 [{rows[0]['d']}→{rows[-1]['d']}]\n"
                 f"- 冰点定义：未来 3 交易日创业板指累计 ≤ {ice_th}% → 基准冰点率 **{base_rate:.1%}**"
                 f"（{len(base)}/{len(rows)}）\n"
                 f"- 重建口径：外盘严格 <D（真隔夜）｜两融完整日 ≤D｜IPO 滚动{cfg['f4'].get('win_days',20)}日历日 ≤D"
                 f"｜情绪/汇率 ≤D。**F2 仅评情绪腿**（容量腿依赖当日 theme 重算，未按时点重建）。\n")
    lines.append("\n## 单因子表现（现行阈值）\n")
    lines.append(f"> **判定门槛卡的是「独立事件数」不是「触发日数」**（2026-07-19 起）。"
                 f"滚动窗口型因子（F4）会把一轮行情摊成十几个连续触发日，日数虚高但信息量不增。"
                 f"事件切分：相邻触发日间隔 ≤ **{EPISODE_GAP}** 个交易日视为同一轮（工程约定，非实证常数）。\n")
    lines.append("| 因子 | 可评日 | 触发率 | **独立事件** | 日/事件 | P(冰点\\|触发) | lift | 触发日 fwd3 均值 | 未触发 fwd3 均值 | 判定 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    verdicts = {}
    for fid in ("F1", "F2", "F3", "F4", "F5"):
        ev = [r for r in rows if r.get(fid) is not None]
        tr = [r for r in ev if r[fid]]
        nt = [r for r in ev if not r[fid]]
        if not ev:
            lines.append(f"| {fid} | 0 | — | — | — | — | — | — | — | **无数据** |")
            verdicts[fid] = "无数据"
            continue
        eps = episodes([r["d"] for r in tr], idx)
        n_ep = len(eps)
        infl = (len(tr) / n_ep) if n_ep else float("nan")
        p_ice = (sum(1 for r in tr if r["ice"]) / len(tr)) if tr else 0
        b = (sum(1 for r in ev if r["ice"]) / len(ev)) if ev else 0
        lift = (p_ice / b) if b else 0
        f3t = st.fmean([r["fwd3"] for r in tr]) if tr else float("nan")
        f3n = st.fmean([r["fwd3"] for r in nt]) if nt else float("nan")
        # ★ 门槛卡事件数：日数被滚动窗膨胀，不代表独立观测
        if n_ep < MIN_N:
            v = f"样本不足(事件={n_ep})"
        elif lift >= 1.5:
            v = "有区分力"
        elif lift >= 1.15:
            v = "弱区分力"
        else:
            v = "≈噪声·建议调整/退役"
        verdicts[fid] = v
        lines.append(f"| {fid} | {len(ev)} | {len(tr)/len(ev):.1%} ({len(tr)}) | **{n_ep}** | "
                     f"{infl:.1f}× | {p_ice:.1%} | {lift:.2f} | {f3t:+.2f}% | {f3n:+.2f}% | **{v}** |")
    # 阈值敏感性（仅对有历史的 F3/F4）
    lines.append("\n## 阈值敏感性扫描（F3 两融 / F4 IPO）\n")
    for fid, key, grid, unit in (("F1", ("semi_th", "asia_th"), [-1.5, -2, -3, -4, -5, -6], "%"),
                                 ("F3", "rzye_5d_th", [-200, -300, -400, -500, -700, -900], "亿"),
                                 ("F4", "funds_win_th", [100, 150, 200, 300, 400, 500], "亿"),
                                 ("F5", "oil_daily_th", [2, 3, 4, 5, 6], "%油价腿")):
        lines.append(f"\n**{fid} · {key}**\n")
        lines.append("| 阈值 | 触发率 | **独立事件** | 日/事件 | P(冰点\\|触发) | lift | 触发日 fwd3 |")
        lines.append("|---|---|---|---|---|---|---|")
        for g in grid:
            c2 = json.loads(json.dumps(cfg))
            for _k in ((key,) if isinstance(key, str) else key):
                c2[fid.lower()][_k] = g
            ev = tr = 0
            ice = 0
            ice_ev = 0          # 可评日中的冰点数 → 用于算**本因子窗口内**的基准
            f3s = []
            trig_days = []
            for i, (d, _) in enumerate(days):
                if i + 3 >= len(days):
                    break
                v = eval_day(d, DATA, c2)[fid]
                if v is None:
                    continue
                ev += 1
                fwd3_ev = sum(days[i + k][1] for k in (1, 2, 3))
                if fwd3_ev <= ice_th:
                    ice_ev += 1
                if v:
                    tr += 1
                    trig_days.append(d)
                    f3s.append(fwd3_ev)
                    if fwd3_ev <= ice_th:
                        ice += 1
            if not ev:
                continue
            # 2026-07-19 修：原为 b = base_rate（全样本 3.9%），与主表的「本因子可评窗口基准」
            # 不是一把尺 → 同一因子同一阈值在报告里出现两个 lift（如 F4 200亿 主表1.68/扫描1.55）。
            # 扫描表系统性低估约 9%。改为与主表同源：b = 本因子可评窗口内的冰点率。
            # 同 [[通用教训]] G-X75——一份报告里的两张表也必须先可比再并列。
            b = (ice_ev / ev) if ev else 0
            p = (ice / tr) if tr else 0
            n_ep = len(episodes(trig_days, idx))
            infl = (tr / n_ep) if n_ep else float("nan")
            lines.append(f"| {g}{unit} | {tr/ev:.1%} ({tr}) | **{n_ep}** | "
                         f"{(f'{infl:.1f}×' if n_ep else '—')} | {p:.1%} | {(p/b if b else 0):.2f} | "
                         f"{(st.fmean(f3s) if f3s else float('nan')):+.2f}% |")
    # 温度分层
    lines.append("\n## 风险温度分层（触发因子数 → 前向）\n")
    lines.append("| 触发数 | 天数 | 冰点率 | lift | fwd3 均值 |")
    lines.append("|---|---|---|---|---|")
    for n in range(0, 6):
        sub = [r for r in rows if sum(1 for f in ("F1", "F2", "F3", "F4", "F5")
                                      if r.get(f) is True) == n]
        if not sub:
            continue
        p = sum(1 for r in sub if r["ice"]) / len(sub)
        lines.append(f"| {n} | {len(sub)} | {p:.1%} | {(p/base_rate if base_rate else 0):.2f} | "
                     f"{st.fmean([r['fwd3'] for r in sub]):+.2f}% |")
    lines.append("\n> 注：lift>1 才有区分力；**独立事件数 <%d 视为不可信**（2026-07-19 起由卡"
                 "『触发日数』改为卡『独立事件数』——滚动窗口型因子的日数被人为膨胀，"
                 "『日/事件』列即膨胀倍数，越大代表该因子的日数越不能当独立观测读）。"
                 "**过往不代表未来**，本报告为阈值参考、非投资建议。\n" % MIN_N)
    rep = "\n".join(lines)
    print(rep)
    if write:
        p = config.PROJECT_ROOT / "docs" / f"五因回测校准_{datetime.date.today().strftime('%Y%m%d')}.md"
        p.parent.mkdir(exist_ok=True)
        p.write_text(rep, encoding="utf-8")
        logger.info(f"✅ 报告 → {p}")
    return verdicts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ice-th", type=float, default=-5.0, help="冰点阈值：未来3日创业板累计%%")
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args()
    run(args.ice_th, not args.no_write)


if __name__ == "__main__":
    main()
