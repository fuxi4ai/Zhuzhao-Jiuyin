#!/usr/bin/env python3
"""自复盘 · 输入包（PRD「烛照九阴自复盘取代课件」R3 · 2026-11-17）

把当日自复盘要用的独立数据收成一个 JSON：
  1. V.V. 的只读输入工具产出的外部包（美股锚、外围、主线 ETF 最新行、资讯快照）；
  2. 本地确认块：各主线对沪深 300 的 5 日、20 日超额，以及主线对应美股锚的 20 日超额。

不读课件，不读任何课件派生表；只读行情库。取不到的字段写进 gaps，不补值。
窗口按交易日历取：行情缺一天、篮子缺一只成员，对应读数为空并记缺口，不换成别的窗口或别的权重。
输出默认落 data/self_recap/<交易日>/inputs.json；同名文件已存在则拒绝覆盖。

V.V. 的工具拒绝把文件写进路径带「claude」开头目录的位置（GOTCHAS ERR-20261117-001），
所以这里不传 --output，接它的标准输出。
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import argparse, datetime, hashlib, json, sqlite3, subprocess
from pathlib import Path
import config

_sys.path.insert(0, str(config.PROJECT_ROOT / "scripts"))
from fetch_theme_etf import THEME_ETF, BENCHMARK
from fetch_us_anchor import THEME_US, BENCHMARK_US

# V.V. 的输入工具。沙箱里挂载路径不同，可用环境变量 ZZJY_VV_TOOL 覆盖。
VV_TOOL = Path(_os.environ.get("ZZJY_VV_TOOL") or
               "/Users/lunarabbit/Documents/Codex/Project Mirror/烛照九阴日报/skills/anchor-follow/scripts/build_inputs.py")
OUT_ROOT = config.PROJECT_ROOT / "data" / "self_recap"


class InputError(RuntimeError):
    pass


def _ro(path):
    conn = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    conn.execute("PRAGMA query_only=ON")
    return conn


def run_vv_tool(tool=VV_TOOL, database_root=None):
    """跑 V.V. 的输入工具，取标准输出。失败即报错，不退回任何替代来源。"""
    if not Path(tool).is_file():
        raise InputError(f"VV_TOOL_MISSING: {tool}")
    cmd = [_sys.executable, str(tool)]
    if database_root:
        cmd += ["--database-root", str(database_root)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise InputError(f"VV_TOOL_FAILED rc={r.returncode}: {(r.stdout or r.stderr).strip()[:300]}")
    try:
        pack = json.loads(r.stdout)
    except json.JSONDecodeError as e:
        raise InputError(f"VV_TOOL_BAD_JSON: {e}")
    if pack.get("lesson_dependency") is not False:
        raise InputError("VV_TOOL_LESSON_DEPENDENCY: 外部包没有声明 lesson_dependency=false")
    return pack


def _open_days(conn, date, n):
    """交易日历里截至 date（含）的最近 n 个开市日。日历读不到、date 不是开市日、不足 n 天 → None。
    窗口由日历定，不由「哪些天恰好有行情」定：行情缺一天，窗口不会跟着缩短。"""
    try:
        rows = conn.execute("SELECT cal_date FROM trade_cal WHERE is_open=1 AND cal_date<=? "
                            "ORDER BY cal_date DESC LIMIT ?", (date, n)).fetchall()
    except sqlite3.Error:
        return None
    days = sorted(str(r[0]) for r in rows)
    if len(days) < n or days[-1] != date:
        return None
    return days


def _excess(series, bench, days):
    """days 这几天的超额之和（百分点）。返回 (数值, 缺数的日期列表)；有任何一天缺数则数值为 None。"""
    if not days:
        return None, []
    miss = [d for d in days if series.get(d) is None or bench.get(d) is None]
    if miss:
        return None, miss
    return round(sum(series[d] - bench[d] for d in days), 2), []


def _basket(vals):
    """篮子取等权均值；任何一只成员没有数，篮子就没有数（不拿剩下的成员冒充原篮子）。"""
    if not vals or any(v is None for v in vals):
        return None
    return round(sum(vals) / len(vals), 2)


def local_block(market_db, date=None):
    """本地确认块。date 为 A 股交易日 YYYYMMDD；缺省取行情库最新一日。"""
    gaps = []
    conn = _ro(market_db)
    try:
        if date is None:
            date = conn.execute("SELECT MAX(trade_date) FROM daily_market").fetchone()[0]
        row = conn.execute(
            "SELECT sh_close, sh_pct_chg, sz_pct_chg, cyb_pct_chg, volume_trillion "
            "FROM daily_market WHERE trade_date=?", (date,)).fetchone()
        if row is None:
            raise InputError(f"NO_MARKET_ROW: daily_market 没有 {date} 这一天")
        market = dict(zip(("sh_close", "sh_pct_chg", "sz_pct_chg", "cyb_pct_chg", "amount_trillion"), row))
        market["source"] = f"market_data.db:daily_market:{date}"
        for k, v in list(market.items()):
            if v is None:
                gaps.append(f"daily_market.{k}:{date}:missing")

        # A 股窗口：按交易日历取，不按行情表里有哪些天
        d20 = _open_days(conn, date, 20)
        d5 = d20[-5:] if d20 else None
        if d20 is None:
            gaps.append(f"trade_cal:{date}:window_unavailable")

        etf = {}
        for code, d, p in conn.execute(
                "SELECT etf_code, trade_date, pct_chg FROM theme_etf_daily WHERE trade_date<=? ORDER BY trade_date",
                (date,)):
            etf.setdefault(code, {})[d] = p
        bench = etf.get(BENCHMARK, {})
        for d in (d20 or [date]):
            if bench.get(d) is None:
                gaps.append(f"theme_etf_daily:{BENCHMARK}:{d}:missing")

        # 美股锚：只用严格早于 A 股交易日的美国日期（A 股当日收盘时，美股同日尚未收盘）。
        # 美国没有本地日历表，窗口取「任一只美股锚有行情的日期」的并集的最近 20 天：
        # 基准或某只锚在其中一天缺行，就是缺数，不让窗口悄悄往前挪。
        us = {}
        for tk, d, p in conn.execute(
                "SELECT ticker, trade_date, pct_chg FROM us_anchor_daily WHERE trade_date<? ORDER BY trade_date",
                (date,)):
            us.setdefault(tk, {})[d] = p
        us_bench = us.get(BENCHMARK_US, {})
        us_all = sorted({d for s in us.values() for d in s})
        us20 = us_all[-20:] if len(us_all) >= 20 else None
        if us20 is None:
            gaps.append(f"us_anchor_daily:{date}:window_unavailable")
        else:
            for d in us20:
                if us_bench.get(d) is None:
                    gaps.append(f"us_anchor_daily:{BENCHMARK_US}:{d}:missing")

        themes = []
        for name, codes in THEME_ETF.items():
            vals = {}
            for label, days in (("e5", d5), ("e20", d20)):
                per = []
                for c in codes:
                    v, miss = _excess(etf.get(c, {}), bench, days)
                    per.append(v)
                    if v is None:
                        why = f"{c}:{','.join(miss)}" if miss else "no_window"
                        gaps.append(f"theme_etf_daily:{name}:{date}:excess_unavailable:{label}:{why}")
                vals[label] = _basket(per)
            day = {c: etf.get(c, {}).get(date) for c in codes}
            for c, v in day.items():
                if v is None:
                    gaps.append(f"theme_etf_daily:{name}:{date}:pct_chg_unavailable:{c}")
            item = {"theme": name, "etf_codes": codes,
                    "e5": vals["e5"], "e20": vals["e20"],
                    "pct_chg": _basket(list(day.values())),      # 与 e5、e20 同一口径：成员等权
                    "pct_chg_members": day,
                    "source": f"market_data.db:theme_etf_daily:{'+'.join(codes)}:{date}"}
            a = THEME_US.get(name)
            if a:
                tk, kind = a[0], a[1]
                s = us.get(tk, {})
                last = max(s) if s else None
                ex20, miss = _excess(s, us_bench, us20)
                item["us_anchor"] = {"ticker": tk, "kind": kind,
                                     "ex20": ex20, "window_end": us20[-1] if us20 else None,
                                     "last_pct_chg": s.get(last), "last_date": last,
                                     "source": f"market_data.db:us_anchor_daily:{tk}:{last}"}
                if ex20 is None:
                    why = ",".join(miss) if miss else "no_window"
                    gaps.append(f"us_anchor_daily:{tk}:ex20_unavailable:{why}")
            else:
                item["us_anchor"] = None
            themes.append(item)
    finally:
        conn.close()
    return date, {"market": market, "themes": themes,
                  "windows": {"a5": [d5[0], d5[-1]] if d5 else None,
                              "a20": [d20[0], d20[-1]] if d20 else None,
                              "us20": [us20[0], us20[-1]] if us20 else None},
                  "basket_rule": "主线含多只 ETF 时取等权均值；任何一只缺数，该主线这一项为空并记缺口",
                  "us_clock": "美股锚只取严格早于 A 股交易日的美国日期"}, gaps


def build(date=None, tool=VV_TOOL, market_db=None, database_root=None):
    market_db = market_db or config.MARKET_DB
    # 外部工具与本脚本用同一个 Database 根，避免沙箱里各读各的
    pack = run_vv_tool(tool, database_root or config.DATABASE_ROOT)
    date, local, gaps = local_block(market_db, date)
    return {
        "schema_version": 2,      # 2：窗口按交易日历取；主线单日涨跌改为成员等权（1 时取的是第一只）
        "kind": "self_recap_inputs",
        "trade_date": date,
        "session": "盘后",
        "observed_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "lesson_dependency": False,
        "local": local,
        "local_gaps": gaps,
        "external_clock": "external 是运行时刻的最新行，可能晚于 A 股收盘；不是当日口径，"
                          "不得用来解释此前的 A 股表现，补做历史日期时不得当作当日证据",
        "external": pack,
    }


def main():
    ap = argparse.ArgumentParser(description="自复盘输入包（只读行情库 + V.V. 输入工具）")
    ap.add_argument("--date", help="A 股交易日 YYYYMMDD；缺省取行情库最新一日")
    ap.add_argument("--out-root", type=Path, default=OUT_ROOT)
    ap.add_argument("--stdout", action="store_true", help="只打印，不落盘")
    a = ap.parse_args()
    try:
        doc = build(a.date)
    except InputError as e:
        print(json.dumps({"status": "failed", "reason": str(e)}, ensure_ascii=False))
        raise SystemExit(2)
    raw = json.dumps(doc, ensure_ascii=False, indent=1, allow_nan=False) + "\n"
    if a.stdout:
        print(raw, end="")
        return
    out = a.out_root / doc["trade_date"] / "inputs.json"
    if out.exists():
        print(json.dumps({"status": "failed", "reason": f"OUTPUT_ALREADY_EXISTS: {out}"}, ensure_ascii=False))
        raise SystemExit(2)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(raw, encoding="utf-8")
    print(json.dumps({"status": "ok", "output": str(out), "trade_date": doc["trade_date"],
                      "themes": len(doc["local"]["themes"]), "local_gaps": len(doc["local_gaps"]),
                      "external_gaps": len(doc["external"].get("gaps", [])),
                      "sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
