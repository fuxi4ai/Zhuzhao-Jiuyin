#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性洗 recap：剔除 yuantu_buy_signals 受益里 hop==3 且无解析 ticker(ts 空) 的远端噪声，
并按 sync_buy_signals 同口径重算 beneficiaries / beneficiaries_ts / beneficiary_count /
ts_resolved / beneficiaries_detail。

Doctor 2026-06-30 拍板（其二·收紧条件删）：只删 hop-3 且无票的远端名（保住有票龙头如中际旭创/寒武纪）；
允许受益清零（本就只剩不可投远端）；有票错挂（彩虹股份@光纤 等）走人工核实另清、本脚本不碰。

用法：
  python3 tools/scrub_hop3_noticker.py            # dry-run（只统计，不写库）
  python3 tools/scrub_hop3_noticker.py --apply    # 写库（自带备份 + 写后 integrity_check）
持久化：以后每次 sync 由 sync_buy_signals.py 内置同款过滤自动维持。
"""
import os, sys, json, shutil, sqlite3, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def rederive(detail):
    """按 sync_buy_signals 口径从 detail 重算派生字段。"""
    names = [e["name"] for e in detail if e.get("name")]
    codes = [f'{e["name"]}:{e["ts"]}' for e in detail if (e.get("ts") or "").strip()]
    return " / ".join(names), " / ".join(codes), len(names), len(codes)


def is_noise(e):
    """hop==3 且无解析 ticker（ts 空）= 远端噪声，剔。"""
    return e.get("hop") == 3 and not (e.get("ts") or "").strip()


def main(apply=False):
    db = config.RECAP_DB
    if apply:
        bak = db + f".bak_{datetime.date.today():%Y%m%d}_scrubhop3"
        shutil.copy2(db, bak)
        print("📦 备份 →", bak)
    con = (config.connect_write(db) if apply
           else sqlite3.connect(f"file:{db}?mode=ro", uri=True))
    rows = con.execute("SELECT id, beneficiaries_detail FROM yuantu_buy_signals "
                       "WHERE beneficiaries_detail IS NOT NULL AND beneficiaries_detail!=''").fetchall()
    n_sig = n_rm = n_empty = 0
    for rid, det in rows:
        try:
            arr = json.loads(det)
        except Exception:
            continue
        kept = [e for e in arr if not is_noise(e)]
        rm = len(arr) - len(kept)
        if not rm:
            continue
        n_sig += 1
        n_rm += rm
        if not kept:
            n_empty += 1
        ben, bts, cnt, tsr = rederive(kept)
        if apply:
            con.execute("UPDATE yuantu_buy_signals SET beneficiaries=?, beneficiaries_ts=?, "
                        "beneficiary_count=?, ts_resolved=?, beneficiaries_detail=? WHERE id=?",
                        (ben, bts, cnt, tsr, json.dumps(kept, ensure_ascii=False), rid))
    if apply:
        con.commit()
        ic = con.execute("PRAGMA integrity_check").fetchone()[0]
        print("integrity_check:", ic)
    print(f"{'[已写库]' if apply else '[dry-run·未写库]'} 触及信号 {n_sig} · 删受益 {n_rm} · 清零 {n_empty}")
    con.close()


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
