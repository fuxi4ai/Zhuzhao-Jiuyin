#!/usr/bin/env python3
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import config
from lib.logger import get_logger
logger = get_logger(__name__)
"""
🐲 四维度复盘数据库 · 命令行查询工具 v1.2
用法: python3 recap_cli.py <command> [options]
"""
import sys, argparse
from recap_db import get_conn
import sqlite3

def cmd_dates(args):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT date, source, speaker FROM recap_daily ORDER BY date DESC LIMIT 20")
    rows = cur.fetchall()
    logger.info(f"📅 最近 20 条记录:\n")
    logger.info(f"{'日期':<12} {'来源':<18} {'发言人'}")
    logger.info("-" * 50)
    for row in rows:
        logger.info(f"{row[0]:<12} {row[1]:<18} {row[2]}")
    conn.close()

def cmd_by_date(args):
    date = args.date
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM recap_daily WHERE date=?", (date,))
    rd = cur.fetchone()
    if not rd:
        logger.info(f"❌ 未找到 {date} 的记录")
        return
    logger.info(f"📅 {date} 复盘\n{'='*60}")
    logger.info(f"Speaker: {rd[3]}")
    logger.info(f"周期:    {rd[4] or '未标注'}")
    logger.info(f"概要:    {rd[5][:100] if rd[5] else '无'}")
    logger.info(f"主题:    {rd[6] or '无'}")
    for table, name, fields in [
        ("dim1_external_pricing", "🌍 Dim1 外围定价", [(2,'汇率','USD/CNY = '),(3,'掉期',''),(4,'原油',''),(5,'方向','')]),
        ("dim2_sector_themes", "🔥 Dim2 行业主线", [(2,'主线',''),(3,'看多',''),(4,'看空','')]),
        ("dim3_sentiment_tech", "📊 Dim3 情绪技术", [(2,'情绪',''),(3,'涨停',''),(4,'跌停',''),(5,'成交','万亿'),(6,'MA60',''),(7,'支撑',''),(8,'阻力','')]),
        ("dim4_trade_plan", "💰 Dim4 交易策略", [(2,'预案',''),(3,'标的',''),(4,'仓位',''),(5,'风险','')]),
    ]:
        cur.execute(f"SELECT * FROM {table} WHERE date=?", (date,))
        row = cur.fetchone()
        if row and any(row[2:]):
            logger.info(f"\n{name}:")
            for idx, label, prefix in fields:
                val = row[idx]
                if val:
                    logger.info(f"   {label}: {prefix}{val}")
    conn.close()

def cmd_by_sector(args):
    keyword = args.keyword
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT rd.date, rd.speaker, d2.main_line, d4.plan
        FROM recap_daily rd
        LEFT JOIN dim2_sector_themes d2 ON rd.date = d2.date
        LEFT JOIN dim4_trade_plan d4 ON rd.date = d4.date
        WHERE d2.main_line LIKE ? OR d2.sectors_bullish LIKE ? OR rd.key_themes LIKE ?
        ORDER BY rd.date DESC LIMIT 20
    """, (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"))
    rows = cur.fetchall()
    logger.info(f"🔍 板块 '{keyword}' 相关记录 ({len(rows)} 条):\n")
    for row in rows:
        logger.info(f"📅 {row[0]} | {row[1]}")
        if row[2]: print(f"   主线: {row[2][:60]}")
        if row[3]: print(f"   预案: {row[3][:60]}")
        logger.info("")
    conn.close()

def cmd_by_emotion(args):
    stage = args.stage
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT rd.date, rd.speaker, d2.main_line, d3.volume_trillion
        FROM recap_daily rd
        JOIN dim3_sentiment_tech d3 ON rd.date = d3.date
        LEFT JOIN dim2_sector_themes d2 ON rd.date = d2.date
        WHERE d3.emotion_stage = ?
        ORDER BY rd.date DESC LIMIT 30
    """, (stage,))
    rows = cur.fetchall()
    logger.info(f"📈 情绪阶段 '{stage}' 记录 ({len(rows)} 条):\n")
    logger.info(f"{'日期':<12} {'Speaker':<8} {'成交(万亿)'}")
    logger.info("-" * 40)
    for row in rows:
        logger.info(f"{row[0]:<12} {row[1]:<8} {row[3] or 'N/A'}")
    conn.close()

