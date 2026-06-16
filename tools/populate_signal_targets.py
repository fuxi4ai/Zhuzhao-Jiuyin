#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os as _os, sys as _sys
_TOOLS = _os.path.dirname(_os.path.abspath(__file__))
_sys.path.insert(0, _TOOLS)
_sys.path.insert(0, _os.path.dirname(_TOOLS))
import config
from lib.logger import get_logger
logger = get_logger(__name__)
import ticker_resolver  # 复用项目名→ts_code 解析器
import logic_taxonomy  # logic_type 中英变体 → canon 单一真源（写时归一·源表不动）
"""
populate_signal_targets.py — 把每日信号炸开成标的级回测记录（两池隔离）
PRD: brain/logs/checkpoints/2026-06-15_标的级胜率回测_PRD.md

两池（绝不混）：
  own         = industry_signals(全 gap·target 逗号串) + yuantu_buy_signals(beneficiaries_ts 已带码)
  dim4_xiaobao = dim4_stock_analysis(小鲍逐股·有名无码→反查)

落 stock_tracking；name→ts_code 走 ticker_resolver，解析不到记 resolve_status='unresolved'
（单列、回测时不计入任一池胜率分母）。幂等：每次先删本脚本管理的行（target_pool 非空）再重灌。

用法:
  python3 tools/populate_signal_targets.py --dry-run
  python3 tools/populate_signal_targets.py
  python3 tools/populate_signal_targets.py --recap-db /tmp/recap_test.db
"""
import sqlite3, argparse, re

_SPLIT = re.compile(r"[,，、;；/]| / ")


def _names(target):
    if not target:
        return []
    return [x.strip() for x in _SPLIT.split(str(target)) if x.strip()]


def _parse_yuantu_ts(s):
    """'中际旭创:300308.SZ / 沪电股份（PCB）:002463.SZ' → [(name, code), ...]（code 可能 None）"""
    out = []
    if not s:
        return out
    for part in re.split(r"\s*/\s*", str(s)):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            nm, code = part.rsplit(":", 1)
            code = code.strip()
            code = code if re.search(r"\d{6}\.(SH|SZ|BJ)", code) else None
            out.append((nm.strip(), code))
        else:
            out.append((part, None))
    return out


def collect(con):
    """返回 (rows, stats)。rows = list of dict（待插入 stock_tracking）。"""
    cur = con.cursor()
    rows, stats = [], {}

    def add(pool, table, sid, date, name, code, sector, reason, conf, gap, logic, source):
        rs = "resolved" if code else "unresolved"
        logic = logic_taxonomy.normalize(logic)  # 中英变体 → canon（缺失保持 None）
        rows.append(dict(
            target_pool=pool, signal_table=table, signal_id=sid, signal_date=date,
            stock_name=name, stock_code=code or "", sector=sector or "",
            bull_reason=(reason or "")[:300], source=source or "",
            initial_confidence=str(conf) if conf is not None else "",
            info_gap_level=gap, logic_type=logic, resolve_status=rs,
            current_status="pending"))

    # ── 自有池 1：industry_signals（target 逗号串，逐名 resolve）──
    n_is, r_is = 0, 0
    for sid, date, target, gap, logic, content, owner in cur.execute(
            "SELECT id,date,target,info_gap_level,logic_type,signal_content,viewpoint_owner "
            "FROM industry_signals WHERE target IS NOT NULL AND target<>''"):
        for nm in _names(target):
            code = ticker_resolver.resolve(nm)
            add("own", "industry_signals", sid, date, nm, code, None, content, None,
                gap, logic, owner or "小鲍")
            n_is += 1; r_is += 1 if code else 0
    stats["industry_signals"] = (n_is, r_is)

    # ── 自有池 2：yuantu_buy_signals（beneficiaries_ts 已带码，缺码再 resolve）──
    n_y, r_y = 0, 0
    for sid, date, bts, stype, conf in cur.execute(
            "SELECT id,date,beneficiaries_ts,signal_type,yuantu_confidence FROM yuantu_buy_signals"):
        for nm, code in _parse_yuantu_ts(bts):
            if not code:
                code = ticker_resolver.resolve(nm)
            add("own", "yuantu_buy_signals", sid, date, nm, code, None, None, conf,
                None, (stype or "").split(",")[0] or None, "渊图")
            n_y += 1; r_y += 1 if code else 0
    stats["yuantu_buy_signals"] = (n_y, r_y)

    # ── dim4 池：dim4_stock_analysis（有名无码→反查）──
    n_d, r_d = 0, 0
    for rid, date, name, code, sector, conf, bull in cur.execute(
            "SELECT rowid,date,stock_name,stock_code,sector,confidence,bull_reason "
            "FROM dim4_stock_analysis WHERE stock_name IS NOT NULL AND stock_name<>''"):
        code = code if (code and re.search(r"\d{6}", str(code))) else ticker_resolver.resolve(name)
        add("dim4_xiaobao", "dim4_stock_analysis", rid, date, name, code, sector, bull, conf,
            None, None, "小鲍")
        n_d += 1; r_d += 1 if code else 0
    stats["dim4_stock_analysis"] = (n_d, r_d)
    return rows, stats


