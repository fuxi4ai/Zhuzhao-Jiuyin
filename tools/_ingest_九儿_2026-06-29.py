#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""九儿 · 260629四维度训练营-总结.pdf 入库 recap.db（dim1–4 + recap_daily）。

口径：source='小鲍复盘课件' / confidence='P2' / kejian_date='2026-06-29'。
仓位：原文明确『总仓位控制在半仓左右』『保持中等仓位(四至五成),进可攻退可守』→ 两处一致、可量化、conf=mid →
      结构化仓位列照落：position_pct_min=.4/max=.5/repr=.45/stance=中性/conf=mid/band=中。
      (与 06-28 分档区间留人工不同：本日为单一总仓立场,闸门通过。)
数字列只录课件明说：成交≈3.53万亿、涨停106/跌停40、离岸人民币重回6.79上方、中证1000支撑7900。
processed_kejian 由 dedup_kejian.py record --all-new 单独管（本脚本不碰）。

安全：写前自动备份 → 写后强 integrity_check → 坏则回滚退非零。
用法：python3 _ingest_九儿_2026-06-29.py <recap.db路径>   # 默认 ~/Documents/Database/烛照九阴/recap.db
"""
import sqlite3, sys, shutil, os
from datetime import datetime
from pathlib import Path
import os.path as _zzosp
sys.path.insert(0, _zzosp.dirname(_zzosp.dirname(_zzosp.abspath(__file__))))
import config  # 中央写护栏 connect_write（G019）

DB = Path(sys.argv[1]) if len(sys.argv) > 1 else (
    Path.home() / "Documents" / "Database" / "烛照九阴" / "recap.db")
NOW = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
D = "2026-06-29"
SRC = "小鲍复盘课件"
CONF = "P2"

# ---------- 提炼内容（九儿现场读原文，不调任何外部LLM） ----------
recap_daily = dict(
    date=D, source=SRC, speaker="小鲍",
    cycle_stage="冰点修复·大小盘剧烈分化·硬科技(芯片)主线确认(长鑫上市前'鱼尾行情')",
    cycle_number=1,
    market_summary=(
        "围绕A股剧烈波动与修复提炼三核心：①市场风格显著'大小票分化',上证50强于中证1000,指数修复但中小盘持仓者操作难度大、"
        "需警惕'权重护盘小票失血'引发的流动性风险(观察锚点:中证1000在7900点支撑,有效跌破则降仓避险);②确认'硬科技'为绝对主线,"
        "芯片强于科技硬件,资金在指数探底回升中明确抱团半导体,医药等仅作轮动避险替补;③半导体处长鑫存储上市前'鱼尾行情'阶段,"
        "预计七月中旬申购前后出现剧烈筹码交换与砸盘。盘面:上证走长下影'大长腿'修复但深成指/创业板实体涨幅微弱=结构性反弹非普涨;"
        "成交≈3.53万亿(量比缩量约1%、存量博弈),涨停106/跌停40呈'冰点修复'赚钱与亏钱效应并存;13:20后韩国三星/海力士扩产消息点燃做多,"
        "机构风险偏好清晰指向芯片与CRO。情绪走'恐慌压制→分歧修复→主线确认';AI利空(Token增速放缓/算力受限)系供给瓶颈非需求萎缩,"
        "中美唯二全链路稀缺性支撑科技长期逻辑。"),
    key_themes=("大小盘分化(上证50>中证1000·权重护盘小票失血·7900锚点);硬科技主线(芯片>科技硬件);长鑫存储IPO'鱼尾行情'(七月中旬申购/七月底上市);"
                "华为产业链国产替代(连接器/GPU·华工科技/华丰科技涨停);光通信康宁GlassBridge'错杀'(Rubin Ultra 2027H2-2028量产);"
                "三星海力士扩产催化(13:20后);CRO/医药轮动避险替补;成交3.53万亿/涨停106跌停40;离岸人民币重回6.79上方"),
    confidence=CONF, created_at=NOW, updated_at=NOW,
)

dim1 = dict(
    date=D,
    usd_cny=6.79,
    key_signals=("地缘:早盘受中东及东亚地缘升温压制、风险偏好下行,午后美伊谈判恢复+霍尔木兹海峡通行正常、国际油价未随地缘风险上涨→市场对地缘的过度定价获修正、情绪回暖;"
                 "汇率:离岸人民币汇率重回6.79上方(人民币走强),外围环境稳定为日内修复提供基础;"
                 "海外催化:13:20后韩国三星与海力士大幅扩充芯片产能消息点燃做多、缓解AI产业链需求担忧;预计今晚美股及日韩修复性上涨。"
                 "(本课件未给纳指/恒生/油价具体点位,数值列除离岸汇率外留空)"),
    pricing_direction="外围转稳·地缘过度定价修正(油价未随地缘上涨·离岸人民币走强)",
    usd_direction="偏弱/稳(离岸人民币重回6.79上方)",
    usd_summary="离岸人民币重回6.79上方、人民币走强;外围环境稳定为日内修复提供基础",
    market_linkage="美伊谈判恢复+霍尔木兹通行正常+油价未随地缘上涨→地缘过度定价修正;离岸汇率回6.79上方;三星海力士扩产(13:20后)点燃A股科技反攻",
    created_at=NOW,
)

dim2 = dict(
    date=D,
    main_line="硬科技主线·芯片(半导体)>科技硬件(指数V型反转中半导体起决定性作用·资金由净流出转大幅净流入)",
    main_line_logic=("主线判定的客观性:市场从冰点向下砸盘后重新修复时,资金最先抱团、涨幅最大、与指数共振最强的板块即主线;"
                     "今日半导体在指数V型反转中起决定性作用、资金由净流出转大幅净流入,铁一般事实确立其主线地位;"
                     "任何主线切换的猜测须待新领涨板块伴随指数大涨出现后方可成立"),
    sector_logic=("半导体/芯片为绝对核心、强度优于科技硬件:全球AI算力需求旺盛(B300服务器半年回本证下游需求刚性)+国产替代在外部压力下强化"
                  "(华为产业链连接器/GPU亮眼,华工科技/华丰科技强势涨停)。时间窗口=长鑫存储IPO(七月中旬申购、七月底上市),老师定义此阶段为'鱼尾行情':"
                  "长鑫作国产存储'正宫',上市吸引资金打新/配置→现有存储概念股(如兆易创新)面临资金分流甚至被抛弃,短期芯片或经筹码交换引发剧烈震荡甚至砸盘、为后续蓄势;"
                  "设备/材料环节业绩确定性强、不受单一成品上市冲击,相对更稳健。"
                  "光通信:近期因康宁GlassBridge新技术担忧大幅回调=过度反应/'错杀'(GlassBridge绑定英伟达Rubin Ultra架构、大规模量产要2027H2甚至2028,未来一年现有光模块财务模型不变),"
                  "跌幅已达20%-30%的优质标的反弹性价比高。医药/CRO作轮动中的避险替补。"),
    sectors_bullish="半导体/芯片(华为产业链连接器/GPU·设备/材料·分选机·华工科技/华丰科技/金海通/银河微电/有研硅),光通信(错杀修复·跌20-30%优质标的),CRO/医药(避险替补·海思科/特一药业)",
    sectors_bearish="中小盘(大小分化·权重护盘小票失血·7900破位则系统性风险),存储成品概念股(长鑫IPO资金分流·兆易创新),边缘题材/跟风股",
    price_catalyst="韩国三星/海力士大幅扩产(13:20后);长鑫存储IPO(七月中旬申购/七月底上市);B300服务器半年回本;美伊谈判恢复+霍尔木兹通行正常;银河微电收购恒泰科半导体复牌",
    supply_demand="AI算力供给侧瓶颈非需求萎缩:Token增速放缓=算力供给不足的被动结果,反印证算力租赁高景气(B300半年回本);中美唯二打通芯片到模型全链路、稀缺性决定主线长期逻辑",
    hot_sectors="半导体芯片,华为产业链(连接器/GPU),光通信(错杀修复),CRO医药,先进封装(分选机)",
    created_at=NOW,
)

signals = [
    dict(category="大小盘/风格", keyword="大小票剧烈分化·权重护盘小票失血·中证1000 7900锚点",
         target="上证50,中证1000,7900,大小盘分化",
         signal_content="上证50显著强于中证1000,历史几次重大调整/'股灾'前夕常伴'权重护盘、小票失血';若持续则多数中小盘持仓者'赚指数不赚钱'甚至亏损。观察锚点:中证1000在7900点支撑,有效跌破并继续下行=市场生态恶化,应果断降仓规避系统性风险",
         logic_type="event_driven"),
    dict(category="电子/半导体", keyword="半导体主线王者·芯片强于科技硬件(V型反转决定性)",
         target="半导体,芯片,科技硬件,主线",
         signal_content="芯片板块强度优于科技硬件、是资金指数修复中首选抱团对象;今日半导体在指数V型反转中起决定性作用,资金由净流出转大幅净流入,铁一般事实确立主线地位;判主线方法论:冰点砸盘后修复时最先抱团、涨幅最大、与指数共振最强者即主线",
         logic_type="logic_driven"),
    dict(category="半导体/IPO", keyword="长鑫存储IPO'鱼尾行情'·七月中旬申购砸盘预警",
         target="长鑫存储,兆易创新,存储,IPO",
         signal_content="长鑫存储预计七月中旬申购、七月底上市,作国产存储'正宫'将吸引资金打新/配置→现有存储概念股(如兆易创新)面临资金分流甚至被抛弃;短期芯片或经筹码交换引发剧烈震荡甚至砸盘(鱼尾→申购前抽血砸盘→上市后新闻效应带新行情),设备/材料不受单一成品上市冲击相对稳健;警惕'利好兑现变利空'尤其非正宗存储概念股",
         logic_type="event_driven"),
    dict(category="国产替代/华为链", keyword="华为产业链连接器/GPU国产替代·B300半年回本",
         target="华为,连接器,GPU,华工科技,华丰科技",
         signal_content="国产替代在外部压力下愈发强化,华为产业链相关连接器、GPU等细分领域表现亮眼(华工科技、华丰科技强势涨停即明证);全球AI算力需求持续旺盛,B300服务器半年回本的暴利现状证下游需求刚性",
         logic_type="logic_driven"),
    dict(category="光通信/材料", keyword="康宁GlassBridge'错杀'·Rubin Ultra量产2027后",
         target="光通信,康宁,GlassBridge,光模块,英伟达",
         signal_content="光通信近期因康宁GlassBridge新技术担忧(疑颠覆现有光模块技术路线)大幅回调,老师解析研报判为过度反应:GlassBridge绑定英伟达Rubin Ultra架构、大规模量产要2027H2甚至2028,未来一年现有光模块企业财务模型不变,当前下跌属典型'错杀';跌幅已达20%-30%的优质标的反弹性价比高",
         logic_type="logic_driven"),
    dict(category="海外/催化", keyword="三星海力士大幅扩产·13:20点燃做多",
         target="三星,海力士,扩产,芯片产能",
         signal_content="下午13:20后韩国关于三星与海力士大幅扩充芯片产能的重磅消息成为点燃市场做多热情的导火索,缓解市场对AI产业链需求的担忧,直接带动A股科技板块集体反攻;机构风险偏好清晰指向芯片与CRO",
         logic_type="event_driven"),
    dict(category="AI/产业逻辑", keyword="AI利空误读·Token增速放缓=供给瓶颈非需求萎缩",
         target="AI,Token,算力,中美全链路",
         signal_content="市场对AI利空(Token增速放缓、算力供应受限)存在误读:实为供给侧瓶颈而非需求侧萎缩,反印证算力租赁高景气(B300半年回本);全球唯中美两国具备打通芯片到模型全链路能力,稀缺性决定科技主线长期逻辑未变",
         logic_type="logic_driven"),
]

dim3 = dict(
    date=D,
    emotion_stage="冰点修复·大小盘剧烈分化·主线确认(恐慌压制→分歧修复→主线确认)",
    limit_up=106,
    limit_down=40,
    volume_trillion=3.53,
    trading_amount="约3.53万亿(量比缩量约1%·存量博弈)",
    up_down_ratio="涨停106/跌停40",
    volume_description="两市成交额约3.53万亿,量比缩量约1%,市场仍以存量博弈为主",
    sentiment_description=("情绪经'恐慌压制→分歧修复→主线确认':早盘受中东及东亚地缘升温压制、避险资金涌入蓝筹,盘面一度'跌出股灾味';"
                           "午后美伊谈判恢复+霍尔木兹通行正常+油价未随地缘上涨→对地缘过度定价修正、情绪回暖;13:20后三星/海力士扩产消息点燃做多、带动科技集体反攻;"
                           "涨停106/跌停40呈赚钱与亏钱效应并存的'冰点修复'特征,机构风险偏好清晰指向芯片与CRO;老师强调不能简单视作全面反转,"
                           "AI利空系供给瓶颈非需求萎缩、情绪波动多为短期消息面与IPO预期扰动所致而非产业逻辑根本破坏"),
    trend_description="上证连续两日下跌后走长下影'大长腿'修复形态、视觉吸引,但深成指/创业板实体涨幅微弱=结构性反弹非普涨;最关键信号为大小盘剧烈切换(上证50>中证1000)",
    support_level_detail="中证1000 7900点为关键支撑/观察锚点,有效跌破并继续下行=市场生态恶化、应果断降仓",
    news_catalysts="三星/海力士扩产(13:20后);美伊谈判恢复+霍尔木兹通行正常;长鑫存储IPO预期;银河微电收购恒泰科半导体复牌;海思科FDA批准",
    policy_news="长鑫存储IPO(七月中旬申购/七月底上市)预期扰动",
    industry_logic="硬科技(芯片)主线确认,芯片>科技硬件;光通信错杀修复;医药/CRO轮动避险替补;大小盘分化下中小盘流动性风险",
    price_driver="13:20三星/海力士扩产消息→科技集体反攻;半导体V型反转资金由净流出转大幅净流入",
    created_at=NOW,
)

dim4_stocks = [
    dict(date=D, stock_name="华工科技", sector="华为产业链/光器件",
         bull_reason="华为产业链代表,受益国产替代情绪,技术图形强势,连接器和光器件方向龙头",
         bear_reason=None, position_suggestion="主线龙头(看好·加粗加红)", confidence="高", source="小鲍老师", updated_at=NOW),
    dict(date=D, stock_name="华丰科技", sector="华为产业链/连接器",
         bull_reason="华为产业链代表,受益国产替代情绪,技术图形强势,连接器方向龙头",
         bear_reason=None, position_suggestion="主线龙头(看好)", confidence="高", source="小鲍老师", updated_at=NOW),
    dict(date=D, stock_name="银河微电", sector="半导体/重组",
         bull_reason="因筹划收购恒泰科半导体而复牌一字涨停,重组预期强烈,内外一致看好",
         bear_reason=None, position_suggestion="重组预期(看好·加粗加红)", confidence="高", source="小鲍老师", updated_at=NOW),
    dict(date=D, stock_name="金海通", sector="半导体设备/分选机",
         bull_reason="半导体分选机龙头,受益先进封装扩产潮,技术形态突破前高,符合'突破战法'特征",
         bear_reason=None, position_suggestion="突破战法(看好·加粗加红)", confidence="高", source="小鲍老师", updated_at=NOW),
    dict(date=D, stock_name="有研硅", sector="半导体材料/硅片",
         bull_reason="因收购安徽某公司股权的独立事件驱动,表现优于同类硅片股,个股Alpha超越行业Beta的典型案例",
         bear_reason=None, position_suggestion="事件驱动Alpha(看好)", confidence="中", source="小鲍老师", updated_at=NOW),
    dict(date=D, stock_name="特一药业", sector="医药",
         bull_reason="医药板块中位置较低,呈标准'N字'或'双响炮'技术形态",
         bear_reason=None, position_suggestion="低位轮动(看好)", confidence="中", source="小鲍老师", updated_at=NOW),
    dict(date=D, stock_name="海思科", sector="医药/创新药",
         bull_reason="因FDA批准具备基本面支撑,具海外BD利好,医药板块位置较低",
         bear_reason=None, position_suggestion="基本面支撑(看好)", confidence="中", source="小鲍老师", updated_at=NOW),
    dict(date=D, stock_name="兆易创新", sector="半导体/存储",
         bull_reason=None,
         bear_reason="作为现有存储概念股,长鑫存储上市将吸引资金打新/配置→面临资金分流甚至被抛弃风险,警惕'利好兑现变利空'(非正宗存储概念股)",
         position_suggestion="规避/减仓(IPO分流风险)", confidence="中", source="小鲍老师", updated_at=NOW),
]

dim4_plan = dict(
    date=D,
    plan=("基调'聚焦芯片主线、半仓待黄金坑、横线战法守纪律'。①短期(明日):预计今晚美股及日韩修复性上涨→带动A股科技硬件整体回流,"
          "今日未完全修复的光通信、PCB等科技硬件细分或有补涨,重点关注今日抗跌或率先反弹的科技硬件标的。"
          "②中期(未来两周):核心变量=长鑫存储IPO,预计七月中旬申购日前后半导体集中筹码松动砸盘——砸盘前逐步降低高位存储股仓位避免接盘,"
          "密切观察砸盘承接力度;砸盘结束后是重新介入半导体优质标的(尤其设备/材料及被错杀光模块)的最佳时机,长鑫上市首日炸裂或再点燃半导体行情形成新上升波段。"
          "③仓位:宏观不确定性消除前保持中等仓位(四至五成/半仓左右),进可攻退可守,'横线战法'设好止损基准线、跌破关键支撑(成本线/技术颈线)坚决执行。"
          "④观察:中证1000是否守住7900点关口+离岸人民币稳定性,若大小票分化加剧且小票破位则无条件降仓避险。"),
    strategy_idea="主线优先聚焦芯片与科技硬件、抓核心龙头不求全覆盖;去伪存真做减法、只攻最强矛头;敬畏七月长鑫IPO砸盘、半仓待黄金坑",
    strategy_framework=("①主线判定客观性:冰点砸盘后修复时资金最先抱团、涨幅最大、与指数共振最强者即主线(今日半导体V型反转决定性、资金净流出转大幅净流入),"
                        "主线切换猜测须待新领涨板块伴随指数大涨出现后方成立。②产业逻辑深度穿透:Token增速放缓=算力供给不足非需求消失(反印证B300半年回本高景气);"
                        "康宁新技术按量产时间表(2027后)论证短期不可替代→'错杀'结论。③事件驱动逆向思维:长鑫上市推演资金博弈路径(鱼尾炒作→申购前抽血砸盘→上市后新闻效应带新行情),"
                        "七月中旬前后警惕'利好兑现变利空'。④纪律:横线战法设多空分界线,价在线上坚定持有、有效跌破无条件离场只尊重市场信号"),
    operation_advice="聚焦芯片与科技硬件抓核心龙头(华工/华丰/银河微电/金海通等加粗加红标的),AB法仓位切换、套牢/横线战法应对震荡;砸盘前降高位存储仓、砸盘后介入设备材料及错杀光模块;每笔设横线止损跌破即离场",
    prediction="明日科技硬件整体回流、光通信/PCB或补涨;未来两周核心变量长鑫IPO,七月中旬申购前后半导体集中砸盘、砸盘后为优质标的(设备/材料/错杀光模块)最佳介入点,长鑫上市首日或再点燃行情",
    entry_conditions="今日抗跌/率先反弹的科技硬件标的;长鑫砸盘结束后介入半导体优质标的(设备/材料/被错杀光模块);价格站稳'横线'多空分界线",
    exit_conditions="价格有效跌破'横线'(成本线/技术颈线)无条件离场;砸盘前逐步降低高位存储股仓位;中证1000破7900且小票破位则无条件降仓避险",
    key_stocks="华工科技,华丰科技,银河微电,金海通,有研硅,特一药业,海思科",
    key_levels="中证1000支撑7900点(破位降仓);横线止损=成本线/技术颈线;离岸人民币6.79",
    risk_warnings="大小盘分化加剧、小票失血/破位7900→系统性风险无条件降仓;长鑫存储IPO七月中旬申购前后筹码交换砸盘、'利好兑现变利空'(非正宗存储概念股如兆易创新资金分流);地缘反复扰动情绪",
    plan_window="T+1~未来两周(七月中旬长鑫IPO为关键节点)",
    # —— 仓位结构化(闸门通过:原文两处一致、可量化、conf=mid) ——
    position_pct_min=0.4,
    position_pct_max=0.5,
    position_repr=0.45,
    position_stance="中性",
    position_conf="mid",
    position_band="中",
    position_raw="『当前总仓位控制在半仓左右,预留充足现金』『在宏观不确定性消除前,保持中等仓位(如四至五成),进可攻退可守』(全文两处一致,均指单一总仓立场;另设条件性降仓触发:中证1000破7900或小票破位则无条件降仓)",
    position_source="260629四维度训练营-总结.pdf",
    created_at=NOW,
)


def _ins(con, table, d):
    cols = [k for k, v in d.items() if v is not None]
    con.execute(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
                [d[c] for c in cols])


def main():
    if not DB.exists():
        print(f"❌ 找不到 recap.db: {DB}"); return 2
    bak = DB.with_name(DB.name + ".bak_pre260629")
    shutil.copy2(DB, bak)
    print(f"已备份 → {bak.name}")
    con = config.connect_write(str(DB))
    before = {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in
              ["recap_daily", "dim1_external_pricing", "dim2_sector_themes",
               "industry_signals", "dim3_sentiment_tech", "dim4_stock_analysis", "dim4_trade_plan"]}
    # 幂等：先删本日已有的同源行
    con.execute("DELETE FROM recap_daily WHERE date=? AND source=?", (D, SRC))
    con.execute("DELETE FROM dim1_external_pricing WHERE date=?", (D,))
    con.execute("DELETE FROM dim2_sector_themes WHERE date=?", (D,))
    con.execute("DELETE FROM industry_signals WHERE date=? AND viewpoint_owner=?", (D, "小鲍老师"))
    con.execute("DELETE FROM dim3_sentiment_tech WHERE date=?", (D,))
    con.execute("DELETE FROM dim4_stock_analysis WHERE date=? AND source=?", (D, "小鲍老师"))
    con.execute("DELETE FROM dim4_trade_plan WHERE date=?", (D,))
    # 插入
    _ins(con, "recap_daily", recap_daily)
    _ins(con, "dim1_external_pricing", dim1)
    _ins(con, "dim2_sector_themes", dim2)
    for s in signals:
        s = dict(s, date=D, confidence=CONF, status="active",
                 viewpoint_owner="小鲍老师", created_at=NOW)
        _ins(con, "industry_signals", s)
    _ins(con, "dim3_sentiment_tech", dim3)
    for st in dim4_stocks:
        _ins(con, "dim4_stock_analysis", st)
    _ins(con, "dim4_trade_plan", dim4_plan)
    con.commit()
    after = {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in before}
    ic = con.execute("PRAGMA integrity_check").fetchone()[0]
    con.close()
    print("行数变化:")
    for t in before:
        print(f"  {t}: {before[t]} → {after[t]}  (+{after[t]-before[t]})")
    print(f"integrity_check: {ic}")
    if ic != "ok":
        print("⚠️ integrity 非 ok，回滚！"); shutil.copy2(bak, DB); return 3
    print("✅ 260629 入库完成（processed_kejian 请用 dedup_kejian.py record --all-new 标记）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
