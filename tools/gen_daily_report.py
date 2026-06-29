#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""烛照九阴 · 可视化日报生成器 v2「暖色日报」（真实数据）
（CC 2026-06-12；范式=Codex 原型 vv-visual-v1，对接文件=cc-handoff-visual-v1.md）

设计定义：以中式纸面和季节意象软化金融数据的冷硬，以严格的信息层级保证判断效率。
铁律：缺数诚实标注（停更于X日/待回填），禁占位符、禁编数据、禁旧值冒充；每区块 vintage 角标。
口径铁律（G-07）：渊图信号按产业信号时间（yuantu_buy_signals.date）分组展示，
  禁用「最新批/前1批/前2批/入库批次」及 created_at/tagged_at。
模板铁律：.report-hero 的 --hero-lock-* / --hero-art-* / --season-* 为锁定变量，
  调整画框只改变量值，不散改布局属性（Doctor 已确认构图）。

输出：AI4ME/烛照九阴-outputs/烛照九阴日报_{数据日}.html（根目录最新；旧报自动移 archived/，永不删）

用法：
    python3 tools/gen_daily_report.py                       # 正式输出（写 AI4ME + 归档旧报）
    python3 tools/gen_daily_report.py --output /tmp/x       # 测试输出（不碰正式目录）
    python3 tools/gen_daily_report.py --no-archive          # 不移动旧报
    python3 tools/gen_daily_report.py --date 20260609       # 指定数据日（≤该日数据）
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import argparse, base64, sqlite3, json, re, shutil, datetime, glob
from pathlib import Path
from collections import defaultdict
import statistics as st
import config
import fundamentals_lookup as fl
from lib.logger import get_logger
logger = get_logger(__name__)

_sys.path.insert(0, str(config.PROJECT_ROOT / "scripts"))
from fetch_theme_etf import THEME_ETF, BENCHMARK
from fetch_us_anchor import THEME_US, BENCHMARK_US

OUT_DIR = config.PROJECT_ROOT.parents[3] / "AI4ME" / "烛照九阴-outputs"
RECORDS = config.PROJECT_ROOT.parents[3] / "Database" / "龙鱼-标的分析库" / "records"
ASSETS = config.PROJECT_ROOT / "assets"
FONT_SEASONS = ASSETS / "zikutang-shike-seasons.ttf"          # 字酷堂石刻体子集（春夏秋冬）
# ART_LAIQIN = ASSETS / "guoshu-laiqin-03-guohua-inkwash-edgefit-h1000.webp"  # 旧《果熟来禽图》水墨版（2026-06-29 弃用，保留可回退）
ART_LAIQIN = ASSETS / "guoshu-laiqin-04-birdberry-h1000.png"  # 鸟果新标题图（2026-06-29 Doctor 换为 PNG 版，旧 .webp 已替换）
ECHARTS_JS = ASSETS / "echarts.min.js"                        # ECharts 本地副本（Cowork 沙箱须内联，详见 _echarts_inline）
ARTIFACT_PATH = config.PROJECT_ROOT.parents[3] / "Claude" / "Artifacts" / "zhuzhao-jiuyin-daily" / "index.html"  # Cowork artifact 部署目标（重渲即部署）


def iso(d): return f"{d[:4]}-{d[4:6]}-{d[6:]}" if d and "-" not in d else d


import re as _re
# 受益公司国别上色（2026-06-30 Doctor）：外企=樱粉，台湾=青绿，中国/香港=蓝。
# curated 名单；保守——拿不准默认蓝（港/陆未解析均蓝）。
# 台企名单来源：渊图 .TW/.TWO 自动命中 8 + 渊图 desc 坐实 5（台积电/联发科/乾坤/南亚电路板/金居），非凭记忆。
TAIWAN_BENE = {
    "MPI Corporation", "WinWay Technology", "创意电子 GUC", "台光电材", "广达电脑",
    "景硕科技", "欣兴电子", "纬湾科技", "台积电", "联发科", "乾坤科技",
    "南亚电路板", "金居开发"}
TAIWAN_COLOR = "#1f8a7a"   # 深青绿
FOREIGN_BENE = {
    "AXT", "Absolics", "Arm Holdings", "Ciena公司", "Coherent", "Disco", "Granopt", "JX先进金属",
    "LG Innotek", "Lasertec", "Lumentum", "Marvell Technology", "Meta Platforms", "SK海力士", "Wafertech",
    "三井金属", "三星电子", "三星电机", "东京电子", "丸和电子", "住友电工", "斗山", "日东纺", "村田制作所",
    "康宁公司", "味之素", "太阳诱电", "奥特斯", "揖斐电", "日本平野", "是德科技", "美光科技", "美光",
    "英伟达", "英特尔", "荏原制作所", "谷歌", "超微半导体", "博通"}
FOREIGN_COLOR = "#d76a92"   # 樱粉


def _is_foreign(name):
    return _re.sub(r"（.*?）|\(.*?\)", "", name or "").strip() in FOREIGN_BENE


def _is_taiwan(name):
    return _re.sub(r"（.*?）|\(.*?\)", "", name or "").strip() in TAIWAN_BENE


def bene_html(raw, fallback):
    """受益标的渲染（图谱口径受益度·轻档 2026-06-25；六维分对齐 2026-06-25·走大宗库口径）：每公司带〔直接/间接·强中弱传导〕+ 白泽口径（命中显纯度/弹性 + **周更六维分**，由 fl 从大宗库 business_breakdown.db 按 **ts_code** 与弹性一起取）；未命中回退渊图图谱 fin。无 detail 回退名字串。"""
    import json as _j
    try:
        det = _j.loads(raw) if raw else []
    except Exception:
        det = []
    if not det:
        return fallback or "—（待标的解析）"
    parts = []
    for b in det:
        tier, tw = b.get("tier", ""), b.get("tier_w", "")
        # 命中共享基本面库（白泽 owner·慢变P0年报）→ 显白泽口径；未命中 → 回退渊图图谱 fin 标注
        bz = fl.fmt(b.get("ts", "")) if b.get("ts") else ""
        if bz:
            fintxt = "　" + bz
        else:
            fin = b.get("fin") or {}
            fintxt = ("　图谱:" + "·".join(f"{k}{v}" for k, v in fin.items())) if fin else ""
        _nm = b.get("name", "")
        _col = (TAIWAN_COLOR if _is_taiwan(_nm)
                else FOREIGN_COLOR if _is_foreign(_nm)
                else "var(--acc,#1B365D)")
        parts.append(f'<span style="color:{_col};font-weight:600">{_nm}</span> '
                     f'<span style="font-size:.82em;opacity:.7">〔{tier}·{tw}传导〕</span>'
                     f'<span style="font-size:.82em;color:var(--gold,#caa45a)">{fintxt}</span>')
    # 悬挂缩进：整串包 inline-block，换行(<br>)的第2+只名字对齐到第1只下方(2026-06-25)
    return '<span style="display:inline-block;vertical-align:top">' + "<br>".join(parts) + "</span>"


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


# ── 状态中文化（文案去内部化：open/closing/no_anchor 不外露）──
STATUS_ZH = {"open": "观察中", "closing": "兑现中", "closed": "已兑现",
             "dormant": "暗态", "no_anchor": "无锚点", "failed": "已证伪",
             "no_data": "待跟踪"}


def fulfill_of(status, desc, excess_cum=None):
    """兑现度卡结构化字段（不硬造百分比：只在有口径时展示数值）。
    返回 dict(v=主值, d=副文案, w=条宽%, sent=弹窗一句话)"""
    desc = desc or ""
    m_days = re.search(r"(\d+)日", desc)
    days = m_days.group(1) if m_days else None
    m_cum = re.search(r"累计([+-]?[\d.]+)%", desc)
    cum = m_cum.group(1) if m_cum else (
        f"{excess_cum * 100:+.1f}" if isinstance(excess_cum, (int, float)) else None)
    m_dd = re.search(r"回撤([+-]?[\d.]+)%", desc)
    if status == "open":
        d = f"潜伏期 · 出现{days}日" if days else "潜伏期 · 未启动"
        return dict(v="未启动", d=d, w=12, sent="价格兑现尚未展开，继续观察锚点是否出现。")
    if status == "no_anchor":
        return dict(v="未跟踪", d="无锚点 · 暂不计", w=6,
                    sent="缺少可跟踪锚点，暂不纳入价格兑现判断。")
    if status == "closing":
        d = (f"{days}日 · 累计{cum}%" if days and cum else "兑现中 · 口径待补")
        sent = (f"跟踪 {days} 日，累计 {cum}%，仍需观察持续性。" if days and cum
                else "已进入价格兑现，数值口径待补。")
        return dict(v="兑现中", d=d, w=52, sent=sent)
    if status == "closed":
        m_dur = re.search(r"历时(\d+)日", desc)
        days = m_dur.group(1) if m_dur else days
        d = (f"{days}日 · 累计{cum}%" if days and cum else "已兑现")
        sent = (f"跟踪 {days} 日，累计 {cum}%，兑现完毕。" if days and cum else "价格兑现已完成。")
        return dict(v="已兑现", d=d, w=88, sent=sent)
    if status == "dormant":
        # 案2：暗态默认不渲染主栏/台账，此分支仅作兜底（如别处误引用）
        return dict(v="暗态", d="已兑现 · 候二段", w=70,
                    sent="本波兑现完毕、转暗态候二段；价格再起达门槛将重新点亮。")
    if status == "failed":
        dd = m_dd.group(1) if m_dd else None
        d = (f"{days}日 · 回撤{dd}%" if days and dd else "已证伪")
        return dict(v="已证伪", d=d, w=24, sent="价格走势未印证信号，逻辑证伪。")
    return dict(v="待跟踪", d="暂无口径", w=8, sent="兑现口径待补。")


