#!/usr/bin/env python3
from ..lib.logger import get_logger
logger = get_logger(__name__)
"""Extract industry signals from 4-dims recap files and write to SQLite."""

import sqlite3
import time
import os

DB_PATH = "/home/admin/openclaw/workspace/projects/烛照九阴/db/recap.db"

signals = [
    # === 2025-11-12 ===
    {
        "date": "2025-11-12",
        "category": "锂电池",
        "keyword": "涨价驱动/VC添加剂",
        "target": "华盛锂电,新宙邦",
        "signal_content": "VC添加剂报价异常高涨|【数据】报价单日涨幅超预期|【时间】2025-11-12|【信息差】山东远传停产检修导致供给收缩|【风险】复产后价格可能暴跌",
        "confidence": "P1",
    },
    {
        "date": "2025-11-12",
        "category": "光伏",
        "keyword": "供给紧缺/硅片",
        "target": "阿特斯,阳光电源",
        "signal_content": "硅片企业降价，光伏行业严重过剩|【数据】硅片价格持续下行|【时间】2025-11-12|【信息差】政策定位为托底而非速效，价格由供需决定|【风险】过剩格局短期难改",
        "confidence": "P2",
    },
    {
        "date": "2025-11-12",
        "category": "科技硬件",
        "keyword": "事件催化/产能管控",
        "target": "",
        "signal_content": "工信部控制低技术水平产能扩张，防止重蹈光伏覆辙|【数据】政策明确限制低水平产能|【时间】2025-11-12|【信息差】利好现有产能公司，新公司扩张难度加大|【风险】外围需求下降",
        "confidence": "P2",
    },
    {
        "date": "2025-11-12",
        "category": "储能",
        "keyword": "需求爆发/储能电池",
        "target": "阳光电源,海博思创",
        "signal_content": "储能电池快速发展，增长趋势比光伏更明显|【数据】储能板块强势|【时间】2025-11-12|【信息差】机构偏好储能大票|【风险】市场风声鹤唳心态可能蔓延",
        "confidence": "P2",
    },
    {
        "date": "2025-11-12",
        "category": "商业航天",
        "keyword": "事件催化/卫星互联网",
        "target": "中国卫星",
        "signal_content": "商业航天板块异动|【数据】核心标的为中国卫星等四只股票|【时间】2025-11-12|【信息差】板块独立走强|【风险】题材炒作持续性存疑",
        "confidence": "P3",
    },

    # === 2025-11-13 ===
    {
        "date": "2025-11-13",
        "category": "贵金属",
        "keyword": "涨价驱动/黄金白银",
        "target": "紫金矿业,山东黄金",
        "signal_content": "现货黄金突破4230美元/盎司，沪银主力涨超5%创历史新高|【数据】黄金4230美元/盎司，沪银+5%|【时间】2025-11-13|【信息差】政府停摆结束，关键数据恢复，美联储12月利率决策依据充足|【风险】停摆为暂时性事件",
        "confidence": "P0",
    },
    {
        "date": "2025-11-13",
        "category": "光模块",
        "keyword": "需求爆发/1.6T光模块",
        "target": "中际旭创,新易盛,天孚通信",
        "signal_content": "1.6T光模块需求显著增长|【数据】预测2026年需求3000万支，英伟达贡献近2000万支、谷歌1200万支|【时间】2025-11-13|【信息差】英伟达可能自建整机柜服务器，液冷订单集中利好大公司|【风险】技术路线变化",
        "confidence": "P0",
    },
    {
        "date": "2025-11-13",
        "category": "锂电池",
        "keyword": "涨价驱动/VC添加剂",
        "target": "华盛锂电",
        "signal_content": "VC价格因山东远传公司停产检修大幅上涨，单日涨幅超预期|【数据】单日涨幅超预期|【时间】2025-11-13|【信息差】市场反应推动锂电池板块强劲表现|【风险】复产预期可能导致价格暴跌",
        "confidence": "P1",
    },
    {
        "date": "2025-11-13",
        "category": "碳酸锂",
        "keyword": "涨价驱动/碳酸锂",
        "target": "天齐锂业,赣锋锂业,大中矿业",
        "signal_content": "摩根大通上调2026年碳酸锂目标价至9万元/吨，长期目标价约10万元/吨|【数据】目标价9万/吨，长期10万/吨|【时间】2025-11-13|【信息差】认为有上涨空间|【风险】供需格局变化",
        "confidence": "P0",
    },
    {
        "date": "2025-11-13",
        "category": "六氟磷酸锂",
        "keyword": "涨价驱动/电解液材料",
        "target": "天赐材料,多氟多,天际股份",
        "signal_content": "六氟磷酸锂市场价格区间10.8万至15万元/吨，主流价格13万元|【数据】主流价13万元/吨|【时间】2025-11-13|【信息差】天赐材料涨停表现优于多氟多和天际股份|【风险】市场表现分化",
        "confidence": "P1",
    },
    {
        "date": "2025-11-13",
        "category": "有机硅",
        "keyword": "涨价驱动/DMC",
        "target": "合盛硅业,东岳硅材",
        "signal_content": "有机硅DMC价格涨至1.25万元/吨，目标价1.35万元/吨|【数据】现价1.25万，目标1.35万|【时间】2025-11-13|【信息差】上涨空间有限|【风险】涨幅已受限",
        "confidence": "P2",
    },
    {
        "date": "2025-11-13",
        "category": "有色金属",
        "keyword": "涨价驱动/锡",
        "target": "兴业银锡",
        "signal_content": "印尼打击走私导致锡出口大幅下降，锡价上涨|【数据】锡出口大幅下降|【时间】2025-11-13|【信息差】供需紧张推动价格上涨|【风险】政策变动",
        "confidence": "P1",
    },
    {
        "date": "2025-11-13",
        "category": "有色金属",
        "keyword": "涨价驱动/铜铝",
        "target": "中信金属,中粮糖业",
        "signal_content": "铜、铝价格上涨|【数据】铜铝价格同步上涨|【时间】2025-11-13|【信息差】政府购金军备竞赛式行为推动大宗商品持续表现|【风险】需求端疲软",
        "confidence": "P2",
    },
    {
        "date": "2025-11-13",
        "category": "锂电池",
        "keyword": "涨价驱动/振华金属",
        "target": "",
        "signal_content": "振华金属价格上调，军工与SOFC需求增长|【数据】价格区间波动明显上调|【时间】2025-11-13|【信息差】两G与SOFC需求增长|【风险】需求持续性",
        "confidence": "P2",
    },
    {
        "date": "2025-11-13",
        "category": "储能",
        "keyword": "需求爆发/电池采购",
        "target": "海博思创,宁德时代",
        "signal_content": "海博思创公告采购200GWh电池，表现强势|【数据】采购200GWh电池|【时间】2025-11-13|【信息差】汽车锂电方向集体大涨|【风险】高位利好逻辑警惕",
        "confidence": "P0",
    },
    {
        "date": "2025-11-13",
        "category": "锂电池",
        "keyword": "涨价驱动/磷酸铁锂电解液",
        "target": "宁德时代,德方纳米",
        "signal_content": "正极材料磷酸铁锂和电解液涨价，是当前市场核心矛盾|【数据】磷酸铁锂和电解液价格上行|【时间】2025-11-13|【信息差】碳酸锂涨价时关注左侧标的，电解液涨价时关注右侧标的|【风险】需计算标的弹性",
        "confidence": "P1",
    },

    # === 2025-11-16 ===
    {
        "date": "2025-11-16",
        "category": "碳酸锂",
        "keyword": "供给紧缺/碳酸锂",
        "target": "天齐锂业,赣锋锂业,大中矿业",
        "signal_content": "碳酸锂可能面临供不应求|【数据】供需趋紧|【时间】2025-11-16|【信息差】从弹性角度筛选受益标的|【风险】价格波动影响企业利润率",
        "confidence": "P1",
    },
    {
        "date": "2025-11-16",
        "category": "有机硅",
        "keyword": "涨价驱动/DMC",
        "target": "合盛硅业",
        "signal_content": "DMC报价上涨显示行业活力|【数据】DMC报价上行|【时间】2025-11-16|【信息差】锂矿与储能行业被视为强劲市场标的|【风险】需持续跟踪",
        "confidence": "P2",
    },
    {
        "date": "2025-11-16",
        "category": "固态电池",
        "keyword": "技术升级/固态电池",
        "target": "海辰药业,赛力斯,宁德时代",
        "signal_content": "固态电池行业发展，海辰药业与赛科动力合作|【数据】合作推进固态电池|【时间】2025-11-16|【信息差】宁德时代可能提前采购设备|【风险】产业化进度不确定",
        "confidence": "P2",
    },
    {
        "date": "2025-11-16",
        "category": "情绪周期",
        "keyword": "情绪周期/大盘信号",
        "target": "",
        "signal_content": "VX指标反映市场贪婪与恐惧，顶点回落预示风险消退|【数据】VX指数高点后阳线伴随快速下行|【时间】2025-11-16|【信息差】市场大幅涨跌时VX上涨，横盘时VX下跌|【风险】国内缺乏空波动率工具，逆势操作风险高",
        "confidence": "P2",
    },
    {
        "date": "2025-11-16",
        "category": "情绪周期",
        "keyword": "情绪周期/资金流向",
        "target": "",
        "signal_content": "外部资金对A股态度转冷，更倾向投资日韩台资产，外汇持续贬值|【数据】外汇持续贬值|【时间】2025-11-16|【信息差】中概股和光伏资产遭抛售风险|【风险】市场长期调整压力",
        "confidence": "P1",
    },

    # === 2025-11-17 ===
    {
        "date": "2025-11-17",
        "category": "碳酸锂",
        "keyword": "涨价驱动/碳酸锂",
        "target": "天齐锂业,赣锋锂业",
        "signal_content": "碳酸锂价格涨停，赣锋锂业在动力电池大会发言预测2026年市场紧平衡|【数据】碳酸锂涨停|【时间】2025-11-17|【信息差】2026年可能面临紧平衡引发价格上涨|【风险】市场预期较低，次日开盘可能不大幅上涨",
        "confidence": "P0",
    },
    {
        "date": "2025-11-17",
        "category": "钠电池",
        "keyword": "需求爆发/钠电池",
        "target": "容百科技,宁德时代",
        "signal_content": "宁德时代与容百科技钠电池合作，承诺每年采购容百钠电正极材料不少于其采购量60%|【数据】采购量≥60%|【时间】2025-11-17|【信息差】容百设为第一供应商|【风险】碳酸锂价格下跌后钠电池成本优势减弱",
        "confidence": "P0",
    },
    {
        "date": "2025-11-17",
        "category": "光刻胶",
        "keyword": "供给紧缺/光刻胶",
        "target": "",
        "signal_content": "美日关系紧张升级，光刻胶供应紧张|【数据】供应紧张|【时间】2025-11-17|【信息差】美日关系影响供应链|【风险】地缘政治不确定性",
        "confidence": "P2",
    },
    {
        "date": "2025-11-17",
        "category": "固态电池",
        "keyword": "技术升级/固态电池",
        "target": "容百科技,弘光科技,宁德时代",
        "signal_content": "固态电池领域双核心：复合负极材料创新与设备供应商|【数据】弘光科技作为设备供应商表现强劲|【时间】2025-11-17|【信息差】宁德时代在特斯拉供应链中地位增强，德国工厂量产突破|【风险】技术路线竞争",
        "confidence": "P1",
    },
    {
        "date": "2025-11-17",
        "category": "数据中心",
        "keyword": "需求爆发/OCS交换机",
        "target": "",
        "signal_content": "谷歌在德州投资建设数据中心，推动OCS交换机需求|【数据】德州数据中心投资|【时间】2025-11-17|【信息差】谷歌光模块用量增加|【风险】建设进度",
        "confidence": "P2",
    },
    {
        "date": "2025-11-17",
        "category": "情绪周期",
        "keyword": "情绪周期/游资",
        "target": "合富中国,平潭发展",
        "signal_content": "合富中国被停牌核查但未导致游资风险偏好降低，福建题材成情绪锚定点|【数据】合富中国12天11板后被停牌核查|【时间】2025-11-17|【信息差】市场未出现明显亏钱效应|【风险】平潭发展表现决定市场赚钱效应",
        "confidence": "P2",
    },

    # === 2025-11-18 ===
    {
        "date": "2025-11-18",
        "category": "碳酸锂",
        "keyword": "涨价驱动/碳酸锂",
        "target": "天齐锂业,赣锋锂业",
        "signal_content": "碳酸锂现货价格随期货上涨而上调|【数据】现货价格同步上调|【时间】2025-11-18|【信息差】反映市场对碳酸锂价格的积极预期|【风险】持续性存疑",
        "confidence": "P1",
    },
    {
        "date": "2025-11-18",
        "category": "半导体设备",
        "keyword": "需求爆发/半导体设备",
        "target": "北方华创,拓荆科技,中微公司,中芯国际",
        "signal_content": "北方华创、拓荆科技、中微公司三家半导体设备龙头同一天同一时间集体涨停|【数据】三家公司集体涨停|【时间】2025-11-18|【信息差】大资金建仓迹象明显，中芯国际产能利用率高|【风险】后续催化是否持续",
        "confidence": "P0",
    },
    {
        "date": "2025-11-18",
        "category": "AI/数据中心",
        "keyword": "技术升级/算力优化",
        "target": "华为概念,寒武纪,阿里",
        "signal_content": "华为11月21日AI发布会，提升数据中心显卡利用率从30%提高至70%|【数据】利用率从30%→70%|【时间】2025-11-18|【信息差】可能通过虚拟磁化技术实现共享算力池|【风险】技术门槛高但非专利，寒武纪或阿里平头哥可开发类似技术",
        "confidence": "P0",
    },
    {
        "date": "2025-11-18",
        "category": "锂电池",
        "keyword": "涨价驱动/磷酸铁锂",
        "target": "德方纳米,宁德时代",
        "signal_content": "磷酸铁锂因扩产过多面临成本和价格压力，行业协商合理定价|【数据】扩产过多导致价格压力|【时间】2025-11-18|【信息差】碳酸锂持续涨价，但磷酸铁锂受产能过剩制约|【风险】叶公好龙心态",
        "confidence": "P1",
    },
    {
        "date": "2025-11-18",
        "category": "情绪周期",
        "keyword": "情绪周期/市场冰点",
        "target": "",
        "signal_content": "市场冰点暴跌，外汇数据恶化至-1354，成交金额1.94万亿，上证指数跌0.8%连续三天下跌|【数据】外汇-1354，成交1.94万亿，沪指-0.8%|【时间】2025-11-18|【信息差】中日关系紧张升级影响亚太股市|【风险】建议60日均线附近操作，接受4%亏损",
        "confidence": "P1",
    },
    {
        "date": "2025-11-18",
        "category": "光模块",
        "keyword": "需求爆发/光模块",
        "target": "中际旭创,新易盛",
        "signal_content": "光模块、PCB、液冷板块炒作逻辑，英伟达财报前布局|【数据】英伟达财报前|【时间】2025-11-18|【信息差】建议提前布局科技硬件避免财报后波动|【风险】财报不及预期",
        "confidence": "P1",
    },
]


def insert_with_retry(conn, signals):
    """Insert signals with retry on database locked."""
    cursor = conn.cursor()
    created_at = time.strftime("%Y-%m-%d %H:%M:%S")
    inserted = 0
    for sig in signals:
        for attempt in range(3):
            try:
                cursor.execute(
                    """INSERT INTO industry_signals
                       (date, category, keyword, target, signal_content, confidence, status, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        sig["date"],
                        sig["category"],
                        sig["keyword"],
                        sig["target"],
                        sig["signal_content"],
                        sig["confidence"],
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
                    raise
    conn.commit()
    return inserted


def main():
    conn = sqlite3.connect(DB_PATH)
    try:
        count = insert_with_retry(conn, signals)
        logger.info(f"✅ 导读批次4完成：5文件 {count}信号")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
