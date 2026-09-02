#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A股指数真身日线 → market_data.db.cn_index_daily
（research-CC 2026-09-01 · Doctor 裁「换指数真身」：日报「大盘涨跌幅」弃 510300 ETF 代理，
   改 tushare index_daily 真实指数——ETF 二级市场折溢价曾致 08-28/08-31/09-01 连续三日与
   指数偏离 0.20/0.21/0.28pp，代理口径失真。见 GOTCHAS ERR-20260901-002。）

纪律：与 fetch_theme_etf 同——取数默认仅在 Doctor 终端跑（沙箱只验证读表逻辑，不抓数）。
用法：
  python3 scripts/fetch_index_daily.py --from 20240101     # 全量回填（供「大盘」曲线 20 日窗口）
  python3 scripts/fetch_index_daily.py --from 20260901     # 每日增量（班内新增步）
  python3 scripts/fetch_index_daily.py --dry-run           # 只列目标指数不写库

token：与 fetch_theme_etf 同链（env TUSHARE_TOKEN / Keychain tushare_pro / ~/.tushare/token）。
pct_chg 口径：index_daily 官方涨跌幅（%），价格指数（不含分红再投）——与 ETF 复权口径的
  日频差在分红因素上（20 日窗口累计 <0.1pp），快照/曲线展示可忽略。
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from lib.logger import get_logger
logger = get_logger(__name__)
import sqlite3, argparse, time
import config

MARKET_DB = config.MARKET_DB

# ── 大盘基准指数（2026-09-01 Doctor 裁「换指数真身」· 主口径 000300.SH；上证 000001.SH 备用不取）──
INDICES = {
    "000300.SH": "沪深300指数",
}
TABLE = "cn_index_daily"


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
        logger.error("❌ 未找到 TUSHARE_TOKEN（env / Keychain tushare_pro / ~/.tushare/token）")
        _sys.exit(1)
    ts.set_token(tok)
    return ts.pro_api()


def ensure_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cn_index_daily (
            trade_date TEXT,
            idx_code   TEXT,
            close      REAL,
            pct_chg    REAL,
            vol        REAL,
            amount     REAL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (trade_date, idx_code)
        )
    """)
    conn.commit()


def pull_indices(conn, pro, from_date, to_date):
    """拉全部 INDICES 入表（供 fetch_theme_etf 内嵌调用，保证与 ETF 同批原子更新；
    独立回填亦可经 main() 走此函数）。返回写入行数。"""
    ensure_table(conn)
    total = 0
    for c, name in INDICES.items():
        try:
            df = pro.index_daily(ts_code=c, start_date=from_date, end_date=to_date)
        except Exception as e:
            logger.error(f"  ✗ {c}: {e}"); continue
        if df is None or df.empty:
            logger.info(f"  - {c}: 无数据"); continue
        rows = [(r.trade_date, c, float(r.close), float(r.pct_chg),
                 float(r.vol) if r.vol is not None else None,
                 float(r.amount) if r.amount is not None else None)
                for r in df.itertuples()]
        conn.executemany(
            "INSERT OR REPLACE INTO cn_index_daily(trade_date,idx_code,close,pct_chg,vol,amount) "
            "VALUES (?,?,?,?,?,?)", rows)
        conn.commit()
        total += len(rows)
        logger.info(f"  ✓ {c} {name}: {len(rows)} 行, 最新 {rows[-1][0]} pct={rows[-1][3]}")
        time.sleep(0.3)
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="from_date", default="20240101", help="起始 YYYYMMDD")
    ap.add_argument("--to", dest="to_date", default=None, help="结束 YYYYMMDD(默认今天)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    to_date = args.to_date or time.strftime("%Y%m%d")

    logger.info(f"待拉指数 {list(INDICES)} [{args.from_date}→{to_date}]")
    if args.dry_run:
        logger.info("dry-run，仅列出，不写库"); return

    pro = get_pro()
    conn = sqlite3.connect(MARKET_DB)
    n = pull_indices(conn, pro, args.from_date, to_date)
    logger.info(f"\n✅ 完成，写入 {n} 行 → market_data.db.cn_index_daily")
    conn.close()


if __name__ == "__main__":
    main()
