#!/usr/bin/env python3
"""
Phase A: 全量迁移 — information_gap 推理引擎

哥哥定义的推理逻辑:
Phase 1: 供需评估 → 强度 + 持续性 → demand/supply gap
Phase 2: 时间窗口 → information gap = 发现到市场反应的窗口期

用法:
  python3 migrate_information_gap.py          # 执行迁移（dry-run 预览）
  python3 migrate_information_gap.py --execute # 真正写入数据库
"""

import os
import sys
import re
import json
import sqlite3
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from exec_logger import ExecLogger, init_log_table

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'db', 'recap.db')

# ============================================================
# Phase 1: 供需信号提取与评估
# ============================================================

# 供需关键词库
DEMAND_SURGE_KW = {
    "strong": ["需求爆发", "供不应求", "订单爆满", "产能不足", "需求激增",
               "订单排满", "产能瓶颈", "缺口扩大", "供不应求"],
    "medium": ["需求增长", "需求回暖", "需求上升", "景气度提升", "需求改善",
               "订单增加", "景气向上", "需求向好", "景气度"],
    "weak":   ["需求平稳", "需求温和", "需求小幅", "略有增长"],
}

SUPPLY_SHOCK_KW = {
    "strong": ["供给紧缺", "供给中断", "产能受限", "停产", "断供",
               "限产", "供给不足", "供给收缩", "供给受限"],
    "medium": ["供给偏紧", "供给紧张", "供给减少", "产能利用率下降",
               "供给收缩", "产量下降"],
    "weak":   ["供给平稳", "供给小幅", "供给略降"],
}

SUSTAINABILITY_KW = {
    "long":   ["持续数月", "长期", "中长期", "半年以上", "结构性", "趋势性"],
    "medium": ["持续数周", "中期", "1-3个月", "季度"],
    "short":  ["短期", "临时", "事件性", "脉冲", "一日游", "数天"],
}


def assess_supply_demand(text, date, industry):
    """
    从文本中评估供需信号的强度和持续性
    返回: (demand_surge_level, supply_shock_level, sustainability, gap_direction)
    """
    if not text:
        return None

    demand_strength = 0  # 0=无, 1=weak, 2=medium, 3=strong
    supply_strength = 0
    sustainability = 0   # 0=无, 1=short, 2=medium, 3=long

    # 检测 demand surge
    for level, kws in DEMAND_SURGE_KW.items():
        for kw in kws:
            if kw in text:
                demand_strength = max(demand_strength, {"weak": 1, "medium": 2, "strong": 3}[level])

    # 检测 supply shock
    for level, kws in SUPPLY_SHOCK_KW.items():
        for kw in kws:
            if kw in text:
                supply_strength = max(supply_strength, {"weak": 1, "medium": 2, "strong": 3}[level])

    # 检测持续性
    for level, kws in SUSTAINABILITY_KW.items():
        for kw in kws:
            if kw in text:
                sustainability = max(sustainability, {"short": 1, "medium": 2, "long": 3}[level])

    if demand_strength == 0 and supply_strength == 0:
        return None

    # 推导 gap 方向
    if demand_strength > supply_strength:
        gap_direction = "demand_driven"
    elif supply_strength > demand_strength:
        gap_direction = "supply_driven"
    else:
        gap_direction = "dual_driven"

    # 综合评分 (1-9)
    combined_score = demand_strength * 3 + supply_strength

    return {
        "date": date,
        "industry": industry,
        "demand_strength": demand_strength,
        "supply_strength": supply_strength,
        "sustainability": sustainability,
        "gap_direction": gap_direction,
        "combined_score": combined_score,
        "evidence_text": text[:200],
    }


# ============================================================
# Phase 2: 时间窗口推理
# ============================================================

