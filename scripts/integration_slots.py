#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""烛照九阴 · 隔日关注固定槽位（L3 · 2026-11-06 金融线脑暴17项）

给 docs/daily_integration_{YYYY-MM-DD}.json 补两个固定键：
  - "eal"       ：EAL 宏观惊奇（只读 Database/宏观研究体系/EAL/attribution.db 的 macro_* 表，
                  取 release_date ∈ [数据日-1, 数据日]（美东发布日 vs A 股数据日的隔夜对齐）的发布与标准化惊奇 z）
  - "starry_ne" ：渊图星空 Newly Emerged（只读 星空/render-archive 最新渊图渲染产物内嵌的 starscape-data，
                  取 signal_emerged_at == 数据日 的信号节点）
两键结构与 notes 条目一致 {"text","source","as_of"}；没有当日产物时 text="无"（如实，不编数）。
另：文件名格式断言——docs/ 下 daily_integration_*.json 的日期段必须是 YYYY-MM-DD（横杠），
     紧凑格式（20261028）会被生成器 iso(data_day) 读漏而渲染「今日无」（2026-10-28 实例）。

纪律：只读上游（attribution.db / 星空产物均不写）；本脚本只写烛照 docs/ 下当日 json 的两个键；
     上游缺件/不可读 → text="无（…不可读）"，不阻断日报（生成器 try/except 包裹）。

用法：
    python3 scripts/integration_slots.py --date 2026-10-28           # 补键并写回 docs/
    python3 scripts/integration_slots.py --date 2026-10-28 --dry-run # 只算不写
    python3 scripts/integration_slots.py --check-names               # 只做文件名格式断言
