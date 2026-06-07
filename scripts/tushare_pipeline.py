#!/usr/bin/env python3
"""
tushare 数据自动填充管线
每日自动拉取最新行情数据填充到 recap.db

功能:
- 自动检测缺失日期
- 拉取涨跌停、成交额、连板数据
- 写入 execution_log 记录

用法:
  python3 tushare_pipeline.py              # 拉取所有缺失日期
  python3 tushare_pipeline.py --from 20260101  # 从某日期开始
  python3 tushare_pipeline.py --latest     # 只拉取最新一天
  python3 tushare_pipeline.py --stats      # 查看当前填充率
"""

import os
import sys
import time
import sqlite3
import argparse
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from exec_logger import ExecLogger, init_log_table

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import config
DB_PATH = config.RECAP_DB

# 从环境变量读取 token，回退到硬编码
TUSHARE_TOKEN = os.environ.get('TUSHARE_TOKEN',
    '32999e6a58e9b207de0d22b60c70ace0f88ddb015d5320dc57956231')

API_INTERVAL = 0.4  # tushare 5000积分: 200次/分钟


def get_pro():
    import tushare as ts
    ts.set_token(TUSHARE_TOKEN)
    return ts.pro_api()


def get_missing_dates(conn, from_date=None):
    """获取需要填充的日期列表"""
    cur = conn.cursor()

    # 获取 dim3_sentiment_tech 中有记录但缺少 tushare 数据的日期
    cur.execute("""
        SELECT DISTINCT date FROM dim3_sentiment_tech
        WHERE (limit_up IS NULL OR limit_down IS NULL
               OR volume_trillion IS NULL OR consecutive_boards IS NULL)
        ORDER BY date
    """)
    all_dates = [r[0] for r in cur.fetchall()]

    if from_date:
        all_dates = [d for d in all_dates if d.replace('-', '') >= from_date]

    return all_dates


def get_latest_trading_date(pro):
    """获取最近一个交易日"""
    try:
        df = pro.trade_cal(exchange='SSE', start_date='20260101',
                          end_date=datetime.now().strftime('%Y%m%d'))
        df = df[df['is_open'] == 1]
        return df.iloc[-1]['cal_date']
    except Exception:
        return None


def fetch_and_backfill(dates, dry_run=False):
    """拉取 tushare 数据并回填"""
    if dry_run:
        logger.info(f"[dry-run] 将处理 {len(dates)} 个日期")
        return 0, 0

    pro = get_pro()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    fetched = 0
    errors = 0

    for i, date in enumerate(dates):
        ts_date = date.replace('-', '')
        logger.info(f"[{i+1}/{len(dates)}] {ts_date}...", end=" ")

        try:
            # 1. 涨跌停
            df = pro.limit_list_d(trade_date=ts_date)
            limit_up = len(df[df['limit'] == 'U'])
            limit_down = len(df[df['limit'] == 'D'])

            # 最高连板
            max_board = 0
            up_stocks = df[df['limit'] == 'U']
            if len(up_stocks) > 0:
                import pandas as pd
                valid = up_stocks['up_stat'].dropna()
                if len(valid) > 0:
                    boards = valid.str.split('/').str[0]
                    nums = pd.to_numeric(boards, errors='coerce').dropna()
                    if len(nums) > 0:
                        max_board = int(nums.max())

            # 2. 成交额（上证指数）
            vol_t = None
            idx_df = pro.index_daily(ts_code='000001.SH', trade_date=ts_date)
            if len(idx_df) > 0:
                amount = idx_df.iloc[0].get('amount')
                if amount and amount > 0:
                    vol_t = round(amount * 1000 / 1e12, 2)  # 千元→万亿元

            # 更新 dim3_sentiment_tech
            cur.execute("""
                UPDATE dim3_sentiment_tech
                SET limit_up = ?, limit_down = ?,
                    volume_trillion = ?, consecutive_boards = ?
                WHERE date = ?
            """, (limit_up, limit_down, vol_t, max_board, date))

            # 更新 tushare_stats
            cur.execute("""
                INSERT OR REPLACE INTO tushare_stats (date, limit_up, limit_down, consecutive_limit)
                VALUES (?, ?, ?, ?)
            """, (date, limit_up, limit_down, max_board))

            conn.commit()
            fetched += 1
            logger.info(f"✅ 涨停={limit_up} 跌停={limit_down} 连板={max_board} 成交={vol_t or 'N/A'}万亿")

        except Exception as e:
            errors += 1
            logger.info(f"❌ {e}")

        time.sleep(API_INTERVAL)

    conn.close()
    return fetched, errors


def print_stats():
    """打印当前填充率"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute('SELECT COUNT(*) FROM dim3_sentiment_tech')
    total = cur.fetchone()[0]

    cols = [
        ('limit_up', '涨停家数'),
        ('limit_down', '跌停家数'),
        ('volume_trillion', '成交额(万亿)'),
        ('consecutive_boards', '连板高度'),
        ('emotion_stage', '情绪阶段'),
        ('industry_logic', '产业逻辑'),
    ]

    logger.info(f"\n{'字段'.ljust(25)} {'填充'.ljust(12)} {'百分比'.ljust(8)} {'进度条'}")
    logger.info("-" * 60)
    for col, label in cols:
        cur.execute(f"SELECT COUNT({col}) FROM dim3_sentiment_tech WHERE {col} IS NOT NULL AND {col} != ''")
        filled = cur.fetchone()[0]
        pct = filled / total * 100 if total > 0 else 0
        bar = '█' * int(pct / 5) + '░' * (20 - int(pct / 5))
        logger.info(f"{label.ljust(20)} {filled:>3}/{total}   {pct:5.1f}%  {bar}")

    conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--from', dest='from_date', help='起始日期 YYYYMMDD')
    parser.add_argument('--latest', action='store_true', help='只拉最新交易日')
    parser.add_argument('--dry-run', action='store_true', help='预览模式')
    parser.add_argument('--stats', action='store_true', help='查看填充率')
    args = parser.parse_args()

    if args.stats:
        print_stats()
        sys.exit(0)

    conn = sqlite3.connect(DB_PATH)
    init_log_table(conn)

    if args.latest:
        pro = get_pro()
        latest = get_latest_trading_date(pro)
        if latest:
            dates = [f"{latest[:4]}-{latest[4:6]}-{latest[6:]}"]
        else:
            logger.info("❌ 无法获取最新交易日")
            sys.exit(1)
    else:
        dates = get_missing_dates(conn, args.from_date)

    logger.info(f"待处理日期: {len(dates)} 个")
    if dates:
        logger.info(f"范围: {dates[0]} ~ {dates[-1]}")

    if dates and not args.dry_run:
        with ExecLogger("tushare_pipeline", "tushare_backfill", conn=conn) as elog:
            fetched, errors = fetch_and_backfill(dates)
            elog.update(rows_affected=fetched,
                       details={"fetched": fetched, "errors": errors})
            logger.info(f"\n✅ 完成: 成功{fetched}, 失败{errors}")

    conn.close()
