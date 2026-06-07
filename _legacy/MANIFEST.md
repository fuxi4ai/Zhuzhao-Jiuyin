# _legacy · 退役脚本归档

> 2026-06-06 大修归档。以下脚本均为**一次性迁移/批处理/已被取代**，保留备查，不再维护、不参与运行。
> 现役工具见项目 `tools/`、`scripts/`、`news/`，路径统一走根目录 `config.py`。

## db/ — 旧建库/校验一次性脚本
- `extract_signals.py`、`migrate_predictor_accuracy.py`、`verify_daily_predictions.py`
  （recap.db 已建好并迁入 `Database/烛照九阴/`，建表/迁移类脚本退役。`db/*.sql` schema 仍留原位备查。）

## raw-4dims/ — 课件批量提取一次性脚本
- `batch_extract / batch21_insert / insert_batch1 / extract_batch{2,5,11,19} / extract_all_unextracted / extract_signals`
  （历史分批入库脚本。现役课件提取由 `tools/xiaobao_extractor.py` + 九儿负责，语料源已迁 `Database/烛照九阴/Raw-Recap/`。）

## scripts/ + scripts-oneoff/ — 迁移与历史榨取
- `migrate_base_tables / migrate_information_gap / migrate_print_to_logging`（schema/日志迁移，已完成）
- `pipeline_extract`（旧全量提取，被 xiaobao_extractor 取代）
- `init_market_db`（行情库已转公共数据层 `Database/Market-Data/`，由句芒建维护）
- `archive_v2_tables`（v2→v3 归档，已完成）
- `scripts-oneoff/*`（squeeze v2~v7、各 batch 提取、backfill_md/tushare/jumang —— 历史回灌，一次性）

## news/ — 退役信源（D7 决策）
- `caixin_bridge`（财新：已娱乐化、价值低，**搁置备查不删**）
- `gangtise_bridge / gangtise_recap_bridge / gangtise_*.{txt,json}`（冈底斯 GTS 桥：**弃用**）
- `recap_bridge.py`（v1，被 `recap_bridge_v2.py` 取代）
- `import_fetch_results.py`（财新深抓一次性入库）

## dragon-palace/ — 龙宫梦境（D4 退役）
- 原 openclaw 记忆提取/优化机制；职能已由 brain（note/consolidate/resume）接管，不迁入。仅存空壳，归档。

---
*单一可信源原则：现役代码只认 `config.py` 给出的 Database/ 路径。*
