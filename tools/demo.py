#!/usr/bin/env python3
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import config
from lib.logger import get_logger
logger = get_logger(__name__)
"""
复盘数据库试用版演示
运行: python3 demo.py
"""
import sys
from recap_db import *

logger.info("=" * 60)
logger.info("🐲 四维度复盘数据库 · 试用版 v1.1")
logger.info("=" * 60)

# 1. 全量记录
logger.info(f"\n📊 数据库共 {len(list_dates())} 条记录:")
for d in list_dates():
    logger.info(f"   {d['date']} | {d['source']} | {d['speaker']}")

# 2. 完整查询
logger.info("\n📅 查询 2026-05-06 完整复盘:")
recap = get_recap("2026-05-06")
if recap:
    logger.info(f"   Speaker: {recap['speaker']}")
    logger.info(f"   周期: {recap['cycle_stage']}")
    logger.info(f"   概要: {recap['market_summary']}")
    if recap['dim1_external_pricing']:
        d1 = recap['dim1_external_pricing']
        logger.info(f"   Dim1 外围: USD/CNY={d1['usd_cny']} 掉期={d1['forex_swap']} 方向={d1['pricing_direction']}")
    if recap['dim2_sector_themes']:
        d2 = recap['dim2_sector_themes']
        logger.info(f"   Dim2 主线: {d2['main_line']} 看多={d2['sectors_bullish']}")
    if recap['dim3_sentiment_tech']:
        d3 = recap['dim3_sentiment_tech']
        logger.info(f"   Dim3 情绪: {d3['emotion_stage']} 成交={d3['volume_trillion']}万亿 MA60={d3['ma60']}")
    if recap['dim4_trade_plan']:
        d4 = recap['dim4_trade_plan']
        logger.info(f"   Dim4 策略: {d4['plan']} 仓位={d4['position_guidance']}")

# 3. 板块查询
logger.info("\n🔍 查询 '算力' 相关:")
for r in query_by_sector("算力"):
    logger.info(f"   {r['date']} | {r['speaker']} | 主线: {r['main_line']}")

# 4. 板块映射
logger.info("\n🔄 板块标准化映射:")
for alias in ["光模块", "CPO", "锂电池", "AI算力"]:
    canon = normalize_sector(alias)
    logger.info(f"   '{alias}' → {canon or '(未收录)'}")

# 5. 板块热度
logger.info("\n🔥 板块热度排行:")
for h in sector_heat_rank():
    logger.info(f"   {h['sector']}: {h['count']} 次提及")

logger.info("\n" + "=" * 60)
logger.info("💡 试用版包含 13 条示例数据（10条老版 + 3条四维度）")
logger.info("   完整导入 ~300 条数据请在 Phase 2 执行")
logger.info("=" * 60)
