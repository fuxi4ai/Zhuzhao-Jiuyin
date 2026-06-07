-- ========================================
-- news.db Schema v1.0
-- 新闻模块专用数据库
-- 2026-05-11 · 九儿
-- ========================================

-- 1. 原始新闻（所有抓到的原始数据）
CREATE TABLE IF NOT EXISTS news_raw (
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
    word_count      INTEGER DEFAULT 0,      -- 字数
    status          TEXT DEFAULT 'raw',     -- raw/cleaned/merged/archived

    -- 去重相关
    content_hash    TEXT UNIQUE,            -- 正文 MD5 哈希
    title_hash      TEXT,                   -- 标题 MD5 哈希

    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

-- 2. 清洗后的新闻（去重 + 分类 + 标准化）
CREATE TABLE IF NOT EXISTS news_cleaned (
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
    word_count      INTEGER DEFAULT 0,

    -- 结构化提取
    entities        TEXT,                   -- 实体提取（JSON）
    stocks_mentioned TEXT,                  -- 提及的标的（JSON 数组）
    price_signals   TEXT,                   -- 价格信号（JSON）
    policy_signals  TEXT,                   -- 政策信号（JSON）
    sentiment       TEXT DEFAULT 'neutral', -- positive/negative/neutral

    -- 质量评分
    quality_score   REAL DEFAULT 0,         -- 0-100
    is_deep         INTEGER DEFAULT 0,      -- 是否深度内容

    created_at      TEXT DEFAULT (datetime('now'))
);

-- 3. 事件聚类（同一事件的多个报道合并）
CREATE TABLE IF NOT EXISTS news_events (
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
CREATE TABLE IF NOT EXISTS source_config (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    type            TEXT,                   -- http/api/browser
    base_url        TEXT,
    config          TEXT,                   -- JSON 配置
    credentials     TEXT,                   -- 凭证引用
    status          TEXT DEFAULT 'active',
    last_fetch      TEXT,
    fetch_count     INTEGER DEFAULT 0,
    created_at      TEXT DEFAULT (datetime('now'))
);

-- 5. 抓取日志
CREATE TABLE IF NOT EXISTS fetch_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL,
    fetch_time      TEXT NOT NULL,
    articles_found  INTEGER DEFAULT 0,
    articles_new    INTEGER DEFAULT 0,
    articles_skipped INTEGER DEFAULT 0,
    status          TEXT,                   -- success/partial/failed
    error_message   TEXT,
    duration_ms     INTEGER
);

-- ========================================
-- 索引
-- ========================================
CREATE INDEX IF NOT EXISTS idx_raw_category ON news_raw(category, fetch_time);
CREATE INDEX IF NOT EXISTS idx_raw_status ON news_raw(status);
CREATE INDEX IF NOT EXISTS idx_raw_hash ON news_raw(content_hash);
CREATE INDEX IF NOT EXISTS idx_raw_source_time ON news_raw(source, fetch_time);
CREATE INDEX IF NOT EXISTS idx_cleaned_category ON news_cleaned(category);
CREATE INDEX IF NOT EXISTS idx_cleaned_time ON news_cleaned(publish_time);
CREATE INDEX IF NOT EXISTS idx_cleaned_quality ON news_cleaned(quality_score DESC);
CREATE INDEX IF NOT EXISTS idx_events_category ON news_events(category, status);
CREATE INDEX IF NOT EXISTS idx_events_time ON news_events(start_time);

-- ========================================
-- 初始信源配置
-- ========================================
INSERT INTO source_config (name, type, base_url, config, status)
VALUES
    ('财新（数据通）', 'http', 'https://www.caixin.com',
     '{"cookie_file": "credentials/cookies.json", "categories": ["AI", "半导体", "大宗商品", "地缘政治"]}',
     'active'),
    ('财新周刊（PRO）', 'browser', 'https://cxdata.caixin.com',
     '{"requires_login": true, "categories": ["AI", "半导体", "大宗商品", "地缘政治"]}',
     'pending'),
    ('冈底斯投研', 'api', 'https://open.gelonghui.com',
     '{"api_key_ref": "vault:gangtise"}',
     'pending');
