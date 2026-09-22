#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mac 原生 · stock_daily 增量落库（根治沙箱 FUSE 大表写回回退）
-------------------------------------------------------------
- 只用标准库（urllib），无三方依赖。
- 交易日锚点走 Tushare trade_cal（不信系统时钟）。
- 把 stock_daily 从 当前 max 的次日 补到「最近一个已收盘交易日」（北京日历）。
- pro.daily by trade_date 全市场一次一天；INSERT OR IGNORE 幂等；
  防空壳：单日 < MIN_ROWS 视为未就绪/异常 → 跳过不写、记日志（绝不写半库）。
- 有任何"应到而未落"的目标日 → 退出码非 0，供 wrapper 标 ❌（不静默失败）。

用法： python3 ingest_stock_daily.py            # 补到最近收盘日
       python3 ingest_stock_daily.py 20260722  # 只补指定日（调试）
"""
import os, sys, json, time, sqlite3, urllib.request
from datetime import datetime, timezone, timedelta

DB      = os.path.expanduser("~/Documents/Database/Market-Data/market_data.db")
ENVFILE = os.path.expanduser("~/Documents/Database/.env")
API     = "http://api.tushare.pro"
FIELDS  = "ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount"
MIN_ROWS = 5000          # 口径闸：全市场当日 ~5500，低于此视为未就绪/残缺
BJ = timezone(timedelta(hours=8))


def log(msg):
    print(f"[{datetime.now(BJ):%Y-%m-%d %H:%M:%S} CST] {msg}", flush=True)


def read_token():
    for line in open(ENVFILE, encoding="utf-8"):
        line = line.strip()
        if line.startswith("TUSHARE_TOKEN="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("❌ 没在 ~/Documents/Database/.env 读到 TUSHARE_TOKEN")


def api_call(token, api_name, params, fields="", retries=3):
    body = json.dumps({"api_name": api_name, "token": token,
                       "params": params, "fields": fields}).encode()
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(API, data=body,
                                         headers={"Content-Type": "application/json"})
            r = json.load(urllib.request.urlopen(req, timeout=60))
            if r.get("code") != 0:
                raise RuntimeError(f"tushare code={r.get('code')} msg={r.get('msg')}")
            return r["data"]["fields"], r["data"]["items"]
        except Exception as e:
            last = e
            log(f"  ⚠ {api_name} 第 {i+1}/{retries} 次失败：{e}")
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"{api_name} 重试耗尽：{last}")


def open_trade_days(token, after_yyyymmdd, end_yyyymmdd):
    """返回 (after, end] 区间内的开市日（升序）。"""
    _, items = api_call(token, "trade_cal",
                        {"exchange": "SSE", "start_date": after_yyyymmdd,
                         "end_date": end_yyyymmdd, "is_open": "1"}, "cal_date")
    days = sorted(x[0] for x in items)
    return [d for d in days if d > after_yyyymmdd]


def cur_max(con):
    r = con.execute("SELECT MAX(trade_date) FROM stock_daily").fetchone()[0]
    return r or "20000101"


CAL_LOOKBACK_DAYS = 120


def persist_trade_cal(con, token, end_yyyymmdd, lookback_days=CAL_LOOKBACK_DAYS):
    """把 tushare trade_cal 落成 `market_data.db.trade_cal`（2026-09-22 加）。

    **为什么落表**：陈旧判定需要一个**独立于「待取数的行情表」**的日历参照系。
    原先两处陈旧判定（本目录 mac_daily_marketdata.py 的收尾、风险日报 build_risk_daily.py
    的 R 护栏）都拿 `stock_daily` 当时钟，而 stock_daily 本身也要取数 ⇒ 网络共模停摆时
    时钟与各表**一起冻结**，判定恒绿（通用教训 G-X193）。
    trade_cal 走 tushare 的**日历**接口、与行情表无耦合，且一次拉多天、对网络抖动的
    暴露面小得多，是这条链上唯一够格当参照系的东西。

    写 (cal_date, is_open) 两列，**忠实保存源数据**（含闭市日），由消费者自行过滤 is_open=1。
    INSERT OR REPLACE 幂等；窗口锚在**今天**而非 stock_daily 的 max，故即使行情停更多日，
    日历仍是新的。
    """
    start = (datetime.strptime(end_yyyymmdd, "%Y%m%d")
             - timedelta(days=lookback_days)).strftime("%Y%m%d")
    fields, items = api_call(token, "trade_cal",
                             {"exchange": "SSE", "start_date": start,
                              "end_date": end_yyyymmdd}, "cal_date,is_open")
    con.execute("CREATE TABLE IF NOT EXISTS trade_cal "
                "(cal_date TEXT PRIMARY KEY, is_open INTEGER)")
    con.executemany("INSERT OR REPLACE INTO trade_cal (cal_date, is_open) VALUES (?,?)",
                    [(str(c), int(o)) for c, o in items])
    con.commit()
    open_n = sum(1 for _, o in items if int(o) == 1)
    log(f"  ✓ trade_cal：{start}→{end_yyyymmdd} 共 {len(items)} 天（开市 {open_n}）")
    return len(items)


def ingest_one(con, token, day):
    fields, items = api_call(token, "daily", {"trade_date": day}, FIELDS)
    n = len(items)
    if n < MIN_ROWS:
        log(f"  ✗ {day}: 仅 {n} 行 (< {MIN_ROWS})，判未就绪/残缺 → 跳过不写")
        return False, n
    ph = ",".join("?" * len(fields))
    before = con.execute("SELECT COUNT(*) FROM stock_daily").fetchone()[0]
    con.executemany(
        f"INSERT OR IGNORE INTO stock_daily ({','.join(fields)}) VALUES ({ph})", items)
    con.commit()
    after = con.execute("SELECT COUNT(*) FROM stock_daily").fetchone()[0]
    log(f"  ✓ {day}: 拉 {n} 行，新增 {after - before}")
    return True, n


def main():
    token = read_token()
    now = datetime.now(BJ)
    today_bj = now.strftime("%Y%m%d")
    con = sqlite3.connect(DB)
    try:
        # 日历落表先行。刻意独立 try：日历失败**不阻断**行情落库（两者职责不同），
        # 只留下游陈旧判定退回 stock_daily 时钟的告警。
        try:
            persist_trade_cal(con, token, today_bj)
        except Exception as e:
            log(f"  ⚠ trade_cal 落表失败（不阻断行情落库；下游陈旧判定将退回 stock_daily 时钟）：{e}")
        mx = cur_max(con)
        if len(sys.argv) > 1:                       # 调试：只补指定日
            targets = [sys.argv[1]]
        else:
            targets = open_trade_days(token, mx, today_bj)
        if not targets:
            log(f"stock_daily 已最新（max={mx}），无缺口。")
            return 0
        log(f"stock_daily max={mx} → 待补交易日 {targets}")
        missed = []
        for day in targets:
            ok, _ = ingest_one(con, token, day)
            if not ok:
                missed.append(day)
        new_mx = cur_max(con)
        log(f"完成：stock_daily max={new_mx}"
            + (f"；未落 {missed}" if missed else "，无遗漏"))
        # 只有"最新那个目标日"没落才算硬失败（旧日缺失可能是历史空洞，不阻断）
        if targets[-1] not in missed:
            return 0
        # 例外：最新目标日=今天且现在还没到收盘后 EOD 就绪点(16:00 CST) → 属正常，不判失败
        if targets[-1] == today_bj and now.strftime("%H%M") < "1600":
            log("（最新目标日=今日、尚未到 16:00 收盘后 EOD 就绪点 → 属正常，本次不判失败）")
            return 0
        return 1
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