def cmd_heatmap(args):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT main_line, COUNT(*) as cnt
        FROM dim2_sector_themes
        WHERE main_line IS NOT NULL AND main_line != ''
        GROUP BY main_line
        ORDER BY cnt DESC LIMIT 15
    """)
    rows = cur.fetchall()
    logger.info("🔥 行业主线热度排行:\n")
    logger.info(f"{'排名':<4} {'提及':<6} {'主线'}")
    logger.info("-" * 60)
    for i, row in enumerate(rows, 1):
        bar = '█' * min(row[1] * 3, 30)
        logger.info(f"{i:<4} {row[1]:<6} {row[0][:50]} {bar}")
    conn.close()

def cmd_emotion(args):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT COALESCE(emotion_stage, '未标注') as stage, COUNT(*) as cnt
        FROM dim3_sentiment_tech d3
        JOIN recap_daily rd ON d3.date = rd.date
        GROUP BY emotion_stage ORDER BY cnt DESC
    """)
    rows = cur.fetchall()
    total = sum(r[1] for r in rows)
    logger.info(f"📊 情绪阶段分布 (总计 {total} 条):\n")
    logger.info(f"{'阶段':<8} {'天数':<6} {'占比':<8} {'分布'}")
    logger.info("-" * 60)
    for row in rows:
        pct = f"{row[1]/total*100:.1f}%"
        bar = '█' * (row[1] // 2)
        logger.info(f"{row[0]:<8} {row[1]:<6} {pct:<8} {bar}")
    logger.info(f"\n📅 最近 30 天情绪走势:")
    cur.execute("""
        SELECT rd.date, d3.emotion_stage
        FROM dim3_sentiment_tech d3
        JOIN recap_daily rd ON d3.date = rd.date
        WHERE rd.date >= (SELECT MAX(date) - 30 FROM recap_daily)
        ORDER BY rd.date DESC LIMIT 30
    """)
    emoji_map = {'冰点':'🧊','主升':'🚀','退潮':'📉','复苏':'🌱','过热':'🔥','调整':'↔️','震荡':'〰️','休市':'🔒'}
    for row in cur.fetchall():
        emoji = emoji_map.get(row[1], '❓')
        logger.info(f"   {row[0]}  {emoji} {row[1] or '未标注'}")
    conn.close()

def cmd_stats(args):
    conn = get_conn()
    cur = conn.cursor()
    logger.info("🐲 四维度复盘数据库 · 统计概览\n")
    cur.execute("SELECT COUNT(*) FROM recap_daily")
    total = cur.fetchone()[0]
    logger.info(f"📊 总计: {total} 条")
    cur.execute("SELECT MIN(date), MAX(date) FROM recap_daily")
    start, end = cur.fetchone()
    logger.info(f"📅 跨度: {start} → {end}")
    cur.execute("SELECT source, COUNT(*) FROM recap_daily GROUP BY source")
    logger.info(f"\n📁 来源:")
    for row in cur.fetchall(): print(f"   {row[0]:20s} → {row[1]} 条")
    tables = [('dim1_external_pricing','Dim1 外围'),('dim2_sector_themes','Dim2 主线'),('dim3_sentiment_tech','Dim3 情绪'),('dim4_trade_plan','Dim4 策略')]
    logger.info(f"\n📐 维度覆盖率:")
    for table, name in tables:
        cur.execute(f"SELECT COUNT(DISTINCT date) FROM {table}")
        has = cur.fetchone()[0]
        logger.info(f"   {name:16s} → {has:3d}/{total} 条 ({has/total*100:.1f}%)")
    conn.close()

def cmd_plan_accuracy(args):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM prediction_log")
    count = cur.fetchone()[0]
    if count == 0:
        logger.info("📝 预案验证日志为空\n需要句芒行情数据库对接后自动回填")
    else:
        cur.execute("SELECT plan_accuracy, COUNT(*) FROM prediction_log GROUP BY plan_accuracy ORDER BY plan_accuracy")
        logger.info("🎯 预案准确率:\n")
        for row in cur.fetchall(): print(f"   {row[0]}: {row[1]} 条")
    conn.close()

def cmd_search(args):
    keyword = args.keyword
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT rd.date, rd.speaker, 'Dim2' as source, d2.main_line as content
        FROM dim2_sector_themes d2 JOIN recap_daily rd ON d2.date = rd.date
        WHERE d2.main_line LIKE ? OR d2.sectors_bullish LIKE ?
        UNION ALL
        SELECT rd.date, rd.speaker, 'Dim4', d4.plan
        FROM dim4_trade_plan d4 JOIN recap_daily rd ON d4.date = rd.date
        WHERE d4.plan LIKE ? OR d4.key_stocks LIKE ?
        ORDER BY 1 DESC LIMIT 20
    """, (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"))
    rows = cur.fetchall()
    logger.info(f"🔍 搜索 '{keyword}' ({len(rows)} 条):\n")
    for row in rows:
        logger.info(f"📅 {row[0]} | {row[1]} | [{row[2]}]")
        if row[3]: print(f"   {row[3][:80]}")
        logger.info("")
    conn.close()

def cmd_trend(args):
    field = args.field
    days = args.days
    conn = get_conn()
    cur = conn.cursor()
    if field == "emotion_stage":
        cur.execute(f"""
            SELECT rd.date, d3.emotion_stage
            FROM dim3_sentiment_tech d3 JOIN recap_daily rd ON d3.date = rd.date
            WHERE rd.date >= (SELECT MAX(date) - {days} FROM recap_daily)
            ORDER BY rd.date DESC LIMIT {days}
        """)
        emoji_map = {'冰点':'🧊','主升':'🚀','退潮':'📉','复苏':'🌱','过热':'🔥','调整':'↔️','震荡':'〰️','休市':'🔒'}
        logger.info(f"📈 近 {days} 天情绪走势:\n")
        for i, (date, stage) in enumerate(cur.fetchall()):
            if i > 0 and i % 7 == 0: print()
            emoji = emoji_map.get(stage, '❓')
            logger.info(f"   {date} {emoji} {stage or '未标注':<4}", end="  ")
        logger.info("")
    elif field == "volume_trillion":
        cur.execute(f"""
            SELECT rd.date, d3.volume_trillion
            FROM dim3_sentiment_tech d3 JOIN recap_daily rd ON d3.date = rd.date
            WHERE d3.volume_trillion IS NOT NULL
            ORDER BY rd.date DESC LIMIT {days}
        """)
        rows = cur.fetchall()
        max_vol = max(r[1] for r in rows) if rows else 3
        logger.info(f"📊 近 {days} 天成交额走势(万亿):\n")
        for date, vol in rows:
            bar = '█' * int(vol / max_vol * 30)
            logger.info(f"   {date}  {vol:.2f}万亿  {bar}")
    conn.close()

def cmd_similar(args):
    date, top = args.date, args.top
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT d3.emotion_stage, d3.limit_up, d3.limit_down,
               d3.volume_trillion, d2.main_line
        FROM dim3_sentiment_tech d3
        LEFT JOIN dim2_sector_themes d2 ON d3.date = d2.date
        WHERE d3.date = ?
    """, (date,))
    target = cur.fetchone()
    if not target:
        logger.info(f"❌ 未找到 {date}")
        return
    t_emo, t_up, t_down, t_vol, t_main = target
    cur.execute("""
        SELECT rd.date, d3.emotion_stage, d3.limit_up, d3.limit_down,
               d3.volume_trillion, d2.main_line
        FROM dim3_sentiment_tech d3 JOIN recap_daily rd ON d3.date = rd.date
        LEFT JOIN dim2_sector_themes d2 ON rd.date = d2.date
        WHERE rd.date != ?
    """, (date,))
    candidates = []
    for row in cur.fetchall():
        score = 0
        if row[1] == t_emo: score += 2
        if row[4] and t_vol and abs(row[4] - t_vol) < 0.3: score += 1
        if row[2] and t_up and abs(row[2] - t_up) < 10: score += 1
        if row[5] and t_main:
            tw = set(t_main[:20].split())
            rw = set(row[5][:20].split())
            if tw & rw: score += 1
        candidates.append((row[0], score, row[1], row[4], row[5]))
    candidates.sort(key=lambda x: x[1], reverse=True)
    logger.info(f"🔍 与 {date} 最相似的 {top} 个交易日:\n")
    logger.info(f"目标: 情绪={t_emo} 涨停={t_up} 成交={t_vol}万亿\n")
    logger.info(f"{'排名':<4} {'日期':<12} {'相似度':<6} {'情绪':<6} {'成交':<8} {'主线'}")
    logger.info("-" * 80)
    for i, (d, score, emo, vol, main) in enumerate(candidates[:top], 1):
        logger.info(f"{i:<4} {d:<12} {score:<6} {emo or '未标注':<6} {vol or 'N/A':<8} {(main or '')[:30]}")
    conn.close()

