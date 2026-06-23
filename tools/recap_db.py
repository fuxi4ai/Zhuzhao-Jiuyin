#!/usr/bin/env python3
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import config
from lib.logger import get_logger
logger = get_logger(__name__)
"""
复盘数据库操作模块 (recap_db.py) v1.1
2026-05-07

提供四维度复盘数据库的读写接口。
"""

import sqlite3
import os
from datetime import datetime
from typing import Optional, List, Dict

DB_PATH = config.RECAP_DB


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=DELETE")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


# ─── 主表操作 ─────────────────────────────────────────────

def insert_recap(date: str, source: str = None, speaker: str = None,
                 cycle_stage: str = None, cycle_number: int = None,
                 market_summary: str = None, key_themes: str = None):
    """插入/替换主表记录"""
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO recap_daily (date, source, speaker, cycle_stage, cycle_number, market_summary, key_themes) VALUES (?,?,?,?,?,?,?)",
        (date, source, speaker, cycle_stage, cycle_number, market_summary, key_themes))
    conn.commit()
    conn.close()


def get_recap(date: str) -> Optional[dict]:
    """获取某日完整数据（含四维 + 摘要）"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM recap_daily WHERE date=?", (date,)).fetchone()
    if not row:
        conn.close()
        return None

    result = dict(row)
    for dim in ["dim1_external_pricing", "dim2_sector_themes", "dim3_sentiment_tech", "dim4_trade_plan"]:
        d = conn.execute(f"SELECT * FROM {dim} WHERE date=?", (date,)).fetchone()
        result[dim] = dict(d) if d else None

    rows = conn.execute("SELECT * FROM recap_summary WHERE date=? ORDER BY id", (date,)).fetchall()
    result["summary"] = [dict(r) for r in rows]

    g = conn.execute("SELECT * FROM recap_guide WHERE date=?", (date,)).fetchone()
    result["guide"] = dict(g) if g else None

    conn.close()
    return result


def list_dates(source: str = None) -> list:
    """列出所有交易日"""
    conn = get_conn()
    sql = "SELECT date, source, speaker FROM recap_daily ORDER BY date"
    params = []
    if source:
        sql = "SELECT date, source, speaker FROM recap_daily WHERE source=? ORDER BY date"
        params = [source]
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── 板块 & 个股 ──────────────────────────────────────────

def add_sector_alias(canonical: str, aliases: str, category: str = None):
    """添加板块标准化映射"""
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO sector_alias (canonical_name, aliases, category) VALUES (?,?,?)",
                 (canonical, aliases, category))
    conn.commit()
    conn.close()


def normalize_sector(raw_name: str) -> Optional[str]:
    """板块名称标准化：输入别名，返回标准名称"""
    conn = get_conn()
    row = conn.execute(
        "SELECT canonical_name FROM sector_alias WHERE canonical_name=? OR aliases LIKE ?",
        (raw_name, f"%{raw_name}%")).fetchone()
    conn.close()
    return row["canonical_name"] if row else None


def add_stock(code: str, name: str, aliases: str = None, sector: str = None):
    """添加个股标准化记录"""
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO stock_master (code, name, aliases, sector) VALUES (?,?,?,?)",
                 (code, name, aliases, sector))
    conn.commit()
    conn.close()


# ─── 预测验证 ─────────────────────────────────────────────

def log_prediction(recap_date: str, plan: str, verify_date: str = None,
                   result: str = None, actual_market: str = None,
                   actual_sector: str = None, notes: str = None):
    """记录一次预测验证（追加式，不覆盖）"""
    conn = get_conn()
    conn.execute(
        "INSERT INTO prediction_log (recap_date, plan, verify_date, result, actual_market, actual_sector, notes) VALUES (?,?,?,?,?,?,?)",
        (recap_date, plan, verify_date, result, actual_market, actual_sector, notes))
    conn.commit()
    conn.close()


def get_prediction_history(recap_date: str) -> list:
    """获取某日预案的所有验证记录"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM prediction_log WHERE recap_date=? ORDER BY verify_date",
        (recap_date,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── 查询 & 统计 ──────────────────────────────────────────

def query_by_sector(sector: str, limit: int = 20) -> list:
    """按板块关键词查询"""
    conn = get_conn()
    rows = conn.execute(
        """SELECT d.date, d.speaker, t.main_line, t.sector_logic, t.sectors_bullish
           FROM dim2_sector_themes t JOIN recap_daily d ON t.date = d.date
           WHERE t.main_line LIKE ? OR t.sector_logic LIKE ? OR t.sectors_bullish LIKE ?
           ORDER BY t.date DESC LIMIT ?""",
        (f"%{sector}%", f"%{sector}%", f"%{sector}%", limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def query_accuracy(speaker: str = None, limit: int = 50) -> list:
    """查询预判验证记录"""
    conn = get_conn()
    sql = """
        SELECT p.recap_date, p.plan, p.result, p.verify_date, p.actual_market, p.notes
        FROM prediction_log p
        JOIN recap_daily d ON p.recap_date = d.date
    """
    params = []
    if speaker:
        sql += " WHERE d.speaker LIKE ?"
        params.append(f"%{speaker}%")
    sql += " ORDER BY p.verify_date DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def sector_heat_rank(limit: int = 30) -> list:
    """板块热度排行（按提及次数）"""
    conn = get_conn()
    rows = conn.execute("""
        SELECT main_line, COUNT(*) as cnt,
               GROUP_CONCAT(date) as dates
        FROM dim2_sector_themes
        WHERE main_line IS NOT NULL
        GROUP BY main_line
        ORDER BY cnt DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [{"sector": r["main_line"], "count": r["cnt"], "dates": r["dates"]} for r in rows]


def emotion_distribution() -> list:
    """情绪周期分布统计"""
    conn = get_conn()
    rows = conn.execute("""
        SELECT emotion_stage, COUNT(*) as cnt
        FROM dim3_sentiment_tech
        WHERE emotion_stage IS NOT NULL
        GROUP BY emotion_stage
        ORDER BY cnt DESC
    """).fetchall()
    conn.close()
    return [{"stage": r["emotion_stage"], "count": r["cnt"]} for r in rows]


def count_by_range(start: str, end: str) -> dict:
    """日期范围统计"""
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) as cnt FROM recap_daily WHERE date BETWEEN ?",
                         (f"{start}/{end}",)).fetchone()["cnt"]

    speakers = {}
    rows = conn.execute(
        "SELECT speaker, COUNT(*) as cnt FROM recap_daily WHERE date BETWEEN ? AND ? GROUP BY speaker",
        (start, end)).fetchall()
    for r in rows:
        speakers[r["speaker"]] = r["cnt"]

    conn.close()
    return {"total": total, "by_speaker": speakers}


if __name__ == "__main__":
    logger.info("✅ recap_db.py v1.1 loaded")
    logger.info(f"DB: {DB_PATH}")

# ─── 板块标准化 ─────────────────────────────────────────────

def normalize_sector(name: str) -> Optional[str]:
    """将板块别名标准化（调用 sector_standardizer）"""
    try:
        from sector_standardizer import standardize_sector
        return standardize_sector(name)
    except Exception as e:
        logger.debug(f"板块标准化失败 {name}: {e}")
        return name


def sync_sector_mapping():
    """同步板块映射到数据库"""
    from sector_standardizer import sync_sector_alias_to_db
    sync_sector_alias_to_db()


def sync_stock_mapping():
    """同步个股库到数据库"""
    from stock_extractor import sync_stocks_to_db
    sync_stocks_to_db()

