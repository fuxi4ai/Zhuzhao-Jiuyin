#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
持久化负向测试 · market_data 陈旧判定（STALE_POLICY）与 margin 自检基数
======================================================================
锁定 2026-09-22 实撞的两个缺陷，防其复发：

  ① 共模盲区 —— margin_daily 与 margin_guarantee_ratio 双双停更时，
     旧口径 `COUNT(margin_daily WHERE trade_date > MAX(stat_date))` **恒为 0**；
     风险日报 build_risk_daily.py 的同款护栏用的是同一条自指查询，因而一起失明。

  ② 零新增却报 ✅ —— 子步 exit 0 **不代表**数据落地（有的取数脚本把网络失败
     降级成 WARNING / 「0 日新增」照样 exit 0）。退出码必须由收尾陈旧判定兜住。

跑法：  python3 tools/test_marketdata_staleness.py
安全性：**只读仓库真库**。被测脚本以「源码文本改写常量 + 桩 run()」的方式在
        /tmp 下执行，绝不触发取数、绝不写仓库内任何文件；改写失败即报错退出
        （防「静默跑向真库」）。
"""
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "ops" / "mac_daily_marketdata.py"
# 真库路径由源码路径反推（parents[5] = Documents），使沙箱与 Mac 两处解析一致——
# 用 Path.home() 在沙箱里会指错，安全断言就成了恒真的摆设。
REAL_DB = SRC.parents[5] / "Database/Market-Data/market_data.db"

TRADE_TABLES = ["stock_daily", "daily_market", "theme_etf_daily",
                "market_amount_daily", "limit_list_daily", "margin_daily",
                "us_anchor_daily", "intl_index_daily"]

D0, D1, D2, D3 = "20260922", "20260921", "20260918", "20260917"
# 市场时钟序列：stock_daily 必须**至少两天**，否则被测脚本按设计跳过陈旧判定。
TD_SERIES = [D3, D2, D1, D0]


# ─────────────────────────── 被测源码装载 ───────────────────────────
def load_instrumented(db_path: Path, workdir: Path):
    """把编排器源码读进来，改写三处常量后 exec，返回其命名空间。

    改写必须**逐个断言命中**——否则测试会在无声中跑向真库。
    """
    text = SRC.read_text(encoding="utf-8")
    subs = [
        (r'DB  = os\.path\.join\(HOME, "Documents/Database/Market-Data/market_data\.db"\)',
         f'DB = {str(db_path)!r}'),
        (r'LOGDIR = os\.path\.join\(ZZ, "logs"\)',
         f'LOGDIR = {str(workdir / "logs")!r}'),
        (r'STATUS = os\.path\.join\(ZZ, "ops", "\.last_run_status"\)',
         f'STATUS = {str(workdir / ".last_run_status")!r}'),
    ]
    for pat, rep in subs:
        text, n = re.subn(pat, rep, text)
        if n != 1:
            raise SystemExit(f"❌ 常量改写未命中（{pat}）——源码已变，测试拒绝运行以防跑向真库")
    ns = {"__name__": "_instrumented_not_main", "__file__": str(SRC)}
    exec(compile(text, str(SRC), "exec"), ns)
    ns["run"] = lambda name, args, cwd: True        # 桩：不触发任何取数/落库
    return ns


def build_db(path: Path, rows: dict, stat_date: str, stock_per_day: int = 3, omit=(),
             trade_cal=None):
    """造一张最小库：各表只留 trade_date 列；margin_guarantee_ratio 留 stat_date。

    ⚠ stock_daily 刻意每日塞多行（`stock_per_day`）——它在真实库里是**每股一行**（每日 ~5500 行）。
    若夹具每日只塞一行，「COUNT(*) 与 COUNT(DISTINCT) 等价」，DISTINCT 那个坑就测不出来
    （2026-09-22 正是这样放过了 COUNT(*)=27763 的真错）。
    """
    if path.exists():
        path.unlink()
    con = sqlite3.connect(path)
    for t in TRADE_TABLES:
        if t in omit:
            continue
        con.execute(f"CREATE TABLE {t}(trade_date TEXT)")
    con.execute("CREATE TABLE margin_guarantee_ratio(stat_date TEXT)")
    for t, days in rows.items():
        if t in omit:
            continue
        payload = [(d,) for d in days for _ in range(stock_per_day if t == "stock_daily" else 1)]
        con.executemany(f"INSERT INTO {t}(trade_date) VALUES(?)", payload)
    con.execute("INSERT INTO margin_guarantee_ratio(stat_date) VALUES(?)", (stat_date,))
    if trade_cal is not None:                      # [(cal_date, is_open), …]
        con.execute("CREATE TABLE trade_cal (cal_date TEXT PRIMARY KEY, is_open INTEGER)")
        con.executemany("INSERT OR REPLACE INTO trade_cal (cal_date, is_open) VALUES (?,?)",
                        trade_cal)
    con.commit()
    con.close()


def run_case(name, rows, stat_date, workdir, omit=(), trade_cal=None):
    db = workdir / f"{name}.db"
    build_db(db, rows, stat_date, omit=omit, trade_cal=trade_cal)
    # 每案例独立 logdir：日志文件名按日期生成，共用目录会让后一个案例读到前一个的判词。
    case_dir = workdir / name
    case_dir.mkdir(exist_ok=True)
    ns = load_instrumented(db, case_dir)
    rc = ns["main"]()
    logfile = sorted((case_dir / "logs").glob("mac_marketdata_*.log"))[-1]
    return rc, logfile.read_text(encoding="utf-8")


def run_garbage_case(name, workdir):
    """收尾核验本身失败的路径：库存在但不是 sqlite。"""
    db = workdir / f"{name}.db"
    db.write_text("this is not a sqlite database\n")
    case_dir = workdir / name
    case_dir.mkdir(exist_ok=True)
    ns = load_instrumented(db, case_dir)
    rc = ns["main"]()
    logfile = sorted((case_dir / "logs").glob("mac_marketdata_*.log"))[-1]
    return rc, logfile.read_text(encoding="utf-8")


def main():
    workdir = Path(tempfile.mkdtemp(prefix="mdm_stale_test_"))
    before = (REAL_DB.stat().st_mtime_ns, REAL_DB.stat().st_size) if REAL_DB.exists() else None
    ok = True

    def check(desc, cond, extra=""):
        nonlocal ok
        print(f"  {'✓' if cond else '✗'} {desc}" + (f"   {extra}" if extra else ""))
        if not cond:
            ok = False

    # ── 案例 A：复现 09-22 真实形状（theme_etf/market_amount 落 D1、margin 两表停 09-15）──
    print("\n案例 A · 复现 2026-09-22 形态（应判 FAIL，且硬档恰为三张表）")
    A = {t: [D0] for t in TRADE_TABLES}
    A["stock_daily"] = TD_SERIES
    A.update({"theme_etf_daily": [D1], "market_amount_daily": [D1],
              "limit_list_daily": [D1], "us_anchor_daily": [D1], "intl_index_daily": [D1],
              "margin_daily": ["20260915"]})
    rc, log = run_case("a", A, "20260915", workdir)
    check("退出码 = 1", rc == 1, f"rc={rc}")
    m = re.search(r"❌ 应到未到（计入退出码）：(.+)", log)
    got_hard = sorted(re.findall(r"([A-Za-z_]+)\(", m.group(1))) if m else []
    check("硬档**恰为**三张表（非子集断言）",
          got_hard == sorted(["margin_daily", "market_amount_daily", "theme_etf_daily"]),
          f"got={got_hard}")
    check("时钟来源标注为「回退」（无 trade_cal 时）且打出时效行",
          "市场时钟 = stock_daily(回退" in log and "日历天" in log)
    check("margin 行同时打出新旧两个基数",
          "落后大盘" in log and "落后 margin_daily" in log)

    # ── 案例 B：共模盲区防回归（本测试的核心断言）──
    print("\n案例 B · 共模盲区防回归（旧口径恒 0 · 新口径可见 · 且必须按交易日去重）")
    con = sqlite3.connect(workdir / "a.db")
    old_metric = con.execute(
        "SELECT COUNT(*) FROM margin_daily WHERE trade_date > "
        "(SELECT MAX(stat_date) FROM margin_guarantee_ratio)").fetchone()[0]
    naive = con.execute(
        "SELECT COUNT(*) FROM stock_daily WHERE trade_date > "
        "(SELECT MAX(stat_date) FROM margin_guarantee_ratio)").fetchone()[0]
    distinct = con.execute(
        "SELECT COUNT(DISTINCT trade_date) FROM stock_daily WHERE trade_date > "
        "(SELECT MAX(stat_date) FROM margin_guarantee_ratio)").fetchone()[0]
    con.close()
    # 下面前三条是**夹具属性**（构造出来的，与生产代码无关，永不可能失败）——
    # 保留只为把「盲区长什么样」写清楚；**真正的回归锁是第四条**（读生产代码打出的日志）。
    check("[夹具属性·非生产断言] 旧口径（与 margin_daily 互比）= 0 ← 盲区长这样",
          old_metric == 0, f"old={old_metric}")
    check(f"[夹具属性·非生产断言] 不去重会把 {len(TD_SERIES)} 个交易日算成 {naive} 行",
          naive == len(TD_SERIES) * 3, f"naive={naive}")
    check(f"[夹具属性·非生产断言] 去重后 = {len(TD_SERIES)} 个交易日",
          distinct == len(TD_SERIES), f"distinct={distinct}")
    # ★ 端到端回归锁：生产代码打出的「落后大盘 N 交易日」必须等于去重后的值
    #   （变异 N1 证明：把 COUNT(DISTINCT) 改回 COUNT(*) 只有这一条会响）
    m = re.search(r"落后大盘 (\d+) 交易日", log)
    check(f"★ 脚本日志里的「落后大盘」= {len(TD_SERIES)}（非 {naive}）",
          bool(m) and int(m.group(1)) == len(TD_SERIES),
          f"log={m.group(1) if m else '未匹配'}")

    # ── 案例 C：负向对照 · 全部达档 → 必须 PASS（防「一律报红」的假阳性）──
    print("\n案例 C · 全部达档（应判 PASS）")
    C = {t: [D0] for t in TRADE_TABLES}
    C["stock_daily"] = TD_SERIES
    C.update({"limit_list_daily": [D1], "margin_daily": [D1],
              "us_anchor_daily": [D1], "intl_index_daily": [D1]})
    rc, log = run_case("c", C, D1, workdir)
    check("退出码 = 0", rc == 0, f"rc={rc}")
    check("无 ❌ 应到未到", "❌ 应到未到" not in log)
    check("判定确已执行（非因时钟不足被跳过）", "市场时钟不足" not in log)

    # ── 案例 D：境外假期不同步 → 只记录、不计退出码（G-X122 防误报）──
    print("\n案例 D · intl_index/us_anchor 仅落后 D0（境外假期）→ 只记录不判红")
    D = {t: [D0] for t in TRADE_TABLES}
    D["stock_daily"] = TD_SERIES
    D.update({"limit_list_daily": [D1], "margin_daily": [D1],
              "intl_index_daily": [D2], "us_anchor_daily": [D2]})
    rc, log = run_case("d", D, D1, workdir)
    check("退出码 = 0（软档不进退出码）", rc == 0, f"rc={rc}")
    check("软档确有记录（不静默）", "⚠ 应到未到（仅记录" in log)

    # ── 案例 E：市场时钟不足 → 跳过判定而非误判 ──
    print("\n案例 E · 市场时钟不足（stock_daily 仅 1 个交易日）→ 跳过判定")
    E = {t: [D0] for t in TRADE_TABLES}
    E["stock_daily"] = [D0]
    rc, log = run_case("e", E, D0, workdir)
    check("给出「市场时钟不可得」而非误判", "市场时钟不可得" in log)
    check("退出码 = 0", rc == 0, f"rc={rc}")

    # ── 案例 F：收尾核验本身失败（库不是 sqlite）→ 必须 fail-visible，不得默认放行 ──
    print("\n案例 F · 收尾核验失败（库打不开）→ 按失败处理")
    rc, log = run_garbage_case("f", workdir)
    check("退出码 = 1（fail-visible，非静默放行）", rc == 1, f"rc={rc}")
    check("日志明写「收尾核对失败」", "收尾核对失败" in log)

    # ── 案例 G：硬档位表缺失 → 判不了按「应到未到」处理，不得打全绿 ──
    print("\n案例 G · 硬档位表缺失 → 不得打全绿")
    G = {t: [D0] for t in TRADE_TABLES if t != "margin_daily"}
    G["stock_daily"] = TD_SERIES
    G.update({"limit_list_daily": [D1], "us_anchor_daily": [D1], "intl_index_daily": [D1]})
    rc, log = run_case("g", G, D1, workdir, omit=("margin_daily",))
    check("退出码 = 1", rc == 1, f"rc={rc}")
    check("明写「硬档位表无法判定」", "硬档位表无法判定" in log)
    check("不打「✅ 各表均达到…」", "✅ 各表均达到" not in log)

    # ── 案例 H：trade_cal 独立日历 —— 共模停摆的根治路径（G-X193）──
    #   两臂对照：数据完全相同，唯一差别是「有没有 trade_cal」。
    #   无 cal 时时钟自己也冻住 ⇒ 相对落后被压缩 ⇒ 全绿（这正是 09-22 事故的形状）；
    #   有 cal 时时钟靠独立日历保持正确 ⇒ 各表落后被如实判出。
    print("\n案例 H · trade_cal 独立日历：同数据、有/无日历两臂对照")
    frozen = {t: [D2] for t in TRADE_TABLES}
    frozen["stock_daily"] = [D3, D2]                     # 共模：时钟自己也冻在 09-18
    frozen.update({"limit_list_daily": [D3], "margin_daily": [D3],
                   "us_anchor_daily": [D3], "intl_index_daily": [D3]})
    cal = [("20260917", 1), ("20260918", 1), ("20260919", 0),
           ("20260920", 0), ("20260921", 1), ("20260922", 1)]

    rc_no, log_no = run_case("h_no", frozen, D3, workdir)
    check("[对照臂·无 trade_cal] rc = 0 ← 共模停摆下全绿，正是事故形状",
          rc_no == 0, f"rc={rc_no}")
    check("[对照臂] 时钟来源标为回退", "市场时钟 = stock_daily(回退" in log_no)

    rc_cal, log_cal = run_case("h_cal", frozen, D3, workdir, trade_cal=cal)
    check("[治疗臂·有 trade_cal] rc = 1 ← 时钟保持正确，落后被如实判出",
          rc_cal == 1, f"rc={rc_cal}")
    check("[治疗臂] 时钟来源 = trade_cal", "市场时钟 = trade_cal" in log_cal)
    check("[治疗臂] 确有表被判落后", "❌ 应到未到" in log_cal,
          (re.search(r"❌ 应到未到（计入退出码）：(.+)", log_cal).group(1)[:70]
           if "❌ 应到未到" in log_cal else "无"))

    # ── 安全断言：全程未碰真库（真断言，非恒真）──
    print("\n安全核验")
    if before is None:
        print("  ⚠ 未核 · 真库路径不可达，本条安全断言**未执行**（不计入通过）")
    else:
        after = REAL_DB.stat()
        check("真库 mtime/size 逐位未变",
              (after.st_mtime_ns, after.st_size) == before,
              f"before={before} after={(after.st_mtime_ns, after.st_size)}")
    check("真库无 -wal/-shm 残留（未以写模式打开过）",
          not (REAL_DB.parent / (REAL_DB.name + "-wal")).exists()
          and not (REAL_DB.parent / (REAL_DB.name + "-shm")).exists())

    shutil.rmtree(workdir, ignore_errors=True)
    print(f"\n{'✅ 全过' if ok else '❌ 有失败项'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
