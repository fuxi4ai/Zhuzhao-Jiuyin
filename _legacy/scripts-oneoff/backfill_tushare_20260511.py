#!/usr/bin/env python3
"""
从 tushare pro 回灌复盘数据 → recap.db
功能: limit_up, limit_down, volume_trillion, consecutive_boards
命名: backfill_tushare_20260511.py (功能名_日期格式)
"""
import sqlite3
import time
import os
from datetime import datetime

import tushare as ts

RECAP_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'db', 'recap.db')
TUSHARE_TOKEN = os.environ.get('TUSHARE_TOKEN', '')  # 硬编码已移除：用环境变量；旧 token 请轮换

# tushare 频率限制: 200次/分钟，每次调用间隔 0.4s
API_INTERVAL = 0.4


def get_all_dates_to_backfill():
    """获取所有需要回填的日期"""
    recap = sqlite3.connect(RECAP_DB)
    cur = recap.cursor()
    cur.execute('SELECT DISTINCT date FROM dim3_sentiment_tech ORDER BY date')
    all_dates = [r[0] for r in cur.fetchall()]
    recap.close()
    return all_dates


def backfill_from_tushare(dates):
    """从 tushare 拉取并回填数据"""
    ts.set_token(TUSHARE_TOKEN)
    pro = ts.pro_api()

    recap = sqlite3.connect(RECAP_DB)
    rcur = recap.cursor()

    results = []
    total = len(dates)
    fetched = 0
    skipped = 0
    errors = 0

    for i, date in enumerate(dates):
        tushare_date = date.replace('-', '')

        print(f'[{i+1}/{total}] 处理 {date}...', end=' ')

        # 检查是否已有数据
        rcur.execute('SELECT limit_up, limit_down, volume_trillion, consecutive_boards FROM dim3_sentiment_tech WHERE date = ?', (date,))
        rows = rcur.fetchall()
        if not rows:
            print('日期不存在，跳过')
            skipped += 1
            time.sleep(API_INTERVAL)
            continue

        # 检查哪些字段需要填充
        needs = set()
        for row in rows:
            if row[0] is None:
                needs.add('limit_up')
            if row[1] is None:
                needs.add('limit_down')
            if row[2] is None:
                needs.add('volume_trillion')
            if row[3] is None:
                needs.add('consecutive_boards')

        if not needs:
            print('全部已有数据，跳过')
            skipped += 1
            time.sleep(API_INTERVAL)
            continue

        try:
            # 1. 涨跌停数据
            if needs & {'limit_up', 'limit_down', 'consecutive_boards'}:
                df = pro.limit_list_d(trade_date=tushare_date)
                limit_up_count = len(df[df['limit'] == 'U'])
                limit_down_count = len(df[df['limit'] == 'D'])

                # 最高连板数 (从 up_stat 提取 X/Y 中的 X)
                max_board = 0
                up_stocks = df[df['limit'] == 'U']
                if len(up_stocks) > 0:
                    valid_stats = up_stocks['up_stat'].dropna()
                    if len(valid_stats) > 0:
                        boards = valid_stats.str.split('/').str[0]
                        boards_num = boards.astype(int, errors='ignore')
                        # 过滤掉非数字
                        boards_num = boards_num[pd.to_numeric(boards_num, errors='coerce').notna()]
                        if len(boards_num) > 0:
                            max_board = int(boards_num.max())

                # 2. 成交额 → volume_trillion (万亿)
                vol_t = None
                if 'volume_trillion' in needs:
                    # 用指数成交额来估算 (上证指数)
                    idx_df = pro.index_daily(ts_code='000001.SH', trade_date=tushare_date)
                    if len(idx_df) > 0:
                        # amount 单位是千元
                        amount_thousand = idx_df.iloc[0]['amount']
                        if amount_thousand and amount_thousand > 0:
                            # 千元 → 元 → 万亿元
                            amount_yuan = amount_thousand * 1000
                            vol_t = round(amount_yuan / 1e12, 2)

                # 更新数据库
                updated_rows = 0
                for row in rows:
                    updates = {}
                    if 'limit_up' in needs:
                        updates['limit_up'] = limit_up_count
                    if 'limit_down' in needs:
                        updates['limit_down'] = limit_down_count
                    if 'consecutive_boards' in needs:
                        updates['consecutive_boards'] = max_board
                    if 'volume_trillion' in needs and vol_t is not None:
                        updates['volume_trillion'] = vol_t

                    set_clause = ', '.join(f'{k} = ?' for k in updates.keys())
                    values = list(updates.values())
                    rcur.execute(
                        f'UPDATE dim3_sentiment_tech SET {set_clause} WHERE date = ?',
                        values + [date]
                    )
                    updated_rows += rcur.rowcount

                recap.commit()
                fetched += 1

                info = []
                if 'limit_up' in needs:
                    info.append(f'涨停={limit_up_count}')
                if 'limit_down' in needs:
                    info.append(f'跌停={limit_down_count}')
                if 'consecutive_boards' in needs:
                    info.append(f'连板={max_board}')
                if 'volume_trillion' in needs and vol_t is not None:
                    info.append(f'成交={vol_t}万亿')

                print(f'✅ 更新{updated_rows}条: {", ".join(info)}')
            else:
                print('无需此源数据')
                skipped += 1

        except Exception as e:
            print(f'❌ 错误: {e}')
            errors += 1

        time.sleep(API_INTERVAL)

    recap.close()
    print(f'\n=== 回灌完成 ===')
    print(f'成功: {fetched}, 跳过: {skipped}, 错误: {errors}')


def print_stats():
    """打印当前填充率"""
    recap = sqlite3.connect(RECAP_DB)
    cur = recap.cursor()
    cur.execute('SELECT COUNT(*) FROM dim3_sentiment_tech')
    total = cur.fetchone()[0]

    cols = ['limit_up', 'limit_down', 'volume_trillion', 'consecutive_boards',
            'sentiment_description', 'trend_description', 'policy_news',
            'emotion_stage', 'industry_logic', 'up_down_ratio',
            'news_catalysts', 'price_driver']

    print(f'\n=== 当前填充率 (总记录: {total}) ===')
    for c in cols:
        cur.execute(f'SELECT COUNT({c}) FROM dim3_sentiment_tech WHERE {c} IS NOT NULL AND {c} != ""')
        filled = cur.fetchone()[0]
        pct = filled / total * 100
        bar = '█' * int(pct / 5) + '░' * (20 - int(pct / 5))
        print(f'{c:25s} {filled:3d}/{total} ({pct:5.1f}%) {bar}')

    recap.close()


if __name__ == '__main__':
    # 尝试导入 pandas (tushare 返回 DataFrame)
    try:
        import pandas as pd
    except ImportError:
        print('需要先安装 pandas: pip install pandas')
        exit(1)

    dates = get_all_dates_to_backfill()
    print(f'需要处理的日期: {len(dates)} 天')
    print(f'日期范围: {dates[0]} ~ {dates[-1]}')
    print()

    backfill_from_tushare(dates)
    print_stats()
