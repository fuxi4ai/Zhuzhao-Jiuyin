#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""烛照九阴 recap.db 端到端健康自检（只读 · 零网络）→ 写 Database/烛照九阴/_health.json。

判「recap 日更是否按期入库 + 新不新鲜」，供海螺姑娘资产看板 conch survey 读取 → 节点发光告警。
口径（对齐 conch/白泽 schema · G-X45 第三批 · 2026-07-01 立）：
  target_date = 六张关键 dim 表 max(date) 的最大值
  gap_days    = today - target_date（自然日）
  overall
    · fail  = 关键表读不到 / gap_days >= FAIL_DAYS（≥5 天没更新，明显有事）
    · stale = gap_days >= STALE_DAYS（≥2 天没更新，工作日应日更）
    · ok    = 其他

红线：只读文件（`file:...?mode=ro`），绝不写 db、不联网。
被 recap-kejian-review 定时任务末尾调用（每天 06:30，紧跟句芒审核之后）；也可手动跑。
env：ZZJY_DATABASE_ROOT 覆盖 Database 根（gateway 平铺挂载下必设 · 见 G-X45）。
"""
import json, os, sqlite3, sys
from datetime import datetime, date
from pathlib import Path

# 关键 dim 表列表（date 语义 = 复盘对应的交易日）
KEY_TABLES = [
    "recap_daily",
    "dim1_external_pricing",
    "dim2_sector_themes",
    "dim3_sentiment_tech",
    "dim4_trade_plan",
    "dim4_stock_analysis",
]

STALE_DAYS = 2   # 工作日日更，>=2 天未更新 → stale
FAIL_DAYS = 5    # >=5 天未更新（跨长假仍应有 6/29 之类的最后一批）→ fail


def _database_root() -> Path:
    """gateway 平铺挂载下 Documents 父目录不成立，用 ZZJY_DATABASE_ROOT 覆盖 Database 根（G-X45）。
    未设则向上找 Documents/Database（Mac 原生走这条）。"""
    env = os.environ.get("ZZJY_DATABASE_ROOT")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    for anc in here.parents:
        if (anc / "Database").is_dir():
            return anc / "Database"
    # 兜底
    return Path.home() / "Documents" / "Database"


def main():
    db_root = _database_root()
    recap = db_root / "烛照九阴" / "recap.db"
    out = db_root / "烛照九阴" / "_health.json"
    now = datetime.now().astimezone().isoformat(timespec="seconds")

    if not recap.exists():
        payload = {
            "generated": now, "overall": "fail",
            "fails": [f"recap.db 缺失: {recap}"], "warns": [],
            "target_date": None, "checks": {},
            "note": "烛照九阴 recap.db 自检 · 库文件不存在",
        }
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print("write error:", e)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload["overall"] == "ok" else 1

    fails, warns, checks = [], [], {}
    try:
        conn = sqlite3.connect(f"file:{recap}?mode=ro", uri=True)
        cur = conn.cursor()
        max_dates = []
        for t in KEY_TABLES:
            try:
                cur.execute(f"SELECT MAX(date), COUNT(*) FROM {t}")
                mx, n = cur.fetchone()
                checks[t] = {"max_date": mx, "rows": n}
                if mx:
                    max_dates.append(mx)
            except Exception as e:
                checks[t] = {"error": str(e)}
                warns.append(f"{t} 读表失败:{e}")
        conn.close()
    except Exception as e:
        payload = {
            "generated": now, "overall": "fail",
            "fails": [f"recap.db 打开失败:{e}"], "warns": [],
            "target_date": None, "checks": checks,
            "note": "烛照九阴 recap.db 自检 · 打开失败",
        }
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as ee:
            print("write error:", ee)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1

    # target_date + gap
    target_date = max(max_dates) if max_dates else None
    gap_days = None
    if target_date:
        try:
            td = date.fromisoformat(target_date)
            gap_days = (date.today() - td).days
            checks["gap_days"] = gap_days
            if gap_days >= FAIL_DAYS:
                fails.append(f"最新数据日 {target_date} 距今 {gap_days} 天（≥{FAIL_DAYS} 天=fail）")
            elif gap_days >= STALE_DAYS:
                warns.append(f"最新数据日 {target_date} 距今 {gap_days} 天（≥{STALE_DAYS} 天=stale）")
        except Exception as e:
            warns.append(f"target_date 解析失败({target_date}):{e}")
    else:
        fails.append("所有关键表 max(date) 均为空")

    overall = "fail" if fails else ("stale" if warns else "ok")
    payload = {
        "generated": now, "overall": overall, "fails": fails, "warns": warns,
        "target_date": target_date, "checks": checks,
        "note": ("烛照九阴 recap.db 自检 · 六张关键 dim 表 max(date) 判 target_date · "
                 f"阈值 stale≥{STALE_DAYS}d/fail≥{FAIL_DAYS}d · 只读零网络"),
    }
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"recap health: {overall}  target={target_date}  gap={gap_days}d  fails={fails}  warns={warns}")
        print(f"→ {out}")
    except Exception as e:
        print("=== RECAP _HEALTH JSON (写盘失败，stdout 输出) ===")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print("write error:", e)
    return 0 if overall != "fail" else 1


if __name__ == "__main__":
    sys.exit(main())
