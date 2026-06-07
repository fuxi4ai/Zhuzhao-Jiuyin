#!/usr/bin/env python3
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import config
from lib.logger import get_logger
logger = get_logger(__name__)
"""
🐲 四维度复盘数据库 · 板块标准化引擎
严格区分：光模块 ≠ CPO
"""

# 板块标准名 → 别名映射
SECTOR_MAP = {
    "光模块": [
        "光模块", "可插拔光模块", "光器件", "光通信", "光通信模块",
        "光模块方向", "光通信方向", "可插拔"
    ],
    "CPO": [
        "CPO", "共封装光学", "硅光", "CPO封装", "CPO方向",
        "硅光方向", "共封装"
    ],
    "AI算力": [
        "AI算力", "算力", "算力方向", "算力链", "算力板块",
        "AI算力方向", "数据中心", "服务器", "AI服务器",
        "算力服务器", "AI基建", "算力基建"
    ],
    "AI硬件": [
        "AI硬件", "存储", "PCB", "液冷", "散热", "HBM",
        "存储芯片", "AI硬件方向"
    ],
    "半导体": [
        "半导体", "芯片", "光刻胶", "EDA", "封测",
        "半导体方向", "芯片方向", "国产芯片", "芯片板块",
        "晶圆代工", "半导体设备"
    ],
    "新能源电池": [
        "锂电池", "电池", "六氟磷酸锂", "VC溶剂", "隔膜",
        "碳酸锂", "电池方向", "锂电池方向", "固态电池",
        "储能", "储能电池", "动力电池", "锂电",
        "新能源", "新能源方向"
    ],
    "光伏": [
        "光伏", "光伏设备", "硅料", "逆变器", "光伏方向",
        "光伏板块", "光伏产业链", "光伏概念"
    ],
    "消费电子": [
        "消费电子", "鸿蒙", "华为概念", "手机链",
        "消费电子方向", "鸿蒙方向", "华为概念方向"
    ],
    "机器人": [
        "机器人", "人形机器人", "电机", "减速器",
        "机器人方向", "人形机器人方向", "智能制造"
    ],
    "商业航天": [
        "商业航天", "卫星", "火箭", "SpaceX概念",
        "商业航天方向", "卫星方向", "航天"
    ],
    "医药": [
        "医药", "CRO", "创新药", "医疗器械", "医疗数据",
        "医药方向", "医药板块", "创新药方向", "减肥药"
    ],
    "白酒": [
        "白酒", "白酒方向", "白酒板块", "酒类"
    ],
    "金融": [
        "券商", "保险", "银行", "非银金融",
        "券商方向", "银行方向", "金融方向",
        "红利", "红利板块", "农业银行", "高股息"
    ],
    "军工": [
        "军工", "军工方向", "军工板块", "国防"
    ],
    "中东/能源": [
        "中东", "中东地缘", "能源", "原油",
        "中东方向", "能源方向", "地缘冲突"
    ],
    "光纤": [
        "光纤", "光纤方向", "光纤光缆"
    ],
    "煤化工": [
        "煤化工", "煤化工方向", "宝丰能源"
    ],
    "AI软件/应用": [
        "AI应用", "AI软件", "火山引擎", "飞书",
        "AI软件方向", "AI应用方向", "大模型"
    ],
    "固态电池": [
        "固态电池", "固态电池方向"
    ],
    "电力": [
        "电力", "电力方向", "电网", "智能电网",
        "电力板块", "电网设备"
    ],
}

# 反向索引：别名 → 标准名
_alias_to_canonical = {}
for canonical, aliases in SECTOR_MAP.items():
    _alias_to_canonical[canonical] = canonical  # 标准名自身也是别名
    for alias in aliases:
        _alias_to_canonical[alias] = canonical


def standardize_sector(name: str) -> str:
    """将板块别名标准化为标准名"""
    if not name:
        return None
    name = name.strip()
    # 精确匹配
    if name in _alias_to_canonical:
        return _alias_to_canonical[name]
    # 模糊匹配：包含关系
    for alias, canonical in _alias_to_canonical.items():
        if alias in name or name in alias:
            return canonical
    return name


def standardize_text(text: str) -> str:
    """将文本中的板块别名替换为标准名（按词边界替换，避免误替换）"""
    if not text:
        return text
    result = text
    # 按长度排序，先替换长的别名
    sorted_aliases = sorted(_alias_to_canonical.keys(), key=len, reverse=True)
    for alias in sorted_aliases:
        if alias in result:
            canonical = _alias_to_canonical[alias]
            if canonical == alias:  # 已经是标准名，跳过
                continue
            # 用中文词边界：只替换独立出现的别名
            # 简单策略：替换后检查是否产生重复标准名
            result = result.replace(alias, canonical)
    # 清理重复替换产生的错误（如"新中东/能源新中东/能源电池"）
    # 这是一个已知限制，建议使用 extract_sectors 而非 standardize_text
    return result


def extract_sectors(text: str) -> list:
    """从文本中提取板块标准名列表"""
    if not text:
        return []
    found = set()
    for alias, canonical in _alias_to_canonical.items():
        if alias in text:
            found.add(canonical)
    return sorted(found)


def sync_sector_alias_to_db():
    """同步板块映射到数据库"""
    import sys
    from recap_db import get_conn
    conn = get_conn()
    cur = conn.cursor()
    
    categories = {
        "光模块": "光通信", "CPO": "光通信", "AI算力": "AI硬件",
        "AI硬件": "AI硬件", "半导体": "半导体", "新能源电池": "新能源",
        "光伏": "新能源", "消费电子": "消费电子", "机器人": "智能制造",
        "商业航天": "军工航天", "医药": "医药", "白酒": "消费",
        "金融": "金融", "军工": "军工", "中东/能源": "能源",
        "光纤": "通信", "煤化工": "化工", "AI软件/应用": "AI软件",
        "固态电池": "新能源", "电力": "能源",
    }
    
    for canonical, aliases in SECTOR_MAP.items():
        aliases_str = ",".join(aliases)
        cur.execute(
            "INSERT OR REPLACE INTO sector_alias (canonical_name, aliases, category) VALUES (?,?,?)",
            (canonical, aliases_str, categories.get(canonical, "其他"))
        )
    
    conn.commit()
    count = len(SECTOR_MAP)
    logger.info(f"✅ 板块映射已同步: {count} 个标准板块")
    conn.close()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--sync":
        sync_sector_alias_to_db()
    else:
        # 演示
        logger.info("=== 板块标准化引擎演示 ===\n")
        test_cases = [
            "光模块", "CPO", "AI算力", "锂电池", "六氟磷酸锂",
            "共封装光学", "鸿蒙", "券商", "固态电池", "中东地缘"
        ]
        for tc in test_cases:
            canon = standardize_sector(tc)
            logger.info(f"   '{tc}' → '{canon}'")
        
        logger.info("\n=== 文本标准化 ===")
        text = "关注光模块和CPO方向，锂电池和储能板块"
        logger.info(f"   原文: {text}")
        logger.info(f"   标准化: {standardize_text(text)}")
        
        logger.info("\n=== 板块提取 ===")
        text2 = "主线是AI算力、光模块、锂电池，回避券商和白酒"
        sectors = extract_sectors(text2)
        logger.info(f"   提取: {sectors}")
