#!/usr/bin/env python3
"""
Phase A: 全量迁移 — 基础数据迁移

迁移顺序:
1. emotion_cycle  ← dim3_sentiment_tech + cycle_quant
2. hot_sectors    ← dim2_sector_themes.hot_sectors (JSON拆分)
3. industry_signals 去重合并 ← dim2 已有数据 + 现有 industry_signals

用法:
  python3 migrate_base_tables.py          # dry-run 预览
  python3 migrate_base_tables.py --execute # 执行写入
"""

import os
import sys
import json
import re
import sqlite3
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from exec_logger import ExecLogger, init_log_table

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'db', 'recap.db')


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ============================================================
# 1. emotion_cycle 迁移
# ============================================================
def migrate_emotion_cycle(conn, dry_run=True, return_items=False):
    cur = conn.cursor()

    # 从 dim3 获取情绪阶段 + 基础数据
    cur.execute("""
        SELECT date, emotion_stage, limit_up, limit_down,
               consecutive_boards, volume_trillion, up_down_ratio,
               sentiment_description, industry_logic
        FROM dim3_sentiment_tech
        ORDER BY date
    """)
    dim3_rows = [dict(r) for r in cur.fetchall()]

    # 从 cycle_quant 获取量化评分
    cur.execute("SELECT date, total_score, cycle_stage, confidence FROM cycle_quant")
    quant_map = {}
    for r in cur.fetchall():
        quant_map[r["date"]] = dict(r)

    # 从 cycle_comparison 获取小鲍判断
    cur.execute("SELECT date, bao_stage, quant_stage FROM cycle_comparison")
    comp_map = {}
    for r in cur.fetchall():
        comp_map[r["date"]] = dict(r)

    # 季节映射
    SEASON_MAP = {
        "冰点": "冰点",
        "复苏": "春",
        "主升": "夏",
        "过热": "秋",
        "退潮": "冬",
        "调整": "秋",
        "震荡": "秋",
    }

    RISK_MAP = {
        "冰点": "低",
        "复苏": "中",
        "主升": "高",
        "过热": "高",
        "退潮": "中",
        "调整": "中",
        "震荡": "中",
    }

    POSITION_MAP = {
        "冰点": "轻仓",
        "复苏": "中等",
        "主升": "重仓",
        "过热": "中等",
        "退潮": "轻仓",
        "调整": "轻仓",
        "震荡": "中等",
    }

    inserts = []
    for row in dim3_rows:
        date = row["date"]
        stage = row["emotion_stage"]
        if not stage:
            # 尝试从 cycle_comparison 获取
            if date in comp_map:
                stage = comp_map[date].get("bao_stage")

        if not stage:
            continue

        season = SEASON_MAP.get(stage, stage)
        risk = RISK_MAP.get(stage, "中")
        position = POSITION_MAP.get(stage, "中等")

        # 计算 emotion_score (从 cycle_quant 或简单映射)
        score = None
        if date in quant_map:
            score = quant_map[date].get("total_score")

        # 如果 quant 没有评分，简单映射
        if score is None:
            score_map = {"冰点": 10, "复苏": 30, "调整": 40, "主升": 80, "过热": 70, "退潮": 20, "震荡": 50}
            score = score_map.get(stage, 50)

        # up_down_ratio 解析
        up_down = row.get("up_down_ratio")
        up_down_val = 0
        if up_down:
            m = re.search(r'(\d+)\s*[:：]\s*(\d+)', str(up_down))
            if m:
                up_down_val = int(m.group(1)) / max(int(m.group(2)), 1)

        inserts.append({
            "date": date,
            "limit_up": row.get("limit_up"),
            "limit_down": row.get("limit_down"),
            "seal_rate": None,  # dim3 没有封板率字段
            "total_volume": row.get("volume_trillion"),
            "up_down_ratio": up_down_val,
            "emotion_score": score,
            "emotion_season": season,
            "risk_appetite": risk,
            "position_suggestion": position,
        })

    logger.info(f"\n1. emotion_cycle: 准备迁移 {len(inserts)} 条")
    if not dry_run:
        with ExecLogger("migrate_emotion_cycle", "batch_migrate", conn=conn) as elog:
            for item in inserts:
                cur.execute("""
                    INSERT OR REPLACE INTO emotion_cycle
                    (date, limit_up, limit_down, seal_rate, total_volume, up_down_ratio,
                     emotion_score, emotion_season, risk_appetite, position_suggestion)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    item["date"], item["limit_up"], item["limit_down"],
                    item["seal_rate"], item["total_volume"], item["up_down_ratio"],
                    item["emotion_score"], item["emotion_season"],
                    item["risk_appetite"], item["position_suggestion"],
                ))
            conn.commit()
            elog.update(rows_affected=len(inserts))
            logger.info(f"   ✅ 已写入 {len(inserts)} 条")
    else:
        # 打印样本
        seasons = defaultdict(int)
        for i in inserts:
            seasons[i["emotion_season"]] += 1
        logger.info(f"   季节分布: {dict(seasons)}")
        if inserts:
            logger.info(f"   样本: {inserts[0]}")

    if return_items:
        return inserts
    return len(inserts)


# ============================================================
# 2. hot_sectors 迁移
# ============================================================
def migrate_hot_sectors(conn, dry_run=True):
    cur = conn.cursor()

    # 从 dim2_sector_themes 提取热点板块
    cur.execute("SELECT date, hot_sectors, sectors_bullish, main_line, limit_up_count FROM dim2_sector_themes ORDER BY date")
    dim2_rows = [dict(r) for r in cur.fetchall()]

    inserts = []
    seen = set()

    for row in dim2_rows:
        date = row["date"]
        raw = row.get("hot_sectors") or row.get("sectors_bullish") or ""

        if not raw:
            continue

        # 尝试解析 JSON
        try:
            sectors = json.loads(raw)
            if isinstance(sectors, list):
                sector_list = sectors
            elif isinstance(sectors, str):
                sector_list = [sectors]
            else:
                sector_list = []
        except (json.JSONDecodeError, TypeError):
            # 不是 JSON，按逗号/顿号拆分
            sector_list = re.split(r'[,，、/|]', raw)
            sector_list = [s.strip() for s in sector_list if s.strip()]

        for i, sector in enumerate(sector_list[:5]):  # 只取 Top 5
            key = (date, sector)
            if key in seen:
                continue
            seen.add(key)

            inserts.append({
                "date": date,
                "rank": i + 1,
                "sector_name": sector[:50],
                "pct_change": None,
                "ts_code": None,
                "is_industry_logic": 0,
                "related_signal_id": None,
            })

    logger.info(f"\n2. hot_sectors: 准备迁移 {len(inserts)} 条")
    if not dry_run:
        with ExecLogger("migrate_hot_sectors", "batch_migrate", conn=conn) as elog:
            for item in inserts:
                cur.execute("""
                    INSERT OR REPLACE INTO hot_sectors
                    (date, rank, sector_name, pct_change, ts_code, is_industry_logic, related_signal_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    item["date"], item["rank"], item["sector_name"],
                    item["pct_change"], item["ts_code"],
                    item["is_industry_logic"], item["related_signal_id"],
                ))
            conn.commit()
            elog.update(rows_affected=len(inserts))
            logger.info(f"   ✅ 已写入 {len(inserts)} 条")
    else:
        # 打印样本
        if inserts:
            logger.info(f"   样本: {inserts[0]}")
            logger.info(f"   覆盖日期: {len(set(i['date'] for i in inserts))}")

    return len(inserts)


