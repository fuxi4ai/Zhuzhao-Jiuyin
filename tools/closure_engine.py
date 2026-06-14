#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""兑现检测引擎（closure engine）——「发现产业逻辑：买入 → 市场兑现」自动判定
（CC 2026-06-10；方案见 docs/兑现检测引擎-dryrun方案-20260610.md，Doctor 已批口径）

状态机（ETF 级，主线锚定）：
  open    → closing : 发现日后，主线代表 ETF 对 510300 超额连续为正 ≥ Y=3 日
                      （streak 首日 = date_realized）
  closing → closed  : 累计超额峰值 peak ≥ X=5% 且 绝对回撤 peak−cum ≥ 5pp
                      （Doctor 2026-06-10 拍板：绝对回撤，防小峰值相对回撤误触）

双轨铁律：ETF 级只回答「市场是否兑现该主线」；标的级 verify_return 独立字段，
          两轨不互相覆盖，背离样本（板块兑现但标的没赚）标 divergent。

用法：
  python3 tools/closure_engine.py --dry-run            # 全量判定 → 审核 TSV，不写库
  python3 tools/closure_engine.py --apply              # 先 .bak 再加列+回填（需先过 dry-run）
  python3 tools/closure_engine.py --dry-run --table yuantu   # 只跑 yuantu_buy_signals
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import sqlite3, argparse, shutil, datetime, csv
from collections import defaultdict
import config
from lib.logger import get_logger
logger = get_logger(__name__)

# 主线→ETF 单一可信源：复用 fetch_theme_etf 的字典，绝不二抄
_sys.path.insert(0, str(config.PROJECT_ROOT / "scripts"))
from fetch_theme_etf import THEME_ETF, BENCHMARK

# ── 口径常量（Doctor 2026-06-10 拍板）─────────────────────────────
Y_STREAK = 3        # open→closing：连续超额为正天数
X_PEAK = 0.05       # closed 前提：累计超额峰值下限
DD_ABS = 0.05       # closing→closed：绝对回撤 5pp
WINDOW = 120        # 信号后观察窗口（交易日）

# ── sector_alias canonical → THEME_ETF 键 ────────────────────────
CANON2THEME = {
    "光模块": "光模块/CPO/光通信/光纤", "CPO": "光模块/CPO/光通信/光纤",
    "光纤": "光模块/CPO/光通信/光纤", "光模块/CPO": "光模块/CPO/光通信/光纤",
    "半导体": "半导体/芯片/半导体材料",
    "机器人": "机器人", "光伏": "光伏",
    "新能源电池": "新能源电池/锂电/储能/固态", "固态电池": "新能源电池/锂电/储能/固态",
    "电力": "电力/电网/算电协同/燃气轮机",
    "医药": "创新药/医药/CRO", "军工": "军工", "商业航天": "商业航天/卫星",
    "消费电子": "消费电子/华为/鸿蒙", "AI软件/应用": "AI软件/应用",
    "白酒": "白酒/消费", "金融": "券商/金融",
    "AI算力": "AI算力/AI硬件/科技硬件", "AI硬件": "AI算力/AI硬件/科技硬件",
    # 无 ETF 锚（覆盖洞）→ None = no_anchor 降级
    "中东/能源": None, "煤化工": None,
}
# 引擎补充词典（sector_alias 覆盖不到的渊图链路术语；命中标 tier=hint，待九儿审入 alias 表）
ENGINE_HINTS = {
    "光模块/CPO/光通信/光纤": ["激光器", "磷化铟", "InP", "FAU", "铌酸锂", "光器件",
                              "光通信", "DSP", "DCI", "光纤", "硅光", "光检测", "光学"],
    "AI算力/AI硬件/科技硬件": ["PCB", "铜箔", "服务器", "CPU", "GPU", "HBM", "存储",
                              "英伟达", "Rubin", "TPU", "算力", "MLCC", "基板", "钽粉",
                              "铜缆", "液冷", "数据中心", "晶圆", "封测"],
    "半导体/芯片/半导体材料": ["芯片", "海光", "昇腾", "出口管制", "光刻", "代工"],
    "电力/电网/算电协同/燃气轮机": ["电气设备", "电网", "变压器", "燃气轮机", "HVDC"],
    # 大宗/金属（Doctor 2026-06-10 补锚）
    "黄金/贵金属": ["黄金", "白银", "贵金属", "金价", "黄金白银"],
    "稀土": ["稀土", "永磁", "钕铁硼"],
    "钨/小金属": ["钨", "钼", "锗", "锑", "铼", "小金属", "稀有金属"],
    "有色金属": ["有色", "铝", "铜", "锌", "金属"],
    "光伏": ["晶科", "隆基", "组件", "硅片"],
}


