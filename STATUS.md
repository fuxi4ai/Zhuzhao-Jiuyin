# 🕯️ 烛照九阴 · 数据库状态

> 最后更新: 2026-06-24（实测重核）
> 执行人: CC（核对真库 `Database/烛照九阴/recap.db`，只读）

---

## 数据库概况

| 项目 | 值 |
|------|------|
| **复盘库** | `Database/烛照九阴/recap.db`（**31 表 · ~4.1 MB**）|
| **公共行情库** | `Database/Market-Data/market_data.db`（句芒维护·只读；sector_daily 已退役，高低切改 theme_etf_daily）|
| **课件语料** | `Database/烛照九阴/Raw-Recap/`（**215 份**·只读第三方语料）|
| **路径入口** | 项目根 `config.py`（**单一可信源·无 MySQL**；`python3 config.py` 自检）|
| **渊图契约** | `行业研究/mapping/latest.json`（只读）|

---

## 核心表记录数（实测 2026-06-24）

| 表 | 记录数 | 说明 |
|---|--------|------|
| recap_daily | 163 | 每日复盘主表 |
| dim1_external_pricing | 132 | 外围定价 |
| dim2_sector_themes | 167 | 行业主线 |
| dim2p_supply_demand | 32 | 供需结论层（以渊图为准）|
| dim3_sentiment_tech | 164 | 情绪技术 |
| dim4_trade_plan | 179 | 交易策略 |
| dim4_stock_analysis | 248 | 重点标的（小鲍逐股）|
| emotion_cycle | **365** | 情绪周期 |
| industry_signals | 1299 | 产业信号 |
| yuantu_buy_signals | 102 | 渊图买入信号 |
| stock_tracking | 2527 | 标的级回测池（⚠ 收益列待 populate，见下）|
| processed_kejian | 215 | 课件去重台账（dedup_kejian 之主）|
| tushare_limit | 6000 | 涨跌停明细（连板/炸板源）|

---

## 工具链（现役·均经 config.py 取路径）

| 工具 | 路径 | 说明 |
|------|------|------|
| recap_cli / recap_db / recap_import | `tools/` | CLI 查询 / 库操作 keystone / 录入 |
| **dedup_kejian** | `tools/dedup_kejian.py` | 课件去重（filename+md5）·**processed_kejian 之主**（scan/record/prune）⭐ |
| xiaobao_extractor | `tools/xiaobao_extractor.py` | 小鲍课件正则提取 |
| emotion_engine_v2 / cycle_quant / cycle_compare | `tools/` | 情绪引擎 / 量化周期 / 双轨对比 |
| yuantu_client / ticker_resolver / sync_buy_signals / logic_discovery | `tools/` | 渊图消费 / 名→code / 信号同步 / 逻辑发现 |
| **标的级回测** migrate_stock_tracking_backtest / populate_signal_targets / signal_winrate_backtest | `tools/` | 炸开信号入池 → 前向超额/命中回写（详 `brain/.../2026-06-15_标的级胜率回测_PRD.md`）|
| enhance_with_jumang | `scripts/` | 行情融合（已 repoint 公共行情库）|
| ~~tushare_pipeline~~ | `scripts/_DEPRECATED_/` | 已退役（镜像表停更）|

---

## 剩余 Gap / 待办

| 项 | 说明 |
|----|------|
| **stock_tracking 收益列 0/2527** | 回测工具齐、未跑：待 Mac 跑 `populate_signal_targets → signal_winrate_backtest`（写 recap.db）→ 收益/超额/命中列落地、出分池胜率 |
| cycle_compare 双轨一致率 37.6% | 量化阶段退化，待用公共行情库重算量化分（G011 已修报错本身）|
| emotion_stage 部分空 | 2026-05 后新录入未标注情绪阶段 |
| news_events 不启用 | 课件管线落 dim1/dim2/industry_signals/recap_daily；news.db 已归档 |

---

## 兑现口径（案2 Phase1 · 2026-06-24）

closure_engine 状态机：`open→closing`（连续超额为正≥3日）→ `closed` 触发（峰值≥5% 且绝对回撤≥5pp）后**不再终态/剔除**，转 **`dormant`（暗态）**；暗态期价格再起（连续超额为正 **≥Y′=4 日** 且 自暗态低点回升 **≥Z=5pp**）→ **点亮**回 `closing`（二段），可多轮。`gap_status ∈ {open, closing, dormant, no_anchor, no_data}`（旧 `closed` 终态已降级为 dormant）。新增列 `dormant_since/relit_date/relit_count`。日报：暗态不渲染主栏/台账，仅留「暗态 N 条」计数入口。Y′/Z 由回测定值（docs/兑现回测_案二点亮扫参_20260624.md），Doctor 2026-06-24 拍板 Y′=4/Z=5pp。**信号层（渊图 thesis 变化→剔）= Phase2，未做。**

---

*STATUS.md · 2026-06-24 实测 · CC*
