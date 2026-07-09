import sqlite3, json
from bisect import bisect_right
R = 'file:/tmp/recap_ro.db?mode=ro'
M = 'file:/tmp/md_ro.db?mode=ro'
def conn(u): return sqlite3.connect(u, uri=True)
def ymd(s): return str(s).replace('-','')[:8]
def load_cal(m):
    return [d for (d,) in m.execute("SELECT DISTINCT trade_date FROM stock_daily ORDER BY trade_date")]
def load_bench(m):
    # 510300 基准：theme_etf_daily
    rows = m.execute("SELECT trade_date, pct_chg FROM theme_etf_daily WHERE is_benchmark=1 ORDER BY trade_date").fetchall()
    return dict(rows)
def fwd_cum(seq, dates, start_idx, n):
    """dates: 交易日列表; seq: date->pct; 从 start_idx(含)起 n 日累计%。数据缺任一日返回 None"""
    acc = 1.0
    for d in dates[start_idx:start_idx+n]:
        p = seq.get(d)
        if p is None: return None
        acc *= (1 + p/100.0)
    if start_idx + n > len(dates): return None
    return (acc-1)*100.0
def first_td_after(cal, date_ymd):
    """信号日后的第一个交易日 index（严格 > 信号日）"""
    i = bisect_right(cal, date_ymd)
    return i if i < len(cal) else None
