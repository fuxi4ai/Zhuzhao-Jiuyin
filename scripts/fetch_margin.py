#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""两融（融资融券）市场级余额拉取 → 公共 market_data.db.margin_daily（附加表，不动句芒既有表）
（CC 2026-07-17；五因风险温度 F3「杠杆被动出清」数据源，Doctor 终端跑——网络下载禁在沙箱）

口径：全市场两融 = 上交所(SSE)+深交所(SZSE)+北交所(BSE) 汇总。
  主指标 = 融资余额 rzye（媒体『融资余额减少约1700亿』即此，杠杆多头的直接水位）；
  另存 融券余额 rqye、融资融券余额 rzrqye。tushare 原值单位『元』，本表统一存『亿元』(/1e8)。
来源：tushare pro `margin`（融资融券交易汇总·市场级）。BSE 若无数据/接口不返回则跳过、不报错。

用法：
  # 一次性回填（Doctor 终端；网络）——起始日可调，2.5 年足够覆盖回测窗口
  python3 scripts/fetch_margin.py --from 20240101
  # 日更增量（接入 07:00 链后每日跑）
  python3 scripts/fetch_margin.py --from 20260701
  # 只读对照（沙箱可跑，不联网）：最新余额 + 近5/周变化，验证回填结果
  python3 scripts/fetch_margin.py --check
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from lib.logger import get_logger
logger = get_logger(__name__)
import sqlite3, argparse, time
import config

# tushare margin exchange_id → 本表列前缀
EXCHANGES = {"SSE": "sse", "SZSE": "szse", "BSE": "bse"}


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
        CREATE TABLE IF NOT EXISTS margin_daily (
            trade_date    TEXT PRIMARY KEY,   -- YYYYMMDD
            total_rzye    REAL,               -- 全市场融资余额（亿元）· F3 主指标
            total_rqye    REAL,               -- 全市场融券余额（亿元）
            total_rzrqye  REAL,               -- 全市场融资融券余额（亿元）
            sse_rzrqye    REAL,               -- 上交所两融余额（亿元）
            szse_rzrqye   REAL,               -- 深交所两融余额（亿元）
            bse_rzrqye    REAL,               -- 北交所两融余额（亿元·缺则 NULL）
            source        TEXT DEFAULT 'tushare_margin',
            updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


def fetch(from_date, to_date):
    pro = get_pro()
    conn = sqlite3.connect(config.MARKET_DB)
    ensure_table(conn)
    # data[trade_date] = {'sse_rzrqye':.., 'szse_rzrqye':.., 'bse_rzrqye':.., 'rzye':.., 'rqye':.., 'rzrqye':..}
    data = {}
    for ex, tag in EXCHANGES.items():
        try:
            df = pro.margin(exchange_id=ex, start_date=from_date, end_date=to_date)
        except Exception as e:
            logger.warning(f"  ⚠ {ex} margin 拉取失败/无数据：{e}（跳过，不阻断）")
            continue
        n = 0
        for r in df.itertuples():
            d = data.setdefault(r.trade_date, {})
            rzrqye = float(getattr(r, "rzrqye", 0) or 0) / 1e8
            d[f"{tag}_rzrqye"] = rzrqye
            d["rzye"] = d.get("rzye", 0.0) + float(getattr(r, "rzye", 0) or 0) / 1e8
            d["rqye"] = d.get("rqye", 0.0) + float(getattr(r, "rqye", 0) or 0) / 1e8
            d["rzrqye"] = d.get("rzrqye", 0.0) + rzrqye
            n += 1
        logger.info(f"  ✓ {ex}: {n} 行")
        time.sleep(0.4)
    # 只写『完整日』：SSE 与 SZSE 均到位（两融明细 T+1，当日尾部常仅 SSE 先发→跳过，
    # 次日 SZSE 发布后经 INSERT OR REPLACE 自动补全；BSE 微量·可选）。避免半日 total 污染日/周变。
    skipped = [dt for dt, v in data.items() if not ("sse_rzrqye" in v and "szse_rzrqye" in v)]
    rows = [(dt,
             round(v.get("rzye", 0.0), 2),
             round(v.get("rqye", 0.0), 2),
             round(v.get("rzrqye", 0.0), 2),
             round(v["sse_rzrqye"], 2),
             round(v["szse_rzrqye"], 2),
             (round(v["bse_rzrqye"], 2) if "bse_rzrqye" in v else None))
            for dt, v in sorted(data.items())
            if "sse_rzrqye" in v and "szse_rzrqye" in v]
    if skipped:
        logger.info(f"  ⏭ 跳过 {len(skipped)} 个不完整日（缺 SZSE，两融 T+1）：{sorted(skipped)[-3:]}")
    conn.executemany(
        "INSERT OR REPLACE INTO margin_daily"
        "(trade_date,total_rzye,total_rqye,total_rzrqye,sse_rzrqye,szse_rzrqye,bse_rzrqye)"
        " VALUES (?,?,?,?,?,?,?)", rows)
    conn.commit()
    if rows:
        logger.info(f"✅ 写入 {len(rows)} 日 → margin_daily "
                    f"[{rows[0][0]}→{rows[-1][0]}] 最新融资余额 {rows[-1][1]:.0f} 亿元 "
                    f"（两融合计 {rows[-1][3]:.0f} 亿元）")
    else:
        logger.info("✅ 0 日新增 → margin_daily（休市/已最新/接口无返回）")
    conn.close()


def check():
    """只读对照（不联网）：最新融资余额 + 近5日/周变化，验证回填结果、供 F3 阈值定初值。"""
    md = sqlite3.connect(f"file:{config.MARKET_DB}?mode=ro", uri=True)
    try:
        # 只取完整日（szse 非空），避免半日污染日/周变
        rows = md.execute(
            "SELECT trade_date,total_rzye,total_rzrqye FROM margin_daily "
            "WHERE szse_rzrqye IS NOT NULL ORDER BY trade_date DESC LIMIT 10").fetchall()
        incomplete = md.execute(
            "SELECT COUNT(*) FROM margin_daily WHERE szse_rzrqye IS NULL").fetchone()[0]
    except sqlite3.OperationalError:
        logger.error("margin_daily 不存在——先在终端跑 --from 回填")
        return
    if not rows:
        logger.error("margin_daily 无完整日——先在终端跑 --from 回填")
        return
    if incomplete:
        logger.info(f"  （另有 {incomplete} 个不完整日/半日 SSE-only，已排除；SZSE 发布后自动补全）")
    rows = rows[::-1]  # 升序
    latest = rows[-1]
    logger.info(f"最新 {latest[0]}：融资余额 {latest[1]:.0f} 亿 · 两融合计 {latest[2]:.0f} 亿")
    if len(rows) >= 2:
        d1 = rows[-1][1] - rows[-2][1]
        logger.info(f"  日变（融资余额）：{d1:+.1f} 亿")
    if len(rows) >= 6:
        d5 = rows[-1][1] - rows[-6][1]
        logger.info(f"  近5日变（融资余额）：{d5:+.1f} 亿  ← F3『杠杆被动出清』周变化口径候选")
    cnt = md.execute("SELECT COUNT(*), MIN(trade_date), MAX(trade_date) FROM margin_daily").fetchone()
    logger.info(f"  覆盖：{cnt[0]} 日 [{cnt[1]}→{cnt[2]}]")


def main():
    ap = argparse.ArgumentParser(description="两融市场级余额 → market_data.margin_daily（F3 数据源）")
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
