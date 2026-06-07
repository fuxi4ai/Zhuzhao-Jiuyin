#!/usr/bin/env python3
from ..lib.logger import get_logger
logger = get_logger(__name__)
"""
烛照九阴 · 产业信号批量提取脚本
批量处理 raw/4-dims/ 目录下未提取的所有导读和总结文件
"""

import sqlite3
import os
import re
import time
import json

DB_PATH = "/home/admin/openclaw/workspace/projects/烛照九阴/db/recap.db"
RAW_DIR = "/home/admin/openclaw/workspace/projects/烛照九阴/raw/4-dims/"

# ============================================================
# 1. 确定未提取的文件
# ============================================================

def get_existing_dates():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT date FROM industry_signals")
    dates = {r[0] for r in cur.fetchall()}
    conn.close()
    return dates

def parse_file_date(filename):
    m = re.search(r'(\d{6})', filename)
    if not m:
        return None
    ds = m.group(1)
    year = "20" + ds[:2]
    month = ds[2:4]
    day = ds[4:6]
    return f"{year}-{month}-{day}"

def get_unextracted_files(existing_dates):
    files = []
    for f in sorted(os.listdir(RAW_DIR)):
        if not (f.endswith("导读.md") or f.endswith("总结.md")):
            continue
        if f.endswith(".py") or f.endswith(".json"):
            continue
        date = parse_file_date(f)
        if date and date not in existing_dates:
            files.append((date, f))
    return files

# ============================================================
# 2. 信号提取规则引擎
# ============================================================

# 行业关键词映射 (category -> possible keywords in text)
INDUSTRY_PATTERNS = {
    "锂电池": [r"锂电", r"磷酸铁锂", r"VC添加剂", r"电解液", r"六氟磷酸锂", r"正极材料", r"负极材料", r"隔膜"],
    "碳酸锂": [r"碳酸锂"],
    "贵金属": [r"黄金", r"白银", r"沪银", r"现货金", r"贵金属"],
    "光模块": [r"光模块", r"光通信", r"光进铜退", r"CPO", r"NPO", r"OCS"],
    "储能": [r"储能", r"储能电池", r"海博思创"],
    "有机硅": [r"有机硅", r"DMC"],
    "有色金属": [r"铜", r"铝", r"锡", r"锑", r"钨", r"钼", r"有色"],
    "半导体": [r"半导体", r"芯片", r"华虹", r"中芯", r"制程", r"存储芯片", r"功率半导体"],
    "半导体设备": [r"半导体设备", r"北方华创", r"拓荆", r"中微公司"],
    "固态电池": [r"固态电池", r"半固态"],
    "钠电池": [r"钠电池", r"钠电"],
    "原油": [r"原油", r"霍尔木兹", r"油价", r"布伦特", r"WITI"],
    "油运": [r"油运", r"中远海能", r"招商轮船"],
    "煤化工": [r"煤化工", r"华鲁恒升", r"宝丰能源"],
    "光伏": [r"光伏", r"硅片", r"TOPCon", r"HJT", r"钙钛矿"],
    "AI算力": [r"算力", r"阿里云", r"平头哥", r"AI服务器", r"数据中心", r"液冷"],
    "PCB": [r"PCB", r"CCL", r"覆铜板", r"铜箔"],
    "化工": [r"化工", r"硫磺", r"碳酸锶", r"钛白粉", r"MDI"],
    "商业航天": [r"商业航天", r"卫星互联网", r"中国卫星"],
    "情绪周期": [r"情绪周期", r"VX指标", r"连板", r"涨停", r"跌停", r"赚钱效应", r"亏钱效应", r"冰点"],
    "数据中心": [r"数据中心", r"算力中心", r"IDC"],
    "AI应用": [r"MiniMax", r"字节跳动", r"AI应用", r"agent", r"大模型"],
    "电力": [r"电力", r"算电协同", r"火电"],
    "能源": [r"未来能源", r"能源"],
    "光刻胶": [r"光刻胶"],
    "SAF": [r"SAF", r"生物航煤"],
    "钢铁": [r"钢铁"],
}

# 涨价关键词
PRICE_UP_PATTERNS = [r"涨价", r"价格上涨", r"价格上调", r"报价上涨", r"涨停", r"涨幅", r"目标价", r"上调"]

