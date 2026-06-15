#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import config
from lib.logger import get_logger
logger = get_logger(__name__)
"""
migrate_stock_tracking_backtest.py — stock_tracking 扩列（标的级胜率回测轨）
PRD: brain/logs/checkpoints/2026-06-15_标的级胜率回测_PRD.md

幂等：已存在的列跳过。只 ADD COLUMN，绝不改/删既有列与其它表。
复用既有列作绝对收益：next_day_return / next_3d_return / next_5d_return /
next_10d_return / max_return / max_drawdown（已在表中）。

用法:
  python3 tools/migrate_stock_tracking_backtest.py --dry-run
  python3 tools/migrate_stock_tracking_backtest.py
  python3 tools/migrate_stock_tracking_backtest.py --recap-db /tmp/recap_test.db
"""
import sqlite3, argparse

# 新增列（绝对收益复用既有 next_*_return / max_*，此处不重复加）
NEW_COLS = [
    ("target_pool", "TEXT"),       # own / dim4_xiaobao
    ("signal_table", "TEXT"),      # 来源表
    ("signal_id", "INTEGER"),      # 来源行 id
    ("info_gap_level", "INTEGER"),
    ("logic_type", "TEXT"),
    ("resolve_status", "TEXT"),    # resolved / unresolved
    ("excess_1d", "REAL"),
    ("excess_3d", "REAL"),
    ("excess_5d", "REAL"),
    ("excess_10d", "REAL"),
    ("hit_3d", "INTEGER"),         # excess_3d>0 → 1
    ("bench_code", "TEXT"),
]


def main():
    ap = argparse.ArgumentParser(description="stock_tracking 扩列")
    ap.add_argument("--recap-db", default=config.RECAP_DB)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    con = sqlite3.connect(args.recap_db)
    cur = con.cursor()
    existing = {r[1] for r in cur.execute("PRAGMA table_info(stock_tracking)")}
    if not existing:
        logger.error("stock_tracking 表不存在，中止"); con.close(); _sys.exit(2)

    todo = [(c, t) for c, t in NEW_COLS if c not in existing]
    print(f"stock_tracking 现有 {len(existing)} 列；待加 {len(todo)} 列：{[c for c,_ in todo]}")
    if args.dry_run:
        print("[dry-run] 未改表。"); con.close(); return
    for c, t in todo:
        cur.execute(f'ALTER TABLE stock_tracking ADD COLUMN "{c}" {t}')
    con.commit()
    now = {r[1] for r in cur.execute("PRAGMA table_info(stock_tracking)")}
    con.close()
    print(f"✅ 扩列完成，现 {len(now)} 列。新列齐：{all(c in now for c,_ in NEW_COLS)}")


if __name__ == "__main__":
    main()