def load_alias(rc):
    """sector_alias → [(alias, theme)] 按 alias 长度降序（最长匹配优先）"""
    pairs = []
    for canon, aliases in rc.execute("SELECT canonical_name, aliases FROM sector_alias"):
        theme = CANON2THEME.get(canon, "__UNKNOWN__")
        if theme == "__UNKNOWN__":
            continue
        for a in {canon, *(x.strip() for x in (aliases or "").split(",") if x.strip())}:
            pairs.append((a, theme, "alias"))
    for theme, words in ENGINE_HINTS.items():
        pairs.extend((w, theme, "hint") for w in words)
    return sorted(pairs, key=lambda t: -len(t[0]))


# 金融主线只认 keyword 命中——正文里的「券商/银行」几乎都是信源描述
# （"【信息差】券商研报""券商渠道反馈""传导到银行"），不是板块（2026-06-10 假阳性修正）
KEYWORD_ONLY_THEMES = {"券商/金融"}


def map_theme(kw_text, content_text, alias_pairs):
    """匹配优先级（2026-06-10 修正「晶科能源」被降级词「能源」子串劫持）：
    ① keyword×有锚词 → ② keyword×降级词(None,如中东/能源) → ③ 正文×有锚词(金融除外) → ④ 未命中"""
    anchored = [(a, t, tier) for a, t, tier in alias_pairs if t is not None]
    downgrade = [(a, t, tier) for a, t, tier in alias_pairs if t is None]
    for a, theme, tier in anchored:
        if a and a in kw_text:
            return theme, tier
    for a, _t, tier in downgrade:
        if a and a in kw_text:
            return None, "downgrade"          # 故意无锚（覆盖洞主线）
    for a, theme, tier in anchored:
        if theme in KEYWORD_ONLY_THEMES:
            continue
        if a and a in content_text:
            return theme, tier
    return None, "unmatched"


# ── 行情：theme → 日超额序列 ─────────────────────────────────────
# ⚠️ GOTCHA：fund_daily 为**未复权价**，份额折算/分红会污染 close 环比
# （实例：516780 于 20260525 折算 close −49.8% 而真实 +0.3%；基准 510300 亦有
#   250618/260119 两处污点）。日收益一律用 pct_chg，禁止 close 环比。
def load_excess(md):
    px = defaultdict(dict)
    for d, code, pc in md.execute(
            "SELECT trade_date, etf_code, pct_chg FROM theme_etf_daily "
            "WHERE pct_chg IS NOT NULL ORDER BY trade_date"):
        px[code][d] = pc / 100.0
    dates = sorted(px[BENCHMARK].keys())

    def rets(code):
        return px[code]

    bench = rets(BENCHMARK)
    excess = {}
    for theme, codes in THEME_ETF.items():
        rs = [rets(c) for c in codes]
        ex = {}
        for d in dates:
            if d not in bench:
                continue
            vals = [r[d] for r in rs if d in r]
            if vals:
                ex[d] = sum(vals) / len(vals) - bench[d]
        excess[theme] = ex
    return dates, excess