# 逻辑类型分类规则
LOGIC_RULES = {
    "tech_innovation": [r"新技术", r"突破", r"新工艺", r"新.*产品", r"研发", r"量产", r"创新", r"迭代", r"发布.*版本"],
    "supply_shock": [r"供给", r"短缺", r"停产", r"检修", r"断供", r"制裁", r"出口.*下降", r"海峡.*封", r"供应链"],
    "demand_surge": [r"需求", r"采购.*GWh", r"放量", r"订单", r"供不应求", r"产能.*不足"],
    "price_driven": [r"涨价", r"价格.*涨", r"报价.*涨", r"上调.*价", r"涨停", r"涨幅.*超", r"目标价.*上调"],
    "event_driven": [r"政策", r"会议", r"地缘", r"冲突", r"发布.*公告", r"调整.*价", r"发布会", r"限制", r"管制"],
    "emotion_cycle": [r"情绪周期", r"冰点", r"赚钱效应", r"亏钱效应", r"涨停", r"跌停", r"连板", r"VX", r"资金.*流出", r"资金.*流入"],
}

# ============================================================
# 3. 文本信号提取函数
# ============================================================

def extract_signals_from_text(text, file_date):
    """从文本中提取产业信号，返回信号列表"""
    signals = []
    
    # 按段落/章节分析
    # 先提取所有可能的行业信号段落
    sections = re.split(r'[一二三四五六七八九十、]+[、.．]', text)
    
    for section in sections:
        if len(section) < 50:  # 太短的段落跳过
            continue
            
        # 判断是否包含行业信号
        found_industry = None
        found_keyword = None
        for ind, patterns in INDUSTRY_PATTERNS.items():
            for pat in patterns:
                if re.search(pat, section):
                    found_industry = ind
                    found_keyword = ind
                    break
            if found_industry:
                break
        
        if not found_industry:
            continue
        
        # 提取具体数据/事实
        # 提取价格数据
        prices = re.findall(r'[\d.]+[万千万亿]?(?:美元|元|美元/盎司|/吨|/股|/盎司|/芯公里)', section)
        # 提取百分比
        percentages = re.findall(r'[\d.]+%', section)
        # 提取数量
        quantities = re.findall(r'[\d.]+[万千万亿]?[GWh|支|桶|股|家]', section)
        # 提取股票
        stocks = extract_stocks(section)
        
        has_number = bool(prices or percentages or quantities)
        
        # 提取逻辑
        logic = extract_logic(section)
        
        # 提取时间
        time_info = extract_time_info(section, file_date)
        
        # 提取信息差
        info_gap = extract_info_gap(section)
        
        # 提取风险
        risk = extract_risk(section)
        
        # 判断是否应该提取
        # 规则：只提取有具体数字支撑的信号
        # 涨价逻辑必须提取
        has_price_up = any(re.search(p, section) for p in PRICE_UP_PATTERNS)
        is_emotion = ind == "情绪周期"
        
        if not has_number and not has_price_up and not is_emotion:
            continue
            
        # 判断逻辑类型
        logic_type = classify_logic_type(section)
        
        # 信息差评分
        info_gap_level = score_info_gap(section, has_number, has_price_up)
        
        # 构建信号内容
        signal_parts = []
        if logic:
            signal_parts.append(logic)
        if prices:
            signal_parts.append("【数据】" + "；".join(prices[:3]))
        if percentages:
            signal_parts.append("【涨幅】" + "；".join(percentages[:3]))
        if quantities:
            signal_parts.append("【数量】" + "；".join(quantities[:3]))
        if time_info:
            signal_parts.append("【时间】" + time_info)
        if info_gap:
            signal_parts.append("【信息差】" + info_gap)
        if risk:
            signal_parts.append("【风险】" + risk)
            
        if not signal_parts:
            continue
            
        signal_content = "|".join(signal_parts)
        
        # 关键词细化
        keyword_detail = extract_keyword_detail(section, found_keyword)
        
        signals.append({
            "date": file_date,
            "category": found_industry,
            "keyword": keyword_detail,
            "target": ",".join(stocks[:5]) if stocks else "",
            "signal_content": signal_content,
            "logic_type": logic_type,
            "info_gap_level": info_gap_level,
            "confidence": "P2",
            "status": "new",
        })
    
    # 去重（同一日期同一category保留最完整的）
    seen = {}
    for sig in signals:
        key = (sig["date"], sig["category"], sig.get("keyword", ""))
        if key not in seen or len(sig["signal_content"]) > len(seen[key]["signal_content"]):
            seen[key] = sig
    
    return list(seen.values())


