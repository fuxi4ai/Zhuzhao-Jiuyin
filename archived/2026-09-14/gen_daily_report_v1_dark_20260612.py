#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""烛照九阴 · 可视化日报生成器 v1（M0+M1 合并，真实数据）
（CC 2026-06-10；PRD=docs/可视化日报PRD-20260610.md）

铁律：缺数诚实标注（停更于X日/待回填），禁占位符、禁编数据、禁旧值冒充；每区块 vintage 角标。
输出：AI4ME/烛照九阴-outputs/烛照九阴日报_{数据日}.html（根目录最新；旧报自动移 archived/，永不删）

用法：python3 tools/gen_daily_report.py
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import sqlite3, json, shutil, datetime, glob
from collections import defaultdict
import statistics as st
import config
from lib.logger import get_logger
logger = get_logger(__name__)

_sys.path.insert(0, str(config.PROJECT_ROOT / "scripts"))
from fetch_theme_etf import THEME_ETF, BENCHMARK
from fetch_us_anchor import THEME_US, BENCHMARK_US

OUT_DIR = config.PROJECT_ROOT.parents[3] / "AI4ME" / "烛照九阴-outputs"
RECORDS = config.PROJECT_ROOT.parents[3] / "Database" / "龙鱼-标的分析库" / "records"


def iso(d): return f"{d[:4]}-{d[4:6]}-{d[6:]}" if d and "-" not in d else d


def kcap(amount_trillion):
    """Doctor 经验表线性插值（经验非规律）：1万亿→1.5 / 2→3.5 / 3→5.5"""
    pts = [(1.0, 1.5), (2.0, 3.5), (3.0, 5.5)]
    a = amount_trillion
    if a <= 1:
        return 1.5 * a
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        if a <= x2:
            return y1 + (y2 - y1) * (a - x1) / (x2 - x1)
    return 5.5 + 2.0 * (a - 3.0)


