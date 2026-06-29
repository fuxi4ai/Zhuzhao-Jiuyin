#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""九儿 · 260628四维度训练营-总结.pdf 入库 recap.db（dim1–4 + recap_daily）。

口径：source='小鲍复盘课件' / confidence='P2' / kejian_date='2026-06-28'。
仓位：原文给分档区间(科技高位30-50% + 低位潜伏10-20%)，无单一总仓成数 → conf=low →
      仓位数值列(position_pct_min/max/repr/stance/conf/band)留空，只落 plan/strategy/guidance，
      并追加 data/待人工复核-仓位.md（沿用 06-22~06-25 既有处置）。
processed_kejian 由 dedup_kejian.py record --all-new 单独管（本脚本不碰）。

安全：写前自动备份 → 写后强 integrity_check（非 quick_check，G019 铁律）→ 坏则回滚退非零。
用法：python3 ingest_260628.py <recap.db路径>   # 默认 ~/Documents/Database/烛照九阴/recap.db
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
D = "2026-06-28"
SRC = "小鲍复盘课件"
CONF = "P2"

# ---------- 提炼内容（九儿现场读原文，不调任何外部LLM） ----------
recap_daily = dict(
    date=D, source=SRC, speaker="小鲍",
    cycle_stage="喇叭收敛震荡周期·K型复苏(科技主线高位震荡·硬科技抱团非泡沫·回调即加仓)",
    cycle_number=1,
    market_summary=(
        "围绕宏观局势、风格切换与产业逻辑提炼三核心：①全球地缘冲突长期化+波动化→市场进入'喇叭收敛'震荡周期,"
        "适应政策与消息驱动的反复博弈;②A股呈典型'K型复苏'结构,统计局规上工业利润+18.8%、其中电子+103%贡献率43.1%,"
        "验证科技主线坚实基本面,资金抱团科技是基于业绩确定性的理性选择而非泡沫;③交易上区分'趋势标的'与'热点题材',"
        "科技主线高位震荡时以仓位控制(30%-50%)结合低位补涨板块做防御性布局,严禁盲目抄底无增长弱势板块。"
        "盘面:半导体洁净室(亚翔/圣晖)作前置环节率先反应、产业链景气度传导先行;大盘四千点附近反复震荡=消化获利盘抬高平均成本,非趋势终结。"),
    key_themes=("喇叭收敛震荡;K型复苏(电子利润+103%贡献43.1%、工业利润+18.8%);半导体洁净室先行(亚翔集成/圣晖集成);"
                "央视带货功率半导体/玻纤/光纤;商业航天'放弃火箭只做卫星'(航天工程/中国卫星);玻璃基板GlassBridge路线争议;"
                "日本产业链国产替代'人无我有';OpenAI延期IPO(行业天花板未到);回避地产/证券/白酒/养猪/银行红利(价值陷阱)"),
    confidence=CONF, created_at=NOW, updated_at=NOW,
)

dim1 = dict(
    date=D,
    key_signals=("地缘:美伊冲突及俄乌局势,美单方面释放和平信号常伴军事行动升级('口惠而实不至')→油价波动加剧、全球避险情绪升温;"
                 "汇率/贵金属:美元指数走强与黄金下跌形成'强美元弱黄金'格局,反映美联储加息预期+地缘风险溢价的复杂定价;"
                 "对A股:输入性通胀压力及出口链不确定性增加,但同时催生自主可控及军工板块交易机会。(本课件未给具体点位/涨跌幅数值,数值列留空)"),
    pricing_direction="外部动荡·避险升温(强美元弱黄金·油价波动加剧)",
    usd_direction="强(强美元弱黄金)",
    usd_summary="强美元、弱黄金格局;反映美联储加息预期与地缘风险溢价定价",
    market_linkage="强美元/黄金弱/油价波动加剧/避险升温;输入性通胀+出口链不确定→利好自主可控与军工",
    created_at=NOW,
)

