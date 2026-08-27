#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""烛照九阴 · 美债 FRED 序列取数

2026-08-27 Doctor 令：日报「美债10年期收益率」二级详情页需要——
  DFII10      10Y 实际收益率（TIPS constant maturity · 日频 · 滞后 T+1）
  THREEFYTP10 10Y 期限溢价（NY Fed ACM 模型 · 日频序列 · 周更）
通道：FRED API（api.stlouisfed.org 白名单已通 · 白泽 fetch_fed_inputs_fred 同款 · key 读 Database/.env），仅标准库。
写库：market_data.db 新表 fred_ust_daily（增量 upsert · PRIMARY KEY(trade_date, series_id)）。
失败语义：任一序列网络/解析异常 → exit 2 优雅退出（班内不阻断，与「无 token 优雅跳过」同族）。
锁：本脚本不抢单写者锁（与 fetch_intl_index 同款）；班内由班持锁，手工跑请先抢锁再跑。
"""
import datetime
import json
import pathlib
import sqlite3
import sys
import urllib.parse
import urllib.request

LOOKBACK_DAYS = 45  # 回看窗口（FRED 滞后 1-2 天/周更序列，45 天足够增量对账）
SERIES = {
    "DFII10": "10Y 实际收益率（TIPS constant maturity）",
    "THREEFYTP10": "10Y 期限溢价（ACM · NY Fed 周更）",
}
TABLE = "fred_ust_daily"


def _docroot():
    """稳妥定位 Documents 根：向上找含 Database/.env 的祖先（G-X88 平铺挂载同款防御）"""
    p = pathlib.Path(__file__).resolve()
    for _ in range(10):
        p = p.parent
        if (p / "Database" / ".env").exists():
            return p
    sys.exit("[FATAL] 未找到 Database/.env 祖先目录")


def _db_path():
    try:
        import config
        return config.MARKET_DB
    except Exception:
        return str(_docroot() / "Database" / "Market-Data" / "market_data.db")


def _fred_key():
    for line in (_docroot() / "Database" / ".env").read_text().splitlines():
        if line.startswith("FRED_API_KEY="):
            return line.split("=", 1)[1].strip()
    sys.exit("[FATAL] .env 无 FRED_API_KEY")


def fetch(series_id):
    """FRED API 通道（api.stlouisfed.org 白名单已通·白泽同款）→ [(YYYYMMDD, value)] 升序"""
    start = (datetime.date.today() - datetime.timedelta(days=LOOKBACK_DAYS)).isoformat()
    q = urllib.parse.urlencode({
        "series_id": series_id, "api_key": _fred_key(), "file_type": "json",
        "observation_start": start, "sort_order": "asc", "limit": 1000})
    url = f"https://api.stlouisfed.org/fred/series/observations?{q}"
    with urllib.request.urlopen(url, timeout=30) as r:
        obs = json.loads(r.read()).get("observations") or []
    rows = [(o["date"].replace("-", ""), float(o["value"]))
            for o in obs if o.get("value") not in (".", "")]
    if not rows:
        raise RuntimeError(f"{series_id}: FRED 返回空序列")
    return rows


def main():
    con = sqlite3.connect(_db_path())
    con.execute(f"""CREATE TABLE IF NOT EXISTS {TABLE} (
        trade_date TEXT NOT NULL,
        series_id  TEXT NOT NULL,
        value      REAL NOT NULL,
        updated_at TEXT DEFAULT (datetime('now','localtime')),
        PRIMARY KEY (trade_date, series_id))""")
    for sid, desc in SERIES.items():
        try:
            rows = fetch(sid)
        except Exception as e:  # 网络/解析失败 → 优雅退出不阻断班
            print(f"[skip] {sid} 取数失败: {e}", file=sys.stderr)
            con.close()
            sys.exit(2)
        con.executemany(
            f"INSERT OR REPLACE INTO {TABLE} (trade_date, series_id, value) VALUES (?,?,?)",
            [(d, sid, v) for d, v in rows])
        print(f"[ok] {sid} {desc}: +{len(rows)} 行, 最新 {rows[-1][0]} = {rows[-1][1]}")
    con.commit()
    con.close()
    print("done")


if __name__ == "__main__":
    main()
