#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S2 risk_function 单测（PRD C3）：resolve_temp 四象限+边界 · 滚动分位正确性 · 与研究版抽样对齐。
跑法：python3 tools/test_risk_function.py（无 pytest 依赖，纯 assert；退出码 0=全过）"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import risk_function as rf

PASS = []


def ok(name, cond):
    assert cond, f"FAIL: {name}"
    PASS.append(name)


# ── 1 · resolve_temp 四象限 ──
ok("T0E0→calm", rf.resolve_temp(0, 0, 3) == ("calm", "平静"))
ok("T0E2→calm(环境不定级)", rf.resolve_temp(0, 2, 3)[0] == "calm")
ok("T1E0→alert无共振", rf.resolve_temp(1, 0, 3) == ("alert", "触发·无共振"))
ok("T1E1→resonance", rf.resolve_temp(1, 1, 3) == ("resonance", "共振1"))
ok("T2E3→共振3", rf.resolve_temp(2, 3, 3) == ("resonance", "共振3"))
# 边界：环境层全不可评（B3 缺数≠灭灯——不得默认成"无共振"）
ok("T1·环境全不可评→alert专用文案", rf.resolve_temp(1, 0, 0) == ("alert", "触发·环境层不可评"))
# 边界：部分可评 → 分母如实入文案
ok("T1E1/2→共振1/2", rf.resolve_temp(1, 1, 2) == ("resonance", "共振1/2"))
# v1 不走本函数
try:
    rf.resolve_temp(1, 0, 3, "v1")
    ok("v1应抛错", False)
except ValueError:
    ok("v1抛错√", True)

# ── 2 · _rolling_pct 手算对照（window=3, min_periods=2）──
d = ["d1", "d2", "d3", "d4", "d5"]
v = [10, 20, 15, 5, 30]
p = rf._rolling_pct(d, v, window=3, min_periods=2)
ok("d1不足min_periods不出数", "d1" not in p)
ok("d2: win[10,20] v=20 →1.0", abs(p["d2"] - 1.0) < 1e-9)
ok("d3: win[10,20,15] v=15 →2/3", abs(p["d3"] - 2 / 3) < 1e-9)
ok("d4: win[20,15,5] v=5 →1/3", abs(p["d4"] - 1 / 3) < 1e-9)
ok("d5: win[15,5,30] v=30 →1.0", abs(p["d5"] - 1.0) < 1e-9)
# None 值跳过
p2 = rf._rolling_pct(["a", "b", "c"], [1, None, 2], window=3, min_periods=2)
ok("None跳过后c可评", "c" in p2 and "b" not in p2)

# ── 3 · 与研究版抽样对齐（真库集成；库缺则跳过并标注）──
import config
idb = config.OUTPUT_ROOT / "回调级别判别" / "index_research.db"
uni = config.DATABASE_ROOT.parent / "AI4ME" / "回调级别判别" / "outputs" / "universe_fixed.json"
if idb.exists():
    pa, last = rf.a6_percentiles(str(idb))
    # 研究版回放（bt_combo 20260618/0714/0717 → p100/p87/p91，四舍五入到整数百分位）
    for dd, exp in (("20260618", 100), ("20260714", 87), ("20260717", 91)):
        got = round(pa[dd] * 100)
        ok(f"A6@{dd}≈p{exp}(得p{got})", abs(got - exp) <= 1)
    ok("A6 last_date=库尾", last >= "20260717")
else:
    print("SKIP: index_research.db 不在（A6 抽样对齐未跑）")
if uni.exists():
    pb, lastb, shb = rf.b6_percentiles(config.MARKET_DB, str(uni))
    for dd, exp in (("20260714", 100), ("20260717", 98)):
        got = round(pb[dd] * 100)
        ok(f"B6@{dd}≈p{exp}(得p{got})", abs(got - exp) <= 1)
    # 0714 为全窗史高 63.9%（判别器/研究版双源）
    ok("B6 share 序列尾值≈59.6%(0717)", shb is not None and abs(shb - 0.596) < 0.01)
else:
    print("SKIP: universe_fixed.json 不在（B6 抽样对齐未跑）")

print(f"✅ {len(PASS)}/{len(PASS)} 全过：", "、".join(PASS[:6]) + f" …共{len(PASS)}项")