def gather(date_cap=None):
    md = sqlite3.connect(f"file:{config.MARKET_DB}?mode=ro", uri=True)
    rc = sqlite3.connect(f"file:{config.RECAP_DB}?mode=ro", uri=True)
    D = {}

    # ── 行情底座：theme ETF 日收益（pct_chg，复权口径） ──
    px = defaultdict(dict)
    for d, c, p in md.execute("SELECT trade_date, etf_code, pct_chg FROM theme_etf_daily "
                              "WHERE pct_chg IS NOT NULL ORDER BY trade_date"):
        px[c][d] = p / 100
    dates = sorted(px[BENCHMARK])
    if date_cap:
        dates = [d for d in dates if d <= date_cap]
        if not dates:
            raise SystemExit(f"--date {date_cap} 早于最早行情日，无法生成")
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

    # ── 市场快照（画框下方四联条） ──
    snap = {}
    snap["bench_pct"] = round(px[BENCHMARK][data_day] * 100, 2)
    snap["bench_note"] = "沪深300代理"
    ud = md.execute("SELECT SUM(pct_chg>0), SUM(pct_chg<0), SUM(pct_chg=0) FROM stock_daily "
                    "WHERE trade_date=?", (data_day,)).fetchone()
    snap["up_n"], snap["down_n"], snap["flat_n"] = (ud if ud and ud[0] is not None
                                                    else (None, None, None))
    amt_row = md.execute("SELECT trade_date, total_trillion FROM market_amount_daily "
                         "WHERE trade_date<=? ORDER BY trade_date DESC LIMIT 1",
                         (data_day,)).fetchone()
    snap["amount"] = amt_row[1] if amt_row and amt_row[0] == data_day else None
    snap["amount_vintage"] = amt_row[0] if amt_row else None
    lim = md.execute("SELECT SUM(limit_type='U'), SUM(limit_type='D') FROM limit_list_daily "
                     "WHERE trade_date=?", (data_day,)).fetchone()
    snap["limit_up"], snap["limit_down"] = lim if lim else (None, None)
    D["snap"] = snap

    # ── 周期与情绪（emotion_cycle v2） ──
    em_rows = rc.execute("SELECT date, emotion_score, emotion_season, risk_appetite, cycle_no, "
                         "limit_up, limit_down, jinji, premium, height FROM emotion_cycle "
                         "WHERE emotion_score IS NOT NULL AND date<=? "
                         "ORDER BY date DESC LIMIT 60", (iso(data_day),)).fetchall()[::-1]
    em_last = em_rows[-1]
    sc_vals = [r[1] for r in em_rows]
    ma5 = [round(st.fmean(sc_vals[max(0, i - 4):i + 1]), 1) for i in range(len(sc_vals))]
    last50 = sc_vals[-50:]
    pct_rank = round(100 * sum(1 for v in last50 if v <= sc_vals[-1]) / len(last50))
    trend = ("上行" if len(ma5) > 1 and ma5[-1] > ma5[-2]
             else ("下行" if len(ma5) > 1 and ma5[-1] < ma5[-2] else "走平"))
    D["emotion"] = {
        "series": [[r[0], r[1], ma5[i]] for i, r in enumerate(em_rows)],
        "date": em_last[0], "score": em_last[1], "season": em_last[2],
        "risk": em_last[3], "cycle_no": em_last[4],
        "limit_up": em_last[5], "limit_down": em_last[6],
        "jinji": em_last[7], "premium": em_last[8], "height": em_last[9],
        "ma5": ma5[-1], "pct_rank": pct_rank, "trend": trend,
    }

    # ── 容量 ──
    cap_val = kcap(snap["amount"]) if snap["amount"] else None

    def kday_at(d):
        # 容量宽度口径：主线篮子日内对沪深300超额 > +0.5pp（与"主线资格"同阈值，
        # 普涨跟涨不计；2026-06-23 Doctor 裁定由裸涨幅>1% 切超额口径）
        b = px[BENCHMARK].get(d)
        if b is None:
            return 0
        k = 0
        for t in THEME_ETF:
            vals = [px[c][d] for c in THEME_ETF[t] if d in px[c]]
            if vals and (sum(vals) / len(vals) - b) > 0.005:
                k += 1
        return k
    kday_today = kday_at(data_day)
    kday = int(st.median([kday_at(d) for d in dates[-5:]]))
    state = None
    if cap_val:
        if kday >= cap_val:
            state = "满载"
        else:
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

    # 外盘指数（隔夜·期货预期）——每个 code 取自身最新交易日一行（缺则不返回，render 标缺）
    intl = []
    try:
        for code, sym, name, kind, td, close, pct, note in md.execute(
                "SELECT code, symbol, name, kind, trade_date, close, pct_chg, note "
                "FROM intl_index_daily i WHERE trade_date=("
                "  SELECT MAX(trade_date) FROM intl_index_daily j WHERE j.code=i.code)"):
            intl.append({"code": code, "symbol": sym, "name": name, "kind": kind,
                         "date": td, "close": close, "pct": pct, "note": note})
    except sqlite3.OperationalError:
        pass
    D["intl"] = {x["code"]: x for x in intl}

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

    # ── 主线板块 · 近3日（资格=对大盘有比较优势；数量≤当日K_cap） ──
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

    # 信号明细（近14天）——机会/风险模块仍用
    cutoff = (datetime.date.fromisoformat(iso(data_day)) - datetime.timedelta(days=14)).isoformat()
    sigs = rc.execute(
        "SELECT date, etf_anchor, keyword, info_gap_level, gap_status, gap_desc, confidence "
        "FROM industry_signals WHERE date>=? AND etf_anchor!='' "
        "AND (info_gap_level>=3 OR gap_status IN ('open','closing')) "
        "ORDER BY date DESC, info_gap_level DESC, gap_raw DESC", (cutoff,)).fetchall()
    D["signals"] = [dict(date=r[0], theme=(r[1] or "").split("/")[0], kw=r[2],
                         lvl=r[3], status=r[4], desc=r[5], conf=r[6]) for r in sigs]

    # ── GAP 信号栏主源：渊图信号 × 行情兑现 ──
    # 口径铁律（G-07）：按产业信号时间分组（yuantu_buy_signals.date=信号自带时间，
    # 缺自带时间时上游已回填纪要/研报 data_vintage）；created_at 仅为入库痕迹，禁用。
    yt_dates = [r[0] for r in rc.execute(
        "SELECT DISTINCT date FROM yuantu_buy_signals WHERE length(date)=10 "
        "ORDER BY date DESC LIMIT 3")]
    ytdays = []
    for sd in yt_dates:
        rows = rc.execute(
            "SELECT industry_chain, signal_node, signal_type, yuantu_confidence, "
            "beneficiaries, xiaobao_echo, gap_status, gap_desc, etf_anchor, excess_cum, "
            "beneficiaries_detail "
            "FROM yuantu_buy_signals WHERE date=? ORDER BY yuantu_confidence DESC", (sd,)).fetchall()
        sigs_d = []
        for r in rows:
            status = r[6] or "no_data"
            if status == "dormant":
                continue   # 案2：暗态不渲染主栏，仅计入暗态计数（D["dormant_n"]）
            desc = (r[7] or "").replace("发现", "出现")   # 文案去内部化
            sigs_d.append(dict(
                chain=r[0] or r[1], node=r[1], stype=r[2] or "", conf=r[3],
                bene=r[4] or "", bene_detail=r[10] or "", echo=bool(r[5]), status=status,
                desc=desc, theme=(r[8] or "").split("/")[0],
                fulfill=fulfill_of(status, desc, r[9])))
        ytdays.append({"date": sd, "sigs": sigs_d})
    D["ytdays"] = ytdays

    # 案2 暗态计数（已兑现·候二段，不渲染主栏/台账，仅留入口）
    try:
        D["dormant_n"] = rc.execute(
            "SELECT COUNT(*) FROM yuantu_buy_signals WHERE gap_status='dormant'").fetchone()[0]
    except Exception:
        D["dormant_n"] = 0

    # ── 在途未兑现台账：所有 open/closing 渊图信号（不受 top-3 时间窗限制）──
    # 补全展示：被主栏时间窗吞掉但状态仍在途的信号；同产业链取最近一条去重，
    # 排除已在主栏 top-3 窗口的信号日，标注"停跟天数"（data_day − 信号日）。
    yt_dateset = set(yt_dates)
    seen_chains, inflight = set(), []
    for r in rc.execute(
            "SELECT date, industry_chain, signal_node, signal_type, yuantu_confidence, "
            "beneficiaries, xiaobao_echo, gap_status, gap_desc, etf_anchor, excess_cum, "
            "date_realized, direction, direction_flip_date, beneficiaries_detail, "
            "source_plevel, relit_count "
            "FROM yuantu_buy_signals WHERE length(date)=10 "
            "AND gap_status IN ('open','closing') ORDER BY date DESC"):
        chain = r[1] or r[2]
        if chain in seen_chains:
            continue
        seen_chains.add(chain)
        if r[0] in yt_dateset:          # 已在主栏 top-3 窗口展示，不重复
            continue
        status = r[7] or "no_data"
        desc = (r[8] or "").replace("发现", "出现")
        try:
            lag = (datetime.date.fromisoformat(iso(data_day))
                   - datetime.date.fromisoformat(r[0])).days
        except Exception:
            lag = None
        # 进入趋势天数 = data_day − date_realized（价格触发/streak首日）；open 无则 None
        try:
            trend_lag = (datetime.date.fromisoformat(iso(data_day))
                         - datetime.date.fromisoformat(iso(r[11]))).days if r[11] else None
        except Exception:
            trend_lag = None
        inflight.append(dict(
            date=r[0], chain=chain, node=r[2], stype=r[3] or "", conf=r[4] or 0,
            bene=r[5] or "", echo=bool(r[6]), status=status, desc=desc,
            theme=(r[9] or "").split("/")[0], lag=lag, trend_lag=trend_lag,
            date_realized=r[11] or "", direction=r[12] or "多", flip_date=r[13] or "",
            bene_detail=r[14] or "",
            plv=r[15] or "—", relit=r[16] or 0,
            fulfill=fulfill_of(status, desc, r[10])))
    inflight.sort(key=lambda x: (x["lag"] if x["lag"] is not None else -1), reverse=True)
    # 方向分治（2026-06-25）：多头进正向台账；空头(卖出/买入转卖出)入风险提示、不正向追踪
    D["inflight"] = [g for g in inflight if g.get("direction") != "空"]
    D["inflight_risk"] = [g for g in inflight if g.get("direction") == "空"]

    # 课件信号（第二印证源，页面弱化为「课件信号」）：仅最新一批
    sd = rc.execute("SELECT MAX(date) FROM industry_signals WHERE etf_anchor!='' "
                    "AND (info_gap_level>=3 OR gap_status IN ('open','closing'))").fetchone()[0]
    rows = rc.execute(
        "SELECT etf_anchor, keyword, info_gap_level, gap_status, gap_desc, "
        "signal_content, confidence FROM industry_signals "
        "WHERE date=? AND etf_anchor!='' "
        "AND (info_gap_level>=3 OR gap_status IN ('open','closing')) "
        "ORDER BY info_gap_level DESC, gap_raw DESC", (sd,)).fetchall() if sd else []
    D["sigdays"] = [{"date": (sd or ""), "sigs": [dict(
        theme=(r[0] or "").split("/")[0], theme_full=r[0], kw=r[1], lvl=r[2],
        status=r[3], desc=(r[4] or "").replace("发现", "出现"), content=r[5] or "", conf=r[6] or "")
        for r in rows]}]

    # ── 机会 + 标的 + 三口径仓位 ──
    ratings = D["_ratings"]
    opps = []
    for t in themes:
        # 价格信号叠加（2026-06-30 Doctor·分层）：产业逻辑买入已在上游独立成栏，本栏在其上叠价格确认。
        # 两层——中期趋势没坏 e20≥0（不接飞刀，与锚侧 ex20 同 20 日窗）+ 短期正在启动 e5>0（新鲜点火）。
        early = ((t["sig"].get("open", 0) > 0 or "兑现初期" in (t["desc"] or ""))
                 and t["e20"] >= 0 and t["e5"] > 0)
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
            opps.append({"theme": t["short"], "e20": t["e20"], "e5": t["e5"], "desc": t["desc"],
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

    # ── 风险 ──
    risks = []
    risk_themes = []
    for t in themes:
        u = t["us"]
        if u and u["kind"] == "echo" and u["ex20"] < -10 and t["e20"] > 5:
            risk_themes.append(t["short"])
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
    if "源杰科技" in ratings:
        risks.append({"lvl": "黄", "txt": "估值极限标的在主线内：源杰科技（龙鱼估值维 2/15，PB 历史97.9%分位）"
                      "、奥比中光（PB 99.5%分位）——追高赔率差"})
    em = D["emotion"]
    if "秋" in (em["season"] or "") or "冬" in (em["season"] or ""):
        risks.append({"lvl": "黄", "txt": f"情绪周期处下行期（{em['season']}，评分 {em['score']}）"
                      "——风险偏好收缩中，机会提示需折扣"})
    D["risks"] = risks
    D["risk_themes"] = risk_themes
    return D


# ───────────────────────── HTML 渲染 ─────────────────────────
THEME_COLOR = {  # 星云色（按资金族近似）
    "光模块": "#4fc3f7", "AI算力": "#5b8cff", "半导体": "#7c6cff", "消费电子": "#9b7bff",
    "AI软件": "#6fd3e7", "机器人": "#ff8a5b", "商业航天": "#c06cff", "军工": "#b35bff",
    "新能源电池": "#3ddc97", "光伏": "#69d88a", "电力": "#5bd0c0",
    "创新药": "#ff6b9d", "白酒": "#e89b6b", "券商": "#d4a25c",
    "黄金": "#e8c46b", "稀土": "#e8a05b", "钨": "#caa86b", "有色金属": "#d8b05b",
}

SEASON_COLOR = {"春": "#3f9c76", "夏": "#a94e3f", "秋": "#8b6f32", "冬": "#1B365D"}
SEASON_GLOW = {"春": "47,125,99", "夏": "214,126,52", "秋": "139,111,50", "冬": "27,54,93"}  # 季节晕染 rgb（夏=橘色，与红字成双色；其余各保本季色，永不回绿）

_CND = "〇一二三四五六七八九"


def _cn_num(n):
    if n < 10:
        return _CND[n]
    if n == 10:
        return "十"
    if n < 20:
        return "十" + _CND[n % 10]
    return _CND[n // 10] + "十" + (_CND[n % 10] if n % 10 else "")


def cn_date(iso_str):
    """2026-06-12 → 二〇二六年六月十二日　星期五"""
    dt = datetime.date.fromisoformat(iso_str)
    y = "".join(_CND[int(c)] for c in str(dt.year))
    wd = "一二三四五六日"[dt.weekday()]
    return f"{y}年{_cn_num(dt.month)}月{_cn_num(dt.day)}日　星期{wd}"


def gen_stars(seed=42, n=(26, 16, 7)):
    """三层互质 tile 随机星场（低对比纹理，借鉴龙鱼标的库星空卡）"""
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


# ── 外盘栏目（隔夜·期货预期）：A股开盘前的外部定价背景 ──────────────────
# 两栏：美股(隔夜回望)在左、亚洲(期货预期)在右。code/symbol 与 fetch_intl_index.INDICES 同步。
INTL_US_INDEX = ("NASDAQ", "纳斯达克 · 隔夜", "美股隔夜 · 宽科技 tone")
INTL_US_STOCKS = [   # 美股栏代表股（AI/科技硬件链）
    ("NVDA", "英伟达",     "AI 算力"),
    ("AVGO", "博通",       "AI 网络 / ASIC"),
    ("LITE", "Lumentum",  "光模块 / CPO"),
    ("SPCX", "SpaceX",    "商业航天 · 新上市"),
]
INTL_ASIA = [        # 亚洲栏（期货预期 · 开盘前远期）
    ("JP_FUT",   "日本 · 股指期货",    "CME日经225 · 含半导体设备权重"),
    ("KR_PROXY", "韩国 · 股指期货预期", "MSCI韩国(EWY) · 三星/SK海力士存储芯"),
]
_INTL_KIND_BADGE = {"overnight": "隔夜回望", "us_stock": "隔夜",
                    "futures": "期货预期", "etf_proxy": "期货预期 · ETF代理"}


def _dir_cls(pct):
    return "up" if (pct or 0) > 0 else ("dn" if (pct or 0) < 0 else "flat")


def _intl_card(label, note, it):
    """大卡（纳指 / 日本 / 韩国）——沿用页面 .card 暖色范式。缺数→诚实「待回填」，绝不冒充。"""
    badge = _INTL_KIND_BADGE.get(it["kind"], it["kind"]) if it else ""
    if not it or it.get("pct") is None:
        return (f'<div class="card intl-card"><div class="k">{label}'
                f'<span class="intl-badge">待回填</span></div>'
                f'<div class="v"><span class="na">—</span></div>'
                f'<div class="sub">{note}</div></div>')
    pct = it["pct"]
    close = f'{it["close"]:,.2f}' if it.get("close") is not None else "—"
    shown_note = it.get("note") or note   # DB 内随源记的 note 优先（生产 QQQ/EWJ 时如实显示）
    return (
        f'<div class="card intl-card"><div class="k">{label}'
        f'<span class="intl-badge">{badge}</span></div>'
        f'<div class="v">{pct_span(pct)}</div>'
        f'<div class="mt">收 {close} ｜ {iso(it["date"])} ｜ {it["symbol"]}</div>'
        f'<div class="sub">{shown_note}</div></div>')


def _intl_stk(name, note, it):
    """美股代表股小卡——暖色 token 瓦片，与 .card 同语言。缺数→待回填。"""
    if not it or it.get("pct") is None:
        return (f'<div class="intl-stk"><div class="nm">{name}</div>'
                f'<div class="pc"><span class="na">—</span></div>'
                f'<div class="mt">待回填 · {note}</div></div>')
    pct = it["pct"]
    close = f'{it["close"]:,.2f}' if it.get("close") is not None else "—"
    shown_note = it.get("note") or note
    return (f'<div class="intl-stk"><div class="nm">{name}'
            f'<span class="sy">{it["symbol"]}</span></div>'
            f'<div class="pc">{pct_span(pct)}</div>'
            f'<div class="mt">{close} · {shown_note}</div></div>')


def intl_section(D):
    """外盘栏目 HTML（两栏：美股左 / 亚洲右）——全沿用页面暖色范式（.card/.chip 体系、token 配色、宋体数字）。"""
    intl = D.get("intl") or {}
    expected = [INTL_US_INDEX[0]] + [s[0] for s in INTL_US_STOCKS] + [a[0] for a in INTL_ASIA]
    have = sum(1 for c in expected if intl.get(c))
    vint = (f'{have}/{len(expected)} 已取' if have else '待回填')

    nasdaq = _intl_card(INTL_US_INDEX[1], INTL_US_INDEX[2], intl.get(INTL_US_INDEX[0]))
    stks = "".join(_intl_stk(nm, note, intl.get(code)) for code, nm, note in INTL_US_STOCKS)
    asia = "".join(_intl_card(label, note, intl.get(code)) for code, label, note in INTL_ASIA)

    style = (
        "<style>"
        ".intl-cols{display:grid;grid-template-columns:1fr 1fr;gap:14px;align-items:start;margin-top:6px}"
        "@media(max-width:760px){.intl-cols{grid-template-columns:1fr}}"
        ".intl-colhd{color:var(--sub);font-size:11.5px;letter-spacing:1px;font-weight:600;margin:2px 0 9px}"
        ".intl-card{margin-bottom:10px}"
        ".intl-card .k{display:flex;align-items:baseline;gap:7px}"
        ".intl-card .v{font-size:25px;margin-top:3px}"
        ".intl-card .mt{color:var(--sub);font-size:11px;margin-top:4px;"
        "font-family:var(--num);font-variant-numeric:tabular-nums}"
        ".intl-badge{font-size:10px;font-weight:400;color:#6b6a64;background:#fbf8ef;"
        "border:1px solid var(--line);border-radius:999px;padding:2px 8px;letter-spacing:0;white-space:nowrap}"
        ".intl-stocks{display:grid;grid-template-columns:1fr 1fr;gap:8px}"
        ".intl-stk{background:var(--card);border:1px solid var(--line);border-radius:12px;"
        "padding:8px 10px;box-shadow:var(--whisper)}"
        ".intl-stk .nm{font-size:12px;color:var(--tx);font-weight:600;display:flex;"
        "justify-content:space-between;align-items:baseline;gap:5px}"
        ".intl-stk .sy{font-size:9px;color:var(--sub);font-weight:400}"
        ".intl-stk .pc{font-size:17px;font-weight:600;font-family:var(--num);"
        "font-variant-numeric:tabular-nums;margin:2px 0 1px}"
        ".intl-stk .mt{font-size:10px;color:var(--sub);line-height:1.4}"
        "</style>")
    return (
        f'{style}'
        f'<h2 style="margin-bottom:4px">外盘 · 隔夜与期货预期 '
        f'<span class="vintage">A股开盘前的外部定价背景（AI/科技硬件链）· 各市场按自身最新交易日 · {vint}</span></h2>'
        f'<div class="intl-cols">'
        f'<div><div class="intl-colhd">美股 · 隔夜回望</div>{nasdaq}'
        f'<div class="intl-stocks">{stks}</div></div>'
        f'<div><div class="intl-colhd">亚洲 · 期货预期</div>{asia}</div>'
        f'</div>')


def _font_face():
    """字酷堂石刻体子集（春夏秋冬）内嵌；缺文件则回退本机字体栈（视觉降级，不报错）"""
    if not FONT_SEASONS.exists():
        logger.warning(f"⚠️ 石刻体子集缺失：{FONT_SEASONS}（『春』将回退本机字体）")
        return ""
    b64 = base64.b64encode(FONT_SEASONS.read_bytes()).decode()
    return ('@font-face{font-family:"ZZJY-ZKTSKT-Embedded";'
            f'src:url("data:font/ttf;base64,{b64}") format("truetype");'
            'font-weight:400;font-style:normal;font-display:block;'
            'unicode-range:U+6625,U+590F,U+79CB,U+51AC;}')


def _laiqin_art():
    if not ART_LAIQIN.exists():
        logger.warning(f"⚠️ 《果熟来禽图》素材缺失：{ART_LAIQIN}（画框左侧将留白）")
        return "none"
    mime = "image/webp" if ART_LAIQIN.suffix.lower() == ".webp" else "image/png"
    b64 = base64.b64encode(ART_LAIQIN.read_bytes()).decode()
    return f'url("data:{mime};base64,{b64}")'


def _echarts_inline():
    """ECharts 内联 <script>。

    Cowork artifact 沙箱只允许 Chart.js / Grid.js / Mermaid 走 CDN，其余库（含 ECharts）
    必须内联，否则 echarts 未定义 → emChart/capGauge 空白（GOTCHA：2026-06-25 CDN 退化致图表全空）。
    缺本地副本则回退 CDN 并告警（沙箱仍可能拦截，但不静默）。
    """
    if not ECHARTS_JS.exists():
        logger.warning(f"⚠️ echarts 本地副本缺失：{ECHARTS_JS}（回退 CDN，Cowork 沙箱可能拦截致图表空白）")
        return '<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>'
    return "<script>" + ECHARTS_JS.read_text(encoding="utf-8") + "</script>"


def _deploy_to_artifact(html, dd):
    """重渲即部署：给日报 HTML 套上 cowork-artifact-meta 头，直接写入 Cowork artifact 的
    index.html，使生成器一步同时更新 AI4ME 产物与 artifact。

    - Artifacts 目录不存在（异机/无 Cowork 环境）→ 跳过 + 告警，不报错、不阻塞生成。
    - 写前备份现有 index.html 到 index.bak.<ts>.html（可逆，永不直接覆盖无备份）。
    - 注意：直接写文件绕过 update_artifact，manifest 的 updatedAt 不会刷新，但渲染读的是
      文件本身，内容照常更新（已由 2026-06-26 echarts 手工补丁验证）。
    """
    art_dir = ARTIFACT_PATH.parent
    if not art_dir.exists():
        logger.warning(f"⚠️ Cowork artifact 目录不存在：{art_dir}（跳过部署，仅写 AI4ME）")
        return
    meta = {
        "name": "烛照九阴复盘日报",
        "schemaVersion": 1,
        "description": (f"最后更新：{datetime.datetime.now():%Y-%m-%d %H:%M}（{dd} 期）。\n"
                        "Update at：周一至周五 07:00（生成器自动部署，无需手工 update_artifact）。\n\n"
                        "盘后复盘看板，ECharts 与字体内联、画框《果熟来禽图》内嵌，完全自包含；数据为当期快照。"),
    }
    meta_block = ('<script type="application/json" id="cowork-artifact-meta">\n'
                  + json.dumps(meta, ensure_ascii=False, indent=2)
                  + '\n</script>\n')
    artifact_html = html.replace("<!DOCTYPE html>\n", "<!DOCTYPE html>\n" + meta_block, 1)
    if ARTIFACT_PATH.exists():
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        bak = ARTIFACT_PATH.with_name(f"index.bak.{stamp}.html")
        shutil.copy2(ARTIFACT_PATH, bak)
        logger.info(f"📦 artifact 旧版备份 → {bak.name}")
    ARTIFACT_PATH.write_text(artifact_html, encoding="utf-8")
    logger.info(f"🚀 已部署到 Cowork artifact → {ARTIFACT_PATH}（{len(artifact_html)/1048576:.2f} MB）")


# 暖色日报 CSS（普通字符串 + 占位符，规避 f-string 花括号转义——G-04）
# 注意：.report-hero 的 --hero-lock-* / --hero-art-* / --season-* 为 Doctor 锁定变量。
CSS_WARM = """
__FONT_FACE__
:root{--bg:#f5f4ed;--card:#faf9f5;--panel:#f1eee4;--line:#e8e6dc;--tx:#141413;--sub:#6b6a64;
--red:#a94e3f;--grn:#2f7d63;--gold:#8b6f32;--acc:#1B365D;--spring:#2f7d63;
--brand-tint:#eef2f7;--sand:#eee6d6;--border-soft:#eeeade;--whisper:0 4px 24px rgba(20,20,19,.05);
--laiqin-art:__LAIQIN_ART__;
--stone:"ZZJY-ZKTSKT-Embedded","zktskt","字酷堂石刻体","ZiKuTangShiKeTi","Zikutang Shiketi","STKaiti","Kaiti SC",serif;
--zh:"Source Han Serif SC","思源宋体 SC","思源宋体","Songti SC","STSong",serif;
--num:var(--zh)}
*{box-sizing:border-box;margin:0}
body{background:
radial-gradient(900px 520px at 50% -8%,rgba(47,125,99,.14),transparent 62%),
radial-gradient(900px 560px at 86% -8%,rgba(27,54,93,.10),transparent 58%),
linear-gradient(180deg,#f8f4ea 0%,var(--bg) 42%,#eee7d8 100%);
color:var(--tx);font:15px/1.65 var(--zh);font-weight:400;padding:22px;max-width:1280px;margin:auto;
-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
h1{font-size:22px;font-weight:700;letter-spacing:3px}
h2{font-size:15px;font-weight:600;color:var(--acc);margin:30px 0 12px;letter-spacing:1.5px}
.vintage{color:var(--sub);font-size:12px;font-weight:400;letter-spacing:0}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(175px,1fr));gap:12px;margin-top:14px}
/* 非重点面板：轻装饰，给 P0 模块让位 */
.card,.opp,.risk{position:relative;overflow:hidden;
 background:var(--card);
 border:1px solid var(--line);
 box-shadow:var(--whisper)}
.card::after,.opp::after,.risk::after{content:"";position:absolute;inset:0;border-radius:inherit;pointer-events:none;
 background:linear-gradient(180deg,rgba(255,255,255,.45),transparent 42%)}
.card{border-radius:16px;padding:14px 16px}
.card .k{color:var(--sub);font-size:12px;letter-spacing:.5px}
.card .v{font-size:27px;font-weight:600;font-family:var(--num);font-variant-numeric:tabular-nums;margin-top:3px;letter-spacing:0}
.card .sub{color:var(--sub);font-size:11px;margin-top:3px}
.card .v,.snapshot-number,.p0-v,.liquidity-grid b,.mday-h b,.mday-h .sub,.mc-pct,.mcard .sub,.sc-h .lvl,.tag,.thermo,.chip em,.opp-h .sub,.opp-d,.risk,.score-vars span,.score-formula,.dk,.fulfill-v,.fulfill-d,td,#modal .sub,#modal .desc,#modal .tag{font-family:var(--num);font-variant-numeric:tabular-nums lining-nums;font-feature-settings:"tnum" 1,"lnum" 1;letter-spacing:0}
.liquidity-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:10px 0 6px}
.liquidity-grid div{padding:8px 10px;border-radius:10px;background:#f4efe5;border:1px solid var(--border-soft)}
.liquidity-grid b{display:block;font-family:var(--zh);font-size:17px;line-height:1.12;color:var(--tx)}
.liquidity-grid span{display:block;color:var(--sub);font-size:10.5px;margin-top:3px}
.score-basis{margin-top:8px;padding:10px 11px;border-radius:12px;background:rgba(244,239,229,.62);border:1px solid var(--border-soft)}
.score-formula{font-size:11.5px;line-height:1.55;color:var(--sub)}
.score-formula b{color:var(--tx);font-weight:600}
.score-vars{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.score-vars span{font-size:10.5px;line-height:1;padding:6px 7px;border-radius:999px;background:#fbf8ef;border:1px solid rgba(27,54,93,.10);color:#4f5b70}
.up{color:var(--red)} .dn{color:var(--grn)} .na{color:#9a9386}
.udbar{display:flex;height:11px;border-radius:999px;overflow:hidden;margin-top:10px;background:#eadfcb;
 border:1px solid var(--line);box-shadow:inset 0 1px 4px rgba(20,20,19,.10);position:relative}
.udbar::after{content:"";position:absolute;inset:1px;border-radius:inherit;
 background:linear-gradient(180deg,rgba(255,255,255,.50),transparent 54%);pointer-events:none}
.udbar i{background:linear-gradient(90deg,#b87364,var(--red));box-shadow:0 0 14px rgba(169,78,63,.18)}
.udbar b{background:linear-gradient(90deg,var(--grn),#198a67);box-shadow:0 0 18px rgba(61,220,151,.26)}
.row2{display:grid;grid-template-columns:minmax(0,1.08fr) minmax(300px,.92fr);gap:12px;margin-top:14px}
@media(max-width:900px){.row2{grid-template-columns:1fr}.cards{grid-template-columns:1fr 1fr}}
.season{font-size:34px} .gauge,#emChart{height:170px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden;box-shadow:var(--whisper)}
th{color:var(--sub);font-weight:600;font-size:11px;text-align:left;padding:9px 11px;border-bottom:1px solid var(--line);letter-spacing:1px}
td{padding:8px 11px;border-bottom:1px solid var(--border-soft);font-family:var(--num);font-variant-numeric:tabular-nums;vertical-align:middle;font-size:13.5px}
td.tname,td.desc,td.kw{font-family:var(--zh)}
.tname{font-weight:600;font-size:14px} .desc{color:var(--sub);font-size:12px;max-width:300px;line-height:1.5}
.tag{font-size:11px;padding:1px 7px;border-radius:9px;background:#ebe6db;color:var(--sub)}
.t-closing{background:#f0e6cf;color:var(--gold)} .t-open{background:var(--brand-tint);color:var(--acc)} .t-closed{background:#ebe6db} .t-dormant{background:#e7e2d6;color:var(--sub)}
.dormant-note{margin:2px 0 16px;padding:9px 13px;border-radius:12px;background:var(--panel);border:1px dashed var(--line);color:var(--sub);font-size:12px}
.led-grid{display:grid;gap:8px;margin:10px 0 16px;align-items:stretch}
.led-colh{align-self:end;text-align:center;font-size:10.5px;color:var(--sub);letter-spacing:.08em;padding-bottom:3px}
.led-rowh{align-self:center;font-size:12px;font-weight:600;color:var(--tx);padding-right:6px;white-space:nowrap}
.led-tile{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:1px;min-height:52px;border-radius:12px;background:rgba(251,248,239,.72);border:1px solid rgba(27,54,93,.08);cursor:pointer;transition:transform .15s,border-color .15s,box-shadow .15s}
.led-tile:hover{transform:translateY(-3px);border-color:rgba(27,54,93,.28);box-shadow:0 6px 16px rgba(27,54,93,.08)}
.led-tile b{font-size:20px;font-weight:700;color:var(--acc);line-height:1;font-variant-numeric:tabular-nums}
.led-tile span{font-size:9.5px;color:var(--sub)}
.led-tile.empty{background:transparent;border:1px dashed var(--line);cursor:default;transform:none;box-shadow:none}
.led-tile.empty b{color:var(--line);font-size:14px}
.led-tile.sum{background:var(--panel);cursor:default;transform:none;box-shadow:none;border-color:transparent}
.led-tile.sum b{color:var(--tx)}
.led-tile.sum.total b{color:var(--acc)}
.lm-item{margin:9px 0}
.lm-r1{display:grid;grid-template-columns:minmax(0,1fr) 104px 74px;gap:8px;align-items:center;font-size:12.5px}
.lm-chain{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:600;color:var(--tx)}
.lm-st{justify-self:end;display:flex;gap:5px;align-items:center}
.lm-conf{justify-self:end;color:var(--sub);font-size:11px;font-variant-numeric:tabular-nums;white-space:nowrap}
.lm-r2{font-size:11px;color:var(--sub);margin-top:2px;line-height:1.4}
.lm-item{cursor:pointer;border-radius:9px;padding:5px 7px;margin:6px -7px;transition:background .15s}
.lm-item:hover{background:rgba(27,54,93,.05)}
.lm-conf{color:var(--sub)}
.lm-back{display:inline-block;margin:0 0 12px;font-size:11.5px;color:var(--acc);cursor:pointer;font-weight:600}
.lm-back:hover{text-decoration:underline}
.ledger-wrap{margin:8px 0 14px}
.ledger-h{font-size:14px;font-weight:600;color:var(--tx);margin:12px 0 8px}
.ledger-h .sub{font-weight:400}
.ledger-row{display:flex;align-items:center;gap:10px;padding:8px 12px;margin:5px 0;border-radius:11px;
 border:1px solid var(--line);background:var(--card);cursor:pointer;
 transition:transform .15s,box-shadow .15s,border-color .15s}
.ledger-row:hover{transform:translateX(2px);box-shadow:var(--whisper);border-color:var(--sc)}
.lg-dot{width:9px;height:9px;border-radius:50%;flex:0 0 auto;background:var(--sc)}
.lg-chain{font-size:13px;font-weight:500;color:var(--tx);flex:0 1 auto;
 overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:46%}
.lg-meta{font-size:11px;color:var(--sub);margin-left:auto;text-align:right;flex:0 0 auto}
@media(max-width:900px){.lg-chain{max-width:38%}.lg-meta{font-size:10px}}
.thermo{font-size:10px;color:var(--sub);border:1px solid var(--line);border-radius:6px;padding:0 4px;margin-left:4px}
.chip{display:inline-block;background:#f4efe5;border:1px solid var(--line);border-radius:8px;padding:3px 10px;margin:3px 6px 0 0}
.chip em{font-style:normal;color:var(--gold);font-size:11px;margin-left:6px}
.opp{border:1px solid #d7deea;border-radius:14px;padding:12px 14px;margin-bottom:10px;
 background:linear-gradient(135deg,var(--brand-tint),var(--card))}
.opp-h{font-weight:600} .opp-d{color:var(--sub);font-size:12px;margin:4px 0}
.risk{border-radius:14px;padding:10px 14px;margin-bottom:8px;font-size:13px}
.r-红{border-color:#e3c4bb;background:linear-gradient(135deg,#f4e5df,var(--card))}
.r-黄{border-color:#dfd0aa;background:linear-gradient(135deg,#f3ead6,var(--card))}
.foot{color:#9a9386;font-size:11px;margin:30px 0 10px;border-top:1px solid var(--line);padding-top:10px}
.mday{margin-bottom:18px}
.mday-h{font-size:14px;margin-bottom:10px;color:var(--tx)} .mday-h b{font-family:var(--num)}
.mrow{display:flex;gap:12px;overflow-x:auto;padding:4px 2px 10px}
.mrow::-webkit-scrollbar{height:6px} .mrow::-webkit-scrollbar-thumb{background:#d7cdb9;border-radius:3px}
.mrow .mcard,.mrow .scard,.mrow .fulfill-card{flex:0 0 236px}
.report-title{margin:2px 0 14px;padding:0 4px;display:inline-block;text-align:center}
.report-name{display:block;font-size:24px;font-weight:700;letter-spacing:1.8px;line-height:1.18;color:var(--tx);white-space:nowrap;text-align:left}
.report-meta{display:block;color:var(--sub);font-size:12px;line-height:1.35;text-align:center;white-space:nowrap;margin-top:6px}
.report-hero{
 --hero-lock-min-height:296px;--hero-lock-padding:26px 32px 26px;--hero-lock-grid:minmax(285px,.88fr) minmax(420px,1.12fr);--hero-lock-gap:34px;
 --hero-art-left:0;--hero-art-top:0;--hero-art-width:min(58%,660px);--hero-art-height:100%;
 --season-left:50%;--season-top:50%;--season-width:min(320px,34vw);--season-glow-width:260px;--season-glow-height:190px;
 position:relative;margin:4px 0 18px;min-height:var(--hero-lock-min-height);padding:var(--hero-lock-padding);border:1px solid rgba(27,54,93,.16);
 border-radius:22px;display:grid;grid-template-columns:var(--hero-lock-grid);gap:var(--hero-lock-gap);align-items:stretch;
 background:
 radial-gradient(480px 210px at 50% 42%,rgba(47,125,99,.16),transparent 70%),
 radial-gradient(520px 250px at 76% 8%,rgba(27,54,93,.10),transparent 72%),
 linear-gradient(135deg,#fbf8ef,#f1eadc);
 box-shadow:var(--whisper),inset 0 0 0 1px rgba(255,255,255,.48);overflow:hidden}
.report-hero::before{content:"";position:absolute;inset:-20%;background:
 radial-gradient(1px 1px at 12% 24%,rgba(27,54,93,.22),transparent),
 radial-gradient(1px 1px at 28% 70%,rgba(80,78,73,.16),transparent),
 radial-gradient(1.4px 1.4px at 74% 32%,rgba(47,125,99,.18),transparent),
 radial-gradient(1px 1px at 88% 78%,rgba(27,54,93,.14),transparent);
 background-size:180px 130px;opacity:.84;animation:twinkle 4.8s ease-in-out infinite alternate;z-index:0;pointer-events:none}
.report-hero::after{content:none}
.hero-art{position:absolute;left:var(--hero-art-left);top:var(--hero-art-top);width:var(--hero-art-width);height:var(--hero-art-height);
 background:var(--laiqin-art) left top/auto 100% no-repeat;filter:blur(.25px) saturate(1.02);
 z-index:1;pointer-events:none}
.season-core{position:absolute;left:var(--season-left);top:var(--season-top);transform:translate(-50%,-50%);z-index:4;width:var(--season-width);text-align:center;padding:0;pointer-events:none}
.season-core::before{content:"";position:absolute;left:50%;top:50%;width:var(--season-glow-width);height:var(--season-glow-height);transform:translate(-50%,-50%);
 background:
  radial-gradient(62% 46% at 44% 48%,rgba(__SEASON_GLOW__,.15) 0%,rgba(__SEASON_GLOW__,.09) 34%,rgba(__SEASON_GLOW__,.035) 58%,transparent 78%),
  radial-gradient(44% 36% at 60% 36%,rgba(__SEASON_GLOW__,.10) 0%,rgba(__SEASON_GLOW__,.045) 42%,transparent 72%),
  radial-gradient(46% 40% at 36% 64%,rgba(__SEASON_GLOW__,.08) 0%,rgba(__SEASON_GLOW__,.035) 38%,transparent 74%);
 filter:blur(10px) contrast(1.08);opacity:.92;z-index:-1;pointer-events:none}
.season-label{font-size:12px;color:var(--sub);letter-spacing:.24em;text-transform:uppercase;margin-bottom:18px}
.season-glyph{font-family:var(--stone) !important;font-weight:400;font-style:normal;font-synthesis:none;font-size:118px;line-height:.92;color:__SEASON_COLOR__;
 text-shadow:0 0 22px rgba(__SEASON_GLOW__,.24),0 0 46px rgba(__SEASON_GLOW__,.10),0 1px 0 rgba(255,255,255,.42),0 9px 22px rgba(20,20,19,.12);
 letter-spacing:0;margin:0 auto}
.season-sub{font-family:var(--zh);font-size:13px;color:var(--sub);margin-top:20px}
.hero-date-vertical{position:absolute;right:28px;top:34px;bottom:34px;z-index:3;writing-mode:vertical-rl;text-orientation:mixed;
 font-family:var(--zh);font-size:13px;line-height:1.8;letter-spacing:.16em;color:rgba(27,54,93,.54);
 display:flex;align-items:center;justify-content:center;pointer-events:none}
.snapshot-band{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:-4px 0 16px;padding:0 4px}
.snapshot-item{position:relative;padding:12px 14px 11px;background:linear-gradient(180deg,rgba(255,250,241,.42),rgba(255,250,241,0));min-height:70px}
.snapshot-label{font-size:11px;line-height:1.35;color:var(--sub);letter-spacing:.08em}
.snapshot-number{font-family:var(--zh);font-size:21px;line-height:1.12;font-weight:600;font-variant-numeric:tabular-nums;margin-top:7px;color:var(--tx)}
.snapshot-note{font-size:11px;line-height:1.35;color:var(--sub);margin-top:5px}
.snapshot-bar{display:flex;height:7px;border-radius:999px;overflow:hidden;background:#eadfcb;margin-top:8px;border:1px solid var(--line)}
.snapshot-bar .gain{display:block;background:linear-gradient(90deg,#b87364,var(--red));box-shadow:0 0 12px rgba(169,78,63,.16)}
.snapshot-bar .loss{display:block;background:linear-gradient(90deg,#3ddc97,#198a67);box-shadow:0 0 12px rgba(61,220,151,.20)}
.snapshot-bar .flat{display:block;background:linear-gradient(90deg,#9ab6d8,#5f88b7);box-shadow:0 0 10px rgba(95,136,183,.16)}
.p0-strip{display:grid;grid-template-columns:repeat(2,1fr);gap:12px;margin:16px 0 10px}
.p0-card{position:relative;padding:14px 16px;border-radius:18px;border:1px solid var(--line);
 background:linear-gradient(145deg,var(--card),#f2ebdd);overflow:hidden;
 box-shadow:var(--whisper)}
.p0-card::before{content:"";position:absolute;inset:0;background:radial-gradient(260px 100px at 12% 0,color-mix(in srgb,var(--sc,#1B365D) 18%,transparent),transparent 68%);opacity:.72}
.p0-card>*{position:relative}
.p0-k{font-size:11px;color:var(--sub);letter-spacing:.14em;text-transform:uppercase}
.p0-v{font-size:22px;font-weight:700;margin-top:4px}
.p0-d{font-size:12px;color:var(--sub)}
.gap-chain{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:10px 0 18px}
.gap-step{position:relative;padding:12px 13px;border-radius:15px;background:var(--card);border:1px solid var(--line);
 box-shadow:var(--whisper)}
.gap-step::after{content:"";position:absolute;top:50%;right:-10px;width:10px;height:1px;background:linear-gradient(90deg,var(--acc),transparent)}
.gap-step:last-child::after{display:none}
.gap-step b{display:block;font-size:13px}
.gap-step span{display:block;color:var(--sub);font-size:11px;margin-top:2px}
.gap-step.jump{cursor:pointer;transition:transform .15s ease,border-color .15s ease,box-shadow .15s ease}
.gap-step.jump:hover,.gap-step.jump:focus-visible{transform:translateY(-1px);border-color:var(--acc);box-shadow:0 5px 16px rgba(0,0,0,.07);outline:none}
.gap-step .jhint{position:absolute;right:11px;bottom:7px;margin:0;font-size:10px;color:var(--acc);opacity:.55}
@media(max-width:900px){.report-title{max-width:100%}.report-meta{white-space:normal}.report-hero{--hero-lock-min-height:520px;--hero-lock-grid:1fr;--hero-art-width:340px;--hero-art-height:100%;--season-top:150px;--season-width:260px;grid-template-columns:var(--hero-lock-grid);min-height:var(--hero-lock-min-height)}.hero-art{background-size:auto 100%;filter:blur(.25px) saturate(1.02)}.hero-date-vertical{right:16px;top:22px;bottom:auto;height:180px;font-size:12px;opacity:.78}.season-glyph{font-size:92px}.snapshot-band,.p0-strip,.gap-chain{grid-template-columns:1fr}.snapshot-band{margin:0 0 14px;padding:0}.snapshot-item{min-height:auto}}
/* ── 星空卡（低对比纹理，重点模块专用）── */
.glass{position:relative;
 background:linear-gradient(150deg,#fbf8ef,#f0eadc 46%,#f7f3ea);
 backdrop-filter:none;-webkit-backdrop-filter:none;
 border:1px solid var(--line);border-radius:18px;
 box-shadow:var(--whisper),inset 0 0 0 1px rgba(255,255,255,.42)}
.glass>*{position:relative;z-index:1}
.glass::after{content:"";position:absolute;inset:0;border-radius:inherit;pointer-events:none;z-index:0;
 background:linear-gradient(180deg,rgba(255,255,255,.44),transparent 32%);mix-blend-mode:normal}
.mcard{padding:16px 18px;min-height:90px;cursor:pointer;overflow:hidden;transition:transform .18s,box-shadow .18s,border-color .18s}
.mcard:hover{transform:translateY(-3px);border-color:rgba(27,54,93,.34);
 box-shadow:0 0 0 1px rgba(27,54,93,.10),0 8px 28px rgba(20,20,19,.08),inset 0 0 0 1px rgba(255,255,255,.55);
 background:linear-gradient(150deg,#fffaf1,#f0eadc 42%,#f7f3ea)}
.mcard .aurora{position:absolute;inset:0;z-index:0;pointer-events:none;overflow:hidden;border-radius:inherit}
.mcard .neb{position:absolute;inset:0;filter:blur(10px);opacity:.9;will-change:transform;
 animation:nebDrift 22s ease-in-out infinite alternate;
 background:radial-gradient(50% 60% at 10% 0%,color-mix(in srgb,var(--sc,#888) 60%,transparent),transparent 66%),
  radial-gradient(55% 65% at 35% 25%,color-mix(in srgb,var(--sc,#888) 38%,transparent),transparent 70%),
  radial-gradient(70% 80% at 62% 48%,color-mix(in srgb,var(--sc,#888) 22%,transparent),transparent 76%)}
.mcard .stars{position:absolute;inset:0;opacity:.9;animation:twinkle 4.5s ease-in-out infinite alternate;
 background-image:__STARS_BG__;
 background-repeat:repeat;background-size:__STARS_SIZE__}
@keyframes nebDrift{from{transform:translate(-2%,-1%) scale(1)}to{transform:translate(2%,2%) scale(1.06)}}
@keyframes twinkle{0%{opacity:.62}100%{opacity:.95}}
.mc-h{display:flex;justify-content:space-between;align-items:baseline;font-size:13px}
.mc-h b{font-size:18px;font-weight:700;letter-spacing:.5px;color:var(--acc)}
.mc-pct{font-family:var(--num);font-size:18px;font-weight:600}
.mcard .sub{font-size:13.5px;margin-top:6px;line-height:1.45}
.mcard .stars{display:none}
.mcard .neb{animation:none;opacity:.45;filter:blur(14px)}
.dk{display:inline-block;min-width:66px;color:var(--sub);font-size:11px}
/* 信号小卡 + 兑现度卡 */
.scard{min-height:88px;padding:12px 14px;cursor:pointer;overflow:hidden;transition:transform .18s,box-shadow .18s,border-color .18s}
.scard:hover{transform:translateY(-3px);border-color:rgba(27,54,93,.34);
 box-shadow:0 0 0 1px rgba(27,54,93,.10),0 8px 28px rgba(20,20,19,.08)}
.scard .neb{opacity:.5} .scard .stars{opacity:.6}
.scard.xb{opacity:.72;border-style:dashed} .scard.xb:hover{opacity:1}
.fulfill-card{min-height:88px;padding:12px 14px;cursor:pointer;overflow:hidden;border-radius:10px;background:rgba(251,248,239,.72);
 border:1px solid rgba(27,54,93,.12);box-shadow:inset 0 1px 0 rgba(255,255,255,.58);
 display:flex;flex-direction:column;justify-content:center;gap:6px;transition:transform .18s,box-shadow .18s,border-color .18s}
.fulfill-card:hover{transform:translateY(-3px);border-color:rgba(27,54,93,.34);
 box-shadow:0 0 0 1px rgba(27,54,93,.10),0 8px 28px rgba(20,20,19,.08)}
.fulfill-k{font-size:10.5px;line-height:1;color:var(--sub);letter-spacing:.08em}
.fulfill-v{font-size:18px;font-weight:700;line-height:1;color:var(--acc)}
.fulfill-bar{height:6px;border-radius:999px;overflow:hidden;background:#eadfcb;border:1px solid rgba(27,54,93,.10)}
.fulfill-bar span{display:block;width:var(--fulfill,12%);height:100%;border-radius:inherit;background:linear-gradient(90deg,#8aa0c8,#4fc3f7)}
.fulfill-d{font-size:10.5px;line-height:1.3;color:var(--sub)}
.sc-h{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.sc-h .lvl{font-family:var(--num);color:var(--gold);font-weight:600;font-size:13px}
.sc-kw{font-size:13.5px;font-weight:600;line-height:1.4;margin-bottom:3px}
/* 中心浮层 */
#overlay{display:none;position:fixed;inset:0;z-index:90;background:rgba(80,78,73,.22);
 backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px)}
#overlay.show{display:block;animation:fadeIn .16s ease}
#modal{position:fixed;left:50%;top:50%;transform:translate(-50%,-50%);z-index:99;
 width:min(580px,92vw);max-height:82vh;overflow-y:auto;padding:20px 22px;
 display:none;animation:popIn .2s cubic-bezier(.2,.9,.3,1.2)}
#modal.show{display:block}
#modal .modal-title{font-size:19px;font-weight:700;margin-bottom:12px;display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;
 padding-bottom:10px;border-bottom:1px solid var(--line)}
#modal>div:not(.modal-title):not(.aurora){margin-bottom:7px;position:relative;z-index:1;font-size:13px}
#modalX{position:absolute;right:14px;top:12px;z-index:2;cursor:pointer;color:var(--sub);font-size:18px;
 width:28px;height:28px;display:flex;align-items:center;justify-content:center;border-radius:50%;transition:all .15s}
#modalX:hover{color:var(--tx);background:#f0eadc;transform:rotate(90deg)}
@keyframes fadeIn{from{opacity:0}to{opacity:1}}
@keyframes popIn{from{opacity:0;transform:translate(-50%,-46%) scale(.96)}to{opacity:1;transform:translate(-50%,-50%) scale(1)}}
"""

# 图表 JS（普通字符串 + 占位符；ECharts 用 SVG renderer 保证字体）
JS_TPL = """
const em = echarts.init(document.getElementById('emChart'), null, {renderer:'svg'});
const es = __EM_SERIES__;
em.setOption({grid:{left:34,right:12,top:18,bottom:24},
 xAxis:{type:'category',data:es.map(x=>x[0].slice(5)),axisLabel:{color:'#6b6a64',fontSize:9,interval:14},axisLine:{lineStyle:{color:'#e8e6dc'}},axisTick:{show:false}},
 yAxis:{min:0,max:100,axisLabel:{color:'#6b6a64',fontSize:9},splitLine:{lineStyle:{color:'rgba(80,78,73,.14)'}},splitArea:{show:true,areaStyle:{color:['rgba(47,125,99,.035)','rgba(27,54,93,.025)']}}},
 series:[
  {type:'line',name:'当日原始',data:es.map(x=>x[1]),smooth:false,symbol:'none',lineStyle:{color:'rgba(27,54,93,.30)',width:1},z:1},
  {type:'line',name:'MA5 · 季节判定',data:es.map(x=>x[2]),smooth:true,symbol:'circle',symbolSize:3,
  itemStyle:{color:'#2f7d63'},lineStyle:{color:'#2f7d63',width:3,shadowBlur:8,shadowColor:'rgba(47,125,99,.18)'},z:3,
  areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[{offset:0,color:'rgba(47,125,99,.16)'},{offset:1,color:'rgba(47,125,99,0)'}]}},
  markLine:{silent:true,symbol:'none',label:{color:'#6b6a64',fontSize:10},lineStyle:{color:'rgba(139,111,50,.38)',type:'dashed'},data:[{yAxis:50,name:'中线'}]}}],
 tooltip:{trigger:'axis',backgroundColor:'rgba(250,249,245,.98)',borderColor:'#d7deea',textStyle:{color:'#141413',fontSize:11}}});
const g = echarts.init(document.getElementById('capGauge'), null, {renderer:'svg'});
g.setOption({series:[{type:'gauge',min:0,max:__GMAX__,startAngle:205,endAngle:-25,
 progress:{show:true,width:12,roundCap:true,itemStyle:{color:'#2f7d63',shadowBlur:8,shadowColor:'rgba(47,125,99,.18)'}},
 axisLine:{roundCap:true,lineStyle:{width:12,color:[[0.34,'rgba(47,125,99,.24)'],[0.62,'rgba(139,111,50,.28)'],[1,'rgba(169,78,63,.24)']]}},
 pointer:{show:false},axisTick:{distance:2,length:5,lineStyle:{color:'rgba(80,78,73,.26)',width:1}},splitLine:{distance:2,length:10,lineStyle:{color:'rgba(80,78,73,.32)',width:1}},
 axisLabel:{show:false},
 detail:{valueAnimation:true,fontSize:30,color:'#141413',fontFamily:'Source Han Serif SC',offsetCenter:[0,'12%'],formatter:'K {value}'},
 data:[{value:__KDAY__}],title:{show:false},
 markLine:{}},
 {type:'gauge',min:0,max:__GMAX__,startAngle:205,endAngle:-25,
  pointer:{show:true,length:'68%',width:4,itemStyle:{color:'#a94e3f',shadowBlur:8,shadowColor:'rgba(169,78,63,.22)'}},
  anchor:{show:true,size:7,itemStyle:{color:'#faf9f5',borderColor:'#a94e3f',borderWidth:2}},
  axisLine:{show:false},axisTick:{show:false},splitLine:{show:false},axisLabel:{show:false},detail:{show:false},
  data:[{value:__KCAP__}]}]});
let modalStack=[];
function showTpl(id){
 const tpl=document.getElementById(id);
 const body=document.getElementById('modalBody');
 body.innerHTML='';
 body.appendChild(tpl.content.cloneNode(true));
 const t=body.querySelector('.modal-title');
 if(t&&t.style.getPropertyValue('--sc'))
  document.getElementById('modal').style.setProperty('--sc',t.style.getPropertyValue('--sc'));
 document.getElementById('overlay').classList.add('show');
 document.getElementById('modal').classList.add('show');
 document.body.style.overflow='hidden';}
function openModal(id){modalStack.push(id);showTpl(id);}
function backModal(){
 modalStack.pop();
 if(modalStack.length){showTpl(modalStack[modalStack.length-1]);}
 else{closeModal();}}
function closeModal(){
 modalStack=[];
 document.getElementById('overlay').classList.remove('show');
 document.getElementById('modal').classList.remove('show');
 document.body.style.overflow='';}
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeModal();});
window.addEventListener('resize',()=>{em.resize();g.resize();});
"""


def render(D):
    STARS_BG, STARS_SIZE = gen_stars()
    s, cap, em = D["snap"], D["capacity"], D["emotion"]
    dd = iso(D["data_day"])
    season = (em["season"] or "—")[0]

    css = (CSS_WARM
           .replace("__FONT_FACE__", _font_face())
           .replace("__LAIQIN_ART__", _laiqin_art())
           .replace("__SEASON_COLOR__", SEASON_COLOR.get(season, "#3f9c76"))
           .replace("__SEASON_GLOW__", SEASON_GLOW.get(season, "47,125,99"))
           .replace("__STARS_BG__", STARS_BG)
           .replace("__STARS_SIZE__", STARS_SIZE))

    # ── 首屏画框（Doctor 锁定构图：框外标题 → 画框 → 四联条）──
    hero = f"""
<header class="report-title" aria-label="日报标题">
<div class="report-name">烛照九阴 · 复盘日报</div>
<div class="report-meta">数据日 {dd} ｜ 生成 {D["gen_time"]}</div>
</header>

<section class="report-hero" aria-label="今日情绪周期">
<div class="hero-art" aria-hidden="true"></div>
<div class="hero-date-vertical" aria-label="{cn_date(dd)}">{cn_date(dd)}</div>
<div class="season-core" aria-label="情绪周期：{season}">
 <div class="season-label">情绪周期</div>
 <div class="season-glyph">{season}</div>
 <div class="season-sub">评分 {em["score"]} ｜ 风险偏好 {em["risk"]} ｜ MA5 {em["ma5"]}</div>
</div>
</section>"""

    # ── 市场快照四联条 ──
    amount_str = f"{s['amount']:.2f}" if s["amount"] else None
    amount_html = (f'<div class="snapshot-number">{amount_str} 万亿</div>'
                   f'<div class="snapshot-note">容量 K_cap≈{cap["kcap"]}</div>'
                   if amount_str else
                   '<div class="snapshot-number na">待回填</div>'
                   f'<div class="snapshot-note">market_amount_daily 停更于 {iso(s["amount_vintage"]) if s["amount_vintage"] else "—"}</div>')
    if s["up_n"] is not None:
        tot = s["up_n"] + s["down_n"] + (s["flat_n"] or 0)
        gw, lw = 100 * s["up_n"] / tot, 100 * s["down_n"] / tot
        fw = max(0.0, 100 - gw - lw)
        # 涨在前（红）/ 跌在后（绿）/ 平最后（蓝）——Doctor 2026-06-12 裁定，A股红涨绿跌口径
        breadth_html = (f'<div class="snapshot-number"><span class="up">{s["up_n"]}</span> / '
                        f'<span class="dn">{s["down_n"]}</span></div>'
                        f'<div class="snapshot-bar" aria-label="涨跌平盘家数占比（涨红/跌绿/平蓝）">'
                        f'<span class="gain" style="width:{gw:.0f}%"></span>'
                        f'<span class="loss" style="width:{lw:.0f}%"></span>'
                        f'<span class="flat" style="width:{fw:.0f}%"></span></div>')
        if s["flat_n"] is None:
            breadth_html = (f'<div class="snapshot-number"><span class="up">{s["up_n"]}</span> / '
                            f'<span class="dn">{s["down_n"]}</span></div>'
                            '<div class="snapshot-note">平盘家数缺数，仅展示涨跌</div>')
    else:
        breadth_html = '<div class="snapshot-number na">待回填</div><div class="snapshot-note">stock_daily 当日缺数</div>'
    snapshot = f"""
<div class="snapshot-band" aria-label="画框下方市场快照">
 <div class="snapshot-item">
  <div class="snapshot-label">大盘涨跌幅</div>
  <div class="snapshot-number">{pct_span(s["bench_pct"])}</div>
  <div class="snapshot-note">{s["bench_note"]}</div>
 </div>
 <div class="snapshot-item">
  <div class="snapshot-label">两市总成交额</div>
  {amount_html}
 </div>
 <div class="snapshot-item">
  <div class="snapshot-label">涨跌家数比</div>
  {breadth_html}
 </div>
 <div class="snapshot-item">
  <div class="snapshot-label">涨跌停家数比</div>
  <div class="snapshot-number"><span class="up">{s["limit_up"] if s["limit_up"] is not None else "—"}</span> / <span class="dn">{s["limit_down"] if s["limit_down"] is not None else "—"}</span></div>
  <div class="snapshot-note">全市场统一口径</div>
 </div>
</div>"""

    # ── P0 双卡 ──
    md0 = D["maindays"][0] if D["maindays"] else None
    if md0 and md0["lines"]:
        p0_main_v = " / ".join(L["short"] for L in md0["lines"][:3])
        p0_main_d = f'当日达标 {md0["qualified"]} 条，按容量展示前 {len(md0["lines"])} 条'
        p0_main_sc = THEME_COLOR.get(md0["lines"][0]["short"], "#4fc3f7")
    else:
        p0_main_v, p0_main_d, p0_main_sc = "今日无达标主线", "无板块对大盘有比较优势", "#8aa0c8"
    yt0 = D["ytdays"][0]["sigs"][0] if D["ytdays"] and D["ytdays"][0]["sigs"] else None
    if yt0:
        chain_short = yt0["chain"].split("（")[0]
        p0_gap_v, p0_gap_d = f"新线索：{chain_short}", "看后续价格反应，并用主线强度确认"
    else:
        p0_gap_v, p0_gap_d = "近期无新渊图信号", "等待研报/纪要入图谱"
    p0 = f"""
<div class="p0-strip" aria-label="核心判断">
 <div class="p0-card" style="--sc:{p0_main_sc}">
  <div class="p0-k">P0 · 主线板块</div>
  <div class="p0-v">{p0_main_v}</div>
  <div class="p0-d">{p0_main_d}</div>
 </div>
 <div class="p0-card" style="--sc:#e8c46b">
  <div class="p0-k">P0 · GAP</div>
  <div class="p0-v">{p0_gap_v}</div>
  <div class="p0-d">{p0_gap_d}</div>
 </div>
</div>"""

    # ── 情绪评分卡（含判分依据）+ 容量仪表 ──
    chips = [
        (f"晋级率 {em['jinji']:.0f}%" if em.get("jinji") is not None else "晋级率"),
        (f"涨停 {em['limit_up']}" if em.get("limit_up") is not None else "涨停数"),
        (f"跌停 {em['limit_down']}" if em.get("limit_down") is not None else "跌停数"),
        "涨跌比", "主线宽度 K_day", "成交额 5 日变化",
        (f"涨停次日溢价 {em['premium']:+.1f}%" if em.get("premium") is not None else "涨停次日溢价"),
        (f"连板高度 {em['height']}" if em.get("height") is not None else "连板高度"),
    ]
    chips_html = "".join(f"<span>{c}</span>" for c in chips)
    em_series = json.dumps(em["series"], ensure_ascii=False)
    kt_note = f"；当日 {cap['kday_today']} 为普涨尖峰" if cap["kday_today"] > cap["kday"] + 3 else ""
    state_str = cap["state"] or "—"
    row2 = f"""
<h2>一 · 情绪周期与市场快照 <span class="vintage">emotion_v2 · {em["date"]} ｜ 市场读数环绕情绪周期</span></h2>
<div class="row2">
 <div class="card"><div class="k">情绪评分 60 日 <span class="vintage">粗线=MA5（季节判定口径），细线=当日原始</span></div><div id="emChart"></div>
  <div class="score-basis" aria-label="情绪评分判分依据">
   <div class="score-formula"><b>判分依据</b>：8 个市场情绪变量取 50 日滚动分位后加权平均；跌停数反向计分，连板高度降权。</div>
   <div class="score-vars">{chips_html}</div>
   <div class="score-formula">当日读数：原始 {em["score"]}，水平分位 {em["pct_rank"]}，趋势{em["trend"]}。</div>
  </div></div>
 <div class="card"><div class="k">成交额 × 容量仪表 <span class="vintage">经验非规律</span></div>
  <div class="liquidity-grid">
   <div><b>{amount_str + " 万亿" if amount_str else "待回填"}</b><span>全市场成交额</span></div>
   <div><b>{state_str}</b><span>K {cap["kday"]} / K_cap {cap["kcap"]}</span></div>
  </div>
  <div id="capGauge" class="gauge"></div>
  <div class="sub">K=主线超额>0.5pp 宽度·5日中位{kt_note}；成交额决定容量上限，需结合主线与 GAP 判断持续性。</div></div>
</div>"""

    def us_html_of(u):
        if not u:
            return '<span class="na">无美股锚</span>'
        arrow = "▲" if u["overnight"] > 0 else "▼"
        ucls = "up" if u["overnight"] > 0 else "dn"
        alert = "⚡" if u["alert"] else ""
        kind = "" if u["kind"] == "echo" else '<span class="thermo">温度计</span>'
        return (f'{u["tkr"]} <span class="{ucls}">{arrow}{abs(u["overnight"]):.1f}%</span>{alert} '
                f'<span class="sub">20日超额 {u["ex20"]:+.1f}%</span>{kind}')

    # ── 主线板块 · 近3日 ──
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
        amt = f"{day['amount']:.4f}".rstrip("0").rstrip(".") if day["amount"] else "—"
        main_html += f"""
<div class="mday">
 <div class="mday-h">{day_names[di]} <b>{iso(day["date"])}</b>
  <span class="sub">成交 {amt} 万亿 → K_cap {day["kcap"] or "—"} ｜ {qnote}</span></div>
 <div class="mrow">{cards or empty}</div>
</div>"""

    # ── GAP 判断链（面向使用者的文案，内部口径不外露）──
    yt_all = [g for day in D["ytdays"] for g in day["sigs"]]
    closing_sig = next((g for g in yt_all if g["status"] == "closing"), None)
    closed_sig = next((g for g in yt_all if g["status"] == "closed"), None)
    step1 = (f'最新关注 {yt0["chain"].split("（")[0]}，另有 {max(0, len(D["ytdays"]) - 1)} 个信号日待跟踪'
             if yt0 else "近期无新渊图信号入图谱")
    if closing_sig:
        step2 = f'{closing_sig["chain"].split("（")[0]} 兑现中，继续看行情是否跟随'
    elif closed_sig:
        step2 = f'{closed_sig["chain"].split("（")[0]} 已兑现，关注轮动去向'
    else:
        step2 = "暂无信号进入价格兑现阶段"
    n_kj = len(D["sigdays"][0]["sigs"]) if D["sigdays"] else 0
    step3 = f"{n_kj} 条课件信号参与对照，分层看强弱" if n_kj else "今日无课件信号对照"
    opp_part = "、".join(o["theme"] for o in D["opps"][:2])
    risk_part = "与".join(D["risk_themes"][:2])
    step4 = ((f"{opp_part}偏机会" if opp_part else "暂无机会提示") +
             (f"；{risk_part}需看锚点背离" if risk_part else ""))
    gap_chain = f"""
<div class="gap-chain" aria-label="GAP 判断链">
 <div class="gap-step jump" role="button" tabindex="0" aria-label="跳到渊图信号卡区" onclick="document.getElementById('sec-gap').scrollIntoView({{behavior:'smooth',block:'start'}})" onkeydown="if(event.key==='Enter'||event.key===' '){{event.preventDefault();this.click();}}"><b>新线索</b><span>{step1}</span><span class="jhint">↘</span></div>
 <div class="gap-step jump" role="button" tabindex="0" aria-label="跳到在途未兑现台账" onclick="document.getElementById('sec-ledger').scrollIntoView({{behavior:'smooth',block:'start'}})" onkeydown="if(event.key==='Enter'||event.key===' '){{event.preventDefault();this.click();}}"><b>价格反应</b><span>{step2}</span><span class="jhint">↘</span></div>
 <div class="gap-step jump" role="button" tabindex="0" aria-label="跳到主线板块" onclick="document.getElementById('sec-main').scrollIntoView({{behavior:'smooth',block:'start'}})" onkeydown="if(event.key==='Enter'||event.key===' '){{event.preventDefault();this.click();}}"><b>主线确认</b><span>{step3}</span><span class="jhint">↘</span></div>
 <div class="gap-step jump" role="button" tabindex="0" aria-label="跳到机会/风险提示" onclick="document.getElementById('sec-opp').scrollIntoView({{behavior:'smooth',block:'start'}})" onkeydown="if(event.key==='Enter'||event.key===' '){{event.preventDefault();this.click();}}"><b>机会 / 风险</b><span>{step4}</span><span class="jhint">↘</span></div>
</div>"""

    # ── 渊图信号卡 / 兑现度卡 配对（按产业信号时间分组）──
    sig_names = ["最新信号日", "上一信号日", "再前信号日"]
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
            zh = STATUS_ZH.get(g["status"], g["status"])
            fl = g["fulfill"]
            cards += f"""
<div class="scard glass" style="--sc:{sc}" onclick="openModal('{gid}')">
 <div class="aurora" aria-hidden="true"><div class="neb"></div><div class="stars"></div></div>
 <div class="sc-h"><span class="tag t-{g["status"]}">{zh}</span>
  <span class="lvl" title="渊图置信度">置信度 {g["conf"]:.2f}</span></div>
 <div class="sc-kw">{g["chain"]}</div>
 <div class="sub">{stype}{("｜" + g["theme"]) if g["theme"] else ""}</div>
 <template id="{gid}"><div class="modal-title" style="--sc:{sc}">{g["chain"]}
   <span class="sub">信号时间 {iso(day["date"])} ｜ {stype} ｜ 渊图置信度 {g["conf"]:.2f}</span></div>
  <div><span class="dk">兑现状态</span><span class="tag t-{g["status"]}">{zh}</span>
    <span class="desc">{g["desc"] or ""}</span></div>
  <div><span class="dk">兑现度</span><span class="tag">{fl["v"]}</span>
    <span class="desc">{fl["sent"]}</span></div>
  <div style="margin:13px 0"><span class="dk">受益标的</span><span class="desc">{bene_html(g.get("bene_detail",""), bene)}</span></div>
  <div><span class="dk">小鲍印证</span>{echo}<span class="sub">（第二源回声）</span></div>
  <div><span class="dk">图谱节点</span><span class="sub">{g["node"]}</span></div>
 </template></div>
<div class="fulfill-card glass" style="--sc:{sc};--fulfill:{fl["w"]}%" onclick="openModal('{gid}')" aria-label="兑现度：{fl["v"]}">
 <div class="fulfill-k">兑现度</div>
 <div class="fulfill-v">{fl["v"]}</div>
 <div class="fulfill-bar" aria-hidden="true"><span></span></div>
 <div class="fulfill-d">{fl["d"]}</div>
</div>"""
        empty = '<div class="na" style="padding:8px 0">该信号日无渊图信号</div>'
        label = sig_names[di] if di < len(sig_names) else "信号日"
        sig_html += f"""
<div class="mday">
 <div class="mday-h">{label} <b>{iso(day["date"])}</b>
  <span class="sub">渊图信号 {len(day["sigs"])} 条（按产业信号时间；优先信号自带时间，其次纪要/研报日期）</span></div>
 <div class="mrow">{cards or empty}</div>
</div>"""

    # ── 在途未兑现台账 · 机制 × 信源 矩阵卡（点格弹二级页列该格信号）2026-06-29 ──
    def _mech(stype):
        parts = [x.strip() for x in (stype or "").split(",") if x.strip()]
        if len(set(parts)) == 1:
            return TYPE_ZH.get(parts[0], parts[0])
        return "多机制叠加" if len(parts) >= 2 else "未标注"
    MECHS = ["多机制叠加", "需求爆发", "供给冲击", "持续失衡", "未标注"]
    cells = defaultdict(list)
    for li, g in enumerate(D["inflight"]):
        cells[(_mech(g["stype"]), g.get("plv") or "—")].append((li, g))
    plvs = [p for p in ["P1", "P2", "—"] if any((m, p) in cells for m in MECHS)]
    mechs = [m for m in MECHS if any((m, p) in cells for p in plvs)]
    n_inflight = len(D["inflight"])

    def cid(m, p):
        return "led_" + str(MECHS.index(m)) + "_" + {"P1": "a", "P2": "b", "—": "c"}[p]
    tmpls = ""
    dtmpls = ""   # 三级深详情卡（受益标的等）
    for m in mechs:
        for p in plvs:
            lst = cells.get((m, p), [])
            if not lst:
                continue
            items = ""
            for li, g in lst:
                fl = g["fulfill"]
                zh = STATUS_ZH.get(g["status"], g["status"])
                relit_tag = '<span class="tag" style="color:var(--gold)">二段</span>' if g.get("relit") else ''
                lag = f'{g["lag"]}天' if g["lag"] is not None else '—'
                items += (f'<div class="lm-item" onclick="openModal(\'lmdet_{li}\')"><div class="lm-r1">'
                          f'<span class="lm-chain">{g["chain"]}</span>'
                          f'<span class="lm-st">{relit_tag}<span class="tag t-{g["status"]}">{zh}</span></span>'
                          f'<span class="lm-conf">置信 {g["conf"]:.2f} ›</span></div>'
                          f'<div class="lm-r2">买入 {lag} · {fl["sent"]}</div></div>')
                sc = THEME_COLOR.get(g["theme"], "#8aa0c8")
                stype_zh = "·".join(TYPE_ZH.get(x.strip(), x.strip())
                                    for x in g["stype"].split(",")) if g["stype"] else ""
                bene = "、".join(b.strip() for b in g["bene"].split("/") if b.strip()) or "—（待标的解析）"
                echo_html = ('<span class="tag" style="color:var(--gold)">小鲍同步✓</span>' if g["echo"]
                             else '<span class="tag">小鲍未提及</span>')
                buy_lag = f'产业信号买入：{g["lag"]} 天' if g["lag"] is not None else '产业信号买入：—'
                trend_lag = (f'进入趋势：{g["trend_lag"]} 天' if g.get("trend_lag") is not None
                             else '进入趋势：未触发')
                dtmpls += (f'<template id="lmdet_{li}"><div class="modal-title" style="--sc:{sc}">{g["chain"]}'
                           f'<span class="sub">信号时间 {g["date"]} ｜ {stype_zh} ｜ 渊图置信度 {g["conf"]:.2f}</span></div>'
                           f'<div class="lm-back" onclick="backModal()">← 返回</div>'
                           f'<div><span class="dk">兑现节奏</span><span class="tag">{buy_lag}</span> <span class="tag">{trend_lag}</span></div>'
                           f'<div><span class="dk">兑现状态</span><span class="tag t-{g["status"]}">{zh}</span><span class="desc">{g["desc"] or ""}</span></div>'
                           f'<div><span class="dk">兑现度</span><span class="tag">{fl["v"]}</span><span class="desc">{fl["sent"]}</span></div>'
                           f'<div style="margin:13px 0"><span class="dk">受益标的</span><span class="desc">{bene_html(g.get("bene_detail", ""), bene)}</span></div>'
                           f'<div><span class="dk">小鲍印证</span>{echo_html}<span class="sub">（第二源回声）</span></div>'
                           f'<div><span class="dk">图谱节点</span><span class="sub">{g["node"]}</span></div></template>')
            tmpls += (f'<template id="{cid(m, p)}"><div class="modal-title">{m} × {p}'
                      f'<span class="sub">{len(lst)} 条在途</span></div>{items}</template>')

    def colsum(p):
        return sum(len(cells.get((m, p), [])) for m in mechs)
    # 软卡网格（无表格边框，沿用页面暖色卡片语言）
    gi = ['<div class="led-corner"></div>']
    gi += [f'<div class="led-colh">{p}</div>' for p in plvs] + ['<div class="led-colh">合计</div>']
    for m in mechs:
        gi.append(f'<div class="led-rowh">{m}</div>')
        rsum = 0
        for p in plvs:
            n = len(cells.get((m, p), []))
            rsum += n
            gi.append(f'<div class="led-tile" onclick="openModal(\'{cid(m, p)}\')"><b>{n}</b><span>条</span></div>'
                      if n else '<div class="led-tile empty"><b>·</b></div>')
        gi.append(f'<div class="led-tile sum"><b>{rsum}</b></div>')
    gi.append('<div class="led-rowh">合计</div>')
    gi += [f'<div class="led-tile sum"><b>{colsum(p)}</b></div>' for p in plvs]
    gi.append(f'<div class="led-tile sum total"><b>{n_inflight}</b></div>')
    grid = (f'<div class="led-grid" style="grid-template-columns:auto repeat({len(plvs) + 1},minmax(58px,1fr))">'
            + "".join(gi) + '</div>')
    ledger_html = (f"""
<div class="ledger-wrap" id="sec-ledger">
 <div class="ledger-h">在途未兑现台账 · 机制 × 信源 <span class="sub">{n_inflight} 条 open/closing 信号（同链取最近；点格看该格信号；<span style="color:var(--gold)">二段</span>=点亮中）</span></div>
 {grid}
 {tmpls}{dtmpls}
</div>""" if n_inflight else """
<div class="ledger-wrap" id="sec-ledger"><div class="ledger-h">在途未兑现台账 <span class="sub">当前无窗外在途信号</span></div></div>""")

    # ── 空头风险提示（direction=空 · 卖出/买入转卖出 · 利空逻辑 · 不正向追踪、不计进入趋势）──
    risk = D.get("inflight_risk", [])
    if risk:
        rrows = ""
        for g in risk:
            sc = THEME_COLOR.get(g["theme"], "#d9534f")
            stopped = "已停跟" in (g["desc"] or "")
            badge = "🛑 已停跟(绝对回撤≥5pp)" if stopped else "⚠️ 空头风险·观察中"
            flip = f" ｜ 转卖出日 {iso(g['flip_date'])}" if g.get("flip_date") else ""
            rstype = "·".join(TYPE_ZH.get(x.strip(), x.strip())
                              for x in g["stype"].split(",")) if g.get("stype") else ""
            rstype_seg = f"{rstype} ｜ " if rstype else ""
            rrows += f"""
<div class="ledger-row glass" style="--sc:{sc}">
 <span class="lg-dot" style="background:#d9534f"></span>
 <span class="lg-chain">{g["chain"]}</span>
 <span class="lg-meta">{g["theme"] or "—"} ｜ {rstype_seg}<b style="color:#ff6b6b">产业信号：卖出</b> ｜ {badge} ｜ 信号日 {g["date"]}{flip}</span>
</div>"""
        ledger_html += f"""
<div class="ledger-wrap" id="sec-risk" style="margin-top:14px">
 <div class="ledger-h" style="color:#ff8080">⚠️ 空头风险提示 <span class="sub">{len(risk)} 条 direction=空（卖出/买入转卖出 · 利空逻辑 · 不正向追踪、不计进入趋势）</span></div>
 {rrows}
</div>"""

    # 案2 暗态计数入口（不渲染暗态线本身，仅给一个可感知的入口）
    _dn = D.get("dormant_n", 0)
    dormant_html = (
        f'<div class="dormant-note">🌙 暗态 {_dn} 条（已兑现·候二段 · 不在主栏/台账展示；价格再起达门槛 Y′=4日/回升5pp 自动点亮回二段）</div>'
        if _dn else "")

    # ── 课件信号（第二印证，弱化为「课件信号」）──
    xb_html = ""
    for di, day in enumerate(D["sigdays"]):
        if not day["sigs"]:
            continue
        cards = ""
        for si, g in enumerate(day["sigs"]):
            gid = f"s{di}x{si}"
            sc = THEME_COLOR.get(g["theme"], "#8aa0c8")
            zh = STATUS_ZH.get(g["status"], g["status"])
            lvl_tag = (f'<span class="lvl" title="信息差等级(1-5,越高潜在超额越大)">信息差 {g["lvl"]}/5</span>'
                       if g["lvl"] else "")
            lvl_sub = f' ｜ 信息差等级 {g["lvl"]}/5' if g["lvl"] else ""
            cards += f"""
<div class="scard glass xb" style="--sc:{sc}" onclick="openModal('{gid}')">
 <div class="sc-h"><span class="tag t-{g["status"]}">{zh}</span>
  {lvl_tag}</div>
 <div class="sc-kw">{g["kw"]}</div>
 <div class="sub">{g["theme"]}</div>
 <template id="{gid}"><div class="modal-title" style="--sc:{sc}">{g["kw"]}
   <span class="sub">{iso(day["date"])} ｜ {g["theme_full"]}{lvl_sub} ｜ {g["conf"]}</span></div>
  <div><span class="dk">状态</span><span class="tag t-{g["status"]}">{zh}</span></div>
  <div><span class="dk">兑现定性</span><span class="desc">{g["desc"] or "—"}</span></div>
  <div><span class="dk">信号内容</span><span class="desc">{g["content"][:600]}</span></div>
 </template></div>"""
        xb_html += f"""
<div class="mday">
 <div class="mday-h"><span class="sub">课件信号</span> <b>{iso(day["date"])}</b>
  <span class="sub">{len(day["sigs"])} 条</span></div>
 <div class="mrow">{cards}</div>
</div>"""

    # ── 机会 + 仓位 ──
    opp_html = ""
    for o in D["opps"]:
        tg = "".join(
            f'<span class="chip">{x["name"]}'
            + (f'<em>{x["total"]}·{x["rating"]}</em>' if x.get("total") else "<em>未评分</em>")
            + "</span>" for x in o["targets"]) or '<span class="na">信号无标的字段</span>'
        opp_html += (f'<div class="opp"><div class="opp-h">{o["theme"]} '
                     f'<span class="sub">5日 {o.get("e5", 0):+.1f}% · 20日 {o["e20"]:+.1f}% · {o["note"]}</span></div>'
                     f'<div class="opp-d">{o["desc"] or ""}</div><div class="chips">{tg}</div></div>')
    if not opp_html:
        opp_html = '<div class="na">当日无满足条件（兑现早期×价格启动〔20日未坏+5日转正〕×容量×锚不背离）的机会——诚实空仓提示</div>'

    risk_html = "".join(f'<div class="risk r-{r["lvl"]}">{"🔴" if r["lvl"]=="红" else "🟡"} {r["txt"]}</div>'
                        for r in D["risks"]) or '<div class="na">无自动风险命中</div>'

    pos = D["positions"]
    xbp = (f'{pos["xiaobao"]["band"]}（{pos["xiaobao"]["pref"]}/5）'
           f'<div class="sub">⚠️ 数据 {pos["xiaobao"]["date"]}（课件口径，停更则如实显示）</div>'
           if pos["xiaobao"] else '<span class="na">无数据</span>')
    pos_card = f"""
<div class="card" style="margin-top:10px"><div class="k">仓位 · 三口径并列（不合成）</div>
 <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-top:8px">
  <div><div class="k">小鲍 band（总仓位）</div><div>{xbp}</div></div>
  <div><div class="k">容量状态（能否开新线）</div><div>{state_str}（K {cap["kday"]}/{cap["kcap"]}）</div></div>
  <div><div class="k">龙鱼评级（个股资格）</div><div class="sub">见机会卡片标的 chips 内分数</div></div>
 </div><div class="sub" style="margin-top:6px">{pos["note"]}</div></div>"""

    intl_html = intl_section(D)

    js = (JS_TPL
          .replace("__EM_SERIES__", em_series)
          .replace("__GMAX__", f"{max(8, (cap['kcap'] or 6) + 2):.0f}")
          .replace("__KDAY__", str(cap["kday"]))
          .replace("__KCAP__", str(cap["kcap"] or 0)))

    return f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>烛照九阴日报 · {dd}</title>
{_echarts_inline()}
<style>{css}</style></head><body>
{hero}
{snapshot}
{p0}
{row2}

{intl_html}

<h2 id="sec-main">二 · 主线板块 · 近3日 <span class="vintage">资格=涨幅>1%且对大盘超额>0.5pp（跟涨不算主线）｜ 数量≤当日成交额对应K_cap ｜ 点卡片看详情</span></h2>
{main_html}

<h2 id="sec-gap">三 · GAP 信号栏 <span class="vintage">新线索 / 价格反应 / 主线确认 / 机会风险 ｜ 含在途台账 ｜ 点四步脊跳到对应详情区，点卡片看详情</span></h2>
{gap_chain}
{sig_html}
{ledger_html}
{dormant_html}
{xb_html}

<h2 id="sec-opp">四 · 机会提示 <span class="vintage">候选观察方向，非投资建议</span></h2>
{opp_html}
{pos_card}

<h2>五 · 风险提示 <span class="vintage">{len([r for r in D["risks"] if r["lvl"]=="红"])} 红 / {len([r for r in D["risks"] if r["lvl"]=="黄"])} 黄 ｜ 展开看具体锚与标的</span></h2>
{risk_html}

<div class="foot">烛照九阴 · 数据：recap.db / market_data.db / 龙鱼-标的分析库 ｜ 缺数=诚实标注，禁占位禁编数 ｜ 仓位与标的为体系内信号聚合，非投资建议</div>

<div id="overlay" onclick="backModal()"></div>
<div id="modal" class="glass"><div class="aurora" aria-hidden="true"><div class="neb"></div><div class="stars"></div></div>
 <div id="modalX" onclick="closeModal()">✕</div><div id="modalBody"></div></div>

<script>{js}</script>
</body></html>"""


def main():
    ap = argparse.ArgumentParser(description="烛照九阴 · 暖色日报生成器 v2")
    ap.add_argument("--output", help="输出目录覆盖（测试用；不写正式 AI4ME 目录）")
    ap.add_argument("--no-archive", action="store_true", help="不移动旧报到 archived/")
    ap.add_argument("--no-deploy", action="store_true", help="不部署到 Cowork artifact（仅写 AI4ME 产物）")
    ap.add_argument("--date", help="数据日上限 YYYYMMDD（默认取最新行情日）")
    args = ap.parse_args()

    out_dir = Path(args.output) if args.output else OUT_DIR
    is_official = (out_dir.resolve() == OUT_DIR.resolve()) if OUT_DIR.exists() else not args.output
    out_dir.mkdir(parents=True, exist_ok=True)

    D = gather(date_cap=args.date)
    html = render(D)
    fname = f"烛照九阴日报_{D['data_day']}.html"

    if is_official and not args.no_archive:
        (out_dir / "archived").mkdir(exist_ok=True)
        # 旧报移 archived/（永不删，删除权归 Doctor）
        for old in out_dir.glob("烛照九阴日报_*.html"):
            if old.name != fname:
                shutil.move(str(old), str(out_dir / "archived" / old.name))
                logger.info(f"📦 旧报归档 → archived/{old.name}")
    out = out_dir / fname
    if is_official and out.exists():
        # 同名旧报先存档再覆盖（永不删，删除权归 Doctor）
        (out_dir / "archived").mkdir(exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        keep = out_dir / "archived" / f"{out.stem}.pre-{stamp}{out.suffix}"
        shutil.move(str(out), str(keep))
        logger.info(f"📦 同名旧报存档 → archived/{keep.name}")
    out.write_text(html, encoding="utf-8")
    mode = "正式" if is_official else "测试"
    logger.info(f"✅ 日报生成（{mode}·暖色范式 v2）→ {out}（{out.stat().st_size/1048576:.2f} MB）")
    logger.info(f"   主线 {len(D['themes'])} 条 | 渊图信号日 {len(D['ytdays'])} | 机会 {len(D['opps'])} | 风险 {len(D['risks'])}")

    # 重渲即部署：正式产物自动同步到 Cowork artifact（测试 --output 或 --no-deploy 跳过）
    if is_official and not args.no_deploy:
        _deploy_to_artifact(html, D['data_day'])


if __name__ == "__main__":
    main()
