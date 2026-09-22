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

陈旧可见性（2026-09-22 加）：**子步退出码为 0 不等于数据落地**——有的取数脚本把网络失败降级成
WARNING 或「0 日新增」照样 exit 0（09-22 实撞：theme_etf / margin 报 ✅ 而当日一行未落）。
故收尾加「各表 vs 市场时钟」判定，应到未到的硬档位折进本程序退出码（见 STALE_POLICY）。
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

# --from 增量起点：回看 7 天（INSERT OR IGNORE 幂等，重叠无害）
# 服务四个脚本：theme_etf / market_amount / limit_list / margin。
# （intl_index / kr_stocks 不吃 --from；guarantee_ratio 用 --fetch。原注写「五表」与实际不符，2026-08-01 订正。）
FROM = (datetime.now() - timedelta(days=7)).strftime("%Y%m%d")

# ── 陈旧判定策略（2026-09-22 加）──────────────────────────────────────────────
# 动机＝2026-09-22 实撞：margin_daily 与 margin_guarantee_ratio 双双停在 09-15，其后
#   09-16/17/18/21/22 五个交易日无数据（按东财 T+1 口径，当班时点应有的是前四个），
#   而旧自检是「两表互比」——COUNT(margin_daily WHERE trade_date > MAX(stat_date))
#   ⇒ 两表一起停更时恒为 0，共模停更完全不可见。风险日报 build_risk_daily.py 的同款护栏
#     用的是同一条自指查询，因而同样失明（页面照常显示 09-15 的 R，无任何陈旧标记）。
#   ⇒ 改与**市场时钟**比：stock_daily 的最近交易日 D0 与其前一交易日 D1。
#     选 stock_daily 的理由＝同库同族、天然只含交易日（无日历/节假日毛刺），
#     与 build_risk_daily.py 原注释「交易日差用 margin_daily 数，不用日历天」同源。
# 档位依据＝实读 09-15/09-16 两份运行日志的落库行为：
#   D0（当日 17:30 北京可得）：stock_daily / daily_market / theme_etf_daily / market_amount_daily
#   D1（T+1 发布）：limit_list_daily / margin_daily / us_anchor_daily / intl_index_daily
# ⚠ 本表**不含 stock_daily**：D0 就是由它定义的 ⇒ `stock_daily < D0` 恒假，写进来只是一条
#   **恒真死条目**，会让「被覆盖了」是错觉。它自己的时效由收尾段的**市场时钟判定**单独负责
#   （与**日历天**比，>7 天才报——A 股最长连休约 8–10 天，留足防误报余量）。
# ⚠ 残留盲区（如实标注）：D0/D1 取自一张**待取数**的表 ⇒ 网络整体中断时，时钟与各表**一起冻结**，
#   本判定仍会全绿。彻底根治需独立日历源（当前 market_data.db 无 trade_cal 表）。
#   缓解：各取数子步失败已让退出码非 0；且市场时钟判定会把「时钟陈旧 >7 天」显式打出来。
# 每项第二字段＝是否计入本程序退出码。标 False 的是「境外市场假期与 A 股不同步」，
#   判红会天天误报 —— G-X122：一条误报就能让真信号从此没人看。
STALE_POLICY = {
    "daily_market":        ("D0", True),
    "theme_etf_daily":     ("D0", True),
    "market_amount_daily": ("D0", True),
    "limit_list_daily":    ("D1", True),
    "margin_daily":        ("D1", True),
    "intl_index_daily":    ("D0", False),
    "us_anchor_daily":     ("D1", False),
}

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
    log(f"四表 --from={FROM}（theme_etf/market_amount/limit_list/margin · 回看 7 天，去重幂等）")
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
    # R 值（全市场平均维持担保比例）→ margin_guarantee_ratio。走 akshare 东财、非 tushare，参数是 --fetch 不是 --from。
    # 2026-08-01 补：此前该表**没有任何主人**——日更步骤只写在一份从未生效的 SKILL 里（落在
    #   ~/Documents/Claude/Scheduled/ 那棵调度器不读的树上，见 [[通用教训]] G-X118），
    #   现有数据全部来自 2026-07-28 06:10 的一次手动回填（3355 行·stat_date 止于 20260727），此后零写入。
    #   消费方＝风险日报「杠杆踩踏」爆仓点位法（Projects/风险日报/build_risk_daily.py L103）。
    # ⚠ 刻意不并入 ok：东财全量拉 3300+ 行**已知易 ChunkedEncodingError**（脚本自带 3 次指数退避），
    #   而下游 build_risk_daily.py 已有 R 陈旧护栏（>3 交易日页面标 ⚠、>10 交易日 buffer 降参考）。
    #   并进 ok 会让一条已知偶发的网络腿把整个 launchd job 标 FAIL，造成告警疲劳、反而掩盖真问题。
    #   失败仍由 run() 打 ❌ 进日志，看得见；停更由下游护栏兜底。
    run("guarantee_ratio", [os.path.join(ZZ, "scripts/fetch_guarantee_ratio.py"), "--fetch"], ZZ)
    ok &= run("intl_index",   [os.path.join(ZZ, "scripts/fetch_intl_index.py")], ZZ)
    ok &= run("kr_stocks",    [os.path.join(ZZ, "scripts/fetch_kr_stocks.py")], ZZ)

    # ④ 收尾：核各表 max 落日志 + 陈旧判定（2026-09-22 加）
    #    ⚠ 本段必须在**所有写库方之后**跑（2026-06-30 为 Market-Data 立的「体检挪到末位写库方」）。
    log("---- 各表 MAX(trade_date) ----")
    _stale_hard, _stale_soft, _closing_failed = [], [], False
    try:
        import sqlite3
        con = sqlite3.connect(f"file:{DB}?mode=ro&immutable=1", uri=True)
        for t in ["stock_daily","daily_market","theme_etf_daily","market_amount_daily",
                  "limit_list_daily","margin_daily","us_anchor_daily","intl_index_daily"]:
            try:
                log(f"  {t:22s} {con.execute(f'SELECT MAX(trade_date) FROM {t}').fetchone()[0]}")
            except Exception as e:
                log(f"  {t:22s} ERR {e}")
        # margin_guarantee_ratio 单独一行：它的日期列是 stat_date 不是 trade_date，
        # 塞进上面的循环只会打印 ERR（2026-08-01 加）。同时算出下游护栏用的「落后几个交易日」，
        # 让停更在本日志里就看得见，不必等风险日报页面才发现。
        try:
            _r = con.execute("SELECT MAX(stat_date) FROM margin_guarantee_ratio").fetchone()[0]
            # 2026-09-22 订正基数：原基数是 margin_daily ⇒ 两表一起停更时恒为 0（共模盲区，
            #   风险日报同款护栏一并失明）。改以市场时钟、天然只含交易日的 stock_daily 为基数；
            #   两个数都打出来，便于和旧口径对照。
            # ⚠ 必须 COUNT(DISTINCT trade_date)：stock_daily 是**每股一行**（每日 ~5500 行），
            #   COUNT(*) 会把 5 个交易日算成 27763（2026-09-22 实测踩到，靠真实形状夹具逮出）。
            _lag_cal = con.execute(
                "SELECT COUNT(DISTINCT trade_date) FROM stock_daily WHERE trade_date > ?",
                (_r,)).fetchone()[0]
            _lag_peer = con.execute(
                "SELECT COUNT(DISTINCT trade_date) FROM margin_daily WHERE trade_date > ?",
                (_r,)).fetchone()[0]
            _flag = "" if _lag_cal <= 3 else f"  ⚠陈旧{_lag_cal}交易日（下游 build_risk_daily 将标警）"
            log(f"  {'margin_guarantee_ratio':22s} {_r}  (stat_date · 落后大盘 {_lag_cal} 交易日"
                f" · 落后 margin_daily {_lag_peer} 交易日){_flag}")
        except Exception as e:
            log(f"  {'margin_guarantee_ratio':22s} ERR {e}")

        # ── 陈旧判定：各表 vs 市场时钟（STALE_POLICY）──
        # 时钟来源（2026-09-22 二轮复验后改）：**优先 trade_cal** —— 它是独立于行情表的日历接口
        #   （ingest_stock_daily.persist_trade_cal 落表），一次拉多天、网络暴露面小。
        #   缺失时退回 stock_daily **并显式标注共模盲区**（G-X193：网络整体中断时二者一起冻结）。
        bj = datetime.utcnow() + timedelta(hours=8)               # 北京时间
        # 今日尚未收盘（北京 <15:00）时把日历截到昨日，否则会把还没产生的当日数据算成缺口
        cutoff = (bj.strftime("%Y%m%d") if bj.hour >= 15
                  else (bj - timedelta(days=1)).strftime("%Y%m%d"))
        D0 = D1 = clock_src = None
        try:
            _c = [r[0] for r in con.execute(
                "SELECT cal_date FROM trade_cal WHERE is_open=1 AND cal_date <= ? "
                "ORDER BY cal_date DESC LIMIT 2", (cutoff,))]
            if len(_c) >= 2:
                D0, D1, clock_src = str(_c[0]), str(_c[1]), "trade_cal"
        except Exception:
            pass
        if clock_src is None:
            _days = [r[0] for r in con.execute(
                "SELECT DISTINCT trade_date FROM stock_daily ORDER BY trade_date DESC LIMIT 2")]
            if len(_days) >= 2:
                D0, D1, clock_src = str(_days[0]), str(_days[1]), "stock_daily(回退·有共模盲区)"
        if clock_src is None:
            log("  ⚠ 市场时钟不可得（trade_cal 缺失且 stock_daily 交易日 < 2），本次跳过陈旧判定"
                "——「全绿」不成立，请人工看")
        else:
            log(f"---- 陈旧判定（市场时钟 = {clock_src} · D0={D0} · D1={D1} · 截到 {cutoff}）----")
            # 时钟自身时效。阈值随来源而不同：
            #  · trade_cal：日历一次拉多天且与行情无耦合 ⇒ 健康的日历**永远**给出 D0=cutoff 当日
            #    （或最近的已收盘开市日），故 >3 天即说明日历没刷新/拉取失败，可判得紧。
            #  · stock_daily 回退：日历天含长假，据二轮复验对真实库全历史实算，相邻交易日间隔
            #    **最大 11 天、13 处 >7 天**（春节/国庆）⇒ 必须放到 12 天，否则每个长假误报。
            #    （原注释写「A 股最长连休约 8–10 天」是错的，已订正。）
            _cal_lag = (datetime.strptime(cutoff, "%Y%m%d") - datetime.strptime(D0, "%Y%m%d")).days
            _thr = 3 if clock_src == "trade_cal" else 12
            log(f"  {'市场时钟':22s} {D0}（落后截点 {_cal_lag} 日历天·阈值 {_thr}）"
                + ("  ⚠ 时钟本身疑似冻结——此时「各表达档」不可信" if _cal_lag > _thr else ""))
            _skipped = []
            for _t, (_tier, _hard) in STALE_POLICY.items():
                _floor = D0 if _tier == "D0" else D1
                try:
                    _mx = con.execute(f"SELECT MAX(trade_date) FROM {_t}").fetchone()[0]
                except Exception as e:
                    log(f"  {_t:22s} 判定跳过 ERR {e}")
                    # 判不了 ≠ 没问题：硬档位表无法判定时按「应到未到」处理（fail-visible）
                    if _hard:
                        _skipped.append(_t)
                    continue
                if _mx is None or str(_mx) < _floor:
                    (_stale_hard if _hard else _stale_soft).append(f"{_t}({_mx}<{_floor})")
            if _stale_hard:
                log(f"  ❌ 应到未到（计入退出码）：" + " · ".join(_stale_hard))
            if _skipped:
                log(f"  ❌ 硬档位表无法判定（计入退出码）：" + " · ".join(_skipped))
                _stale_hard += [f"{t}(判定失败)" for t in _skipped]
            if _stale_soft:
                log(f"  ⚠ 应到未到（仅记录·境外假期不同步）：" + " · ".join(_stale_soft))
            if not _stale_hard and not _stale_soft:
                log("  ✅ 各表均达到市场时钟所要求的档位（时钟时效见上一行；时钟自身的残余"
                    "共模盲区见文件头 STALE_POLICY 注）")
        con.close()
    except Exception as e:
        # fail-visible：收尾核验本身失败意味着「本轮没有任何陈旧判定」，绝不能默认放行
        log(f"  ❌ 收尾核对失败（本轮无陈旧判定，按失败处理）：{e}")
        _closing_failed = True
    ok &= (not _stale_hard) and (not _closing_failed)

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
