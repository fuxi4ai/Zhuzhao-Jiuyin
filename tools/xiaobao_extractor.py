#!/usr/bin/env python3
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import config
from lib.logger import get_logger
logger = get_logger(__name__)
"""
小鲍复盘课件提取器 v1.0
=========================
功能：从小鲍复盘课件中提取市场数据 + 产业逻辑
方案：规则提取（市场数据） + LLM 提取（产业逻辑）

可复用设计：
- 所有提取字段参数化
- Prompt 模板可配置
- 输出格式标准化（JSON → 数据库）

用法：
  python3 xiaobao_extractor.py --file 课件路径.md
  python3 xiaobao_extractor.py --dir 课件目录/
  python3 xiaobao_extractor.py --dry-run --file 课件路径.md
"""

import json
import re
import sqlite3
import argparse
import os
import sys
from datetime import datetime

# ============================================================
# 参数化配置（可调整）
# ============================================================

# 1. 市场数据提取规则（正则表达式）
MARKET_RULES = {
    "指数": {
        "pattern": r'\|\s*(上证|创业板|科创|北证)\s*\|\s*([\d,.]+)\s*\|\s*([+-]?[\d.]+)%?',
        "fields": ["name", "close", "change_pct"]
    },
    "总成交额": {
        "pattern": r'\*\*总成交额[：:]\*\*\s*([\d,]+)\s*亿',
        "fields": ["total_volume"]
    },
    "涨跌分布": {
        "pattern": r'\*\*涨跌分布[：:]\*\*\s*(\d+)\s*比\s*(\d+)',
        "fields": ["up_count", "down_count"]
    },
    "涨跌停": {
        "pattern": r'\*\*涨跌停分布[：:]\*\*\s*(\d+)/(\d+)',
        "fields": ["limit_up", "limit_down"]
    },
    "封板率": {
        "pattern": r'\*\*封板率[：:]\*\*\s*([\d.]+)%',
        "fields": ["seal_rate"]
    },
    "赚钱效应": {
        "pattern": r'\*\*赚钱效应[：:]\*\*\s*(.*)',
        "fields": ["money_effect"]
    },
    "连板标的": {
        "pattern": r'\*\*连板标的[：:]\*\*\s*(.*)',
        "fields": ["continuous_board"]
    },
    "炸板率": {
        "pattern": r'\*\*炸板率[：:]\*\*\s*(.*)',
        "fields": ["broken_rate"]
    },
}

# 2. 板块热度提取规则（匹配到下一个板块标题或文件末尾）
SECTOR_PATTERN = r'###\s*🔥\s*([^+]+)\+([+-]?[\d.]+)%\s*(.*?)(?=###\s*🔥|$)'

# 3. LLM 提取配置
LLM_CONFIG = {
    # 提取字段（可调整）
    "extract_fields": {
        "industry_logic": "产业逻辑（技术迭代/供需变化/产能/价格趋势）",
        "catalyst": "催化原因（事件/业绩/政策）",
        "capital_signal": "资金信号（流入/流出/观望）",
        "targets": "关注标的（股票名称列表）",
        "technical": "技术位（突破/支撑/压力）"
    },
    
    # 过滤规则（泛泛描述不提取）
    "skip_patterns": [
        "走势震荡", "观望为主", "短期调整", "等待方向",
        "横盘整理", "缩量", "无量", "弱势"
    ],
    
    # Prompt 模板
    "prompt_template": """你是产业逻辑提取专家。从以下复盘片段中提取产业逻辑信息。

提取字段：
{field_descriptions}

要求：
1. 只提取有具体产业逻辑的条目（技术迭代/供需变化/产能/价格趋势）
2. 过滤"走势震荡"、"观望为主"等泛泛描述
3. 输出纯 JSON，格式：{{"industry_logic": "...", "catalyst": "...", "capital_signal": "...", "targets": ["..."], "technical": "..."}}

输入：
{sector_content}

输出：
"""
}

# 4. 数据库配置
DB_CONFIG = {
    "path": config.RECAP_DB,
    "tables": {
        "emotion_cycle": "emotion_cycle",
        "hot_sectors": "hot_sectors",
        "industry_signals": "industry_signals",
        "daily_summary": "daily_summary"
    }
}

