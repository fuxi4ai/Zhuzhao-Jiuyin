# 🕯️ 烛照九阴 · 数据库状态

> 最后更新: 2026-06-06（大修实测）
> 执行人: CC（核对真库 `Database/烛照九阴/recap.db`）

---

## 数据库概况

| 项目 | 值 |
|------|------|
| **复盘库** | `Database/烛照九阴/recap.db`（2.2 MB，29 表）|
| **新闻库** | `Database/烛照九阴/news.db`（155 KB）|
| **公共行情库** | `Database/Market-Data/market_data.db`（207 MB，121.9 万行，句芒维护·只读）|
| **课件语料** | `Database/烛照九阴/Raw-Recap/`（206 份，只读第三方语料）|
| **数据范围** | recap_daily 2025-10-14 ~ 2026-06-03 |
| **路径入口** | 项目根 `config.py`（单一可信源；`python3 config.py` 自检）|

> 注：旧 `jumang_market.db` 副本已确证漂移（118.7万 < 121.9万），D5 作废；统一用公共行情源。

---

## 核心表记录数（实测 2026-06-06）

| 表 | 记录数 | 说明 |
|---|--------|------|
| recap_daily | 152 | 每日复盘主表 |
| dim3_sentiment_tech | 153 | 情绪技术主表 |
| dim2_sector_themes | 156 | 行业主线 |
| dim2p_supply_demand | 32 | 供需结论层（以渊图为准，带渊图置信度）|
| dim4_trade_plan | 145 | 交易策略 |
| dim4_stock_analysis | 182 | 重点标的 |
| dim1_external_pricing | 121 | 外围定价 |
| cycle_quant | 103 | 量化情绪周期 |
| emotion_cycle | 106 | 情绪周期 |
| industry_signals | 1231 | 产业信号（统一 P2×0.7）|
| predictor_accuracy | 82 | 预测者准确率 |
| tushare_limit / index / north | 6000 / 539 / 301 | 行情回填 |

**来源分布**: four_dimensions 132 · 小鲍复盘课件 19 · tushare 1

---

## dim3_sentiment_tech 填充率（153 条，实测）

| 字段 | 填充率 |
|------|--------|
| limit_up | 93% |
| limit_down | 92% |
| consecutive_boards | 90% |
| volume_trillion | 85% |
| emotion_stage | 81% |
| news_catalysts | 74% |
| industry_logic | 73% |

---

## 工具链（现役，均经 config.py 取路径）

| 工具 | 路径 | 说明 |
|------|------|------|
| recap_cli | `tools/recap_cli.py` | CLI 查询（12 命令）⭐ |
| recap_db | `tools/recap_db.py` | 数据库操作模块（keystone）|
| recap_import | `tools/recap_import.py` | 快速录入 |
| xiaobao_extractor | `tools/xiaobao_extractor.py` | 小鲍课件提取 ⭐（D7 现役）|
| cycle_quant | `tools/cycle_quant.py` | 量化情绪周期 |
| cycle_compare | `tools/cycle_compare.py` | 双轨对比（⚠ 见 GOTCHAS G011）|
| sector_standardizer / stock_extractor / logic_discovery | `tools/` | 板块标准化 / 个股 / 逻辑发现 |
| enhance_with_jumang | `scripts/enhance_with_jumang.py` | 行情融合（已 repoint 公共行情库）|
| tushare_pipeline / stock_stats / exec_logger | `scripts/` | 行情回填 / 统计 / 执行日志 |
| recap_bridge_v2 / news_cleaner | `news/` | 新闻入库桥 / 清洗 |
| **yuantu_client** | `tools/yuantu_client.py` | 渊图消费客户端（只读 latest.json 契约）⭐新 |
| **ticker_resolver** | `tools/ticker_resolver.py` | 公司名→ts_code（覆盖待句芒 stock_basic）⭐新 |
| **sync_buy_signals** | `tools/sync_buy_signals.py` | 渊图派生买入信号同步→ yuantu_buy_signals ⭐新 |
| logic_discovery | `tools/logic_discovery.py` | `hot`=渊图派生买入信号；`echo`=小鲍第二印证 |
| backtest_yuantu_signals | `scripts/backtest_yuantu_signals.py` | 买入信号受益标的回测 ⭐新 |

---

## 剩余 Gap / 待办

| 项 | 说明 |
|----|------|
| news_events 表 = 0 | 新闻事件层尚未落数据（news_raw/cleaned 各 17）|
| ~~cycle_compare 报错~~ | ✅ G011 已修（补回 compare_cycles/normalize_stage）。但量化阶段退化（85 条 83 判冰点），双轨一致率仅 37.6%，待用公共行情库重算量化分 |
| emotion_stage 29 条空 | 多为 2026-05 后新录入未标注情绪阶段 |
| __pycache__ 残留 | 云同步 FUSE 挂载禁止删除旧 .pyc，已由 .gitignore 屏蔽，无害 |

---

*STATUS.md · 2026-06-06 · CC*