def infer_time_windows(supply_demand_signals, hot_sectors_data, emotion_data):
    """
    从供需信号和热点板块数据推理信息差窗口

    T1 = 供需信号首次出现（有具体数据支撑）
    T2 = 对应板块首次成为热点
    T3 = 板块热度达峰（连续上涨后首次回调）

    information gap = T1 ~ T2
    realization gap = T2 ~ T3
    """
    gaps = []

    # 按产业分组（清理产业名）
    by_industry = defaultdict(list)
    for sig in supply_demand_signals:
        # 清理产业名：取第一个有意义的关键词
        industry = sig["industry"].strip()
        # 如果太长，截取前 10 字符
        if len(industry) > 10:
            industry = industry[:10]
        by_industry[industry].append(sig)

    for industry, signals in by_industry.items():
        signals.sort(key=lambda x: x["date"])

        # T1: 首个供需信号日期
        t1 = signals[0]["date"]

        # 找 T2: 该产业对应的板块首次成为热点
        t2 = None
        for hs in hot_sectors_data:
            # 简单匹配：热点板块名包含产业关键词
            if any(kw in hs.get("sector_name", "") for kw in industry_keywords(industry)):
                if hs["date"] >= t1:
                    t2 = hs["date"]
                    break

        # 找 T3: 板块热度达峰（简化：连续 3 天热点后的日期）
        t3 = None
        if t2:
            hot_days = sum(1 for hs in hot_sectors_data
                          if hs["date"] >= t2 and
                          any(kw in hs.get("sector_name", "") for kw in industry_keywords(industry)))
            if hot_days >= 3:
                # 粗略估计 T3 = T2 + 3 个交易日
                t3 = add_trading_days(t2, 5)

        # 构建 gap 记录
        gap_info = {
            "industry": industry,
            "t1_discovered": t1,
            "t2_realized": t2,
            "t3_closed": t3,
            "information_gap_days": days_between(t1, t2) if t2 else None,
            "realization_gap_days": days_between(t2, t3) if t2 and t3 else None,
            "gap_status": "closed" if t3 else ("closing" if t2 else "open"),
            "best_signal": signals[0],
        }
        gaps.append(gap_info)

    return gaps


def industry_keywords(industry):
    """将产业名映射到板块关键词"""
    mapping = {
        "光模块": ["光模块", "CPO", "光通信"],
        "PCB": ["PCB", "覆铜板", "CCL"],
        "半导体": ["半导体", "芯片", "IC"],
        "存储": ["存储", "HBM", "DRAM", "NAND"],
        "锂": ["锂", "锂电池", "碳酸锂"],
        "光伏": ["光伏", "太阳能"],
        "AI": ["AI", "人工智能", "算力"],
    }
    return mapping.get(industry, [industry])


def days_between(d1, d2):
    if not d1 or not d2:
        return None
    try:
        dt1 = datetime.strptime(d1, "%Y-%m-%d")
        dt2 = datetime.strptime(d2, "%Y-%m-%d")
        return (dt2 - dt1).days
    except (ValueError, TypeError):
        return None


def add_trading_days(date_str, n):
    """粗略增加 n 个交易日"""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        # 简单估计：每个交易日 +1 天，跳过周末
        days_added = 0
        while days_added < n:
            dt += timedelta(days=1)
            if dt.weekday() < 5:  # 周一~周五
                days_added += 1
        return dt.strftime("%Y-%m-%d")
    except (OverflowError, ValueError):
        return None


