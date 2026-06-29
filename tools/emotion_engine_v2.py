#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""情绪周期引擎 v2 —— 风险偏好周期（FOMO/fear 反身循环）的定量约束层
（CC 2026-06-10；设计=docs/情绪周期重算-对齐与设计v0-20260610.md，Doctor 五问已闭环）

修复对象：cycle_quant 绝对静态阈值病根（G006/G010）→ 全成分改**滚动分位**（过热度模型宪法）。
定位：参考指标非交易策略——全侧先行、当日即出、无确认期；顶侧置信高/底侧置信低。

成分（8 项，因果分层）：
  因·赚钱效应直测: 晋级率(昨U今连板占比) / 涨停股次日溢价(昨U今日均涨幅)
  果·行为症状:     涨停数 / 跌停数(负) / 涨跌比 / 主线宽度K_day
  果·滞后症状:     成交额变化 / 连板高度(降权·24-09失灵教训)
数据：market_data.db limit_list_daily(全口径已修复) + market_amount_daily + theme_etf_daily
      + stock_daily(涨跌比,仅20260603后可用,缺则该成分剔除并降 confidence)

四季：score 趋势项(MA3-MA10)定上/下行 × 水平项(滚动分位)定季节；
极寒：冬内 跌停>涨停 且 跌停>10 家（资格），强度=跌停数滚动分位（P90+ 深度极寒）。
前瞻倾向：夏×高位→"秋风险积累中"；冬×极寒后→"春机会孕育中"。

用法：
  python3 tools/emotion_engine_v2.py --dry-run                # 历史全跑+校准报告，不写库
  python3 tools/emotion_engine_v2.py --dry-run --w-jinji 2.0  # 晋级率加权（机制检验）
  python3 tools/emotion_engine_v2.py --apply                  # 批准后回填 emotion_cycle
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import sqlite3, argparse, datetime, shutil, csv
from collections import defaultdict
import statistics as st
import config
from lib.logger import get_logger
logger = get_logger(__name__)

PCT_WIN = 50        # 滚动分位基线窗（≈1个周期，§3.3）
MA_S, MA_L = 5, 15  # 趋势均线（2026-06-10 单向状态机后重校准：周期28日/个落先验带内，
                    # 火热点50%/中位+1日·极寒75%/中位0；MA3/10周期过快17个，MA5/20火热点掉30%）
EXTREME_DOWN_MIN = 10  # 极寒资格：跌停>10家（Doctor 经验下限）
LV_FIRE = 80        # 火热点：夏×分位≥80（2026-06-10 校准：12点vs市场11高点，命中42%，中位先行6.5日）
FIRE_GAP = 20       # 火热点去重间隔（交易日），防单日回落毛刺重复触发


def rolling_pct(series, win=PCT_WIN):
    """值→滚动分位(0-100)，窗口不足用已有样本（≥10）"""
    out = {}
    keys = sorted(series)
    vals = [series[k] for k in keys]
    for i, k in enumerate(keys):
        lo = max(0, i - win + 1)
        window = [v for v in vals[lo:i + 1] if v is not None]
        v = vals[i]
        if v is None or len(window) < 10:
            out[k] = None
            continue
        out[k] = 100.0 * sum(1 for x in window if x <= v) / len(window)
    return out


