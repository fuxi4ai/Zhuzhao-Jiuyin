#!/usr/bin/env python3
"""
四维度 Markdown 数据回灌 — 更新已有记录中 NULL 的字段
"""

import sqlite3, os, re, glob
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'db', 'recap.db')
MD_DIR = os.path.expanduser('~/Downloads/转换文稿')

def parse_date(filename):
    base = os.path.splitext(os.path.basename(filename))[0]
    m = re.match(r'(\d{2})(\d{2})(\d{2})', base)
    if m:
        yy, mm, dd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        year = 2000 + yy if yy < 50 else 1900 + yy
        return f'{year:04d}-{mm:02d}-{dd:02d}'
    return None

def extract(text):
    r = {}
    ft = text

    # 外汇掉期
    m = re.search(r'外汇掉期.*?(-?\d+)', ft)
    if m: r['forex_swap'] = int(m.group(1))

    # 汇率
    m = re.search(r'(?:外汇汇率|人民币汇率|美元兑人民币|离岸人民币).*?([\d.]+)', ft)
    if m:
        v = float(m.group(1))
        if 6.0 < v < 8.0: r['usd_cny'] = v

    # 原油
    m = re.search(r'(?:布伦特)?原油[价格]?[为：:]\s*([\d.]+)', ft)
    if m: r['brent_oil'] = float(m.group(1))

    # 涨跌停
    m = re.search(r'触及涨停\s*(\d+)', ft)
    if m: r['limit_up_touch'] = int(m.group(1))
    m = re.search(r'实际涨停\s*(\d+)', ft)
    if m: r['limit_up'] = int(m.group(1))
    if 'limit_up' not in r:
        m = re.search(r'涨停\s*(\d+)\s*家', ft)
        if m: r['limit_up'] = int(m.group(1))

    m = re.search(r'触及跌停\s*(\d+)', ft)
    if m: r['limit_down_touch'] = int(m.group(1))
    m = re.search(r'实际跌停\s*(\d+)', ft)
    if m: r['limit_down'] = int(m.group(1))
    if 'limit_down' not in r:
        m = re.search(r'跌停\s*(\d+)\s*家', ft)
        if m: r['limit_down'] = int(m.group(1))

    # 连板
    m = re.search(r'(\d+)\s*连板', ft)
    if m: r['consecutive_boards'] = int(m.group(1))

    # 成交额
    m = re.search(r'成交[额金额].*?([\d.]+)\s*万亿', ft)
    if not m: m = re.search(r'A股成交.*?([\d.]+)\s*万亿', ft)
    if not m: m = re.search(r'市场成交.*?([\d.]+)\s*万亿', ft)
    if m: r['volume_trillion'] = float(m.group(1))

    # 成交量描述
    if '严重缩量' in ft: r['volume_description'] = '严重缩量'
    elif '缩量' in ft: r['volume_description'] = '缩量'
    elif '放量' in ft: r['volume_description'] = '放量'

    # MA60
    m = re.search(r'MA60.*?([\d.]+)\s*点', ft)
    if not m: m = re.search(r'MA60[均线]*[为：:=]\s*([\d.]+)', ft)
    if m: r['ma60'] = float(m.group(1))

    # 情绪阶段
    stage_map = [
        ('大冰点','冰点'),('情绪冰点','冰点'),('小冰点','冰点'),('市场冰点','冰点'),
        ('主升浪','主升'),('主升','主升'),('退潮期','退潮'),('退潮','退潮'),
        ('过热','过热'),('显著回暖','复苏'),('情绪回暖','复苏'),('复苏','复苏'),
        ('调整期','调整'),('调整','调整'),('高位震荡','震荡'),('震荡','震荡'),
    ]
    for kw, stage in stage_map:
        if kw in ft:
            r['emotion_stage'] = stage
            break

    # 赚钱效应
    for kw, desc in [('赚钱效应下行','赚钱效应下行'),('赚钱效应分化','赚钱效应分化'),
                      ('赚钱效应上行','赚钱效应上行'),('赚钱效应显著回升','赚钱效应显著回升'),
                      ('赚钱效应小幅上行','赚钱效应小幅上行'),('亏钱效应上行','亏钱效应上行')]:
        if kw in ft:
            r['sentiment_description'] = desc
            break

    # 趋势
    for kw, desc in [('MA60之上偏多头','MA60之上偏多头'),('高位震荡','高位震荡'),
                      ('放量下跌','放量下跌'),('缩量下跌','缩量下跌'),('放量上涨','放量上涨')]:
        if kw in ft:
            r['trend_description'] = desc
            break

    # 涨跌家数比
    m = re.search(r'涨\s*(\d+)\s*家[、,，\s]*下[跌落]*\s*(\d+)\s*家', ft)
    if not m: m = re.search(r'上涨\s*(\d+)\s*家[、,，\s]*下跌\s*(\d+)\s*家', ft)
    if not m: m = re.search(r'(\d+)\s*家上涨[、,，\s]*(\d+)\s*家下跌', ft)
    if m:
        up, down = int(m.group(1)), int(m.group(2))
        if up > 100 and down > 100:
            r['up_down_ratio'] = f'{up}:{down}'

    # 板块
    for pat in [r'看多[：:]\s*([^\n]+)', r'看好[：:]\s*([^\n]+)']:
        for m in re.finditer(pat, ft):
            items = re.split(r'[、，,\s]+', m.group(1).strip())
            r.setdefault('sectors_bullish', []).extend([i.strip() for i in items if 1 < len(i.strip()) < 20])
    for pat in [r'看空[：:]\s*([^\n]+)', r'不看好[：:]\s*([^\n]+)']:
        for m in re.finditer(pat, ft):
            items = re.split(r'[、，,\s]+', m.group(1).strip())
            r.setdefault('sectors_bearish', []).extend([i.strip() for i in items if 1 < len(i.strip()) < 20])
    for pat in [r'上涨热[点门][：:]\s*([^\n]+)', r'热点板块[：:]\s*([^\n]+)']:
        for m in re.finditer(pat, ft):
            items = re.split(r'[、，,\s]+', m.group(1).strip())
            r.setdefault('hot_sectors', []).extend([i.strip() for i in items if 1 < len(i.strip()) < 20])

    # 政策/产业/涨价
    for pat in [r'政策[：:]\s*([^\n]{5,50})']:
        for m in re.finditer(pat, ft):
            r.setdefault('policy_news', []).append(m.group(1).strip()[:200])
    for pat in [r'产业[逻辑链][：:]\s*([^\n]{10,200})', r'核心逻辑[：:]\s*([^\n]{10,150})']:
        for m in re.finditer(pat, ft):
            r.setdefault('industry_logic', []).append(m.group(1).strip()[:200])
    for pat in [r'涨价.*?逻辑.*?([^\n]{10,150})', r'涨价主线.*?([^\n]{10,150})']:
        for m in re.finditer(pat, ft):
            r.setdefault('price_driver', []).append(m.group(1).strip()[:200])

    # 消息催化
    for pat in [r'[（(]消息[）)]:?\s*([^\n]{5,100})', r'消息面[：:]\s*([^\n]{5,100})']:
        for m in re.finditer(pat, ft):
            r.setdefault('news_catalysts', []).append(m.group(1).strip()[:200])

    # 策略
    if '偏多头' in ft: r['strategy_idea'] = 'MA60之上偏多头思维'
    elif '控制仓位' in ft: r['strategy_idea'] = '控制仓位'
    elif '水下低吸' in ft: r['strategy_idea'] = '水下低吸'
    if 'Double仓' in ft or '加倍仓' in ft: r['position_guidance'] = '突破关键位可加倍仓'
    elif '空仓' in ft: r['position_guidance'] = '空仓观望'
    elif '轻仓' in ft: r['position_guidance'] = '轻仓操作'
    elif '重仓' in ft: r['position_guidance'] = '可适当重仓'
    elif '减仓' in ft: r['position_guidance'] = '减仓观望'
    risks = []
    if '假消息' in ft: risks.append('假消息频发需辨别')
    if '高位大票' in ft: risks.append('高位大票上方有顶')
    if risks: r['risk_warnings'] = '；'.join(risks)

    return r

