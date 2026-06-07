#!/usr/bin/env python3
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import config
from lib.logger import get_logger
logger = get_logger(__name__)
"""
🐲 四维度复盘数据库 · 快速录入工具
用法: python3 recap_import.py --template    # 打印模板
      python3 recap_import.py --file xxx.md  # 解析并入库
      python3 recap_import.py --interactive   # 交互式录入
"""
import sys, argparse, re, os
from recap_db import get_conn, normalize_sector
from sector_standardizer import extract_sectors
from stock_extractor import extract_stocks

TEMPLATE = """\
# 复盘快速录入模板
# 使用说明：填写后保存为 .md 文件，运行 recap_import.py --file xxx.md 入库

## 基本信息
日期: YYYY-MM-DD
Speaker: 小鲍老师/天哥/其他

## Dim1 外围定价
USD/CNY: (可选)
掉期: (可选)
原油: (可选)
方向: 看多/看空/震荡 (可选)

## Dim2 行业主线
主线: (用自然语言描述)
看多板块: 板块1,板块2
看空板块: 板块1,板块2 (可选)

## Dim3 情绪技术
情绪: 冰点/复苏/调整/退潮/主升/过热/震荡
涨停: (数字)
跌停: (数字)
成交(万亿): (数字)
MA60: (可选)
支撑: (可选)
阻力: (可选)
催化: (消息/事件/政策)

## Dim4 交易策略
预案: (具体交易计划)
标的: 个股1,个股2
仓位: (如：6-8成)
风险: (风险提示)
"""


def parse_template(text):
    """解析 Markdown 模板"""
    data = {}
    
    # 基本信息
    m = re.search(r'日期:\s*(\S+)', text)
    if m: data['date'] = m.group(1)
    m = re.search(r'Speaker:\s*(.+)', text)
    if m: data['speaker'] = m.group(1).strip()
    
    # Dim1
    m = re.search(r'USD/CNY:\s*([\d.]+)', text)
    if m: data['usd_cny'] = float(m.group(1))
    m = re.search(r'掉期:\s*([-+\d.]+)', text)
    if m: data['forex_swap'] = float(m.group(1))
    m = re.search(r'原油:\s*([\d.]+)', text)
    if m: data['brent_oil'] = float(m.group(1))
    m = re.search(r'方向:\s*(看多|看空|震荡)', text)
    if m: data['pricing_direction'] = m.group(1)
    
    # Dim2
    m = re.search(r'主线:\s*(.+)', text)
    if m: data['main_line'] = m.group(1).strip()
    m = re.search(r'看多板块:\s*(.+)', text)
    if m: data['sectors_bullish'] = m.group(1).strip()
    m = re.search(r'看空板块:\s*(.+)', text)
    if m: data['sectors_bearish'] = m.group(1).strip()
    
    # Dim3
    m = re.search(r'情绪:\s*(\S+)', text)
    if m: data['emotion_stage'] = m.group(1)
    m = re.search(r'涨停:\s*(\d+)', text)
    if m: data['limit_up'] = int(m.group(1))
    m = re.search(r'跌停:\s*(\d+)', text)
    if m: data['limit_down'] = int(m.group(1))
    m = re.search(r'成交\(万亿\):\s*([\d.]+)', text)
    if m: data['volume_trillion'] = float(m.group(1))
    m = re.search(r'MA60:\s*([\d.]+)', text)
    if m: data['ma60'] = float(m.group(1))
    m = re.search(r'支撑:\s*(.+)', text)
    if m: data['support_level'] = m.group(1).strip()
    m = re.search(r'阻力:\s*(.+)', text)
    if m: data['resistance_level'] = m.group(1).strip()
    m = re.search(r'催化:\s*(.+)', text)
    if m: data['news_catalysts'] = m.group(1).strip()
    
    # Dim4
    m = re.search(r'预案:\s*(.+)', text)
    if m: data['plan'] = m.group(1).strip()
    m = re.search(r'标的:\s*(.+)', text)
    if m: data['key_stocks'] = m.group(1).strip()
    m = re.search(r'仓位:\s*(.+)', text)
    if m: data['position_guidance'] = m.group(1).strip()
    m = re.search(r'风险:\s*(.+)', text)
    if m: data['risk_warnings'] = m.group(1).strip()
    
    return data


