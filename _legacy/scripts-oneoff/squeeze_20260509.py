#!/usr/bin/env python3
"""
四维度课件 · 终极榨取 v2
处理：1) 各种大标题变体  2) 板块段落式内容  3) 导读文件补充
"""
import sqlite3, os, re, glob
from datetime import datetime

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'db', 'recap.db')
MD = os.path.expanduser('~/Downloads/转换文稿')

def parse_date(fn):
    base = os.path.splitext(fn)[0]
    m = re.match(r'(\d{2})(\d{2})(\d{2})', base)
    if m:
        yy, mm, dd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        year = 2000 + yy if yy < 50 else 1900 + yy
        return f'{year:04d}-{mm:02d}-{dd:02d}'
    return None

def clean(raw):
    text = re.sub(r'\n## 第\d+页\n', '\n', raw)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text

def extract(text):
    r = {'industry_logic': [], 'news_catalysts': [], 'policy_news': [],
         'price_driver': [], 'limit_up': None, 'limit_down': None,
         'consecutive_boards': None, 'ma60': None, 'sentiment_description': None,
         'trend_description': None, 'emotion_stage': None, 'volume_trillion': None,
         'up_down_ratio': None}

    # ========== 行业逻辑 ==========
    # 模式1: "（X）XXX板块/行业" 段落
    for m in re.finditer(r'[（(][一二三四五六七八九十\d]+[）)]\s*([^\n（(]{2,50})\s*\n([^\n]{20,500})', text):
        title, content = m.group(1).strip(), m.group(2).strip()[:400]
        if any(kw in title+content for kw in ['板块','行业','产业链','涨价','逻辑','驱动','催化','IPO','重组']):
            r['industry_logic'].append(f'[{title}] {content[:300]}')

    # 模式2: "核心逻辑："
    for m in re.finditer(r'核心逻辑[：:]\s*([^\n]{10,300})', text):
        r['industry_logic'].append(f'核心逻辑: {m.group(1).strip()[:250]}')

    # 模式3: "X逻辑："
    for m in re.finditer(r'([^\n]{2,18})逻辑[：:]\s*([^\n]{10,250})', text):
        pfx = m.group(1).strip()
        if pfx not in ['核心','交易','事件驱动','底层','炒新','回购注销','老票新']:
            r['industry_logic'].append(f'{pfx}逻辑: {m.group(2).strip()[:200]}')

    # 模式4: 产业链排序/传导
    for m in re.finditer(r'产业链[排序传导顺序][：:]\s*([^\n]{10,250})', text):
        r['industry_logic'].append(f'产业链: {m.group(1).strip()[:200]}')

    # 模式5: 事件驱动逻辑
    for m in re.finditer(r'事件驱动逻辑[：:]\s*([^\n]{10,300})', text):
        r['industry_logic'].append(f'事件驱动: {m.group(1).strip()[:250]}')

    # 模式6: 整段提取 — 各种大标题变体
    for pat in [r'行业动态与板块深度解析[^\n]*\n(.{100,4000})',
                r'(?:当日)?核心行业热点解析[^\n]*\n(.{100,4000})',
                r'重点行业[解剖]析[^\n]*\n(.{100,4000})',
                r'行业与板块机会全梳理[^\n]*\n(.{100,4000})']:
        m = re.search(pat, text, re.DOTALL)
        if m:
            content = m.group(1).strip()[:3000]
            for stop in ['四、市场趋势','四、四维度','五、关键时间','六、市场情绪','四、盘面']:
                idx = content.find(stop)
                if idx > 100: content = content[:idx]; break
            sections = re.split(r'[（(][一二三四五六七八九十\d]+[）)]', content)
            for sec in sections:
                sec = sec.strip()
                if len(sec) > 60:
                    r['industry_logic'].append(sec[:500])

    # ========== 消息催化 ==========
    for pat in [r'重点事件与题材深度剖析[^\n]*\n(.{50,3000})',
                r'重点行业产业信息与投资逻辑[^\n]*\n(.{100,3000})']:
        m = re.search(pat, text, re.DOTALL)
        if m:
            content = m.group(1).strip()[:2000]
            idx = content.find('五、核心交易策略')
            if idx > 50: content = content[:idx]
            r['news_catalysts'].append(f'重点事件: {content[:600]}')

    for m in re.finditer(r'(核心事件|未来[核心]?预期|会议预期|下一周核心事件|催化因素)[：:]\s*([^\n]{10,300})', text):
        r['news_catalysts'].append(f'{m.group(1)}: {m.group(2).strip()[:250]}')

    # 核心催化
    for m in re.finditer(r'核心催化[是：:]\s*([^\n]{10,300})', text):
        r['news_catalysts'].append(f'核心催化: {m.group(1).strip()[:250]}')

    # ========== 政策新闻 ==========
    for pat in [r'市场趋势与政策导向总结[^\n]*\n(.{50,2000})',
                r'宏观市场与资金面核心判断[^\n]*\n(.{100,2000})']:
        m = re.search(pat, text, re.DOTALL)
        if m:
            content = m.group(1).strip()[:1500]
            for stop in ['五、关键时间','五、核心交易','六、市场情绪']:
                idx = content.find(stop)
                if idx > 100: content = content[:idx]; break
            r['policy_news'].append(content[:800])

    m = re.search(r'四[、大]核心趋势[^\n]*\n(.{100,2000})', text, re.DOTALL)
    if m:
        content = m.group(1).strip()[:1000]
        if content and content[:50] not in [p[:50] for p in r['policy_news']]:
            r['policy_news'].append(content[:600])

    for m in re.finditer(r'(国九条|财政政策|货币政策|降准|降息|两会|全会|发改委|工信部|政治局会议).{0,15}[：:]\s*([^\n]{10,300})', text):
        r['policy_news'].append(f'{m.group(1)}: {m.group(2).strip()[:250]}')

    # ========== 涨价驱动 ==========
    m = re.search(r'大宗商品涨价板块[（(][^\n）)]*[）)]\s*\n(.{30,800})', text)
    if m:
        r['price_driver'].append(f'大宗商品: {m.group(1).strip()[:300]}')

    for m in re.finditer(r'([^\n]{2,25})涨价[逻辑主线][：:]\s*([^\n]{10,250})', text):
        r['price_driver'].append(f'[{m.group(1).strip()}] {m.group(2).strip()[:200]}')

    for m in re.finditer(r'([^\n]{2,25})价格[上涨突破升至].{0,15}[：:]\s*([^\n]{10,200})', text):
        r['price_driver'].append(f'[{m.group(1).strip()}] {m.group(2).strip()[:200]}')

    for m in re.finditer(r'(?:发布)?涨价[函通知][，,：:]\s*([^\n]{10,200})', text):
        r['price_driver'].append(f'涨价函: {m.group(1).strip()[:200]}')

    # 价格描述
    for m in re.finditer(r'([^\n]{2,20})价格.*?(?:上涨|突破|升至|飙升至).*?([\d.]+)', text):
        sector = m.group(1).strip()
        price = m.group(2)
        r['price_driver'].append(f'[{sector}] 价格{price}')

    # ========== 数值字段 ==========
    for pat, key in [(r'触及涨停\s*(\d+)', 'limit_up'), (r'实际涨停\s*(\d+)', 'limit_up'),
                     (r'收盘涨停\s*(\d+)', 'limit_up'), (r'涨停\s*(\d+)\s*家', 'limit_up')]:
        m = re.search(pat, text)
        if m and r[key] is None: r[key] = int(m.group(1))

    for pat, key in [(r'触及跌停\s*(\d+)', 'limit_down'), (r'实际跌停\s*(\d+)', 'limit_down'),
                     (r'收盘跌停\s*(\d+)', 'limit_down'), (r'跌停\s*(\d+)\s*家', 'limit_down')]:
        m = re.search(pat, text)
        if m and r[key] is None: r[key] = int(m.group(1))

    m = re.search(r'(\d+)\s*连板', text)
    if m and r['consecutive_boards'] is None: r['consecutive_boards'] = int(m.group(1))

    m = re.search(r'成交[额金额].{0,10}([\d.]+)\s*万亿', text)
    if m: r['volume_trillion'] = float(m.group(1))

    for kw, desc in [('赚钱效应下行','赚钱效应下行'),('赚钱效应分化','赚钱效应分化'),
                      ('赚钱效应上行','赚钱效应上行'),('赚钱效应显著回升','赚钱效应显著回升'),
                      ('赚钱效应小幅上行','赚钱效应小幅上行'),('亏钱效应上行','亏钱效应上行')]:
        if kw in text and r['sentiment_description'] is None:
            r['sentiment_description'] = desc

    stage_map = [('大冰点','冰点'),('情绪冰点','冰点'),('小冰点','冰点'),('冰点','冰点'),
                 ('主升浪','主升'),('主升','主升'),('退潮期','退潮'),('退潮','退潮'),
                 ('过热','过热'),('显著回暖','复苏'),('情绪回暖','复苏'),('复苏','复苏'),
                 ('调整期','调整'),('调整','调整'),('高位震荡','震荡'),('震荡','震荡')]
    for kw, stage in stage_map:
        if kw in text and r['emotion_stage'] is None:
            r['emotion_stage'] = stage

    for kw, desc in [('MA60之上偏多头','MA60之上偏多头'),('高位震荡','高位震荡'),
                      ('放量下跌','放量下跌'),('缩量下跌','缩量下跌'),('放量上涨','放量上涨')]:
        if kw in text and r['trend_description'] is None:
            r['trend_description'] = desc

    m = re.search(r'MA60.{0,20}([\d.]+)\s*点', text)
    if m: r['ma60'] = float(m.group(1))

    for pat in [r'涨\s*(\d{3,4})\s*家[、,，\s]*下[跌落]*\s*(\d{3,4})\s*家',
                r'上涨\s*(\d{3,4})\s*家[、,，\s]*下跌\s*(\d{3,4})\s*家',
                r'(\d{3,4})\s*家上涨[、,，\s]*(\d{3,4})\s*家下跌']:
        m = re.search(pat, text)
        if m:
            up, down = int(m.group(1)), int(m.group(2))
            if 500 < up < 5000 and 500 < down < 5000:
                r['up_down_ratio'] = f'{up}:{down}'
                break

    # 去重
    for k in r:
        if isinstance(r[k], list):
            seen, unique = set(), []
            for item in r[k]:
                key = item[:100]
                if key not in seen:
                    seen.add(key)
                    unique.append(item[:500])
            r[k] = unique[:8]

    return r

