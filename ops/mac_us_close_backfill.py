#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mac 原生 · 美股收盘后补数班 编排器（launchd 入口）
-------------------------------------------------------------
解决什么：日更主班 com.zhuzhao.marketdata 触发在美股收盘之前，
所以它取到的美股腿永远是「隔夜/盘中」读数，us_anchor_daily 结构性晚一天。
本班排在**美股完整收盘之后**，把当日收盘价补进公共行情库。

为什么在 Mac 原生跑而不在 Cowork 沙箱：
  沙箱经 FUSE 直写挂载盘真盘是 GOTCHAS G019 明令禁止的（recap.db 曾被写坏且
  quick_check 漏报），config.connect_write 就是为此立的护栏。原生路径
  (/Users/...) 护栏放行，写入即 durable。2026-08-01 补数班迁本机即为此。

为什么是 .py 而不是 .sh：launchd 执行的顶层程序即 TCC(完全磁盘访问) 的授权主体。
用 bash 跑则主体是 /bin/bash（未授 FDA → 写 ~/Documents 被拦）；改用 python3.13
直接跑，主体就是已授 FDA 的 python3.13，整条链（含它 spawn 的 python 子进程）都覆盖。
——与主班 mac_daily_marketdata.py 同款理由，勿改回 .sh。

由 launchd (com.zhuzhao.usclose) 周一~五 美股收盘后触发；也可手动：
    /Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13 \
        ops/mac_us_close_backfill.py

铁律（与 Cowork 版补数班 SKILL 一致）：
  ① 绝不编数。脚本自带盘中守卫（纯数据驱动、不看系统钟）；守卫判定末根是盘中
     快照就丢弃 → 本班少写一天，下一班 --from=max+1 自愈。宁可少一天，不可假一天。
  ② 本编排器不改任何取数脚本、不改任何判定逻辑，只调现成脚本 + 读库核对。
  ③ 失败可见：任一步非零退出 → 日志标 ❌ 且本程序退出码非 0，绝不静默。
  ④ 只碰 us_anchor_daily / intl_index_daily 两张表，不碰 recap.db、不生成日报。
