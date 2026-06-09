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
    
    # 4. 主线持续性 = 当日主线代表ETF相对沪深300超额收益连续为正天数（替代旧版全局常数）
    import theme_strength
    # 硬保护：没拉 theme_etf_daily 就不要写退化分
    has_etf = mcur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='theme_etf_daily'").fetchone()
    etf_rows = mcur.execute("SELECT COUNT(*) FROM theme_etf_daily").fetchone()[0] if has_etf else 0
    if etf_rows == 0:
        logger.error("❌ market_data.db 无 theme_etf_daily 数据。请先在终端跑 "
                     "scripts/fetch_theme_etf.py 拉取 ETF 行情，再跑本脚本。已中止，未写库。")
        rdb.close(); mdb.close(); return
    logger.info(f"📊 主线持续性: 用 theme_etf_daily({etf_rows}行)超额连续为正天数")
    alias_rows = rcur.execute("SELECT canonical_name, aliases FROM sector_alias").fetchall()
    mainline_by_date = dict(rcur.execute(
        "SELECT date, main_line FROM dim2_sector_themes WHERE main_line IS NOT NULL").fetchall())

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

            # 当日主线 → 代表ETF → 超额收益连续为正天数（无主线/无锚则 None）
            tdays, _theme, _etfs = theme_strength.theme_continuity_days(
                mainline_by_date.get(date), date, mdb, alias_rows)
            theme_days_val = tdays if _etfs else None

            result = calculate_score(
                limit_up=limit_up, limit_down=limit_down,
                consecutive=consecutive, volume=volume,
                north=north, theme_days=theme_days_val,
            )
            sc = result['details']   # {limit_up,limit_down,consecutive,volume,north,theme_continuity}

            # 可用指标数 + 置信度（calculate_score 不返回，这里自算）
            avail = sum(1 for v in (limit_up, limit_down, consecutive, volume, north, theme_days_val)
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
                  limit_up, limit_down, consecutive, volume, north, theme_days_val, date))
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