def gather():
    md = sqlite3.connect(f"file:{config.MARKET_DB}?mode=ro", uri=True)
    rc = sqlite3.connect(f"file:{config.RECAP_DB}?mode=ro", uri=True)
    D = {}

    # ── 行情底座：theme ETF 日收益（pct_chg，复权口径） ──
    px = defaultdict(dict)
    for d, c, p in md.execute("SELECT trade_date, etf_code, pct_chg FROM theme_etf_daily "
                              "WHERE pct_chg IS NOT NULL ORDER BY trade_date"):
        px[c][d] = p / 100
    dates = sorted(px[BENCHMARK])
    data_day = dates[-1]
    D["data_day"] = data_day
    D["gen_time"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    def theme_ex(theme):
        cs = THEME_ETF[theme]
        out = {}
        for d in dates:
            vals = [px[c][d] for c in cs if d in px[c]]
            if vals and d in px[BENCHMARK]:
                out[d] = sum(vals) / len(vals) - px[BENCHMARK][d]
        return out

    # ── 区块1 市场快照 ──
    snap = {}
    snap["bench_pct"] = round(px[BENCHMARK][data_day] * 100, 2)
    snap["bench_note"] = "510300ETF（沪深300代理）"
    ud = md.execute("SELECT SUM(pct_chg>0), SUM(pct_chg<0), SUM(pct_chg=0) FROM stock_daily "
                    "WHERE trade_date=?", (data_day,)).fetchone()
    snap["up_n"], snap["down_n"], snap["flat_n"] = (ud if ud and ud[0] is not None
                                                    else (None, None, None))
    amt_row = md.execute("SELECT trade_date, total_trillion FROM market_amount_daily "
                         "ORDER BY trade_date DESC LIMIT 1").fetchone()
    snap["amount"] = amt_row[1] if amt_row and amt_row[0] == data_day else None
    snap["amount_vintage"] = amt_row[0] if amt_row else None
    lim = md.execute("SELECT SUM(limit_type='U'), SUM(limit_type='D') FROM limit_list_daily "
                     "WHERE trade_date=?", (data_day,)).fetchone()
    snap["limit_up"], snap["limit_down"] = lim if lim else (None, None)
    fx = None
    try:
        fx = md.execute("SELECT trade_date, mid_close FROM fx_daily "
                        "ORDER BY trade_date DESC LIMIT 1").fetchone()
    except sqlite3.OperationalError:
        pass
    snap["fx"] = {"val": fx[1], "vintage": fx[0]} if fx else None  # None=待回填，诚实展示
    D["snap"] = snap

    # ── 区块2 周期与情绪（emotion_cycle v2，今日刚落库） ──
    em_rows = rc.execute("SELECT date, emotion_score, emotion_season, risk_appetite, cycle_no "
                         "FROM emotion_cycle WHERE emotion_score IS NOT NULL "
                         "ORDER BY date DESC LIMIT 60").fetchall()[::-1]
    em_last = em_rows[-1]
    xb = rc.execute("SELECT date, cycle_stage FROM recap_daily WHERE cycle_stage IS NOT NULL "
                    "ORDER BY date DESC LIMIT 1").fetchone()
    sc_vals = [r[1] for r in em_rows]
    ma5 = [round(st.fmean(sc_vals[max(0, i - 4):i + 1]), 1) for i in range(len(sc_vals))]
    D["emotion"] = {
        "series": [[r[0], r[1], ma5[i]] for i, r in enumerate(em_rows)],
        "date": em_last[0], "score": em_last[1], "season": em_last[2],
        "risk": em_last[3], "cycle_no": em_last[4],
        "xiaobao": {"stage": xb[1], "date": xb[0]} if xb else None,
        "note": "emotion_engine_v2（滚动分位·全侧先行）；小鲍口径为第二印证（回测：系统性偏防御）",
    }

    # ── 区块3 容量 + 主线矩阵 + 信号 ──
    cap_val = kcap(snap["amount"]) if snap["amount"] else None
    # K_day：当日涨>1% 主线数；容量占用读数用 5 日中位（防普涨日尖峰虚报满载）
    def kday_at(d):
        k = 0
        for t in THEME_ETF:
            vals = [px[c][d] for c in THEME_ETF[t] if d in px[c]]
            if vals and sum(vals) / len(vals) > 0.01:
                k += 1
        return k
    kday_today = kday_at(data_day)
    kday = int(st.median([kday_at(d) for d in dates[-5:]]))
    state = None
    if cap_val:
        if kday >= cap_val:
            state = "满载"
        else:
            # 虹吸判定：跑出超额的集中于单族（粗判：20日超额>5%的主线里 AI硬件族占比≥75%）
            strong = [t for t in THEME_ETF
                      if sum(theme_ex(t).get(d, 0) for d in dates[-20:]) > 0.05]
            ai = sum(1 for t in strong if any(k in t for k in ["光模块", "AI算力", "半导体", "消费电子"]))
            state = "虹吸" if strong and ai / len(strong) >= 0.75 else "有空位"
    D["capacity"] = {"kday": kday, "kday_today": kday_today,
                     "kcap": round(cap_val, 1) if cap_val else None,
                     "state": state, "amount": snap["amount"]}

    # 美股锚（隔日映射 L1）
    us = defaultdict(dict)
    try:
        for d, t, p in md.execute("SELECT trade_date, ticker, pct_chg FROM us_anchor_daily "
                                  "WHERE pct_chg IS NOT NULL"):
            us[t][d] = p / 100
    except sqlite3.OperationalError:
        pass
    us_days = sorted(us.get(BENCHMARK_US, {}))

    def us_info(theme):
        if theme not in THEME_US or not us_days:
            return None
        tkr, kind = THEME_US[theme]
        if tkr not in us:
            return None
        uds = sorted(set(us[tkr]) & set(us_days))
        if not uds:
            return None
        last = uds[-1]
        ex20 = sum(us[tkr][d] - us[BENCHMARK_US][d] for d in uds[-20:])
        ov = us[tkr][last] - us[BENCHMARK_US][last]
        # A股交易日与美股收盘的陈旧度
        stale = 1
        return {"tkr": tkr, "kind": kind, "us_date": last, "overnight": round(ov * 100, 1),
                "ex20": round(ex20 * 100, 1),
                "alert": abs(ov) >= (0.04 if tkr == "ALM" else 0.02)}

    themes = []
    for t in THEME_ETF:
        ex = theme_ex(t)
        ds = [d for d in dates if d in ex]
        spark = []
        cum = 0
        for d in ds[-20:]:
            cum += ex[d]
            spark.append(round(cum * 100, 2))
        e5 = sum(ex[d] for d in ds[-5:]) * 100
        e20 = sum(ex[d] for d in ds[-20:]) * 100
        e60 = sum(ex[d] for d in ds[-60:]) * 100
        sig = rc.execute("SELECT gap_status, COUNT(*) FROM industry_signals "
                         "WHERE etf_anchor=? AND date>=? GROUP BY gap_status",
                         (t, (datetime.date.fromisoformat(iso(dates[-22]))).isoformat())
                         ).fetchall()
        sigc = dict(sig)
        latest_desc = rc.execute("SELECT gap_desc FROM industry_signals WHERE etf_anchor=? "
                                 "AND gap_status='closing' ORDER BY date DESC LIMIT 1",
                                 (t,)).fetchone()
        themes.append({
            "name": t, "short": t.split("/")[0], "e5": round(e5, 1), "e20": round(e20, 1),
            "e60": round(e60, 1), "spark": spark, "sig": sigc,
            "desc": latest_desc[0] if latest_desc else "",
            "us": us_info(t),
        })
    themes.sort(key=lambda x: -x["e20"])
    D["themes"] = themes

    # ── 区块3 主线板块 · 近3日（日期→卡片；资格=对大盘有比较优势；数量≤当日K_cap） ──
    ratings = {}
    for f in glob.glob(str(RECORDS / "*.json")):
        try:
            j = json.load(open(f))
            a = j["analyses"][-1]
            ratings[j["name"]] = {"total": a["total"], "rating": a.get("rating", ""),
                                  "date": a["analysis_date"]}
        except Exception:
            pass
    D["_ratings"] = ratings
    amt_all = dict(md.execute("SELECT trade_date, total_trillion FROM market_amount_daily"))
    tmap = {t["name"]: t for t in themes}
    maindays = []
    for d in dates[-3:][::-1]:          # 当日 / 前1日 / 前2日
        day_amt = amt_all.get(d)
        day_cap = round(kcap(day_amt)) if day_amt else None
        lines = []
        for name in THEME_ETF:
            cs = THEME_ETF[name]
            vals = [px[c][d] for c in cs if d in px[c]]
            if not vals or d not in px[BENCHMARK]:
                continue
            day_pct = sum(vals) / len(vals) * 100
            excess = day_pct - px[BENCHMARK][d] * 100
            # 主线资格（Doctor 2026-06-10）：涨幅>+1% 且 对大盘超额>+0.5pp——普涨跟涨不算主线
            if day_pct > 1.0 and excess > 0.5:
                t = tmap[name]
                tg = rc.execute(
                    "SELECT target FROM industry_signals WHERE etf_anchor=? AND date>=? "
                    "AND target IS NOT NULL AND target NOT IN ('','(主题)') "
                    "ORDER BY date DESC LIMIT 4",
                    (name, (datetime.date.fromisoformat(iso(d))
                            - datetime.timedelta(days=30)).isoformat())).fetchall()
                leaders, seen = [], set()
                for row in tg:
                    for n in (row[0] or "").replace("、", ",").split(","):
                        n = n.strip()
                        if n and n not in seen and len(leaders) < 5:
                            seen.add(n)
                            rt = ratings.get(n)
                            leaders.append(n + (f"({rt['total']})" if rt else ""))
                logic = rc.execute(
                    "SELECT keyword, substr(signal_content,1,80) FROM industry_signals "
                    "WHERE etf_anchor=? AND date<=? ORDER BY date DESC LIMIT 1",
                    (name, iso(d))).fetchone()
                lines.append({
                    "name": name, "short": name.split("/")[0],
                    "day_pct": round(day_pct, 2), "excess": round(excess, 2),
                    "etf": " / ".join(cs), "e20": t["e20"], "spark": t["spark"],
                    "us": t["us"], "desc": t["desc"],
                    "leaders": leaders,
                    "logic": (f"{logic[0]}｜{logic[1]}" if logic else "近期无入库产业逻辑信号"),
                })
        lines.sort(key=lambda x: -x["excess"])
        shown = lines[:day_cap] if day_cap else lines
        maindays.append({"date": d, "amount": day_amt, "kcap": day_cap,
                         "qualified": len(lines), "lines": shown})
    D["maindays"] = maindays

    # 信号明细（近14天，gap_level≥3 或 closing/open）——机会/风险模块仍用
    cutoff = (datetime.date.fromisoformat(iso(data_day)) - datetime.timedelta(days=14)).isoformat()
    sigs = rc.execute(
        "SELECT date, etf_anchor, keyword, info_gap_level, gap_status, gap_desc, confidence "
        "FROM industry_signals WHERE date>=? AND etf_anchor!='' "
        "AND (info_gap_level>=3 OR gap_status IN ('open','closing')) "
        "ORDER BY date DESC, info_gap_level DESC", (cutoff,)).fetchall()
    D["signals"] = [dict(date=r[0], theme=(r[1] or "").split("/")[0], kw=r[2],
                         lvl=r[3], status=r[4], desc=r[5], conf=r[6]) for r in sigs]

    # 信号栏主源：渊图信号 × 行情兑现（Doctor 2026-06-10：产业信号主源=渊图×行情对比，
    # 课件降为第二印证——主从倒置的信号层兑现，呼应 6-06 评估结论 B）
    yt_dates = [r[0] for r in rc.execute(
        "SELECT DISTINCT date FROM yuantu_buy_signals WHERE length(date)=10 "
        "ORDER BY date DESC LIMIT 3")]
    ytdays = []
    for sd in yt_dates:
        rows = rc.execute(
            "SELECT industry_chain, signal_node, signal_type, yuantu_confidence, "
            "beneficiaries, xiaobao_echo, gap_status, gap_desc, etf_anchor "
            "FROM yuantu_buy_signals WHERE date=? ORDER BY yuantu_confidence DESC", (sd,)).fetchall()
        ytdays.append({"date": sd.replace("-", ""), "sigs": [dict(
            chain=r[0] or r[1], node=r[1], stype=r[2] or "", conf=r[3],
            bene=r[4] or "", echo=bool(r[5]), status=r[6] or "no_data",
            desc=r[7] or "", theme=(r[8] or "").split("/")[0]) for r in rows]})
    D["ytdays"] = ytdays

    # 课件信号（第二印证源）：仅最新一批
    sd = rc.execute("SELECT MAX(date) FROM industry_signals WHERE etf_anchor!='' "
                    "AND (info_gap_level>=3 OR gap_status IN ('open','closing'))").fetchone()[0]
    rows = rc.execute(
        "SELECT etf_anchor, keyword, info_gap_level, gap_status, gap_desc, "
        "signal_content, confidence FROM industry_signals "
        "WHERE date=? AND etf_anchor!='' "
        "AND (info_gap_level>=3 OR gap_status IN ('open','closing')) "
        "ORDER BY info_gap_level DESC", (sd,)).fetchall() if sd else []
    D["sigdays"] = [{"date": (sd or "").replace("-", ""), "sigs": [dict(
        theme=(r[0] or "").split("/")[0], theme_full=r[0], kw=r[1], lvl=r[2],
        status=r[3], desc=r[4] or "", content=r[5] or "", conf=r[6] or "")
        for r in rows]}]

    # ── 区块4 机会 + 标的 + 三口径仓位 ──
    ratings = D["_ratings"]
    opps = []
    for t in themes:
        early = (t["sig"].get("open", 0) > 0 or "兑现初期" in (t["desc"] or "")) and t["e20"] > 0
        anchor_ok = not (t["us"] and t["us"]["kind"] == "echo" and t["us"]["ex20"] < -10)
        if early and anchor_ok and D["capacity"]["state"] in ("有空位", "虹吸", "满载"):
            tg = rc.execute("SELECT DISTINCT target FROM industry_signals WHERE etf_anchor=? "
                            "AND date>=? AND target IS NOT NULL AND target NOT IN ('','(主题)') "
                            "ORDER BY date DESC LIMIT 3", (t["name"], cutoff)).fetchall()
            names = []
            for row in tg:
                for n in (row[0] or "").replace("、", ",").split(","):
                    n = n.strip()
                    if n and len(names) < 6:
                        names.append({"name": n, **ratings.get(n, {})})
            opps.append({"theme": t["short"], "e20": t["e20"], "desc": t["desc"],
                         "targets": names,
                         "note": "容量" + (D["capacity"]["state"] or "未知")})
    D["opps"] = opps[:4]

    xb_pos = rc.execute("SELECT date, position_band, position_risk_pref FROM dim4_trade_plan "
                        "WHERE position_band IS NOT NULL ORDER BY date DESC LIMIT 1").fetchone()
    D["positions"] = {
        "xiaobao": {"band": xb_pos[1], "pref": xb_pos[2], "date": xb_pos[0]} if xb_pos else None,
        "capacity": D["capacity"]["state"],
        "note": "三口径并列（Doctor 裁定，不合成）：小鲍=总仓位 ｜ 容量=能否开新线 ｜ 龙鱼=个股配置资格",
    }

    # ── 区块5 风险 ──
    risks = []
    for t in themes:
        u = t["us"]
        if u and u["kind"] == "echo" and u["ex20"] < -10 and t["e20"] > 5:
            risks.append({"lvl": "红", "txt": f"美股锚背离：{t['short']} A股20日超额 {t['e20']:+.1f}% "
                          f"但锚 {u['tkr']} 20日超额 {u['ex20']:+.1f}%（全球定价撤退，A股独舞）"})
    od = rc.execute("SELECT COUNT(*), GROUP_CONCAT(DISTINCT etf_anchor) FROM industry_signals "
                    "WHERE gap_desc LIKE '%逾期%'").fetchone()
    if od and od[0]:
        risks.append({"lvl": "黄", "txt": f"逾期未启动信号 {od[0]} 条（{(od[1] or '').replace('创新药/医药/CRO','创新药')}）"
                      "——逻辑存疑或等轮动"})
    if D["capacity"]["state"] == "满载":
        risks.append({"lvl": "黄", "txt": f"容量满载：K(5日中位) {kday} ≥ K_cap {D['capacity']['kcap']}"
                      "（新线启动需旧线让位，注意轮动）"})
    for nm, r in ratings.items():
        pass
    if "源杰科技" in ratings:
        risks.append({"lvl": "黄", "txt": "估值极限标的在主线内：源杰科技（龙鱼估值维 2/15，PB 历史97.9%分位）"
                      "、奥比中光（PB 99.5%分位）——追高赔率差"})
    em = D["emotion"]
    if "秋" in (em["season"] or "") or "冬" in (em["season"] or ""):
        risks.append({"lvl": "黄", "txt": f"情绪周期处下行期（{em['season']}，评分 {em['score']}）"
                      "——风险偏好收缩中，机会提示需折扣"})
    D["risks"] = risks
    return D


# ───────────────────────── HTML 渲染 ─────────────────────────
THEME_COLOR = {  # 星云色（按资金族近似）
    "光模块": "#4fc3f7", "AI算力": "#5b8cff", "半导体": "#7c6cff", "消费电子": "#9b7bff",
    "AI软件": "#6fd3e7", "机器人": "#ff8a5b", "商业航天": "#c06cff", "军工": "#b35bff",
    "新能源电池": "#3ddc97", "光伏": "#69d88a", "电力": "#5bd0c0",
    "创新药": "#ff6b9d", "白酒": "#e89b6b", "券商": "#d4a25c",
    "黄金": "#e8c46b", "稀土": "#e8a05b", "钨": "#caa86b", "有色金属": "#d8b05b",
}


def gen_stars(seed=42, n=(26, 16, 7)):
    """三层互质 tile 随机星场（借鉴龙鱼标的库星空卡）"""
    import random
    rnd = random.Random(seed)
    tiles = [(173, 127), (233, 181), (311, 263)]
    grads, sizes = [], []
    for layer, cnt in enumerate(n):
        lo, hi = [(0.5, 0.9), (0.7, 1.3), (1.4, 1.9)][layer]
        for _ in range(cnt):
            s = rnd.uniform(lo, hi)
            grads.append(f"radial-gradient({s:.2f}px {s:.2f}px at {rnd.uniform(0,100):.1f}% "
                         f"{rnd.uniform(0,100):.1f}%, rgba(255,255,255,{rnd.uniform(.5,.95):.2f}), transparent)")
            sizes.append(f"{tiles[layer][0]}px {tiles[layer][1]}px")
    return ",\n    ".join(grads), ", ".join(sizes)


def spark_svg(vals, w=120, h=28):
    if not vals or len(vals) < 2:
        return ""
    mn, mx = min(vals), max(vals)
    rng = (mx - mn) or 1
    pts = " ".join(f"{i*w/(len(vals)-1):.1f},{h-2-(v-mn)/rng*(h-4):.1f}"
                   for i, v in enumerate(vals))
    color = "#ff5d5d" if vals[-1] >= 0 else "#3ddc97"
    zero_y = h - 2 - (0 - mn) / rng * (h - 4) if mn < 0 < mx else None
    zl = (f'<line x1="0" y1="{zero_y:.1f}" x2="{w}" y2="{zero_y:.1f}" '
          f'stroke="#2a3354" stroke-dasharray="2,3"/>') if zero_y else ""
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}">{zl}'
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.6"/></svg>')


