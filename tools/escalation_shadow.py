#!/usr/bin/env python3
"""🕯️ escalation_shadow.py — A3「信息升级重置时钟」影子模式（PRD 2026-07-16）

动机（回测/案例依据）：
  - 信息差载体是语义升级而非提及次数（AI4ME/CC-信号信息差假设回测-20260716.md）；
  - 案例：concept_LaserShortage2026 04-15 兑现 +70% 转暗后，6 月 EML 提价/锁产能升级链
    零新信号——升级被困在 persistent/暗态里（AI4ME/CC-复盘日报信号逻辑综合评估-20260716.md §三.4）。

影子模式（Doctor 批 2026-07-16，7 天复核期）：
  - 只写独立表 recap.escalation_shadow + 落 docs/escalation_shadow_{date}.md 日志；
  - **不**改 yuantu_buy_signals、**不**进日报展示、**不**影响 closure/gap 任何现有逻辑；
  - 复核通过后另行放开（届时才按 PRD 给 escalation 信号进强信号栏）。

升级判定（冻结初版·PRD §2-A3）——同一 signal_node 的 description 摘要量值出现：
  ① 缺口/短缺百分比新高 ② 涨价/提价幅度新档 ③ 交期数值延长 ④ 锁定年限延后。
  纯复述/同数值不触发。
"""
import hashlib
import re
import sqlite3
from datetime import datetime
from pathlib import Path

DDL = """
CREATE TABLE IF NOT EXISTS escalation_shadow (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  signal_node TEXT,
  observed_at TEXT,
  digest TEXT,
  gap_pct REAL, hike_pct REAL, lead_weeks REAL, lock_year INTEGER,
  escalated INTEGER DEFAULT 0,
  kinds TEXT,
  evidence TEXT
);
CREATE INDEX IF NOT EXISTS idx_esc_node ON escalation_shadow(signal_node, observed_at);
"""

_NUM = r"(\d+(?:\.\d+)?)"


def extract_markers(text: str) -> dict:
    """从节点描述抽四类量值（取各类最大值；抽不到=None）。"""
    t = text or ""
    def _max(pat, cast=float):
        vals = [cast(m) for m in re.findall(pat, t)]
        return max(vals) if vals else None
    gap = _max(rf"(?:缺口|短缺|缺货)[^。；;，,]{{0,16}}?{_NUM}\s*%")
    hike = _max(rf"(?:涨价|提价|上调|上涨|涨幅)[^。；;，,]{{0,12}}?{_NUM}\s*%")
    # 交期：N 周 / N 个月（月×4.3 归一为周）
    lead_w = _max(rf"(?:交期|交货周期|交货期)[^。；;，,]{{0,16}}?{_NUM}\s*周")
    lead_m = _max(rf"(?:交期|交货周期|交货期)[^。；;，,]{{0,16}}?{_NUM}\s*个?月")
    lead = max([x for x in (lead_w, (lead_m * 4.3) if lead_m else None) if x is not None], default=None)
    lock = _max(rf"(?:锁定|锁至|长协)[^。；;]{{0,24}}?(20\d\d)", cast=int)
    return {"gap_pct": gap, "hike_pct": hike, "lead_weeks": lead, "lock_year": lock}


def detect(prev: dict | None, cur: dict) -> tuple[bool, list[str]]:
    """prev/cur 为 extract_markers 输出。返回 (是否升级, 类别列表)。首见不算升级。"""
    if prev is None:
        return False, []
    kinds = []
    rules = [("缺口扩大", "gap_pct"), ("涨价加码", "hike_pct"),
             ("交期延长", "lead_weeks"), ("锁定延后", "lock_year")]
    for label, k in rules:
        p, c = prev.get(k), cur.get(k)
        if c is not None and (p is None or c > p):
            # p 为 None 时：该维度首次出现量值——旧文无此维度、新文给出＝新信息，计升级
            kinds.append(label if p is not None else f"{label}(新维度)")
    return (len(kinds) > 0), kinds


def run_shadow(recap_db: str, kg_nodes: list, project_root: str, dry_run: bool = False) -> dict:
    """对 kg_nodes（[{id, description}]）跑影子检测。返回统计。不改 yuantu_buy_signals。"""
    conn = sqlite3.connect(recap_db)
    conn.executescript(DDL)
    now = datetime.now().isoformat(timespec="seconds")
    stats = {"seen": 0, "baseline_new": 0, "escalated": 0, "unchanged": 0}
    events = []
    for n in kg_nodes:
        node, desc = n.get("id"), n.get("description") or ""
        if not node:
            continue
        stats["seen"] += 1
        digest = hashlib.sha1(desc.encode()).hexdigest()
        cur = extract_markers(desc)
        row = conn.execute(
            "SELECT digest, gap_pct, hike_pct, lead_weeks, lock_year FROM escalation_shadow "
            "WHERE signal_node=? ORDER BY observed_at DESC, id DESC LIMIT 1", (node,)).fetchone()
        if row and row[0] == digest:
            stats["unchanged"] += 1
            continue
        prev = None if row is None else {"gap_pct": row[1], "hike_pct": row[2],
                                         "lead_weeks": row[3], "lock_year": row[4]}
        esc, kinds = detect(prev, cur)
        if row is None:
            stats["baseline_new"] += 1
        if esc:
            stats["escalated"] += 1
            events.append({"node": node, "kinds": kinds, "prev": prev, "cur": cur})
        if not dry_run:
            conn.execute(
                "INSERT INTO escalation_shadow (signal_node,observed_at,digest,gap_pct,hike_pct,"
                "lead_weeks,lock_year,escalated,kinds,evidence) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (node, now, digest, cur["gap_pct"], cur["hike_pct"], cur["lead_weeks"],
                 cur["lock_year"], 1 if esc else 0, ",".join(kinds), desc[:300]))
    if not dry_run:
        conn.commit()
        # 影子日志（仅升级日或首日基线落一行摘要）
        try:
            d = datetime.now().strftime("%Y-%m-%d")
            p = Path(project_root) / "docs" / f"escalation_shadow_{d}.md"
            lines = [f"# escalation 影子日志 {d}",
                     f"扫描 {stats['seen']} · 新基线 {stats['baseline_new']} · 无变化 {stats['unchanged']} · **升级候选 {stats['escalated']}**", ""]
            for e in events:
                lines.append(f"- **{e['node']}** ｜ {'、'.join(e['kinds'])} ｜ prev={e['prev']} → cur={e['cur']}")
            lines.append("\n> 影子模式：未写 yuantu_buy_signals、未进日报。7 天复核（约 07-23）后由 Doctor 决定是否放开。")
            p.write_text("\n".join(lines), encoding="utf-8")
        except Exception:
            pass
    conn.close()
    return stats
