#!/usr/bin/env python3
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import config
from lib.logger import get_logger
logger = get_logger(__name__)
"""
🐲 产业逻辑发现模块 v1.0
用法: python3 logic_discovery.py <command> [options]

命令:
  types          - 列出所有产业逻辑类型
  by-type TYPE   - 按逻辑类型查询
  by-sector SECTOR - 按行业查询
  hot            - 高价值信号（供给冲击+涨价）
  trend          - 月度趋势
  timeline       - 特定逻辑类型的时间线
  stats          - 统计摘要
  search KEYWORD - 关键词搜索
"""

import sqlite3, sys, os, argparse
from datetime import datetime

DB_PATH = config.RECAP_DB

TYPE_NAMES = {
    'tech_innovation': '🔧 技术革新',
    'supply_shock': '⚡ 供给冲击',
    'demand_surge': '🚀 需求爆发',
    'price_driven': '💰 涨价驱动',
    'event_driven': '📢 事件催化',
    'emotion_cycle': '📊 情绪周期',
    'other': '❓ 其他',
}

def get_conn():
    return sqlite3.connect(DB_PATH)

def cmd_types(args):
    """列出所有产业逻辑类型"""
    conn = get_conn()
    c = conn.cursor()
    
    # 从映射表获取
    rows = c.execute("SELECT logic_type, label_zh, label_en, description FROM logic_type_mapping ORDER BY label_zh").fetchall()
    
    logger.info("\n📋 产业逻辑类型\n")
    logger.info(f"{'类型ID':<20} {'中文':<10} {'英文':<15} {'说明'}")
    logger.info("-" * 70)
    for lt, zh, en, desc in rows:
        logger.info(f"{lt:<20} {zh:<10} {en:<15} {desc}")
    
    # 信号数量
    logger.info(f"\n信号分布:")
    rows = c.execute("""
        SELECT logic_type, count(*) as cnt 
        FROM industry_signals 
        GROUP BY logic_type 
        ORDER BY cnt DESC
    """).fetchall()
    
    total = sum(r[1] for r in rows)
    for lt, cnt in rows:
        name = TYPE_NAMES.get(lt, lt)
        bar = '█' * (cnt // 5)
        logger.info(f"  {name}: {cnt:3d}条 ({cnt/total*100:.1f}%) {bar}")
    
    conn.close()

def cmd_by_type(args):
    """按逻辑类型查询"""
    logic_type = args.type
    
    if logic_type not in TYPE_NAMES:
        logger.info(f"❌ 未知逻辑类型: {logic_type}")
        logger.info(f"可用类型: {', '.join(TYPE_NAMES.keys())}")
        sys.exit(1)
    
    conn = get_conn()
    c = conn.cursor()
    
    limit = getattr(args, 'limit', 20)
    date_from = getattr(args, 'from', None)
    date_to = getattr(args, 'to', None)
    
    query = "SELECT date, category, keyword, target, signal_content FROM industry_signals WHERE logic_type = ?"
    params = [logic_type]
    
    if date_from:
        query += " AND date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND date <= ?"
        params.append(date_to)
    
    query += " ORDER BY date DESC LIMIT ?"
    params.append(limit)
    
    rows = c.execute(query, params).fetchall()
    
    logger.info(f"\n{TYPE_NAMES[logic_type]} · 查询结果 ({len(rows)}条)")
    logger.info("=" * 80)
    
    for date, cat, kw, target, content in rows:
        logger.info(f"\n📅 {date} | {cat}")
        logger.info(f"   [{kw}]")
        if target:
            logger.info(f"   标的: {target}")
        # 显示内容（截断）
        content_display = content[:120] if content else ''
        logger.info(f"   {content_display}")
    
    conn.close()

def cmd_by_sector(args):
    """按行业查询"""
    sector = args.sector
    
    conn = get_conn()
    c = conn.cursor()
    
    limit = getattr(args, 'limit', 20)
    
    rows = c.execute("""
        SELECT date, logic_type, category, keyword, target, signal_content
        FROM industry_signals
        WHERE category LIKE ? OR keyword LIKE ?
        ORDER BY date DESC
        LIMIT ?
    """, (f'%{sector}%', f'%{sector}%', limit)).fetchall()
    
    logger.info(f"\n🔍 行业「{sector}」查询结果 ({len(rows)}条)")
    logger.info("=" * 80)
    
    for date, lt, cat, kw, target, content in rows:
        lt_name = TYPE_NAMES.get(lt, lt)
        logger.info(f"\n📅 {date} | {lt_name}")
        logger.info(f"   [{cat}] {kw}")
        if target:
            logger.info(f"   标的: {target}")
        content_display = content[:120] if content else ''
        logger.info(f"   {content_display}")
    
    conn.close()

def cmd_hot(args):
    """产业逻辑：买入信号（渊图派生）——主从倒置后的正式买入视图。
    源 = yuantu_buy_signals（渊图市场信号 conf≥0.7 + 受益传导链 + 标的），
    小鲍只作第二印证（xiaobao_echo）。由 tools/sync_buy_signals.py 同步。"""
    conn = get_conn()
    c = conn.cursor()
    limit = getattr(args, 'limit', 15)
    min_conf = getattr(args, 'min_conf', 0.7)
    only_ts = getattr(args, 'with_ts', False)
    only_echo = getattr(args, 'echo', False)

    if not c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='yuantu_buy_signals'").fetchone():
        logger.info("⚠️ 尚无 yuantu_buy_signals 表。先跑：python3 tools/sync_buy_signals.py")
        conn.close(); return

    q = """SELECT date, industry_chain, signal_type, yuantu_confidence, source_plevel,
                  beneficiaries_ts, beneficiaries, xiaobao_echo, beneficiary_count, ts_resolved
           FROM yuantu_buy_signals WHERE yuantu_confidence >= ?"""
    params = [min_conf]
    if only_ts:
        q += " AND ts_resolved > 0"
    if only_echo:
        q += " AND xiaobao_echo = 1"
    q += " ORDER BY yuantu_confidence DESC, date DESC LIMIT ?"
    params.append(limit)
    rows = c.execute(q, params).fetchall()

    logger.info(f"\n🔥 产业逻辑：买入信号（渊图派生，{len(rows)}条 · conf≥{min_conf}）")
    logger.info("   渊图信号(conf≥0.7)+受益传导链+标的 · 小鲍=第二印证")
    logger.info("=" * 80)
    for date, ind, st, conf, p, bts, ben, echo, bcnt, tscnt in rows:
        echo_s = "✓小鲍印证" if echo else "—"
        logger.info(f"\n📅 {date} | conf={conf} {p or ''} | {st} | {echo_s}")
        logger.info(f"   产业逻辑: {ind}")
        if bts:
            logger.info(f"   标的(已解析{tscnt}): {bts}")
        elif ben:
            logger.info(f"   受益公司({bcnt}, 待解析码): {ben[:120]}")
    conn.close()


def cmd_echo(args):
    """小鲍课件视图（第二印证/情绪共振）——降级自旧 cmd_hot。
    小鲍 supply_shock+price_driven 的涨价/缺口文本，仅作渊图信号的情绪共振参考，
    不再是「买入起点」（买入起点见 hot=渊图派生）。"""
    conn = get_conn()
    c = conn.cursor()
    limit = getattr(args, 'limit', 15)
    rows = c.execute("""
        SELECT date, category, keyword, target, signal_content, logic_type
        FROM industry_signals
        WHERE logic_type IN ('supply_shock', 'price_driven')
          AND (signal_content LIKE '%涨价%'
               OR signal_content LIKE '%缺口%'
               OR signal_content LIKE '%停产%'
               OR signal_content LIKE '%配额%'
               OR signal_content LIKE '%紧缺%')
        ORDER BY date DESC
        LIMIT ?
    """, (limit,)).fetchall()
    logger.info(f"\n📣 小鲍情绪共振视图（第二印证，{len(rows)}条）")
    logger.info("   ⚠️ 小鲍课件文本，仅作渊图信号印证参考，非买入起点（买入见 hot）")
    logger.info("=" * 80)
    for date, cat, kw, target, content, lt in rows:
        lt_name = TYPE_NAMES.get(lt, lt)
        logger.info(f"\n📅 {date} | {lt_name}")
        logger.info(f"   [{cat}] {kw}")
        if target:
            logger.info(f"   标的: {target}")
        content_display = content[:150] if content else ''
        logger.info(f"   {content_display}")
    conn.close()

def cmd_trend(args):
    """月度趋势"""
    conn = get_conn()
    c = conn.cursor()
    
    rows = c.execute("""
        SELECT substr(date, 1, 7) as month, logic_type, count(*) as cnt
        FROM industry_signals
        WHERE logic_type NOT IN ('emotion_cycle', 'other')
        GROUP BY month, logic_type
        ORDER BY month, cnt DESC
    """).fetchall()
    
    logger.info("\n📈 产业逻辑月度趋势\n")
    logger.info(f"{'月份':<8}", end='')
    for lt in ['tech_innovation', 'supply_shock', 'demand_surge', 'price_driven', 'event_driven']:
        name = TYPE_NAMES[lt].replace(' ', '')
        logger.info(f"{name:>10}", end='')
    logger.info("")
    logger.info("-" * 60)
    
    current_month = None
    row_data = {}
    for month, lt, cnt in rows:
        if month not in row_data:
            row_data[month] = {}
        row_data[month][lt] = cnt
    
    for month in sorted(row_data.keys()):
        logger.info(f"{month:<8}", end='')
        for lt in ['tech_innovation', 'supply_shock', 'demand_surge', 'price_driven', 'event_driven']:
            cnt = row_data[month].get(lt, 0)
            logger.info(f"{cnt:>10}", end='')
        logger.info("")
    
    conn.close()

def cmd_timeline(args):
    """时间线"""
    logic_type = args.type
    
    if logic_type not in TYPE_NAMES:
        logger.info(f"❌ 未知逻辑类型: {logic_type}")
        sys.exit(1)
    
    conn = get_conn()
    c = conn.cursor()
    
    rows = c.execute("""
        SELECT date, category, keyword, substr(signal_content, 1, 100) as content
        FROM industry_signals
        WHERE logic_type = ?
        ORDER BY date
    """, (logic_type,)).fetchall()
    
    logger.info(f"\n📅 {TYPE_NAMES[logic_type]} · 完整时间线 ({len(rows)}条)")
    logger.info("=" * 80)
    
    current_date = None
    for date, cat, kw, content in rows:
        if date != current_date:
            if current_date:
                logger.info("")
            logger.info(f"\n📆 {date}")
            current_date = date
        logger.info(f"   {cat} | {kw}")
        logger.info(f"     {content}")
    
    conn.close()

def cmd_stats(args):
    """统计摘要"""
    conn = get_conn()
    c = conn.cursor()
    
    total = c.execute('SELECT count(*) FROM industry_signals').fetchone()[0]
    dates = c.execute('SELECT MIN(date), MAX(date), COUNT(DISTINCT date) FROM industry_signals').fetchone()
    
    logger.info(f"\n📊 产业逻辑发现模块 · 统计摘要")
    logger.info("=" * 50)
    logger.info(f"总信号数: {total}")
    logger.info(f"日期范围: {dates[0]} ~ {dates[1]}")
    logger.info(f"覆盖交易日: {dates[2]}个")
    
    logger.info(f"\n逻辑类型分布:")
    rows = c.execute("""
        SELECT logic_type, count(*) as cnt
        FROM industry_signals
        GROUP BY logic_type
        ORDER BY cnt DESC
    """).fetchall()
    
    for lt, cnt in rows:
        name = TYPE_NAMES.get(lt, lt)
        pct = cnt / total * 100
        bar = '█' * int(pct / 2)
        logger.info(f"  {name}: {cnt:3d}条 ({pct:.1f}%) {bar}")
    
    # 行业 TOP10
    logger.info(f"\n行业 TOP10:")
    rows = c.execute("""
        SELECT category, count(*) as cnt
        FROM industry_signals
        WHERE category NOT IN ('情绪周期', '市场情绪')
        GROUP BY category
        ORDER BY cnt DESC
        LIMIT 10
    """).fetchall()
    
    for cat, cnt in rows:
        bar = '█' * (cnt // 2)
        logger.info(f"  {cat}: {cnt:3d}条 {bar}")
    
    conn.close()

def cmd_search(args):
    """关键词搜索"""
    keyword = args.keyword
    
    conn = get_conn()
    c = conn.cursor()
    
    limit = getattr(args, 'limit', 20)
    
    rows = c.execute("""
        SELECT date, logic_type, category, keyword as kw, target, signal_content
        FROM industry_signals
        WHERE signal_content LIKE ? OR category LIKE ? OR keyword LIKE ?
        ORDER BY date DESC
        LIMIT ?
    """, (f'%{keyword}%', f'%{keyword}%', f'%{keyword}%', limit)).fetchall()
    
    logger.info(f"\n🔍 搜索「{keyword}」({len(rows)}条)")
    logger.info("=" * 80)
    
    for date, lt, cat, kw, target, content in rows:
        lt_name = TYPE_NAMES.get(lt, lt)
        logger.info(f"\n📅 {date} | {lt_name}")
        logger.info(f"   [{cat}] {kw}")
        if target:
            logger.info(f"   标的: {target}")
        content_display = content[:120] if content else ''
        logger.info(f"   {content_display}")
    
    conn.close()

def main():
    parser = argparse.ArgumentParser(description='🐲 产业逻辑发现模块')
    subparsers = parser.add_subparsers(dest='command')
    
    # types
    subparsers.add_parser('types', help='列出所有产业逻辑类型')
    
    # by-type
    p = subparsers.add_parser('by-type', help='按逻辑类型查询')
    p.add_argument('type', help='逻辑类型ID')
    p.add_argument('--limit', type=int, default=20)
    p.add_argument('--from', dest='from', help='起始日期 YYYY-MM-DD')
    p.add_argument('--to', help='结束日期 YYYY-MM-DD')
    
    # by-sector
    p = subparsers.add_parser('by-sector', help='按行业查询')
    p.add_argument('sector', help='行业名称')
    p.add_argument('--limit', type=int, default=20)
    
    # hot（渊图派生买入信号）
    p = subparsers.add_parser('hot', help='产业逻辑：买入信号（渊图派生）')
    p.add_argument('--limit', type=int, default=15)
    p.add_argument('--min-conf', dest='min_conf', type=float, default=0.7)
    p.add_argument('--with-ts', dest='with_ts', action='store_true', help='只看已解析到 ts_code 的')
    p.add_argument('--echo', action='store_true', help='只看有小鲍第二印证的')

    # echo（小鲍情绪共振视图，降级自旧 hot）
    p = subparsers.add_parser('echo', help='小鲍情绪共振视图（第二印证）')
    p.add_argument('--limit', type=int, default=15)
    
    # trend
    subparsers.add_parser('trend', help='月度趋势')
    
    # timeline
    p = subparsers.add_parser('timeline', help='时间线')
    p.add_argument('type', help='逻辑类型ID')
    
    # stats
    subparsers.add_parser('stats', help='统计摘要')
    
    # search
    p = subparsers.add_parser('search', help='关键词搜索')
    p.add_argument('keyword', help='搜索关键词')
    p.add_argument('--limit', type=int, default=20)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    commands = {
        'types': cmd_types,
        'by-type': cmd_by_type,
        'by-sector': cmd_by_sector,
        'hot': cmd_hot,
        'echo': cmd_echo,
        'trend': cmd_trend,
        'timeline': cmd_timeline,
        'stats': cmd_stats,
        'search': cmd_search,
    }
    
    commands[args.command](args)

if __name__ == "__main__":
    main()
