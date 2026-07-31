# 🕯️ 烛照九阴 · 数据库状态

> 最后更新: **2026-07-31（北京）/ 07-30（美西·沙箱）** —— 例行自查重核
> 执行人: CC（核对真库 `Database/烛照九阴/recap.db`，**全程 `mode=ro` 只读**）
> **数据快照时点 = recap.db mtime `2026-07-30 22:02`**。若该 mtime 已变，本文数字即已过期，请重核。
>
> ⚠ **上一版的教训**：本文件 mtime 曾是 07-28，正文却写「最后更新 2026-06-24」，数字停在六周前（声称 31 表 / 4.1 MB / 课件 215 份）。**光看文件 mtime 会误判它是新的**——故此后每次重核必同时更新上面这行日期与快照时点。

---

## 数据库概况

| 项目 | 值 |
|------|------|
| **复盘库** | `Database/烛照九阴/recap.db`（**33 表 · 5.21 MB** · `integrity_check = ok` · `journal_mode = delete`）|
| **公共行情库** | `Database/Market-Data/market_data.db`（句芒维护·只读；sector_daily 已退役，高低切改 theme_etf_daily）|
| **课件语料** | `Database/烛照九阴/Raw-Recap/`（**244 份** doc/docx/pdf·只读第三方语料）·与 `processed_kejian` **逐文件名对账差集为 0**（零遗漏、零幽灵）|
| **路径入口** | 项目根 `config.py`（**单一可信源·无 MySQL**；`python3 config.py` 自检）|
| **渊图契约** | `行业研究/mapping/latest.json`（只读）|

---

## 核心表记录数（实测 **2026-07-30 22:02 快照** · 括号内为 06-24 旧值）

| 表 | 记录数 | max(date) | 说明 |
|---|--------|-----------|------|
| recap_daily | **192** (163) | 2026-07-30 | 每日复盘主表 ｜ ⚠ 该列语义是**复盘发布日**非交易日，见下 |
| dim1_external_pricing | **161** (132) | 2026-07-30 | 外围定价 |
| dim2_sector_themes | **196** (167) | 2026-07-30 | 行业主线 |
| dim2p_supply_demand | 32 (32) | 2026-06-04 | 供需结论层（以渊图为准）｜ ⚠ 新表·未回填 |
| dim3_sentiment_tech | **193** (164) | 2026-07-30 | 情绪技术 |
| dim4_trade_plan | **208** (179) | 2026-07-30 | 交易策略 |
| dim4_stock_analysis | **458** (248) | 2026-07-30 | 重点标的（小鲍逐股）｜ 🔧 07-30 新增 `conviction` 列·回填 359/458 = **78.4% 未完** |
| emotion_cycle | **393** (365) | 2026-07-30 | 情绪周期 |
| industry_signals | **1504** (1299) | 2026-07-30 | 产业信号（最大表）|
| yuantu_buy_signals | 102 (102) | 2026-07-26 | 渊图买入信号（按 KG 节奏，非日更）|
| stock_tracking | **3327** (2527) | 2026-07-30 | 标的级回测池（⚠ 收益列 populate 状态见下方 Gap）|
| hot_sectors | **277** (—) | 2026-07-30 | 每日热点板块 ｜ **07-30 回填 +241 行**（原仅 36 行·停于 05-12）|
| processed_kejian | **244** (215) | 2026-07-30 | 课件去重台账（dedup_kejian 之主）·与磁盘对账差集 0 |
| ~~tushare_limit~~ | 6000 | 冻结 20260506 | **已于 2026-07-17 就地退役** → `_deprecated_tushare_limit_20260717`；连板/炸板源改走公共 `market_data.db` |

> **⚠ `recap_daily.date` 不是交易日，是「复盘发布日」**（2026-07-31 Doctor 确认）：小鲍老师把**周五的复盘挪到周日**、连周末信息一起总结。故 192 天里周一~周四各 37–40 天、**周日 35 天、周五仅 1 天**。任何按交易日理解此列的下游逻辑都会出错。
> **⚠ `foreign_key_check` 报 44 条违规＝已知无害，勿当事故排查**：根因即上条——`dim3`/`dim4` 按盘面日期（有周五 17–18 条）而 `recap_daily` 按发布日，两套语义都对、错的是 schema 建了 FK；且 `PRAGMA foreign_keys = 0`，该约束从未生效。SQLite 不支持 `DROP CONSTRAINT`，重建表风险大于收益 → **只记录不动 schema**。

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
| **日报受益公司着色切渊图 region**（下一步） | 现 `gen_daily_report.py` 靠硬编码 `TAIWAN_BENE`(13)/`FOREIGN_BENE` 上色（台=青绿`#1f8a7a`/外=樱粉`#d76a92`/中港=蓝）；渊图已建 `properties.region`(中/港/台/其他·主上市地口径·2026-06-30 回填483/待核验3)。下一步改报告读渊图 region 替换两套硬编码集，去维护负担（新台企不必再手补 `TAIWAN_BENE`）。读法参 `tools/yuantu_client.py` |
| **stock_tracking 收益列**（原记 0/2527） | 回测工具齐：待 Mac 跑 `populate_signal_targets → signal_winrate_backtest`（写 recap.db）→ 收益/超额/命中列落地、出分池胜率。⚠ **分母已变 2527 → 3327**（2026-07-31 实测），收益列填充率本次未核 |
| **`dim4_stock_analysis.conviction` 回填未收口**（2026-07-31 新增） | 07-30 手术新增该列并逐日回填，现 **359/458 = 78.4%**，缺 **13 个交易日 / 99 行**：`06-30 ~ 07-14`（连续 11 个交易日）+ `07-22` + `07-26`。缺口**按日全有或全无**，说明是逐日重跑解析填的、那 13 天还没轮到。⚠ 备份名作 `prec2拆列`，但 `conviction` **并非**从 `confidence` 拆出（后者全库恒为 `P2` 信源级别标记，前者是信念度 高208/中151），二者语义无关——是**新增语义列** |
| cycle_compare 双轨一致率 37.6% | 量化阶段退化，待用公共行情库重算量化分（G011 已修报错本身）|
| emotion_stage 部分空 | 2026-05 后新录入未标注情绪阶段 |
| news_events 不启用 | 课件管线落 dim1/dim2/industry_signals/recap_daily；news.db 已归档 |

