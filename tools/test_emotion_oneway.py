#!/usr/bin/env python3
"""test_emotion_oneway.py — 情绪周期单向不变量 + 无后变更 负向测试（2026-09-16 Doctor 修复立）

断言组：
  A · 单向不变量：季节序列仅允许 春→夏→秋→冬→春 前进/循环，任何反向跳变即 FAIL
  B · 无改写：corrected 恒 False（报错撤回触发器已移除）
  C · 因果稳定（无后变更）：抽样日期按「截止当日数据」截断重算，season 与全历史计算逐日一致
  D · 极寒一致性：extreme=True 的行 season 必为冬

用法：ZZJY_DATABASE_ROOT=<挂载> python3 tools/test_emotion_oneway.py
只读 market_data.db；截断副本落 /tmp。
"""
import os, sys, sqlite3, tempfile, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import config
sys.path.insert(0, os.path.join(HERE, "..", ".."))
from tools.emotion_engine_v2 import compute

ORDER = ["春", "夏", "秋", "冬"]


def main():
    fails = []

    def check(name, cond, detail=""):
        print(f"{'✓' if cond else '✗'} {name}" + (f" · {detail}" if detail else ""))
        if not cond:
            fails.append(name)

    md = sqlite3.connect(f"file:{config.MARKET_DB}?mode=ro", uri=True)
    out = compute(md)
    dates = [r["date"] for r in out]
    print(f"全历史 {len(out)} 日 [{dates[0]}→{dates[-1]}]")

    # A · 单向不变量
    viol = []
    prev = None
    for r in out:
        s = r["season"]
        if prev is not None and s != prev:
            if ORDER.index(s) != (ORDER.index(prev) + 1) % 4:
                viol.append((prev, s, r["date"]))
        prev = s
    check("A 无反向跳变", not viol, f"{len(viol)} 处：{viol[:5]}")

    # B · 无改写
    corr = [r["date"] for r in out if r.get("corrected")]
    check("B corrected 恒 False", not corr, f"{len(corr)} 处 {corr[:5]}")

    # D · 极寒一致性
    bad_ext = [r["date"] for r in out if r.get("extreme") and r["season"] != "冬"]
    check("D 极寒必在冬", not bad_ext, f"{len(bad_ext)} 处 {bad_ext[:5]}")

    # C · 因果稳定：抽样日期截断重算
    # 采样：每 ~25 日 + 历史修正段附近日期（20250325/20250428/20250613/20251106/20260309/20260717/20260730/20260904/20260910 的段尾+1）
    # 采样：修正段尾次日 + 最新日（全量截断重算慢〔挂载盘多小查询〕，6 点覆盖关键段）
    sample = ["20250326", "20250621", "20251113", "20260324", "20260721", "20260916"]
    # 建截断库副本（4 张指标表）
    tables = ["limit_list_daily", "daily_market", "stock_daily", "theme_etf_daily"]
    conn = sqlite3.connect(f"file:{config.MARKET_DB}?mode=ro", uri=True)
    n_ok = 0
    for d in sample:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        tc = sqlite3.connect(tmp.name)
        for t in tables:
            try:
                rows = conn.execute(f"SELECT * FROM {t} WHERE trade_date <= ?", (d,)).fetchall()
            except sqlite3.OperationalError as e:
                continue
            cols = [c[1] for c in conn.execute(f"PRAGMA table_info({t})")]
            tc.execute(f"CREATE TABLE {t} ({', '.join(c for c in cols)})")
            tc.executemany(f"INSERT INTO {t} VALUES ({','.join('?'*len(cols))})", rows)
        tc.commit()
        out_t = compute(tc)
        tc.close(); os.unlink(tmp.name)
        full = {r["date"]: r["season"] for r in out}
        got = {r["date"]: r["season"] for r in out_t}
        if got.get(d) == full.get(d):
            n_ok += 1
        else:
            check(f"C 截断重算 {d}", False, f"全历史={full.get(d)} 截断={got.get(d)}")
    check("C 因果稳定（无后变更）", n_ok == len(sample), f"抽样 {len(sample)} 日全部一致 · 实核 {n_ok}")

    print(f"\n{'✅ 全过' if not fails else '❌ 失败 ' + str(fails)} · 断言 4 组（C 抽样 {len(sample)} 日）· 失败 {len(fails)}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
