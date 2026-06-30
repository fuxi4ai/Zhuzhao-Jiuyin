#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""韩国存储双雄（三星电子 005930.KS / SK海力士 000660.KS）→ market_data.db.intl_index_daily
（烛阴 2026-06-30；为日报「外部定价·韩国」区供数：直追两只票而非 EWY 代理）

源：Yahoo Finance chart API（urllib 直取，不依赖 yfinance 包；白名单已开、沙箱直达）。
  实测 2026-06-30：005930.KS 新鲜到 06-30，比 stockanalysis KRX（延迟 Jun-11）/ EWY（CDN 卡 0626）都准。
铁律（数据真实性）：取不到 → 跳过、不写、不编；上层日报按缺数诚实标「待回填」。
写库：走 config.connect_write（沙箱须设 ZZJY_DATABASE_ROOT=/tmp/dbroot 走 /tmp 副本，禁直写挂载盘真盘）。

用法：
  python3 scripts/fetch_kr_stocks.py            # 增量拉两只票最新若干日 → intl_index_daily
  python3 scripts/fetch_kr_stocks.py --dry-run  # 只打印拟写
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import argparse
import datetime
import json
import sqlite3
import urllib.request

import config
from lib.logger import get_logger

logger = get_logger(__name__)

# code（内部稳定键）, yahoo symbol, 中文名, note
KR_STOCKS = [
    ("KR_SAMSUNG", "005930.KS", "三星电子",  "存储/半导体 · KOSPI 龙头"),
    ("KR_HYNIX",   "000660.KS", "SK海力士",  "HBM/存储 · KOSPI 龙头"),
]
CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=15d&interval=1d"


def fetch_one(sym):
    """返回 [(yyyymmdd, close, pct_chg), ...] 升序；失败/空→[]（绝不编）。"""
    req = urllib.request.Request(CHART.format(sym=sym), headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        j = json.loads(r.read().decode())
    res = (j.get("chart", {}).get("result") or [None])[0]
    if not res:
        return []
    ts = res.get("timestamp") or []
    closes = res.get("indicators", {}).get("quote", [{}])[0].get("close") or []
    out = []
    prev = None
    for t, c in zip(ts, closes):
        if c is None:
            continue
        d = datetime.datetime.utcfromtimestamp(t).strftime("%Y%m%d")
        pct = round((c / prev - 1) * 100, 4) if prev else None
        out.append((d, round(float(c), 2), pct))
        prev = c
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rows = []
    for code, sym, name, note in KR_STOCKS:
        try:
            series = fetch_one(sym)
        except Exception as e:  # noqa: BLE001
            logger.error(f"  ✗ {code} {sym}: {type(e).__name__} {str(e)[:80]} → 标缺、保留旧行、绝不编")
            continue
        if not series:
            logger.error(f"  ✗ {code} {sym}: 空 → 标缺")
            continue
        logger.info(f"  ✓ {code} {name}: 取回 {len(series)} 日，最新 {series[-1][0]} 收 {series[-1][1]:,.0f}")
        for d, close, pct in series:
            if pct is None:
                continue   # 窗口首日无前收，跳过（避免假 0%）
            rows.append((d, code, sym, name, "kr_stock", close, pct, "yahoo", note))

    if args.dry_run:
        for r in rows[-6:]:
            logger.info(f"  [dry] {r[0]} {r[1]} 收{r[5]:,.0f} {r[6]:+.2f}%")
        logger.info(f"🔍 dry-run：拟写 {len(rows)} 行（未落库）")
        return

    conn = config.connect_write(config.MARKET_DB)
    conn.executemany(
        "INSERT OR REPLACE INTO intl_index_daily "
        "(trade_date,code,symbol,name,kind,close,pct_chg,source,updated_at,note) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        [(d, c, sy, nm, k, cl, pc, src, datetime.datetime.now().isoformat(timespec="seconds"), nt)
         for d, c, sy, nm, k, cl, pc, src, nt in rows])
    conn.commit()
    logger.info(f"✅ intl_index_daily 写入/更新 {len(rows)} 行（三星/SK海力士）")


if __name__ == "__main__":
    main()
