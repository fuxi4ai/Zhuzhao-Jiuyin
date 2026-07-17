#!/usr/bin/env python3
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))
import config
from lib.logger import get_logger
logger = get_logger(__name__)
"""
recap_bridge v2.0 - 使用财新 Bridge API 补充 recap 数据库
===========================================================
功能：
1. 从 caixin_bridge 获取实时/历史数据
2. 映射到 recap.db 的 Dim1/Dim2/Dim3 字段
3. 注意时间对应：bridge 提供的是当前数据，需要与 recap 的 date 字段匹配

数据映射：
┌─────────────────┬──────────────────────────┬─────────────────────────┐
│ Bridge API      │ → recap 表                │ → 字段                  │
├─────────────────┼──────────────────────────┼─────────────────────────┤
│ caixin_market   │ dim1_external_pricing     │ key_signals, pricing    │
│ _overview       │                          │ _direction              │
├─────────────────┼──────────────────────────┼─────────────────────────┤
│ caixin_index    │ dim1_external_pricing     │ hang_seng, nasdaq       │
│ _rank           │                          │                         │
├─────────────────┼──────────────────────────┼─────────────────────────┤
│ caixin_hk       │ dim1_external_pricing     │ hang_seng (补充)        │
│ _indices        │                          │                         │
├─────────────────┼──────────────────────────┼─────────────────────────┤
│ caixin_industry │ dim2_sector_themes        │ hot_sectors, price      │
│ _rank           │                          │ _catalyst               │
├─────────────────┼──────────────────────────┼─────────────────────────┤
│ caixin_hot      │ dim3_sentiment_tech       │ news_catalysts          │
│ _stocks         │                          │                         │
├─────────────────┼──────────────────────────┼─────────────────────────┤
│ caixin_hk       │ dim2_sector_themes        │ 港股板块 (新维度)        │
│ _industry       │                          │                         │
└─────────────────┴──────────────────────────┴─────────────────────────┘

用法：
  python3 recap_bridge_v2.py              # 补充今天的数据
  python3 recap_bridge_v2.py --date 2026-05-10  # 补充指定日期
  python3 recap_bridge_v2.py --dry-run    # 预览不写入
"""

import json
import sqlite3
import requests
import sys
from datetime import datetime

BRIDGE_URL = "http://localhost:8765/invoke"
RECAP_DB = config.RECAP_DB
NEWS_DB = config.NEWS_DB


def bridge_call(tool, args={}):
    """调用 bridge API"""
    try:
        r = requests.post(BRIDGE_URL, json={"tool": tool, "args": args}, timeout=10)
        return r.json()
    except Exception as e:
        logger.info(f"⚠️ Bridge 调用失败 ({tool}): {e}")
        return None


def get_market_data():
    """获取 A 股主要指数行情"""
    d = bridge_call("caixin_market_overview")
    if not d or not d.get("data"):
        return None

    market = {}
    for m in d["data"].get("marketData", []):
        name = m.get("indShortName", "")
        market[name] = {
            "price": m.get("curPrice"),
            "change": m.get("changeRate"),
            "updown": m.get("priceUpdown1"),
        }

    return market


def get_hk_indices():
    """获取港股指数"""
    d = bridge_call("caixin_hk_indices")
    if not d or not d.get("data"):
        return None

    indices = {}
    for s in d["data"]:
        name = s.get("prodName", "")
        indices[name] = {
            "price": s.get("curPrice"),
            "change": s.get("changeRate"),
        }

    return indices


def get_industry_rank():
    """获取行业板块排行"""
    d = bridge_call("caixin_industry_rank", {"size": 10, "type": "changeRate"})
    if not d or not d.get("data"):
        return None

    industries = []
    for ind in d["data"][:10]:
        industries.append({
            "name": ind.get("induClassName", ""),
            "change": ind.get("changeRate", 0),
            "leader": ind.get("leadShortName", ""),
            "leader_change": ind.get("leadChangeRate", 0),
            "total_value": ind.get("totValue", 0),
        })

    return industries


