#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""离岸人民币 USD/CNH 日序列拉取 → recap.db.fx_cnh_daily
（烛阴 2026-06-30；为日报「美元兑（离岸）人民币汇率」栏供数：当前值 + 近7交易日曲线）

源策略：
  • 主路 = Tushare Pro `fx_daily`（ts_code=USDCNH.FXCM），与 stock_daily 同 provider/proxy/token，
    数据与全库同源一致；有历史 → 可一次回填出 7 天曲线。
  • 一次性种子 = `--backfill-dim1`：把 dim1_external_pricing.usd_cny 里**已记录的真实离岸点**
    （课件驱动、稀疏）灌进表，source='dim1'，让曲线在 Tushare 接通前先有真数据。
铁律（数据真实性）：拉不到 → 跳过、不写、不编；上层日报按缺数诚实标「待回填」。

日期口径（2026-11-16 起 · 风险日报 GOTCHAS NOTE-20261116-001）：表内 tushare 行的 trade_date ＝ 北京日。
  Tushare/FXCM 日线的 trade_date 是 K 线起点（纽约 17:00），标 D 的那根对应北京 D+1；周五、周六标的残根丢弃；
  北京 T+1 07:00 之前没走完的那根不写（所以北京凌晨跑，最新一行是前一个北京日）；买价、卖价缺一不写；
  日期不是严格 YYYYMMDD 即报错、整批不写。口径同 剑酒青丘 fetch_cn_liquidity.redate_fxcm
  （market_data.cn_liquidity_daily.usdcnh_spot）。2026-11-16 之前写入的 tushare 行是起点日口径，
  已于同日删除并按新口径重灌（--from 20260610）；dim1 种子行未动。

写库：走 config.connect_write（沙箱须设 ZZJY_DATABASE_ROOT=/tmp/dbroot 走 /tmp 副本，禁直写挂载盘真盘）。

用法：
  python3 scripts/fetch_fx_cnh.py --backfill-dim1        # 一次性种子（dim1 已录真实点）
  python3 scripts/fetch_fx_cnh.py                        # 增量拉 Tushare fx_daily（近窗）
  python3 scripts/fetch_fx_cnh.py --from 20260601        # Tushare 回填指定起始
  python3 scripts/fetch_fx_cnh.py --dry-run              # 只列拟写，不落库
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import argparse
import datetime
import json
import re
import sqlite3
import urllib.request
from pathlib import Path

import config
from lib.logger import get_logger

logger = get_logger(__name__)

API = "https://api.tushare.pro"
FX_TS_CODE = "USDCNH.FXCM"   # 离岸人民币（复盘世界 Tushare 若用别码，改这里）
DOTENV = Path(config.ENV_FILE)
BJ = datetime.timezone(datetime.timedelta(hours=8))
BAR_DONE_AT = datetime.time(7, 0)   # 北京日 T 那根到北京 T+1 07:00 之后才算走完（纽约 17:00 收线＝北京 05:00/06:00，留余量）


def load_token() -> str:
    tok = _os.environ.get("TUSHARE_TOKEN", "").strip()
    if tok:
        return tok
    if DOTENV.exists():
        for line in DOTENV.read_text(encoding="utf-8").splitlines():
            if line.startswith("TUSHARE_TOKEN="):
                return line.split("=", 1)[1].strip().strip("'\"")
    return ""