dim2 = dict(
    date=D,
    main_line="硬科技主线(电子半导体)·K型复苏(电子利润翻倍验证·回调即加仓)",
    main_line_logic=("'K型复苏'下资金流向高成长科技是必然:CPI转正预期使红利资产(银行)吸引力下降,新'国九条'限制微盘股炒作空间;"
                     "判断科技是否见顶不看市盈率而看供需——只要云厂商算力计划买不到、大模型需求仍激增,科技逻辑就未破坏,'泡沫'靠时间与业绩兑现自然消化"),
    sector_logic=("电子半导体为绝对核心:统计局电子利润+103%(贡献43.1%),AI算力需求爆发+国产替代双驱;功率半导体/先进封装(HBM相关设备)/玻璃基板"
                  "处于供需紧平衡甚至供不应求,央视实地调研证去库存完成、订单饱满,老师看法'回调即加仓'用时间换空间消化估值。"
                  "商业航天与军工=低位高性价比,阶段策略'放弃火箭、只做卫星'(火箭回收成功率不确定且多事件驱动;卫星互联网确定性更高,随长征系列发射推进卫星制造/应用端率先受益,航天工程/中国卫星估值修复),军工无人机/3D打印新技术应用值得关注。"
                  "传统周期与红利承压:地产/证券/白酒/养猪缺边际利好易陷'价值陷阱',银行红利逻辑建立在负利率之上、随CPI回升与利率上行而衰减,建议观望"),
    sectors_bullish="电子半导体(功率半导体/先进封装HBM/玻璃基板/半导体洁净室·亚翔集成/圣晖集成),商业航天卫星(航天工程/中国卫星),军工(无人机/3D打印),国产替代(日本材料设备替代)",
    sectors_bearish="地产,证券,白酒,养猪,银行(红利逻辑衰减·价值陷阱·缺边际利好)",
    price_catalyst="统计局工业利润+18.8%/电子+103%;央视带货功率半导体/玻纤/光纤;长征系列火箭发射;OpenAI延期IPO(行业天花板未到)",
    supply_demand="功率半导体/先进封装/玻璃基板供需紧平衡甚至供不应求;央视调研证去库存完成、订单饱满",
    hot_sectors="电子半导体,半导体洁净室,商业航天卫星,先进封装HBM,玻璃基板",
    created_at=NOW,
)

signals = [
    dict(category="半导体/洁净室", keyword="半导体洁净室先行指标·扩产预期前置",
         target="洁净室,亚翔集成,圣晖集成,半导体扩产",
         signal_content="每当半导体板块启动扩产预期,洁净室作为前置环节总率先反应;亚翔集成/圣晖集成异动不只是单股上涨,更是产业链景气度传导的先行指标,市场资金正从炒概念转向追踪有实际订单落地与产能扩张支撑的细分领域",
         logic_type="event_driven"),
    dict(category="电子/半导体", keyword="电子利润+103%贡献43.1%·K型复苏引擎",
         target="电子,半导体,统计局,工业利润",
         signal_content="国家统计局:规模以上工业企业利润同比+18.8%,其中电子行业利润激增103%、贡献率高达43.1%,确立电子作为当前经济复苏引擎地位;基本面坚实,资金抱团科技是基于业绩确定性的理性选择而非泡沫破裂前兆",
         logic_type="event_driven"),
    dict(category="政策/官媒", keyword="央视连续带货功率半导体/玻纤/光纤",
         target="央视,功率半导体,玻纤,光纤",
         signal_content="央视连续带货功率半导体、玻纤、光纤等硬科技,释放强烈产业政策支持信号;官方媒体背书有效对冲外部地缘负面情绪,使国内资金敢在科技主线接力",
         logic_type="event_driven"),
    dict(category="商业航天", keyword="放弃火箭只做卫星·卫星互联网确定性",
         target="卫星互联网,航天工程,中国卫星,长征系列",
         signal_content="阶段策略'放弃火箭、只做卫星':火箭回收技术备受关注但成功率不确定、相关公司多事件驱动;卫星互联网建设确定性更高,随长征系列发射推进卫星制造与应用端率先受益,火箭发射成功催化下卫星产业链有望估值修复",
         logic_type="event_driven"),
    dict(category="半导体/材料", keyword="玻璃基板GlassBridge技术路线争议",
         target="玻璃基板,Glass Bridge,光纤,耦合器",
         signal_content="市场对Glass Bridge等技术路径理解尚不统一(有认为替代光纤、有认为替代耦合器),不确定性导致相关个股走势分化;技术路径明朗前对此类标的保持谨慎",
         logic_type="event_driven"),
    dict(category="国产替代", keyword="日本产业链替代·人无我有",
         target="日本,材料,设备,国产替代",
         signal_content="地缘政治变化下,部分原由日本垄断的材料/设备领域国产替代紧迫性大幅提升,可能成为未来一段时间科技股挖掘的新方向,关注能实现'人无我有'突破的细分龙头",
         logic_type="logic_driven"),
    dict(category="AI/海外", keyword="OpenAI延期IPO·行业天花板未到",
         target="OpenAI,AI产业链,IPO",
         signal_content="老师解读:未上市公司通常增长见顶才选择上市,OpenAI延期说明仍处高速成长期、希望通过B端进一步验证获更高估值;对全球AI产业链是积极信号,意味行业天花板远未到来",
         logic_type="event_driven"),
]