"""
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta

PY = sys.executable                                    # 当前 python3.13（已授 FDA）
HOME = os.path.expanduser("~")
ZZ = os.path.join(HOME, "Documents/Claude/Projects/Financial/烛照九阴")
DB = os.path.join(HOME, "Documents/Database/Market-Data/market_data.db")
LOGDIR = os.path.join(ZZ, "logs")
os.makedirs(LOGDIR, exist_ok=True)
LOG = os.path.join(LOGDIR, f"mac_usclose_{datetime.now():%Y%m%d}.log")
STATUS = os.path.join(ZZ, "ops", ".last_run_status_usclose")

# 验收基准：美股锚 19 票、intl_index 美股腿 5 条。
# 这两个数字是**验收标准**不是取数清单——取哪些票由脚本自己的配置决定，
# 改票池时记得同步这里，否则本班会把「正常扩票」误报成 ❌。
EXPECT_ANCHOR_N = 19
US_LEG_CODES = {"NASDAQ", "SPCX", "NVDA", "AVGO", "LITE"}
US_LEG_KINDS = ("overnight", "us_stock")

_logf = open(LOG, "a", encoding="utf-8", buffering=1)


def log(msg):
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S %Z}] {msg}"
    print(line, flush=True)
    _logf.write(line + "\n")


def run(name, args, cwd=ZZ):
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


def ro():
    """只读连接。探水位/核对一律走只读，避免本编排器自身持写锁。"""
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)


def next_iso(yyyymmdd):
    """库里存 'YYYYMMDD'，脚本 --from 吃 ISO 'YYYY-MM-DD'。取 max 的次日。
    不跳周末——取数脚本按区间拉、INSERT OR IGNORE 幂等，多给一两天无害，
    少给才会漏。max 为空则回看 7 天兜底。"""
    if not yyyymmdd:
        return (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    return (datetime.strptime(str(yyyymmdd), "%Y%m%d") + timedelta(days=1)).strftime("%Y-%m-%d")


def probe():
    """返回 (us_anchor_max, 美股腿_max)。"""
    con = ro()
    try:
        a = con.execute("SELECT MAX(trade_date) FROM us_anchor_daily").fetchone()[0]
        q = "SELECT MAX(trade_date) FROM intl_index_daily WHERE kind IN (?,?)"
        b = con.execute(q, US_LEG_KINDS).fetchone()[0]
        return a, b
    finally:
        con.close()


def verify(before_anchor, before_leg):
    """回读核对——本班的验收，不能省。返回 True 表示无硬伤。"""
    ok = True
    con = ro()
    try:
        # —— 美股锚 ——
        mx = con.execute("SELECT MAX(trade_date) FROM us_anchor_daily").fetchone()[0]
        n = con.execute(
            "SELECT COUNT(*) FROM us_anchor_daily WHERE trade_date=?", (mx,)).fetchone()[0]
        moved = "推进" if str(mx) != str(before_anchor) else "未推进"
        log(f"  us_anchor_daily 最新日 {mx}（{moved}） 票数 {n}/{EXPECT_ANCHOR_N}")
        if n != EXPECT_ANCHOR_N:
            miss = [r[0] for r in con.execute(
                "SELECT DISTINCT ticker FROM us_anchor_daily WHERE ticker NOT IN "
                "(SELECT ticker FROM us_anchor_daily WHERE trade_date=?)", (mx,))]
            log(f"  ❌ 最新日票数不足，疑缺：{miss}")
            ok = False

        # —— intl_index 美股腿 ——
        q = "SELECT MAX(trade_date) FROM intl_index_daily WHERE kind IN (?,?)"
        lmx = con.execute(q, US_LEG_KINDS).fetchone()[0]
        got = {r[0] for r in con.execute(
            "SELECT code FROM intl_index_daily WHERE trade_date=? AND kind IN (?,?)",
            (lmx,) + US_LEG_KINDS)}
        moved = "推进" if str(lmx) != str(before_leg) else "未推进"
        log(f"  intl_index 美股腿 最新日 {lmx}（{moved}） 到齐 {sorted(got)}")
        if US_LEG_CODES - got:
            log(f"  ❌ 美股腿缺：{sorted(US_LEG_CODES - got)}")
            ok = False

        # —— 两腿对齐提醒（不判 ❌：节假日/单腿停更都可能造成暂时错位）——
        if str(mx) != str(lmx):
            log(f"  ⚠ 两腿日期错位：us_anchor={mx} vs 美股腿={lmx}，请留意下游取数口径")

        # —— macro 腿只看在不在，不核收盘（刻意分层，见 GOTCHAS G033）——
        for code in ("US10Y", "BRENT", "JP_FUT"):
            r = con.execute(
                "SELECT MAX(trade_date) FROM intl_index_daily WHERE code=?", (code,)).fetchone()[0]
            log(f"  ℹ macro {code:7s} 最新 {r}（读数语义·不开盘中守卫·非收盘价）")
    except Exception as e:
        log(f"  ❌ 回读核对本身失败：{e}")
        ok = False
    finally:
        con.close()
    return ok


def main():
    log("==================== 美股收盘后补数班 开始 ====================")
    log(f"python={PY}")
    log(f"db={DB}")

    try:
        a_max, l_max = probe()
    except Exception as e:
        log(f"❌ 探水位失败（库不可读？）：{e}")
        open(STATUS, "w").write(f"FAIL probe {datetime.now():%Y-%m-%d %H:%M:%S}\n")
        return 1
    log(f"水位：us_anchor_daily={a_max}  intl_index 美股腿={l_max}")

    a_from, l_from = next_iso(a_max), next_iso(l_max)
    log(f"起点：us_anchor --from={a_from}   intl_index --from={l_from}")

    ok = True
    ok &= run("us_anchor 补数",
              [os.path.join(ZZ, "scripts/fetch_us_anchor.py"), "--from", a_from])
    ok &= run("intl_index 补数",
              [os.path.join(ZZ, "scripts/fetch_intl_index.py"),
               "--from", l_from, "--source", "yfinance"])

    log("---- 回读核对 ----")
    ok &= verify(a_max, l_max)

    log("提醒：需要美债/商品真收盘的场景（事件归因、回测）请另取官方源"
        "（H.15 / FRED DGS10 / 官方结算价），勿把 intl_index_daily 的 macro 腿 close 当收盘价用。")

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