def load_indicators(md):
    """→ {date: {ind: value}}，date=YYYYMMDD"""
    ind = defaultdict(dict)
    # 涨停/跌停/连板高度/晋级率/次日溢价（limit_list_daily，全口径）
    days = [r[0] for r in md.execute(
        "SELECT DISTINCT trade_date FROM limit_list_daily ORDER BY trade_date")]
    lu, ld, hmax, uset, uret = {}, {}, {}, {}, {}
    for d in days:
        rows = md.execute("SELECT ts_code, limit_type, limit_times, pct_chg "
                          "FROM limit_list_daily WHERE trade_date=?", (d,)).fetchall()
        us = {r[0] for r in rows if r[1] == "U"}
        lu[d] = len(us)
        ld[d] = sum(1 for r in rows if r[1] == "D")
        hmax[d] = max([r[2] for r in rows if r[1] == "U"] or [0])
        uset[d] = us
    for i in range(1, len(days)):
        y, t = days[i - 1], days[i]
        if not uset[y]:
            continue
        # 晋级率：昨U今日仍U
        ind[t]["jinji"] = 100.0 * len(uset[y] & uset[t]) / len(uset[y])
        # 次日溢价：昨U今日均涨幅（stock_daily 覆盖则算）
        q = ",".join("?" * len(uset[y]))
        prem = md.execute(f"SELECT AVG(pct_chg) FROM stock_daily "
                          f"WHERE trade_date=? AND ts_code IN ({q})",
                          (t, *uset[y])).fetchone()[0]
        ind[t]["premium"] = prem
    for d in days:
        ind[d]["limit_up"] = lu[d]
        ind[d]["limit_down"] = ld[d]
        ind[d]["height"] = hmax[d]
    # 成交额（5日变化率，水位归容量模块管）
    amt = dict(md.execute("SELECT trade_date, total_trillion FROM market_amount_daily"))
    ks = sorted(amt)
    for i, d in enumerate(ks):
        if i >= 5 and amt[ks[i - 5]]:
            ind[d]["vol_chg"] = 100.0 * (amt[d] / amt[ks[i - 5]] - 1)
    # 涨跌比（仅全市场段）
    for d, up, dn in md.execute(
            "SELECT trade_date, SUM(pct_chg>0), SUM(pct_chg<0) FROM stock_daily "
            "WHERE trade_date>='20260603' GROUP BY trade_date"):
        if dn:
            ind[d]["updown"] = up / dn
    # 主线宽度 K_day（theme_etf 涨>1% 主线数，复用容量口径）
    _sys.path.insert(0, str(config.PROJECT_ROOT / "scripts"))
    from fetch_theme_etf import THEME_ETF, BENCHMARK
    px = defaultdict(dict)
    for d, c, p in md.execute("SELECT trade_date, etf_code, pct_chg FROM theme_etf_daily "
                              "WHERE pct_chg IS NOT NULL"):
        px[c][d] = p / 100
    for d in sorted(px[BENCHMARK]):
        k = 0
        for t, cs in THEME_ETF.items():
            vals = [px[c][d] for c in cs if d in px[c]]
            if vals and sum(vals) / len(vals) > 0.01:
                k += 1
        ind[d]["kday"] = k
    return ind, days


# 成分定义: (键, 方向+1/-1, 权重, 层)
COMPONENTS = [
    ("jinji",      +1, 1.0, "因"),   # 晋级率
    ("premium",    +1, 1.0, "因"),   # 涨停次日溢价
    ("limit_up",   +1, 1.0, "果"),
    ("limit_down", -1, 1.0, "果"),
    ("updown",     +1, 1.0, "果"),
    ("kday",       +1, 1.0, "果"),
    ("vol_chg",    +1, 1.0, "滞后"),
    ("height",     +1, 0.5, "滞后"),  # 连板高度降权（24-09 失灵）
]


