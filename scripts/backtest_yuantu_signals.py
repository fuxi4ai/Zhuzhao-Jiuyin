#!/usr/bin/env python3
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import config
from lib.logger import get_logger
logger = get_logger(__name__)
"""
🕯️ backtest_yuantu_signals.py — 渊图买入信号有效性回测

对 yuantu_buy_signals 中已解析 ts_code 的标的，用 market_data.db 算信号日后 N 日收益，
与上证基准比超额；按信号类型 / 有无小鲍印证分组。验"灯亮→受益方向"是否有 edge。

⚠️ 边界：① 样本小、非平稳，仅作方向性参考，非择时承诺；② 入场=信号日(报告 data_vintage)
后首个交易日收盘，无前视；③ 指标看分布与超额，不看"胜率绝对值"。

用法: python3 scripts/backtest_yuantu_signals.py [--windows 5,10,20] [--write]
"""
import sqlite3, argparse, statistics
from pathlib import Path

MARKET = config.MARKET_DB
RECAP = config.RECAP_DB


def _load_index(mconn):
    """上证基准：trade_date → 累计净值用的 pct（这里直接存 close 算窗口收益）。"""
    rows = mconn.execute("SELECT trade_date, sh_close FROM daily_market WHERE sh_close IS NOT NULL ORDER BY trade_date").fetchall()
    return [(d, c) for d, c in rows]


def _fwd_return(mconn, ts_code, date, ndays):
    """ts_code 在 date 后首个交易日入场，持有 ndays 个交易日的收益。"""
    rows = mconn.execute(
        "SELECT trade_date, close FROM stock_daily WHERE ts_code=? AND trade_date>=? ORDER BY trade_date LIMIT ?",
        (ts_code, date.replace("-", ""), ndays + 1)).fetchall()
    if len(rows) < 2:
        # 试带横杠日期格式
        rows = mconn.execute(
            "SELECT trade_date, close FROM stock_daily WHERE ts_code=? AND trade_date>=? ORDER BY trade_date LIMIT ?",
            (ts_code, date, ndays + 1)).fetchall()
    if len(rows) < 2:
        return None
    entry = rows[0][1]
    exit_ = rows[min(ndays, len(rows) - 1)][1]
    if not entry:
        return None
    return exit_ / entry - 1.0


def _idx_return(idx, date, ndays):
    fmt = [(d, c) for d, c in idx if d >= date.replace("-", "")] or [(d, c) for d, c in idx if d >= date]
    if len(fmt) < 2:
        return None
    return fmt[min(ndays, len(fmt) - 1)][1] / fmt[0][1] - 1.0


def run(windows, write=False):
    if not Path(MARKET).exists():
        logger.error(f"❌ 缺 market_data.db: {MARKET}"); sys.exit(2)
    rconn = sqlite3.connect(RECAP)
    mconn = sqlite3.connect(MARKET)
    idx = _load_index(mconn)

    sigs = rconn.execute(
        "SELECT signal_node,date,signal_type,beneficiaries_ts,xiaobao_echo FROM yuantu_buy_signals WHERE ts_resolved>0 AND date IS NOT NULL").fetchall()
    logger.info(f"回测样本：{len(sigs)} 条带标的信号 · 窗口 {windows}\n")

    agg = {w: {"ret": [], "exc": [], "echo_exc": [], "noecho_exc": []} for w in windows}
    write_rows = []
    for node, date, st, bts, echo in sigs:
        codes = [seg.split(":")[-1] for seg in (bts or "").split(" / ") if ":" in seg]
        per_sig_exc20 = []
        for w in windows:
            ir = _idx_return(idx, date, w)
            rets = [r for c in codes if (r := _fwd_return(mconn, c, date, w)) is not None]
            if not rets:
                continue
            mret = statistics.mean(rets)
            agg[w]["ret"].append(mret)
            if ir is not None:
                exc = mret - ir
                agg[w]["exc"].append(exc)
                (agg[w]["echo_exc"] if echo else agg[w]["noecho_exc"]).append(exc)
                if w == max(windows):
                    per_sig_exc20.append(exc)
        if per_sig_exc20:
            write_rows.append((statistics.mean(per_sig_exc20), node))

    def desc(xs):
        if not xs:
            return "n=0"
        xs2 = sorted(xs)
        return (f"n={len(xs)} 均值={statistics.mean(xs)*100:+.2f}% 中位={xs2[len(xs2)//2]*100:+.2f}% "
                f"胜率(>0)={sum(1 for x in xs if x>0)/len(xs):.0%}")

    for w in windows:
        logger.info(f"── 窗口 {w} 日 ──")
        logger.info(f"  标的绝对收益 : {desc(agg[w]['ret'])}")
        logger.info(f"  超额(vs上证) : {desc(agg[w]['exc'])}")
        logger.info(f"    有小鲍印证 : {desc(agg[w]['echo_exc'])}")
        logger.info(f"    无小鲍印证 : {desc(agg[w]['noecho_exc'])}")
    logger.info("\n⚠️ 样本小+非平稳，仅方向性参考；正超额≠可交易策略，需滚动样本外+更多样本复核。")

    if write and write_rows:
        rconn.executemany("UPDATE yuantu_buy_signals SET verify_return=?, verify_status='已回测' WHERE signal_node=?", write_rows)
        rconn.commit()
        logger.info(f"\n✅ 已回填 {len(write_rows)} 条 verify_return（{max(windows)}日超额）。")
    rconn.close(); mconn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--windows", default="5,10,20")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    run([int(x) for x in a.windows.split(",")], write=a.write)