# ============================================================
# 规则提取（市场数据）
# ============================================================

def extract_market_data(text):
    """用正则提取市场数据"""
    result = {}
    
    for rule_name, rule in MARKET_RULES.items():
        match = re.search(rule["pattern"], text)
        if match:
            groups = match.groups()
            for i, field in enumerate(rule["fields"]):
                value = groups[i]
                # 数值转换
                if field in ("close", "change_pct", "total_volume", "seal_rate"):
                    try:
                        value = float(value.replace(",", ""))
                    except (ValueError, AttributeError):
                        logger.debug(f"数值转换失败: {field}={value}")
                elif field in ("up_count", "down_count", "limit_up", "limit_down"):
                    try:
                        value = int(value)
                    except (ValueError, TypeError):
                        logger.debug(f"整数转换失败: {field}={value}")
                result[field] = value
    
    return result


def extract_sector_blocks(text):
    """提取板块热度块（名称+涨幅+内容）"""
    blocks = []
    
    # 使用 DOTALL 模式匹配多行内容
    matches = list(re.finditer(SECTOR_PATTERN, text, re.DOTALL))
    
    for match in matches:
        sector_name = match.group(1).strip()
        sector_change = match.group(2).strip()
        content = match.group(3).strip()
        
        # 过滤空内容
        if content and len(content) > 10:
            blocks.append({
                "name": sector_name,
                "change_pct": float(sector_change),
                "content": content
            })
    
    return blocks


# ============================================================
# LLM 提取（产业逻辑）
# ============================================================

def extract_industry_logic_with_llm(sectors, api_call_fn=None):
    """
    用 LLM 提取产业逻辑
    api_call_fn: 外部传入的 API 调用函数，默认使用百炼 API
    """
    if api_call_fn is None:
        api_call_fn = call_bailian_api
    
    results = []
    
    for sector in sectors:
        content = sector["content"]
        
        # 检查是否需要跳过
        skip = False
        for pattern in LLM_CONFIG["skip_patterns"]:
            if pattern in content and len(content) < 50:
                skip = True
                break
        if skip:
            results.append({**sector, "llm_extracted": None})
            continue
        
        # 构建 Prompt
        field_descriptions = "\n".join(
            f"- {k}: {v}" for k, v in LLM_CONFIG["extract_fields"].items()
        )
        
        prompt = LLM_CONFIG["prompt_template"].format(
            field_descriptions=field_descriptions,
            sector_content=content[:500]  # 限制输入长度
        )
        
        # 调用 LLM
        try:
            response = api_call_fn(prompt)
            extracted = parse_llm_response(response)
            results.append({**sector, "llm_extracted": extracted})
        except Exception as e:
            logger.info(f"  ⚠️ LLM 提取失败 ({sector['name']}): {e}")
            results.append({**sector, "llm_extracted": None})
    
    return results