def tushare_call(token, api_name, params, fields, retries=2):
    """HTTP API 直调（stdlib urllib，走系统代理）。同 fill_index_north 范式。"""
    body = json.dumps({"api_name": api_name, "token": token,
                       "params": params, "fields": fields}).encode()
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(API, data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                out = json.loads(r.read().decode())
            if out.get("code") != 0:
                raise RuntimeError(f"tushare {api_name}: {out.get('msg')}")
            d = out["data"]
            return [dict(zip(d["fields"], row)) for row in d["items"]]
        except RuntimeError:
            raise
        except Exception as e:  # noqa: BLE001  网络抖动 → 重试
            last = e
            if attempt < retries:
                import time
                time.sleep(2 * (attempt + 1))
    raise last


def ensure_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fx_cnh_daily (
            trade_date TEXT PRIMARY KEY,    -- YYYYMMDD
            close      REAL,                -- 离岸 USD/CNH 收盘（mid）
            source     TEXT,                -- tushare / dim1
            updated_at TEXT
        )""")


def upsert(conn, rows, dry):
    """rows: [(trade_date, close, source)]。INSERT OR REPLACE（同日后到源覆盖）。"""
    now = datetime.datetime.now().isoformat(timespec="seconds")
    if dry:
        for d, v, s in rows:
            logger.info(f"  [dry] {d}  {v}  ({s})")
        return 0
    conn.executemany(
        "INSERT OR REPLACE INTO fx_cnh_daily (trade_date, close, source, updated_at) "
        "VALUES (?,?,?,?)", [(d, v, s, now) for d, v, s in rows])
    conn.commit()
    return len(rows)


def backfill_dim1(conn, dry):
    """把 dim1_external_pricing.usd_cny 已记录的真实离岸点灌进来（source='dim1'）。"""
    rows = []
    for d, v in conn.execute(
            "SELECT date, usd_cny FROM dim1_external_pricing "
            "WHERE usd_cny IS NOT NULL ORDER BY date"):
        td = (d or "").replace("-", "")
        if len(td) == 8:
            try:
                rows.append((td, float(v), "dim1"))
            except (TypeError, ValueError):
                continue
    logger.info(f"[dim1] 可种子 {len(rows)} 条真实离岸点")
    # 不覆盖已有 tushare 源：仅插入缺失日（INSERT OR IGNORE 语义）
    have = {r[0] for r in conn.execute("SELECT trade_date FROM fx_cnh_daily")}
    rows = [r for r in rows if r[0] not in have]
    if not rows:
        logger.info("[dim1] 无新增（已全部在库）")
        return 0
    if dry:
        for d, v, s in rows:
            logger.info(f"  [dry] {d}  {v}  (dim1)")
        return 0
    now = datetime.datetime.now().isoformat(timespec="seconds")
    conn.executemany(
        "INSERT OR IGNORE INTO fx_cnh_daily (trade_date, close, source, updated_at) "
        "VALUES (?,?,?,?)", [(d, v, s, now) for d, v, s in rows])
    conn.commit()
    return len(rows)


_YMD = re.compile(r"[0-9]{8}")


def parse_ymd(td):
    """严格 YYYYMMDD：必须是 8 位 ASCII 数字、是真实日历日、且格式化回去与原串相同；否则 ValueError。
    （strptime 本身宽松，'202611' 会被读成 2026-01-01。）"""
    if not isinstance(td, str) or not _YMD.fullmatch(td):
        raise ValueError(f"日期不是严格 YYYYMMDD：{td!r}")
    d = datetime.datetime.strptime(td, "%Y%m%d").date()
    if d.strftime("%Y%m%d") != td:
        raise ValueError(f"日期不是严格 YYYYMMDD：{td!r}")
    return d


def redate_fxcm(rows, now_bj):
    """FXCM 日线的 trade_date 是 K 线起点（纽约 17:00）：标 D 的那根覆盖到 D+1 纽约 17:00，对应北京 D+1。
    周日标的那根＝周一；周五、周六标的是只有零星报价的残根，丢弃。
    北京日 T 的那根要到北京 T+1 07:00 之后才算走完，没走完的不写（写了就是盘中快照）。
    买价、卖价缺一不写（单边价与中间价差半个价差，2024 起中位 36 点）。
    trade_date 不是严格 YYYYMMDD → ValueError，整批不写（宁停不写错日期）。
    口径同 剑酒青丘 fetch_cn_liquidity.redate_fxcm（cn_liquidity_daily.usdcnh_spot）。2026-11-16 · 风险日报 GOTCHAS NOTE-20261116-001。
    rows: [{'trade_date','bid_close','ask_close'}]；now_bj: 带时区的当前时刻 → [(北京日 YYYYMMDD, 中间价)] 按日期升序。"""
    if now_bj.tzinfo is None:
        raise ValueError("now_bj 必须带时区")
    out = {}
    for r in rows:
        d = parse_ymd(r.get("trade_date"))
        b, a = r.get("bid_close"), r.get("ask_close")
        if b is None or a is None:
            continue
        if d.weekday() in (4, 5):
            continue
        t = d + datetime.timedelta(days=1)
        done_at = datetime.datetime.combine(t + datetime.timedelta(days=1), BAR_DONE_AT, BJ)
        if now_bj < done_at:
            continue
        out[t.strftime("%Y%m%d")] = (float(b) + float(a)) / 2
    return sorted(out.items())


def fetch_tushare(conn, token, start, end, dry, now_bj=None):
    if not token:
        logger.info("[tushare] 待配 TUSHARE_TOKEN，跳过取数（留缺，绝不编）。")
        return 0
    parse_ymd(start)
    parse_ymd(end)
    # 重标后北京日＝起点日+1，起点往前多取 3 天，才能盖到 start 当日（周一要靠上周日标的那根）
    q_start = (parse_ymd(start) - datetime.timedelta(days=3)).strftime("%Y%m%d")
    recs = tushare_call(token, "fx_daily",
                        {"ts_code": FX_TS_CODE, "start_date": q_start, "end_date": end},
                        "trade_date,bid_close,ask_close")
    now_bj = now_bj or datetime.datetime.now(BJ)
    rows = [(td, round(mid, 4), "tushare") for td, mid in redate_fxcm(recs, now_bj) if td >= start]
    logger.info(f"[tushare] fx_daily({FX_TS_CODE}) 起点日 {q_start}~{end} 取回 {len(recs)} 根 → "
                f"北京日 ≥{start} 已走完且双边报价 {len(rows)} 条"
                + (f"（{rows[0][0]}~{rows[-1][0]}）" if rows else ""))
    return upsert(conn, rows, dry)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill-dim1", action="store_true",
                    help="一次性：用 dim1 已记录真实离岸点种子（不覆盖 tushare 源）")
    ap.add_argument("--from", dest="start", help="Tushare 回填起始 YYYYMMDD（默认近 20 日窗）")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = (sqlite3.connect(f"file:{config.RECAP_DB}?mode=ro", uri=True) if args.dry_run
            else config.connect_write(config.RECAP_DB))
    if not args.dry_run:
        ensure_table(conn)

    n = 0
    if args.backfill_dim1:
        n += backfill_dim1(conn, args.dry_run) if not args.dry_run else backfill_dim1(
            sqlite3.connect(f"file:{config.RECAP_DB}?mode=ro", uri=True), True)
    else:
        today = datetime.date.today().strftime("%Y%m%d")
        start = args.start or (datetime.date.today() - datetime.timedelta(days=20)).strftime("%Y%m%d")
        n += fetch_tushare(conn, load_token(), start, today, args.dry_run)

    logger.info(f"✅ fx_cnh_daily {'(dry-run 未写)' if args.dry_run else f'写入/更新 {n} 条'}")


if __name__ == "__main__":
    main()
