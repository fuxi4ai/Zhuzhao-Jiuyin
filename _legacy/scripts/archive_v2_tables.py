#!/usr/bin/env python3
"""
v2 旧表归档 — 导出为 SQL 文件，归档到 dragon-palace/

用法:
  python3 archive_v2_tables.py              # dry-run 预览
  python3 archive_v2_tables.py --execute     # 执行归档
"""

import os
import sys
import sqlite3
import shutil
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from exec_logger import ExecLogger, init_log_table

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'db', 'recap.db')
ARCHIVE_DIR = os.path.join(os.path.dirname(__file__), '..', 'dragon-palace', 'v2-archive')

# v2 旧表列表（保留不归档的表除外）
V2_TABLES = [
    'dim1_external_pricing',
    'dim2_sector_themes',
    'dim2p_supply_demand',
    'dim3_sentiment_tech',
    'dim4_trade_plan',
    'dim4_stock_analysis',
    'cycle_quant',
    'cycle_comparison',
    'recap_daily',
    'recap_summary',
    'recap_guide',
    'sector_alias',
    'stock_master',
    'stock_tracking',
    'prediction_log',
    'logic_type_mapping',
]

# 保留不归档的表
KEEP_TABLES = [
    'tushare_index', 'tushare_limit', 'tushare_north', 'tushare_stats',
    'emotion_cycle', 'industry_signals', 'hot_sectors',
    'information_gap', 'daily_summary', 'predictor_accuracy',
    'execution_log', 'sqlite_sequence',
]


def archive_tables(dry_run=True):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 获取实际存在的旧表
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    all_tables = set(r["name"] for r in cur.fetchall())
    v2_exists = [t for t in V2_TABLES if t in all_tables]

    logger.info(f"📦 待归档表: {len(v2_exists)} 个")
    total_rows = 0

    for t in v2_exists:
        cur.execute(f"SELECT COUNT(*) FROM [{t}]")
        cnt = cur.fetchone()[0]
        total_rows += cnt
        logger.info(f"  {t}: {cnt} 条")

    if dry_run:
        logger.info(f"\n[dry-run] 共 {total_rows} 条记录，加 --execute 执行归档")
        conn.close()
        return

    # 创建归档目录
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_db = os.path.join(ARCHIVE_DIR, f"v2_tables_{timestamp}.db")

    total_exported = 0

    with ExecLogger("archive_v2_tables", "archive", conn=conn) as elog:
        archive_conn = sqlite3.connect(archive_db)
        archive_cur = archive_conn.cursor()

        for table in v2_exists:
            # 导出 CREATE TABLE
            cur.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table}'")
            create_sql = cur.fetchone()
            if create_sql:
                archive_cur.execute(create_sql[0])

            # 导出数据
            cur.execute(f"SELECT * FROM [{table}]")
            rows = cur.fetchall()
            if rows:
                cols = rows[0].keys()
                placeholders = ", ".join(["?"] * len(cols))
                col_names = ", ".join(cols)
                for row in rows:
                    archive_cur.execute(f"INSERT INTO [{table}] ({col_names}) VALUES ({placeholders})", tuple(row))
                archive_conn.commit()

            total_exported += len(rows)
            logger.info(f"  ✅ {table}: {len(rows)} 条已归档")

        archive_conn.close()
        elog.update(rows_affected=total_exported)

    # 压缩归档文件
    archive_size = os.path.getsize(archive_db)
    logger.info(f"\n✅ 归档完成: {archive_db}")
    logger.info(f"   文件大小: {archive_size / 1024:.1f} KB")
    logger.info(f"   总记录数: {total_exported}")

    conn.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="执行归档")
    args = parser.parse_args()
    archive_tables(dry_run=not args.execute)
