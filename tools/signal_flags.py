#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🕯️ signal_flags.py — 信号「不做」判据单一真源

目前一条：**已无信息差·不做** —— price_driven（涨价逻辑）× info_gap_level=1（gap1）。
依据：烛照标的级回测实证（2026-06-16）——涨价一旦公开，供需摆明面、信息差归零，
超额随之消失（gap1·涨价 45%/均超额≈0~负；gap3 才有 edge）。详见
`permanent/经验库.md` [EXP-20260616-001-S] · `通用教训.md` G-X16。

落点：方案 B 读时渲染（Doctor 2026-06-16 拍板）——本模块只给判据，不落库、不动源表、不动 schema；
backtest 用 SQL 谓词把 gap1·涨价从可交易胜率分母剔除并单列；其它消费端用 no_trade_reason() 打标。
可逆：删本文件 + 回退 backtest 两处引用即可。范围 v1 = gap1；如需扩 gap2 改这一处即可。

用法:
  from signal_flags import no_trade_reason, NO_INFO_GAP_SQL
  r = no_trade_reason("price_driven", 1)   # -> "已无信息差·不做"
"""

NO_INFO_GAP_REASON = "已无信息差·不做"

# SQL 谓词（供 backtest 过滤/单列；与 no_trade_reason 同源同义）
NO_INFO_GAP_SQL = "(logic_type='price_driven' AND info_gap_level=1)"


def no_trade_reason(logic_type, info_gap_level):
    """返回「不做」理由字符串；可做则 None。
    判据 v1：price_driven × gap1（涨价已公开=无信息差）。"""
    try:
        gap = int(info_gap_level) if info_gap_level is not None else None
    except (TypeError, ValueError):
        gap = None
    if logic_type == "price_driven" and gap == 1:
        return NO_INFO_GAP_REASON
    return None


if __name__ == "__main__":
    # 自检：对照 recap.db 数出会被标「已无信息差·不做」的样本
    import os as _os, sys as _sys, sqlite3
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    import config
    c = sqlite3.connect(config.RECAP_DB)
    n = c.execute(f"SELECT COUNT(*) FROM stock_tracking WHERE target_pool='own' "
                  f"AND hit_3d IS NOT NULL AND {NO_INFO_GAP_SQL}").fetchone()[0]
    print(f"判据命中（own·进分母·gap1×涨价）: {n} 行 → 标「{NO_INFO_GAP_REASON}」、剔出可交易分母")
    # 几个判据点测
    for lg, g in [("price_driven", 1), ("price_driven", 2), ("event_driven", 1), ("price_driven", None)]:
        print(f"  no_trade_reason({lg!r},{g}) = {no_trade_reason(lg, g)!r}")
    c.close()