def get_hk_industry():
    """获取港股行业排行"""
    d = bridge_call("caixin_hk_industry", {"size": 10, "orderField": "changeRate"})
    if not d or not d.get("data"):
        return None

    industries = []
    for ind in d["data"][:10]:
        industries.append({
            "name": ind.get("induClassName", ""),
            "change": ind.get("changeRate", 0),
        })

    return industries


def get_hot_stocks():
    """获取热门股票"""
    d = bridge_call("caixin_hot_stocks", {"size": 15})
    if not d or not isinstance(d, list):
        return None

    stocks = []
    for s in d[:15]:
        stocks.append({
            "name": s.get("name", ""),
            "code": s.get("code", ""),
            "hotness": s.get("sumNum", 0),
        })

    return stocks


def get_news_articles(category=None, date=None, days_back=7):
    """从 news.db 获取清洗后的新闻（默认拉取最近 N 天）"""
    conn = sqlite3.connect(NEWS_DB)
    conn.row_factory = sqlite3.Row

    sql = "SELECT * FROM news_cleaned WHERE quality_score >= 40"
    params = []

    if date and days_back:
        # 拉取 date 前后 days_back 天内的新闻
        sql += " AND publish_time >= date(?, ?)"
        params.extend([date, f"-{days_back} days"])
    elif date:
        sql += " AND publish_time LIKE ?"
        params.append(f"{date}%")

    if category:
        sql += " AND category = ?"
        params.append(category)

    sql += " ORDER BY quality_score DESC"

    articles = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.close()
    return articles


def supplement_dim1(date, market, hk_indices, dry_run=False):
    """补充 Dim1 外部定价"""
    conn = sqlite3.connect(RECAP_DB)

    # 检查是否已有今天的数据
    existing = conn.execute(
        "SELECT id FROM dim1_external_pricing WHERE date = ?", (date,)
    ).fetchone()

    if not existing:
        # 创建新记录
        conn.execute("""
            INSERT INTO dim1_external_pricing (date) VALUES (?)
        """, (date,))
        row_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    else:
        row_id = existing[0]

    # 构建 key_signals
    signals = []
    if market:
        for name, data in market.items():
            signals.append(f"{name}: {data['price']:.2f} ({data['change']:+.2f}%)")
    if hk_indices:
        for name, data in hk_indices.items():
            signals.append(f"{name}: {data['price']:.2f} ({data['change']:+.2f}%)")

    # 定价方向判断
    a_trend = "bullish" if market and market.get("上证指数", {}).get("change", 0) > 0 else "bearish"
    hk_trend = "neutral"
    if hk_indices:
        hs_change = hk_indices.get("恒生指数", {}).get("change", 0)
        hk_trend = "bullish" if hs_change > 0.5 else "bearish" if hs_change < -0.5 else "neutral"

    key_signals_json = json.dumps({"a_share": signals[:6], "hk": signals[6:12]}, ensure_ascii=False)
    pricing_direction = f"A股:{a_trend} | 港股:{hk_trend}"

    # 恒生指数
    hang_seng = hk_indices.get("恒生指数", {}).get("price") if hk_indices else None

    # 市场联动
    linkage = "A股半导体/电子领涨" if market else "数据缺失"

    if not dry_run:
        conn.execute("""
            UPDATE dim1_external_pricing
            SET key_signals = ?, pricing_direction = ?, hang_seng = ?,
                market_linkage = ?
            WHERE id = ?
        """, (key_signals_json, pricing_direction, hang_seng, linkage, row_id))
        conn.commit()
        logger.info(f"  ✅ Dim1 已更新 (id={row_id})")
    else:
        logger.info(f"  🔍 Dim1 预览:")
        logger.info(f"    signals: {signals[:5]}...")
        logger.info(f"    direction: {pricing_direction}")

    conn.close()


