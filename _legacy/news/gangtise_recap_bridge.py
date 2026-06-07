#!/usr/bin/env python3
from ..lib.logger import get_logger
logger = get_logger(__name__)
"""
gangtise_recap_bridge.py - 冈底斯投研 → recap 数据库对接 v2
==========================================================
重点：
1. KB 语义知识库（核心）→ 提取关键数据/供需/趋势
2. 会议纪要（重要）→ 提取专家观点
3. 研报（低优先级）→ 只存标题+摘要，CC 在提炼

KB 提取规则：
- 数字提取：产能、产量、需求、占比、价格
- 趋势判断：增/降/紧缺/过剩/爆发
- 供需关系：供不应求/产能不足/供过于求
"""

import json
import re
import sqlite3
import requests
import sys
from datetime import datetime

GANGTISE_BRIDGE = "http://localhost:8766/invoke"
RECAP_DB = "/home/admin/openclaw/workspace/projects/烛照九阴/db/recap.db"

# ============================================================
# 查询关键词（按哥哥指定的 4 个范围）
# ============================================================

KB_QUERIES = {
    "AI硬件": [
        "CoWoS产能利用率", "HBM供需缺口", "800G光模块需求",
        "AI芯片 先进封装", "GPU 散热 电源",
    ],
    "半导体设备": [
        "光刻机 产能", "刻蚀设备 订单", "半导体 扩产",
    ],
    "大宗商品": [
        "碳酸锂供需平衡", "原油供给中断", "OPEC 减产",
        "能源进口", "大宗商品涨价",
    ],
    "地缘政治": [
        "美伊停火进展", "霍尔木兹海峡", "中美贸易",
        "美联储 利率",
    ],
}

SUMMARY_KEYWORDS = [
    "CoWoS 产能", "HBM 需求", "光模块", "碳酸锂",
    "原油 供给", "美伊", "霍尔木兹", "半导体设备",
]

REPORT_KEYWORDS = [
    "AI硬件", "半导体设备", "光模块", "HBM", "CoWoS",
    "刻蚀设备", "AI芯片", "碳酸锂",
]

# gts_summary 会议纪要 P1 判断关键词
P1_KEYWORDS = ["帕米尔", "专家", "路演", "调研"]

# ============================================================
# KB 智能提取
# ============================================================

def extract_kb_insights(content, title=""):
    """
    从 KB 内容中提取关键洞察。
    返回: (data_points, trend, supply_demand)
    """
    data_points = []
    trend_signals = []
    supply_demand = ""

    # 1. 提取数字信息（产能/产量/需求/占比/价格）
    number_patterns = [
        r'(\d+[.\d]*)\s*[万千亿]%?',  # 数字 + 单位
        r'(\d+[.\d]*)\s*[片颗万吨]',   # 数字 + 量词
    ]

    # 2. 提取关键趋势词
    trend_keywords = {
        "供不应求": ["紧缺", "不足", "供不应求", "缺口", "紧张"],
        "产能扩张": ["扩产", "扩建", "新增产能", "投产", "放量"],
        "需求增长": ["需求增长", "需求旺盛", "高景气", "爆发", "快速增长"],
        "供过于求": ["过剩", "供过于求", "价格下行", "下跌"],
    }

    content_lower = content.lower()

    for trend, keywords in trend_keywords.items():
        for kw in keywords:
            if kw in content_lower or kw in content:
                trend_signals.append(trend)
                break

    # 3. 提取供需判断
    if any(kw in content for kw in ["产能紧缺", "供不应求", "供给中断", "供给不足", "紧缺"]):
        supply_demand = "供不应求"
    elif any(kw in content for kw in ["过剩", "供过于求", "价格下行"]):
        supply_demand = "供过于求"
    elif any(kw in content for kw in ["供需平衡", "基本平衡"]):
        supply_demand = "供需平衡"

    # 4. 提取关键数据行（包含数字的短句）
    sentences = re.split(r'[。；\n]', content)
    for s in sentences[:10]:  # 前10句
        if re.search(r'\d', s) and len(s) > 10:
            # 清理 markdown 符号
            clean = re.sub(r'[|`\[\]#*]', '', s).strip()
            if len(clean) > 15:
                data_points.append(clean[:100])

    return {
        "data_points": data_points[:5],
        "trend": list(set(trend_signals)),
        "supply_demand": supply_demand,
    }


