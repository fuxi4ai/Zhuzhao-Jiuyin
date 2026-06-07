#!/usr/bin/env python3
from ..lib.logger import get_logger
logger = get_logger(__name__)
"""
烛照九阴 - 产业信号提取引擎 批次5
从5个四维度训练营文件中提取产业信号，写入SQLite数据库
"""

import sqlite3
import time
import os

DB_PATH = "/home/admin/openclaw/workspace/projects/烛照九阴/db/recap.db"

# 确保目录存在
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

signals = [
    # === 2025-11-10 导读 ===
    {
        "date": "2025-11-10",
        "category": "锂电",
        "keyword": "涨价驱动/碳酸锂",
        "target": "天齐锂业,赣锋锂业,宁德时代,德方纳米",
        "signal_content": "碳酸锂价格大涨近7%，带动锂电产业链上游走强。锂电涨价逻辑持续强化，上游材料涨幅显著。|【数据】碳酸锂单日涨幅近7%|【时间】2025-11-10|【信息差】上游锂矿股未同步上涨，或存在融券做空|【风险】宁德为涨价最终承担方，短期利润承压",
        "confidence": "P0",
        "status": "new",
    },
    {
        "date": "2025-11-10",
        "category": "锂电",
        "keyword": "涨价驱动/电解液添加剂",
        "target": "华盛锂电",
        "signal_content": "电解液添加剂VC涨价，华盛锂电受催化持续上涨，昨日信息催化后未跌。VC在铁锂电池中添加比例高于三元锂。|【数据】VC价格上涨，华盛锂电持续强势|【时间】2025-11-10|【信息差】铁锂电池VC添加比例更高|【风险】需观察后续持续性",
        "confidence": "P0",
        "status": "new",
    },
    {
        "date": "2025-11-10",
        "category": "光伏",
        "keyword": "涨价驱动/硅片",
        "target": "TCL中环,弘元绿能",
        "signal_content": "光伏炒作从硅料向硅片蔓延，TCL中环（光伏硅片市占率全球第一）大涨，后续预计传导至电池片（尤其N型TOPCon）。|【数据】TCL中环大涨，硅片环节领涨|【时间】2025-11-10|【信息差】硅料收紧信息若出台，硅片价格将跟进上涨|【风险】光伏是强预期非强事实，涨价待落地",
        "confidence": "P1",
        "status": "new",
    },
    {
        "date": "2025-11-10",
        "category": "贵金属",
        "keyword": "事件催化/央行储备",
        "target": "山东黄金",
        "signal_content": "美国参议院60:40通过结束停摆协议后黄金反常上涨，核心逻辑为各国央行竞争性储备黄金——停摆期间央行购金暂停，解决后黄金军备竞赛重启。|【数据】美国参议院60票对40票通过协议|【时间】2025-11-10|【信息差】停摆解决后黄金上涨（反常）|【风险】央行购金力度不确定性",
        "confidence": "P1",
        "status": "new",
    },
    {
        "date": "2025-11-10",
        "category": "消费",
        "keyword": "需求爆发/免税",
        "target": "中国中免",
        "signal_content": "海南离岛免税1-7号同比增长30%，环比加速，消费复苏逻辑驱动。|【数据】海南离岛免税1-7号同比+30%|【时间】2025-11-10|【信息差】环比加速|【风险】消费复苏持续性待验证",
        "confidence": "P1",
        "status": "new",
    },
    {
        "date": "2025-11-10",
        "category": "煤炭",
        "keyword": "供给紧缺/动力煤",
        "target": "中煤能源",
        "signal_content": "动力煤价格有上涨迹象，进口减少、北方九港库存同比下降、电厂库存下降，中电联预测消费增速与火电发电量增加，供需缺口支撑价格。|【数据】北方九港库存同比下降|【时间】2025-11-10|【信息差】进口减少+下游库存双降|【风险】政策调控可能干预价格",
        "confidence": "P1",
        "status": "new",
    },
    {
        "date": "2025-11-10",
        "category": "半导体",
        "keyword": "需求爆发/代工",
        "target": "",
        "signal_content": "台积电10月营收增长16%创历史新高（7月增速25%），增速放缓系基数效应，持续增长为常态。|【数据】台积电10月营收同比+16%，总量历史新高|【时间】2025-11-10|【信息差】增速新低是基数效应，非增长乏力|【风险】全球半导体需求周期",
        "confidence": "P1",
        "status": "new",
    },
    # === 2025-11-10 总结 ===
    {
        "date": "2025-11-10",
        "category": "有机硅",
        "keyword": "涨价驱动/有机硅",
        "target": "合盛硅业,东岳集团",
        "signal_content": "有机硅板块核心标的为合成硅液和东岳股份，盘面验证前两者为细分龙头，兴发集团、新安股份被剔除。|【数据】东岳股份盘面验证为细分龙头|【时间】2025-11-10|【信息差】仅前两者有持续活性|【风险】有机硅产能扩张可能压制价格",
        "confidence": "P2",
        "status": "new",
    },
    {
        "date": "2025-11-10",
        "category": "磷化工",
        "keyword": "涨价驱动/磷化工",
        "target": "芭田股份,云天化,云图控股,澄星股份,川恒股份",
        "signal_content": "磷化工分两条线：化肥线保留芭田股份、云天化、云图控股、史丹利；上游原材料聚焦澄星股份、川恒股份。|【数据】标的池精简后聚焦龙头|【时间】2025-11-10|【信息差】化肥线仅前两者有持续活性|【风险】化肥价格受政策调控影响",
        "confidence": "P2",
        "status": "new",
    },
    {
        "date": "2025-11-10",
        "category": "燃气轮机",
        "keyword": "供给紧缺/数据中心电力",
        "target": "联德股份,万泽股份",
        "signal_content": "燃气轮机板块核心标的联德股份、万泽股份，仅前两者符合燃气轮机核心逻辑（数据中心缺电题材发电端）。|【数据】标的精简后仅保留两家核心|【时间】2025-11-10|【信息差】日韩股市持续上涨→数据中心缺电逻辑→燃气轮机|【风险】海外需求变化",
        "confidence": "P1",
        "status": "new",
    },
    {
        "date": "2025-11-10",
        "category": "SOFC",
        "keyword": "技术升级/燃料电池",
        "target": "潍柴动力,振华股份",
        "signal_content": "SOFC固体氧化物燃料电池板块核心标的潍柴动力、振华股份，其余活性不足。属于电力产业链发电端分支。|【数据】潍柴动力、振华股份为核心|【时间】2025-11-10|【信息差】需跟踪能否成为主线|【风险】产业化进度不确定",
        "confidence": "P2",
        "status": "new",
    },
    {
        "date": "2025-11-10",
        "category": "光伏",
        "keyword": "涨价驱动/硅料",
        "target": "通威股份,大全能源,特变电工",
        "signal_content": "光伏硅料环节（通威、大全、特变）横盘震荡，但硅料收紧信息若出台将推动硅片价格上涨。硅料是产业链最源头。|【数据】硅料环节横盘，等待催化|【时间】2025-11-10|【信息差】硅料→硅片→电池片传导链条|【风险】光伏行业过剩严重",
        "confidence": "P1",
        "status": "new",
    },
    # === 2025-11-11 导读 ===
    {
        "date": "2025-11-11",
        "category": "光模块",
        "keyword": "供给紧缺/光器件",
        "target": "源杰科技,仕佳光子,天孚通信",
        "signal_content": "1.6T光模块进入量产前验证阶段，头部厂商大规模备货导致关键元器件供应瓶颈，上游零部件厂商受益。|【数据】源杰科技、仕佳光子盘面强势，天孚通信曾涨10%+|【时间】2025-11-11|【信息差】关键元器件供应瓶颈|【风险】科技硬件整体情绪低迷",
        "confidence": "P1",
        "status": "new",
    },
    {
        "date": "2025-11-11",
        "category": "固态电池",
        "keyword": "技术升级/固态电池",
        "target": "",
        "signal_content": "固态电池中期审查将于11月启动，预计12月初出结果，后续进入装车测试与中试线招标阶段。|【数据】11月启动审查，12月初出结果|【时间】2025-11-11|【信息差】核心供应商包括川衡、国瓷材料、上海十八等|【风险】能否炒作仍不确定",
        "confidence": "P2",
        "status": "new",
    },
    {
        "date": "2025-11-11",
        "category": "光伏",
        "keyword": "技术升级/钙钛矿",
        "target": "",
        "signal_content": "半导体所研制出光电转换率27%的钙钛矿太阳能电池（2025年11月7日发布），双面发电特性，目前处于实验室向生产线验证阶段。|【数据】光电转换率27%|【时间】2025-11-07发布|【信息差】钙钛矿可在玻璃正反面贴合实现双倍发电|【风险】尚未规模化应用",
        "confidence": "P2",
        "status": "new",
    },
    {
        "date": "2025-11-11",
        "category": "光伏",
        "keyword": "技术升级/BC电池",
        "target": "爱旭股份,帝尔激光",
        "signal_content": "BC电池渗透率约5%，通过将导电组件移至背面显著提升光电转化效率，核心改造设备来自帝尔激光（激光打孔），生产端核心为爱旭股份（ABC电池技术）。|【数据】BC电池渗透率约5%|【时间】2025-11-11|【信息差】BC是二代电池升级版|【风险】渗透率低，市场空间待验证",
        "confidence": "P1",
        "status": "new",
    },
    {
        "date": "2025-11-11",
        "category": "硅片",
        "keyword": "涨价驱动/硅片龙头",
        "target": "弘元绿能",
        "signal_content": "弘元绿能Q3单季利润5亿、营收24亿，为硅片环节龙头，当前总市值247亿，有望带动其他硅片标的跟风。|【数据】Q3单季利润5亿、营收24亿|【时间】2025-11-11|【信息差】硅片环节业绩最强势标的|【风险】光伏行业整体过剩",
        "confidence": "P1",
        "status": "new",
    },
    # === 2025-11-11 总结 ===
    {
        "date": "2025-11-11",
        "category": "储能",
        "keyword": "需求爆发/储能电池",
        "target": "阳光电源,海博思创,宁德时代",
        "signal_content": "储能系统紧缺带动全产业链上涨，储能电池以磷酸铁锂为主（含宁德专用储能电池），大量走货推动供需结构变化。|【数据】储能需求拉动全产业链|【时间】2025-11-11|【信息差】老登方向精简为电力和储能|【风险】交割期临近市场波动",
        "confidence": "P0",
        "status": "new",
    },
    {
        "date": "2025-11-11",
        "category": "锂电",
        "keyword": "涨价驱动/电池材料",
        "target": "华盛锂电",
        "signal_content": "电解液添加剂VC在铁锂电池中添加比例高于三元锂，受储能需求拉动价格上涨；磷酸铁、六氟磷酸锂涨幅显著，为电池领域涨势最猛的两类材料。|【数据】VC、磷酸铁、六氟磷酸锂涨幅显著|【时间】2025-11-11|【信息差】储能需求→磷酸铁锂需求→材料涨价传导链|【风险】价格过高可能抑制需求",
        "confidence": "P0",
        "status": "new",
    },
    {
        "date": "2025-11-11",
        "category": "特种金属",
        "keyword": "涨价驱动/钨铬",
        "target": "振华股份",
        "signal_content": "黑钨矿均价涨至31.3万吨（此前记录27万多），钨矿持续上涨；金属铬、铬盐、氧化铬等品种涨价，振华股份表现稳健。|【数据】黑钨矿均价31.3万吨（此前27万多）|【时间】2025-11-11|【信息差】钨矿+铬系双涨价|【风险】大宗商品价格波动",
        "confidence": "P1",
        "status": "new",
    },
    {
        "date": "2025-11-11",
        "category": "宏观",
        "keyword": "事件催化/交割期",
        "target": "",
        "signal_content": "11月金融衍生品集中交割：中金所11月21日、上交所11月26日、富时A50 11月27日，三个日期密集相邻，11月11-20日为炒作窗口期，下旬波动率上升。|【数据】三个交割日仅隔2个交易日|【时间】2025-11-21/26/27|【信息差】大胖手严格控制节奏，为明年KPI预留空间|【风险】交割期市场波动率急剧上升",
        "confidence": "P1",
        "status": "new",
    },
    # === 2025-11-12 导读 ===
    {
        "date": "2025-11-12",
        "category": "锂电",
        "keyword": "涨价驱动/VC添加剂",
        "target": "华盛锂电",
        "signal_content": "VC添加剂报价异常高涨，可能由招商电信发布。锂电池产业链持续增长，储能电池快速发展带动涨价。|【数据】VC添加剂报价异常高涨|【时间】2025-11-12|【信息差】储能电池需求持续拉动涨价|【风险】报价来源待核实",
        "confidence": "P0",
        "status": "new",
    },
    {
        "date": "2025-11-12",
        "category": "科技硬件",
        "keyword": "供给紧缺/反内卷政策",
        "target": "",
        "signal_content": "工信部提出控制低技术水平产能扩张，防止科技硬件重蹈光伏覆辙。政策利好现有产能公司，新公司扩张难度加大。|【数据】工信部政策限制低技术水平产能|【时间】2025-11-12|【信息差】利好现有产能公司|【风险】外围需求下降",
        "confidence": "P1",
        "status": "new",
    },
    {
        "date": "2025-11-12",
        "category": "光伏",
        "keyword": "供给紧缺/收储托底",
        "target": "阿特斯",
        "signal_content": "光伏行业面临严重过剩，阿特斯太阳能股价大跌，硅片企业降价。政策定位为托底而非速效，价格由供需决定。市场对收储平台存在担忧。|【数据】阿特斯大跌，硅片企业降价|【时间】2025-11-12|【信息差】政策托底而非速效，供需决定价格|【风险】行业严重过剩，风声鹤唳",
        "confidence": "P0",
        "status": "new",
    },
    {
        "date": "2025-11-12",
        "category": "商业航天",
        "keyword": "事件催化/商业航天",
        "target": "中国卫星",
        "signal_content": "商业航天板块异动，核心标的为中国卫星等四只股票。|【数据】四只商业航天核心标的异动|【时间】2025-11-12|【信息差】板块整体异动|【风险】题材持续性待验证",
        "confidence": "P2",
        "status": "new",
    },
]

