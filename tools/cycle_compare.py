#!/usr/bin/env python3
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import config
from lib.logger import get_logger
logger = get_logger(__name__)
"""
🐲 情绪周期对比分析工具
双轨制：小鲍标注 vs 量化指标
"""
import sys, sqlite3
from cycle_quant import compare_cycles

DB_PATH = config.RECAP_DB

def create_comparison_table():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cycle_comparison (
            date TEXT PRIMARY KEY,
            bao_stage TEXT,
            quant_stage TEXT,
            quant_score INTEGER,
            match BOOLEAN,
            next_day_return REAL,           -- 次日实际涨跌（后期句芒回填）
            bao_correct BOOLEAN,            -- 小鲍预测是否正确
            quant_correct BOOLEAN,          -- 量化预测是否正确
            verified_at DATETIME            -- 验证时间
        )
    """)
    conn.commit()
    conn.close()

def run_comparison():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # 获取有小鲍标注 + 量化结果的日期
    cur.execute("""
        SELECT rd.date, d3.emotion_stage, cq.cycle_stage, cq.total_score
        FROM recap_daily rd
        JOIN dim3_sentiment_tech d3 ON rd.date = d3.date
        JOIN cycle_quant cq ON rd.date = cq.date
        WHERE d3.emotion_stage IS NOT NULL
        ORDER BY rd.date
    """)
    
    rows = cur.fetchall()
    match_count = 0
    mismatch_count = 0
    total = len(rows)
    
    cur.execute("DELETE FROM cycle_comparison")
    
    for date, bao, quant, score in rows:
        comp = compare_cycles(bao, quant)
        cur.execute(
            "INSERT OR REPLACE INTO cycle_comparison (date, bao_stage, quant_stage, quant_score, match) VALUES (?,?,?,?,?)",
            (date, bao, quant, score, comp['match'])
        )
        if comp['match']:
            match_count += 1
        else:
            mismatch_count += 1
    
    conn.commit()
    
    logger.info(f"=== 情绪周期双轨制对比报告 ===\n")
    logger.info(f"📊 总样本: {total} 条")
    logger.info(f"✅ 一致: {match_count} 条 ({match_count/total*100:.1f}%)")
    logger.info(f"❌ 分歧: {mismatch_count} 条 ({mismatch_count/total*100:.1f}%)")
    
    # 按小鲍标注分组
    logger.info(f"\n📋 按小鲍标注分组:")
    cur.execute("""
        SELECT bao_stage, COUNT(*) as total, SUM(CASE WHEN match=1 THEN 1 ELSE 0 END) as matched
        FROM cycle_comparison
        GROUP BY bao_stage
        ORDER BY total DESC
    """)
    logger.info(f"{'小鲍标注':<8} {'总数':<6} {'一致':<6} {'一致率':<8}")
    logger.info("-" * 35)
    for row in cur.fetchall():
        rate = row[2]/row[1]*100 if row[1] > 0 else 0
        logger.info(f"{row[0]:<8} {row[1]:<6} {row[2]:<6} {rate:.1f}%")
    
    # 按量化结果分组
    logger.info(f"\n📊 按量化结果分组:")
    cur.execute("""
        SELECT quant_stage, COUNT(*) as total, SUM(CASE WHEN match=1 THEN 1 ELSE 0 END) as matched
        FROM cycle_comparison
        GROUP BY quant_stage
        ORDER BY total DESC
    """)
    logger.info(f"{'量化标注':<8} {'总数':<6} {'一致':<6} {'一致率':<8}")
    logger.info("-" * 35)
    for row in cur.fetchall():
        rate = row[2]/row[1]*100 if row[1] > 0 else 0
        logger.info(f"{row[0]:<8} {row[1]:<6} {row[2]:<6} {rate:.1f}%")
    
    # 分歧明细
    if mismatch_count > 0:
        logger.info(f"\n🔍 分歧明细 (前20条):")
        cur.execute("""
            SELECT date, bao_stage, quant_stage, quant_score
            FROM cycle_comparison
            WHERE match = 0
            ORDER BY date DESC LIMIT 20
        """)
        logger.info(f"{'日期':<12} {'小鲍':<8} {'量化':<8} {'量化分':<6}")
        logger.info("-" * 40)
        for row in cur.fetchall():
            logger.info(f"{row[0]:<12} {row[1]:<8} {row[2]:<8} {row[3]:<6}")
    
    conn.close()

def show_quant_table():
    """展示量化评分明细表"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    cur.execute("""
        SELECT date, total_score, cycle_stage,
               score_limit_up, score_limit_down, score_volume, confidence
        FROM cycle_quant
        ORDER BY date DESC LIMIT 20
    """)
    
    rows = cur.fetchall()
    logger.info("=== 量化评分明细表 (最近 20 条) ===\n")
    logger.info(f"{'日期':<12} {'总分':<6} {'周期':<8} {'涨停分':<6} {'跌停分':<6} {'量能分':<6} {'置信度':<6}")
    logger.info("-" * 55)
    for row in rows:
        logger.info(f"{row[0]:<12} {row[1]:<6} {row[2]:<8} {row[3] or 0:<6} {row[4] or 0:<6} {row[5] or 0:<6} {row[6]:.2f}")
    
    conn.close()

if __name__ == "__main__":
    import sys
    
    create_comparison_table()
    
    if len(sys.argv) > 1 and sys.argv[1] == "--table":
        show_quant_table()
    else:
        run_comparison()
