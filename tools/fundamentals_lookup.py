#!/usr/bin/env python3
"""
fundamentals_lookup.py — 烛照九阴 → 共享基本面库（白泽 owner）只读查询。

数据分层（G-X30）：渊图=关系/方向/传导；**共享基本面库**=纯度/弹性（慢变 P0 年报）。
本模块按 ts_code 查白泽产出的共享库 `Database/宏观-大宗商品/business_breakdown.db` 的
`fundamentals` 表（品种×公司：纯度/自产/长单/需求弹性/营收占比），命中返回白泽口径明细、
未命中返回 None（由调用方回退到渊图图谱传导度）。

铁律：**只读**。本模块对共享库不含任何写操作（库 owner=白泽，烛照九阴只读）。
"""
import os, sys, sqlite3, functools
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

SHARED_FUNDAMENTALS_DB = os.path.join(config.DATABASE_ROOT, "宏观-大宗商品", "business_breakdown.db")


@functools.lru_cache(maxsize=1)
def _conn():
    if not os.path.exists(SHARED_FUNDAMENTALS_DB):
        return None
    # 只读 URI 连接（物理上禁写）
    return sqlite3.connect(f"file:{SHARED_FUNDAMENTALS_DB}?mode=ro", uri=True)


def lookup(ts_code):
    """ts_code → 白泽口径基本面明细（命中取营收占比最高的品种行）；未命中或库缺 → None。
    返回 dict：{commodity, purity, revenue_ratio, demand_elasticity, self_produce,
              long_term, data_source, report_period}。"""
    if not ts_code:
        return None
    c = _conn()
    if c is None:
        return None
    try:
        rows = c.execute(
            "SELECT commodity, purity, revenue_ratio, demand_elasticity, self_produce, "
            "long_term, data_source, report_period "
            "FROM fundamentals WHERE ts_code=? AND purity IS NOT NULL "
            "ORDER BY COALESCE(revenue_ratio,0) DESC, COALESCE(purity,0) DESC", (ts_code,)
        ).fetchall()
    except Exception:
        return None
    if not rows:
        return None
    r = rows[0]
    return {"commodity": r[0], "purity": r[1], "revenue_ratio": r[2],
            "demand_elasticity": r[3], "self_produce": r[4], "long_term": r[5],
            "data_source": r[6], "report_period": r[7]}


def fmt(ts_code):
    """详情卡用的紧凑白泽口径文案；未命中返回空串。"""
    d = lookup(ts_code)
    if not d:
        return ""
    bits = [f"{d['commodity']}"]
    if d.get("purity") is not None:
        bits.append(f"纯度{d['purity']}")
    if d.get("revenue_ratio") is not None:
        bits.append(f"营收占比{d['revenue_ratio']:.0%}")
    if d.get("demand_elasticity") is not None:
        bits.append(f"需求弹性{d['demand_elasticity']}")
    return "白泽口径：" + "·".join(bits)


if __name__ == "__main__":
    import sys
    for ts in (sys.argv[1:] or ["300502.SZ", "002463.SZ", "002916.SZ", "999999.SZ"]):
        print(ts, "→", lookup(ts) or "未命中（回退图谱传导度）")
