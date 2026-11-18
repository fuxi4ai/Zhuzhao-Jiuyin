#!/usr/bin/env python3
"""自复盘 · 与课件信号的逐日对照（PRD「烛照九阴自复盘取代课件」R4 · 2026-11-17）

并行期内每个交易日一行：课件当天点到了哪些主线，自复盘覆盖了哪些，各自独有哪些。
结果写 data/self_recap/compare.csv；同一交易日重跑会替换该日那一行。

这是对照，不是取数：本脚本只读课件派生的 industry_signals 用来比对，
它的结果不回流进自复盘记录，也不进日报。

「方向相反」这一栏脚本不算。课件信号表没有方向列，方向要靠读文字判断，
由审核的人填 opposite 与 opposite_note 两栏。人工结论跟着两侧内容的版本走：
每行记下自复盘记录与课件当日信号各自的校验值；重跑时两侧有一侧变过，已填的内容照留，
但 opposite_review 标「待复核」，由审核的人重读后清掉这一栏。
非盲写的交易日在 blind 与 note 两栏写明，这一行只验证流程。
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import argparse, csv, datetime, hashlib, json, sqlite3
from pathlib import Path
import config
from tools.self_recap_validate import validate

OUT_ROOT = config.PROJECT_ROOT / "data" / "self_recap"
FIELDS = ["trade_date", "kejian_rows", "kejian_rows_no_theme", "kejian_themes", "self_records",
          "self_records_no_theme", "self_themes", "overlap", "only_kejian", "only_self",
          "overlap_list", "only_kejian_list", "only_self_list", "opposite", "opposite_note",
          "opposite_review", "blind", "note", "self_sha256", "kejian_sha256", "computed_at"]


def kejian_side(recap_db, date):
    """课件当日入库的信号。date 为 YYYYMMDD。"""
    iso = f"{date[:4]}-{date[4:6]}-{date[6:]}"
    conn = sqlite3.connect(Path(recap_db).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        rows = conn.execute("SELECT COALESCE(etf_anchor,''), COALESCE(keyword,''), COALESCE(signal_content,'') "
                            "FROM industry_signals WHERE date=? AND COALESCE(status,'') != 'retired'",
                            (iso,)).fetchall()
    finally:
        conn.close()
    themes = sorted({r[0] for r in rows if r[0]})
    # 课件一侧的版本：当日每条信号的主线、关键词、正文。人工判方向读的就是这些
    digest = hashlib.sha256(json.dumps(sorted(map(list, rows)), ensure_ascii=False).encode("utf-8")).hexdigest()
    return len(rows), sum(1 for r in rows if not r[0]), themes, digest


def compare(doc, recap_db, records_sha=None):
    """records_sha 为 records.json 的字节校验值；不给则按文档内容算。"""
    date = doc["trade_date"]
    n_rows, n_blank, k_themes, k_digest = kejian_side(recap_db, date)
    if records_sha is None:
        records_sha = hashlib.sha256(json.dumps(doc, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    notes = []
    if n_rows == 0:
        notes.append("当日无课件入库")
    if doc.get("blind") is not True:
        notes.append("非盲写：这一行只验证流程，不作证据")
    recs = doc["records"]
    s_themes = sorted({r["theme"] for r in recs if r.get("theme")})
    ks, ss = set(k_themes), set(s_themes)
    return {
        "trade_date": date,
        "kejian_rows": n_rows, "kejian_rows_no_theme": n_blank, "kejian_themes": len(ks),
        "self_records": len(recs), "self_records_no_theme": sum(1 for r in recs if not r.get("theme")),
        "self_themes": len(ss),
        "overlap": len(ks & ss), "only_kejian": len(ks - ss), "only_self": len(ss - ks),
        "overlap_list": "；".join(sorted(ks & ss)),
        "only_kejian_list": "；".join(sorted(ks - ss)),
        "only_self_list": "；".join(sorted(ss - ks)),
        "opposite": "", "opposite_note": "", "opposite_review": "",
        "blind": "是" if doc.get("blind") is True else "否",
        "note": "；".join(notes),
        "self_sha256": records_sha, "kejian_sha256": k_digest,
        "computed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    }


def upsert(csv_path, row):
    rows = []
    if csv_path.exists():
        with csv_path.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
    for old in rows:
        if old["trade_date"] == row["trade_date"]:   # 重跑保留人工填的两栏，但要看两侧内容变没变
            row["opposite"] = old.get("opposite") or ""
            row["opposite_note"] = old.get("opposite_note") or ""
            if not (row["opposite"] + row["opposite_note"]).strip():
                row["opposite_review"] = ""
            elif not old.get("self_sha256") or not old.get("kejian_sha256"):
                row["opposite_review"] = "待复核：填写时没有记下两侧版本"
            else:
                changed = [name for name, k in (("自复盘记录", "self_sha256"), ("课件信号", "kejian_sha256"))
                           if old[k] != row[k]]
                row["opposite_review"] = ("待复核：填写后" + "、".join(changed) + "变过" if changed
                                          else old.get("opposite_review") or "")
    rows = [r for r in rows if r["trade_date"] != row["trade_date"]] + [row]
    rows.sort(key=lambda r: r["trade_date"])
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = csv_path.with_suffix(".csv.tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        # csv 模块默认行尾是 \r\n，git diff --check 会当成行尾空白拦下（GOTCHAS ERR-20261117-002）
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    tmp.replace(csv_path)
    return len(rows)


def main():
    ap = argparse.ArgumentParser(description="自复盘与课件信号逐日对照")
    ap.add_argument("--date", required=True, help="A 股交易日 YYYYMMDD")
    ap.add_argument("--out-root", type=Path, default=OUT_ROOT)
    ap.add_argument("--dry-run", action="store_true", help="只打印，不写 compare.csv")
    a = ap.parse_args()
    rec = a.out_root / a.date / "records.json"
    if not rec.is_file():
        print(json.dumps({"status": "failed", "reason": f"NO_RECORDS: {rec}"}, ensure_ascii=False))
        raise SystemExit(2)
    doc = json.loads(rec.read_text(encoding="utf-8"))
    errs = validate(doc, None, rec.parent / "inputs.json")
    if errs:
        print(json.dumps({"status": "failed", "reason": "RECORDS_INVALID", "errors": errs[:5]}, ensure_ascii=False))
        raise SystemExit(2)
    if doc["trade_date"] != a.date:
        print(json.dumps({"status": "failed", "reason": "DATE_MISMATCH"}, ensure_ascii=False))
        raise SystemExit(2)
    row = compare(doc, config.RECAP_DB, hashlib.sha256(rec.read_bytes()).hexdigest())
    if not a.dry_run:
        n = upsert(a.out_root / "compare.csv", row)
        row["_rows_in_csv"] = n
    print(json.dumps(row, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