def run_machine(ex, dates, disc):
    """状态机：返回 dict(gap_status, date_realized, excess_cum/peak, closed_date, gap_desc)"""
    ds = [d for d in dates if d > disc and d in ex][:WINDOW]
    cum = peak = 0.0
    streak = 0
    realized = closed = None
    streak_start = None
    seen = 0          # closed 前实际走过的交易日数
    for d in ds:
        seen += 1
        cum += ex[d]
        if ex[d] > 0:
            if streak == 0:
                streak_start = d
            streak += 1
        else:
            streak = 0
        if realized is None and streak >= Y_STREAK:
            realized = streak_start
        peak = max(peak, cum)
        if realized and peak >= X_PEAK and (peak - cum) >= DD_ABS:
            closed = d
            break
    status = "closed" if closed else ("closing" if realized else "open")
    days_run = sum(1 for d in ds[:seen] if realized and d >= realized)
    return dict(gap_status=status, date_realized=realized,
                excess_cum=round(cum, 4), excess_peak=round(peak, 4),
                closed_date=closed, n_days=len(ds),
                gap_desc=describe(status, len(ds), seen, days_run, cum, peak))


def describe(status, n_days, seen, days_run, cum, peak):
    """缺口定性（人话一列，Doctor 2026-06-10 要求）"""
    pc = lambda v: f"{v*100:+.1f}%"
    if status == "open":
        if n_days == 0:
            return "刚发现·行情待走"
        if n_days <= 10:
            return f"潜伏期（发现{n_days}日未启动）"
        if n_days > 30:
            return f"⚠️逾期未启动（{n_days}日，累计{pc(cum)}）——逻辑存疑或锚不对"
        return f"未启动（{n_days}日，累计{pc(cum)}）"
    if status == "closing":
        if days_run <= 5:
            return f"兑现初期（启动{days_run}日，累计{pc(cum)}）"
        if cum >= 0.10:
            return f"主升兑现中（{days_run}日，累计{pc(cum)}，峰值{pc(peak)}）"
        if peak - cum >= 0.03:
            return f"兑现中·回撤近警戒（峰值{pc(peak)}→现{pc(cum)}）"
        return f"兑现进行（{days_run}日，累计{pc(cum)}）"
    # closed
    tail = "（窗口内走完）" if seen < n_days or seen < WINDOW else "（满窗）"
    if cum < peak * 0.3:
        return f"兑现完毕·深回吐（峰值{pc(peak)}→{pc(cum)}，{seen}日）已轮动{tail}"
    return f"兑现完毕（峰值{pc(peak)}，历时{seen}日）已轮动{tail}"


# ── 信号装载 ─────────────────────────────────────────────────────
def norm_date(s):
    """'2026-05-26'→'20260526'；'2026-01'(仅月)→'20260115'+precision=month"""
    s = (s or "").strip()
    p = s.replace("-", "")
    if len(p) == 8:
        return p, "day"
    if len(p) == 6:
        return p + "15", "month"
    return None, "bad"


def load_signals(rc, which):
    sigs = []
    if which in ("all", "industry"):
        for sid, dt, kw, content in rc.execute(
                "SELECT id, date, keyword, signal_content FROM industry_signals"):
            d, prec = norm_date(dt)
            sigs.append(dict(table="industry_signals", id=sid, disc=d, prec=prec,
                             kw_text=kw or "", content_text=content or "",
                             label=(kw or "")[:40]))
    if which in ("all", "yuantu"):
        for sid, node, dt, chain in rc.execute(
                "SELECT id, signal_node, date, industry_chain FROM yuantu_buy_signals"):
            d, prec = norm_date(dt)
            sigs.append(dict(table="yuantu_buy_signals", id=sid, disc=d, prec=prec,
                             kw_text=f"{node or ''} {chain or ''}", content_text="",
                             label=node[:40]))
    return sigs


# ── apply：加列 + 回填 ───────────────────────────────────────────
APPLY_COLS = [("gap_status", "TEXT"), ("date_realized", "TEXT"),
              ("etf_anchor", "TEXT"), ("excess_cum", "REAL"),
              ("excess_peak", "REAL"), ("closed_date", "TEXT"),
              ("gap_desc", "TEXT")]


