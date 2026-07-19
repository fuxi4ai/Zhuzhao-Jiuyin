#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""新股 IPO 募资拉取 → 公共 market_data.db.ipo_daily（附加表，不动句芒既有表）
（CC 2026-07-17；五因风险温度 F4「IPO 虹吸」数据源，Doctor 终端跑——网络下载禁在沙箱）

口径：按新股 **上市日 ipo_date** 聚合当日家数与募集资金合计（亿元）。
  F4「虹吸」= 近 N 日新股募资合计（存量资金被超级 IPO 分流的压力）。
来源：tushare pro `new_share`（IPO 新股列表）。字段 funds=募集资金(亿元)、ipo_date=上市日。
  IPO 稀疏（多数交易日 0）——只对有新股上市的日期建行，消费侧按滚动窗口求和（缺日=0）。

用法：
  # 一次性回填（Doctor 终端；网络）——起始日与两融对齐 20240101
  python3 scripts/fetch_ipo.py --from 20240101
  # 日更增量
  python3 scripts/fetch_ipo.py --from 20260701
  # 只读对照（沙箱可跑，不联网）：近20日/60日募资合计 + 最近几笔
  python3 scripts/fetch_ipo.py --check
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from lib.logger import get_logger
logger = get_logger(__name__)
import sqlite3, argparse, time, datetime
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
        CREATE TABLE IF NOT EXISTS ipo_daily (
            trade_date  TEXT PRIMARY KEY,   -- 上市日 ipo_date YYYYMMDD
            n_ipo       INTEGER,            -- 当日上市新股家数
            funds_yi    REAL,               -- 当日募集资金合计（亿元）· F4 主指标
            names       TEXT,               -- 当日新股名（逗号分隔，便于人读）
            source      TEXT DEFAULT 'tushare_new_share',
            updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


def fetch(from_date, to_date):
    pro = get_pro()
    conn = sqlite3.connect(config.MARKET_DB)
    ensure_table(conn)
    df = pro.new_share(start_date=from_date, end_date=to_date)
    agg = {}  # ipo_date -> {'n':int,'funds':float,'names':[]}
    for r in df.itertuples():
        d = getattr(r, "ipo_date", None)
        if not d or not (from_date <= d <= to_date):   # 防接口忽略区间返回全量
            continue
        a = agg.setdefault(d, {"n": 0, "funds": 0.0, "names": []})
        a["n"] += 1
        f = getattr(r, "funds", None)
        if f is not None:
            try:
                a["funds"] += float(f)
            except (TypeError, ValueError):
                pass
        nm = getattr(r, "name", None)
        if nm:
            a["names"].append(str(nm))
    rows = [(d, v["n"], round(v["funds"], 3), ",".join(v["names"]))
            for d, v in sorted(agg.items())]
    conn.executemany(
        "INSERT OR REPLACE INTO ipo_daily(trade_date,n_ipo,funds_yi,names) VALUES (?,?,?,?)", rows)
    conn.commit()
    if rows:
        logger.info(f"✅ 写入 {len(rows)} 个上市日 → ipo_daily [{rows[0][0]}→{rows[-1][0]}] "
                    f"共 {sum(r[1] for r in rows)} 只新股 · 募资合计 {sum(r[2] for r in rows):.0f} 亿")
    else:
        logger.info("✅ 0 个上市日 → ipo_daily（区间内无新股/接口无返回）")
    conn.close()


def _win_sum(cur, end_yyyymmdd, days):
    start = (datetime.date.fromisoformat(f"{end_yyyymmdd[:4]}-{end_yyyymmdd[4:6]}-{end_yyyymmdd[6:]}")
             - datetime.timedelta(days=days)).strftime("%Y%m%d")
    r = cur.execute("SELECT COALESCE(SUM(funds_yi),0), COALESCE(SUM(n_ipo),0) FROM ipo_daily "
                    "WHERE trade_date>? AND trade_date<=?", (start, end_yyyymmdd)).fetchone()
    return r[0], r[1], start


def check():
    """只读对照（不联网）：近20/60日历日募资合计 + 最近几笔，供 F4 阈值定初值。"""
    md = sqlite3.connect(f"file:{config.MARKET_DB}?mode=ro", uri=True)
    try:
        cnt = md.execute("SELECT COUNT(*),MIN(trade_date),MAX(trade_date) FROM ipo_daily").fetchone()
    except sqlite3.OperationalError:
        logger.error("ipo_daily 不存在——先在终端跑 --from 回填")
        return
    if not cnt or not cnt[0]:
        logger.error("ipo_daily 为空——先在终端跑 --from 回填")
        return
    mx = cnt[2]
    f20, n20, s20 = _win_sum(md, mx, 20)
    f60, n60, s60 = _win_sum(md, mx, 60)
    logger.info(f"覆盖 {cnt[0]} 个上市日 [{cnt[1]}→{mx}]")
    logger.info(f"  近20日历日({s20}→{mx})：{n20} 只 · 募资 {f20:.0f} 亿  ← F4『IPO虹吸』窗口候选")
    logger.info(f"  近60日历日：{n60} 只 · 募资 {f60:.0f} 亿")
    logger.info("  最近上市日：")
    for r in md.execute("SELECT trade_date,n_ipo,funds_yi,names FROM ipo_daily ORDER BY trade_date DESC LIMIT 5"):
        logger.info(f"    {r[0]}: {r[1]}只 {r[2]:.1f}亿 · {r[3]}")


def main():
    ap = argparse.ArgumentParser(description="新股 IPO 募资 → market_data.ipo_daily（F4 数据源）")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--from", dest="from_date", help="回填/增量起始日 YYYYMMDD")
    g.add_argument("--check", action="store_true", help="只读对照（沙箱可跑，不联网）")
    ap.add_argument("--to", dest="to_date", default=time.strftime("%Y%m%d"))
    args = ap.parse_args()
    if args.check:
        check()
    else:
        fetch(args.from_date, args.to_date)


if __name__ == "__main__":
    main()