def insert_signals(db_path, signals):
    """写入信号到SQLite，带重试机制"""
    retries = 3
    for attempt in range(retries):
        try:
            conn = sqlite3.connect(db_path, timeout=10)
            cursor = conn.cursor()

            # 建表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS industry_signals (
                    id INTEGER PRIMARY KEY,
                    date TEXT NOT NULL,
                    category TEXT NOT NULL,
                    keyword TEXT,
                    target TEXT,
                    signal_content TEXT,
                    confidence TEXT DEFAULT 'P2',
                    status TEXT DEFAULT 'new',
                    created_at TEXT
                )
            """)

            # 获取当前最大id
            cursor.execute("SELECT COALESCE(MAX(id), 0) FROM industry_signals")
            max_id = cursor.fetchone()[0]

            # 插入信号
            now = "2025-11-12 21:31:00"
            for i, sig in enumerate(signals):
                row_id = max_id + i + 1
                cursor.execute("""
                    INSERT INTO industry_signals (id, date, category, keyword, target, signal_content, confidence, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    row_id,
                    sig["date"],
                    sig["category"],
                    sig["keyword"],
                    sig["target"],
                    sig["signal_content"],
                    sig["confidence"],
                    sig["status"],
                    now,
                ))

            conn.commit()
            conn.close()
            return len(signals)
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() and attempt < retries - 1:
                time.sleep(1)
                continue
            raise

# 执行
count = insert_signals(DB_PATH, signals)
logger.info(f"✅ 批次5完成：5文件 {count}信号")

# 验证
conn = sqlite3.connect(DB_PATH, timeout=10)
cursor = conn.cursor()
cursor.execute("SELECT id, date, category, keyword, confidence FROM industry_signals ORDER BY id DESC LIMIT 10")
rows = cursor.fetchall()
logger.info("\n最近10条信号：")
for r in rows:
    logger.info(f"  id={r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]}")
cursor.execute("SELECT COUNT(*) FROM industry_signals")
total = cursor.fetchone()[0]
logger.info(f"\n数据库总信号数: {total}")
conn.close()
