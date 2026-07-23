#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mac 原生 · 每日行情落库 编排器（launchd 入口）
-------------------------------------------------------------
根治：沙箱经 FUSE 整库写回丢大表(stock_daily)导致日报隔天退回。
在本机原生文件系统上按序落 market_data.db，写入即 durable。

为什么是 .py 而不是 .sh：launchd 执行的顶层程序即 TCC(完全磁盘访问) 的授权主体。
用 bash 跑则主体是 /bin/bash（未授 FDA → 写 ~/Documents 被拦）；改用 python3.13
直接跑，主体就是已授 FDA 的 python3.13，整条链（含它 spawn 的 python 子进程）都覆盖。

由 launchd (com.zhuzhao.marketdata) 周一~五 02:30(本地时区) 触发；也可手动：
    /Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13 \
        ops/mac_daily_marketdata.py

失败可见性铁律：任一步非零退出 → 日志标 ❌ 且本程序退出码非 0，绝不静默。
"""
import os, sys, subprocess
from datetime import datetime, timedelta

PY  = sys.executable                                   # 当前 python3.13（已授 FDA）
HOME = os.path.expanduser("~")
ZZ  = os.path.join(HOME, "Documents/Claude/Projects/Financial/烛照九阴")
JQ  = os.path.join(HOME, "Documents/Claude/Projects/Financial/剑酒青丘/infrastructure/取数工具")
DB  = os.path.join(HOME, "Documents/Database/Market-Data/market_data.db")
LOGDIR = os.path.join(ZZ, "logs")
os.makedirs(LOGDIR, exist_ok=True)
LOG    = os.path.join(LOGDIR, f"mac_marketdata_{datetime.now():%Y%m%d}.log")
STATUS = os.path.join(ZZ, "ops", ".last_run_status")

# 五表增量起点：回看 7 天（INSERT OR IGNORE 幂等，重叠无害）
FROM = (datetime.now() - timedelta(days=7)).strftime("%Y%m%d")

_logf = open(LOG, "a", encoding="utf-8", buffering=1)
def log(msg):
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S %Z}] {msg}"
    print(line, flush=True)
    _logf.write(line + "\n")

def run(name, args, cwd):
    log(f"▶ {name}")
    try:
        p = subprocess.run([PY] + args, cwd=cwd, stdout=_logf, stderr=subprocess.STDOUT)
    except Exception as e:
        log(f"❌ {name} 无法启动：{e}")
        return False
    if p.returncode == 0:
        log(f"✅ {name} 完成")
        return True
    log(f"❌ {name} 失败 (exit {p.returncode})（详见上方日志）")
    return False

def main():
    log("==================== Mac 原生行情落库 开始 ====================")
    log(f"python={PY}")
    log(f"五表 --from={FROM}（回看 7 天，去重幂等）")
    ok = True
    # ① 公共层锚点大表（FUSE 下最易丢的就是它）
    ok &= run("stock_daily 落库", [os.path.join(ZZ, "ops/ingest_stock_daily.py")], ZZ)
    # ② 句芒派生（只填空不覆盖）
    ok &= run("aggregate_derived", [os.path.join(JQ, "aggregate_derived.py")], JQ)
    ok &= run("fill_index_north",  [os.path.join(JQ, "fill_index_north.py")], JQ)
    # ③ 烛照五表
    ok &= run("theme_etf",    [os.path.join(ZZ, "scripts/fetch_theme_etf.py"),     "--from", FROM], ZZ)
    ok &= run("market_amount",[os.path.join(ZZ, "scripts/fetch_market_amount.py"), "--from", FROM], ZZ)
    ok &= run("limit_list",   [os.path.join(ZZ, "scripts/fetch_limit_list.py"),    "--from", FROM], ZZ)
    ok &= run("margin",       [os.path.join(ZZ, "scripts/fetch_margin.py"),        "--from", FROM], ZZ)
    ok &= run("intl_index",   [os.path.join(ZZ, "scripts/fetch_intl_index.py")], ZZ)
    ok &= run("kr_stocks",    [os.path.join(ZZ, "scripts/fetch_kr_stocks.py")], ZZ)

    # ④ 收尾：核各表 max 落日志
    log("---- 各表 MAX(trade_date) ----")
    try:
        import sqlite3
        con = sqlite3.connect(f"file:{DB}?mode=ro&immutable=1", uri=True)
        for t in ["stock_daily","daily_market","theme_etf_daily","market_amount_daily",
                  "limit_list_daily","margin_daily","us_anchor_daily","intl_index_daily"]:
            try:
                log(f"  {t:22s} {con.execute(f'SELECT MAX(trade_date) FROM {t}').fetchone()[0]}")
            except Exception as e:
                log(f"  {t:22s} ERR {e}")
        con.close()
    except Exception as e:
        log(f"  收尾核对失败：{e}")

    stamp = f"{datetime.now():%Y-%m-%d %H:%M:%S %Z}"
    if ok:
        log("==================== 全部完成 · 无 ❌ ====================")
        open(STATUS, "w").write(f"OK {stamp}\n")
        return 0
    log("==================== 完成但有 ❌ · 见日志 ====================")
    open(STATUS, "w").write(f"FAIL {stamp}\n")
    return 1

if __name__ == "__main__":
    sys.exit(main())
