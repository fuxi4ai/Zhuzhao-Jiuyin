-- ========================================
-- recap.db Schema v3.0
-- 基于两条主线重新设计
-- 2026-05-12 · 九儿
-- ========================================

-- ========================================
-- 主线1: 市场热度与情绪周期
-- 决定仓位水位和操作策略
-- ========================================

CREATE TABLE IF NOT EXISTS emotion_cycle (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT NOT NULL UNIQUE,     -- 交易日期

    -- 基础指标
    limit_up        INTEGER DEFAULT 0,        -- 涨停数
    limit_down      INTEGER DEFAULT 0,        -- 跌停数
    seal_rate       REAL DEFAULT 0,           -- 封板率
    total_volume    REAL DEFAULT 0,           -- 沪深总成交额（亿）
    up_down_ratio   REAL DEFAULT 0,           -- 涨跌家数比

    -- 优化版情绪周期评分
    emotion_score   REAL DEFAULT 0,           -- 综合评分（0-100）
    emotion_season  TEXT,                     -- 春夏秋冬（冰点/修复/主升/高潮/退潮）
    risk_appetite   TEXT,                     -- 风险偏好：高/中/低

    -- 仓位建议（由情绪周期推导）
    position_suggestion TEXT,                 -- 仓位建议：重仓/中等/轻仓/空仓

    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

-- ========================================
-- 主线2: 底层产业逻辑 vs 市场认知
-- 发现信息差，寻找超额收益
-- ========================================

-- 产业词头表（哥哥的数据库对接）
-- 未来结构：供给紧缺 → HBM → 海力士
CREATE TABLE IF NOT EXISTS industry_signals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT NOT NULL,            -- 信号日期
    category        TEXT NOT NULL,            -- 大类：技术升级/供给紧缺/需求爆发/产能瓶颈
    keyword         TEXT,                     -- 关键词：HBM/CoWoS/碳酸锂
    target          TEXT,                     -- 标的：海力士/台积电/天齐锂业
    signal_content TEXT,                     -- 信号内容：具体数据/事件
    confidence      TEXT DEFAULT 'P2',        -- 置信度：P0/P1/P2/P3
    status          TEXT DEFAULT 'new',       -- new/tracked/realized/expired

    created_at      TEXT DEFAULT (datetime('now'))
);

-- 热点板块表（每日市场在炒什么）
CREATE TABLE IF NOT EXISTS hot_sectors (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT NOT NULL,            -- 交易日期
    rank            INTEGER,                  -- 排名 1-5
    sector_name     TEXT,                     -- 板块名称
    pct_change      REAL,                     -- 板块涨幅
    ts_code         TEXT,                     -- 同花顺指数代码

    -- 分析字段
    is_industry_logic INTEGER DEFAULT 0,      -- 是否有产业逻辑支撑（0/1）
    related_signal_id INTEGER,                -- 关联的产业信号 ID

    created_at      TEXT DEFAULT (datetime('now'))
);

-- 信息差追踪表（核心）
CREATE TABLE IF NOT EXISTS information_gap (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id       INTEGER,                  -- 关联的产业信号
    date_discovered TEXT,                     -- 发现日期
    date_realized   TEXT,                     -- 市场认知日期（利好兑现）
    sector_hot_days INTEGER DEFAULT 0,        -- 对应板块连续涨了多少天
    gap_status      TEXT DEFAULT 'open',      -- open/closing/closed
    action          TEXT,                     -- 建议操作：买入/持有/减仓/清仓

    created_at      TEXT DEFAULT (datetime('now'))
);

-- ========================================
-- 辅助表
-- ========================================

-- 每日复盘摘要（简洁版）
CREATE TABLE IF NOT EXISTS daily_summary (
    date            TEXT PRIMARY KEY,
    emotion_season  TEXT,                     -- 情绪季节
    hot_sectors     TEXT,                     -- Top 5 热点板块（JSON）
    key_signals     TEXT,                     -- 关键产业信号（JSON）
    information_gap TEXT,                     -- 当前开放的信息差（JSON）
    notes           TEXT,                     -- 备注

    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

-- ========================================
-- 旧表兼容（保留但标记废弃）
-- ========================================
-- dim1_external_pricing   → 废弃，数据迁移到 emotion_cycle
-- dim2_sector_themes      → 废弃，数据迁移到 industry_signals + hot_sectors
-- dim3_sentiment_tech     → 废弃，数据迁移到 industry_signals + information_gap
-- dim4_trading_strategy   → 废弃，数据迁移到 emotion_cycle
-- recap_daily             → 废弃

-- ========================================
-- 预测者准确率追踪表（2026-05-19 新增）
-- 按人统计预测准确率，不混在一起看
-- ========================================

CREATE TABLE IF NOT EXISTS predictor_accuracy (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    predictor_name  TEXT NOT NULL,          -- 预测者：小鲍老师/九儿/...
    date            TEXT NOT NULL,          -- 预测日期
    prediction_type TEXT NOT NULL,          -- 情绪周期/涨跌方向/板块/个股
    prediction      TEXT NOT NULL,          -- 具体预测内容
    actual_result   TEXT,                   -- 实际结果
    is_correct      INTEGER,                -- 1=正确, 0=错误, NULL=待验证
    next_day_return REAL,                   -- 次日大盘涨跌幅（参考）
    notes           TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    verified_at     TEXT
);

CREATE INDEX IF NOT EXISTS idx_pa_predictor ON predictor_accuracy(predictor_name);
CREATE INDEX IF NOT EXISTS idx_pa_date ON predictor_accuracy(date);
CREATE INDEX IF NOT EXISTS idx_pa_type ON predictor_accuracy(prediction_type);

-- ========================================
-- 索引
-- ========================================
CREATE INDEX IF NOT EXISTS idx_emotion_date ON emotion_cycle(date);
CREATE INDEX IF NOT EXISTS idx_signals_date ON industry_signals(date);
CREATE INDEX IF NOT EXISTS idx_signals_category ON industry_signals(category);
CREATE INDEX IF NOT EXISTS idx_hot_date ON hot_sectors(date);
CREATE INDEX IF NOT EXISTS idx_gap_status ON information_gap(gap_status);
