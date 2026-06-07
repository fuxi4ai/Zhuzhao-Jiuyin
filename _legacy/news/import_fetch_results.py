#!/usr/bin/env python3
from ..lib.logger import get_logger
logger = get_logger(__name__)
"""
新闻入库脚本 - 将抓取结果写入 news.db
用法: python3 import_fetch_results.py
"""

import json
import hashlib
import sqlite3
from datetime import datetime

# 读取 v2 抓取结果
with open('/home/admin/openclaw/workspace/temp/caixin_deep_fetch_v2.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

conn = sqlite3.connect('/home/admin/openclaw/workspace/news/db/news.db')
conn.row_factory = sqlite3.Row

raw_count = 0
skipped = 0

for art in data.get('articles', []):
    detail = art.get('detail', {})
    if isinstance(detail, dict) and 'error' in detail:
        skipped += 1
        continue

    full_text = detail.get('full_text', '') if isinstance(detail, dict) else ''
    if not full_text:
        skipped += 1
        continue

    title = art.get('title', '')
    content_hash = hashlib.md5(full_text.encode()).hexdigest()
    title_hash = hashlib.md5(title.encode()).hexdigest()

    # 检查是否已存在（去重）
    existing = conn.execute(
        "SELECT id FROM news_raw WHERE content_hash = ?",
        (content_hash,)
    ).fetchone()

    if existing:
        skipped += 1
        continue

    conn.execute("""
        INSERT INTO news_raw 
        (source, source_url, title, author, publish_time, fetch_time, 
         category, sub_category, content_type, raw_text, word_count, 
         content_hash, title_hash, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        'caixin',
        art.get('url', ''),
        title,
        detail.get('author', ''),
        detail.get('publish_time', ''),
        data.get('fetch_time', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        art.get('category', ''),
        '',
        art.get('source', ''),
        full_text,
        detail.get('word_count', len(full_text)),
        content_hash,
        title_hash,
        'raw'
    ))
    raw_count += 1

conn.commit()
conn.close()

logger.info(f"✅ 入库完成: {raw_count} 篇新增, {skipped} 篇跳过")
