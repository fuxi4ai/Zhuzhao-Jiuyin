#!/usr/bin/env python3
from .lib.logger import get_logger
logger = get_logger(__name__)
"""
🐲 句芒行情库 · 共享 SQLite 数据库结构
九儿创建，供句芒参考和复用
"""
import sqlite3
import os

DB_PATH = "/home/admin/openclaw/workspace/database/market/market_data.db"

def create_market_db():
    """创建行情数据库结构"""
    conn = sqlite3.connect(DB_PATH)
    
    # 1. 每日行情摘要
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_market (
            trade_date TEXT PRIMARY KEY,
            sh_close REAL,            -- 上证收盘
            sh_pct_chg REAL,          -- 上证涨跌幅(%)
            sz_close REAL,            -- 深证收盘
            sz_pct_chg REAL,          -- 深证涨跌幅(%)
            cyb_close REAL,           -- 创业板收盘
            cyb_pct_chg REAL,         -- 创业板涨跌幅(%)
            volume_trillion REAL,     -- 全市场成交量(万亿)
            limit_up INTEGER,         -- 涨停家数
            limit_down INTEGER,       -- 跌停家数
            max_consecutive INTEGER,  -- 最高连板
            north_money REAL,         -- 北向净流入(亿元)
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 2. 板块指数
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sector_daily (
            trade_date TEXT,
            sector_name TEXT,         -- 板块名称（如 AI算力、光模块）
            sector_code TEXT,         -- 板块代码（如有）
            pct_chg REAL,             -- 涨跌幅(%)
            volume REAL,              -- 成交量
            turnover REAL,            -- 成交额
            PRIMARY KEY (trade_date, sector_name)
        )
    """)
    
    # 3. 北向资金
    conn.execute("""
        CREATE TABLE IF NOT EXISTS north_flow (
            trade_date TEXT PRIMARY KEY,
            north_money REAL,         -- 北向净流入(亿元)
            south_money REAL,         -- 南向净流入(亿元)
            hgt REAL,                 -- 沪港通
            sgt REAL,                 -- 深港通
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 创建索引
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sector_date ON sector_daily(trade_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sector_name ON sector_daily(sector_name)")
    
    conn.commit()
    conn.close()
    logger.info(f"✅ market_data.db 已创建: {DB_PATH}")
    logger.info(f"   表: daily_market, sector_daily, north_flow")

if __name__ == "__main__":
    create_market_db()
