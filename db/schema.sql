-- ============================================================
-- 复盘数据库 (Post-Market Recap Database) v1.1
-- 创建时间: 2026-05-07
-- 更新: 2026-05-07 (根据头脑风暴决策)
-- ============================================================

-- ① 每日复盘主表
CREATE TABLE IF NOT EXISTS recap_daily (
    date                TEXT PRIMARY KEY,
    source              TEXT,               -- 'four_dimensions' | 'old_practice' | 'tian_ge'
    speaker             TEXT,               -- 观点发言人（可多值，逗号分隔）
    cycle_stage         TEXT,               -- 市场周期阶段
    cycle_number        INTEGER,
    market_summary      TEXT,
    key_themes          TEXT,               -- 核心关键词（逗号分隔）
    created_at          TEXT DEFAULT (datetime('now')),
    updated_at          TEXT DEFAULT (datetime('now'))
);

-- ② 维度一：外围市场定价
CREATE TABLE IF NOT EXISTS dim1_external_pricing (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    date                TEXT NOT NULL REFERENCES recap_daily(date),
    nasdaq              REAL,
    hang_seng           REAL,
    usd_cny             REAL,
    forex_swap          INTEGER,
    brent_oil           REAL,
    bitcoin             REAL,
    key_signals         TEXT,
    pricing_direction   TEXT,               -- '看多' / '看空' / '中性'
    created_at          TEXT DEFAULT (datetime('now'))
);

-- ③ 维度二：行业主线
CREATE TABLE IF NOT EXISTS dim2_sector_themes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    date                TEXT NOT NULL REFERENCES recap_daily(date),
    main_line           TEXT,               -- 当日主线
    sector_logic        TEXT,               -- 产业逻辑
    sectors_bullish     TEXT,               -- 看多板块（逗号分隔，已标准化）
    sectors_bearish     TEXT,               -- 规避板块（逗号分隔）
    yuantu_ref          TEXT,               -- 关联渊图卡片 ID（轻量引用）
    price_catalyst      TEXT,               -- 涨价/供给侧催化
    sub_themes          TEXT,               -- 支线题材
    created_at          TEXT DEFAULT (datetime('now'))
);

-- ④ 维度三：情绪/技术/消息催化
CREATE TABLE IF NOT EXISTS dim3_sentiment_tech (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    date                TEXT NOT NULL REFERENCES recap_daily(date),
    emotion_stage       TEXT,               -- 情绪周期阶段
    limit_up            INTEGER,            -- 涨停家数（可NULL）
    limit_down          INTEGER,            -- 跌停家数（可NULL）
    consecutive_boards  INTEGER,            -- 连板高度（可NULL）
    volume_trillion     REAL,               -- A股成交额（万亿）
    ma60                REAL,               -- MA60 均线
    support_level       TEXT,               -- 支撑位
    resistance_level    TEXT,               -- 压力位
    tech_indicators     TEXT,               -- 其他技术指标
    news_catalysts      TEXT,               -- 消息催化
    created_at          TEXT DEFAULT (datetime('now'))
);

-- ⑤ 维度四：交易策略
CREATE TABLE IF NOT EXISTS dim4_trade_plan (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    date                TEXT NOT NULL REFERENCES recap_daily(date),
    plan                TEXT,               -- 交易预案
    entry_conditions    TEXT,               -- 买入条件
    exit_conditions     TEXT,               -- 卖出/止损条件
    position_guidance   TEXT,               -- 仓位指引
    key_stocks          TEXT,               -- 重点观察标的
    risk_warnings       TEXT,               -- 风险提示
    key_levels          TEXT,               -- 关键锚定价位
    plan_accuracy       TEXT,               -- 验证结果: '准确' / '偏差' / '反向' / '未验证'
    actual_outcome      TEXT,               -- 实际走势回顾
    plan_window         TEXT DEFAULT 'T+1', -- 验证窗口（默认次日）
    created_at          TEXT DEFAULT (datetime('now'))
);

-- ⑥ 原文摘要表（总结类，用于全文检索）
CREATE TABLE IF NOT EXISTS recap_summary (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    date                TEXT NOT NULL REFERENCES recap_daily(date),
    source_file         TEXT,
    section             TEXT,               -- 章节标题
    content             TEXT,               -- 内容摘要
    created_at          TEXT DEFAULT (datetime('now'))
);

-- ⑦ 导读记录表（独立存放）
CREATE TABLE IF NOT EXISTS recap_guide (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    date                TEXT NOT NULL REFERENCES recap_daily(date),
    source_file         TEXT,
    keywords            TEXT,               -- 关键词（逗号分隔）
    chapters            TEXT,               -- 章节速览（JSON 或文本）
    full_summary        TEXT,               -- 全文摘要
    created_at          TEXT DEFAULT (datetime('now'))
);

-- ⑧ 板块标准化映射表
CREATE TABLE IF NOT EXISTS sector_alias (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name      TEXT NOT NULL,      -- 标准名称（如 '光模块/CPO'）
    aliases             TEXT NOT NULL,      -- 别名列表（逗号分隔，如 '光模块,CPO,AI算力,算力'）
    category            TEXT,               -- 分类: 'AI硬件' / '新能源' / '消费' / '金融' 等
    created_at          TEXT DEFAULT (datetime('now'))
);

-- ⑨ 个股标准化表
CREATE TABLE IF NOT EXISTS stock_master (
    code                TEXT PRIMARY KEY,   -- 股票代码（如 '300308'）
    name                TEXT NOT NULL,      -- 全称（如 '中际旭创'）
    aliases             TEXT,               -- 简称/别名（如 '中际,中际旭创'）
    sector              TEXT,               -- 所属板块（关联 sector_alias.canonical_name）
    created_at          TEXT DEFAULT (datetime('now'))
);

-- ⑩ 预测验证日志表（记录每次验证，非覆盖式更新）
CREATE TABLE IF NOT EXISTS prediction_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    recap_date          TEXT NOT NULL,      -- 原复盘日期
    plan                TEXT,               -- 原始预案内容
    verify_date         TEXT,               -- 验证日期
    result              TEXT,               -- 验证结果: '准确' / '偏差' / '反向'
    actual_market       TEXT,               -- 实际市场表现
    actual_sector       TEXT,               -- 实际板块表现
    notes               TEXT,               -- 备注/归因分析
    verified_by         TEXT DEFAULT 'manual',
    created_at          TEXT DEFAULT (datetime('now'))
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_recap_date ON recap_daily(date);
CREATE INDEX IF NOT EXISTS idx_dim1_date ON dim1_external_pricing(date);
CREATE INDEX IF NOT EXISTS idx_dim2_date ON dim2_sector_themes(date);
CREATE INDEX IF NOT EXISTS idx_dim2_sector ON dim2_sector_themes(main_line);
CREATE INDEX IF NOT EXISTS idx_dim3_date ON dim3_sentiment_tech(date);
CREATE INDEX IF NOT EXISTS idx_dim4_date ON dim4_trade_plan(date);
CREATE INDEX IF NOT EXISTS idx_summary_date ON recap_summary(date);
CREATE INDEX IF NOT EXISTS idx_guide_date ON recap_guide(date);
CREATE INDEX IF NOT EXISTS idx_sector_canonical ON sector_alias(canonical_name);
CREATE INDEX IF NOT EXISTS idx_stock_name ON stock_master(name);
CREATE INDEX IF NOT EXISTS idx_pred_recap ON prediction_log(recap_date);