COLS = ["target_pool", "signal_table", "signal_id", "signal_date", "stock_name",
        "stock_code", "sector", "bull_reason", "source", "initial_confidence",
        "info_gap_level", "logic_type", "resolve_status", "current_status"]


def main():
    ap = argparse.ArgumentParser(description="炸开信号入 stock_tracking（两池）")
    ap.add_argument("--recap-db", default=config.RECAP_DB)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    con = sqlite3.connect(args.recap_db)
    if "target_pool" not in {r[1] for r in con.execute("PRAGMA table_info(stock_tracking)")}:
        logger.error("stock_tracking 未扩列，先跑 migrate_stock_tracking_backtest.py"); con.close(); _sys.exit(2)

    rows, stats = collect(con)
    print("=== 炸开标的（两池）· resolve 成功/总数 ===")
    own = [("industry_signals", "自有"), ("yuantu_buy_signals", "自有"), ("dim4_stock_analysis", "dim4")]
    for tbl, pool in own:
        n, r = stats[tbl]
        print(f"  [{pool:<4}] {tbl:<22} {r}/{n} resolved（{(r/n*100 if n else 0):.0f}%）")
    own_n = sum(stats[t][0] for t in ("industry_signals", "yuantu_buy_signals"))
    own_r = sum(stats[t][1] for t in ("industry_signals", "yuantu_buy_signals"))
    print(f"  自有池合计 {own_r}/{own_n} · dim4 池 {stats['dim4_stock_analysis'][1]}/{stats['dim4_stock_analysis'][0]}")

    if args.dry_run:
        print(f"[dry-run] 待插 {len(rows)} 行，未写库。"); con.close(); return

    # 既有 UNIQUE(signal_date, stock_name) → 一股一日一行（同股同日未来收益唯一，本就不该重复计）。
    # 去重优先级：own > dim4（重叠归自有）；own 内取最高 info_gap_level。
    bypair = {}
    for r in rows:
        bypair.setdefault((r["signal_date"], r["stock_name"]), set()).add(r["target_pool"])
    overlap = sum(1 for v in bypair.values() if len(v) > 1)

    def rank(r):
        gap = r.get("info_gap_level")
        return (0 if r["target_pool"] == "own" else 1, -(gap if gap is not None else -1))
    seen, dedup = set(), []
    for r in sorted(rows, key=rank):
        k = (r["signal_date"], r["stock_name"])
        if k in seen:
            continue
        seen.add(k); dedup.append(r)

    cur = con.cursor()
    # 幂等：删本脚本管理的行（target_pool 非空），保留任何遗留手录行（target_pool IS NULL）
    cur.execute("DELETE FROM stock_tracking WHERE target_pool IS NOT NULL")
    ph = ", ".join("?" for _ in COLS)
    cur.executemany(
        f'INSERT OR IGNORE INTO stock_tracking ({", ".join(COLS)}) VALUES ({ph})',
        [[r.get(c) for c in COLS] for r in dedup])
    con.commit()
    print(f"  去重：{len(rows)}→{len(dedup)} 行（一股一日一行·own 优先）；跨池重叠 {overlap} 例（归 own）")
    tot = cur.execute("SELECT COUNT(*) FROM stock_tracking WHERE target_pool IS NOT NULL").fetchone()[0]
    pools = dict(cur.execute("SELECT target_pool, COUNT(*) FROM stock_tracking GROUP BY target_pool"))
    unres = cur.execute("SELECT COUNT(*) FROM stock_tracking WHERE resolve_status='unresolved'").fetchone()[0]
    con.close()
    print(f"✅ 写入 {tot} 行 · 分池 {pools} · 未解析 {unres} 行（不计胜率分母）")


if __name__ == "__main__":
    main()
