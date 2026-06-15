#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import config
from lib.logger import get_logger
logger = get_logger(__name__)
"""
signal_winrate_backtest.py — 标的级胜率回测（两池隔离）
PRD: brain/logs/checkpoints/2026-06-15_标的级胜率回测_PRD.md

读 stock_tracking（已 populate）+ 句芒 Market-Data（只读）：
  个股前向 1/3/5/10 交易日累计收益（用 stock_daily.pct_chg，**绝不用 close 环比**·GOTCHA）
  超额 = 个股累计 − 沪深300基准累计（theme_etf_daily is_benchmark·pct_chg）
  命中 = next3d 超额 > 0（hit_3d）
回写 stock_tracking；并分池出胜率：
  自有池(own)  : 按 info_gap_level × logic_type 分组超额胜率
  dim4 池      : 单列「小鲍命中率」，**绝不并入自有池分母**
未解析(resolve_status='unresolved')与无行情的标的：不计入任一池胜率分母。

用法:
  python3 tools/signal_winrate_backtest.py --dry-run
  python3 tools/signal_winrate_backtest.py
  python3 tools/signal_winrate_backtest.py --recap-db /tmp/recap_test.db
"""
import sqlite3, argparse
from datetime import date
from functools import lru_cache

WINDOWS = [1, 3, 5, 10]
ADJ_MAX_DAYS = 10   # 首个前向交易日须距信号日 ≤ 此自然日，否则判该股信号期无行情（GOTCHA·行情口径断裂 20260603）


def _ymd(d):
    return str(d).replace("-", "")[:8] if d else ""


def _date(ymd):
    return date(int(ymd[:4]), int(ymd[4:6]), int(ymd[6:8]))


def _cum(series_after, n):
    """series_after = [(date, pct_chg%)] 已按日期升序的『信号后』序列；取前 n 日累计收益(%)。"""
    if len(series_after) < n:
        return None
    acc = 1.0
    for _, p in series_after[:n]:
        acc *= (1 + (p or 0) / 100.0)
    return (acc - 1) * 100.0


def _path_extremes(series_after, n=10):
    """前 n 日累计路径的最大涨幅 / 最大回撤(%)。"""
    seg = series_after[:n]
    if not seg:
        return None, None
    acc, hi, lo = 1.0, 0.0, 0.0
    for _, p in seg:
        acc *= (1 + (p or 0) / 100.0)
        cum = (acc - 1) * 100.0
        hi, lo = max(hi, cum), min(lo, cum)
    return hi, lo


