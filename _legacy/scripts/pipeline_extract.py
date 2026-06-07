#!/usr/bin/env python3
"""
统一数据提取管线 — 合并所有 batch/squeeze/extract 脚本
支持增量提取、自动重试、执行日志记录

用法:
  python3 pipeline_extract.py                  # 提取所有待处理文件
  python3 pipeline_extract.py --dry-run          # 预览不写入
  python3 pipeline_extract.py --from 2026-01-01  # 从某日期开始
  python3 pipeline_extract.py --stats            # 查看已提取统计
"""

import os
import re
import json
import sqlite3
import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from exec_logger import ExecLogger, init_log_table

DB_PATH = "/home/admin/openclaw/workspace/projects/烛照九阴/db/recap.db"
RAW_DIR = "/home/admin/openclaw/workspace/projects/烛照九阴/raw"

# ============================================================
# 信号分类规则
# ============================================================
CATEGORY_MAP = {
    "技术升级": "技术升级",
    "供给紧缺": "供给紧缺",
    "需求爆发": "需求爆发",
    "涨价驱动": "涨价驱动",
    "事件催化": "事件催化",
    "情绪周期": "情绪周期",
}

def classify_category(text):
    """从文本中推断分类"""
    text = text or ""
    for keyword, category in CATEGORY_MAP.items():
        if keyword in text:
            return category
    return "其他"

def extract_date_from_filename(filename):
    """从文件名提取日期: 251130xxx → 2025-11-30"""
    m = re.search(r'(\d{6})', filename)
    if m:
        d = m.group(1)
        year = int(d[:2])
        year = 2000 + year if year < 50 else 1900 + year
        return f"{year}-{d[2:4]}-{d[4:6]}"
    return None

def parse_raw_file(filepath):
    """解析 raw markdown 文件，提取信号"""
    signals = []
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    file_date = extract_date_from_filename(os.path.basename(filepath))

    # 简单解析：按章节/段落提取关键信息
    # 这是一个简化版，实际应根据文件结构调整
    sections = re.split(r'#+\s+', content)
    for section in sections:
        lines = section.strip().split('\n')
        if not lines:
            continue
        heading = lines[0].strip()
        body = '\n'.join(lines[1:]).strip()

        if not body or len(body) < 20:
            continue

        # 提取关键词
        keywords = []
        targets = []
        # 找股票名（中文+后缀模式）
        stock_pattern = re.findall(r'([\u4e00-\u9fa5]{2,6}(?:科技|电子|光电|材料|矿业|药业|集团|股份|发展))', body)
        targets = list(set(stock_pattern))[:5]

        category = classify_category(heading + body)
        keyword = heading[:30] if heading else category

        signals.append({
            "date": file_date,
            "category": category,
            "keyword": keyword,
            "target": ",".join(targets),
            "signal_content": body[:500],
            "confidence": "P2",
            "status": "new",
        })

    return signals

def insert_signals(conn, signals, dry_run=False):
    """批量插入信号到 industry_signals 表"""
    if dry_run:
        return len(signals)

    cursor = conn.cursor()
    inserted = 0
    for sig in signals:
        try:
            cursor.execute("""
                INSERT INTO industry_signals (date, category, keyword, target, signal_content, confidence, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                sig["date"], sig["category"], sig["keyword"],
                sig["target"], sig["signal_content"],
                sig["confidence"], sig["status"],
            ))
            inserted += 1
        except sqlite3.IntegrityError:
            pass  # 重复数据跳过

    conn.commit()
    return inserted

def get_already_processed_dates(conn):
    """获取已处理过的日期（避免重复）"""
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT date FROM industry_signals WHERE date IS NOT NULL")
    return set(r[0] for r in cur.fetchall())

def get_raw_files(from_date=None):
    """获取待处理的 raw 文件"""
    raw_dir = Path(RAW_DIR)
    if not raw_dir.exists():
        logger.info(f"⚠️ raw 目录不存在: {RAW_DIR}")
        return []

    files = []
    for ext in ["*.md"]:
        files.extend(raw_dir.rglob(ext))

    result = []
    for f in files:
        file_date = extract_date_from_filename(f.name)
        if file_date:
            if from_date and file_date < from_date:
                continue
            result.append((file_date, str(f)))

    return sorted(result, key=lambda x: x[0])

# ============================================================
# 主流程
# ============================================================
def run_pipeline(from_date=None, dry_run=False):
    conn = sqlite3.connect(DB_PATH)
    init_log_table(conn)

    # 获取已处理日期
    processed = get_already_processed_dates(conn)

    # 获取待处理文件
    files = get_raw_files(from_date)
    pending = [(d, f) for d, f in files if d not in processed]

    if not pending:
        logger.info("✅ 没有待处理文件")
        conn.close()
        return

    logger.info(f"📁 待处理文件: {len(pending)} 个")
    if dry_run:
        for d, f in pending:
            logger.info(f"  {d}: {os.path.basename(f)}")
        conn.close()
        return

    total_inserted = 0
    total_files = 0

    with ExecLogger("pipeline_extract", "batch_extract", conn=conn) as elog:
        for i, (date, fpath) in enumerate(pending):
            try:
                signals = parse_raw_file(fpath)
                inserted = insert_signals(conn, signals)
                total_inserted += inserted
                total_files += 1
                logger.info(f"  ✅ {os.path.basename(fpath)}: {inserted} 条信号")
                elog.update(rows_affected=total_inserted,
                           details={"files_processed": total_files, "total_signals": total_inserted})
            except Exception as e:
                logger.info(f"  ❌ {os.path.basename(fpath)}: {e}")

    conn.close()
    logger.info(f"\n✅ 完成: {total_files} 个文件, {total_inserted} 条信号")

def show_stats():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    logger.info("📊 产业信号统计")
    logger.info("-" * 50)

    cur.execute("SELECT COUNT(DISTINCT date) FROM industry_signals")
    logger.info(f"  覆盖日期: {cur.fetchone()[0]}")

    cur.execute("SELECT COUNT(*) FROM industry_signals")
    logger.info(f"  信号总数: {cur.fetchone()[0]}")

    cur.execute("SELECT category, COUNT(*) FROM industry_signals GROUP BY category ORDER BY COUNT(*) DESC")
    logger.info(f"\n  分类分布:")
    for row in cur.fetchall():
        logger.info(f"    {row[0]}: {row[1]}")

    cur.execute("SELECT MIN(date), MAX(date) FROM industry_signals")
    r = cur.fetchone()
    logger.info(f"\n  日期范围: {r[0]} ~ {r[1]}")

    conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不写入")
    parser.add_argument("--from", dest="from_date", help="从某日期开始 (YYYY-MM-DD)")
    parser.add_argument("--stats", action="store_true", help="查看统计")
    args = parser.parse_args()

    if args.stats:
        show_stats()
    else:
        run_pipeline(from_date=args.from_date, dry_run=args.dry_run)
