#!/usr/bin/env python3
from ..lib.logger import get_logger
logger = get_logger(__name__)
"""
烛照九阴 - 四维度纪要 LLM 批量提取 + 入库
每批5篇，串行执行，跑完即入库，全部完成后汇总
"""

import sqlite3
import json
import os
import re
import glob
import time

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "db", "recap.db")
RAW_DIR = os.path.dirname(__file__)
BATCH_SIZE = 5

PROMPT_TEMPLATE = """你是烛照九阴项目的产业信号提取引擎。请仔细阅读以下 {n} 篇小鲍老师四维度训练营总结文件，从中提取所有有价值的产业逻辑与行业信号。

## 提取目标
我们要找的是"产业逻辑：买入"起点——即小鲍老师发现但市场尚未充分认知的产业信息差。

## 提取原则
1. 宁缺毋滥：只提取有具体数字支撑的信号，不要泛泛而谈
2. 硬数据优先：有产能/良率/价格/涨幅数字的信号优先
3. 涨价逻辑重点：任何涨价信息必须提取
4. 供需关系：供给端和需求端分开记录
5. 情绪周期信号：涨跌停数量、情绪阶段判断单独提取
6. 忽略噪音：纯操作技巧（AB法、止损止盈）、纯交易纪律不提取

## 输出格式
严格按以下 JSON 格式输出（只输出 JSON，不要其他内容）：

[
  {{
    "source_file": "文件名",
    "date": "YYYY-MM-DD",
    "signals": [
      {{
        "sector": "行业/板块名称",
        "sub_sector": "细分领域",
        "driver_type": "技术升级|供给紧缺|需求爆发|涨价驱动|事件催化",
        "logic": "一句话概括核心产业逻辑",
        "hard_data": [{{"metric": "指标", "value": "数值", "unit": "单位"}}],
        "key_stocks": ["标的1", "标的2"],
        "timeline": "时间线描述",
        "risk": "风险提示",
        "info_gap": "信息差判断",
        "confidence": "P0|P1|P2|P3"
      }}
    ]
  }}
]

## 文件内容

{files_content}
"""


def get_files():
    """获取所有总结文件，按日期排序"""
    pattern = os.path.join(RAW_DIR, "*总结*.md")
    files = sorted(glob.glob(pattern))
    return files


