#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""课件去重 —— processed_kejian 孤儿表的「主」（2026-06-24 固化）。

此前去重口径（filename + md5，哈希不变不重跑）只活在 SKILL 自然语言里、processed_kejian 表无任何代码读写。
本脚本把它沉成确定性、可复现、可测的代码：

  scan  （只读·默认）：扫 Raw-Recap/ 课件，对每个文件算 md5、查 processed_kejian →
                       分类 new(没记录) / changed(同名但 hash 变) / unchanged(同名同 hash·跳过)。
                       供日更 SKILL 拿「待处理清单」（只这些需子代理读 PDF 提炼 dim3/dim4）。**纯只读**。
  record（写库·Mac）  ：某课件处理完后，把 (filename, md5, kejian_date, now) 写入 processed_kejian
                       （INSERT OR REPLACE）。--file <名> 记一个；--all-new 记本次 scan 的所有 new+changed。

红线：scan 只读（recap.db mode=ro + 只读 Raw-Recap）；record 才写库（沙箱挂载盘禁写 db→只能 Mac 跑）。
路径走祖先查找定位 Documents（GOTCHA-014：不用 ~/expanduser）。
"""
import os, sys, json, hashlib, sqlite3, argparse, re
from pathlib import Path
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # 中央写护栏 connect_write（G019）

KEJIAN_EXTS = {".pdf", ".doc", ".docx"}

def _documents_root():
    here = Path(__file__).resolve()
    for anc in [here] + list(here.parents):
        if anc.name == "Documents":
            return anc
    return here.parents[6]  # 兜底

DOCS = _documents_root()
RECAP_DB = DOCS / "Database" / "烛照九阴" / "recap.db"
RAW_DIR = DOCS / "Database" / "烛照九阴" / "Raw-Recap"

def _md5(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def _kejian_date(name):
    m = re.match(r"^(\d{2})(\d{2})(\d{2})", name)  # YYMMDD 前缀
    if not m:
        return None
    yy, mm, dd = m.groups()
    return f"20{yy}-{mm}-{dd}"

def _processed_map(db):
    """{filename: file_hash}（只读）"""
    if not db.exists():
        return {}
    con = sqlite3.connect(f"file:{db}?mode=ro&immutable=1", uri=True)
    try:
        return {r[0]: r[1] for r in con.execute("SELECT filename, file_hash FROM processed_kejian")}
    finally:
        con.close()

def scan():
    proc = _processed_map(RECAP_DB)
    new, changed, unchanged, undated = [], [], [], []
    files = sorted(p for p in RAW_DIR.iterdir() if p.is_file() and p.suffix.lower() in KEJIAN_EXTS) if RAW_DIR.exists() else []
    for p in files:
        name = p.name
        h = _md5(p)
        d = _kejian_date(name)
        if d is None:
            undated.append(name)
        rec = {"filename": name, "md5": h, "kejian_date": d}
        if name not in proc:
            new.append(rec)
        elif proc[name] != h:
            changed.append(rec)
        else:
            unchanged.append(name)
    return {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "raw_recap_dir": str(RAW_DIR), "db": str(RECAP_DB),
        "total_files": len(files),
        "new": new, "changed": changed, "unchanged_count": len(unchanged),
        "undated_names": undated,
        "to_process": new + changed,  # 这些才需子代理读 PDF 提炼
    }

def record(filenames):
    """写 processed_kejian（INSERT OR REPLACE）。Mac 跑。"""
    if not RECAP_DB.exists():
        print(f"❌ recap.db 不存在：{RECAP_DB}"); return 2
    con = config.connect_write(str(RECAP_DB))
    cur = con.cursor()
    n = 0
    for name in filenames:
        p = RAW_DIR / name
        if not p.exists():
            print(f"[skip] 文件不存在：{name}"); continue
        cur.execute(
            "INSERT OR REPLACE INTO processed_kejian(filename, file_hash, kejian_date, processed_at) VALUES (?,?,?,?)",
            (name, _md5(p), _kejian_date(name), datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        n += 1
    con.commit(); con.close()
    print(f"✅ 已记录 {n} 个课件到 processed_kejian")
    return 0

def prune(apply=False):
    """删 processed_kejian 中「登记但文件已不在 Raw-Recap」的陈旧记录。dry-run 默认；--apply 才写库（Mac）。"""
    proc = _processed_map(RECAP_DB)
    existing = {p.name for p in RAW_DIR.iterdir() if p.is_file()} if RAW_DIR.exists() else set()
    stale = sorted(fn for fn in proc if fn not in existing)
    if not stale:
        print("processed_kejian 无陈旧记录（登记的课件文件都还在）")
        return 0
    print(f"陈旧记录 {len(stale)} 条（登记但文件已不在 Raw-Recap）：")
    for fn in stale:
        print("  ·", fn)
    if not apply:
        print("（dry-run·未删；加 --apply 实删）")
        return 0
    if not RECAP_DB.exists():
        print(f"❌ recap.db 不存在：{RECAP_DB}"); return 2
    con = config.connect_write(str(RECAP_DB))
    con.executemany("DELETE FROM processed_kejian WHERE filename=?", [(fn,) for fn in stale])
    con.commit(); con.close()
    print(f"✅ 已删 {len(stale)} 条陈旧记录")
    return 0

def main():
    ap = argparse.ArgumentParser(description="课件去重（processed_kejian 主）")
    sub = ap.add_subparsers(dest="cmd")
    sp = sub.add_parser("scan", help="只读·报 new/changed/unchanged 与待处理清单")
    sp.add_argument("--json", action="store_true", help="输出完整 JSON")
    rp = sub.add_parser("record", help="写库·标已处理（Mac）")
    g = rp.add_mutually_exclusive_group(required=True)
    g.add_argument("--file", help="记单个课件文件名")
    g.add_argument("--all-new", action="store_true", help="记本次 scan 的所有 new+changed")
    pp = sub.add_parser("prune", help="删登记但文件已不在的陈旧记录（dry-run 默认）")
    pp.add_argument("--apply", action="store_true", help="实删（写库·Mac）")
    a = ap.parse_args()

    if a.cmd in (None, "scan"):
        r = scan()
        if getattr(a, "json", False):
            print(json.dumps(r, ensure_ascii=False, indent=2)); return 0
        print(f"课件去重扫描（filename+md5）· {RAW_DIR}")
        print(f"  共 {r['total_files']} 个课件；待处理 {len(r['to_process'])}（new {len(r['new'])} / changed {len(r['changed'])}）；未变 {r['unchanged_count']}")
        for x in r["to_process"]:
            print(f"   · {'NEW' if x in r['new'] else 'CHG'}  {x['filename']}  ({x['kejian_date']})")
        if r["undated_names"]:
            print(f"  ⚠ 无 YYMMDD 日期前缀 {len(r['undated_names'])} 个（kejian_date=None）：{r['undated_names'][:5]}{'…' if len(r['undated_names'])>5 else ''}")
        return 0
    if a.cmd == "record":
        names = [a.file] if a.file else [x["filename"] for x in scan()["to_process"]]
        return record(names)
    if a.cmd == "prune":
        return prune(apply=a.apply)

if __name__ == "__main__":
    sys.exit(main())