def main():
    # 收集所有文件，按日期分组
    files_by_date = {}
    for fp in sorted(glob.glob(os.path.join(MD, '*.md'))):
        date = parse_date(os.path.basename(fp))
        if not date: continue
        fn = os.path.basename(fp)
        if date not in files_by_date:
            files_by_date[date] = {'summary': None, 'guide': None}
        if '总结' in fn:
            files_by_date[date]['summary'] = fp
        elif '导读' in fn:
            files_by_date[date]['guide'] = fp

    conn = sqlite3.connect(DB)
    c = conn.cursor()

    total_updates = 0
    file_count = 0
    stats = {k: 0 for k in ['industry_logic','news_catalysts','policy_news','price_driver']}

    for date in sorted(files_by_date.keys()):
        # 优先总结，其次导读
        fp = files_by_date[date].get('summary') or files_by_date[date].get('guide')
        if not fp: continue

        text = clean(open(fp, 'r', encoding='utf-8').read())
        d = extract(text)

        for k in stats:
            stats[k] += len(d.get(k, []))

        updates = {}
        # 数值字段
        for key, col in [('limit_up','limit_up'),('limit_down','limit_down'),
                         ('consecutive_boards','consecutive_boards'),('ma60','ma60'),
                         ('sentiment_description','sentiment_description'),
                         ('trend_description','trend_description'),
                         ('emotion_stage','emotion_stage'),('volume_trillion','volume_trillion'),
                         ('up_down_ratio','up_down_ratio')]:
            if d.get(key) is not None:
                updates[col] = d[key]

        # 列表字段
        for key, col in [('industry_logic','industry_logic'),('news_catalysts','news_catalysts'),
                         ('policy_news','policy_news'),('price_driver','price_driver')]:
            items = d.get(key, [])
            if items:
                updates[col] = '; '.join(items)

        if updates:
            file_count += 1
            for col, val in updates.items():
                c.execute(f'UPDATE dim3_sentiment_tech SET {col} = ? WHERE date = ?', (val, date))
                total_updates += c.rowcount

    conn.commit()
    conn.close()

    print(f'✅ 终极榨取完成！处理 {file_count} 个日期，{total_updates} 次写入\n')
    print('📊 提取数据量:')
    for k, v in sorted(stats.items(), key=lambda x: -x[1]):
        bar = '█' * min(v//2, 50)
        print(f'  {k:25s} {bar} {v}')

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM dim3_sentiment_tech WHERE date >= "2025-10-19" AND date <= "2026-03-30"')
    total = c.fetchone()[0]
    print(f'\n📊 交集范围内 dim3 填充率 (n={total}):')
    for col in ['emotion_stage','industry_logic','news_catalysts','policy_news','price_driver',
                'up_down_ratio','volume_trillion','limit_up','limit_down','ma60',
                'sentiment_description','trend_description','consecutive_boards']:
        c.execute(f'SELECT COUNT(*) FROM dim3_sentiment_tech WHERE date >= "2025-10-19" AND date <= "2026-03-30" AND {col} IS NOT NULL')
        filled = c.fetchone()[0]
        bar = '█' * int(filled/total*50) + '░' * (50 - int(filled/total*50))
        print(f'  {bar} {col:25s} {filled}/{total} ({filled/total*100:.1f}%)')
    conn.close()

if __name__ == '__main__':
    main()
