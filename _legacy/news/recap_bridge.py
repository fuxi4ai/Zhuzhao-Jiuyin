#!/usr/bin/env python3
from ..lib.logger import get_logger
logger = get_logger(__name__)
"""
新闻模块 → recap 数据库桥接
将清洗后的新闻数据填充到 recap 数据库的 Dim3 字段
"""

import json
import sqlite3
from datetime import datetime

NEWS_DB = '/home/admin/openclaw/workspace/news/db/news.db'
RECAP_DB = '/home/admin/openclaw/workspace/projects/烛照九阴/db/recap.db'


def query_news_by_date(date, category=None):
    """按日期查询清洗后的新闻"""
    conn = sqlite3.connect(NEWS_DB)
    conn.row_factory = sqlite3.Row

    sql = "SELECT * FROM news_cleaned WHERE quality_score >= 40"
    params = []

    if date:
        sql += " AND publish_time LIKE ?"
        params.append(f"{date}%")

    if category:
        sql += " AND category = ?"
        params.append(category)

    sql += " ORDER BY quality_score DESC"

    articles = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.close()
    return articles


def generate_recap_input(date=None):
    """生成可供 recap 录入的结构化数据"""
    categories = ['AI', '半导体', '大宗商品', '地缘政治']
    output = {}

    for cat in categories:
        articles = query_news_by_date(date, cat)
        high_quality = [a for a in articles if a['quality_score'] >= 50]

        output[cat] = {
            'total_articles': len(articles),
            'high_quality': len(high_quality),
            'articles': [{
                'title': a['title'],
                'summary': a['summary'],
                'quality_score': a['quality_score'],
                'category': a['category'],
                'sub_category': a['sub_category'],
                'stocks': json.loads(a['stocks_mentioned']) if a['stocks_mentioned'] else [],
                'price_signals': json.loads(a['price_signals']) if a['price_signals'] else [],
                'url': next((s for s in json.loads(a['source_ids']) if s), ''),
            } for a in high_quality],
            'price_signals': [],
            'policy_signals': [],
        }

        # 提取价格信号
        for a in high_quality:
            if a['price_signals']:
                output[cat]['price_signals'].extend(json.loads(a['price_signals']))

    return output


if __name__ == '__main__':
    result = generate_recap_input()
    logger.info(json.dumps(result, ensure_ascii=False, indent=2))