# ============================================================
# 3. daily_summary 批量生成
# ============================================================
def generate_daily_summaries(conn, dry_run=True, emotion_items=None):
    cur = conn.cursor()

    # 优先使用传入的 emotion_items（即将写入的数据）
    if emotion_items:
        ec_map = {item["date"]: item["emotion_season"] for item in emotion_items}
    else:
        cur.execute("SELECT date, emotion_season FROM emotion_cycle ORDER BY date")
        ec_map = {r["date"]: r["emotion_season"] for r in cur.fetchall()}

    cur.execute("SELECT date, sector_name, rank FROM hot_sectors WHERE rank <= 5 ORDER BY date, rank")
    hs_rows = cur.fetchall()
    hs_by_date = defaultdict(list)
    for r in hs_rows:
        hs_by_date[r["date"]].append(r["sector_name"])

    cur.execute("SELECT date, category, keyword FROM industry_signals ORDER BY date")
    sig_rows = cur.fetchall()
    sig_by_date = defaultdict(list)
    for r in sig_rows:
        sig_by_date[r["date"]].append(f"{r['category']}/{r['keyword']}")

    inserts = []
    for date in sorted(ec_map.keys()):
        hot_json = json.dumps(hs_by_date.get(date, []), ensure_ascii=False)
        sig_json = json.dumps(sig_by_date.get(date, [])[:5], ensure_ascii=False)

        inserts.append({
            "date": date,
            "emotion_season": ec_map[date],
            "hot_sectors": hot_json,
            "key_signals": sig_json,
            "information_gap": "[]",
            "notes": "",
        })

    logger.info(f"\n3. daily_summary: 准备生成 {len(inserts)} 条")
    if not dry_run:
        with ExecLogger("migrate_daily_summary", "batch_generate", conn=conn) as elog:
            for item in inserts:
                cur.execute("""
                    INSERT OR REPLACE INTO daily_summary
                    (date, emotion_season, hot_sectors, key_signals, information_gap, notes)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    item["date"], item["emotion_season"], item["hot_sectors"],
                    item["key_signals"], item["information_gap"], item["notes"],
                ))
            conn.commit()
            elog.update(rows_affected=len(inserts))
            logger.info(f"   ✅ 已写入 {len(inserts)} 条")
    else:
        if inserts:
            logger.info(f"   样本: date={inserts[0]['date']}, season={inserts[0]['emotion_season']}")

    return len(inserts)


# ============================================================
# Main
# ============================================================
def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="执行写入（默认 dry-run）")
    args = parser.parse_args()

    conn = get_conn()
    init_log_table(conn)

    logger.info("=" * 50)
    logger.info("🔄 全量迁移 — 基础数据")
    logger.info("=" * 50)

    n1_items = migrate_emotion_cycle(conn, dry_run=not args.execute, return_items=True)
    n2 = migrate_hot_sectors(conn, dry_run=not args.execute)
    n3 = generate_daily_summaries(conn, dry_run=not args.execute, emotion_items=n1_items)

    logger.info(f"\n{'='*50}")
    if args.execute:
        logger.info("✅ 迁移完成")
    else:
        logger.info("[dry-run] 未写入数据库，加 --execute 执行写入")

    # 打印迁移后统计
    if args.execute:
        cur = conn.cursor()
        for table in ["emotion_cycle", "hot_sectors", "daily_summary"]:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            logger.info(f"  {table}: {cur.fetchone()[0]} 条")

    conn.close()


if __name__ == "__main__":
    main()