# ============================================================
# 主流程
# ============================================================
def run_migration(dry_run=True):
    conn = sqlite3.connect(DB_PATH)
    init_log_table(conn)
    conn.row_factory = sqlite3.Row

    cur = conn.cursor()

    # 1. 从 dim2_sector_themes 提取供需信号
    cur.execute("SELECT date, sector_logic, supply_demand, price_chain, main_line FROM dim2_sector_themes")
    dim2_rows = cur.fetchall()

    # 2. 从 hot_sectors 提取热点板块
    cur.execute("SELECT date, sector_name, rank FROM hot_sectors ORDER BY date")
    hot_sectors_rows = [dict(r) for r in cur.fetchall()]

    # 3. 从 emotion_cycle 提取情绪数据
    cur.execute("SELECT date, emotion_season FROM emotion_cycle ORDER BY date")
    emotion_rows = [dict(r) for r in cur.fetchall()]

    logger.info(f"📊 数据源: dim2={len(dim2_rows)} 条, hot_sectors={len(hot_sectors_rows)} 条, emotion={len(emotion_rows)} 条")

    # Phase 1: 评估每条 dim2 记录的供需信号
    # 已知板块词库（从 industry_signals 和 hot_sectors 中提取）
    KNOWN_SECTORS = [
        "光模块", "PCB", "半导体", "存储芯片", "锂电池", "光伏", "AI算力",
        "机器人", "商业航天", "稀土", "有色金属", "储能", "固态电池",
        "液冷", "电网设备", "化工", "煤炭", "贵金属", "钨", "锂矿",
        "消费电子", "AI芯片", "光纤", "光通信", "医药", "房地产",
        "电力", "核电", "风电", "新能源车", "智能驾驶", "油气",
        "银行", "保险", "证券", "钢铁", "铝", "铜", "碳酸锂",
    ]

    def extract_industry(text):
        """从文本中提取最可能的行业名"""
        if not text:
            return "未知"
        for sector in KNOWN_SECTORS:
            if sector in text:
                return sector
        # 如果没匹配到已知板块，尝试提取
        m = re.search(r'([\u4e00-\u9fa5]{2,6}(?:板块|产业|产业链|行业))', text)
        if m:
            return m.group(1)
        return "其他"

    signals = []
    for row in dim2_rows:
        text = (row["sector_logic"] or "") + (row["supply_demand"] or "") + (row["price_chain"] or "")
        industry = extract_industry(text)

        result = assess_supply_demand(text, row["date"], industry)
        if result:
            signals.append(result)

    logger.info(f"✅ Phase 1: 识别到 {len(signals)} 条供需信号")

    # 打印信号分布
    by_strength = defaultdict(int)
    for s in signals:
        by_strength[(s["demand_strength"], s["supply_strength"])] += 1
    logger.info("  强度分布 (demand, supply):")
    for k, v in sorted(by_strength.items()):
        logger.info(f"    demand={k[0]}, supply={k[1]}: {v} 条")

    # Phase 2: 推理时间窗口
    gaps = infer_time_windows(signals, hot_sectors_rows, emotion_rows)

    logger.info(f"\n✅ Phase 2: 推理到 {len(gaps)} 个信息差窗口")

    # 打印 gap 示例
    for g in sorted(gaps, key=lambda x: x["information_gap_days"] or 999)[:10]:
        bs = g["best_signal"]
        info_days = g["information_gap_days"]
        print(f"  {g['industry']}: T1={g['t1_discovered']}, T2={g['t2_realized']}, "
              f"info_gap={info_days}天, status={g['gap_status']}")

    # 如果非 dry-run，写入数据库
    if not dry_run:
        with ExecLogger("migrate_information_gap", "batch_migrate", conn=conn) as elog:
            inserted = 0
            for g in gaps:
                bs = g["best_signal"]
                cur.execute("""
                    INSERT OR IGNORE INTO information_gap
                    (signal_id, date_discovered, date_realized, sector_hot_days, gap_status, action)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    None,  # signal_id — 后续关联
                    g["t1_discovered"],
                    g["t2_realized"],
                    g["information_gap_days"] or 0,
                    g["gap_status"],
                    "买入" if g["gap_status"] == "open" else ("持有" if g["gap_status"] == "closing" else "观望"),
                ))
                inserted += 1

            conn.commit()
            elog.update(rows_affected=inserted)
            logger.info(f"\n✅ 写入 {inserted} 条 information_gap 记录")
    else:
        logger.info("\n[dry-run] 未写入数据库，加 --execute 执行写入")

    conn.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="执行写入（默认 dry-run）")
    args = parser.parse_args()

    run_migration(dry_run=not args.execute)
