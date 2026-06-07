# 📰 新闻模块 · INDEX

> **位置**: `projects/烛照九阴/news/`
> **版本**: v1.1
> **创建**: 2026-05-11
> **更新**: 2026-05-11 15:19
> **定位**: 独立的新闻获取、清洗、整理模块

---

## 四大护法

| 文件 | 说明 | 状态 |
|------|------|------|
| PRD.md | 产品需求文档（架构/Schema/流程） | ✅ |
| INDEX.md | 索引（本文档） | ✅ |
| STATUS.md | 运行状态 | ✅ |
| GOTCHAS.md | 错题本 | ✅ |

---

## 项目结构

```
news/
├── PRD.md                    # 产品需求文档
├── INDEX.md                  # 索引（本文档）
├── STATUS.md                 # 运行状态
├── GOTCHAS.md                # 错题本
├── schema/
│   └── news_schema.sql       # 数据库建表
├── db/
│   └── news.db               # SQLite 数据库
├── fetchers/
│   ├── caixin_bridge.py      # 财新 API Bridge（主要数据源）
│   ├── tools.json            # MCP 工具定义
│   └── requirements.txt      # 依赖
├── cleaners/
│   └── news_cleaner.py       # 清洗器（去重/分类/评分/提取）
├── tools/
│   ├── recap_bridge_v2.py        # 财新 Bridge → recap (Dim1/2/3)
│   ├── gangtise_recap_bridge.py  # 冈底斯 → recap (Dim2/3) ✅
│   └── import_fetch_results.py   # 历史抓取结果入库
└── output/                      # 结构化产出
```

---

## 数据库 Schema

| 表 | 说明 | 记录数 |
|---|------|--------|
| news_raw | 原始新闻 | 17 |
| news_cleaned | 清洗后新闻 | 17 |
| news_events | 事件聚类 | 0 |
| source_config | 信源配置 | 3 |
| fetch_log | 抓取日志 | 0 |

---

## 与主项目关系

```
caixin_bridge API → 行情/行业/热门/港股 → recap.db (Dim1/2/3)
     ↓
news.db (清洗后的新闻) → recap_bridge_v2 → recap.db (Dim3 补充)
```

---

## 抓取范围

| 类别 | 关键词 | 状态 |
|------|--------|------|
| AI 硬件 | GPU/HBM/CoWoS/光模块/散热/电源… | ✅ |
| 半导体设备 | 光刻/刻蚀/沉积/封测/量测… | ✅ |
| 大宗商品 | 原油/碳酸锂/OPEC/煤炭/能源… | ✅ |
| 地缘政治 | 美伊 / 美中 | ✅ |

---

## Bridge 接口

### 财新 Bridge（端口 8765）

| 接口 | 功能 | 状态 |
|------|------|------|
| caixin_market_overview | A 股主要指数 | ✅ |
| caixin_hot_stocks | 热门股票榜 | ✅ |
| caixin_stock_rank | A 股个股排行 | ✅ |
| caixin_industry_rank | A 股行业排行 | ✅ |
| caixin_index_rank | A 股指数排行 | ✅ |
| caixin_hk_indices | 港股指数 | ✅ |
| caixin_hk_industry | 港股行业排行 | ✅ |
| caixin_stock_news | 个股新闻 | ⚠️ |
| caixin_search | 搜索股票 | ❌ 400 |

### 冈底斯投研 Bridge（端口 8766）

| 接口 | 功能 | 置信度 | 状态 |
|------|------|--------|------|
| gts_kb | 语义知识库 | P2 | ✅ 独家供需数据 |
| gts_report | 国内研报 | P2 | ✅ 按日期检索 |
| gts_summary | 会议纪要 | P2（含"帕米尔"/"专家"→P1） | ✅ 供需纪要 |
| gts_quote | 日K行情 | P0 | ⚠️ 走 tushare pro 渠道 |
| gts_valuation | 估值分位 | - | ⚠️ 走 tushare pro 渠道 |
| gts_financial | 财务报表 | - | ⏳ 走 tushare pro 渠道 |
| gts_foreign_report | 外资研报 | P1 | 🔒 哥哥有免费渠道，不用此接口 |

---

*2026-05-11 · 九儿*