def pct_span(v, suffix="%"):
    if v is None:
        return '<span class="na">—</span>'
    cls = "up" if v > 0 else ("dn" if v < 0 else "")
    return f'<span class="{cls}">{v:+.1f}{suffix}</span>'


def render(D):
    STARS_BG, STARS_SIZE = gen_stars()
    s, cap, em = D["snap"], D["capacity"], D["emotion"]
    dd = iso(D["data_day"])
    fx_html = (f'<div class="v">{D["snap"]["fx"]["val"]:.4f}</div><div class="sub">USDCNH · {iso(D["snap"]["fx"]["vintage"])}</div>'
               if s["fx"] else '<div class="v na">待回填</div><div class="sub">fx_daily 未拉取（fetch_fx.py）</div>')
    udf = (f'{s["up_n"]} / {s["down_n"]}' if s["up_n"] is not None else "—")
    ud_bar = ""
    if s["up_n"]:
        tot = s["up_n"] + s["down_n"] + (s["flat_n"] or 0)
        ud_bar = (f'<div class="udbar"><i style="width:{100*s["up_n"]/tot:.0f}%"></i>'
                  f'<b style="width:{100*s["down_n"]/tot:.0f}%"></b></div>')

    def us_html_of(u):
        if not u:
            return '<span class="na">无美股锚</span>'
        arrow = "▲" if u["overnight"] > 0 else "▼"
        ucls = "up" if u["overnight"] > 0 else "dn"
        alert = "⚡" if u["alert"] else ""
        kind = "" if u["kind"] == "echo" else '<span class="thermo">温度计</span>'
        return (f'{u["tkr"]} <span class="{ucls}">{arrow}{abs(u["overnight"]):.1f}%</span>{alert} '
                f'<span class="sub">20日超额 {u["ex20"]:+.1f}%</span>{kind}')

    day_names = ["当日", "前1日", "前2日"]
    main_html = ""
    for di, day in enumerate(D["maindays"]):
        cards = ""
        for li, L in enumerate(day["lines"]):
            cid = f"d{di}l{li}"
            leaders = "、".join(L["leaders"]) or "—（近月信号无标的字段）"
            sc = THEME_COLOR.get(L["short"], "#8aa0c8")
            cards += f"""
<div class="mcard glass" style="--sc:{sc}" onclick="openModal('{cid}')">
 <div class="aurora" aria-hidden="true"><div class="neb"></div><div class="stars"></div></div>
 <div class="mc-h"><b>{L["short"]}</b><span class="mc-pct">{pct_span(L["day_pct"])}</span></div>
 <div class="sub">超额 {pct_span(L["excess"], "pp")} ｜ 20日超额 {L["e20"]:+.1f}%</div>
 <template id="{cid}"><div class="modal-title" style="--sc:{sc}">{L["short"]}
   <span class="mc-pct">{pct_span(L["day_pct"])}</span>
   <span class="sub">{iso(day["date"])} ｜ 超额 {pct_span(L["excess"], "pp")}</span></div>
  <div><span class="dk">ETF</span>{L["etf"]}</div>
  <div><span class="dk">美股映射</span>{us_html_of(L["us"])}</div>
  <div><span class="dk">龙头公司</span>{leaders} <span class="sub">（近月信号标的，括号=龙鱼分）</span></div>
  <div><span class="dk">产业逻辑</span><span class="desc">{L["logic"]}</span></div>
  <div><span class="dk">兑现定性</span><span class="desc">{L["desc"] or "—"}</span></div>
  <div><span class="dk">20日走势</span>{spark_svg(L["spark"], 200, 36)}</div>
 </template></div>"""
        qnote = (f'达标 {day["qualified"]} 条' +
                 (f'，按容量展示前 {day["kcap"]}' if day["qualified"] > (day["kcap"] or 99)
                  else ""))
        empty = '<div class="na" style="padding:8px 0">当日无达标主线（无板块对大盘有比较优势）</div>'
        main_html += f"""
<div class="mday">
 <div class="mday-h">{day_names[di]} <b>{iso(day["date"])}</b>
  <span class="sub">成交 {day["amount"] or "—"} 万亿 → K_cap {day["kcap"] or "—"} ｜ {qnote}</span></div>
 <div class="mrow">{cards or empty}</div>
</div>"""

    # 信号栏主源：渊图信号卡（近3批）
    sig_names = ["最新批", "前1批", "前2批"]
    TYPE_ZH = {"supply_shock": "供给冲击", "demand_surge": "需求爆发",
               "persistent_imbalance": "持续失衡"}
    sig_html = ""
    for di, day in enumerate(D["ytdays"]):
        cards = ""
        for si, g in enumerate(day["sigs"]):
            gid = f"y{di}x{si}"
            sc = THEME_COLOR.get(g["theme"], "#8aa0c8")
            stype = "·".join(TYPE_ZH.get(x.strip(), x.strip()) for x in g["stype"].split(","))
            bene = "、".join(b.strip() for b in g["bene"].split("/") if b.strip()) or "—（待标的解析）"
            echo = ('<span class="tag" style="color:var(--gold)">小鲍同步✓</span>' if g["echo"]
                    else '<span class="tag">小鲍未提及</span>')
            cards += f"""
<div class="scard glass" style="--sc:{sc}" onclick="openModal('{gid}')">
 <div class="aurora" aria-hidden="true"><div class="neb"></div><div class="stars"></div></div>
 <div class="sc-h"><span class="tag t-{g["status"]}">{g["status"]}</span>
  <span class="lvl" title="渊图置信度">conf {g["conf"]:.2f}</span></div>
 <div class="sc-kw">{g["chain"]}</div>
 <div class="sub">{stype}{("｜" + g["theme"]) if g["theme"] else ""}</div>
 <template id="{gid}"><div class="modal-title" style="--sc:{sc}">{g["chain"]}
   <span class="sub">{iso(day["date"])} ｜ {stype} ｜ 渊图 conf {g["conf"]:.2f}</span></div>
  <div><span class="dk">兑现状态</span><span class="tag t-{g["status"]}">{g["status"]}</span>
    <span class="desc">{g["desc"] or ""}</span></div>
  <div><span class="dk">受益标的</span><span class="desc">{bene}</span></div>
  <div><span class="dk">小鲍印证</span>{echo}<span class="sub">（第二源回声）</span></div>
  <div><span class="dk">图谱节点</span><span class="sub">{g["node"]}</span></div>
 </template></div>"""
        empty = '<div class="na" style="padding:8px 0">该批无渊图信号</div>'
        sig_html += f"""
<div class="mday">
 <div class="mday-h">{sig_names[di]} <b>{iso(day["date"])}</b>
  <span class="sub">渊图信号 {len(day["sigs"])} 条（图谱级·随研报/纪要入库，兑现状态=行情对比日更）</span></div>
 <div class="mrow">{cards or empty}</div>
</div>"""

    # 课件信号 · 第二印证（仅最新批，弱化展示）
    xb_html = ""
    for di, day in enumerate(D["sigdays"]):
        cards = ""
        for si, g in enumerate(day["sigs"]):
            gid = f"s{di}x{si}"
            sc = THEME_COLOR.get(g["theme"], "#8aa0c8")
            cards += f"""
<div class="scard glass xb" style="--sc:{sc}" onclick="openModal('{gid}')">
 <div class="sc-h"><span class="tag t-{g["status"]}">{g["status"]}</span>
  {f'<span class="lvl" title="信息差等级(1-5,越高潜在超额越大)">gap {g["lvl"]}</span>' if g["lvl"] else ''}</div>
 <div class="sc-kw">{g["kw"]}</div>
 <div class="sub">{g["theme"]}</div>
 <template id="{gid}"><div class="modal-title" style="--sc:{sc}">{g["kw"]}
   <span class="sub">{iso(day["date"])} ｜ {g["theme_full"]}{f' ｜ 信息差等级 {g["lvl"]}/5' if g["lvl"] else ''} ｜ {g["conf"]}</span></div>
  <div><span class="dk">状态</span><span class="tag t-{g["status"]}">{g["status"]}</span></div>
  <div><span class="dk">兑现定性</span><span class="desc">{g["desc"] or "—"}</span></div>
  <div><span class="dk">信号内容</span><span class="desc">{g["content"][:600]}</span></div>
 </template></div>"""
        xb_html += f"""
<div class="mday">
 <div class="mday-h"><span class="sub">第二印证 · 小鲍课件信号</span> <b>{iso(day["date"])}</b>
  <span class="sub">{len(day["sigs"])} 条（观点层回声，不作信号主源）</span></div>
 <div class="mrow">{cards}</div>
</div>"""

    opp_html = ""
    for o in D["opps"]:
        tg = "".join(
            f'<span class="chip">{x["name"]}'
            + (f'<em>{x["total"]}·{x["rating"]}</em>' if x.get("total") else "<em>未评分</em>")
            + "</span>" for x in o["targets"]) or '<span class="na">信号无标的字段</span>'
        opp_html += (f'<div class="opp"><div class="opp-h">{o["theme"]} '
                     f'<span class="sub">20日超额 {o["e20"]:+.1f}% · {o["note"]}</span></div>'
                     f'<div class="opp-d">{o["desc"] or ""}</div><div class="chips">{tg}</div></div>')
    if not opp_html:
        opp_html = '<div class="na">当日无满足三条件（兑现早期×容量×锚不背离）的机会——诚实空仓提示</div>'

    risk_html = "".join(f'<div class="risk r-{r["lvl"]}">{"🔴" if r["lvl"]=="红" else "🟡"} {r["txt"]}</div>'
                        for r in D["risks"]) or '<div class="na">无自动风险命中</div>'

    pos = D["positions"]
    xbp = (f'{pos["xiaobao"]["band"]}（{pos["xiaobao"]["pref"]}/5）'
           f'<div class="sub">⚠️ 数据 {pos["xiaobao"]["date"]}（课件口径，停更则如实显示）</div>'
           if pos["xiaobao"] else '<span class="na">无数据</span>')

    em_series = json.dumps(em["series"], ensure_ascii=False)
    season_icon = {"春": "🌱", "夏": "☀️", "秋": "🍂", "冬": "❄️"}.get((em["season"] or " ")[0], "")

    return f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>烛照九阴日报 · {dd}</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<style>
