#!/usr/bin/env python3
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from lib.logger import get_logger
logger = get_logger(__name__)
"""
🐲 复盘数据库 · 句芒行情数据融合
利用句芒的 market_data.db 补全量化 7 指标
"""
import sqlite3

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import config
# tools/ 非包，加入 sys.path 以便 import cycle_quant
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), 'tools'))
RECAP_DB = config.RECAP_DB
MARKET_DB = config.MARKET_DB

def enhance_cycle_quant():
    """用句芒数据补全 cycle_quant 表"""
    rdb = sqlite3.connect(RECAP_DB)
    rcur = rdb.cursor()
    mdb = sqlite3.connect(MARKET_DB)
    mcur = mdb.cursor()
    
    logger.info("=== 句芒行情数据融合 ===\n")
    
    # 1. 获取句芒行情数据（列名对齐 market_data.db: limit_up/limit_down/max_consecutive/volume_trillion）
    mcur.execute("""
        SELECT trade_date, limit_up, limit_down, max_consecutive, volume_trillion
        FROM daily_market
    """)
    market_data = {r[0]: r for r in mcur.fetchall()}
    
    # 2. 获取北向资金
    mcur.execute("SELECT trade_date, north_money FROM north_flow")
    north_data = {r[0]: r[1] for r in mcur.fetchall()}
    
    # 3. 计算涨跌家数比 (需要涨跌家数，看 daily_market 是否有)
    mcur.execute("PRAGMA table_info(daily_market)")
    cols = [r[1] for r in mcur.fetchall()]
    
    # 检查是否有涨跌家数
    up_col = 'up_count' if 'up_count' in cols else None
    down_col = 'down_count' if 'down_count' in cols else None
    
    # 4. 计算主线持续性 (板块连续出现天数)
    logger.info("📊 计算主线持续性...")
    mcur.execute("""
        SELECT sector_name, COUNT(*) as days
        FROM sector_daily
        GROUP BY sector_name
    """)
    theme_days = {r[0]: r[1] for r in mcur.fetchall()}
    
    # 取最长连续板块作为主线持续性
    max_theme_days = max(theme_days.values()) if theme_days else 0
    logger.info(f"   最长连续板块: {max_theme_days} 天")
    
    # 5. 更新 cycle_quant
    updated = 0
    rcur.execute("SELECT date FROM cycle_quant ORDER BY date")
    dates = [r[0] for r in rcur.fetchall()]
    
    # 适配 cycle_quant.calculate_score 当前接口（旧 calculate_emotion_score 已不存在）
    from cycle_quant import calculate_score

    for date in dates:
        mkey = date.replace('-', '')   # cycle_quant 用 YYYY-MM-DD，market_data 用 YYYYMMDD
        if mkey in market_data:
            md = market_data[mkey]
            limit_up = md[1]
            limit_down = md[2]
            consecutive = md[3]
            volume = md[4]            # volume_trillion（修复退化：此前恒为 None）
            north = north_data.get(mkey)

            result = calculate_score(
                limit_up=limit_up, limit_down=limit_down,
                consecutive=consecutive, volume=volume,
                north=north, theme_days=max_theme_days,
            )
            sc = result['details']   # {limit_up,limit_down,consecutive,volume,north,theme_continuity}

            # 可用指标数 + 置信度（calculate_score 不返回，这里自算）
            avail = sum(1 for v in (limit_up, limit_down, consecutive, volume, north, max_theme_days)
                        if v is not None)
            confidence = round(avail / 6, 2)

            rcur.execute("""
                UPDATE cycle_quant
                SET total_score = ?, cycle_stage = ?,
                    score_limit_up = ?, score_limit_down = ?,
                    score_consecutive_limit = ?, score_volume = ?,
                    score_north_flow = ?, score_theme_continuity = ?,
                    available_indicators = ?, confidence = ?,
                    limit_up = ?, limit_down = ?, consecutive_limit = ?,
                    volume_trillion = ?, north_flow_billion = ?, theme_continuity_days = ?
                WHERE date = ?
            """, (result['total_score'], result['cycle_stage'],
                  sc['limit_up'], sc['limit_down'],
                  sc['consecutive'], sc['volume'],
                  sc['north'], sc['theme_continuity'],
                  avail, confidence,
                  limit_up, limit_down, consecutive, volume, north, max_theme_days, date))
            updated += 1
    
    rdb.commit()
    logger.info(f"\n✅ 更新: {updated}/{len(dates)} 条")
    
    # 6. 重新对比双轨制
    rcur.execute("""
        SELECT rd.date, d3.emotion_stage, cq.cycle_stage, cq.total_score
        FROM recap_daily rd
        JOIN dim3_sentiment_tech d3 ON rd.date = d3.date
        JOIN cycle_quant cq ON rd.date = cq.date
        WHERE d3.emotion_stage IS NOT NULL AND cq.available_indicators >= 4
        ORDER BY rd.date
    """)
    rows = rcur.fetchall()
    if rows:
        match = sum(1 for _, bao, quant, _ in rows 
                   if (bao == quant) or 
                      (bao in ['复苏', '调整'] and quant in ['复苏', '冰点']) or
                      (bao in ['主升', '过热'] and quant == '火热'))
        logger.info(f"\n=== 双轨对比 (≥4 指标) ===")
        logger.info(f"   有效样本: {len(rows)} 条")
        logger.info(f"   一致: {match} 条 ({match/len(rows)*100:.1f}%)")
    
    # 7. 分数分布
    rcur.execute("""
        SELECT cycle_stage, COUNT(*), ROUND(AVG(total_score), 1)
        FROM cycle_quant
        WHERE available_indicators >= 4
        GROUP BY cycle_stage
        ORDER BY cycle_stage
    """)
    logger.info(f"\n=== 量化分数分布 ===")
    logger.info(f"{'阶段':<8} {'天数':<6} {'均分'}")
    logger.info("-" * 25)
    for row in rcur.fetchall():
        logger.info(f"{row[0]:<8} {row[1]:<6} {row[2]}")
    
    rdb.close()
    mdb.close()
    logger.info("\n✅ 融合完成")

if __name__ == "__main__":
    enhance_cycle_quant()
