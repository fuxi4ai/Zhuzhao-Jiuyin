#!/usr/bin/env python3
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))
import config
from lib.logger import get_logger
logger = get_logger(__name__)
"""
新闻清洗器 - 去重 + 分类 + 评分 + 结构化提取
用法: python3 news_cleaner.py [--dry-run]
"""

import json
import sqlite3
import hashlib
from datetime import datetime
from difflib import SequenceMatcher
from collections import defaultdict

DB_PATH = config.NEWS_DB

# ============================================================
# 配置：分类关键词
# ============================================================

CATEGORIES = {
    'AI': {
        'keywords': ['AI', '人工智能', '大模型', 'LLM', '算力', 'GPU', '智能体',
                     '英伟达', 'NVIDIA', 'OpenAI', 'Claude', '文心', '通义',
                     '深度学习', 'Transformer', 'Skill化', '数字员工',
                     'AI芯片', 'AI服务器', '智算中心', 'AI基础设施'],
        'sub_categories': ['政策', '技术突破', '融资', '产品', '人才', '投资逻辑', '监管'],
    },
    '半导体': {
        'keywords': ['半导体', '芯片', 'Chip', '台积电', '中芯国际', '封装', 'CoWoS',
                     'HBM', '存储芯片', '光模块', 'CPO', '光刻', 'EUV', '晶圆',
                     '先进封装', '长电科技', '华虹', '海光', '寒武纪', '昇腾',
                     '内存', 'DRAM', 'NAND', 'SOC'],
        'sub_categories': ['产能', '价格', '技术', '制裁', '出口', '周期'],
    },
    '大宗商品': {
        'keywords': ['大宗商品', '原油', '黄金', '铜', '铁矿石', '碳酸锂', '锂价',
                     '煤炭', '天然气', 'OPEC', '欧佩克', '石油', '期货',
                     '商品指数', 'CCI', '能源', '储能'],
        'sub_categories': ['价格', '供需', '政策', '制裁', '地缘影响', '技术'],
    },
    '地缘政治': {
        'keywords': ['地缘', '霍尔木兹', '伊朗', '海峡', '中东', '中美', '特朗普',
                     '访华', '关税', '贸易战', '制裁', '停火', '美伊',
                     '美联储', '沃什', '鲍威尔', '汇率', '人民币',
                     '俄乌', '北约', '欧佩克', '供应链'],
        'sub_categories': ['冲突', '谈判', '政策', '制裁', '贸易', '货币政策'],
    },
}

# 标的关键词映射
STOCK_KEYWORDS = {
    '天齐锂业': ['天齐锂业'],
    '天华新能': ['天华新能'],
    '盛新锂能': ['盛新锂能'],
    '宁德时代': ['宁德时代'],
    '恒力石化': ['恒力石化'],
    '中国石油': ['中国石油', '中石油'],
    '中国石化': ['中国石化', '中石化'],
    '百度': ['百度', '文心'],
    '中芯国际': ['中芯国际', 'SMIC'],
    '台积电': ['台积电', 'TSMC'],
}

# ============================================================
# 1. 去重
# ============================================================

def dedup_articles(articles):
    """基于标题 + 正文相似度去重"""
    if not articles:
        return []

    deduped = []
    for art in articles:
        is_dup = False
        title = art.get('title', '')
        text = art.get('raw_text', '')

        for existing in deduped:
            # 标题相似度
            title_sim = SequenceMatcher(None, title, existing.get('title', '')).ratio()
            # 正文相似度（截断到 500 字）
            text_sim = SequenceMatcher(None, text[:500], existing.get('raw_text', '')[:500]).ratio()

            if title_sim > 0.9 or text_sim > 0.85:
                is_dup = True
                # 保留字数更多的版本
                if len(text) > len(existing.get('raw_text', '')):
                    idx = deduped.index(existing)
                    deduped[idx] = art
                break

        if not is_dup:
            deduped.append(art)

    return deduped


# ============================================================
# 2. 分类
# ============================================================

