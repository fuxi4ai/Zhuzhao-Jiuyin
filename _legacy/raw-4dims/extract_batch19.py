#!/usr/bin/env python3
from ..lib.logger import get_logger
logger = get_logger(__name__)
"""批次19: 四维度训练营产业信号提取 (251230-260105)"""

import sqlite3
import time
import os

DB_PATH = "/home/admin/openclaw/workspace/projects/烛照九阴/db/recap.db"

# Ensure db directory exists
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

signals = [
    # ===== 251230 =====
    {
        "date": "2025-12-30",
        "category": "化工/石油",
        "keyword": "事件催化/中东地缘",
        "target": "资源类,化工类",
        "signal_content": "中东地缘冲突升级:也门全国紧急90天,红海航运危机→石油供应紧张+化工品涨价|【数据】也门取消与阿联酋联合防务协议,空袭运兵船|【时间】2025-12-30|【信息差】冲突区域为石油主产区+红海航道,双重涨价驱动|【风险】局势可能快速缓和",
        "confidence": "P2",
    },
    {
        "date": "2025-12-30",
        "category": "机器人",
        "keyword": "技术升级/特斯拉供应链",
        "target": "五洲新春,三花智控,锋龙股份,天奇股份,万向钱潮,浙江荣泰,拓普集团",
        "signal_content": "机器人板块全面爆发,接力商业航天:新剑传动从特斯拉供应商升级为技术供应伙伴,获灵巧手模组订单|【数据】12月29日10余个涨停,12月30日全面爆发,三花智控千亿市值首板涨停|【时间】2025-12-25至12-30|【信息差】灵巧手是特斯拉机器人核心难点,导致2代/2.5代延迟升级|【风险】春节前规避连板行情",
        "confidence": "P0",
    },
    {
        "date": "2025-12-30",
        "category": "数字人民币",
        "keyword": "事件催化/金融IT",
        "target": "翠微股份",
        "signal_content": "数字人民币2.0核心变革:从现金转为存款,运营方可动用资金放贷产生货币乘数效应|【数据】此前银行无法动用数字人民币资金放贷,2.0彻底改变|【时间】2025-12-30|【信息差】银行有强烈动力推广(抢其他银行存款)+政府支持|【风险】政策出台到全面推广需数月时间",
        "confidence": "P2",
    },
    {
        "date": "2025-12-30",
        "category": "商业航天",
        "keyword": "事件催化/跨年主题",
        "target": "商业航天板块",
        "signal_content": "商业航天跨年主题潜力:年末Q4启动,春节前调整,春节后重启,参考2024-2025年人形机器人/飞行汽车跨年行情|【数据】指数下跌期间逆指数避风港|【时间】2025年末至2026年春节|【信息差】第三/第四周期若指数暴跌,商业航天可能成为市场反抽核心|【风险】当前已调整,需休息2-3周后关注",
        "confidence": "P2",
    },
    # ===== 260104 =====
    {
        "date": "2026-01-04",
        "category": "石油/油气开采",
        "keyword": "事件催化/委内瑞拉局势",
        "target": "通源石油,新奥股份",
        "signal_content": "美国对委内瑞拉军事行动→油气开采产业链受益:委内瑞拉全球原油储量最大但产出仅占全球1%,美国控制后将推动钻井勘探+开采设施建设|【数据】VLCC运价暴跌验证交易逻辑,90%原油出口中国链条断裂|【时间】2026-01-04|【信息差】炒作核心从原油价格波动转向油气开采产业链,通源石油(钻井开采)优于新奥股份(LNG贸易)|【风险】地缘事件不确定性,开发进度不及预期",
        "confidence": "P1",
    },
    {
        "date": "2026-01-04",
        "category": "存储芯片",
        "keyword": "事件催化/超级IPO",
        "target": "合肥城建,上峰水泥",
        "signal_content": "长鑫存储IPO获受理:预估市值3000亿→冲高至6000亿-1万亿(参考摩尔线程700%涨幅),吸金300亿+|【数据】长鑫存储3000亿级IPO,后续长江存储连续IPO|【时间】2026-01-04|【信息差】历史规律:牛市常以超大型标的巨额IPO结束;含长量逻辑(合肥城建/上峰水泥持股不到1%)|【风险】长江存储上市后板块资金获利了结",
        "confidence": "P1",
    },
    {
        "date": "2026-01-04",
        "category": "商业航天",
        "keyword": "事件催化/IPO影子股",
        "target": "鲁信创投,金风科技,中国卫星,中国卫通,航天电子,航天晨光,航发科技",
        "signal_content": "蓝箭航天IPO预期市值2000亿→A股含蓝量炒作;商业航天进入跨年炒作,从火箭→卫星→卫星运营三阶段|【数据】鲁信创投持股1%(对应20亿市值增量),金风科技持股10%|【时间】2026-01-04|【信息差】中国卫通涨停标志炒作进入卫星运营阶段|【风险】影子股情绪驱动,上市预期兑现后回落",
        "confidence": "P2",
    },
    {
        "date": "2026-01-04",
        "category": "GPU",
        "keyword": "涨价驱动/估值重估",
        "target": "沐曦股份,摩尔线程",
        "signal_content": "GPU赛道估值重估:壁仞科技港股上市提供横向对比锚,营收为核心估值指标|【数据】壁仞2024H1营收5000万+全年3亿+,港股估值800亿港币;沐曦2024年营收7亿/2025年预估15亿,合理市值1600-1800亿,当前2300亿存在溢价|【时间】2026-01-04|【信息差】沐曦回落至1700-1800亿时估值匹配壁仞|【风险】AH溢价过高",
        "confidence": "P2",
    },
    {
        "date": "2026-01-04",
        "category": "机器人",
        "keyword": "事件催化/宇树IPO",
        "target": "锋龙股份,五洲新春",
        "signal_content": "宇树机器人IPO绿通通道取消→二级供应商利空,国内龙头老二利好;特斯拉供应链不受影响|【数据】三大炒作思路:国内成品龙头/特斯拉供应链/通用二级供应商|【时间】2026-01-04|【信息差】宇树上市延迟→资金转向替代性老二标的|【风险】连板标的波动极大,可能出现3个板回调",
        "confidence": "P1",
    },
    # ===== 260105 =====
    {
        "date": "2026-01-05",
        "category": "保险",
        "keyword": "需求爆发/资金迁移",
        "target": "上市险企",
        "signal_content": "2026年保险业开门红:个险期交普遍60%以上高增长,部分同比增速超100%|【数据】利率下行→居民储蓄迁移至保底+浮动收益保险产品|【时间】2026-01-05|【信息差】保险长钱规模增长为A股带来稳定增量资金,利好趋势行情延续|【风险】利率若回升可能逆转迁移趋势",
        "confidence": "P1",
    },
    {
        "date": "2026-01-05",
        "category": "脑机接口",
        "keyword": "事件催化/马斯克量产",
        "target": "南京熊猫,创新医疗,岩山科技,三博脑科,美好医疗,爱朋医疗",
        "signal_content": "马斯克官宣脑机接口设备大规模量产(穿硬脑膜侵入式+自动化手术)|【数据】创新医疗市值104亿/打板资金12亿;南京熊猫AH股属性港股涨39%;爱朋医疗唯一换手标的|【时间】2026-01-05|【信息差】纯热点炒作无业绩托底,10cm看南京熊猫港股锚定,20cm看爱朋医疗开盘+换手|【风险】T日爆发后次日不追首板,可接受10-20%亏损",
        "confidence": "P2",
    },
    {
        "date": "2026-01-05",
        "category": "储能",
        "keyword": "需求爆发/政策驱动",
        "target": "PCS,变压器,微逆,宁德时代",
        "signal_content": "甘肃+湖北发布容量电价补偿机制→储能项目放量|【数据】甘肃330元/千瓦·年(试行2年),本金收益率8-10%,叠加调频超10%;湖北165元/千瓦·年(试行1年)|【时间】2026-01-05|【信息差】储能需求增长传导至PCS/变压器/微逆/储能电芯|【风险】政策执行不及预期",
        "confidence": "P1",
    },
    {
        "date": "2026-01-05",
        "category": "AI/大模型",
        "keyword": "事件催化/DeepSeek发布",
        "target": "每日互动,并行科技,铜牛信息,杭钢股份",
        "signal_content": "DeepSeek春节大概率发布新模型(V3.3/V3.5/V4),V4最可能点燃市场情绪|【数据】历次DeepSeek炒作核心标的每日互动|【时间】2026年春节前|【信息差】当前处于有预期且无法证伪阶段|【风险】预期兑现即下跌,不恋战",
        "confidence": "P2",
    },
    {
        "date": "2026-01-05",
        "category": "锂电/锂矿",
        "keyword": "涨价驱动/底部回升",
        "target": "国城矿业,宁德时代",
        "signal_content": "碳酸锂现货报价12万+,盘面接近13万,锂电产业链底部回升|【数据】储能需求传导+新能源车需求复苏|【时间】2026-01-05|【信息差】国城矿业锂矿股核心,宁德时代储能电芯龙头|【风险】固态电池技术不达标(能量密度不足)",
        "confidence": "P1",
    },
    {
        "date": "2026-01-05",
        "category": "有色金属/铝",
        "keyword": "涨价驱动/供给紧缺",
        "target": "云铝股份,中孚实业",
        "signal_content": "铝价突破3000美元/吨,海外产能受限+国内产能天花板|【数据】云铝股份与中孚实业弹性最高|【时间】2026-01-05|【信息差】金属炒作顺序:铜铝→原油→农产品|【风险】价格高位回调风险",
        "confidence": "P1",
    },
    {
        "date": "2026-01-05",
        "category": "半导体/PCB",
        "keyword": "技术升级/封装演进",
        "target": "亚翔集成,圣晖集成,百城股份,兆易创新,普冉股份",
        "signal_content": "台积电封装技术从COWOS进化到COWOP(砍掉中间基板直封PCB);英伟达Rubin架构3月测试6月完成|【数据】COWOP 2027年落地,Rubin架构带动PCB板块异动|【时间】2026-01-05|【信息差】洁净室为半导体最强主线,存储芯片为辅;PCB技术要求提升|【风险】技术落地不及预期",
        "confidence": "P2",
    },
]

def write_signals(db_path, signals):
    """写入信号到SQLite,含locked重试机制"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create table if not exists
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS industry_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            category TEXT NOT NULL,
            keyword TEXT,
            target TEXT,
            signal_content TEXT,
            confidence TEXT DEFAULT 'P2',
            status TEXT DEFAULT 'new',
            created_at TEXT
        )
    ''')
    conn.commit()
    
    count = 0
    for sig in signals:
        for attempt in range(3):
            try:
                cursor.execute(
                    "INSERT INTO industry_signals (date, category, keyword, target, signal_content, confidence, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))",
                    (sig["date"], sig["category"], sig["keyword"], sig["target"],
                     sig["signal_content"], sig["confidence"], "new")
                )
                conn.commit()
                count += 1
                break
            except sqlite3.OperationalError as e:
                if "locked" in str(e) and attempt < 2:
                    time.sleep(1)
                    continue
                else:
                    logger.info(f"❌ 写入失败: {e}")
                    raise
    
    conn.close()
    return count

if __name__ == "__main__":
    n = write_signals(DB_PATH, signals)
    logger.info(f"✅ 批次19完成：5文件 {n}信号")