def call_bailian_api(prompt):
    """调用百炼 API（通过本地 LiteLLM 代理）"""
    import requests
    
    url = "http://localhost:8899/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    
    payload = {
        "model": "openrouter/bailian/qwen3.6-plus",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 1000
    }
    
    response = requests.post(url, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    
    data = response.json()
    return data["choices"][0]["message"]["content"]


def parse_llm_response(response):
    """解析 LLM 返回的 JSON"""
    # 清理可能的 markdown 代码块
    response = response.strip()
    if response.startswith("```"):
        response = re.sub(r'^```.*?\n', '', response)
        response = re.sub(r'\n```$', '', response)
    
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        # 尝试提取 JSON 部分
        match = re.search(r'\{.*\}', response, re.DOTALL)
        if match:
            return json.loads(match.group())
        return None


# ============================================================
# 数据库写入
# ============================================================

def write_to_db(date, market_data, sectors_with_logic, dry_run=False):
    """写入数据库"""
    db_path = DB_CONFIG["path"]
    if not os.path.isabs(db_path):
        workspace = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        db_path = os.path.join(workspace, db_path)
    
    conn = sqlite3.connect(db_path)
    
    # 1. 写入情绪周期
    if market_data:
        up_down_ratio = 0
        if market_data.get("down_count", 0) > 0:
            up_down_ratio = market_data.get("up_count", 0) / market_data["down_count"]
        
        conn.execute("""
            INSERT OR REPLACE INTO emotion_cycle 
            (date, limit_up, limit_down, seal_rate, total_volume, up_down_ratio, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        """, (
            date,
            market_data.get("limit_up", 0),
            market_data.get("limit_down", 0),
            market_data.get("seal_rate", 0),
            market_data.get("total_volume", 0),
            up_down_ratio,
        ))
        if not dry_run:
            logger.info(f"  ✅ emotion_cycle 已更新 {date}")
    
    # 2. 写入热点板块
    for i, sector in enumerate(sectors_with_logic[:5]):  # 只存 Top 5
        conn.execute("""
            INSERT OR REPLACE INTO hot_sectors 
            (date, rank, sector_name, pct_change, created_at)
            VALUES (?, ?, ?, ?, datetime('now'))
        """, (date, i + 1, sector["name"], sector["change_pct"]))
    
    if not dry_run:
        logger.info(f"  ✅ hot_sectors 已更新 {date} ({len(sectors_with_logic[:5])} 条)")
    
    # 3. 写入产业信号
    for sector in sectors_with_logic:
        llm = sector.get("llm_extracted")
        if not llm:
            continue
        
        industry_logic = llm.get("industry_logic", "")
        if not industry_logic or len(industry_logic) < 5:
            continue
        
        conn.execute("""
            INSERT INTO industry_signals 
            (date, category, keyword, signal_content, confidence, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            date,
            "产业逻辑",
            sector["name"],
            industry_logic,
            "P2",
            "new"
        ))
    
    if not dry_run:
        conn.commit()
        logger.info(f"  ✅ industry_signals 已更新 {date}")
    
    conn.close()


# ============================================================
# 主流程
# ============================================================

def extract_from_file(file_path, dry_run=False):
    """从单个课件文件提取"""
    logger.info(f"📄 提取: {file_path}")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        text = f.read()
    
    # 从文件名提取日期
    basename = os.path.basename(file_path)
    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', basename)
    date = date_match.group(1) if date_match else datetime.now().strftime("%Y-%m-%d")
    
    # 1. 规则提取市场数据
    logger.info("  📊 规则提取市场数据...")
    market_data = extract_market_data(text)
    logger.info(f"    提取到 {len(market_data)} 个字段")
    
    # 2. 提取板块热度块
    logger.info("  🔥 提取板块热度...")
    sector_blocks = extract_sector_blocks(text)
    logger.info(f"    提取到 {len(sector_blocks)} 个板块")
    
    # 3. LLM 提取产业逻辑
    logger.info("  🤖 LLM 提取产业逻辑...")
    sectors_with_logic = extract_industry_logic_with_llm(sector_blocks)
    extracted_count = sum(1 for s in sectors_with_logic if s.get("llm_extracted"))
    logger.info(f"    成功提取 {extracted_count}/{len(sector_blocks)} 个板块的产业逻辑")
    
    # 4. 写入数据库
    logger.info("  💾 写入数据库...")
    write_to_db(date, market_data, sectors_with_logic, dry_run)
    
    return {
        "date": date,
        "market_data": market_data,
        "sectors": sectors_with_logic
    }


def process_directory(dir_path, dry_run=False):
    """批量处理课件目录"""
    results = []
    
    # 按日期排序
    files = sorted([
        os.path.join(dir_path, f) 
        for f in os.listdir(dir_path) 
        if f.endswith('.md')
    ])
    
    for file_path in files:
        result = extract_from_file(file_path, dry_run)
        results.append(result)
    
    return results


def main():
    parser = argparse.ArgumentParser(description="小鲍复盘课件提取器")
    parser.add_argument("--file", help="单个课件文件路径")
    parser.add_argument("--dir", help="课件目录路径")
    parser.add_argument("--dry-run", action="store_true", help="预览不写入")
    
    args = parser.parse_args()
    
    if args.file:
        extract_from_file(args.file, args.dry_run)
    elif args.dir:
        process_directory(args.dir, args.dry_run)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
