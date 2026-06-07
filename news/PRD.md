# 新闻模块 · PRD v1.0

> **设计人**: 九儿
> **日期**: 2026-05-11
> **定位**: 独立的新闻获取、清洗、整理模块
> **与 recap 关系**: 新闻模块是上游数据源，recap 对接清洗后的产出

---

## 1 · 为什么需要独立模块

### 问题
| 问题 | 说明 |
|------|------|
| 新闻数据杂 | 快讯、深度、PR、广告混在一起 |
| 高度冗余 | 同一事件多信源报道，标题不同但内容相似 |
| 信息密度不均 | T 早报是碎片，专栏是框架，不能混为一谈 |
| 与复盘维度不匹配 | recap 需要结构化字段（政策/消息/涨价），但新闻是自然语言 |

### 解决
```
原始新闻 → 新闻模块（清洗/整理/结构化） → 结构化产出 → recap 数据库
```

---

## 2 · 架构

```
┌─────────────────────────────────────────────────┐
│                  新闻模块 (news)                  │
├─────────────────────────────────────────────────┤
│                                                 │
│  ┌─────────────┐   ┌─────────────┐              │
│  │  数据获取层  │──▶│  数据清洗层  │              │
│  │  Fetchers   │   │  Cleaning   │              │
│  └─────────────┘   └──────┬──────┘              │
│                           │                     │
│              ┌────────────▼────────────┐        │
│              │    新闻数据库 (SQLite)    │        │
│              │    news.db              │        │
│              └────────────┬────────────┘        │
│                           │                     │
│              ┌────────────▼────────────┐        │
│              │    结构化产出层           │        │
│              │    (供 recap 对接)       │        │
│              └─────────────────────────┘        │
└─────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────┐
│              recap 数据库 (对接层)                │
│  Dim3 消息催化 / 政策新闻 / 涨价驱动              │
└─────────────────────────────────────────────────┘
```

---

## 3 · 数据获取层

### 信源管理

| 信源 | 抓取方式 | 频率 | 置信度 | 状态 |
|------|---------|------|--------|------|
| 财新（数据通） | HTTP + Cookie | 每日盘后 | P1 | ✅ 可用 |
| 财新周刊（PRO） | 浏览器自动化 | 每周 | P1 | 🔄 待开发 |
| 冈底斯投研 | API | 盘中 + 盘后 | P1 | ✅ 已接入（端口 8766） |
| 帕米尔研究 | API (gts_summary) | 按需 | P1（含"专家"/"帕米尔"） | ⏳ 待接入 |
| gts_kb 语义知识库 | API | 按需 | P2 | ✅ 可用 |
| gts_report 国内研报 | API | 按需 | P2 | ✅ 可用 |
| 其他信源 | 待定 | 待定 | - | ⏳ 待规划 |

### 抓取规则

| 规则 | 说明 |
|------|------|
| **只抓指定范围** | 泛 AI、半导体、大宗商品、地缘政治（哥哥指定） |
| **其他行业** | 等哥哥要求再扩展 |
| **深度优先** | 深度报道 > 周刊 > 专栏 > 快讯 |
| **过滤噪音** | 排除"特别呈现"、融资快讯、产品 PR、T 早报 |

### 抓取脚本

```
news/fetchers/
├── caixin_fetcher.py      # 财新新闻抓取（已开发 v2.0）
├── caixin_pro_fetcher.py  # 财新 PRO 专享（浏览器自动化）
├── gangtise_fetcher.py    # 冈底斯投研（待开发）
└── base_fetcher.py        # 抓取器基类
```

---

## 4 · 新闻数据库（news.db）

### Schema 设计