def main():
    ap = argparse.ArgumentParser(description="标的级胜率回测")
    ap.add_argument("--recap-db", default=config.RECAP_DB)
    ap.add_argument("--dry-run", action="store_true", help="计算并打印，不回写 stock_tracking")
    args = ap.parse_args()

    mkt = sqlite3.connect(f"file:{config.MARKET_DB}?mode=ro", uri=True)

    # 基准（沪深300）日序列
    brow = mkt.execute(
        "SELECT etf_code, COUNT(*) c FROM theme_etf_daily WHERE is_benchmark=1 "
        "GROUP BY etf_code ORDER BY c DESC LIMIT 1").fetchone()
    bench_code = brow[0] if brow else None
    bench = {}
    if bench_code:
        for d, p in mkt.execute(
                "SELECT trade_date, pct_chg FROM theme_etf_daily WHERE is_benchmark=1 AND etf_code=? ORDER BY trade_date",
                (bench_code,)):
            bench[d] = p
    bench_dates = sorted(bench)
    logger.info(f"基准 = {bench_code}（{len(bench)} 日）")

    @lru_cache(maxsize=None)
    def stock_series(ts):
        return mkt.execute(
            "SELECT trade_date, pct_chg FROM stock_daily WHERE ts_code=? ORDER BY trade_date", (ts,)).fetchall()

    def after(series, sigymd):
        return [(d, p) for d, p in series if d > sigymd]

    def bench_after(sigymd):
        return [(d, bench[d]) for d in bench_dates if d > sigymd]

    con = sqlite3.connect(args.recap_db)
    cur = con.cursor()
    targets = cur.execute(
        "SELECT id, stock_code, signal_date FROM stock_tracking "
        "WHERE target_pool IS NOT NULL AND resolve_status='resolved' "
        "AND stock_code IS NOT NULL AND stock_code<>''").fetchall()

    updates, n_ok, n_nodata, n_gap = [], 0, 0, 0
    for rid, ts, sigd in targets:
        sigymd = _ymd(sigd)
        sa = after(stock_series(ts), sigymd)
        if not sa:
            n_nodata += 1
            continue
        # 覆盖断层守卫：首个前向交易日须紧邻信号日，否则该股信号期无行情，跳到数月后＝假收益
        if (_date(sa[0][0]) - _date(sigymd)).days > ADJ_MAX_DAYS:
            n_gap += 1
            continue
        ba = bench_after(sigymd)
        rets = {n: _cum(sa, n) for n in WINDOWS}
        bres = {n: _cum(ba, n) for n in WINDOWS}
        exc = {n: (rets[n] - bres[n]) if (rets[n] is not None and bres[n] is not None) else None for n in WINDOWS}
        hi, lo = _path_extremes(sa, 10)
        hit3 = None if exc[3] is None else (1 if exc[3] > 0 else 0)
        updates.append((rets[1], rets[3], rets[5], rets[10], hi, lo,
                        exc[1], exc[3], exc[5], exc[10], hit3, bench_code, rid))
        n_ok += 1

    print(f"=== 回测：{len(targets)} 个已解析标的 · 算出收益 {n_ok}（其中含窗口不足<3日者，hit_3d 留空不计分母）· "
          f"无行情 {n_nodata} · 覆盖断层跳过 {n_gap}（信号期早于 stock_daily 全市场覆盖 20260603）===")

    if not args.dry_run:
        # 先清空托管行收益列，保证被跳过/无行情的行为 NULL（幂等 + 不留陈旧假值）
        cur.execute(
            "UPDATE stock_tracking SET next_day_return=NULL, next_3d_return=NULL, next_5d_return=NULL, "
            "next_10d_return=NULL, max_return=NULL, max_drawdown=NULL, excess_1d=NULL, excess_3d=NULL, "
            "excess_5d=NULL, excess_10d=NULL, hit_3d=NULL, bench_code=NULL WHERE target_pool IS NOT NULL")
        cur.executemany(
            "UPDATE stock_tracking SET next_day_return=?, next_3d_return=?, next_5d_return=?, "
            "next_10d_return=?, max_return=?, max_drawdown=?, excess_1d=?, excess_3d=?, "
            "excess_5d=?, excess_10d=?, hit_3d=?, bench_code=?, current_status='backtested' WHERE id=?",
            updates)
        con.commit()
        print(f"✅ 回写 {len(updates)} 行")

    # ── 出胜率：自有池 own（gap × logic）──
    def winrate_rows(where):
        return cur.execute(
            f"SELECT info_gap_level, logic_type, COUNT(*) n, "
            f"ROUND(AVG(hit_3d)*100,1) winrate, ROUND(AVG(excess_3d),2) avg_excess3d, "
            f"ROUND(AVG(next_3d_return),2) avg_ret3d "
            f"FROM stock_tracking WHERE {where} AND hit_3d IS NOT NULL "
            f"GROUP BY info_gap_level, logic_type ORDER BY info_gap_level DESC, n DESC").fetchall()

    print("\n【自有池 own · 超额胜率（next3d 超额>0 计命中）· 按 info_gap_level × logic_type】")
    print(f"  {'gap':>3} {'logic_type':<16} {'样本':>4} {'胜率%':>6} {'均超额%':>7} {'均收益%':>7}")
    for gap, logic, n, wr, ae, ar in winrate_rows("target_pool='own'"):
        print(f"  {str(gap if gap is not None else '—'):>3} {str(logic or '—'):<16} {n:>4} "
              f"{str(wr if wr is not None else '—'):>6} {str(ae if ae is not None else '—'):>7} "
              f"{str(ar if ar is not None else '—'):>7}")
    ov = cur.execute("SELECT COUNT(*), ROUND(AVG(hit_3d)*100,1), ROUND(AVG(excess_3d),2) "
                     "FROM stock_tracking WHERE target_pool='own' AND hit_3d IS NOT NULL").fetchone()
    print(f"  自有池总体：样本 {ov[0]} · 胜率 {ov[1]}% · 均超额 {ov[2]}%")

    # ── dim4 池：单列「小鲍命中率」，绝不并入自有 ──
    d = cur.execute("SELECT COUNT(*), ROUND(AVG(hit_3d)*100,1), ROUND(AVG(excess_3d),2), "
                    "ROUND(AVG(next_3d_return),2) FROM stock_tracking "
                    "WHERE target_pool='dim4_xiaobao' AND hit_3d IS NOT NULL").fetchone()
    print(f"\n【dim4 池 · 小鲍命中率（独立·不并入自有）】样本 {d[0]} · 命中率 {d[1]}% · 均超额 {d[2]}% · 均收益 {d[3]}%")

    con.close(); mkt.close()


if __name__ == "__main__":
    main()