def read_file(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def parse_date_from_filename(filename):
    """从文件名提取日期，如 251019 → 2025-10-19"""
    basename = os.path.basename(filename)
    # 匹配 251019 或 260506 等6位数字
    m = re.match(r'(\d{6})', basename)
    if m:
        d = m.group(1)
        yy = int(d[:2])
        year = 2000 + yy if yy < 50 else 1900 + yy
        month = int(d[2:4])
        day = int(d[4:6])
        return f"{year:04d}-{month:02d}-{day:02d}"
    return "unknown"


def extract_with_llm(batch_files, batch_idx):
    """调用 LLM 提取（通过 subprocess 调用 openai 兼容 API）"""
    import subprocess
    
    contents = []
    for f in batch_files:
        content = read_file(f)
        # 截断过长文件（保留前8000字符）
        if len(content) > 8000:
            content = content[:8000] + "\n...(已截断)..."
        fname = os.path.basename(f)
        contents.append(f"### 文件: {fname}\n\n{content}")
    
    files_content = "\n\n---\n\n".join(contents)
    prompt = PROMPT_TEMPLATE.format(n=len(batch_files), files_content=files_content)
    
    # 读取百炼 API key
    workspace = os.path.expanduser('~/openclaw/workspace')
    vault_path = os.path.join(workspace, 'credentials', 'api_keys.json')
    api_key = None
    base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    
    if os.path.exists(vault_path):
        with open(vault_path) as f:
            keys = json.load(f)
        entries = keys.get('entries', {})
        bailian = entries.get('bailian', {})
        api_key = bailian.get('api_key')
        bu = bailian.get('base_url', '')
        if bu:
            if bu.startswith('http'):
                base_url = bu.rstrip('/') + '/chat/completions'
            else:
                base_url = 'https://' + bu.rstrip('/') + '/chat/completions'
    
    if not api_key:
        logger.info(f"  ⚠️ 无法读取 API key，跳过批次 {batch_idx}")
        return None
    
    payload = {
        "model": "qwen-plus",
        "messages": [
            {"role": "system", "content": "你是一个产业信号提取引擎，只输出 JSON，不要输出其他内容。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 8000
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    try:
        result = subprocess.run(
            ["curl", "-s", "-X", "POST", api_url,
             "-H", f"Authorization: Bearer {api_key}",
             "-H", "Content-Type: application/json",
             "-d", json.dumps(payload)],
            capture_output=True, text=True, timeout=120
        )
        
        if result.returncode != 0:
            logger.info(f"  ❌ curl 失败: {result.stderr[:200]}")
            return None
        
        response = json.loads(result.stdout)
        
        if 'choices' not in response or not response['choices']:
            logger.info(f"  ❌ API 无返回: {result.stdout[:500]}")
            return None
        
        text = response['choices'][0]['message']['content']
        
        # 提取 JSON
        # 尝试直接解析
        try:
            data = json.loads(text)
        except:
            # 尝试从 markdown 代码块中提取
            m = re.search(r'```(?:json)?\s*\n([\s\S]*?)\n```', text)
            if m:
                data = json.loads(m.group(1))
            else:
                # 尝试找到第一个 [ 和最后一个 ]
                start = text.find('[')
                end = text.rfind(']')
                if start != -1 and end != -1:
                    data = json.loads(text[start:end+1])
                else:
                    logger.info(f"  ❌ 无法解析 JSON: {text[:500]}")
                    return None
        
        # 统一格式
        if isinstance(data, dict) and 'results' in data:
            data = data['results']
        if not isinstance(data, list):
            data = [data]
        
        return data
        
    except subprocess.TimeoutExpired:
        logger.info(f"  ⏱️ 超时，跳过批次 {batch_idx}")
        return None
    except Exception as e:
        logger.info(f"  ❌ 异常: {e}")
        return None


def insert_to_db(extracted_data):
    """写入数据库"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    total_signals = 0
    total_files = 0
    
    for file_result in extracted_data:
        source_file = file_result.get('source_file', '')
        date = file_result.get('date', '')
        signals = file_result.get('signals', [])
        
        if not signals:
            continue
        
        total_files += 1
        
        for sig in signals:
            sector = sig.get('sector', '')
            sub_sector = sig.get('sub_sector', '')
            driver_type = sig.get('driver_type', '')
            logic = sig.get('logic', '')
            hard_data = sig.get('hard_data', [])
            key_stocks = sig.get('key_stocks', [])
            timeline = sig.get('timeline', '')
            risk = sig.get('risk', '')
            info_gap = sig.get('info_gap', '')
            confidence = sig.get('confidence', 'P2')
            
            # 构建 signal_content
            content_parts = [logic]
            if hard_data:
                data_str = "; ".join([f"{d['metric']}={d['value']}{d['unit']}" for d in hard_data])
                content_parts.append(f"【数据】{data_str}")
            if timeline:
                content_parts.append(f"【时间】{timeline}")
            if info_gap:
                content_parts.append(f"【信息差】{info_gap}")
            if risk:
                content_parts.append(f"【风险】{risk}")
            signal_content = " | ".join(content_parts)
            
            # keyword = driver_type + sub_sector
            keyword = f"{driver_type}"
            if sub_sector:
                keyword += f"/{sub_sector}"
            
            # target = 股票列表
            target = ",".join(key_stocks) if key_stocks else ""
            
            cursor.execute("""
                INSERT INTO industry_signals (date, category, keyword, target, signal_content, confidence, status)
                VALUES (?, ?, ?, ?, ?, ?, 'new')
            """, (date, sector, keyword, target, signal_content, confidence))
            total_signals += 1
    
    conn.commit()
    conn.close()
    return total_files, total_signals


def main():
    files = get_files()
    logger.info(f"共 {len(files)} 个文件，每批 {BATCH_SIZE} 篇，共 {(len(files) + BATCH_SIZE - 1) // BATCH_SIZE} 批")
    
    # 分批
    batches = [files[i:i+BATCH_SIZE] for i in range(0, len(files), BATCH_SIZE)]
    
    grand_total_files = 0
    grand_total_signals = 0
    batch_results = []
    
    for idx, batch in enumerate(batches):
        batch_start = time.time()
        batch_names = [os.path.basename(f) for f in batch]
        
        logger.info(f"\n[{idx+1}/{len(batches)}] 提取: {', '.join(batch_names[:2])}...({len(batch)}篇)")
        
        # LLM 提取
        extracted = extract_with_llm(batch, idx+1)
        
        if extracted:
            # 写入数据库
            n_files, n_signals = insert_to_db(extracted)
            elapsed = time.time() - batch_start
            logger.info(f"  ✅ 入库 {n_files} 文件, {n_signals} 信号 ({elapsed:.1f}s)")
            grand_total_files += n_files
            grand_total_signals += n_signals
            batch_results.append({"batch": idx+1, "files": n_files, "signals": n_signals})
        else:
            logger.info(f"  ❌ 提取失败")
            batch_results.append({"batch": idx+1, "files": 0, "signals": 0})
        
        # 小停顿，避免 API 限流
        if idx < len(batches) - 1:
            time.sleep(1)
    
    # 最终汇总
    logger.info(f"\n{'='*60}")
    logger.info(f"📊 批量提取完成")
    logger.info(f"{'='*60}")
    logger.info(f"总批次数: {len(batches)}")
    logger.info(f"成功批次: {sum(1 for b in batch_results if b['signals'] > 0)}")
    logger.info(f"总文件数: {grand_total_files}")
    logger.info(f"总信号数: {grand_total_signals}")
    logger.info(f"{'='*60}")
    
    # 验证数据库
    conn = sqlite3.connect(DB_PATH)
    total = conn.execute("SELECT count(*) FROM industry_signals").fetchone()[0]
    logger.info(f"数据库 industry_signals 总记录数: {total}")
    
    # 按置信度统计
    for conf in ['P0', 'P1', 'P2', 'P3']:
        count = conn.execute("SELECT count(*) FROM industry_signals WHERE confidence=?", (conf,)).fetchone()[0]
        logger.info(f"  {conf}: {count}")
    conn.close()


if __name__ == "__main__":
    main()