def import_recap(data):
    """将解析后的数据入库"""
    conn = get_conn()
    
    # 标准化板块
    if data.get('sectors_bullish'):
        sectors = extract_sectors(data['sectors_bullish'])
        data['sectors_bullish'] = ','.join(sectors) if sectors else data['sectors_bullish']
    
    # 提取个股
    if data.get('key_stocks'):
        stocks = extract_stocks(data['key_stocks'])
        if stocks:
            data['key_stocks'] = ','.join([s[0] for s in stocks])
    
    # 插入主表
    conn.execute(
        "INSERT OR REPLACE INTO recap_daily (date, source, speaker, cycle_stage, market_summary, key_themes) VALUES (?,?,?,?,?,?)",
        (data.get('date'), 'manual', data.get('speaker', ''), None, data.get('main_line', ''), data.get('sectors_bullish', '')))
    
    # Dim1
    if any(k in data for k in ['usd_cny', 'forex_swap', 'brent_oil', 'pricing_direction']):
        conn.execute(
            "INSERT OR REPLACE INTO dim1_external_pricing (date, usd_cny, forex_swap, brent_oil, pricing_direction) VALUES (?,?,?,?,?)",
            (data['date'], data.get('usd_cny'), data.get('forex_swap'), data.get('brent_oil'), data.get('pricing_direction')))
    
    # Dim2
    if data.get('main_line'):
        conn.execute(
            "INSERT OR REPLACE INTO dim2_sector_themes (date, main_line, sectors_bullish, sectors_bearish) VALUES (?,?,?,?)",
            (data['date'], data['main_line'], data.get('sectors_bullish'), data.get('sectors_bearish')))
    
    # Dim3
    conn.execute(
        "INSERT OR REPLACE INTO dim3_sentiment_tech (date, emotion_stage, limit_up, limit_down, volume_trillion, ma60, support_level, resistance_level, news_catalysts) VALUES (?,?,?,?,?,?,?,?,?)",
        (data['date'], data.get('emotion_stage'), data.get('limit_up'), data.get('limit_down'),
         data.get('volume_trillion'), data.get('ma60'), data.get('support_level'), data.get('resistance_level'),
         data.get('news_catalysts')))
    
    # Dim4
    conn.execute(
        "INSERT OR REPLACE INTO dim4_trade_plan (date, plan, key_stocks, position_guidance, risk_warnings) VALUES (?,?,?,?,?)",
        (data['date'], data.get('plan'), data.get('key_stocks'), data.get('position_guidance'), data.get('risk_warnings')))
    
    conn.commit()
    conn.close()
    logger.info(f"✅ {data['date']} 复盘已入库")


def interactive_import():
    """交互式录入"""
    logger.info("🐲 复盘快速录入 (交互式)\n")
    logger.info("按 Enter 跳过可选字段，输入 'q' 退出\n")
    
    data = {}
    data['date'] = input("日期 (YYYY-MM-DD): ").strip()
    if not data['date'] or data['date'] == 'q': return
    data['speaker'] = input("Speaker (小鲍老师): ").strip() or "小鲍老师"
    
    logger.info("\n--- Dim1 外围定价 (可选) ---")
    d = input("USD/CNY: ").strip()
    if d: data['usd_cny'] = float(d)
    d = input("掉期: ").strip()
    if d: data['forex_swap'] = float(d)
    d = input("原油: ").strip()
    if d: data['brent_oil'] = float(d)
    d = input("方向 (看多/看空/震荡): ").strip()
    if d: data['pricing_direction'] = d
    
    logger.info("\n--- Dim2 行业主线 ---")
    data['main_line'] = input("主线: ").strip()
    data['sectors_bullish'] = input("看多板块: ").strip()
    data['sectors_bearish'] = input("看空板块 (可选): ").strip()
    
    logger.info("\n--- Dim3 情绪技术 ---")
    data['emotion_stage'] = input("情绪 (冰点/复苏/调整/退潮/主升/过热): ").strip()
    d = input("涨停: ").strip()
    if d: data['limit_up'] = int(d)
    d = input("跌停: ").strip()
    if d: data['limit_down'] = int(d)
    d = input("成交(万亿): ").strip()
    if d: data['volume_trillion'] = float(d)
    d = input("MA60 (可选): ").strip()
    if d: data['ma60'] = float(d)
    d = input("支撑 (可选): ").strip()
    if d: data['support_level'] = d
    d = input("阻力 (可选): ").strip()
    if d: data['resistance_level'] = d
    data['news_catalysts'] = input("催化 (可选): ").strip()
    
    logger.info("\n--- Dim4 交易策略 ---")
    data['plan'] = input("预案: ").strip()
    data['key_stocks'] = input("标的: ").strip()
    data['position_guidance'] = input("仓位: ").strip()
    data['risk_warnings'] = input("风险 (可选): ").strip()
    
    # 预览
    logger.info(f"\n📋 预览:")
    logger.info(f"   日期: {data['date']}")
    logger.info(f"   情绪: {data.get('emotion_stage', 'N/A')}")
    logger.info(f"   成交: {data.get('volume_trillion', 'N/A')} 万亿")
    logger.info(f"   主线: {data.get('main_line', 'N/A')[:50]}")
    
    confirm = input("\n确认入库? (y/n): ").strip()
    if confirm.lower() == 'y':
        import_recap(data)
    else:
        logger.info("❌ 已取消")


def main():
    parser = argparse.ArgumentParser(description="🐲 复盘快速录入工具")
    parser.add_argument("--template", action="store_true", help="打印模板")
    parser.add_argument("--file", help="解析并入库")
    parser.add_argument("--interactive", action="store_true", help="交互式录入")
    args = parser.parse_args()
    
    if args.template:
        logger.info(TEMPLATE)
    elif args.file:
        if not os.path.exists(args.file):
            logger.info(f"❌ 文件不存在: {args.file}")
            return
        with open(args.file) as f:
            text = f.read()
        data = parse_template(text)
        if not data.get('date'):
            logger.info("❌ 未找到日期字段")
            return
        import_recap(data)
    elif args.interactive:
        interactive_import()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()