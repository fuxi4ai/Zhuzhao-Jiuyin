#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hot_sectors 写入管道（2026-07-30 立）——把 dim2_sector_themes.hot_sectors 文本列派生成 hot_sectors 表行。

## 为什么需要它
`hot_sectors` 是**孤儿表**：全量 grep `INSERT INTO hot_sectors` 零命中，从没有任何脚本写过它。
库里原有 36 行（2025-11-04 ~ 2026-05-12）是早期手工/已废脚本填的，此后停更约 50 个交易日。
而同一份课件的热点信息其实**一直有在入库**——落在 `dim2_sector_themes.hot_sectors` 这个**同名的文本列**里
（正是它此前让 grep 误命中、掩盖了表没人写的事实）。

## 口径（provenance 必须诚实）
- 本脚本**不读 PDF、不做新提炼**，只把**已入库、已带 P2 标记**的 dim2 文本列拆成结构化行 —— 属**库内派生**，
  不是二次提取，因此不引入新的幻觉风险。
- `sector_name` 保留完整片段（含括号注释），以便回溯 dim2 原文。
- `is_industry_logic` 由关键词判定（涨价/提价/景气/供需/缺口/紧缺/订单/排产/满产/扩产/新国标/矛盾积累/产业逻辑），
  属**保守派生推断**：命中才置 1，否则 0。
- `pct_change` / `ts_code` / `related_signal_id` 一律 NULL —— 课件与 dim2 均无此数据，**留空不编**（数据真实性铁律）。
- dim2 该列为空的日期**跳过**，不补（缺口是诚实的）。

## 用法
    python3 tools/sync_hot_sectors.py --backfill            # 回填所有缺口日（幂等）
    python3 tools/sync_hot_sectors.py --date 2026-07-30     # 只同步某日
    python3 tools/sync_hot_sectors.py --backfill --dry-run  # 只看不写
沙箱须走 /tmp 副本往返（G-X33）：export ZZJY_DATABASE_ROOT=/tmp/dbroot-xxx
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import sqlite3, re, argparse
from datetime import datetime, timedelta
import config

INDUSTRY_KW = ["涨价", "提价", "景气", "供需", "缺口", "紧缺", "订单", "排产", "满产",
               "扩产", "新国标", "矛盾积累", "产业逻辑", "涨幅确定", "供不应求"]


def split_sectors(text):
    """双分隔符切分（分号优先，否则逗号）。已验证括号内无分隔符，不会误切。"""
    if not text or not text.strip():
        return []
    parts = re.split(r"[;；]", text) if re.search(r"[;；]", text) else re.split(r"[,，]", text)
    return [p.strip() for p in parts if p.strip()]


def is_industry_logic(name):
    return 1 if any(k in name for k in INDUSTRY_KW) else 0


def sync(con, dates=None, backfill=False, dry=False):
    cur = con.cursor()
    now = (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")

    if backfill:
        rows = cur.execute("""SELECT date, hot_sectors FROM dim2_sector_themes
            WHERE hot_sectors IS NOT NULL AND trim(hot_sectors)<>'' ORDER BY date""").fetchall()
    else:
        q = ",".join("?" * len(dates))
        rows = cur.execute(f"""SELECT date, hot_sectors FROM dim2_sector_themes
            WHERE date IN ({q}) AND hot_sectors IS NOT NULL AND trim(hot_sectors)<>''
            ORDER BY date""", dates).fetchall()

    done_days, ins, skipped_existing, empty_days = 0, 0, 0, []
    for d, text in rows:
        secs = split_sectors(text)
        if not secs:
            empty_days.append(d)
            continue
        # 幂等：该日已有行则跳过（不覆盖手工数据）
        if cur.execute("SELECT COUNT(*) FROM hot_sectors WHERE date=?", (d,)).fetchone()[0]:
            skipped_existing += 1
            continue
        for i, name in enumerate(secs, 1):
            if not dry:
                cur.execute("""INSERT INTO hot_sectors(date, rank, sector_name, pct_change,
                    ts_code, is_industry_logic, related_signal_id, created_at)
                    VALUES (?,?,?,NULL,NULL,?,NULL,?)""", (d, i, name, is_industry_logic(name), now))
            ins += 1
        done_days += 1
    if not dry:
        con.commit()
    return dict(days=done_days, rows=ins, skipped_existing=skipped_existing, empty=empty_days)


def main():
    ap = argparse.ArgumentParser(description="hot_sectors 派生同步（源：dim2_sector_themes.hot_sectors）")
    ap.add_argument("--date", action="append", help="指定日期，可重复")
    ap.add_argument("--backfill", action="store_true", help="回填所有缺口日")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not a.backfill and not a.date:
        ap.error("需 --backfill 或 --date")
    con = sqlite3.connect(config.RECAP_DB)
    before = con.execute("SELECT COUNT(*) FROM hot_sectors").fetchone()[0]
    r = sync(con, a.date, a.backfill, a.dry_run)
    after = con.execute("SELECT COUNT(*) FROM hot_sectors").fetchone()[0]
    print(f"hot_sectors 同步{'（dry-run）' if a.dry_run else ''}：")
    print(f"  写入 {r['days']} 天 / {r['rows']} 行；已有数据跳过 {r['skipped_existing']} 天")
    if r["empty"]:
        print(f"  ⚠ dim2 该列为空、未补（缺口保留）：{r['empty']}")
    print(f"  表行数 {before} → {after}")
    con.close()


if __name__ == "__main__":
    main()