```sql
-- ========================================
-- news.db - 新闻模块专用数据库
-- ========================================

-- 1. 原始新闻（所有抓到的原始数据）
CREATE TABLE news_raw (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL,          -- 信源: caixin/gangtise/pamir
    source_url      TEXT,                   -- 原始 URL
    title           TEXT NOT NULL,          -- 标题
    author          TEXT,                   -- 作者
    publish_time    TEXT,                   -- 发布时间
    fetch_time      TEXT NOT NULL,          -- 抓取时间
    category        TEXT,                   -- 大类: AI/半导体/大宗商品/地缘政治
    sub_category    TEXT,                   -- 子类: 政策/涨价/冲突/融资...
    content_type    TEXT,                   -- 内容类型: 深度/快讯/周刊/专栏
    raw_text        TEXT,                   -- 原始全文
    word_count      INTEGER,                -- 字数
    status          TEXT DEFAULT 'raw',     -- raw/cleaned/merged/archived

    -- 去重相关
    content_hash    TEXT UNIQUE,            -- 正文 MD5 哈希（去重用）
    title_hash      TEXT,                   -- 标题 MD5 哈希

    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

-- 2. 清洗后的新闻（去重 + 分类 + 标准化）
CREATE TABLE news_cleaned (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_ids      TEXT,                   -- 关联的 news_raw.id（JSON 数组）
    title           TEXT NOT NULL,          -- 标准化标题
    publish_time    TEXT,                   -- 发布时间
    category        TEXT NOT NULL,          -- 大类
    sub_category    TEXT,                   -- 子类
    content_type    TEXT,                   -- 内容类型
    summary         TEXT,                   -- 摘要（200 字以内）
    key_points      TEXT,                   -- 关键要点（JSON 数组）
    full_text       TEXT,                   -- 合并后的完整文本
    word_count      INTEGER,

    -- 结构化提取
    entities        TEXT,                   -- 实体提取（JSON）：公司/人物/地点
    stocks_mentioned TEXT,                  -- 提及的标的（JSON 数组）
    price_signals   TEXT,                   -- 价格信号（JSON）：涨价/跌价
    policy_signals  TEXT,                   -- 政策信号（JSON）
    sentiment       TEXT,                   -- 情绪: positive/negative/neutral

    -- 质量评分
    quality_score   REAL,                   -- 0-100，信息密度评分
    is_deep         INTEGER DEFAULT 0,      -- 是否深度内容

    created_at      TEXT DEFAULT (datetime('now'))
);

-- 3. 事件聚类（同一事件的多个报道合并）
CREATE TABLE news_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_title     TEXT NOT NULL,          -- 事件名称
    start_time      TEXT,                   -- 事件开始时间
    end_time        TEXT,                   -- 事件结束时间（NULL=持续中）
    category        TEXT NOT NULL,          -- 大类
    sub_category    TEXT,
    status          TEXT DEFAULT 'active',  -- active/closed

    -- 事件摘要
    summary         TEXT,                   -- 事件概述
    timeline        TEXT,                   -- 事件时间线（JSON）
    key_developments TEXT,                  -- 关键进展（JSON 数组）
    impact_analysis TEXT,                   -- 影响分析

    -- 关联
    related_stocks  TEXT,                   -- 关联标的（JSON 数组）
    related_sectors TEXT,                   -- 关联板块（JSON 数组）

    news_ids        TEXT,                   -- 关联的 news_cleaned.id（JSON 数组）

    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

-- 4. 信源配置
CREATE TABLE source_config (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,          -- 信源名称
    type            TEXT,                   -- http/api/browser
    base_url        TEXT,
    config          TEXT,                   -- 配置（JSON）
    credentials     TEXT,                   -- 凭证引用（不存明文）
    status          TEXT DEFAULT 'active',
    last_fetch      TEXT,                   -- 最后抓取时间
    fetch_count     INTEGER DEFAULT 0,
    created_at      TEXT DEFAULT (datetime('now'))
);

-- 5. 抓取日志
CREATE TABLE fetch_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL,
    fetch_time      TEXT NOT NULL,
    articles_found  INTEGER DEFAULT 0,
    articles_new    INTEGER DEFAULT 0,      -- 新增（去重后）
    articles_skipped INTEGER DEFAULT 0,     -- 跳过（重复/过滤）
    status          TEXT,                   -- success/partial/failed
    error_message   TEXT,
    duration_ms     INTEGER
);

-- 索引
CREATE INDEX idx_raw_category ON news_raw(category, fetch_time);
CREATE INDEX idx_raw_status ON news_raw(status);
CREATE INDEX idx_raw_hash ON news_raw(content_hash);
CREATE INDEX idx_cleaned_category ON news_cleaned(category);
CREATE INDEX idx_cleaned_time ON news_cleaned(publish_time);
CREATE INDEX idx_events_category ON news_events(category, status);
```

---

## 5 · 数据清洗层

### 清洗流程

```
原始新闻
    │
    ▼
① 去重检测
    ├── 标题 MD5 匹配 → 直接合并
    ├── 正文相似度 >80% → 合并（保留最长版本）
    └── 同事件不同信源 → 进入事件聚类
    │
    ▼
② 内容分类
    ├── 大类: AI / 半导体 / 大宗商品 / 地缘政治
    ├── 子类: 政策 / 涨价 / 冲突 / 融资 / 技术突破 / 人事...
    └── 内容类型: 深度报道 / 周刊 / 专栏 / 快讯 / PR
    │
    ▼
③ 信息密度评分
    ├── 深度报道: 80-100 分（有分析框架）
    ├── 周刊全文: 70-90 分
    ├── 专栏观点: 60-80 分
    ├── 快讯: 20-40 分（信息碎片）
    └── PR/广告: <20 分（直接丢弃）
    │
    ▼
④ 结构化提取
    ├── 实体提取: 公司名、人名、地名
    ├── 标的关联: 提及的 A 股/港股
    ├── 价格信号: "碳酸锂 20 万元"、"原油跌 9%"
    ├── 政策信号: "政治局会议"、"全面实施人工智能+行动"
    └── 情绪标注: 利好/利空/中性
    │
    ▼
⑤ 事件聚类
    ├── 同一事件的多次报道 → 合并为一个 event
    ├── 维护事件时间线
    └── 提取关键进展
    │
    ▼
清洗完成 → 写入 news_cleaned + news_events
```

### 评分规则

