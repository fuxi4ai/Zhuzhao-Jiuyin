#!/usr/bin/env python3
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from lib.logger import get_logger
logger = get_logger(__name__)
"""
执行日志工具 — 统一的数据操作日志记录
"""
import sqlite3
import json
import os
from datetime import datetime

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import config
DB_PATH = config.RECAP_DB

def get_conn():
    return sqlite3.connect(DB_PATH)

def init_log_table(conn):
    """确保 execution_log 表存在"""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS execution_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            script_name     TEXT NOT NULL,
            operation       TEXT NOT NULL,
            started_at      TEXT NOT NULL,
            ended_at        TEXT,
            status          TEXT DEFAULT 'running',
            rows_affected   INTEGER DEFAULT 0,
            details         TEXT,
            error_message   TEXT,
            triggered_by    TEXT DEFAULT 'manual',
            created_at      TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_exec_script ON execution_log(script_name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_exec_started ON execution_log(started_at)")
    conn.commit()

class ExecLogger:
    """上下文管理器：自动记录开始/结束/状态"""
    def __init__(self, script_name, operation, triggered_by="manual", conn=None):
        self.script_name = script_name
        self.operation = operation
        self.triggered_by = triggered_by
        self.conn = conn or get_conn()
        self.log_id = None
        self.started_at = None

    def __enter__(self):
        self.started_at = datetime.now().isoformat()
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO execution_log (script_name, operation, started_at, status, triggered_by)
            VALUES (?, ?, ?, 'running', ?)
        """, (self.script_name, self.operation, self.started_at, self.triggered_by))
        self.log_id = cur.lastrowid
        self.conn.commit()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        ended_at = datetime.now().isoformat()
        if exc_type:
            self.conn.execute("""
                UPDATE execution_log
                SET ended_at = ?, status = 'failed', error_message = ?
                WHERE id = ?
            """, (ended_at, str(exc_val), self.log_id))
        else:
            self.conn.execute("""
                UPDATE execution_log
                SET ended_at = ?, status = 'success'
                WHERE id = ?
            """, (ended_at, self.log_id))
        self.conn.commit()
        return False  # 不吞异常

    def update(self, rows_affected=0, details=None):
        """中途更新进度"""
        d = json.dumps(details, ensure_ascii=False) if details else None
        self.conn.execute("""
            UPDATE execution_log SET rows_affected = ?, details = ?
            WHERE id = ?
        """, (rows_affected, d, self.log_id))
        self.conn.commit()


def show_recent(n=10):
    """展示最近 N 条执行记录"""
    conn = get_conn()
    init_log_table(conn)
    cur = conn.cursor()
    cur.execute("""
        SELECT script_name, operation, started_at, status,
               rows_affected, error_message
        FROM execution_log
        ORDER BY started_at DESC
        LIMIT ?
    """, (n,))
    rows = cur.fetchall()
    logger.info(f"{'脚本'.ljust(35)} {'操作'.ljust(12)} {'开始时间'.ljust(20)} {'状态'.ljust(8)} {'行数'.rjust(6)}")
    logger.info("-" * 90)
    for r in rows:
        status_icon = {"success": "✅", "failed": "❌", "running": "⏳"}.get(r[3], "?")
        logger.info(f"{r[0].ljust(35)} {r[1].ljust(12)} {r[2].ljust(20)} {status_icon} {str(r[4] or '').rjust(6)}")
        if r[5]:
            logger.info(f"  └─ 错误: {r[5][:100]}")
    conn.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--recent", "-n", type=int, default=10, help="展示最近N条记录")
    args = parser.parse_args()
    show_recent(args.recent)