dim3 = dict(
    date=D,
    emotion_stage="喇叭收敛震荡周期·恐高与踏空交织(科技主线高位震荡·四千点反复)",
    sentiment_description=("外围:地缘冲突升级致避险情绪升温、强美元弱黄金格局;国内政策面/消息面呈结构性分化——电子利润+103%与央视带货硬科技提振科技成长信心、"
                           "有效对冲外部地缘负面情绪;但整体仍存疑虑,主要是对科技股高估值的'恐高'与对其他板块'踏空'的焦虑;老师判恐高源于对风格切换底层逻辑的误解"
                           "(CPI转正预期降红利资产吸引力、新国九条限制微盘股炒作),资金流向高成长科技是必然结果,主线逻辑清晰、无需过度悲观"),
    trend_description="大盘四千点附近反复震荡=消化获利盘、抬高市场平均成本的必要过程,非趋势终结;关注震荡中成交量变化,缩量回调至关键支撑位往往是介入良机而非恐慌离场",
    news_catalysts="统计局工业利润+18.8%/电子+103%;央视带货功率半导体/玻纤/光纤;美伊冲突与俄乌局势;OpenAI延期IPO;玻璃基板GlassBridge争议",
    policy_news="CPI转正预期(红利资产吸引力下降);新'国九条'限制微盘股炒作;统计局工业利润数据",
    industry_logic="K型复苏:科技成长(电子)为引擎,传统周期/红利(地产/银行/白酒/养猪)缺边际利好承压",
    created_at=NOW,
    # 注：本课件未明说涨跌停家数/成交额数值 → limit_up/down、volume_trillion、trading_amount 留空(不从行情库倒灌)
)

dim4_stocks = [
    dict(date=D, stock_name="广合科技", sector="PCB",
         bull_reason="典型趋势型标的;PCB领域优质公司,回调至关键技术位后迅速反弹体现机构资金青睐;操作关键是识别回调到位信号,利用均线/前期平台作支撑低吸,博趋势延续",
         bear_reason=None, position_suggestion="回调到位低吸(趋势型)", confidence="中", source="小鲍老师", updated_at=NOW),
    dict(date=D, stock_name="亚威股份", sector="半导体设备",
         bull_reason="持有韩国GSI股份的隐性逻辑:GSI为HBM测试设备关键供应商、受益海力士等扩产计划,使亚威股份弹性较强;位置相对不高,适合作半导体设备端补充配置",
         bear_reason=None, position_suggestion="补充配置(半导体设备端)", confidence="中", source="小鲍老师", updated_at=NOW),
    dict(date=D, stock_name="川环科技", sector="液冷",
         bull_reason="液冷概念低估值优势:相较已大幅上涨同类标的处相对低位、盈亏比极佳,守住前期低点则可期待补涨",
         bear_reason="以前期低点作严格止损参考,一旦跌破则坚决离场", position_suggestion="低吸(前低为止损线)", confidence="中", source="小鲍老师", updated_at=NOW),
]

