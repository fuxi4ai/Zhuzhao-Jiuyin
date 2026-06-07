#!/usr/bin/env python3
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import config
from lib.logger import get_logger
logger = get_logger(__name__)
"""
🕯️ yuantu_client.py — 渊图消费客户端（只读数据契约）

设计：数据耦合，不 import 渊图 py。只读 `行业研究/mapping/latest.json`（软链→canonical）
与 `scoring/*.json`。渊图改名只重指软链，本客户端无感（照搬渊图↔龙鱼 coupling 范式）。

提供：
  healthcheck()                 → 契约自检（节点/边/信号数，失败显眼报警非静默）
  get_signals(min_conf=0.7)     → 市场信号节点（_meta.market_signal.confidence≥阈值）
  beneficiaries(signal_id)      → 信号 N 跳邻域内的受益公司节点（中文名）
  scores()                      → yuantu_scoring 标的分（scoring/*.json）

用法:
  python3 yuantu_client.py health
  python3 yuantu_client.py signals [--min-conf 0.7] [--type supply_shock]
  python3 yuantu_client.py chain <signal_id>
"""
import json, argparse
from functools import lru_cache
from pathlib import Path

# 受益传导用的正向边（排除 competes_with 竞争者 / measured_by / is_a / evolves_from）
BENE_EDGES = {"supplies", "used_in", "enables", "part_of", "requires", "causes", "constrains"}
SIGNAL_CATS = {"demand_surge", "supply_shock", "persistent_imbalance"}
_PLEVEL = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


@lru_cache(maxsize=1)
def load_kg():
    p = Path(config.YUANTU_KG)
    if not p.exists():
        raise FileNotFoundError(f"渊图 latest.json 不存在: {p}（检查软链 / config.YUANTU_KG）")
    kg = json.loads(p.read_text(encoding="utf-8"))
    return kg


def _id2node():
    return {n["id"]: n for n in load_kg()["nodes"]}


def _best_source(node):
    """取节点最佳来源置信度档（P0<P1<P2）与最新 data_vintage。"""
    best_p, latest = None, None
    for ds in node.get("data_sources", []) or []:
        lvl = ds.get("confidence_level")
        if lvl in _PLEVEL and (best_p is None or _PLEVEL[lvl] < _PLEVEL[best_p]):
            best_p = lvl
        dv = ds.get("data_vintage")
        if dv and (latest is None or dv > latest):
            latest = dv
    return best_p, (latest or node.get("updated_at"))


def healthcheck():
    try:
        kg = load_kg()
    except Exception as e:
        return {"ok": False, "error": str(e), "contract": "yuantu-烛阴-v1"}
    nodes, edges = kg.get("nodes", []), kg.get("edges", [])
    sig = sum(1 for n in nodes if (n.get("_meta") or {}).get("market_signal"))
    ok = len(nodes) > 0 and sig > 0
    return {"ok": ok, "canonical_found": True, "node_count": len(nodes),
            "edge_count": len(edges), "signal_count": sig, "contract": "yuantu-烛阴-v1"}


def get_signals(min_conf=0.7, category=None):
    """返回市场信号节点列表。"""
    out = []
    for n in load_kg()["nodes"]:
        ms = (n.get("_meta") or {}).get("market_signal")
        if not ms:
            continue
        conf = ms.get("confidence", 0)
        cats = ms.get("categories") or []
        if conf < min_conf or not cats:
            continue
        if category and category not in cats:
            continue
        p, date = _best_source(n)
        out.append({
            "signal_id": n["id"],
            "categories": cats,
            "signal_conf": conf,
            "source_plevel": p,
            "date": date,
            "industry": _derive_industry(n),
            "description": (n.get("description") or "")[:200],
            "reason": ms.get("reason", ""),
        })
    out.sort(key=lambda x: (x["date"] or "", x["signal_conf"]), reverse=True)
    return out


def _derive_industry(node):
    """v1 行业名推断：取一跳内最近的 product/material 邻居名，否则用节点名/id。"""
    id2n = _id2node()
    for e in load_kg()["edges"]:
        for a, b in ((e["source"], e["target"]), (e["target"], e["source"])):
            if a == node["id"]:
                nb = id2n.get(b)
                if nb and nb.get("type") in ("product", "material") and nb.get("name"):
                    return nb["name"]
    return node.get("name") or node["id"]


@lru_cache(maxsize=1)
def _adjacency():
    adj = {}
    for e in load_kg()["edges"]:
        if e.get("type") not in BENE_EDGES:
            continue
        for a, b in ((e["source"], e["target"]), (e["target"], e["source"])):
            adj.setdefault(a, []).append((b, e.get("type")))
    return adj


def beneficiaries(signal_id, max_depth=3):
    """信号节点 N 跳无向邻域内的受益公司节点（排除竞争边）。"""
    adj = _adjacency()
    id2n = _id2node()
    seen = {signal_id}
    frontier = [(signal_id, 0, [])]
    hits = {}
    while frontier:
        nid, d, path = frontier.pop()
        if d >= max_depth:
            continue
        for tgt, et in adj.get(nid, []):
            if tgt in seen:
                continue
            seen.add(tgt)
            npath = path + [et]
            tn = id2n.get(tgt)
            if tn and str(tgt).startswith("company_"):
                if tgt not in hits:
                    p, _ = _best_source(tn)
                    hits[tgt] = {"company_id": tgt, "name": tn.get("name"),
                                 "hop": d + 1, "path": "→".join(npath), "source_plevel": p}
            frontier.append((tgt, d + 1, npath))
    return sorted(hits.values(), key=lambda x: x["hop"])


def scores():
    """读 scoring/*.json 标的分（含 ts_code）。"""
    out = {}
    sdir = Path(config.YUANTU_SCORES)
    if not sdir.exists():
        return out
    for f in sdir.glob("*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        items = d.values() if isinstance(d, dict) else d
        for it in (items or []):
            if isinstance(it, dict) and it.get("ts_code"):
                out[it["ts_code"]] = it
    return out


def main():
    ap = argparse.ArgumentParser(description="渊图消费客户端")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("health")
    ps = sub.add_parser("signals"); ps.add_argument("--min-conf", type=float, default=0.7); ps.add_argument("--type")
    pc = sub.add_parser("chain"); pc.add_argument("signal_id")
    a = ap.parse_args()
    if a.cmd == "health":
        logger.info(json.dumps(healthcheck(), ensure_ascii=False))
    elif a.cmd == "signals":
        sigs = get_signals(a.min_conf, a.type)
        logger.info(f"信号 {len(sigs)} 条（min_conf={a.min_conf}）")
        for s in sigs[:30]:
            logger.info(f"  [{s['date']}] {','.join(s['categories'])} conf={s['signal_conf']} "
                        f"{s['source_plevel']} | {s['industry']} | {s['signal_id']}")
    elif a.cmd == "chain":
        bens = beneficiaries(a.signal_id)
        logger.info(f"{a.signal_id} → 受益公司 {len(bens)} 个")
        for b in bens:
            logger.info(f"  hop{b['hop']} {b['name']} ({b['company_id']}) via {b['path']}")
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
