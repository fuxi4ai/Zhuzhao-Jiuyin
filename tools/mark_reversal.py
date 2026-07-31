#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""人工标注追加器 —— 往 docs/情绪周期_人工标注.tsv 追一条「市场反转日」

（CC 2026-07-30 立 · Doctor 定「引擎肯定要改，但改之前得先攒够数据/标注」）

定位：**只读引擎产物、只写标注文件**。不 import 引擎、不碰 recap.db、不进定时任务。
     坏了只影响标注这一件事，引擎与日报链路完全不受影响。

为什么要脚本而不是手写 TSV：`engine_*` 五列是**评测基线**（日后算「引擎在真实反转前 N 天
     有没有报过信号」全靠它）。手抄有两个风险——抄错，以及日后回看时顺手改。脚本从当日历史
     序列自动抓快照，把基线钉死；基线一旦被改过，提前量这个数就永远说不清了。

用法：
  # 追加一条反转日（engine_* 自动从最新历史序列抓取）
  python3 tools/mark_reversal.py --date 20260731 --direction up \
      --rationale "科技股跟随美股出清，知名基金爆仓；美股夜盘反转，A股跟随见底"

  # 事后回填确认状态
  python3 tools/mark_reversal.py --set-confirmed 20260730 已确认

  # 只看会写什么，不落盘
  python3 tools/mark_reversal.py --date 20260731 --direction up --rationale "…" --dry-run
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import argparse, csv, datetime, glob, re, shutil
import config

ANN_PATH = config.PROJECT_ROOT / "docs" / "情绪周期_人工标注.tsv"
SERIES_GLOB = str(config.PROJECT_ROOT / "docs" / "情绪周期v2_历史序列_*.tsv")
COLS = ["date", "mark_type", "direction", "engine_season", "engine_cycle_no",
        "engine_score", "engine_level_pct", "engine_trend", "engine_hint",
        "confirmed", "rationale", "note", "by", "created"]
CONFIRM_VALS = ("待观察", "已确认", "已证伪")


def latest_series():
    """最新一份历史序列（按文件名日期，不按 mtime——mtime 会被拷贝/同步扰动）"""
    files = glob.glob(SERIES_GLOB)
    dated = [(m.group(1), f) for f in files
             if (m := re.search(r"_(\d{8})\.tsv$", f))]
    if not dated:
        _sys.exit(f"✗ 找不到历史序列：{SERIES_GLOB}\n  先跑 emotion_engine_v2.py --dry-run 生成。")
    return max(dated)[1]


def engine_snapshot(date):
    """抓 date 当日的引擎读数；不在序列中则拒绝（非交易日 / 序列未更新到该日）"""
    path = latest_series()
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            if r["date"] == date:
                return {
                    "engine_season": r.get("season", ""),
                    "engine_cycle_no": r.get("cycle_no", ""),
                    "engine_score": r.get("score", ""),
                    "engine_level_pct": r.get("level_pct", ""),
                    "engine_trend": r.get("trend", ""),
                    "engine_hint": r.get("hint", ""),
                }, path
    _sys.exit(f"✗ {date} 不在历史序列中（{_os.path.basename(path)}）——非交易日，"
              f"或序列尚未更新到该日。\n  先跑 emotion_engine_v2.py --dry-run 再来。")


def read_ann():
    """→ (注释头文本, 表头行, 数据行 list[dict])；文件不存在则报错（模板由人建，脚本不造）"""
    if not ANN_PATH.exists():
        _sys.exit(f"✗ 标注文件不存在：{ANN_PATH}\n  这是真源文件，请先手工建好含注释头的模板。")
    raw = ANN_PATH.read_text(encoding="utf-8").splitlines(keepends=True)
    head = [ln for ln in raw if ln.lstrip().startswith("#")]
    body = [ln for ln in raw if not ln.lstrip().startswith("#") and ln.strip()]
    rows = list(csv.DictReader(body, delimiter="\t"))
    return "".join(head), rows


