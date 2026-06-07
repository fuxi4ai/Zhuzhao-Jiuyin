-- 执行日志表 — 记录每次数据操作的元数据
-- 2026-05-19 · 九儿

CREATE TABLE IF NOT EXISTS execution_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    script_name     TEXT NOT NULL,          -- 脚本名称
    operation       TEXT NOT NULL,          -- 操作类型：extract/load/verify/backfill
    started_at      TEXT NOT NULL,          -- 开始时间
    ended_at        TEXT,                   -- 结束时间
    status          TEXT DEFAULT 'running', -- running/success/failed
    rows_affected   INTEGER DEFAULT 0,      -- 影响行数
    details         TEXT,                   -- JSON 详情
    error_message   TEXT,                   -- 错误信息
    triggered_by    TEXT DEFAULT 'manual',  -- manual/cron/heartbeat
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_exec_script ON execution_log(script_name);
CREATE INDEX IF NOT EXISTS idx_exec_started ON execution_log(started_at);
CREATE INDEX IF NOT EXISTS idx_exec_status ON execution_log(status);
