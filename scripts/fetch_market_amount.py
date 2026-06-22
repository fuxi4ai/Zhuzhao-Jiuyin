#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全市场成交额拉取 → 公共 market_data.db.market_amount_daily（附加表，不动句芒既有表）
（CC 2026-06-10；容量约束模块的数据底座，Doctor 终端跑）

口径：全市场 ≈ 上证(000001.SH) + 深证(399001.SZ) 成交额之和（北交所占比可忽略），单位万亿。
来源：tushare `index_daily`（amount 单位千元，/1e9 → 万亿）。
旁证：recap.db dim3_sentiment_tech.volume_trillion（小鲍课件口径，130 条，~28% 提取脏值，
      仅作 --check 对照，不入正源）。

用法：
  python3 scripts/fetch_market_amount.py --from 20250101     # 回填/增量
  python3 scripts/fetch_market_amount.py --check             # 与小鲍口径/句芒表对照（沙箱可跑）
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from lib.logger import get_logger
logger = get_logger(__name__)
import sqlite3, argparse, time
import config

INDICES = {"000001.SH": "sh", "399001.SZ": "sz"}


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
        CREATE TABLE IF NOT EXISTS market_amount_daily (
            trade_date     TEXT PRIMARY KEY,   -- YYYYMMDD
            sh_trillion    REAL,               -- 上证成交额（万亿）
            sz_trillion    REAL,               -- 深证成交额（万亿）
            total_trillion REAL,               -- 全市场≈沪+深（万亿）
            source         TEXT DEFAULT 'tushare_index_daily',
            updated_at     DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


def fetch(from_date, to_date):
    pro = get_pro()
    conn = sqlite3.connect(config.MARKET_DB)
    ensure_table(conn)
    data = {}
    for code, tag in INDICES.items():
        df = pro.index_daily(ts_code=code, start_date=from_date, end_date=to_date)
        for r in df.itertuples():
            data.setdefault(r.trade_date, {})[tag] = float(r.amount) / 1e9  # 千元→万亿
        logger.info(f"  ✓ {code}: {len(df)} 行")
        time.sleep(0.3)
    rows = [(d, v.get("sh"), v.get("sz"),
             round((v.get("sh") or 0) + (v.get("sz") or 0), 4))
            for d, v in sorted(data.items())]
    conn.executemany(
        "INSERT OR REPLACE INTO market_amount_daily"
        "(trade_date,sh_trillion,sz_trillion,total_trillion) VALUES (?,?,?,?)", rows)
    conn.commit()
    if rows:
        logger.info(f"✅ 写入 {len(rows)} 日 → market_amount_daily "
                    f"[{rows[0][0]}→{rows[-1][0]}] 最新全市场 {rows[-1][3]} 万亿")
    else:
        logger.info("✅ 0 日新增 → market_amount_daily（休市/已最新，无数据可写）")
    conn.close()


def check():
    """三口径对照：tushare 正源 vs 小鲍课件 vs 句芒 daily_market（0603+）"""
    md = sqlite3.connect(f"file:{config.MARKET_DB}?mode=ro", uri=True)
    rc = sqlite3.connect(f"file:{config.RECAP_DB}?mode=ro", uri=True)
    ts_amt = dict(md.execute(
        "SELECT trade_date, total_trillion FROM market_amount_daily"))
    if not ts_amt:
        logger.error("market_amount_daily 为空——先在终端跑 --from 回填")
        return
    xb = dict(rc.execute("SELECT replace(date,'-',''), volume_trillion FROM "
                         "dim3_sentiment_tech WHERE volume_trillion IS NOT NULL"))
    dm = dict(md.execute("SELECT trade_date, volume_trillion FROM daily_market "
                         "WHERE volume_trillion > 0"))
    both = sorted(set(xb) & set(ts_amt))
    bad = [(d, xb[d], ts_amt[d]) for d in both
           if abs(xb[d] - ts_amt[d]) / ts_amt[d] > 0.15]
    logger.info(f"小鲍×tushare 重叠 {len(both)} 日，偏差>15% 共 {len(bad)} 日"
                f"（提取脏值候选，可据此修 dim3）")
    for d, a, b in bad[:10]:
        logger.info(f"  {d}: 小鲍{a} vs tushare{b:.2f}")
    both2 = sorted(set(dm) & set(ts_amt))
    if both2:
        mx = max(abs(dm[d] - ts_amt[d]) / ts_amt[d] for d in both2)
        logger.info(f"句芒×tushare 重叠 {len(both2)} 日，最大偏差 {mx:.1%}")


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--from", dest="from_date")
    g.add_argument("--check", action="store_true")
    ap.add_argument("--to", dest="to_date", default=time.strftime("%Y%m%d"))
    args = ap.parse_args()
    if args.check:
        check()
    else:
        fetch(args.from_date, args.to_date)


if __name__ == "__main__":
    main()