def extract_stocks(text):
    """从文本中提取股票名称"""
    # 常见股票名称模式
    stock_patterns = [
        r"([A-Z][A-Za-z\u4e00-\u9fff]{2,6}(?:科技|药业|材料|能源|硅业|锂业|硅材|矿业|智能|通信|电子|光学|电力|网络|软件|系统|创新|控股|集团))",
        r"(宁德时代|比亚迪|阳光电源|海博思创|中际旭创|新易盛|天孚通信|紫金矿业|山东黄金|天齐锂业|赣锋锂业|大中矿业|合盛硅业|东岳硅材|天赐材料|多氟多|天际股份|兴业银锡|德方纳米|北方华创|拓荆科技|中微公司|中芯国际|寒武纪|中国卫星|平潭发展|合富中国|弘光科技|容百科技|华鲁恒升|宝丰能源|中远海能|招商轮船|中信金属|中粮糖业|海辰药业|赛力斯|阿特斯|新宙邦|华盛锂电)",
    ]
    stocks = set()
    for pat in stock_patterns:
        for m in re.finditer(pat, text):
            name = m.group(1)
            if len(name) >= 2:
                stocks.add(name)
    return list(stocks)


def extract_logic(text):
    """提取核心逻辑描述"""
    # 找关键逻辑句子
    sentences = re.split(r'[。；;]', text)
    for s in sentences:
        s = s.strip()
        if len(s) > 15 and len(s) < 100:
            # 包含关键动词的句子
            if re.search(r'[导致|推动|引发|反映|印证|利好|支撑|驱动|催化]', s):
                return s.strip()
    return ""


def extract_time_info(text, file_date):
    """提取时间信息"""
    # 查找具体时间表达
    time_patterns = [
        r'(\d{4}年\d{1,2}月\d{1,2}日)',
        r'(\d{1,2}月\d{1,2}日)',
        r'(本周|下周|上周|近日|当[日月]|近期)',
    ]
    for pat in time_patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1)
    return file_date


def extract_info_gap(text):
    """提取信息差"""
    # 查找"信息差"相关表述
    patterns = [
        r'信息差[：:]*([^\n|。]{5,80})',
        r'核心[是|在][：:]*([^\n|。]{5,80})',
        r'本质[是|在][：:]*([^\n|。]{5,80})',
        r'关键[是|在][：:]*([^\n|。]{5,80})',
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1).strip()[:80]
    return ""


def extract_risk(text):
    """提取风险警示"""
    patterns = [
        r'风险[：:]*([^\n|。]{5,80})',
        r'警惕([^\n|。]{5,80})',
        r'注意([^\n|。]{5,80})',
        r'不确定[性]*[：:]*([^\n|。]{5,80})',
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1).strip()[:80]
    return ""


def classify_logic_type(text):
    """分类逻辑类型"""
    for lt, patterns in LOGIC_RULES.items():
        for pat in patterns:
            if re.search(pat, text):
                return lt
    return "event_driven"  # default


def score_info_gap(text, has_number, has_price_up):
    """信息差评分 1-5"""
    score = 3  # 默认中等
    
    # 有具体数字 → 更明确 → 更低分
    if has_number:
        score -= 1
    
    # 涨价逻辑 → 信息差较小 → 更低分
    if has_price_up:
        score -= 1
    
    # 有具体机构/数据源引用 → 更低分
    if re.search(r'(摩根|高盛|花旗|彭博|路透|Wind|工信部|发改委)', text):
        score -= 1
    
    # 模糊表述 → 更高分
    if re.search(r'(可能|或许|大概率|疑似|传闻|无法验证)', text):
        score += 1
    
    return max(1, min(5, score))