def update_record(conn, date, d):
    c = conn.cursor()
    updated = []

    # UPDATE dim3_sentiment_tech
    fields = {
        'emotion_stage': d.get('emotion_stage'),
        'limit_up': d.get('limit_up'),
        'limit_down': d.get('limit_down'),
        'consecutive_boards': d.get('consecutive_boards'),
        'volume_trillion': d.get('volume_trillion'),
        'ma60': d.get('ma60'),
        'sentiment_description': d.get('sentiment_description'),
        'trend_description': d.get('trend_description'),
        'up_down_ratio': d.get('up_down_ratio'),
        'volume_description': d.get('volume_description'),
        'policy_news': ', '.join(d.get('policy_news', [])) if d.get('policy_news') else None,
        'industry_logic': ', '.join(d.get('industry_logic', [])) if d.get('industry_logic') else None,
        'price_driver': ', '.join(d.get('price_driver', [])) if d.get('price_driver') else None,
        'news_catalysts': ', '.join(d.get('news_catalysts', [])) if d.get('news_catalysts') else None,
    }
    sets = []
    vals = []
    for col, val in fields.items():
        if val is not None:
            sets.append(f'{col} = ?')
            vals.append(val)
    if sets:
        vals.append(date)
        sql = f'UPDATE dim3_sentiment_tech SET {", ".join(sets)} WHERE date = ?'
        c.execute(sql, vals)
        updated.append(f'dim3:{len(sets)} fields')

    # UPDATE dim1_external_pricing
    d1_fields = {'forex_swap': d.get('forex_swap'), 'usd_cny': d.get('usd_cny'), 'brent_oil': d.get('brent_oil')}
    sets1, vals1 = [], []
    for col, val in d1_fields.items():
        if val is not None:
            sets1.append(f'{col} = ?')
            vals1.append(val)
    if sets1:
        # Check if date exists
        c.execute('SELECT date FROM dim1_external_pricing WHERE date = ?', (date,))
        if c.fetchone():
            vals1.append(date)
            c.execute(f'UPDATE dim1_external_pricing SET {", ".join(sets1)} WHERE date = ?', vals1)
            updated.append(f'dim1:{len(sets1)} fields')
        else:
            vals1.append(date)
            c.execute(f'INSERT INTO dim1_external_pricing (date, {", ".join(d1_fields.keys())}, created_at) VALUES (?, {", ".join(["?"]*len(d1_fields))}, ?)',
                [date] + [d1_fields[k] for k in d1_fields.keys()] + [datetime.now().isoformat()])
            updated.append(f'dim1:INSERT')

    # UPDATE dim2_sector_themes
    d2 = {}
    if d.get('sectors_bullish'): d2['sectors_bullish'] = ', '.join(d['sectors_bullish'])
    if d.get('sectors_bearish'): d2['sectors_bearish'] = ', '.join(d['sectors_bearish'])
    if d.get('hot_sectors'): d2['hot_sectors'] = ', '.join(d['hot_sectors'])
    if d.get('limit_up'): d2['limit_up_count'] = d['limit_up']
    if d.get('limit_down'): d2['limit_down_count'] = d['limit_down']
    sets2, vals2 = [], []
    for col, val in d2.items():
        sets2.append(f'{col} = ?')
        vals2.append(val)
    if sets2:
        c.execute('SELECT date FROM dim2_sector_themes WHERE date = ?', (date,))
        if c.fetchone():
            vals2.append(date)
            c.execute(f'UPDATE dim2_sector_themes SET {", ".join(sets2)} WHERE date = ?', vals2)
            updated.append(f'dim2:{len(sets2)} fields')
        else:
            cols = list(d2.keys()) + ['date', 'created_at']
            placeholders = ','.join(['?'] * len(cols))
            vals2 += [date, datetime.now().isoformat()]
            c.execute(f'INSERT INTO dim2_sector_themes ({", ".join(cols)}) VALUES ({placeholders})', vals2)
            updated.append(f'dim2:INSERT')

    # UPDATE dim4_trade_plan
    d4 = {}
    if d.get('strategy_idea'): d4['strategy_idea'] = d['strategy_idea']
    if d.get('position_guidance'): d4['position_guidance'] = d['position_guidance']
    if d.get('risk_warnings'): d4['risk_warnings'] = d['risk_warnings']
    sets4, vals4 = [], []
    for col, val in d4.items():
        sets4.append(f'{col} = ?')
        vals4.append(val)
    if sets4:
        c.execute('SELECT date FROM dim4_trade_plan WHERE date = ?', (date,))
        if c.fetchone():
            vals4.append(date)
            c.execute(f'UPDATE dim4_trade_plan SET {", ".join(sets4)} WHERE date = ?', vals4)
            updated.append(f'dim4:{len(sets4)} fields')
        else:
            cols = list(d4.keys()) + ['date', 'created_at']
            vals4 += [date, datetime.now().isoformat()]
            c.execute(f'INSERT INTO dim4_trade_plan ({", ".join(cols)}) VALUES ({",".join(["?"]*len(cols))})', vals4)
            updated.append(f'dim4:INSERT')

    return updated

