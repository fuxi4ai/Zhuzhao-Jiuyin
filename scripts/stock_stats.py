#!/usr/bin/env python3
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from lib.logger import get_logger
logger = get_logger(__name__)
"""
📊 标的统计查询工具
用法: python3 scripts/stock_stats.py [--sector <板块>] [--source <来源>] [--status <状态>]
"""
import sqlite3, argparse, os, sys

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import config
DB_PATH = config.RECAP_DB

def print_header():
    logger.info("=" * 70)
    logger.info("📊 重点标的统计分析")
    logger.info("=" * 70)

def print_overall(conn):
    """总体统计"""
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*),
               SUM(CASE WHEN next_day_return > 0 THEN 1 ELSE 0 END),
               ROUND(AVG(next_day_return), 2),
               ROUND(AVG(COALESCE(next_3d_return, next_day_return)), 2),
               ROUND(AVG(max_return), 2),
               ROUND(AVG(max_drawdown), 2)
        FROM stock_tracking WHERE next_day_return IS NOT NULL
    """)
    r = cur.fetchone()
    if r[0] == 0:
        logger.info("\n  (暂无数据)")
        return
    
    hit_rate = r[1]/r[0]*100
    logger.info(f"\n📈 总体统计 ({r[0]} 条信号):")
    logger.info(f"  次日胜率: {hit_rate:.0f}% ({r[1]}/{r[0]})")
    logger.info(f"  次日平均收益: {r[2]:+.2f}%")
    logger.info(f"  3 日平均收益: {r[3]:+.2f}%")
    logger.info(f"  平均最大收益: {r[4]:+.2f}%")
    logger.info(f"  平均最大回撤: {r[5]:+.2f}%")

def print_by_sector(conn):
    """按板块统计"""
    cur = conn.cursor()
    cur.execute("""
        SELECT sector, COUNT(*), 
               SUM(CASE WHEN next_day_return > 0 THEN 1 ELSE 0 END),
               ROUND(AVG(next_day_return), 2),
               ROUND(AVG(COALESCE(next_3d_return, next_day_return)), 2)
        FROM stock_tracking WHERE next_day_return IS NOT NULL
        GROUP BY sector ORDER BY COUNT(*) DESC
    """)
    rows = cur.fetchall()
    if not rows:
        return
    
    logger.info(f"\n📊 按板块统计:")
    logger.info(f"  {'板块':<15} {'信号数':<8} {'胜率':<8} {'次日':<8} {'3 日':<8}")
    logger.info(f"  {'-'*50}")
    for r in rows:
        hr = r[2]/r[1]*100 if r[1] > 0 else 0
        logger.info(f"  {r[0]:<15} {r[1]:<8} {hr:<7.0f}% {r[3]:<7.2f}% {r[4]:<7.2f}%")

def print_by_source(conn):
    """按来源统计"""
    cur = conn.cursor()
    cur.execute("""
        SELECT source, COUNT(*),
               SUM(CASE WHEN next_day_return > 0 THEN 1 ELSE 0 END),
               ROUND(AVG(next_day_return), 2)
        FROM stock_tracking WHERE next_day_return IS NOT NULL
        GROUP BY source ORDER BY COUNT(*) DESC
    """)
    rows = cur.fetchall()
    if not rows:
        return
    
    logger.info(f"\n📊 按来源统计:")
    logger.info(f"  {'来源':<10} {'信号数':<8} {'胜率':<8} {'次日':<8}")
    logger.info(f"  {'-'*40}")
    for r in rows:
        hr = r[2]/r[1]*100 if r[1] > 0 else 0
        logger.info(f"  {r[0]:<10} {r[1]:<8} {hr:<7.0f}% {r[3]:<7.2f}%")

def print_top_signals(conn, limit=10):
    """最佳/最差信号"""
    cur = conn.cursor()
    
    logger.info(f"\n🏆 最佳信号 (Top {limit}):")
    cur.execute("""
        SELECT signal_date, stock_name, sector, next_day_return, next_5d_return
        FROM stock_tracking WHERE next_day_return IS NOT NULL
        ORDER BY COALESCE(next_5d_return, next_day_return) DESC LIMIT ?
    """, (limit,))
    for r in cur.fetchall():
        logger.info(f"  {r[0]} {r[1]} ({r[2]}) 次日:{r[3]:+.2f}% 5 日:{r[4] or 'N/A':>6}")

    logger.info(f"\n💀 最差信号 (Top {limit}):")
    cur.execute("""
        SELECT signal_date, stock_name, sector, next_day_return, next_5d_return
        FROM stock_tracking WHERE next_day_return IS NOT NULL
        ORDER BY COALESCE(next_5d_return, next_day_return) ASC LIMIT ?
    """, (limit,))
    for r in cur.fetchall():
        logger.info(f"  {r[0]} {r[1]} ({r[2]}) 次日:{r[3]:+.2f}% 5 日:{r[4] or 'N/A':>6}")

def main():
    parser = argparse.ArgumentParser(description="📊 标的统计查询")
    parser.add_argument("--sector", help="按板块筛选")
    parser.add_argument("--source", help="按来源筛选")
    args = parser.parse_args()
    
    conn = sqlite3.connect(DB_PATH)
    
    print_header()
    print_overall(conn)
    print_by_sector(conn)
    print_by_source(conn)
    print_top_signals(conn)
    
    conn.close()
    logger.info("\n✅ 查询完成")

if __name__ == "__main__":
    main()