def write_ann(head, rows, dry):
    out = head
    out += "\t".join(COLS) + "\n"
    for r in rows:
        out += "\t".join((r.get(c) or "").replace("\t", " ").replace("\n", " ")
                         for c in COLS) + "\n"
    if dry:
        print("🔍 dry-run，未落盘。将写入：\n")
        print(out[len(head):])
        return
    if ANN_PATH.exists():                       # 可逆优先：每次改动前留一份
        shutil.copy2(ANN_PATH, str(ANN_PATH) + f".bak_{datetime.date.today():%Y%m%d}")
    ANN_PATH.write_text(out, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="情绪周期人工标注追加器")
    ap.add_argument("--date", help="标注日 YYYYMMDD")
    ap.add_argument("--direction", choices=["up", "down", "unknown"],
                    help="up=见底反转向上 / down=见顶反转向下 / unknown=只记反转不定方向")
    ap.add_argument("--rationale", help="机理依据（原话优先，事后不改）")
    ap.add_argument("--type", default="reversal", help="标注类型，默认 reversal")
    ap.add_argument("--note", default="", help="旁注（可选）")
    ap.add_argument("--by", default="Doctor")
    ap.add_argument("--force", action="store_true", help="该日已有标注时覆盖")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--set-confirmed", nargs=2, metavar=("DATE", "VALUE"),
                    help=f"回填确认状态，VALUE ∈ {CONFIRM_VALS}")
    a = ap.parse_args()

    head, rows = read_ann()

    # ── 模式二：回填确认状态 ──
    if a.set_confirmed:
        d, v = a.set_confirmed
        if v not in CONFIRM_VALS:
            _sys.exit(f"✗ confirmed 只能是 {CONFIRM_VALS} 之一，收到「{v}」")
        for r in rows:
            if r["date"] == d:
                old = r.get("confirmed") or "（空）"
                r["confirmed"] = v
                write_ann(head, rows, a.dry_run)
                print(f"✅ {d} confirmed: {old} → {v}")
                return
        _sys.exit(f"✗ 标注文件里没有 {d}")

    # ── 模式一：追加标注 ──
    if not (a.date and a.direction and a.rationale):
        ap.error("追加标注需同时给 --date / --direction / --rationale"
                 "（rationale 是评测时判「人工凭什么看到」的证据，不可省）")
    if not (a.date.isdigit() and len(a.date) == 8):
        _sys.exit(f"✗ date 须为 YYYYMMDD，收到「{a.date}」")

    dup = [r for r in rows if r["date"] == a.date]
    if dup and not a.force:
        _sys.exit(f"✗ {a.date} 已有标注（direction={dup[0].get('direction')}）。"
                  f"要改用 --force，或直接手改文件。")

    snap, src = engine_snapshot(a.date)
    row = {"date": a.date, "mark_type": a.type, "direction": a.direction,
           **snap, "confirmed": "待观察", "rationale": a.rationale,
           "note": a.note, "by": a.by,
           "created": f"{datetime.date.today():%Y-%m-%d}"}
    rows = [r for r in rows if r["date"] != a.date] + [row]
    rows.sort(key=lambda r: r["date"])
    write_ann(head, rows, a.dry_run)

    print(f"✅ 已标注 {a.date} · {a.type} · {a.direction}")
    print(f"   引擎快照（取自 {_os.path.basename(src)}）："
          f"{snap['engine_season']} · cycle {snap['engine_cycle_no']} · "
          f"score {snap['engine_score']} · 分位 {snap['engine_level_pct']} · {snap['engine_trend']}")
    if not snap["engine_hint"]:
        print("   ⚠ 当日引擎 hint 为空 —— 无任何前瞻提示（这正是要攒的样本）")
    else:
        print(f"   引擎当日提示：{snap['engine_hint']}")
    print(f"   标注文件现有 {len(rows)} 条")


if __name__ == "__main__":
    main()