def cmd_rotation(args):
    sector, days = args.sector, args.days
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT rd.date, d3.emotion_stage, d3.volume_trillion,
               d2.main_line, d4.plan
        FROM recap_daily rd
        LEFT JOIN dim3_sentiment_tech d3 ON rd.date = d3.date
        LEFT JOIN dim2_sector_themes d2 ON rd.date = d2.date
        LEFT JOIN dim4_trade_plan d4 ON rd.date = d4.date
        WHERE d2.main_line LIKE ? OR rd.key_themes LIKE ?
        ORDER BY rd.date DESC LIMIT ?
    """, (f"%{sector}%", f"%{sector}%", days))
    rows = cur.fetchall()
    logger.info(f"🔄 '{sector}' 板块轮动 (近 {days} 天):\n")
    for row in rows:
        logger.info(f"📅 {row[0]} | 情绪:{row[1] or '未标注'} | 成交:{row[2] or 'N/A'}万亿")
        if row[3]: print(f"   主线: {row[3][:60]}")
        if row[4]: print(f"   预案: {row[4][:60]}")
        logger.info("")
    conn.close()

def main():
    parser = argparse.ArgumentParser(description="🐲 四维度复盘数据库查询工具")
    sub = parser.add_subparsers(dest="command")
    
    sub.add_parser("dates").set_defaults(func=cmd_dates)
    p = sub.add_parser("by-date"); p.add_argument("date"); p.set_defaults(func=cmd_by_date)
    p = sub.add_parser("by-sector"); p.add_argument("keyword"); p.set_defaults(func=cmd_by_sector)
    p = sub.add_parser("by-emotion"); p.add_argument("stage"); p.set_defaults(func=cmd_by_emotion)
    sub.add_parser("heatmap").set_defaults(func=cmd_heatmap)
    sub.add_parser("emotion").set_defaults(func=cmd_emotion)
    sub.add_parser("stats").set_defaults(func=cmd_stats)
    sub.add_parser("plan-accuracy").set_defaults(func=cmd_plan_accuracy)
    p = sub.add_parser("search"); p.add_argument("keyword"); p.set_defaults(func=cmd_search)
    p = sub.add_parser("trend"); p.add_argument("--field", default="emotion_stage"); p.add_argument("--days", type=int, default=30); p.set_defaults(func=cmd_trend)
    p = sub.add_parser("similar"); p.add_argument("--date", required=True); p.add_argument("--top", type=int, default=5); p.set_defaults(func=cmd_similar)
    p = sub.add_parser("rotation"); p.add_argument("sector"); p.add_argument("--days", type=int, default=30); p.set_defaults(func=cmd_rotation)
    
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return
    args.func(args)

if __name__ == "__main__":
    main()