# 🕯️ 烛照九阴 · 项目索引

> **项目**: 烛照九阴（复盘工作项目 · 烛阴/九儿）
> **路径**: `Claude/Projects/Financial/烛照九阴/`
> **最后更新**: 2026-06-06（大修）

---

## 📂 目录结构（现役）

```
烛照九阴/
├── config.py              ← 路径单一可信源（所有脚本经此取库路径）⭐ 新
├── PRD.md / INDEX.md / README.md / STATUS.md / GOTCHAS.md / 外部资源对接.md
├── tools/                 ← 日常工具（均 import config）
│   ├── recap_db.py        # 数据库操作模块（keystone）
│   ├── recap_cli.py       # CLI 查询（12 命令）⭐
│   ├── recap_import.py    # 快速录入
│   ├── xiaobao_extractor.py  # 小鲍课件提取（D7 现役）⭐
│   ├── cycle_quant.py / cycle_compare.py  # 量化周期 / 双轨对比
│   ├── sector_standardizer.py / stock_extractor.py / logic_discovery.py
│   └── demo.py
├── scripts/               ← 行情/统计/维护
│   ├── enhance_with_jumang.py  # 行情融合（→ 公共行情库）
│   ├── tushare_pipeline.py     # 行情回填
│   ├── stock_stats.py / exec_logger.py
├── news/                  ← 新闻模块（详见 news/INDEX.md）
│   ├── tools/recap_bridge_v2.py   # 新闻→recap 桥（现役）
│   ├── cleaners/news_cleaner.py   # 清洗
│   └── schema/news_schema.sql
├── lib/logger.py          ← 统一日志
├── credentials/           ← 凭证读取（vault：env 优先；token 实存 Database/.env）
├── db/                    ← 仅留 schema 参考（*.sql）；旧 .py 已归档
├── data/                  ← JSON 数据源（old_practice / signals 等）
├── raw/4-dims/            ← 历史课件 markdown（语料正源已迁 Database/Raw-Recap）
├── docs/                  ← 设计文档（15 份，见下）
└── _legacy/               ← 退役脚本归档（37 个，见 _legacy/MANIFEST.md）⭐ 新
```

> **数据不在项目内**：recap.db / news.db / market_data.db 全部住 `Database/`（公共数据层，单一可信源）。

---

## 📊 数据库快照（实测 2026-06-06）

| 表 | 记录数 |
|---|--------|
| recap_daily | 152 |
| dim3_sentiment_tech | 153 |
| dim2_sector_themes | 156 |
| dim4_stock_analysis | 182 |
| dim4_trade_plan | 145 |
| dim1_external_pricing | 121 |
| cycle_quant | 103 |
| industry_signals | 1231 |

**数据范围**: 2025-10-14 ~ 2026-06-03 · **库**: `Database/烛照九阴/recap.db`（29 表）

---

## 📖 docs/ 设计文档（15 份）

复盘数据库架构 · 复盘数据要素提炼 · 每日复盘表模板 · HTML报告模块设计 · 数据遗漏分析 ·
schema迁移方案 · 架构调整方案-v3 · 数据置信度 · 预测者准确率体系 · 产业逻辑发现模块 ·
九儿×句芒-行情库对接需求 · 复盘数据库-外部资源对齐 · 复盘数据库-错题本 · 龙宫梦境设计理念(已退役) · INDEX

---

## 🔗 外部依赖（详见 外部资源对接.md）

| 资源 | 状态 |
|------|------|
| 公共行情库 market_data.db | ✅ 句芒维护，只读引用 |
| tushare pro | ✅ token 在 `Database/.env` |
| 渊图（行业研究） | ✅ CC 正源，烛阴只读引用（产业逻辑主从倒置）|
| 新闻信源 | ✅ 单源=小鲍课件（P2）；财新搁置、冈底斯弃用（D7）|

---

*INDEX.md · 2026-06-06 · CC*