def main():
    files = sorted(glob.glob(os.path.join(MD_DIR, '*.md')))
    conn = sqlite3.connect(DB_PATH)

    updated_count = 0
    new_insert = 0
    skip_count = 0
    field_updates = 0

    for fp in files:
        date = parse_date(fp)
        if not date: continue
        try:
            text = open(fp, 'r', encoding='utf-8').read()
            d = extract(text)
            updates = update_record(conn, date, d)
            if updates:
                updated_count += 1
                field_updates += len(updates)
            else:
                skip_count += 1
        except Exception as e:
            pass

    conn.commit()
    conn.close()

    print(f'回灌完成！更新 {updated_count} 份文件 ({field_updates} 次更新) | 跳过 {skip_count} 份')

    # 打印更新后的统计
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    print(f'\n📊 数据库最终状态:')
    for t in ['recap_daily', 'dim1_external_pricing', 'dim2_sector_themes', 'dim3_sentiment_tech', 'dim4_trade_plan', 'dim4_stock_analysis']:
        c.execute(f'SELECT COUNT(*) FROM {t}')
        print(f'  {t}: {c.fetchone()[0]} 条')

    # 检查新字段填充率
    print(f'\n📊 dim3_sentiment_tech 新字段填充率:')
    for col in ['emotion_stage', 'limit_up', 'limit_down', 'consecutive_boards', 'volume_trillion',
                'ma60', 'sentiment_description', 'trend_description', 'up_down_ratio',
                'volume_description', 'policy_news', 'industry_logic', 'price_driver', 'news_catalysts']:
        c.execute(f'SELECT COUNT(*) FROM dim3_sentiment_tech WHERE {col} IS NOT NULL')
        filled = c.fetchone()[0]
        c.execute(f'SELECT COUNT(*) FROM dim3_sentiment_tech')
        total = c.fetchone()[0]
        pct = f'{filled/total*100:.1f}%' if total else '0%'
        print(f'  {col}: {filled}/{total} ({pct})')

    # dim1 填充率
    print(f'\n📊 dim1_external_pricing 新字段填充率:')
    for col in ['forex_swap', 'usd_cny', 'brent_oil']:
        c.execute(f'SELECT COUNT(*) FROM dim1_external_pricing WHERE {col} IS NOT NULL')
        filled = c.fetchone()[0]
        c.execute(f'SELECT COUNT(*) FROM dim1_external_pricing')
        total = c.fetchone()[0]
        pct = f'{filled/total*100:.1f}%' if total else '0%'
        print(f'  {col}: {filled}/{total} ({pct})')

    # dim2 填充率
    print(f'\n📊 dim2_sector_themes 新字段填充率:')
    for col in ['sectors_bullish', 'sectors_bearish', 'hot_sectors', 'limit_up_count', 'limit_down_count']:
        c.execute(f'SELECT COUNT(*) FROM dim2_sector_themes WHERE {col} IS NOT NULL')
        filled = c.fetchone()[0]
        c.execute(f'SELECT COUNT(*) FROM dim2_sector_themes')
        total = c.fetchone()[0]
        pct = f'{filled/total*100:.1f}%' if total else '0%'
        print(f'  {col}: {filled}/{total} ({pct})')

    # dim4 填充率
    print(f'\n📊 dim4_trade_plan 新字段填充率:')
    for col in ['strategy_idea', 'position_guidance', 'risk_warnings']:
        c.execute(f'SELECT COUNT(*) FROM dim4_trade_plan WHERE {col} IS NOT NULL')
        filled = c.fetchone()[0]
        c.execute(f'SELECT COUNT(*) FROM dim4_trade_plan')
        total = c.fetchone()[0]
        pct = f'{filled/total*100:.1f}%' if total else '0%'
        print(f'  {col}: {filled}/{total} ({pct})')

    conn.close()

if __name__ == '__main__':
    main()
