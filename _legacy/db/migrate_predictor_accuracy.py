#!/usr/bin/env python3
from .lib.logger import get_logger
logger = get_logger(__name__)
"""
Phase 1: 创建 predictor_accuracy 表
Phase 2: 回填 cycle_comparison 准确率（小鲍老师情绪周期判断 vs 实际市场）
Phase 3: 回填 dim4_trade_plan 预测记录
"""

import sqlite3
import json
from datetime import datetime

DB_PATH = "/home/admin/openclaw/workspace/projects/烛照九阴/db/recap.db"

STAGE_TO_DIRECTION = {
    "主升": 1,      # 看多
    "复苏": 1,      # 看多
    "过热": 0.5,    # 偏多但偏谨慎
    "冰点": -1,     # 偏空（但冰点后反弹概率大，所以特殊处理）
    "调整": -0.5,   # 偏空
    "退潮": -1,     # 看空
    "震荡": 0,      # 中性
}

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ============================================================
# Phase 1: 创建 predictor_accuracy 表
# ============================================================
def create_table(conn):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS predictor_accuracy (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            predictor_name  TEXT NOT NULL,          -- 预测者：小鲍老师/九儿/...
            date            TEXT NOT NULL,          -- 预测日期
            prediction_type TEXT NOT NULL,          -- 情绪周期/涨跌方向/板块/个股
            prediction      TEXT NOT NULL,          -- 具体预测内容
            actual_result   TEXT,                   -- 实际结果
            is_correct      INTEGER,                -- 1=正确, 0=错误, NULL=待验证
            next_day_return REAL,                   -- 次日大盘涨跌幅（参考）
            notes           TEXT,
            created_at      TEXT DEFAULT (datetime('now')),
            verified_at     TEXT
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pa_predictor ON predictor_accuracy(predictor_name)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pa_date ON predictor_accuracy(date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pa_type ON predictor_accuracy(prediction_type)")
    conn.commit()
    logger.info("✅ Phase 1: predictor_accuracy 表创建完成")

# ============================================================
# Phase 2: 回填 cycle_comparison — 用 tushare_index 验证
# ============================================================
def backfill_cycle_comparison(conn):
    cur = conn.cursor()

    # 获取上证指数的日K数据，计算每日涨跌幅
    cur.execute("""
        SELECT trade_date, close, pct_chg
        FROM tushare_index
        WHERE ts_code = '000001.SH'
        ORDER BY trade_date
    """)
    index_rows = cur.fetchall()

    # 构建 {date_normalized: pct_chg} 字典
    # tushare_index 日期格式: 20240219 → 转成 2024-02-19
    index_data = {}
    for row in index_rows:
        raw_date = row["trade_date"]
        pct = row["pct_chg"]
        if pct is not None and len(raw_date) == 8:
            normalized = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"
            index_data[normalized] = float(pct)

    # 排序日期
    sorted_dates = sorted(index_data.keys())
    logger.info(f"📊 上证指数日K数据: {len(sorted_dates)} 条, 范围 {sorted_dates[0]} ~ {sorted_dates[-1]}")

    # 获取所有 cycle_comparison 记录
    cur.execute("""
        SELECT date, bao_stage, quant_stage, quant_score
        FROM cycle_comparison
        ORDER BY date
    """)
    comp_rows = cur.fetchall()

    updated = 0
    inserted = 0

    for row in comp_rows:
        pred_date = row["date"]
        bao_stage = row["bao_stage"]
        quant_stage = row["quant_stage"]
        quant_score = row["quant_score"]

        # 找到次日数据
        idx = sorted_dates.index(pred_date) if pred_date in sorted_dates else -1
        next_date = sorted_dates[idx + 1] if 0 <= idx < len(sorted_dates) - 1 else None

        next_day_return = None
        actual_result_text = None
        bao_correct = None

        if next_date and next_date in index_data:
            next_day_return = index_data[next_date]
            # 判断涨跌
            if next_day_return > 0:
                actual_result_text = f"涨 {next_day_return:.2f}%"
            elif next_day_return < 0:
                actual_result_text = f"跌 {abs(next_day_return):.2f}%"
            else:
                actual_result_text = f"平 {next_day_return:.2f}%"

        # 判断小鲍老师的阶段判断是否准确
        # 逻辑：
        #   主升/复苏 → 预期次日上涨
        #   退潮/调整 → 预期次日下跌
        #   冰点 → 预期反弹（上涨），因为冰点是最低谷
        #   过热 → 预期回调（下跌）
        #   震荡 → 预期小幅波动
        direction = STAGE_TO_DIRECTION.get(bao_stage, 0)

        if next_day_return is not None:
            if direction > 0:  # 看多
                bao_correct = 1 if next_day_return > 0 else 0
            elif direction < 0:  # 看空
                bao_correct = 1 if next_day_return < 0 else 0
            elif direction == 0.5:  # 偏多谨慎
                bao_correct = 1 if next_day_return > -0.5 else 0
            elif direction == -0.5:  # 偏空
                bao_correct = 1 if next_day_return <= 0 else 0
            else:  # 震荡/中性
                bao_correct = 1 if abs(next_day_return) < 1.0 else 0

        # 更新 cycle_comparison
        cur.execute("""
            UPDATE cycle_comparison
            SET bao_correct = ?, next_day_return = ?, verified_at = datetime('now')
            WHERE date = ?
        """, (bao_correct, next_day_return, pred_date))

        # 写入 predictor_accuracy
        cur.execute("""
            INSERT INTO predictor_accuracy (
                predictor_name, date, prediction_type, prediction,
                actual_result, is_correct, next_day_return, notes, verified_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (
            "小鲍老师", pred_date, "情绪周期",
            bao_stage,
            actual_result_text,
            bao_correct,
            next_day_return,
            f"上证指数 {pred_date} 次日涨跌 {next_date}",
        ))

        updated += 1
        inserted += 1

    conn.commit()

    # 统计
    cur.execute("SELECT COUNT(*) FROM cycle_comparison WHERE bao_correct = 1")
    correct = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM cycle_comparison WHERE bao_correct = 0")
    wrong = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM cycle_comparison WHERE bao_correct IS NULL")
    unknown = cur.fetchone()[0]

    logger.info(f"✅ Phase 2: 回填完成")
    logger.info(f"   总计: {updated} 条")
    logger.info(f"   正确: {correct} ({correct/(correct+wrong)*100:.1f}%) 正确" if (correct+wrong) > 0 else "   无可验证数据")
    logger.info(f"   错误: {wrong}")
    logger.info(f"   待验证: {unknown}（无次日K线数据）")

    return correct, wrong, unknown

# ============================================================
# Phase 3: 回填 dim4_trade_plan 中的 prediction 记录
# ============================================================
def backfill_trade_plans(conn):
    cur = conn.cursor()

    # 看看有 prediction 数据的行
    cur.execute("""
        SELECT date, prediction, operation_advice, strategy_idea
        FROM dim4_trade_plan
        WHERE prediction IS NOT NULL OR operation_advice IS NOT NULL
        LIMIT 20
    """)
    rows = cur.fetchall()
    logger.info(f"\n📋 dim4_trade_plan 有预测内容的行数: {len(rows)}")
    for r in rows:
        logger.info(f"  {r['date']}: pred={r['prediction'][:50] if r['prediction'] else 'None'}, advice={r['operation_advice'][:50] if r['operation_advice'] else 'None'}")

    if not rows:
        logger.info("   → dim4_trade_plan 暂无 prediction 数据，跳过 Phase 3")
        return 0

    inserted = 0
    for row in rows:
        pred_text = row["prediction"] or ""
        advice = row["operation_advice"] or ""
        strategy = row["strategy_idea"] or ""
        pred_content = f"{pred_text} | {advice} | {strategy}".strip(" | ")

        cur.execute("""
            INSERT INTO predictor_accuracy (
                predictor_name, date, prediction_type, prediction,
                notes, verified_at
            ) VALUES (?, ?, ?, ?, ?, datetime('now'))
        """, (
            "小鲍老师", row["date"], "交易计划",
            pred_content,
            f"来自 dim4_trade_plan, 待验证",
        ))
        inserted += 1

    conn.commit()
    logger.info(f"✅ Phase 3: 写入 {inserted} 条交易计划预测（待后续验证）")
    return inserted

# ============================================================
# Phase 4: 生成汇总报告
# ============================================================
def generate_summary(conn):
    cur = conn.cursor()

    logger.info("\n" + "="*50)
    logger.info("📊 预测者准确率汇总")
    logger.info("="*50)

    cur.execute("""
        SELECT predictor_name,
               COUNT(*) as total,
               SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) as correct,
               SUM(CASE WHEN is_correct = 0 THEN 1 ELSE 0 END) as wrong,
               SUM(CASE WHEN is_correct IS NULL THEN 1 ELSE 0 END) as pending
        FROM predictor_accuracy
        GROUP BY predictor_name
    """)
    rows = cur.fetchall()
    for r in rows:
        accuracy = r["correct"] / (r["correct"] + r["wrong"]) * 100 if (r["correct"] + r["wrong"]) > 0 else None
        print(f"  {r['predictor_name']}: 总{r['total']} 正确{r['correct']} 错误{r['wrong']} 待验证{r['pending']}"
              + (f" 准确率 {accuracy:.1f}%" if accuracy else ""))

    # 按情绪阶段细分
    logger.info("\n📊 小鲍老师 · 各情绪阶段准确率")
    logger.info("-" * 50)
    cur.execute("""
        SELECT prediction,
               COUNT(*) as total,
               SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) as correct,
               SUM(CASE WHEN is_correct = 0 THEN 1 ELSE 0 END) as wrong,
               AVG(next_day_return) as avg_next_return
        FROM predictor_accuracy
        WHERE predictor_name = '小鲍老师' AND prediction_type = '情绪周期'
        GROUP BY prediction
        ORDER BY correct DESC
    """)
    rows = cur.fetchall()
    logger.info(f"  {'阶段':<8} {'总数':>4} {'正确':>4} {'错误':>4} {'准确率':>8} {'次日均涨跌':>10}")
    logger.info("-" * 50)
    for r in rows:
        c = r["correct"] or 0
        w = r["wrong"] or 0
        accuracy = c / (c + w) * 100 if (c + w) > 0 else 0
        avg_ret = r["avg_next_return"] or 0
        logger.info(f"  {r['prediction']:<8} {r['total']:>4} {c:>4} {w:>4} {accuracy:>7.1f}% {avg_ret:>+9.2f}%")

    # 趋势：近7天 vs 近30天
    logger.info("\n📊 小鲍老师 · 时间窗口准确率")
    logger.info("-" * 50)
    cur.execute("""
        SELECT '近7天' as window,
               COUNT(*) as total,
               SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) as correct,
               SUM(CASE WHEN is_correct = 0 THEN 1 ELSE 0 END) as wrong
        FROM predictor_accuracy
        WHERE predictor_name = '小鲍老师' AND prediction_type = '情绪周期'
          AND date >= date('now', '-7 days') AND is_correct IS NOT NULL
        UNION ALL
        SELECT '近30天', COUNT(*),
               SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END),
               SUM(CASE WHEN is_correct = 0 THEN 1 ELSE 0 END)
        FROM predictor_accuracy
        WHERE predictor_name = '小鲍老师' AND prediction_type = '情绪周期'
          AND date >= date('now', '-30 days') AND is_correct IS NOT NULL
        UNION ALL
        SELECT '全部', COUNT(*),
               SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END),
               SUM(CASE WHEN is_correct = 0 THEN 1 ELSE 0 END)
        FROM predictor_accuracy
        WHERE predictor_name = '小鲍老师' AND prediction_type = '情绪周期'
          AND is_correct IS NOT NULL
    """)
    rows = cur.fetchall()
    for r in rows:
        c = r["correct"] or 0
        w = r["wrong"] or 0
        accuracy = c / (c + w) * 100 if (c + w) > 0 else 0
        total = r["total"] or 0
        logger.info(f"  {r['window']}: {c}/{total} = {accuracy:.1f}%")


if __name__ == "__main__":
    conn = get_connection()
    create_table(conn)
    correct, wrong, unknown = backfill_cycle_comparison(conn)
    backfill_trade_plans(conn)
    generate_summary(conn)
    conn.close()
    logger.info("\n✅ 全部完成！")