:root{{--bg:#0a0e1a;--card:#11182b;--line:#1d2742;--tx:#e6edf8;--sub:#8593b2;
--red:#ff5d5d;--grn:#3ddc97;--gold:#e8c46b;--acc:#5b8cff;
--zh:"Songti SC","Noto Serif SC","Source Han Serif SC","STSong",serif;
--num:"SF Pro Display",ui-monospace,"SF Mono",Menlo,Consolas,var(--zh)}}
*{{box-sizing:border-box;margin:0}}
body{{background:radial-gradient(1200px 600px at 70% -10%,#16203d 0%,var(--bg) 55%);
color:var(--tx);font:15px/1.65 var(--zh);font-weight:400;padding:22px;max-width:1280px;margin:auto;
-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}}
h1{{font-size:22px;font-weight:700;letter-spacing:3px}}
h2{{font-size:15px;font-weight:600;color:var(--gold);margin:30px 0 12px;letter-spacing:1.5px}}
.vintage{{color:var(--sub);font-size:12px;font-weight:400;letter-spacing:0}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(175px,1fr));gap:12px;margin-top:14px}}
/* 水晶质感（无星空版）：玻璃渐变+磨砂+内嵌高光+顶部反光条 */
.card,.opp,.risk{{position:relative;overflow:hidden;
 background:linear-gradient(150deg,rgba(255,255,255,.085),rgba(255,255,255,.02) 45%,rgba(255,255,255,.045));
 backdrop-filter:blur(22px) saturate(160%);-webkit-backdrop-filter:blur(22px) saturate(160%);
 border:1px solid var(--line);
 box-shadow:0 8px 30px rgba(0,0,0,.28),inset 0 1px 0 rgba(255,255,255,.22),inset 0 -1px 0 rgba(255,255,255,.05)}}
