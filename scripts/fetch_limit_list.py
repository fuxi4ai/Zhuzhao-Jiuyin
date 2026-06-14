#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""涨跌停个股明细拉取 → 公共 market_data.db.limit_list_daily（附加表，不动句芒既有表）
（CC 2026-06-10；情绪周期重算 #4 已批：解锁晋级率成分 + 修复涨停口径断裂 GOTCHA）

来源：tushare `limit_list_d`（打板专题）。字段含 limit 类型（U涨停/D跌停/Z炸板）、
      limit_times 连板数、open_times 开板次数——晋级率 = 昨日涨停股今日连板占比，由此表自算。

用法：
  python3 scripts/fetch_limit_list.py --from 20251001            # 回填（按交易日循环）
  python3 scripts/fetch_limit_list.py --from 20260609            # 增量
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from lib.logger import get_logger
logger = get_logger(__name__)
import sqlite3, argparse, time
import config


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


def ensure_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS limit_list_daily (
            trade_date  TEXT,
            ts_code     TEXT,
            name        TEXT,
            limit_type  TEXT,     -- U涨停 / D跌停 / Z炸板
            limit_times INTEGER,  -- 连板数
            open_times  INTEGER,  -- 开板次数
            pct_chg     REAL,
            amount      REAL,
            first_time  TEXT,
            last_time   TEXT,
            updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (trade_date, ts_code)
        )
    """)
    conn.commit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="from_date", required=True)
    ap.add_argument("--to", dest="to_date", default=time.strftime("%Y%m%d"))
    args = ap.parse_args()

    pro = get_pro()
    conn = sqlite3.connect(config.MARKET_DB)
    ensure_table(conn)
    # 交易日历：复用 market_amount_daily（已回填 20250102→今）
    days = [r[0] for r in conn.execute(
        "SELECT trade_date FROM market_amount_daily "
        "WHERE trade_date BETWEEN ? AND ? ORDER BY trade_date",
        (args.from_date, args.to_date))]
    have = {r[0] for r in conn.execute(
        "SELECT DISTINCT trade_date FROM limit_list_daily")}
    todo = [d for d in days if d not in have or d == args.to_date]
    logger.info(f"交易日 {len(days)}，已入库跳过 {len(days)-len(todo)}，待拉 {len(todo)}")
    total, failed = 0, []
    for i, d in enumerate(todo):
        df = None
        for attempt in range(3):          # 网络/代理闪断重试
            try:
                df = pro.limit_list_d(trade_date=d)
                break
            except Exception as e:
                if attempt < 2:
                    wait = (attempt + 1) * 5
                    logger.warning(f"  ⟳ {d} 第{attempt+1}次失败({str(e)[:60]})，{wait}s 后重试")
                    time.sleep(wait)
                else:
                    logger.error(f"  ✗ {d}: 3 次均失败，记入补漏清单")
                    failed.append(d)
        if df is None or df.empty:
            continue
        def _i(v):   # NaN/None 安全转 int
            try:
                import math
                return 0 if v is None or (isinstance(v, float) and math.isnan(v)) else int(v)
            except (ValueError, TypeError):
                return 0

        def _f(v):
            try:
                import math
                return None if v is None or (isinstance(v, float) and math.isnan(v)) else float(v)
            except (ValueError, TypeError):
                return None

        rows = [(r.trade_date, r.ts_code, getattr(r, "name", None),
                 getattr(r, "limit", None),
                 _i(getattr(r, "limit_times", None)),
                 _i(getattr(r, "open_times", None)),
                 _f(getattr(r, "pct_chg", None)),
                 _f(getattr(r, "amount", None)),
                 getattr(r, "first_time", None), getattr(r, "last_time", None))
                for r in df.itertuples()]
        conn.executemany(
            "INSERT OR REPLACE INTO limit_list_daily"
            "(trade_date,ts_code,name,limit_type,limit_times,open_times,"
            "pct_chg,amount,first_time,last_time) VALUES (?,?,?,?,?,?,?,?,?,?)",
            rows)
        conn.commit()
        total += len(rows)
        if (i + 1) % 50 == 0:
            logger.info(f"  …{i+1}/{len(todo)} 日，累计 {total} 行")
        time.sleep(0.15)   # 限频友好
    logger.info(f"✅ 完成，写入 {total} 行 → market_data.db.limit_list_daily")
    if failed:
        logger.warning(f"⚠️ {len(failed)} 日未取到，重跑同一命令自动补漏: {failed[:10]}{'…' if len(failed)>10 else ''}")
    conn.close()


if __name__ == "__main__":
    main()
