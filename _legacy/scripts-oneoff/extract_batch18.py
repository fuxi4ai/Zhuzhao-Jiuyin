#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批次18: 四维度训练营 251228~251230 产业信号提取
"""

import sqlite3
import time
import os

DB_PATH = "/home/admin/openclaw/workspace/projects/烛照九阴/db/recap.db"

# Ensure DB directory exists
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

signals = [
    # === 2025-12-28 导读 ===
    {
        "date": "2025-12-28",
        "category": "PCB/CCL",
        "keyword": "涨价驱动/覆铜板",
        "target": "生益科技,南亚新材,金安国纪",
        "signal_content": "建滔覆铜板月内第二次涨价，累计涨幅15%-20%|【数据】累计涨幅15%-20%，铜价暴涨+玻璃布供应紧张双重驱动|【时间】2025年12月|【信息差】以建滔覆铜板价格作为产业链锚定指标，国内厂商跟涨|【风险】铜价回落则涨价逻辑瓦解",
        "confidence": "P0",
    },
    {
        "date": "2025-12-28",
        "category": "锂矿",
        "keyword": "涨价驱动/锂矿",
        "target": "天齐锂业,赣锋锂业",
        "signal_content": "天齐锂业调整锂价定价基准，放弃低价报价|【数据】放弃上海有色网10.05万报价，改用上海钢联更高报价|【时间】2025年12月|【信息差】锂企对低价报价不满，主动切换定价基准反映涨价意愿|【风险】下游电池厂抵制新报价",
        "confidence": "P1",
    },
    {
        "date": "2025-12-28",
        "category": "锂电池",
        "keyword": "供给紧缺/储能",
        "target": "宁德时代,德方纳米,湖南裕能",
        "signal_content": "锂电池产业链供需差扩大，储能需求为核心驱动力|【数据】需求增长预期30%，供给增长20%-30%；若需求突破40%将引发供需失衡|【时间】2025年12月|【信息差】澳大利亚户储补贴+美国数据中心强制配储拉动全球需求，宁德时代矿未复产供给审批收缩|【风险】需求不及40%预期则逻辑不成立",
        "confidence": "P1",
    },
    {
        "date": "2025-12-28",
        "category": "磷酸铁锂",
        "keyword": "供给紧缺/停产检修",
        "target": "丰元股份,德方纳米,湖南裕能",
        "signal_content": "磷酸铁锂龙头集体停产检修，行业供给收缩|【数据】德方纳米、湖南裕能等11月26日公告停产检修，丰元股份因未检修实现涨停|【时间】2025年11月26日公告|【信息差】死道友不死贫道逻辑，未检修企业受益|【风险】检修结束后复产供给恢复",
        "confidence": "P1",
    },
    {
        "date": "2025-12-28",
        "category": "商业航天",
        "keyword": "事件催化/科创板",
        "target": "航天发展,中国卫星,航天机电",
        "signal_content": "商业航天科创板第五套标准降低门槛，火箭企业上市绿色通道|【数据】仅需中大型火箭首次成功入轨即可申报，无需回收成功；国家千亿级创业引导基金落地，预计撬动万亿级社会资本|【时间】2025年12月|【信息差】政策为蓝箭、天兵等特定企业量身定制上市通道|【风险】板块已高位，新入场者面临20%-30%回调风险",
        "confidence": "P2",
    },
    {
        "date": "2025-12-28",
        "category": "情绪周期",
        "keyword": "情绪周期/第二周期",
        "target": "盛通能源,神剑股份",
        "signal_content": "市场明确处于情绪第二周期，做多热情高涨|【数据】连板高度达11板（盛通能源），触及涨停105个、涨停81个，触及跌停3个、跌停1个|【时间】2025年12月27日（上周五）|【信息差】跌停数未增加，赚钱效应在高位维持，亏钱效应局限低位|【风险】第二周期后可能出现逼空下跌",
        "confidence": "P2",
    },
    # === 2025-12-28 总结 ===
    {
        "date": "2025-12-28",
        "category": "宏观流动性",
        "keyword": "事件催化/外汇掉期",
        "target": "",
        "signal_content": "外汇掉期信号持续改善，资金面偏多|【数据】一年期外汇掉期-1101，持续向零方向靠拢，数值越近零资金越偏向流入中国|【时间】2025年12月|【信息差】A股成交2.18万亿放量5%，两次砸盘但跌停未放大，属机构ETF策略性调仓非恐慌出逃|【风险】3964点为关键控价区间，若资金加大砸盘力度则转弱",
        "confidence": "P2",
    },
    # === 2025-12-29 导读 ===
    {
        "date": "2025-12-29",
        "category": "宏观流动性",
        "keyword": "事件催化/外汇掉期",
        "target": "",
        "signal_content": "外汇掉期信号恶化，资金偏向流出|【数据】外汇掉期从-1101变化至-1140，进一步向-2000方向靠拢，灵活配置资金更偏向美国|【时间】2025年12月29日|【信息差】人民币7.0为强劲支撑位，可能触发政策应对|【风险】资金持续外流影响A股流动性",
        "confidence": "P2",
    },
    {
        "date": "2025-12-29",
        "category": "机器人",
        "keyword": "需求爆发/特斯拉",
        "target": "三花智控,拓普集团,均胜电子,五洲新春",
        "signal_content": "特斯拉擎天柱机器人2026年产能10万台，实际产值远低于市场炒作|【数据】10万台×约20万/台=200亿产值；谷歌TPU V7单价1万美元、2026年出货300-400万颗、总产值约2800亿，是擎天柱的14倍|【时间】2025年12月|【信息差】部分券商研报以100万-300万台产能测算属严重夸大|【风险】实际产值远低于千亿赛道预期，存在泡沫",
        "confidence": "P1",
    },
    {
        "date": "2025-12-29",
        "category": "AI算力",
        "keyword": "需求爆发/华为算力",
        "target": "华正新材,寒武纪,摩尔线程",
        "signal_content": "华为AI计算卡2026年Q1韩国落地，字节大额采购催化|【数据】字节跳动传闻400亿采购华为升腾卡；华为韩国计划2026年正式推出AI计算卡和数据中心方案|【时间】2026年Q1|【信息差】国内需求旺盛却优先对外输出，侧面印证华为算力卡产能已具备对外输出条件；字节可能分散采购，寒武纪、摩尔线程、沐曦股份均有机会|【风险】消息矛盾性，实际落地规模待验证",
        "confidence": "P2",
    },
    {
        "date": "2025-12-29",
        "category": "储能",
        "keyword": "需求爆发/户用储能",
        "target": "",
        "signal_content": "乌克兰户用储能需求激增|【数据】需求预计持续至2026年一季度，受俄罗斯打击能源基础设施刺激|【时间】2025年12月-2026年Q1|【信息差】此前俄乌冲突升级时欧洲户储逻辑已被充分炒作，本次属旧闻重提|【风险】战乱环境交付安装存在障碍，实际兑现存疑",
        "confidence": "P3",
    },
    {
        "date": "2025-12-29",
        "category": "机器人",
        "keyword": "涨价驱动/利润分化",
        "target": "优必选,锋龙股份,天奇股份",
        "signal_content": "国内外机器人产业链利润分化严重|【数据】海外机器人毛利率25%，国内仅5%；国内产品可降价至2.5万-9.9万具备价格竞争力|【时间】2025年12月|【信息差】国内破局方向：掌握核心部件（电机、丝杠、PEEK材料）规模化摊薄成本，或打造品牌壁垒|【风险】有量无利格局短期难以改变",
        "confidence": "P2",
    },
    {
        "date": "2025-12-29",
        "category": "贵金属",
        "keyword": "事件催化/保证金上调",
        "target": "紫金矿业",
        "signal_content": "贵金属创历史新高后剧烈跳水，逼空行情终结|【数据】CME和国内交易所同步上调保证金要求，引发杠杆资金出逃；新能源金属跟跌但有产业底|【时间】2025年12月29日|【信息差】贵金属上涨交易美国货币信用缺失，缺乏供需支撑；新能源金属交易供需差，有储能和动力电池需求托底|【风险】逼空终结后可能腰斩再腰斩，回调周期数天至两三个月",
        "confidence": "P1",
    },
    {
        "date": "2025-12-29",
        "category": "情绪周期",
        "keyword": "情绪周期/第二周期",
        "target": "胜通能源,神剑股份,嘉美包装",
        "signal_content": "市场情绪第二周期延续但赚钱效应小幅回落|【数据】涨停99家、跌停21家，最高板胜通能源12板，其次嘉美包装、神剑股份8板|【时间】2025年12月29日|【信息差】亏钱效应抬升但市场高度向上拓展，资金抱团高标；情绪周期与指数不同步|【风险】高标面临30%回调风险，神剑股份断板后需观察是否进入第三周期",
        "confidence": "P2",
    },
    # === 2025-12-30 导读 ===
    {
        "date": "2025-12-30",
        "category": "石油/航运",
        "keyword": "事件催化/地缘冲突",
        "target": "",
        "signal_content": "也门与阿联酋冲突升级，可能引发石油供应紧张|【数据】也门取消与阿联酋防务协议并要求撤军，空袭阿联酋运兵船|【时间】2025年12月30日|【信息差】地区局势失控可能引发石油供应紧张和全球航运危机，进而影响化工品价格及资源股|【风险】地缘冲突持续时间不确定",
        "confidence": "P2",
    },
    {
        "date": "2025-12-30",
        "category": "数字货币",
        "keyword": "事件催化/数字人民币",
        "target": "御银股份,翠微股份",
        "signal_content": "数字人民币进入2.0时代，从现金到存款转变|【数据】数字人民币从现金扩展到存款，激发银行参与动力，开启银行IT系统建设新赛道|【时间】2025年12月|【信息差】美联储新主席倾向支持快速降息候选人，美元走弱人民币走强；但实际IT改造资金有限|【风险】市场炒作可能缺乏实质性资金支撑",
        "confidence": "P3",
    },
    {
        "date": "2025-12-30",
        "category": "情绪周期",
        "keyword": "情绪周期/控盘",
        "target": "",
        "signal_content": "市场连续两天涨幅为零，资金控盘迹象明显|【数据】上证指数连续两天涨幅为零|【时间】2025年12月29-30日|【信息差】情绪仍在第二周期但赚钱效应回落；人民币升值对低利润率公司形成冲击|【风险】控盘行为可能导致后续方向选择的不确定性",
        "confidence": "P2",
    },
]

def write_with_retry(signals, db_path, max_retries=3):
    for attempt in range(max_retries):
        try:
            conn = sqlite3.connect(db_path, timeout=10)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            cursor = conn.cursor()

            # Check if table exists, create if not
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
            conn.commit()

            # Get current max id
            cursor.execute("SELECT COALESCE(MAX(id), 0) FROM industry_signals")
            max_id = cursor.fetchone()[0]

            inserted = 0
            for sig in signals:
                max_id += 1
                cursor.execute("""
                    INSERT INTO industry_signals (id, date, category, keyword, target, signal_content, confidence, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'new', datetime('now', '+8 hours'))
                """, (
                    max_id,
                    sig["date"],
                    sig["category"],
                    sig["keyword"],
                    sig["target"],
                    sig["signal_content"],
                    sig["confidence"],
                ))
                inserted += 1

            conn.commit()
            conn.close()
            return inserted
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() and attempt < max_retries - 1:
                time.sleep(1)
                continue
            raise
    return 0

count = write_with_retry(signals, DB_PATH)
print(f"✅ 批次18完成：5文件 {count}信号")