def supplement_dim2(date, industries, hk_industries, dry_run=False):
    """补充 Dim2 行业主线"""
    conn = sqlite3.connect(RECAP_DB)

    existing = conn.execute(
        "SELECT id FROM dim2_sector_themes WHERE date = ?", (date,)
    ).fetchone()

    if not existing:
        conn.execute("""
            INSERT INTO dim2_sector_themes (date) VALUES (?)
        """, (date,))
        row_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    else:
        row_id = existing[0]

    # 领涨行业
    hot = []
    for ind in (industries or [])[:5]:
        hot.append(f"{ind['name']}({ind['change']:+.2f}%)龙头:{ind['leader']}")

    # 港股行业
    hk_hot = []
    for ind in (hk_industries or [])[:5]:
        hk_hot.append(f"{ind['name']}({ind['change']:+.2f}%)")

    hot_sectors = json.dumps(hot, ensure_ascii=False)
    price_catalyst = f"港股领涨:{','.join(hk_hot[:3])}" if hk_hot else "暂无"

    if not dry_run:
        conn.execute("""
            UPDATE dim2_sector_themes
            SET hot_sectors = ?, price_catalyst = ?
            WHERE id = ?
        """, (hot_sectors, price_catalyst, row_id))
        conn.commit()
        logger.info(f"  ✅ Dim2 已更新 (id={row_id})")
    else:
        logger.info(f"  🔍 Dim2 预览:")
        logger.info(f"    hot_sectors: {hot}")
        logger.info(f"    price_catalyst: {price_catalyst}")

    conn.close()


def supplement_dim3(date, hot_stocks, news_articles, dry_run=False):
    """补充 Dim3 情绪技术"""
    conn = sqlite3.connect(RECAP_DB)

    existing = conn.execute(
        "SELECT id FROM dim3_sentiment_tech WHERE date = ?", (date,)
    ).fetchone()

    if not existing:
        conn.execute("""
            INSERT INTO dim3_sentiment_tech (date) VALUES (?)
        """, (date,))
        row_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    else:
        row_id = existing[0]

    # 热门股票 → news_catalysts
    catalysts = []
    if hot_stocks:
        for s in hot_stocks[:5]:
            catalysts.append(f"{s['name']}({s['code']})热度:{s['hotness']}")

    # 新闻 → policy_news + industry_logic
    policies = []
    industry_logics = []
    for art in (news_articles or [])[:5]:
        if art.get("quality_score", 0) >= 50:
            title = art.get("title", "")
            summary = art.get("summary", "")[:100]
            cat = art.get("category", "")
            if cat in ["地缘政治", "大宗商品"]:
                policies.append(f"[{cat}] {title}")
            else:
                industry_logics.append(f"[{cat}] {title}")

    news_catalysts = json.dumps(catalysts, ensure_ascii=False)
    policy_news = json.dumps(policies, ensure_ascii=False)
    industry_logic = json.dumps(industry_logics, ensure_ascii=False)

    if not dry_run:
        conn.execute("""
            UPDATE dim3_sentiment_tech
            SET news_catalysts = ?, policy_news = ?, industry_logic = ?
            WHERE id = ?
        """, (news_catalysts, policy_news, industry_logic, row_id))
        conn.commit()
        logger.info(f"  ✅ Dim3 已更新 (id={row_id})")
    else:
        logger.info(f"  🔍 Dim3 预览:")
        logger.info(f"    catalysts: {catalysts}")
        logger.info(f"    policies: {policies[:3]}...")
        logger.info(f"    industry: {industry_logics[:3]}...")

    conn.close()