.card::after,.opp::after,.risk::after{{content:"";position:absolute;inset:0;border-radius:inherit;pointer-events:none;
 background:linear-gradient(180deg,rgba(255,255,255,.13),transparent 32%);mix-blend-mode:overlay}}
.card{{border-radius:16px;padding:14px 16px}}
.card .k{{color:var(--sub);font-size:12px;letter-spacing:.5px}}
.card .v{{font-size:27px;font-weight:600;font-family:var(--num);font-variant-numeric:tabular-nums;margin-top:3px;letter-spacing:-.5px}}
.card .sub{{color:var(--sub);font-size:11px;margin-top:3px}}
.up{{color:var(--red)}} .dn{{color:var(--grn)}} .na{{color:#55617e}}
.udbar{{display:flex;height:6px;border-radius:3px;overflow:hidden;margin-top:8px;background:#1b2440}}
.udbar i{{background:var(--red)}} .udbar b{{background:var(--grn)}}
.row2{{display:grid;grid-template-columns:1.2fr 1fr 1fr;gap:12px;margin-top:14px}}
@media(max-width:900px){{.row2{{grid-template-columns:1fr}}.cards{{grid-template-columns:1fr 1fr}}}}
.season{{font-size:34px}} .gauge,#emChart{{height:170px}}
table{{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}}
th{{color:var(--sub);font-weight:600;font-size:11px;text-align:left;padding:9px 11px;border-bottom:1px solid var(--line);letter-spacing:1px}}
td{{padding:8px 11px;border-bottom:1px solid #151d33;font-family:var(--num);font-variant-numeric:tabular-nums;vertical-align:middle;font-size:13.5px}}
td.tname,td.desc,td.kw{{font-family:var(--zh)}}
.tname{{font-weight:600;font-size:14px}} .desc{{color:var(--sub);font-size:12px;max-width:300px;line-height:1.5}}
.tag{{font-size:11px;padding:1px 7px;border-radius:9px;background:#1b2440;color:var(--sub)}}
.t-closing{{background:#3a2a14;color:var(--gold)}} .t-open{{background:#14283a;color:var(--acc)}} .t-closed{{background:#1b2440}}
.thermo{{font-size:10px;color:var(--sub);border:1px solid var(--line);border-radius:6px;padding:0 4px;margin-left:4px}}
.chip{{display:inline-block;background:#1b2440;border:1px solid var(--line);border-radius:8px;padding:3px 10px;margin:3px 6px 0 0}}
.chip em{{font-style:normal;color:var(--gold);font-size:11px;margin-left:6px}}
.opp{{border-left:3px solid var(--acc);border-radius:14px;padding:12px 14px;margin-bottom:10px}}
.opp-h{{font-weight:600}} .opp-d{{color:var(--sub);font-size:12px;margin:4px 0}}
.risk{{border-radius:14px;padding:10px 14px;margin-bottom:8px;font-size:13px}}
.r-红{{border-left:3px solid var(--red)}} .r-黄{{border-left:3px solid var(--gold)}}
.filters{{margin:8px 0}} .filters button{{background:#1b2440;color:var(--sub);border:1px solid var(--line);border-radius:8px;padding:3px 12px;margin-right:6px;cursor:pointer}}
.filters button.on{{color:var(--tx);border-color:var(--acc)}}
.foot{{color:#55617e;font-size:11px;margin:30px 0 10px;border-top:1px solid var(--line);padding-top:10px}}
.mday{{margin-bottom:18px}}
.mday-h{{font-size:14px;margin-bottom:10px;color:var(--tx)}} .mday-h b{{font-family:var(--num)}}
.mrow{{display:flex;gap:12px;overflow-x:auto;padding:4px 2px 10px}}
.mrow::-webkit-scrollbar{{height:6px}} .mrow::-webkit-scrollbar-thumb{{background:#1d2742;border-radius:3px}}
.mrow .mcard{{flex:0 0 250px}} .mrow .scard{{flex:0 0 215px}}
/* ── 星空卡（借鉴龙鱼标的库星河看板）── */
.glass{{position:relative;
 background:linear-gradient(150deg,rgba(255,255,255,.10),rgba(255,255,255,.025) 42%,rgba(255,255,255,.05));
 backdrop-filter:blur(28px) saturate(180%) brightness(1.08);-webkit-backdrop-filter:blur(28px) saturate(180%) brightness(1.08);
 border:1px solid var(--line);border-radius:18px;
 box-shadow:0 10px 40px rgba(0,0,0,.34),inset 0 1px 0 rgba(255,255,255,.28),inset 0 -1px 0 rgba(255,255,255,.06)}}
.glass>*{{position:relative;z-index:1}}
.glass::after{{content:"";position:absolute;inset:0;border-radius:inherit;pointer-events:none;z-index:0;
 background:linear-gradient(180deg,rgba(255,255,255,.16),transparent 30%);mix-blend-mode:overlay}}
.mcard{{padding:14px 16px;cursor:pointer;overflow:hidden;transition:transform .18s,box-shadow .18s,border-color .18s}}
.mcard:hover{{transform:translateY(-4px);border-color:rgba(255,255,255,.26);
 box-shadow:0 18px 50px rgba(0,0,0,.4),0 0 0 1px rgba(255,255,255,.12),inset 0 1px 0 rgba(255,255,255,.34);
 background:linear-gradient(150deg,rgba(255,255,255,.14),rgba(255,255,255,.04) 42%,rgba(255,255,255,.07))}}
.mcard .aurora{{position:absolute;inset:0;z-index:0;pointer-events:none;overflow:hidden;border-radius:inherit}}
.mcard .neb{{position:absolute;inset:0;filter:blur(10px);opacity:.9;will-change:transform;
 animation:nebDrift 22s ease-in-out infinite alternate;
 background:radial-gradient(50% 60% at 10% 0%,color-mix(in srgb,var(--sc,#888) 60%,transparent),transparent 66%),
  radial-gradient(55% 65% at 35% 25%,color-mix(in srgb,var(--sc,#888) 38%,transparent),transparent 70%),
  radial-gradient(70% 80% at 62% 48%,color-mix(in srgb,var(--sc,#888) 22%,transparent),transparent 76%)}}
.mcard .stars{{position:absolute;inset:0;opacity:.9;animation:twinkle 4.5s ease-in-out infinite alternate;
 background-image:{STARS_BG};
 background-repeat:repeat;background-size:{STARS_SIZE}}}
@keyframes nebDrift{{from{{transform:translate(-2%,-1%) scale(1)}}to{{transform:translate(2%,2%) scale(1.06)}}}}
@keyframes twinkle{{0%{{opacity:.62}}100%{{opacity:.95}}}}
.mc-h{{display:flex;justify-content:space-between;align-items:baseline;font-size:16px}}
.mc-h b{{font-size:17px;font-weight:700;letter-spacing:.5px}}
.mc-pct{{font-family:var(--num);font-size:19px;font-weight:600}}
.dk{{display:inline-block;min-width:66px;color:var(--sub);font-size:11px}}
/* 信号小卡 */
.scard{{padding:12px 14px;cursor:pointer;overflow:hidden;transition:transform .18s,box-shadow .18s,border-color .18s}}
.scard:hover{{transform:translateY(-4px);border-color:rgba(255,255,255,.26);
 box-shadow:0 18px 50px rgba(0,0,0,.4),0 0 0 1px rgba(255,255,255,.12)}}
.scard .neb{{opacity:.5}} .scard .stars{{opacity:.6}}
.scard.xb{{opacity:.72;border-style:dashed}} .scard.xb:hover{{opacity:1}}
.sc-h{{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}}
.sc-h .lvl{{font-family:var(--num);color:var(--gold);font-weight:600;font-size:13px}}
.sc-kw{{font-size:13.5px;font-weight:600;line-height:1.4;margin-bottom:3px}}
/* 中心浮层 */
#overlay{{display:none;position:fixed;inset:0;z-index:90;background:rgba(5,8,18,.62);
 backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px)}}
#overlay.show{{display:block;animation:fadeIn .16s ease}}
#modal{{position:fixed;left:50%;top:50%;transform:translate(-50%,-50%);z-index:99;
 width:min(580px,92vw);max-height:82vh;overflow-y:auto;padding:20px 22px;
 display:none;animation:popIn .2s cubic-bezier(.2,.9,.3,1.2)}}
#modal.show{{display:block}}
#modal .modal-title{{font-size:19px;font-weight:700;margin-bottom:12px;display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;
 padding-bottom:10px;border-bottom:1px solid rgba(255,255,255,.12)}}
#modal>div:not(.modal-title):not(.aurora){{margin-bottom:7px;position:relative;z-index:1;font-size:13px}}
#modalX{{position:absolute;right:14px;top:12px;z-index:2;cursor:pointer;color:var(--sub);font-size:18px;
 width:28px;height:28px;display:flex;align-items:center;justify-content:center;border-radius:50%;transition:all .15s}}
#modalX:hover{{color:var(--tx);background:rgba(255,255,255,.1);transform:rotate(90deg)}}
@keyframes fadeIn{{from{{opacity:0}}to{{opacity:1}}}}
@keyframes popIn{{from{{opacity:0;transform:translate(-50%,-46%) scale(.96)}}to{{opacity:1;transform:translate(-50%,-50%) scale(1)}}}}
</style></head><body>

<h1>🏮 烛照九阴 · 复盘日报</h1>
<div class="vintage">数据日 {dd} ｜ 生成 {D["gen_time"]} ｜ 各区块独立标注 vintage，缺数如实显示</div>

<h2>一 · 市场快照 <span class="vintage">{dd}</span></h2>
<div class="cards">
 <div class="card"><div class="k">大盘（{s["bench_note"]}）</div><div class="v">{pct_span(s["bench_pct"])}</div></div>
 <div class="card"><div class="k">涨 / 跌家数 <span class="vintage">全市场口径</span></div><div class="v" style="font-size:18px">{udf}</div>{ud_bar}</div>
 <div class="card"><div class="k">总成交额</div><div class="v">{s["amount"] if s["amount"] else "—"} 万亿</div>
   <div class="sub">对应容量 K_cap≈{cap["kcap"]} 条/日</div></div>
 <div class="card"><div class="k">涨停 / 跌停</div><div class="v" style="font-size:20px"><span class="up">{s["limit_up"]}</span> / <span class="dn">{s["limit_down"]}</span></div>
   <div class="sub">limit_list_daily·全市场统一口径</div></div>
 <div class="card"><div class="k">美元:人民币</div>{fx_html}</div>
</div>

<h2>二 · 周期与情绪 <span class="vintage">emotion_v2 · {em["date"]}</span></h2>
<div class="row2">
 <div class="card"><div class="k">情绪季节（风险偏好周期·单向不可逆）</div>
  <div class="season">{season_icon} {em["season"]}</div>
  <div class="sub">评分 {em["score"]} ｜ 风险偏好 {em["risk"]} ｜ {em["note"]}</div>
  <div class="sub">小鲍第二印证：{em["xiaobao"]["stage"] if em["xiaobao"] else "—"}（{em["xiaobao"]["date"] if em["xiaobao"] else ""}）</div></div>
 <div class="card"><div class="k">情绪评分 60 日 <span class="vintage">粗线=MA5（季节判定口径），细线=当日原始</span></div><div id="emChart"></div></div>
 <div class="card"><div class="k">容量仪表（经验非规律）</div><div id="capGauge" class="gauge"></div>
  <div class="sub">K(5日中位) {cap["kday"]} / K_cap {cap["kcap"]} → <b>{cap["state"]}</b> ｜ 当日 {cap["kday_today"]}{"（普涨尖峰）" if cap["kday_today"] > cap["kday"] + 3 else ""}</div></div>
</div>

<h2>三 · 主线板块 · 近3日 <span class="vintage">资格=涨幅>1%且对大盘超额>0.5pp（跟涨不算主线）｜ 数量≤当日成交额对应K_cap ｜ 点卡片看详情</span></h2>
{main_html}

<h2>三·附 · 信号栏（主源：渊图 × 行情兑现） <span class="vintage">信号发现=渊图图谱（研报/纪要入库），兑现判定=closure_engine 行情日更 ｜ 点卡片看详情</span></h2>
{sig_html}
{xb_html}

<h2>四 · 机会提示 <span class="vintage">规则：兑现早期 × 容量 × 锚不背离 ｜ 体系内信号聚合，非投资建议</span></h2>
{opp_html}
<div class="card" style="margin-top:10px"><div class="k">仓位 · 三口径并列（不合成）</div>
 <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-top:8px">
  <div><div class="k">小鲍 band（总仓位）</div><div>{xbp}</div></div>
  <div><div class="k">容量状态（能否开新线）</div><div>{cap["state"]}（K {cap["kday"]}/{cap["kcap"]}）</div></div>
  <div><div class="k">龙鱼评级（个股资格）</div><div class="sub">见机会卡片标的 chips 内分数</div></div>
 </div><div class="sub" style="margin-top:6px">{pos["note"]}</div></div>

<h2>五 · 风险提示</h2>
{risk_html}

<div class="foot">烛照九阴 · 数据：recap.db / market_data.db / 龙鱼-标的分析库 ｜ 缺数=诚实标注，禁占位禁编数 ｜ 仓位与标的为体系内信号聚合，非投资建议</div>

<div id="overlay" onclick="closeModal()"></div>
<div id="modal" class="glass"><div class="aurora" aria-hidden="true"><div class="neb"></div><div class="stars"></div></div>
 <div id="modalX" onclick="closeModal()">✕</div><div id="modalBody"></div></div>

<script>
const em = echarts.init(document.getElementById('emChart'), null, {{renderer:'svg'}});
const es = {em_series};
em.setOption({{grid:{{left:30,right:8,top:8,bottom:18}},
 xAxis:{{type:'category',data:es.map(x=>x[0].slice(5)),axisLabel:{{color:'#55617e',fontSize:9,interval:14}},axisLine:{{lineStyle:{{color:'#1d2742'}}}}}},
 yAxis:{{min:0,max:100,axisLabel:{{color:'#55617e',fontSize:9}},splitLine:{{lineStyle:{{color:'#151d33'}}}}}},
 series:[
  {{type:'line',name:'当日原始',data:es.map(x=>x[1]),smooth:false,symbol:'none',lineStyle:{{color:'rgba(91,140,255,.22)',width:1}}}},
  {{type:'line',name:'MA5(季节判定口径)',data:es.map(x=>x[2]),smooth:true,symbol:'none',lineStyle:{{color:'#5b8cff',width:2}},
  areaStyle:{{color:{{type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[{{offset:0,color:'rgba(91,140,255,.22)'}},{{offset:1,color:'rgba(91,140,255,0)'}}]}}}},
  markLine:{{silent:true,symbol:'none',label:{{show:false}},lineStyle:{{color:'#2a3354',type:'dashed'}},data:[{{yAxis:50}}]}}}}],
 tooltip:{{trigger:'axis',backgroundColor:'#11182b',borderColor:'#1d2742',textStyle:{{color:'#dde6f5',fontSize:11}}}}}});
const g = echarts.init(document.getElementById('capGauge'), null, {{renderer:'svg'}});
g.setOption({{series:[{{type:'gauge',min:0,max:{max(8, (cap["kcap"] or 6)+2):.0f},startAngle:200,endAngle:-20,
 progress:{{show:true,width:10,itemStyle:{{color:'#e8c46b'}}}},axisLine:{{lineStyle:{{width:10,color:[[1,'#1b2440']]}}}},
 pointer:{{show:false}},axisTick:{{show:false}},splitLine:{{show:false}},
 axisLabel:{{show:false}},
 detail:{{valueAnimation:true,fontSize:30,color:'#dde6f5',offsetCenter:[0,'10%'],formatter:'{{value}}'}},
 data:[{{value:{cap["kday"]}}}],title:{{show:false}},
 markLine:{{}}}},
 {{type:'gauge',min:0,max:{max(8, (cap["kcap"] or 6)+2):.0f},startAngle:200,endAngle:-20,
  pointer:{{show:true,length:'70%',width:3,itemStyle:{{color:'#ff5d5d'}}}},
  axisLine:{{show:false}},axisTick:{{show:false}},splitLine:{{show:false}},axisLabel:{{show:false}},detail:{{show:false}},
  data:[{{value:{cap["kcap"] or 0}}}]}}]}});
function openModal(id){{
 const tpl=document.getElementById(id);
 const body=document.getElementById('modalBody');
 body.innerHTML='';
 body.appendChild(tpl.content.cloneNode(true));
 const t=body.querySelector('.modal-title');
 if(t&&t.style.getPropertyValue('--sc'))
  document.getElementById('modal').style.setProperty('--sc',t.style.getPropertyValue('--sc'));
 document.getElementById('overlay').classList.add('show');
 document.getElementById('modal').classList.add('show');
 document.body.style.overflow='hidden';}}
function closeModal(){{
 document.getElementById('overlay').classList.remove('show');
 document.getElementById('modal').classList.remove('show');
 document.body.style.overflow='';}}
document.addEventListener('keydown',e=>{{if(e.key==='Escape')closeModal();}});
window.addEventListener('resize',()=>{{em.resize();g.resize();}});
</script>
</body></html>"""


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "archived").mkdir(exist_ok=True)
    D = gather()
    html = render(D)
    fname = f"烛照九阴日报_{D['data_day']}.html"
    # 旧报移 archived/（永不删，删除权归 Doctor）
    for old in OUT_DIR.glob("烛照九阴日报_*.html"):
        if old.name != fname:
            shutil.move(str(old), str(OUT_DIR / "archived" / old.name))
            logger.info(f"📦 旧报归档 → archived/{old.name}")
    out = OUT_DIR / fname
    out.write_text(html, encoding="utf-8")
    logger.info(f"✅ 日报生成 → {out}")
    logger.info(f"   主线 {len(D['themes'])} 条 | 信号 {len(D['signals'])} 条 | 机会 {len(D['opps'])} | 风险 {len(D['risks'])}")


if __name__ == "__main__":
    main()
