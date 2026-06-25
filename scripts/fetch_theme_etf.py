#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""主线代表 ETF 行情拉取 → 公共 market_data.db.theme_etf_daily
（research-CC 2026-06-09；默认 Doctor 终端跑。注：『沙箱连不上 tushare』已过时——约 2026-06-11 白名单开放后沙箱经 localhost:3128 代理 + token 已可连）

分工：本脚本在 Doctor 终端用 tushare fund_daily 拉场内 ETF 日线，写入公共行情库
      market_data.db 的新表 theme_etf_daily（附加表，不动句芒既有表）。
      理想由句芒日更管线接管；过渡期 Doctor 手动跑。

用法：
  python3 scripts/fetch_theme_etf.py --from 20250101            # 全量回填
  python3 scripts/fetch_theme_etf.py --from 20260507            # 增量
  python3 scripts/fetch_theme_etf.py --dry-run                  # 只列要拉的ETF不写库

token：从 macOS Keychain(tushare_pro) 或 ~/.tushare/token 或 env TUSHARE_TOKEN 读取，不进对话/git。
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from lib.logger import get_logger
logger = get_logger(__name__)
import sqlite3, argparse, time
import config

MARKET_DB = config.MARKET_DB

# ── 主线 → 代表 ETF（单一可信源，Doctor 核实后改这里）─────────────────
# 复合主线用 list（篮子，超额等权平均）；单主线用单元素 list。
THEME_ETF = {
    "光模块/CPO/光通信/光纤": ["515880.SH"],   # 通信ETF国泰(190亿)；备515050
    "半导体/芯片/半导体材料":  ["159995.SZ"],   # 芯片ETF(254亿)
    "机器人":                 ["562500.SH"],   # 机器人ETF华夏
    "光伏":                   ["515790.SH"],   # 华泰柏瑞中证光伏产业(132亿,最大)
    "新能源电池/锂电/储能/固态": ["159566.SZ"],  # 新能源电池ETF易方达
    "电力/电网/算电协同/燃气轮机": ["159611.SZ"], # 电力ETF广发；电网备159326
    "创新药/医药/CRO":         ["159992.SZ"],   # 创新药ETF
    "军工":                   ["512660.SH"],   # 军工ETF
    "商业航天/卫星":           ["563230.SH"],   # 卫星ETF(近似,Doctor确认OK)
    "消费电子/华为/鸿蒙":       ["561600.SH"],   # 消费电子ETF
    "AI软件/应用":            ["515230.SH"],    # 软件ETF
    "白酒/消费":              ["512690.SH"],    # 酒ETF
    "券商/金融":              ["512880.SH"],    # 证券ETF
    # 大宗/金属（Doctor 2026-06-10 补锚，原覆盖洞）
    "黄金/贵金属":            ["518880.SH"],    # 黄金ETF·现货金价锚；矿业股β备159321/517520
    "稀土":                   ["516780.SH"],    # 稀土ETF·中证稀土产业；备159713
    "钨/小金属":              ["159608.SZ"],    # 稀有金属ETF(钨钼锗锂稀土)·无纯钨ETF代理
    "有色金属":               ["512400.SH"],    # 有色金属ETF·铝/铜/泛金属代理
    # 复合主线（篮子）
    "AI算力/AI硬件/科技硬件":  ["515880.SH", "159995.SZ"],  # 通信+芯片篮子
}
BENCHMARK = "510300.SH"   # 沪深300ETF（超额基准）

def all_codes():
    s = set([BENCHMARK])
    for v in THEME_ETF.values():
        s.update(v)
    return sorted(s)

def get_pro():
    import tushare as ts
    tok = _os.environ.get("TUSHARE_TOKEN")
    if not tok:
        # Keychain
        try:
            import subprocess
            tok = subprocess.check_output(
                ["security", "find-generic-password", "-s", "tushare_pro", "-w"],
                text=True).strip()
        except Exception:
            pass
    if not tok:
        p = _os.path.expanduser("~/.tushare/token")
        if _os.path.exists(p):
            tok = open(p).read().strip()
    if not tok:
        logger.error("❌ 未找到 TUSHARE_TOKEN（env / Keychain tushare_pro / ~/.tushare/token）")
        _sys.exit(1)
    ts.set_token(tok)
    return ts.pro_api()

def ensure_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS theme_etf_daily (
            trade_date TEXT,
            etf_code   TEXT,
            close      REAL,
            pct_chg    REAL,
            is_benchmark INTEGER DEFAULT 0,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (trade_date, etf_code)
        )
    """)
    conn.commit()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="from_date", default="20250101", help="起始 YYYYMMDD")
    ap.add_argument("--to", dest="to_date", default=None, help="结束 YYYYMMDD(默认今天)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    to_date = args.to_date or time.strftime("%Y%m%d")

    codes = all_codes()
    logger.info(f"待拉 ETF {len(codes)} 只 [{args.from_date}→{to_date}]: {codes}")
    if args.dry_run:
        logger.info("dry-run，仅列出，不写库"); return

    pro = get_pro()
    conn = sqlite3.connect(MARKET_DB)
    ensure_table(conn)
    total = 0
    for c in codes:
        try:
            df = pro.fund_daily(ts_code=c, start_date=args.from_date, end_date=to_date)
        except Exception as e:
            logger.error(f"  ✗ {c}: {e}"); continue
        if df is None or df.empty:
            logger.info(f"  - {c}: 无数据"); continue
        isb = 1 if c == BENCHMARK else 0
        rows = [(r.trade_date, c, float(r.close), float(r.pct_chg), isb)
                for r in df.itertuples()]
        conn.executemany(
            "INSERT OR REPLACE INTO theme_etf_daily(trade_date,etf_code,close,pct_chg,is_benchmark) "
            "VALUES (?,?,?,?,?)", rows)
        conn.commit()
        total += len(rows)
        logger.info(f"  ✓ {c}: {len(rows)} 行")
        time.sleep(0.3)   # 限频友好
    logger.info(f"\n✅ 完成，写入 {total} 行 → market_data.db.theme_etf_daily")
    conn.close()

if __name__ == "__main__":
    main()
