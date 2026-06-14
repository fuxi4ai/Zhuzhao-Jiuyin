#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""美元:人民币汇率拉取 → 公共 market_data.db.fx_daily（附加表，不动句芒既有表）
（CC 2026-06-10；可视化日报 PRD 区块1 数据源，Doctor 终端跑，已批）

口径：USDCNH.FXCM（离岸，日频连续性好）为主；USDCNY 在岸若可取一并存，缺则只存离岸。
来源：tushare `fx_daily`。

用法：
  python3 scripts/fetch_fx.py --from 20250101     # 回填/增量（幂等）
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from lib.logger import get_logger
logger = get_logger(__name__)
import sqlite3, argparse, time
import config

CODES = ["USDCNH.FXCM"]   # 主口径离岸；如需在岸再加


def get_pro():
    import tushare as ts
    tok = _os.environ.get("TUSHARE_TOKEN")
    if not tok:
        try:
            import subprocess
            tok = subprocess.check_output(
                ["security", "find-generic-password", "-s", "tushare_pro", "-w"],
                text=True).strip()
        except Exception:
            pass
    if not tok:
        p = _os.path.expanduser("~/.tushare/token")
        if _os.path.exists(p):
            tok = open(p).read().strip()
    if not tok:
        raise RuntimeError("未找到 TUSHARE_TOKEN")
    ts.set_token(tok)
    return ts.pro_api()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="from_date", required=True)
    ap.add_argument("--to", dest="to_date", default=time.strftime("%Y%m%d"))
    args = ap.parse_args()

    pro = get_pro()
    conn = sqlite3.connect(config.MARKET_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fx_daily (
            trade_date TEXT,
            ts_code    TEXT,
            bid_close  REAL,
            ask_close  REAL,
            mid_close  REAL,    -- (bid+ask)/2，日报展示用
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (trade_date, ts_code)
        )
    """)
    total = 0
    for c in CODES:
        df = pro.fx_daily(ts_code=c, start_date=args.from_date, end_date=args.to_date)
        if df is None or df.empty:
            logger.warning(f"  - {c}: 无数据")
            continue
        rows = [(r.trade_date, c, float(r.bid_close), float(r.ask_close),
                 round((float(r.bid_close) + float(r.ask_close)) / 2, 4))
                for r in df.itertuples()]
        conn.executemany(
            "INSERT OR REPLACE INTO fx_daily"
            "(trade_date,ts_code,bid_close,ask_close,mid_close) VALUES (?,?,?,?,?)",
            rows)
        conn.commit()
        total += len(rows)
        logger.info(f"  ✓ {c}: {len(rows)} 行")
        time.sleep(0.3)
    logger.info(f"✅ 写入 {total} 行 → market_data.db.fx_daily")
    conn.close()


if __name__ == "__main__":
    main()