def compute(md, w_jinji=1.0, pct_win=PCT_WIN):
    ind, days = load_indicators(md)
    pcts = {}
    for key, _d, _w, _l in COMPONENTS:
        pcts[key] = rolling_pct({d: ind[d].get(key) for d in days}, pct_win)
    out = []
    score_hist = {}
    for d in days:
        num = den = 0.0
        used = 0
        for key, sign, w, _l in COMPONENTS:
            if key == "jinji":
                w = w * w_jinji
            p = pcts[key].get(d)
            if p is None:
                continue
            num += w * (p if sign > 0 else 100 - p)
            den += w
            used += 1
        if den == 0:
            continue
        score = num / den
        score_hist[d] = score
        out.append(dict(date=d, score=round(score, 1), used=used,
                        confidence=round(used / len(COMPONENTS), 2),
                        limit_up=ind[d].get("limit_up"), limit_down=ind[d].get("limit_down"),
                        jinji=ind[d].get("jinji"),
                        premium=ind[d].get("premium"), height=ind[d].get("height")))
    # 趋势 + 单向季节状态机（Doctor 2026-06-10 四次对齐：春夏秋冬单向前进，倒退=报错修正）
    ks = [r["date"] for r in out]
    sc = [r["score"] for r in out]
    spct = rolling_pct(dict(zip(ks, sc)), pct_win)
    season_conf = {"春": "低", "夏": "高", "秋": "高", "冬": "低"}  # 顶底不对称→置信
    for i, r in enumerate(out):
        mas = st.fmean(sc[max(0, i - MA_S + 1):i + 1])
        mal = st.fmean(sc[max(0, i - MA_L + 1):i + 1])
        r["_up"] = mas >= mal
        r["_lv"] = spct.get(r["date"]) or 50

    ORDER = ["春", "夏", "秋", "冬"]
    S, cyc, corrections = None, 1, 0
    trans_idx = 0            # 当前段起点
    summer_peak = None       # 本周期夏段评分峰值（秋/冬修正基准）
    winter_trough = None     # 上周期冬段评分谷值（春修正基准）
    prev_winter_trough = None
    for i, r in enumerate(out):
        up, lv, s = r["_up"], r["_lv"], r["score"]
        if S is None:
            S = ("春" if lv < 60 else "夏") if up else ("秋" if lv >= 40 else "冬")
        else:
            # ── 修正触发器（先于推进判断）──
            if S in ("秋", "冬") and summer_peak is not None and s > summer_peak:
                # 秋/冬报错：FOMO 未死，本段撤回为夏
                for j in range(trans_idx, i):
                    out[j]["season"] = "夏"
                    out[j]["corrected"] = True
                S, corrections = "夏", corrections + 1
                trans_idx = i
            elif S in ("春", "夏") and winter_trough is not None and s < winter_trough \
                    and cyc > 1 and trans_idx > 0 and out[trans_idx - 1].get("season") == "冬":
                # 春报错：fear 未尽，撤回新周期宣告
                for j in range(trans_idx, i):
                    out[j]["season"] = "冬"
                    out[j]["corrected"] = True
                S, cyc, corrections = "冬", cyc - 1, corrections + 1
                trans_idx = i
            else:
                # ── 单向推进（先行，无确认期）──
                adv = ((S == "春" and up and lv >= 60) or
                       (S == "夏" and not up) or
                       (S == "秋" and not up and lv < 40) or
                       (S == "冬" and up))
                if adv:
                    if S == "冬":
                        prev_winter_trough = winter_trough
                    S = ORDER[(ORDER.index(S) + 1) % 4]
                    if S == "春":
                        cyc += 1
                        winter_trough = prev_winter_trough if prev_winter_trough is not None else winter_trough
                    if S == "夏":
                        summer_peak = s   # 新夏段重置峰值
                    trans_idx = i
        if S == "夏":
            summer_peak = max(summer_peak if summer_peak is not None else s, s)
        if S == "冬":
            winter_trough = min(winter_trough if winter_trough is not None else s, s)
        extreme = (S == "冬" and r["limit_down"] is not None
                   and r["limit_up"] is not None
                   and r["limit_down"] > r["limit_up"]
                   and r["limit_down"] > EXTREME_DOWN_MIN)
        hint = ""
        if S == "冬" and extreme:
            hint = "极寒"
        elif S == "冬" and i >= 1 and out[i - 1].get("extreme"):
            hint = "春机会孕育中"
        r.update(season=S, cycle_no=cyc, level_pct=round(r.pop("_lv"), 1),
                 trend="上行" if r.pop("_up") else "下行",
                 extreme=extreme, hint=hint, season_confidence=season_conf[S])
        r.setdefault("corrected", False)
    logger.info(f"单向状态机：周期数 {cyc} | 修正(报错撤回) {corrections} 次")
    # 火热点（先行风险提示）：夏×分位≥LV_FIRE 的段首日 + FIRE_GAP 去重
    armed, last_fire = True, None
    for i, r in enumerate(out):
        if r["season"] == "夏" and (r["level_pct"] or 0) >= LV_FIRE:
            if armed and (last_fire is None or i - last_fire >= FIRE_GAP):
                r["hint"] = "🔥火热点·秋风险积累中"
                r["fire_point"] = True
                last_fire = i
            armed = False
        else:
            armed = True
        r.setdefault("fire_point", False)
    return out


def market_extrema(md, fractal=10):
    """510300 pct_chg 累积指数 → ±fractal 日分形高/低点"""
    rows = md.execute("SELECT trade_date, pct_chg FROM theme_etf_daily "
                      "WHERE etf_code='510300.SH' AND pct_chg IS NOT NULL "
                      "ORDER BY trade_date").fetchall()
    idx, lvl = [], 1.0
    for d, p in rows:
        lvl *= (1 + p / 100)
        idx.append((d, lvl))
    highs, lows = [], []
    for i in range(fractal, len(idx) - fractal):
        win = [v for _, v in idx[i - fractal:i + fractal + 1]]
        if idx[i][1] == max(win):
            highs.append(idx[i][0])
        if idx[i][1] == min(win):
            lows.append(idx[i][0])
    return highs, lows