def format_kb_insight(item):
    """格式化 KB 洞察为结构化条目"""
    title = item.get("title", "")
    content = item.get("content", "")
    pub = item.get("time", "")
    if pub and isinstance(pub, (int, float)) and pub > 1000000:
        pub = datetime.fromtimestamp(pub / 1000).strftime("%Y-%m-%d")

    insights = extract_kb_insights(content, title)

    parts = []
    parts.append(f"[KB-P2] {title} ({pub})")

    # 趋势信号
    if insights["trend"]:
        parts.append(f"  趋势: {', '.join(insights['trend'])}")

    # 供需判断
    if insights["supply_demand"]:
        parts.append(f"  供需: {insights['supply_demand']}")

    # 关键数据
    if insights["data_points"]:
        parts.append("  数据: " + " | ".join(insights["data_points"][:3]))

    return "\n".join(parts)


def format_summary_insight(item):
    """格式化会议纪要"""
    title = item.get("title", "")
    confidence = "P1" if is_p1(title) else "P2"
    pub = item.get("publishTime", "")
    if isinstance(pub, str) and len(pub) > 10:
        pub = pub[:10]

    brief = item.get("brief", "")[:150]

    parts = [f"[纪要-{confidence}] {title} ({pub})"]
    if brief:
        parts.append(f"  摘要: {brief}")
    return "\n".join(parts)


def format_report_brief(item):
    """研报只存标题+摘要（CC 在提炼，优先级低）"""
    title = item.get("title", "")
    brief = item.get("brief", "")[:100]
    pub = item.get("publishTime", "")
    if isinstance(pub, str) and len(pub) > 10:
        pub = pub[:10]
    if isinstance(pub, (int, float)) and pub > 1000000:
        pub = datetime.fromtimestamp(pub / 1000).strftime("%Y-%m-%d")

    parts = [f"[研报-P2] {title} ({pub})"]
    if brief:
        parts.append(f"  摘要: {brief}")
    return "\n".join(parts)


# ============================================================
# API 调用
# ============================================================

def gts_call(tool, args={}):
    try:
        r = requests.post(GANGTISE_BRIDGE, json={"tool": tool, "args": args}, timeout=60)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.info(f"⚠️ Gangtise API 调用失败 ({tool}): {e}")
        return None


def gts_kb(query, start_date=None, end_date=None, limit=3):
    return gts_call("gts_kb", {
        "query": query, "start_date": start_date, "end_date": end_date, "limit": limit
    })


def gts_summary(keyword, start_date=None, end_date=None, size=5):
    return gts_call("gts_summary", {
        "keyword": keyword, "start_date": start_date, "end_date": end_date, "size": size
    })


def gts_report(keyword, start_date=None, end_date=None, size=3):
    return gts_call("gts_report", {
        "keyword": keyword, "start_date": start_date, "end_date": end_date, "size": size
    })


def parse_timestamp(ts):
    if not ts:
        return ""
    try:
        if isinstance(ts, str):
            return ts[:10]
        return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")
    except (OSError, ValueError, TypeError):
        return ""


def is_p1(title):
    if not title:
        return False
    return any(kw in title for kw in P1_KEYWORDS)


# ============================================================
# 数据库操作
# ============================================================

def get_or_create_recap_date(date, table):
    conn = sqlite3.connect(RECAP_DB)
    existing = conn.execute(f"SELECT id FROM {table} WHERE date = ?", (date,)).fetchone()
    if existing:
        conn.close()
        return existing[0]
    conn.execute(f"INSERT INTO {table} (date) VALUES (?)", (date,))
    row_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return row_id


def set_json_field(table, column, row_id, items):
    if not items:
        return
    conn = sqlite3.connect(RECAP_DB)
    conn.execute(f"UPDATE {table} SET {column} = ? WHERE id = ?",
                 (json.dumps(items, ensure_ascii=False), row_id))
    conn.commit()
    conn.close()


# ============================================================
# 主流程
# ============================================================

