#!/usr/bin/env python3
"""
backfill_direction.py — 给 yuantu_buy_signals 补 direction（多/空）方向场。

口径（Doctor 2026-06-25 复核后定稿 · 取代旧 trend+category 机械规则）：
  方向是语义判断，trend+category / 关键词机械规则均两头误判（实测把"供给约束=利好"误判成空、
  把成本通胀两面信号误判成空）。改「规则出候选 + 逐条核 KG 描述定案」：
  - 入库 direction 以 **CURATED_SHORT 核定空头清单**（按 signal_node id）为准：清单内=空，其余=多。
  - 判据：明确"供给过剩 / 库存出清 / 下游需求被压制"才是空（成本胜/过剩）；成本通胀类看受益
    标的——上游/可提价转嫁者＝提价胜＝多。Doctor 2026-06-25 定案：仅 id80/id96 两条为空。
  - auto 候选规则（_auto_candidate）只对**清单外**新信号生成"疑似空头"候选并打日志，**不直接入库**，
    供后续人工复核扩充 CURATED_SHORT。来源经 signal_node → KG node.id 对接（config.YUANTU_KG）。

新增列：direction TEXT / direction_src TEXT / direction_flip_date TEXT
（direction_flip_date 由 closure_engine 在检测到 多→空 翻向时回填，本脚本只建列、不填。）

只读 KG（外部源）；写 recap.db 走调用方的 /tmp 副本往返（本脚本只认 config.RECAP_DB）。
用法：python3 tools/backfill_direction.py [--dry-run]
"""
import os, sys, json, sqlite3, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def kg_index():
    with open(config.YUANTU_KG, encoding="utf-8") as f:
        kg = json.load(f)
    idx = {}
    for n in kg.get("nodes", []):
        if isinstance(n, dict) and "id" in n:
            idx[n["id"]] = n          # 存完整节点（_auto_candidate 需 name/description）
    return idx


# ── 核定空头清单（Doctor 2026-06-25 逐条核定 · 按 KG signal_node id）──
# 仅明确"供给过剩 / 下游需求被压制"者为空；成本通胀两面信号经受益标的判提价胜→多。
CURATED_SHORT = {
    "concept_SolarGlassOversupply",              # 光伏玻璃供给过剩（真过剩·价跌）
    "concept_ConsumerElectronicsMemoryHeadwind2026",  # 存储涨价压制消费电子出货（下游承压·出货-12.9%）
}

# auto 候选规则：只对清单外信号生成"疑似空头"候选打日志，不入库（供后续复核扩充清单）
_BEAR_KW = ["过剩", "积压", "出清", "滞销", "承压", "下降", "压制效应"]
def _auto_candidate(node):
    txt = (node.get("name", "") + " " + (node.get("description") or ""))
    if any(k in txt for k in ["过剩", "积压", "出清", "滞销"]):
        return True
    if "库存" in txt and ("新高" in txt or "累积" in txt):
        return True
    return False


def ensure_cols(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(yuantu_buy_signals)")}
    for name in ("direction", "direction_src", "direction_flip_date"):
        if name not in cols:
            conn.execute(f"ALTER TABLE yuantu_buy_signals ADD COLUMN {name} TEXT")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    idx = kg_index()
    conn = sqlite3.connect(config.RECAP_DB)
    ensure_cols(conn)

    rows = conn.execute("SELECT id, signal_node, industry_chain FROM yuantu_buy_signals").fetchall()
    n_long = n_short = 0
    candidates = []      # 清单外的疑似空头（auto），仅日志、不入库
    updates = []
    for sid, node, chain in rows:
        if node in CURATED_SHORT:
            d, src = "空", "curated:Doctor2026-06-25核定·过剩/下游承压"
            n_short += 1
        else:
            d, src = "多", "default·非核定空头"
            n_long += 1
            n = idx.get(node)
            if n and _auto_candidate(n):     # 清单外但疑似空头 → 候选待复核
                candidates.append((sid, chain, node))
        updates.append((d, src, sid))

    print(f"核定结果：多={n_long} 空={n_short}（核定清单 {len(CURATED_SHORT)} 条） 共={len(rows)}")
    if candidates:
        print(f"⚠️ 清单外疑似空头候选 {len(candidates)} 条（仅日志、未入库，待人工复核扩充 CURATED_SHORT）:")
        for sid, chain, node in candidates:
            print(f"   候选 id={sid} 【{chain}】 node={node}")
    if a.dry_run:
        for d, src, sid in updates:
            if d == "空":
                print(f"  空 id={sid} :: {src}")
        print("dry-run，未写库")
        return

    conn.executemany("UPDATE yuantu_buy_signals SET direction=?, direction_src=? WHERE id=?", updates)
    conn.commit()
    # 自校验
    nul = conn.execute("SELECT COUNT(*) FROM yuantu_buy_signals WHERE direction IS NULL OR direction=''").fetchone()[0]
    dom = [r[0] for r in conn.execute("SELECT DISTINCT direction FROM yuantu_buy_signals")]
    print(f"✅ 回填完成：空值={nul}（应0） 取值域={dom}（应⊆{{多,空}}）")
    conn.close()


if __name__ == "__main__":
    main()