def classify_article(title, text):
    """自动分类：大类 + 子类"""
    # 标题权重 3x
    combined = f"{title} {title} {title} {text[:1000]}"

    # 加权关键词
    WEIGHTED_KEYWORDS = {
        '半导体': {'台积电': 5, '中芯国际': 5, '芯片': 3, '封装': 3, 'CoWoS': 5,
                   'HBM': 5, '存储芯片': 3, '晶圆': 3, '半导体': 4, '光刻': 4},
        '大宗商品': {'碳酸锂': 5, '锂价': 5, '原油': 3, '石油': 3, 'OPEC': 5,
                     '欧佩克': 5, '煤炭': 3, '天然气': 3, '大宗商品': 3, 'CCI': 5,
                     '能源进口': 3, '大宗商品指数': 5},
        '地缘政治': {'美伊': 5, '霍尔木兹': 5, '停火': 4, '访华': 5, '沃什': 5,
                     '美联储': 4, '中美': 3, '地缘': 4, '博弈': 4, '冲突': 3,
                     '谈判': 3, '制裁': 2},
        'AI': {'人工智能': 3, '大模型': 4, 'LLM': 4, '算力': 3,
               'OpenAI': 4, 'Claude': 4, '智能体': 4, '文心': 4, 'Skill化': 5},
    }

    # 排除词：某些词出现时应降低对应类别
    EXCLUDE_HINTS = {
        '大宗商品': ['特朗普', '谈判', '战争'],  # 地缘相关的石油新闻
        '地缘政治': ['指数', '期货', '价格'],  # 大宗商品相关的价格新闻
    }

    best_cat = None
    best_score = 0
    matched_keywords = []

    for cat, config in CATEGORIES.items():
        score = 0
        cat_keywords = []
        weights = WEIGHTED_KEYWORDS.get(cat, {})
        for kw in config['keywords']:
            if kw in combined:
                w = weights.get(kw, 1)
                score += w
                cat_keywords.append(kw)

        # 排除词减分
        for hint in EXCLUDE_HINTS.get(cat, []):
            if hint in combined:
                score -= 2

        if score > best_score:
            best_score = score
            best_cat = cat
            matched_keywords = cat_keywords

    # 子类判断
    sub_cat = ''
    if best_cat:
        for sc in CATEGORIES[best_cat]['sub_categories']:
            if sc in combined:
                sub_cat = sc
                break

    return best_cat, sub_cat, matched_keywords


# ============================================================
# 3. 质量评分
# ============================================================

def score_article(art):
    """信息密度评分 (0-100)"""
    text = art.get('raw_text', '')
    word_count = len(text)
    content_type = art.get('content_type', '')

    score = 0

    # 字数 (0-20)
    if word_count > 1000:
        score += 20
    elif word_count > 500:
        score += 15
    elif word_count > 200:
        score += 10
    else:
        score += 5

    # 内容类型 (0-30)
    type_scores = {
        '深度': 30, '周刊': 25, '专栏': 20,
        '深度专题': 28, '深度报道': 28,
        '市场洞察': 18, '行业速递': 15,
        '霍尔木兹日报': 18, 'CCI快报': 15,
        '能源内参': 15, '华尔街原声': 20,
        '封面报道': 25, '周刊封面': 25,
        '财新观察': 22,
        'T早报': 5, '快讯': 5,
    }
    for t, s in type_scores.items():
        if t in content_type:
            score += s
            break
    else:
        score += 10

    # 数据密度 (0-20) - 有具体数字
    import re
    numbers = re.findall(r'\d+\.?\d*%', text)
    numbers += re.findall(r'\d+\s*[万亿亿元]', text)
    if len(numbers) >= 3:
        score += 20
    elif len(numbers) >= 1:
        score += 10

    # 信源权威 (0-15)
    if 'weekly.caixin.com' in art.get('source_url', ''):
        score += 15
    elif 'opinion.caixin.com' in art.get('source_url', ''):
        score += 12
    elif 'caixin.com' in art.get('source_url', ''):
        score += 10

    # 分析深度 (0-15) - 有分析性关键词
    analysis_keywords = ['因为', '因此', '意味着', '影响', '驱动', '逻辑', '趋势',
                         '预计', '预计将', '展望', '分析', '核心是', '关键在于',
                         '重塑', '格局', '博弈', '范式', '系统', '冲击', '挑战',
                         '不确定性', '韧性', '自主', '重构']
    analysis_count = sum(1 for kw in analysis_keywords if kw in text)
    score += min(analysis_count * 3, 15)

    return min(score, 100)