def calibrate(out, md):
    """夏→秋交界 vs 局部高点 / 极寒 vs 局部低点 的距离（§3.4 非对称评分）"""
    highs, lows = market_extrema(md)
    days = [r["date"] for r in out]

    def dist(d, targets):  # 交易日距离，先行为负
        if not targets:
            return None
        i = days.index(d)
        best = None
        for t in targets:
            if t in days:
                v = days.index(t) - i   # >0 = 信号先行
                if best is None or abs(v) < abs(best):
                    best = v
        return best
    boundaries = [r["date"] for r in out if r.get("fire_point")]
    extremes = [r["date"] for r in out if r["extreme"]]
    bd = [dist(d, highs) for d in boundaries]
    ed = [dist(d, lows) for d in extremes]
    bd = [x for x in bd if x is not None]
    ed = [x for x in ed if x is not None]

    def score(ds):  # 非对称：先行0~5日最优
        if not ds:
            return None, None, None
        hit = sum(1 for x in ds if -3 <= x <= 5) / len(ds)
        med = st.median(ds)
        return hit, med, len(ds)
    return dict(boundary=score(bd), extreme=score(ed),
                n_high=len(highs), n_low=len(lows),
                boundaries=boundaries, extreme_days=extremes)


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    ap.add_argument("--w-jinji", type=float, default=1.0)
    ap.add_argument("--pct-win", type=int, default=PCT_WIN)
    args = ap.parse_args()

    md = sqlite3.connect(f"file:{config.MARKET_DB}?mode=ro", uri=True)
    out = compute(md, args.w_jinji, args.pct_win)
    cal = calibrate(out, md)
    logger.info(f"历史 {len(out)} 日 [{out[0]['date']}→{out[-1]['date']}] "
                f"w_jinji={args.w_jinji} win={args.pct_win}")
    seasons = defaultdict(int)
    for r in out:
        seasons[r["season"]] += 1
    logger.info(f"季节分布: {dict(seasons)} | 极寒日 {sum(1 for r in out if r['extreme'])} 天")
    bh, bm, bn = cal["boundary"]
    eh, em, en = cal["extreme"]
    logger.info(f"🔥 夏→秋交界 {bn or 0} 次: 命中率(−3~+5日内贴高点)={bh and f'{bh:.0%}'} 中位距离={bm}")
    logger.info(f"🧊 极寒 {en or 0} 天: 命中率(贴低点)={eh and f'{eh:.0%}'} 中位距离={em}")
    logger.info(f"   (市场分形高点 {cal['n_high']} 个 / 低点 {cal['n_low']} 个)")
    logger.info(f"   交界日: {cal['boundaries']}")
    logger.info(f"   极寒日: {cal['extreme_days'][:12]}")

    rpt = config.PROJECT_ROOT / "docs" / \
        f"情绪周期v2_历史序列_{datetime.date.today():%Y%m%d}.tsv"
    cols = ["date", "score", "level_pct", "trend", "cycle_no", "season", "corrected",
            "season_confidence", "hint", "extreme", "jinji", "limit_up", "limit_down",
            "confidence"]
    with open(rpt, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        w.writerows(out)
    logger.info(f"📄 历史序列 → {rpt}")

    if args.apply:
        rc = sqlite3.connect(config.RECAP_DB)
        bak = config.RECAP_DB + f".bak_{datetime.date.today():%Y%m%d}_emotionv2"
        shutil.copy2(config.RECAP_DB, bak)
        logger.info(f"📦 备份 → {bak}")
        have = {x[1] for x in rc.execute("PRAGMA table_info(emotion_cycle)")}
        if "cycle_no" not in have:
            rc.execute("ALTER TABLE emotion_cycle ADD COLUMN cycle_no INTEGER")
            logger.info("  + emotion_cycle.cycle_no INTEGER（单向状态机周期编号）")
        for _col, _typ in (("jinji", "REAL"), ("premium", "REAL"), ("height", "INTEGER")):
            if _col not in have:
                rc.execute(f"ALTER TABLE emotion_cycle ADD COLUMN {_col} {_typ}")
                logger.info(f"  + emotion_cycle.{_col} {_typ}（情绪变量落库·供日报 chip）")
        n = 0
        for r in out:
            iso = f"{r['date'][:4]}-{r['date'][4:6]}-{r['date'][6:]}"
            rc.execute(
                "INSERT INTO emotion_cycle(date, limit_up, limit_down, emotion_score,"
                " emotion_season, risk_appetite, position_suggestion, cycle_no,"
                " jinji, premium, height, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,datetime('now'))"
                " ON CONFLICT(date) DO UPDATE SET limit_up=excluded.limit_up,"
                " limit_down=excluded.limit_down, emotion_score=excluded.emotion_score,"
                " emotion_season=excluded.emotion_season,"
                " risk_appetite=excluded.risk_appetite,"
                " position_suggestion=excluded.position_suggestion,"
                " cycle_no=excluded.cycle_no,"
                " jinji=excluded.jinji, premium=excluded.premium, height=excluded.height,"
                " updated_at=datetime('now')",
                (iso, r["limit_up"], r["limit_down"], r["score"],
                 r["season"] + (("·" + r["hint"]) if r["hint"] else ""),
                 {"春": "中", "夏": "高", "秋": "中", "冬": "低"}[r["season"]],
                 None, r["cycle_no"],
                 r.get("jinji"), r.get("premium"), r.get("height")))   # 仓位建议归三口径并列展示，引擎不代填
            n += 1
        rc.commit()
        logger.info(f"✅ emotion_cycle 回填 {n} 日（季节含前瞻倾向后缀；仓位列留空=三口径并列原则）")
    else:
        logger.info("🔍 dry-run 完成，未写库。")


if __name__ == "__main__":
    main()