def run(date=None, dry_run=False):
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    from datetime import timedelta
    end_date = date
    start_date = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")

    logger.info("=" * 60)
    logger.info(f"gangtise_recap_bridge v2 - 冈底斯投研 → recap")
    logger.info(f"目标日期: {date}")
    logger.info(f"查询范围: {start_date} ~ {end_date}")
    logger.info(f"模式: {'Dry Run' if dry_run else '写入'}")
    logger.info("=" * 60)

    # 1. KB 语义知识库（核心重点）
    logger.info("\n📡 查询 gts_kb (语义知识库 - 核心)...")
    kb_results = []
    kb_by_date = {}

    for category, queries in KB_QUERIES.items():
        for q in queries[:3]:  # 每类取前 3 个
            logger.info(f"  查询: {category} - {q}")
            d = gts_kb(q, start_date, end_date, limit=2)
            if d and d.get("data"):
                items = d["data"]
                if isinstance(items, list):
                    for item in items[:2]:
                        item["_category"] = category
                        insight = format_kb_insight(item)
                        kb_results.append(insight)

                        # 按日期分组
                        pub = parse_timestamp(item.get("time"))
                        if pub:
                            kb_by_date.setdefault(pub, []).append(insight)
                        logger.info(f"    ✓ {item.get('title', '')[:50]}...")

    logger.info(f"  KB 合计: {len(kb_results)} 条")

    # 2. 会议纪要（重要）
    logger.info("\n📡 查询 gts_summary (会议纪要)...")
    summary_results = []
    summary_by_date = {}

    for kw in SUMMARY_KEYWORDS[:5]:
        logger.info(f"  查询: {kw}")
        d = gts_summary(kw, start_date, end_date, size=3)
        if d and d.get("data"):
            data = d["data"]
            items = data.get("list", []) or data.get("data", [])
            if isinstance(items, list):
                for item in items[:3]:
                    item["_keyword"] = kw
                    insight = format_summary_insight(item)
                    summary_results.append(insight)

                    pub = parse_timestamp(item.get("publishTime"))
                    if pub:
                        summary_by_date.setdefault(pub, []).append(insight)
                    logger.info(f"    ✓ {item.get('title', '')[:50]}...")

    logger.info(f"  纪要合计: {len(summary_results)} 条")

    # 3. 研报（低优先级，只存标题+摘要）
    logger.info("\n📡 查询 gts_report (研报 - 低优先)...")
    report_results = []
    report_by_date = {}

    for kw in REPORT_KEYWORDS[:8]:  # AI硬件/半导体设备优先
        logger.info(f"  查询: {kw}")
        d = gts_report(kw, start_date, end_date, size=2)
        if d and d.get("data"):
            data = d["data"]
            items = data.get("list", []) or data.get("data", [])
            if isinstance(items, list):
                for item in items[:2]:
                    insight = format_report_brief(item)
                    report_results.append(insight)

                    pub = parse_timestamp(item.get("publishTime"))
                    if pub:
                        report_by_date.setdefault(pub, []).append(insight)
                    logger.info(f"    ✓ {item.get('title', '')[:50]}...")

    logger.info(f"  研报合计: {len(report_results)} 条")

    # 4. 按日期写入 recap
    logger.info(f"\n📝 按日期写入 recap...")
    all_dates = sorted(set(
        list(kb_by_date.keys()) + list(summary_by_date.keys()) + list(report_by_date.keys())
    ), reverse=True)

    for d in all_dates:
        kb_items = kb_by_date.get(d, [])
        summary_items = summary_by_date.get(d, [])
        report_items = report_by_date.get(d, [])

        # Dim2
        dim2_items = kb_items + summary_items + report_items
        kb_price = [i for i in kb_items if "趋势" in i or "供需" in i]

        # Dim3
        dim3_items = kb_items + summary_items + report_items
        kb_supply = [i for i in kb_items if "供需" in i]
        kb_trend = [i for i in kb_items if "趋势" in i]

        if not dry_run:
            row2 = get_or_create_recap_date(d, "dim2_sector_themes")
            row3 = get_or_create_recap_date(d, "dim3_sentiment_tech")

            set_json_field("dim2_sector_themes", "sector_logic", row2, dim2_items)
            set_json_field("dim2_sector_themes", "price_catalyst", row2, kb_price)
            set_json_field("dim3_sentiment_tech", "industry_logic", row3, dim3_items)
            set_json_field("dim3_sentiment_tech", "supply_demand_info", row3, kb_supply)
            set_json_field("dim3_sentiment_tech", "price_driver", row3, kb_trend)

        logger.info(f"  {d}: KB {len(kb_items)} | 纪要 {len(summary_items)} | 研报 {len(report_items)}")

    logger.info(f"\n{'=' * 60}")
    logger.info("✅ 完成！" if not dry_run else "🔍 Dry Run 结束")
    logger.info(f"{'=' * 60}")


if __name__ == "__main__":
    date_arg = None
    dry_run = False

    for arg in sys.argv[1:]:
        if arg == "--dry-run":
            dry_run = True
        elif arg.startswith("--date="):
            date_arg = arg.split("=")[1]

    run(date=date_arg, dry_run=dry_run)