# ============================================================
# 4. 实体 & 标的提取
# ============================================================

def extract_stocks(text):
    """提取提及的股票"""
    mentioned = []
    for stock, keywords in STOCK_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                mentioned.append(stock)
                break
    return list(set(mentioned))


def extract_price_signals(text):
    """提取价格信号"""
    import re
    signals = []
    patterns = [
        (r'(\w+?)\s*(?:吨价|价格)\s*[\u8feb\u8dcc\u6da8\u5347\u964d]\s*([\d.]+)\s*[\u4e07\u5143\u4ebf]', 'commodity_price'),
        (r'(?:同比|环比)\s*(\w+?)\s*([\u6da8\u8dcc]+)\s*([\d.]+)%?', 'yoy_change'),
        (r'(\w+?)\s*(?:领跌|领涨)\s*([\d.]+)%?', 'lead_change'),
    ]
    for pattern, signal_type in patterns:
        matches = re.findall(pattern, text)
        for m in matches:
            signals.append({'type': signal_type, 'values': list(m)})
    return signals


# ============================================================
# 主流程
# ============================================================

def run_cleaner(dry_run=False):
    """执行清洗流程"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # 1. 获取 raw 状态的文章
    raw_articles = conn.execute(
        "SELECT * FROM news_raw WHERE status = 'raw' ORDER BY id"
    ).fetchall()

    if not raw_articles:
        logger.info("ℹ️  没有待清洗的文章")
        conn.close()
        return

    logger.info(f"📥 待清洗: {len(raw_articles)} 篇")

    # 转为 dict
    articles = [dict(r) for r in raw_articles]

    # 2. 去重
    before_dedup = len(articles)
    articles = dedup_articles(articles)
    after_dedup = len(articles)
    logger.info(f"🔄 去重: {before_dedup} → {after_dedup} 篇 (去掉了 {before_dedup - after_dedup} 篇)")

    # 3. 分类 + 评分 + 提取 → 写入 cleaned
    for art in articles:
        title = art['title']
        text = art['raw_text']

        # 分类
        category, sub_cat, keywords = classify_article(title, text)
        if not category:
            category = '其他'

        # 评分
        quality = score_article(art)

        # 标的提取
        stocks = extract_stocks(text)

        # 价格信号
        price_signals = extract_price_signals(text)

        # 生成摘要（取前 200 字）
        summary = text[:200] if text else ''

        # 判断是否深度
        is_deep = quality >= 60

        if dry_run:
            logger.info(f"  [{art['id']}] {title[:40]}... | {category} | 评分:{quality} | 标的:{stocks}")
            continue

        # 写入 cleaned
        conn.execute("""
            INSERT INTO news_cleaned
            (source_ids, title, publish_time, category, sub_category, content_type,
             summary, key_points, full_text, word_count,
             entities, stocks_mentioned, price_signals, policy_signals, sentiment,
             quality_score, is_deep)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            json.dumps([art['id']]),
            title,
            art.get('publish_time', ''),
            category,
            sub_cat,
            art.get('content_type', ''),
            summary,
            json.dumps(keywords[:5]),
            text,
            art.get('word_count', len(text)),
            json.dumps({'keywords': keywords}),
            json.dumps(stocks),
            json.dumps(price_signals),
            json.dumps([]),
            'neutral',
            quality,
            1 if is_deep else 0
        ))

        # 更新 raw 状态
        conn.execute("UPDATE news_raw SET status = 'cleaned' WHERE id = ?", (art['id'],))

    if not dry_run:
        conn.commit()
        cleaned_count = conn.execute("SELECT COUNT(*) FROM news_cleaned").fetchone()[0]
        logger.info(f"✅ 清洗完成，news_cleaned 共 {cleaned_count} 篇")
    else:
        logger.info(f"🔍 Dry run 完成，未写入数据库")

    conn.close()


if __name__ == '__main__':
    import sys
    dry_run = '--dry-run' in sys.argv
    run_cleaner(dry_run=dry_run)
