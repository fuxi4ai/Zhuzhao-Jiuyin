#!/usr/bin/env python3
"""
回灌 jumang 行情数据 → recap.db
从 jumang_market.db 的 daily_market 表补充 limit_up/limit_down
"""
import sqlite3
import os

JUMANG_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'db', 'jumang_market.db')
RECAP_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'db', 'recap.db')

def main():
    jm = sqlite3.connect(JUMANG_DB)
    recap = sqlite3.connect(RECAP_DB)
    jcur = jm.cursor()
    rcur = recap.cursor()

    # 获取所有需要补充的日期 (limit_up 或 limit_down 为 NULL)
    rcur.execute('''
        SELECT DISTINCT date FROM dim3_sentiment_tech
        WHERE limit_up IS NULL OR limit_down IS NULL
        ORDER BY date
    ''')
    null_dates = [r[0] for r in rcur.fetchall()]
    print(f'需要补充的日期: {len(null_dates)} 天')

    # 从 jumang 查询数据
    jcur.execute('''
        SELECT trade_date, limit_up, limit_down
        FROM daily_market
        WHERE trade_date IN ({})
    '''.format(','.join('?' for _ in null_dates)),
    [d.replace('-', '') for d in null_dates])

    jm_data = {}
    for row in jcur.fetchall():
        jm_data[row[0]] = {'limit_up': row[1], 'limit_down': row[2]}

    print(f'jumang 匹配到: {len(jm_data)} 天')

    # 更新
    updated = 0
    for d in null_dates:
        key = d.replace('-', '')
        if key not in jm_data:
            continue
        lu = jm_data[key]['limit_up']
        ld = jm_data[key]['limit_down']

        rcur.execute('''
            UPDATE dim3_sentiment_tech
            SET limit_up = ?, limit_down = ?
            WHERE date = ? AND (limit_up IS NULL OR limit_down IS NULL)
        ''', (lu, ld, d))
        updated += rcur.rowcount

    recap.commit()
    print(f'更新了 {updated} 条记录')

    # 验证
    rcur.execute('SELECT COUNT(*) FROM dim3_sentiment_tech WHERE limit_up IS NOT NULL')
    lu_filled = rcur.fetchone()[0]
    rcur.execute('SELECT COUNT(*) FROM dim3_sentiment_tech')
    total = rcur.fetchone()[0]
    rcur.execute('SELECT COUNT(*) FROM dim3_sentiment_tech WHERE limit_down IS NOT NULL')
    ld_filled = rcur.fetchone()[0]

    print(f'\n=== 回填后 ===')
    print(f'limit_up: {lu_filled}/{total} ({lu_filled/total*100:.1f}%)')
    print(f'limit_down: {ld_filled}/{total} ({ld_filled/total*100:.1f}%)')

    # WAL checkpoint
    recap.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    recap.close()
    jm.close()
    print('WAL checkpoint 完成')

if __name__ == '__main__':
    main()
