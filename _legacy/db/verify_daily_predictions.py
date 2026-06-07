#!/usr/bin/env python3
from .lib.logger import get_logger
logger = get_logger(__name__)
"""
每日预测验证脚本
每日收盘后运行，验证前一天的预测准确率

用法: python3 verify_daily_predictions.py

逻辑:
1. 查找 predictor_accuracy 中 is_correct IS NULL 的记录
2. 用 tushare_index 上证次日数据验证情绪周期预测
3. 更新 is_correct 和 verified_at
"""

import sqlite3

DB_PATH = "/home/admin/openclaw/workspace/projects/烛照九阴/db/recap.db"

STAGE_TO_DIRECTION = {
    "主升": 1,      # 看多
    "复苏": 1,      # 看多
    "过热": 0.5,    # 偏多谨慎
    "冰点": -1,     # 预期反弹（涨）
    "调整": -0.5,   # 偏空
    "退潮": -1,     # 看空
    "震荡": 0,      # 中性
}

def verify():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 获取上证指数日K
    cur.execute("""
        SELECT trade_date, pct_chg
        FROM tushare_index
        WHERE ts_code = '000001.SH' AND pct_chg IS NOT NULL
        ORDER BY trade_date
    """)
    index_data = {}
    for row in cur.fetchall():
        raw = row[0]
        if len(raw) == 8:
            normalized = f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
            index_data[normalized] = float(row[1])

    sorted_dates = sorted(index_data.keys())

    # 查找待验证的情绪周期预测
    cur.execute("""
        SELECT id, date, prediction, next_day_return
        FROM predictor_accuracy
        WHERE prediction_type = '情绪周期' AND is_correct IS NULL
        ORDER BY date
    """)
    pending = cur.fetchall()

    updated = 0
    for row in pending:
        pa_id, pred_date, prediction, existing_return = row

        if pred_date not in index_data:
            continue

        idx = sorted_dates.index(pred_date)
        if idx >= len(sorted_dates) - 1:
            continue  # 还没有次日数据

        next_date = sorted_dates[idx + 1]
        next_day_return = index_data[next_date]

        # 判断是否正确
        direction = STAGE_TO_DIRECTION.get(prediction, 0)
        is_correct = None

        if direction > 0:  # 看多
            is_correct = 1 if next_day_return > 0 else 0
        elif direction < 0:  # 看空
            is_correct = 1 if next_day_return < 0 else 0
        elif direction == 0.5:  # 偏多谨慎
            is_correct = 1 if next_day_return > -0.5 else 0
        elif direction == -0.5:  # 偏空
            is_correct = 1 if next_day_return <= 0 else 0
        else:  # 震荡/中性
            is_correct = 1 if abs(next_day_return) < 1.0 else 0

        actual_text = f"{'涨' if next_day_return > 0 else '跌'} {abs(next_day_return):.2f}%"

        cur.execute("""
            UPDATE predictor_accuracy
            SET is_correct = ?, actual_result = ?, next_day_return = ?,
                verified_at = datetime('now')
            WHERE id = ?
        """, (is_correct, actual_text, next_day_return, pa_id))
        updated += 1

    conn.commit()

    if updated > 0:
        logger.info(f"✅ 验证了 {updated} 条预测")
    else:
        logger.info("ℹ️ 没有待验证的预测（或暂无次日数据）")

    # 打印最新准确率
    cur.execute("""
        SELECT predictor_name,
               COUNT(*) as total,
               SUM(CASE WHEN is_correct=1 THEN 1 ELSE 0 END) as correct,
               SUM(CASE WHEN is_correct=0 THEN 1 ELSE 0 END) as wrong
        FROM predictor_accuracy
        WHERE is_correct IS NOT NULL
        GROUP BY predictor_name
    """)
    for row in cur.fetchall():
        c, w = row[2], row[3]
        acc = c / (c + w) * 100 if (c + w) > 0 else 0
        logger.info(f"  {row[0]}: {c}/{row[1]} = {acc:.1f}%")

    conn.close()

if __name__ == "__main__":
    verify()