def extract_keyword_detail(text, base_keyword):
    """细化关键词"""
    # 在文本中查找更具体的关键词
    specific_patterns = [
        (r"(HBM|CoWoS|VC|DMC|SAF|CPO|NPO|OCS)", r"\1"),
        (r"(磷酸铁锂|六氟磷酸锂|电解液|正极材料|负极材料|隔膜)", r"\1"),
        (r"(1\.6T|800G|400G)光模块", r"\1光模块"),
        (r"(\d+GWh)电池", r"\1电池"),
        (r"(\d+)纳米", r"\1纳米"),
    ]
    for pat, repl in specific_patterns:
        m = re.search(pat, text)
        if m:
            return base_keyword + "/" + m.group(0)
    return base_keyword


# ============================================================
# 4. 数据库写入
# ============================================================

def insert_signals(conn, signals):
    """写入信号到数据库"""
    cursor = conn.cursor()
    created_at = time.strftime("%Y-%m-%d %H:%M:%S")
    inserted = 0
    skipped = 0
    
    for sig in signals:
        # 检查是否已存在（同一日期同一category）
        cursor.execute(
            "SELECT id FROM industry_signals WHERE date=? AND category=?",
            (sig["date"], sig["category"])
        )
        if cursor.fetchone():
            skipped += 1
            continue
            
        for attempt in range(3):
            try:
                cursor.execute(
                    """INSERT INTO industry_signals
                       (date, category, keyword, target, signal_content, 
                        logic_type, info_gap_level, confidence, status, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        sig["date"],
                        sig["category"],
                        sig["keyword"],
                        sig["target"],
                        sig["signal_content"],
                        sig["logic_type"],
                        sig["info_gap_level"],
                        sig.get("confidence", "P2"),
                        "new",
                        created_at,
                    ),
                )
                inserted += 1
                break
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and attempt < 2:
                    time.sleep(1)
                else:
                    logger.info(f"  ❌ 写入失败: {e}")
                    raise
    
    conn.commit()
    return inserted, skipped


# ============================================================
# 5. 主流程
# ============================================================

def main():
    logger.info("=" * 60)
    logger.info("烛照九阴 · 产业信号批量提取")
    logger.info("=" * 60)
    
    # 1. 获取已有日期
    existing_dates = get_existing_dates()
    logger.info(f"数据库已有 {len(existing_dates)} 个日期")
    
    # 2. 获取未提取文件
    unextracted = get_unextracted_files(existing_dates)
    logger.info(f"未提取文件: {len(unextracted)} 个")
    
    # 3. 统计日期分布
    dates_set = set()
    for d, f in unextracted:
        dates_set.add(d)
    logger.info(f"未提取日期: {len(dates_set)} 个")
    logger.info(f"日期范围: {min(dates_set)} ~ {max(dates_set)}")
    
    # 4. 逐个处理
    total_inserted = 0
    total_skipped = 0
    date_signals = {}  # date -> count
    logic_dist = {}
    
    conn = sqlite3.connect(DB_PATH)
    
    for date, filename in unextracted:
        filepath = os.path.join(RAW_DIR, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            logger.info(f"  ⚠️ 读取失败 {filename}: {e}")
            continue
        
        # 提取信号
        signals = extract_signals_from_text(content, date)
        
        if not signals:
            continue
        
        # 写入数据库
        inserted, skipped = insert_signals(conn, signals)
        total_inserted += inserted
        total_skipped += skipped
        
        if inserted > 0:
            date_signals[date] = inserted
            for sig in signals[:inserted]:  # only count inserted ones
                lt = sig.get("logic_type", "unknown")
                logic_dist[lt] = logic_dist.get(lt, 0) + 1
            
            logger.info(f"  ✅ {date} {filename}: {inserted} 信号")
    
    conn.close()
    
    # 5. 汇总报告
    logger.info("\n" + "=" * 60)
    logger.info("📊 提取汇总")
    logger.info("=" * 60)
    logger.info(f"新增信号: {total_inserted}")
    logger.info(f"跳过重复: {total_skipped}")
    logger.info(f"涉及日期: {len(date_signals)} 个")
    
    if date_signals:
        logger.info("\n日期/信号数:")
        for d in sorted(date_signals.keys()):
            logger.info(f"  {d}: {date_signals[d]} 条")
    
    if logic_dist:
        logger.info("\n逻辑类型分布:")
        for lt, count in sorted(logic_dist.items(), key=lambda x: -x[1]):
            logger.info(f"  {lt}: {count} 条")


if __name__ == "__main__":
    main()