---

## 兑现口径（案2 Phase1 · 2026-06-24）

closure_engine 状态机：`open→closing`（连续超额为正≥3日）→ `closed` 触发（峰值≥5% 且绝对回撤≥5pp）后**不再终态/剔除**，转 **`dormant`（暗态）**；暗态期价格再起（连续超额为正 **≥Y′=4 日** 且 自暗态低点回升 **≥Z=5pp**）→ **点亮**回 `closing`（二段），可多轮。`gap_status ∈ {open, closing, dormant, no_anchor, no_data}`（旧 `closed` 终态已降级为 dormant）。新增列 `dormant_since/relit_date/relit_count`。日报：暗态不渲染主栏/台账，仅留「暗态 N 条」计数入口。Y′/Z 由回测定值（docs/兑现回测_案二点亮扫参_20260624.md），Doctor 2026-06-24 拍板 Y′=4/Z=5pp。**信号层（渊图 thesis 变化→剔）= Phase2，未做。**

---

## 日报改动记录（gen_daily_report.py）

- **2026-06-30**：① 受益公司国别上色——台企=青绿 `#1f8a7a`（`TAIWAN_BENE` 13 家·渊图 .TW 命中 8+desc 坐实 5）/外企=樱粉 `#d76a92`/中港=蓝；②「机会提示」价格闸**分层**——中期 `e20>0`（月度趋势确认）且 短期 `e5>0`（5 日新鲜启动），卡片加显「5日/20日」双窗；③ 秋色 hero 字形 `#8b6f32`→提亮金黄 `#bd9a43`（+glow 同步）。⚠ `TAIWAN_BENE`/`FOREIGN_BENE` 为**写死白名单**，新台企/外企受益公司需手补——待上「切渊图 region」TODO 收口。

---

*STATUS.md · **2026-07-31 例行自查重核**（数据快照 = recap.db mtime 07-30 22:02）· CC ｜ 历史：2026-06-24 首测 → 06-30 补日报改动+region TODO → 07-28 全金融审查（见下方勘误追记）→ 07-31 正文数字重写*

---

## 勘误追记（2026-07-28 全金融审查·实测）

> **⚠ 本节数字已被 2026-07-31 重核取代，保留作审计留档，勿再引用其计数。**
> **两次做法不同，特此交代**：07-28 那次选择「**加追记、不改正文**」（见本节末「不改上文历史内容·留档」）；**07-31 这次选择直接重写正文数字**，因为「正文旧 + 追记新」的结构会让读者按阅读顺序先拿到错数，而多数人不会翻到文末。若日后再核，**请继续重写正文 + 在头部更新快照时点**，别再叠第三层追记——三层时间戳并存正是本次要收拾的乱象。
> 口径提示：本节「recap 对象 **34**」是**含 `sqlite_sequence`** 的计数；正文的 **33 表**不含它，两者不矛盾。

- 本文件主体为 2026-06-24 快照，**多项计数已过期**：recap 对象实测 **34**（原写 31）；`stock_tracking` 实测 **3089** 行（原写 2527，回写列仍 0/3089）；`emotion_cycle` 实测 **390** 行。〔07-31 复核：`stock_tracking` 已 **3327**、`emotion_cycle` 已 **393**〕
- 停更表（僵尸）13 张混在活表中：daily_summary/hot_sectors/predictor_accuracy(停05-12)、information_gap(停05-05)、cycle_quant/cycle_comparison(停03月)、bt_xiaobao_pos_3d(停05-06)、execution_log(停05-19)、dim2p_supply_demand(单日)、prediction_log/recap_guide/recap_summary(0行)、_deprecated×4——归档/标注待裁。
- 全量现状以 `AI4ME/CC-全金融项目情报审查-20260728.md` 为准；本追记不改上文历史内容（留档）。
