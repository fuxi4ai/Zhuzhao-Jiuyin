#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🕯️ logic_taxonomy.py — logic_type 规范化单一真源

为什么需要：industry_signals.logic_type 中英混杂（28 变体），yuantu signal_type 另带
persistent_imbalance，分组被稀释成一堆 n=1~4 噪声格。本模块把所有变体归一到 10 个 canon，
供 populate 写 stock_tracking 时调用。**只读映射、不碰源表**——industry_signals 原值零改动，
stock_tracking.logic_type 写归一值，raw 仍可经 signal_id→industry_signals 还原（可逆无损）。

落点决策见 PRD `2026-06-15_标的级胜率回测`；归并方案 Doctor 2026-06-16 拍板（10 类）。

用法:
  from logic_taxonomy import normalize
  canon = normalize("涨价逻辑")   # -> "price_driven"
  python3 tools/logic_taxonomy.py   # 跑自检（覆盖/计数）
"""

# canon -> [该 canon 收纳的所有原始变体]（canon 自身也算一个变体）
_GROUPS = {
    "price_driven":         ["price_driven", "涨价逻辑", "price_increase", "涨价驱动", "涨价"],
    "event_driven":         ["event_driven", "事件催化", "事件驱动"],
    "demand_surge":         ["demand_surge", "需求爆发", "demand_explosion"],
    "tech_innovation":      ["tech_innovation", "技术升级"],
    "supply_shock":         ["supply_shock", "supply_shortage", "供给紧缺", "capacity_bottleneck"],
    "emotion_cycle":        ["emotion_cycle", "情绪周期", "sentiment"],
    "capacity_policy":      ["capacity_policy", "policy_driven"],
    "trend":                ["trend"],
    "persistent_imbalance": ["persistent_imbalance"],
    "other":                ["other", "logic_driven", "信息差", "cost_advantage", "asset_revaluation"],
}

CANON = list(_GROUPS.keys())

# raw -> canon 反查表
CANON_MAP = {raw: canon for canon, raws in _GROUPS.items() for raw in raws}


def normalize(logic):
    """变体 -> canon。None/空 保持为 None（缺失≠other）；未知非空值兜底 'other'。"""
    if logic is None:
        return None
    key = str(logic).strip()
    if not key:
        return None
    return CANON_MAP.get(key, "other")


if __name__ == "__main__":
    # 自检：对照 recap.db 实际变体，验证全覆盖 + 计数收敛
    import os as _os, sys as _sys, sqlite3
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    import config
    c = sqlite3.connect(config.RECAP_DB)
    from collections import Counter
    raw_ct, canon_ct, unknown = Counter(), Counter(), set()
    for tbl, col in [("industry_signals", "logic_type"), ("yuantu_buy_signals", "signal_type")]:
        for (v,) in c.execute(f"SELECT {col} FROM {tbl}"):
            first = (v or "").split(",")[0].strip() or None  # yuantu 取逗号前第一段，与 populate 一致
            raw_ct[first] += 1
            canon = normalize(first)
            canon_ct[canon] += 1
            if first and first not in CANON_MAP:
                unknown.add(first)
    c.close()
    print(f"原始变体数: {len([k for k in raw_ct if k])}  总行(含None): {sum(raw_ct.values())}")
    print(f"\ncanon 收敛 -> {len([k for k in canon_ct if k])} 类:")
    for k, v in canon_ct.most_common():
        print(f"  {v:>4}  {k}")
    if unknown:
        print(f"\n⚠ 未覆盖变体(兜底进 other): {sorted(unknown)}")
    else:
        print("\n✅ 所有非空变体均显式映射，无兜底漏网")