| 维度 | 权重 | 说明 |
|------|------|------|
| 字数 | 20% | >1000 字得分高 |
| 分析深度 | 30% | 有因果分析/框架 |
| 数据密度 | 20% | 有具体数据/指标 |
| 时效性 | 15% | 越新得分越高 |
| 信源权威 | 15% | 财新周刊 > 财新快讯 |

---

## 6 · 结构化产出（供 recap 对接）

### 产出格式

```json
{
    "date": "2026-05-11",
    "categories": {
        "AI": {
            "events": [
                {
                    "title": "AI 对宏观经济影响",
                    "summary": "AI 将大幅提高生产率，但劳动力市场冲击需平衡",
                    "impact": "positive",
                    "stocks": ["百度", "科大讯飞"],
                    "source_articles": [1, 3, 5]
                }
            ],
            "policy_signals": ["中共中央政治局：全面实施人工智能+行动"],
            "price_signals": []
        },
        "大宗商品": {
            "events": [
                {
                    "title": "阿联酋退出欧佩克",
                    "summary": "中东石油市场长期格局生变",
                    "impact": "negative",
                    "stocks": ["中国石油", "中国石化"],
                    "source_articles": [10]
                },
                {
                    "title": "碳酸锂价格分歧",
                    "summary": "迫近 20 万，但高盛预计 H2 过剩至 6.5 万",
                    "impact": "neutral",
                    "stocks": ["天齐锂业", "天华新能"],
                    "source_articles": [11]
                }
            ],
            "price_signals": [
                {"commodity": "原油", "signal": "跌 9.36%", "reason": "地缘溢价消退"},
                {"commodity": "碳酸锂", "signal": "迫近 20 万", "forecast": "H2 或降至 6.5 万"}
            ]
        },
        "地缘政治": {
            "events": [
                {
                    "title": "美伊停火谈判",
                    "summary": "伊朗要求 30 天内撤销石油制裁，特朗普不满回应",
                    "impact": "uncertain",
                    "stocks": ["恒力石化"],
                    "source_articles": [15, 16, 17]
                }
            ],
            "policy_signals": [
                "特朗普 5/13-15 访华，人民币升破 6.80",
                "沃什接任美联储主席，货币政策或重构"
            ]
        }
    }
}
```

### 与 recap 对接方式

| recap 字段 | 数据来源 | 对接方式 |
|-----------|---------|---------|
| Dim3 政策新闻 | news_events.policy_signals | SQL 查询 + 填充 |
| Dim3 消息催化 | news_events.events | SQL 查询 + 填充 |
| Dim3 涨价驱动 | news_events.price_signals | SQL 查询 + 填充 |
| 行业逻辑 | news_cleaned 中 category 匹配 | 按板块过滤 |

---

## 7 · 项目结构

```
news/
├── README.md                 # 模块说明
├── PRD.md                    # 本文档
├── db/
│   └── news.db               # SQLite 数据库
├── schema/
│   └── news_schema.sql       # 数据库建表语句
├── fetchers/
│   ├── base_fetcher.py       # 基类
│   ├── caixin_fetcher.py     # 财新抓取（v2.0 已开发）
│   └── caixin_pro_fetcher.py # 财新 PRO（待开发）
├── cleaners/
│   ├── dedup.py              # 去重
│   ├── classifier.py         # 分类
│   ├── scorer.py             # 评分
│   ├── extractor.py          # 结构化提取
│   └── event_cluster.py      # 事件聚类
├── pipeline/
│   ├── daily_pipeline.py     # 每日流水线
│   └── weekly_pipeline.py    # 周刊流水线
├── output/
│   └── structured_*.json     # 结构化产出
└── tools/
    ├── news_cli.py           # CLI 查询工具
    └── recap_bridge.py       # 对接 recap 的桥接脚本
```

---

## 8 · 开发阶段

| 阶段 | 任务 | 说明 |
|------|------|------|
| **阶段 1** | 创建 news.db + schema | 数据库结构 ✅ |
| **阶段 1** | 迁移 caixin_fetcher v2.0 到 news/ | 脚本归位 ✅ |
| **阶段 2** | 去重模块（dedup） | 标题 + 正文相似度去重 |
| **阶段 2** | 分类模块（classifier） | 大类/子类/内容类型 |
| **阶段 2** | 每日流水线 | 抓取 → 清洗 → 入库 |
| **阶段 3** | 结构化提取 | 实体/标的/价格/政策 |
| **阶段 3** | 事件聚类 | 同一事件合并 |
| **阶段 3** | recap_bridge | 对接 recap 数据库 ✅ |
| **阶段 4** | 财新 PRO 浏览器自动化 | 周刊全文获取 |
| **阶段 4** | 冈底斯投研接入 | API 对接 ✅ |

---

## 9 · 关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 数据库 | SQLite 本地 | 简单、够用、与 recap 一致 |
| 去重方式 | MD5 + 相似度 | 标题哈希快，正文相似度准 |
| 分类方式 | 规则 + 关键词 | 初期简单有效，后续可加 LLM |
| 事件聚类 | 时间窗口 + 关键词 | 同一时段同一关键词 = 同事件 |
| 与 recap 关系 | 独立库 + 桥接脚本 | 解耦，互不影响 |

---

*2026-05-11 · 九儿*