def run(date=None, dry_run=False):
    """主流程

    ⚠️ 时间对应规则：
    - bridge API 返回的是**实时数据**（当前时刻的市场快照）
    - 因此只能补充 **今天（交易日）** 的 recap 记录
    - 历史日期的数据必须通过 tushare 等历史数据库获取
    - news.db 中的新闻按 publish_time 匹配日期，不受此限制
    """
    today = datetime.now().strftime("%Y-%m-%d")

    if not date:
        date = today

    # 检查：如果请求的不是今天，bridge 实时数据不适用
    if date != today:
        logger.info(f"⚠️  警告：bridge API 只返回实时数据，不能用于历史日期 {date}")
        logger.info(f"   当前时间: {today}")
        logger.info(f"   bridge 行情数据将被跳过（仅补充 news.db 新闻）")

    use_bridge = (date == today)

    logger.info("=" * 60)
    logger.info(f"recap_bridge v2.0 - 财新 Bridge → recap 数据库")
    logger.info(f"目标日期: {date}")
    logger.info(f"模式: {'Dry Run' if dry_run else '写入'}")
    logger.info(f"Bridge 实时数据: {'✅ 启用' if use_bridge else '❌ 跳过（非今日）'}")
    logger.info("=" * 60)

    # 1. 获取 bridge 数据（仅今日可用）
    logger.info("\n📡 获取 bridge 数据...")
    market = None
    hk_indices = None
    industries = None
    hk_industries = None
    hot_stocks = None

    if use_bridge:
        market = get_market_data()
        logger.info(f"  A 股行情: {'✅' if market else '❌'}")

        hk_indices = get_hk_indices()
        logger.info(f"  港股指数: {'✅' if hk_indices else '❌'}")

        industries = get_industry_rank()
        logger.info(f"  行业排行: {'✅' if industries else '❌'}")

        hk_industries = get_hk_industry()
        logger.info(f"  港股行业: {'✅' if hk_industries else '❌'}")

        hot_stocks = get_hot_stocks()
        logger.info(f"  热门股票: {'✅' if hot_stocks else '❌'}")
    else:
        logger.info("  ⏭️  跳过（bridge 仅提供实时数据，不匹配目标日期）")

    # 2. 获取 news.db 数据
    logger.info("\n📰 获取 news.db 数据...")
    news_ai = get_news_articles("AI", date)
    logger.info(f"  AI 新闻: {len(news_ai)} 篇")

    news_comm = get_news_articles("大宗商品", date)
    logger.info(f"  大宗商品: {len(news_comm)} 篇")

    news_geo = get_news_articles("地缘政治", date)
    logger.info(f"  地缘政治: {len(news_geo)} 篇")

    all_news = news_ai + news_comm + news_geo

    # 3. 补充 recap
    logger.info(f"\n📝 补充 recap 数据库...")
    supplement_dim1(date, market, hk_indices, dry_run)
    supplement_dim2(date, industries, hk_industries, dry_run)
    supplement_dim3(date, hot_stocks, all_news, dry_run)

    logger.info(f"\n{'='*60}")
    logger.info("✅ 完成！" if not dry_run else "🔍 Dry Run 结束")
    logger.info(f"{'='*60}")


if __name__ == "__main__":
    date_arg = None
    dry_run = False

    for arg in sys.argv[1:]:
        if arg == "--dry-run":
            dry_run = True
        elif arg.startswith("--date="):
            date_arg = arg.split("=")[1]

    run(date=date_arg, dry_run=dry_run)


# ============================================================
# 📌 预留设计位：持仓标的（等待哥哥提供）
# ============================================================
# 当哥哥提供持仓标的后，在此处配置：
#
# WATCHLIST = {
#     # AI 硬件
#     "中芯国际":   {"id": "101018208", "category": "AI硬件", "sector": "半导体"},
#     "天孚通信":   {"id": "待补充",    "category": "AI硬件", "sector": "光模块"},
#     "中际旭创":   {"id": "待补充",    "category": "AI硬件", "sector": "光模块"},
#     "新易盛":     {"id": "待补充",    "category": "AI硬件", "sector": "光模块"},
#
#     # 半导体设备
#     "北方华创":   {"id": "待补充",    "category": "半导体设备", "sector": "刻蚀/沉积"},
#     "中微公司":   {"id": "待补充",    "category": "半导体设备", "sector": "刻蚀"},
#     "拓荆科技":   {"id": "待补充",    "category": "半导体设备", "sector": "薄膜沉积"},
#
#     # 大宗商品
#     "天齐锂业":   {"id": "待补充",    "category": "大宗商品", "sector": "锂矿"},
#     "赣锋锂业":   {"id": "待补充",    "category": "大宗商品", "sector": "锂矿"},
#
#     # 其他关注
#     "神火股份":   {"id": "待补充",    "category": "大宗商品", "sector": "铝/煤"},
# }
#
# 用途：
# 1. 按日期拉取标的个股新闻 → 补充到 recap Dim3
# 2. 按分类统计新闻密度 → 判断行业热度
# 3. 新闻中涨价/降价信号 → 填充 Dim2 price_catalyst
# ============================================================
WATCHLIST = {}  # 待哥哥提供持仓标的后填写
