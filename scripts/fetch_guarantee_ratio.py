#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全市场融资融券「平均维持担保比例」拉取 → 公共 market_data.db.margin_guarantee_ratio（附加表，不动句芒既有表）
（CC 2026-07-25；风险日报「杠杆踩踏」因子——融资盘集中爆仓危险点位 的关键输入 R。Doctor 终端跑——网络下载禁在沙箱）

背景：爆仓点位法需要 R=全市场平均维持担保比例（总资产/融资负债）。
  标的（宽基ETF代理 510300 沪深300ETF）跌 d → R×(1−d) 逼近追保线150%/平仓线130% → 强平踩踏。
  危险点位 = 现价×(1 − (1 − 线/R))。tushare `margin` 只有余额、无 R；本表补 R。
来源：akshare `stock_margin_account_info`（东财·融资融券账户信息·全市场·**日度**·含平均维持担保比例）。
  实测为日度全历史（2026-07-24 R=265.39%）；标定爆仓点位（Doctor：认级联、不回测）。
单位：存「百分数原值」——即 250.0 表示 250%（脚本按实际列值存，check 会打印供核）。

用法：
  # 先核实字段（Doctor 终端·联网）——打印列名+尾3行，确认哪列是平均维持担保比例
  python3 scripts/fetch_guarantee_ratio.py --probe
  # 回填/更新（Doctor 终端·联网）
  python3 scripts/fetch_guarantee_ratio.py --fetch
  # 只读对照（沙箱可跑·不联网）：最新 R + 跨度，验证回填结果
  python3 scripts/fetch_guarantee_ratio.py --check
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from lib.logger import get_logger
logger = get_logger(__name__)
import sqlite3, argparse, re
import config


def ensure_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS margin_guarantee_ratio (
            stat_date   TEXT PRIMARY KEY,   -- YYYYMMDD（月末统计日）
            avg_ratio   REAL,               -- 全市场平均维持担保比例（百分数原值，250.0=250%）
            source      TEXT DEFAULT 'akshare_stock_margin_account_info',
            updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


def _load_df(retries=3, backoff=2):
    """全量拉取（3300+ 行）易遇 chunked 断流 → 指数退避重试。

    2026-07-28 实测：同一命令 06:07 `ChunkedEncodingError: Response ended prematurely`
    （akshare 内部裸 requests.get、无重试）、06:10 重跑即成功——**两次挂一次**。
    接入烛阴 16:00 无人值守日链后，无重试＝当班必有概率白跑、要等次日才补。
    全部重试失败才抛，让上层 fail-safe 生效（不写库、保留旧行、绝不编数）。
    """
    import akshare as ak, time
    last = None
    for i in range(retries):
        try:
            return ak.stock_margin_account_info()
        except Exception as e:      # ChunkedEncodingError / ProtocolError / 连接超时等一并兜
            last = e
            logger.warning(f"取数第 {i+1}/{retries} 次失败：{type(e).__name__}: {e}")
            if i < retries - 1:
                time.sleep(backoff * (2 ** i))      # 2s → 4s → 8s
    logger.error(f"取数 {retries} 次全失败，放弃本次（库不变、保留旧行）")
    raise last


def _pick_cols(df):
    """模糊匹配：日期列 + 平均维持担保比例列（列名口径可能随 akshare 版本变）。"""
    date_col = None
    ratio_col = None
    for c in df.columns:
        cs = str(c)
        if date_col is None and ("日期" in cs or "日" == cs[-1:] or re.search(r"date", cs, re.I)):
            date_col = c
        if "维持担保" in cs or ("担保" in cs and "比例" in cs):
            ratio_col = c
    if date_col is None:
        date_col = df.columns[0]
    return date_col, ratio_col


def probe():
    df = _load_df()
    print("列名：", list(df.columns))
    print("\n尾 3 行：")
    print(df.tail(3).to_string())
    dc, rc = _pick_cols(df)
    print(f"\n自动识别 → 日期列={dc!r} · 平均维持担保比例列={rc!r}")
    if rc is None:
        print("⚠ 未自动识别到担保比例列——把上面列名贴回，我改映射。")


def fetch():
    df = _load_df()
    dc, rc = _pick_cols(df)
    if rc is None:
        raise RuntimeError(f"未识别到平均维持担保比例列，实际列={list(df.columns)}——先跑 --probe 贴列名给 CC")
    conn = sqlite3.connect(config.MARKET_DB)
    ensure_table(conn)
    rows = 0
    for _, r in df.iterrows():
        raw_d = str(r[dc]).strip()
        d = re.sub(r"\D", "", raw_d)[:8]      # 2026-06-30 / 20260630 → 20260630
        if len(d) != 8:
            continue
        try:
            v = float(str(r[rc]).replace("%", "").replace(",", "").strip())
        except Exception:
            continue
        conn.execute(
            "INSERT OR REPLACE INTO margin_guarantee_ratio(stat_date,avg_ratio,source) VALUES(?,?,?)",
            (d, v, "akshare_stock_margin_account_info"))
        rows += 1
    conn.commit()
    logger.info(f"✅ 写入 {rows} 条 → margin_guarantee_ratio（列：{rc}）")
    check(conn)


def check(conn=None):
    own = conn is None
    if own:
        conn = sqlite3.connect(f"file:{config.MARKET_DB}?mode=ro", uri=True)
    try:
        cnt = conn.execute(
            "SELECT COUNT(*),MIN(stat_date),MAX(stat_date) FROM margin_guarantee_ratio").fetchone()
        logger.info(f"margin_guarantee_ratio：{cnt[0]} 条 · {cnt[1]}→{cnt[2]}")
        for r in conn.execute(
                "SELECT stat_date,avg_ratio FROM margin_guarantee_ratio ORDER BY stat_date DESC LIMIT 3"):
            logger.info(f"  {r[0]} · 平均维持担保比例 {r[1]:.1f}%")
    except sqlite3.OperationalError:
        logger.error("margin_guarantee_ratio 不存在——先在终端跑 --fetch 回填")
    finally:
        if own:
            conn.close()


def main():
    ap = argparse.ArgumentParser(
        description="全市场平均维持担保比例 R → market_data.margin_guarantee_ratio（杠杆踩踏因子输入）")
    ap.add_argument("--probe", action="store_true", help="打印 akshare 列名+尾3行（核实字段·联网）")
    ap.add_argument("--fetch", action="store_true", help="拉取并写库（联网）")
    ap.add_argument("--check", action="store_true", help="只读对照最新 R（沙箱·不联网）")
    a = ap.parse_args()
    if a.probe:
        probe()
    elif a.fetch:
        fetch()
    else:
        check()


if __name__ == "__main__":
    main()
