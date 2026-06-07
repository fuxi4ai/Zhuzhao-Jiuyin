#!/usr/bin/env python3
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import config
from lib.logger import get_logger
logger = get_logger(__name__)
"""
🐲 四维度复盘数据库 · 个股提取器
从复盘原文中提取具体个股名称
"""
import re
from typing import List, Tuple

# A股常见个股名称模式
STOCK_PATTERNS = [
    # 四字名称（最常见）
    r'([一-鿿]{4})(?:股份|科技|集团|药业|能源|电子|通信|材料|环境|汽车)',
    # 三字名称
    r'([一-鿿]{3})(?:股份|科技|集团|药业|能源|电子)',
    # 已知核心个股列表（从课件中提取的高频标的）
]

# 高频核心个股库（从课件提取）
CORE_STOCKS = {
    # 光模块/CPO
    "中际旭创": "光模块", "新易盛": "光模块", "天孚通信": "光模块",
    "光迅科技": "光模块", "华工科技": "光模块", "博创科技": "光模块",
    "太辰光": "光模块", "剑桥科技": "光模块", "中际": "光模块",
    "源杰科技": "光模块", "仕佳光子": "光模块",
    # 半导体
    "海光信息": "半导体", "寒武纪": "半导体", "中芯国际": "半导体",
    "北方华创": "半导体", "中微公司": "半导体", "华天科技": "半导体",
    "长电科技": "半导体",
    # 新能源电池
    "多氟多": "新能源电池", "天际股份": "新能源电池",
    "宁德时代": "新能源电池", "比亚迪": "新能源电池",
    "天赐材料": "新能源电池", "恩捷股份": "新能源电池",
    "星源材质": "新能源电池", "三花智控": "新能源电池",
    # 光伏
    "阿特斯": "光伏", "隆基绿能": "光伏", "通威股份": "光伏",
    "阳光电源": "光伏", "晶澳科技": "光伏", "迈为股份": "光伏设备",
    "捷佳伟创": "光伏设备", "拉普拉斯": "光伏设备",
    # 消费电子/鸿蒙
    "常山北明": "消费电子", "欧菲光": "消费电子",
    "东山精密": "消费电子", "方正科技": "消费电子",
    # AI算力/服务器
    "工业富联": "AI算力", "浪潮信息": "AI算力",
    "中科曙光": "AI算力", "紫光股份": "AI算力",
    # 金融/红利
    "农业银行": "金融", "中国银行": "金融", "中国人寿": "金融",
    # 医药
    "众生药业": "医药", "特一药业": "医药", "恒瑞医药": "医药",
    "药明康德": "医药",
    # 机器人
    "汇川技术": "机器人", "绿的谐波": "机器人", "鸣志电器": "机器人",
    # 商业航天
    "中国卫星": "商业航天", "航天电子": "商业航天",
    # 其他
    "梦百合": "其他", "沧州明珠": "其他", "厦门港务": "其他",
    "隆扬电子": "其他", "元杰科技": "其他",
}

# 过滤词（避免误提取）
FILTER_WORDS = ["市场", "板块", "行业", "概念", "方向", "板块方向", "板块概念",
                "资金", "机构", "游资", "散户", "外资", "政策", "技术"]


def extract_stocks(text: str) -> List[Tuple[str, str]]:
    """从文本中提取个股 (名称, 所属板块)"""
    if not text:
        return []
    
    found = []
    
    # 1. 精确匹配核心个股库
    for stock, sector in CORE_STOCKS.items():
        if stock in text:
            found.append((stock, sector))
    
    # 2. 正则提取四字名称（带后缀）
    pattern1 = r'([A-Za-z\u4e00-\u9fa5]{2,6})(?:股份|科技|集团|药业|能源|电子|通信|材料)'
    for m in re.finditer(pattern1, text):
        name = m.group(0)
        # 过滤已匹配的和无效词
        if any(name[0] in s for s in found) or any(w in name for w in FILTER_WORDS):
            continue
        if len(name) >= 3:
            found.append((name, "其他"))
    
    # 去重（处理简称与全称的重复）
    seen = set()
    unique = []
    # 按名称长度降序排列，优先保留全称
    for stock, sector in sorted(found, key=lambda x: len(x[0]), reverse=True):
        # 检查是否是已保留名称的子串（简称）
        is_sub = False
        for s in seen:
            if stock in s or s in stock:
                is_sub = True
                break
        if not is_sub and stock not in seen:
            seen.add(stock)
            unique.append((stock, sector))
    
    return unique


def sync_stocks_to_db():
    """同步个股库到数据库"""
    import sys
    from recap_db import get_conn
    conn = get_conn()
    cur = conn.cursor()
    
    for stock, sector in CORE_STOCKS.items():
        # 提取别名（简称）
        alias = stock[:2] if len(stock) >= 4 else stock
        cur.execute(
            "INSERT OR REPLACE INTO stock_master (code, name, aliases, sector) VALUES (?,?,?,?)",
            ("", stock, alias, sector)
        )
    
    conn.commit()
    count = len(CORE_STOCKS)
    logger.info(f"✅ 个股库已同步: {count} 只")
    conn.close()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--sync":
        sync_stocks_to_db()
    else:
        # 演示
        logger.info("=== 个股提取器演示 ===\n")
        samples = [
            "关注中际旭创、新易盛、天孚通信，回避海光信息",
            "锂电池方向：宁德时代、多氟多、天际股份、天赐材料",
            "光伏：隆基绿能、通威股份、阿特斯大涨",
            "鸿蒙概念常山北明涨停，欧菲光跟进",
            "红利板块农业银行、中国人寿持续走强",
        ]
        for s in samples:
            stocks = extract_stocks(s)
            logger.info(f"原文: {s}")
            logger.info(f"提取: {stocks}\n")