dim4_plan = dict(
    date=D,
    plan=("基调'紧扣硬科技主线、回调即加仓、严守纪律'。①继续紧扣硬科技主线,重点半导体设备/材料/先进封装,适当关注商业航天(卫星制造)脉冲机会。"
          "②'右侧交易+关键位博弈':主线题材回调企稳果断介入,消息驱动热点快进快出;反对左侧抄底弱势股('便宜不是买入理由',除非基本面逆转如涨价/技术突破)。"
          "③严格仓位管理与止损:持仓重的科技股遇大幅波动可适度减仓锁利/降敞口、但不轻易清仓离场;新开仓必设明确止损位(前低/重要均线),触发立即执行。"
          "④近期预案:若明日日韩股市低开低走A股大概率跟随调整、不宜急抄底,应等企稳;若外围修复A股有望反弹;若连续调整2-3天、优质科技股跌20%左右将是极佳二次介入机会,可周一/周二尾盘分批布局。"),
    strategy_idea="只做强势/只做有边际利好方向;科技'回调即加仓'用时间换空间;趋势标的与热点题材分治;弃火箭保卫星",
    strategy_framework=("①风格成因洞察:风格的形成与终结源于宏观环境与资金偏好共振(银行崛起=通缩避险/微盘落幕=监管流动性枯竭/科技强势=AI真实业绩爆发),"
                        "判科技见顶看供需而非市盈率。②交易时机:右侧交易+关键位博弈,主线回调企稳介入、热点快进快出;反对左侧抄底弱势股。"
                        "③纪律:接受'不完美的交易',明确赚哪部分钱并承担对应风险,止损后重新买入须基于新逻辑而非情感,频繁切策略/犹豫是亏损根源"),
    operation_advice="紧扣半导体设备/材料/先进封装,关注卫星制造脉冲;主线回调企稳介入、热点快进快出;持仓重者大幅波动适度减仓不清仓;新仓必设前低/均线止损触发即执行;连调2-3天科技跌~20%为二次介入良机,周一/周二尾盘分批",
    prediction="短期或维持震荡整理;若日韩低开低走A股跟随调整,外围修复则随之反弹;近期紧扣硬科技(半导体设备/材料/先进封装)+商业航天脉冲",
    entry_conditions="主线题材回调企稳;科技股连调2-3天跌幅~20%二次介入;前低/重要均线企稳低吸",
    exit_conditions="新开仓跌破前低/重要均线止损立即执行;持仓重者大幅波动适度减仓锁利(不轻易清仓)",
    key_stocks="广合科技,亚威股份,川环科技,亚翔集成,圣晖集成,航天工程,中国卫星",
    key_levels="止损=前期低点/重要均线;科技股二次介入参考跌幅~20%",
    risk_warnings="地缘冲突升级致避险升温与输入性通胀;日韩股市低开低走拖累A股;科技股高估值'恐高'情绪;玻璃基板技术路线未明个股分化;盲目抄底地产/白酒/养猪/银行等'价值陷阱'",
    position_guidance=("课件给分档区间——高位科技总仓控制30%-50%、低位潜伏标的10%-20%(且须基本面支撑),为分档防御性指引、非单一整体仓位成数→判 conf=low,"
                       "结构化仓位数值列(position_pct_min/max/repr/stance/conf/band)留空,详见 data/待人工复核-仓位.md。"),
    plan_window="T+1~近期",
    position_source="260628四维度训练营-总结.pdf",
    created_at=NOW,
)

PENDING_POS_MD = """
## 2026-06-28 · 260628四维度训练营-总结.pdf
- 原文摘句: 『将总仓位控制在 30%-50%,既不错过主升浪,又留有应对回撤的余地』『对于低位潜伏的标的,仓位可控制在 10%-20%,且必须是有基本面支撑的低位』
- 疑点: 仓位为分档区间(高位科技30-50% + 低位潜伏10-20%),针对不同标的类别而非单一整体仓位成数;防御性指引,跨度大、无单一可量化总仓立场 → 判 conf=low,结构化仓位数值列留空。
- 处置: dim4_trade_plan 已落 plan/strategy/operation_advice/key_stocks/risk,结构化仓位列(position_pct_min/max/repr/stance/conf/band)留空。备注:若哥哥裁定取防御档,可考虑 stance=防御/谨慎、conf=mid。
"""


def _ins(con, table, d):
    cols = [k for k, v in d.items() if v is not None]
    con.execute(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
                [d[c] for c in cols])


def main():
    if not DB.exists():
        print(f"❌ 找不到 recap.db: {DB}"); return 2
    bak = DB.with_name(DB.name + ".bak_20260629_pre260628")
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
    # 追加待人工复核-仓位.md（仓位 conf=low）
    pend = DB.parent.parent.parent / "Claude" / "Projects" / "Financial" / "烛照九阴" / "data" / "待人工复核-仓位.md"
    # 兜底：直接按已知相对结构找
    if not pend.exists():
        for cand in [Path.home() / "Documents" / "Claude" / "Projects" / "Financial" / "烛照九阴" / "data" / "待人工复核-仓位.md"]:
            if cand.exists(): pend = cand; break
    if pend.exists() and "2026-06-28 · 260628" not in pend.read_text(encoding="utf-8"):
        with open(pend, "a", encoding="utf-8") as f:
            f.write(PENDING_POS_MD)
        print(f"已追加待人工复核 → {pend}")
    else:
        print("待人工复核-仓位.md 已含 06-28 条或未找到，跳过追加")
    print("✅ 260628 入库完成（processed_kejian 请用 dedup_kejian.py record --all-new 标记）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