"""
import argparse
import datetime
import json
import re
import sqlite3
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parent.parent            # 烛照九阴/
try:
    sys.path.insert(0, str(_PROJECT_ROOT))
    import config as _cfg
    DATABASE_ROOT = Path(_cfg.DATABASE_ROOT)
    PROJECTS_ROOT = Path(_cfg.PROJECT_ROOT).parents[1]   # Claude/Projects/
except Exception:  # config 不可导入时按目录相对位置兜底（与 config 同假设：Projects/Financial/烛照九阴）
    DATABASE_ROOT = _PROJECT_ROOT.parents[3] / "Database"
    PROJECTS_ROOT = _PROJECT_ROOT.parents[1]

DOCS_DIR = _PROJECT_ROOT / "docs"
ATTR_DB = DATABASE_ROOT / "宏观研究体系" / "EAL" / "attribution.db"
STARRY_HTML = PROJECTS_ROOT / "星空" / "render-archive" / "yuantu-starry-skies-v3-full-inlined.html"

SLOT_KEYS = ("eal", "starry_ne")
_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_FNAME_RE = re.compile(r"^daily_integration_(.+)\.json$")


# ───────────────────────── 文件名格式断言 ─────────────────────────
def check_filenames(docs_dir: Path = DOCS_DIR):
    """返回不合 YYYY-MM-DD 格式的 daily_integration_*.json 文件名列表（空列表＝全部合格）。"""
    bad = []
    if not docs_dir.is_dir():
        return bad
    for p in sorted(docs_dir.glob("daily_integration_*.json")):
        m = _FNAME_RE.match(p.name)
        if not m or not _ISO_RE.match(m.group(1)):
            bad.append(p.name)
    return bad


def iso_date(d: str) -> str:
    """20261028 / 2026-10-28 → 2026-10-28；其它形态原样返回（由调用方校验）。"""
    d = (d or "").strip()
    if re.fullmatch(r"\d{8}", d):
        return f"{d[:4]}-{d[4:6]}-{d[6:]}"
    return d


# ───────────────────────── EAL 槽位 ─────────────────────────
def eal_slot(date_iso: str, db_path: Path = ATTR_DB) -> dict:
    src = "EAL·attribution.db（macro_event_releases ⋈ macro_standardized_surprises）"
    if not db_path.is_file():
        return {"text": "无（attribution.db 不可读）", "source": src, "as_of": date_iso}
    try:
        d1 = datetime.date.fromisoformat(date_iso)
    except ValueError:
        return {"text": "无（数据日格式非法）", "source": src, "as_of": date_iso}
    d0 = d1 - datetime.timedelta(days=1)
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            rows = con.execute(
                """
                SELECT r.release_date, r.event_family, r.reference_period,
                       s.factor_code, s.surprise_z,
                       (SELECT v.consensus_surprise_value FROM macro_release_values v
                         WHERE v.event_id = r.event_id ORDER BY v.metric_code LIMIT 1) AS cons_surprise
                FROM macro_event_releases r
                LEFT JOIN macro_standardized_surprises s ON s.event_id = r.event_id
                WHERE r.release_date BETWEEN ? AND ?
                ORDER BY r.release_date, r.event_family, s.factor_code
                """,
                (d0.isoformat(), d1.isoformat()),
            ).fetchall()
        finally:
            con.close()
    except sqlite3.Error as e:
        return {"text": f"无（attribution.db 查询失败：{type(e).__name__}）", "source": src, "as_of": date_iso}
    if not rows:
        # 「无」须可辨新鲜度：带 DB 最新发布日，区分「当日确无发布」与「DB 停更」（2026-11-06 独立复核建议）
        try:
            con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            try:
                _mx = con.execute("SELECT MAX(release_date) FROM macro_event_releases").fetchone()[0]
            finally:
                con.close()
        except sqlite3.Error:
            _mx = None
        return {"text": "无", "source": src, "as_of": date_iso,
                "note": f"窗口 {d0.isoformat()}~{d1.isoformat()} 无 macro_* 发布/惊奇记录 · DB 最新发布 {_mx or '未知'}"}
    parts = []
    for rel, fam, per, fac, z, cs in rows:
        seg = f"{fam} {per}（发布 {rel}）"
        if fac is not None and z is not None:
            seg += f" {fac} z={z:+.2f}"
        elif cs is not None:
            seg += f" 共识惊奇 {cs:+g}"
        else:
            seg += " 惊奇未标准化"
        parts.append(seg)
    return {"text": "；".join(parts), "source": src, "as_of": max(r[0] for r in rows)}


# ───────────────────────── 星空 NE 槽位 ─────────────────────────
_DATA_RE = re.compile(r'<script[^>]*id="starscape-data"[^>]*>(.*?)</script>', re.S)


def starry_ne_slot(date_iso: str, html_path: Path = STARRY_HTML) -> dict:
    src = "渊图星空·Newly Emerged（render-archive 渲染产物 starscape-data）"
    if not html_path.is_file():
        return {"text": "无（星空渲染产物不可读）", "source": src, "as_of": date_iso}
    try:
        s = html_path.read_text(encoding="utf-8")
        m = _DATA_RE.search(s)
        if not m:
            return {"text": "无（星空产物未含 starscape-data）", "source": src, "as_of": date_iso}
        data = json.loads(m.group(1))
        nodes = data.get("nodes") or []
    except Exception as e:
        return {"text": f"无（星空产物解析失败：{type(e).__name__}）", "source": src, "as_of": date_iso}
    hit = [n for n in nodes if isinstance(n, dict) and n.get("signal_emerged_at") == date_iso]
    prod_asof = datetime.date.fromtimestamp(html_path.stat().st_mtime).isoformat()
    if not hit:
        return {"text": "无", "source": src, "as_of": date_iso,
                "note": f"渲染产物（{prod_asof}）内无 signal_emerged_at={date_iso} 的信号节点"}
    names = []
    for n in hit:
        nm = n.get("name") or n.get("id") or "?"
        cats = "/".join(n.get("signal_categories") or [])
        names.append(f"{nm}" + (f"〔{cats}〕" if cats else ""))
    return {"text": f"新出现信号 {len(hit)} 个：" + "、".join(names), "source": src, "as_of": date_iso,
            "note": f"渲染产物日期 {prod_asof}"}


# ───────────────────────── 组装 / 写回 ─────────────────────────
def compute_slots(date_iso: str) -> dict:
    return {"eal": eal_slot(date_iso), "starry_ne": starry_ne_slot(date_iso)}


def ensure_slots(date: str, docs_dir: Path = DOCS_DIR, write_back: bool = True):
    """读 docs/daily_integration_{date}.json，补 eal / starry_ne 两键。
    返回 (integration_dict_or_None, slots, info)：
      - 文件存在：返回补键后的 dict（write_back=True 且内容有变则写回）
      - 文件不存在：返回 None（不代建文件——缺件是摘录步的事实，不掩盖），slots 仍算出
    info 含 filename_warning（同日存在紧凑格式文件名时）。"""
    date_iso = iso_date(date)
    slots = compute_slots(date_iso)
    info = {"path": None, "written": False, "filename_warning": None}
    target = docs_dir / f"daily_integration_{date_iso}.json"
    compact = docs_dir / f"daily_integration_{date_iso.replace('-', '')}.json"
    if compact.exists():
        info["filename_warning"] = (f"{compact.name} 为紧凑日期文件名，不合契约 daily_integration_YYYY-MM-DD.json，"
                                    f"生成器按 {target.name} 读取——请改名")
    if not target.exists():
        return None, slots, info
    info["path"] = str(target)
    intg = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(intg, dict):
        return None, slots, info
    changed = False
    for k in SLOT_KEYS:
        if intg.get(k) != slots[k]:
            intg[k] = slots[k]
            changed = True
    if changed and write_back:
        target.write_text(json.dumps(intg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        info["written"] = True
    return intg, slots, info


def main():
    ap = argparse.ArgumentParser(description="烛照九阴 · 隔日关注固定槽位（EAL / 星空 NE）")
    ap.add_argument("--date", help="数据日 YYYY-MM-DD 或 YYYYMMDD（默认今天）")
    ap.add_argument("--dry-run", action="store_true", help="只算不写")
    ap.add_argument("--check-names", action="store_true", help="只做文件名格式断言")
    args = ap.parse_args()

    bad = check_filenames()
    if bad:
        print(f"⚠ 文件名格式不合契约（应为 daily_integration_YYYY-MM-DD.json）：{', '.join(bad)}", file=sys.stderr)
    if args.check_names:
        sys.exit(1 if bad else 0)

    date_iso = iso_date(args.date or datetime.date.today().isoformat())
    if not _ISO_RE.match(date_iso):
        print(f"✗ --date 非法：{args.date}", file=sys.stderr)
        sys.exit(2)
    intg, slots, info = ensure_slots(date_iso, write_back=not args.dry_run)
    print(json.dumps({"date": date_iso, "slots": slots, "info": info, "file_found": intg is not None},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