def ensure_cols(rc, table):
    have = {r[1] for r in rc.execute(f"PRAGMA table_info({table})")}
    for col, typ in APPLY_COLS:
        if col not in have:
            rc.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
            logger.info(f"  + {table}.{col} {typ}")


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    ap.add_argument("--table", choices=["all", "industry", "yuantu"], default="all")
    args = ap.parse_args()

    md = sqlite3.connect(f"file:{config.MARKET_DB}?mode=ro", uri=True)
    rc = sqlite3.connect(config.RECAP_DB if args.apply
                         else f"file:{config.RECAP_DB}?mode=ro",
                         uri=not args.apply)

    if args.apply:  # 铁律：动库先备份
        bak = config.RECAP_DB + f".bak_{datetime.date.today():%Y%m%d}_closure"
        shutil.copy2(config.RECAP_DB, bak)
        logger.info(f"📦 备份 → {bak}")

    dates, excess = load_excess(md)
    alias_pairs = load_alias(rc)
    sigs = load_signals(rc, args.table)
    logger.info(f"信号 {len(sigs)} 条 · 行情 {dates[0]}→{dates[-1]} · 主线 {len(THEME_ETF)}")

    out, stats = [], defaultdict(int)
    for s in sigs:
        if not s["disc"]:
            stats["bad_date"] += 1
            continue
        theme, tier = map_theme(s["kw_text"], s["content_text"], alias_pairs)
        if theme is None:
            stats["no_anchor"] += 1
            out.append({**s, "theme": "", "tier": tier, "gap_status": "no_anchor",
                        "date_realized": "", "excess_cum": "", "excess_peak": "",
                        "closed_date": "", "gap_desc": "无锚未跟踪（情绪周期类或覆盖洞）"})
            continue
        if not excess.get(theme):   # 锚已定义但行情未回填（如新补的大宗ETF）
            stats["no_data"] += 1
            out.append({**s, "theme": theme, "tier": tier, "gap_status": "no_data",
                        "date_realized": "", "excess_cum": "", "excess_peak": "",
                        "closed_date": "", "gap_desc": "锚行情未回填"})
            continue
        r = run_machine(excess[theme], dates, s["disc"])
        stats[r["gap_status"]] += 1
        stats[f"tier_{tier}"] += 1
        out.append({**s, "theme": theme, "tier": tier, **r})

    rpt = config.PROJECT_ROOT / "docs" / \
        f"兑现检测_审核表_{datetime.date.today():%Y%m%d}.tsv"
    cols = ["table", "id", "label", "disc", "prec", "theme", "tier",
            "gap_status", "gap_desc", "date_realized", "excess_cum",
            "excess_peak", "closed_date"]
    with open(rpt, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        w.writerows(out)
    logger.info(f"📄 审核表 → {rpt}")
    logger.info("📊 " + " | ".join(f"{k}={v}" for k, v in sorted(stats.items())))

    if args.apply:
        for table in {"industry_signals", "yuantu_buy_signals"}:
            ensure_cols(rc, table)
        n = 0
        for r in out:
            # no_anchor 也回写——否则映射纠错后旧锚残留库中（2026-06-10 教训）
            rc.execute(
                f"UPDATE {r['table']} SET gap_status=?, date_realized=?, etf_anchor=?,"
                f" excess_cum=?, excess_peak=?, closed_date=?, gap_desc=? WHERE id=?",
                (r["gap_status"], r["date_realized"], r["theme"],
                 r["excess_cum"] or None, r["excess_peak"] or None,
                 r["closed_date"], r["gap_desc"], r["id"]))
            n += 1
        rc.commit()
        logger.info(f"✅ 回填 {n} 条（no_anchor/坏日期未写）")
    else:
        logger.info("🔍 dry-run 完成，未写库。过目审核表后 --apply。")


if __name__ == "__main__":
    main()
