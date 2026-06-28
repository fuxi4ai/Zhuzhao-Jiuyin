#!/usr/bin/env python3
"""
fundamentals_lookup.py — 烛照九阴 → 共享基本面库（白泽 owner）只读查询。

数据分层（G-X30）：渊图=关系/方向/传导；**共享基本面库**=纯度/弹性（慢变 P0 年报）。
本模块按 ts_code 查白泽产出的共享库 `Database/宏观-大宗商品/business_breakdown.db` 的
`benefit_relations` 表（原 fundamentals·2026-06-29 改名；品种×公司：纯度/自产/长单/需求弹性/营收占比），
命中返回白泽口径明细、未命中返回 None（由调用方回退到渊图图谱传导度）。

领域分库（2026-06-29）：**公司六维分改读龙鱼库**（公司级真源，`Database/龙鱼-标的分析库/records/`），
不再读大宗库 stock_scores 镜像（已弃用）。受益关系仍读白泽 benefit_relations。

铁律：**只读**。本模块对两库均不含任何写操作（受益关系 owner=白泽 / 公司评分 owner=龙鱼研究侧，烛照九阴只读）。
"""
import os, sys, json, glob, sqlite3, functools
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

SHARED_FUNDAMENTALS_DB = os.path.join(config.DATABASE_ROOT, "宏观-大宗商品", "business_breakdown.db")
LONGYU_RECORDS = os.path.join(config.DATABASE_ROOT, "龙鱼-标的分析库", "records")  # 公司级真源


def _longyu_six(ts_code):
    """龙鱼库（公司级真源）取 latest 那次六维总分。返回 (six_total, six_max, analysis_date) 或 None。
    领域分库后取代旧 stock_scores 镜像读法；schema 同白泽 lib_public_read.lookup_company。"""
    if not ts_code:
        return None
    hits = glob.glob(os.path.join(LONGYU_RECORDS, f"{ts_code}_*.json"))
    if not hits:
        return None
    try:
        with open(hits[0], encoding="utf-8") as f:
            rec = json.load(f)
    except Exception:
        return None
    analyses = rec.get("analyses") or []
    if not analyses:
        return None
    latest = rec.get("latest")
    a = next((x for x in analyses if x.get("analysis_date") == latest), analyses[-1])
    if a.get("total") is None:
        return None
    return (a.get("total"), 100, a.get("analysis_date"))


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
    d = {}
    try:
        rows = c.execute(
            "SELECT commodity, purity, revenue_ratio, demand_elasticity, self_produce, "
            "long_term, data_source, report_period "
            "FROM benefit_relations WHERE ts_code=? AND purity IS NOT NULL "
            "ORDER BY COALESCE(revenue_ratio,0) DESC, COALESCE(purity,0) DESC", (ts_code,)
        ).fetchall()
        if rows:
            r = rows[0]
            d.update({"commodity": r[0], "purity": r[1], "revenue_ratio": r[2],
                      "demand_elasticity": r[3], "self_produce": r[4], "long_term": r[5],
                      "data_source": r[6], "report_period": r[7]})
    except Exception:
        pass
    # 公司六维分（领域分库 2026-06-29：读龙鱼库公司级真源，取代旧 stock_scores 镜像；
    # 独立于纯度——纯度可 null(待采)但六维仍有，故不受 purity 过滤影响）
    six = _longyu_six(ts_code)
    if six:
        d["six_total"], d["six_max"], d["six_generated"] = six
    return d or None


def fmt(ts_code):
    """详情卡用的紧凑白泽口径文案（含周更六维分·与弹性同源 ts_code 一起取）；未命中返回空串。"""
    d = lookup(ts_code)
    if not d:
        return ""
    bits = []
    if d.get("commodity"):
        bits.append(f"{d['commodity']}")
    if d.get("purity") is not None:
        bits.append(f"纯度{d['purity']}")
    if d.get("revenue_ratio") is not None:
        bits.append(f"营收占比{d['revenue_ratio']:.0%}")
    if d.get("demand_elasticity") is not None:
        bits.append(f"需求弹性{d['demand_elasticity']}")
    head = ("白泽口径：" + "·".join(bits)) if bits else ""
    six = f"六维{d['six_total']}" if d.get("six_total") is not None else ""
    return "·".join(x for x in (head, six) if x)


if __name__ == "__main__":
    import sys
    for ts in (sys.argv[1:] or ["300502.SZ", "002463.SZ", "002916.SZ", "999999.SZ"]):
        print(ts, "→", lookup(ts) or "未命中（回退图谱传导度）")
