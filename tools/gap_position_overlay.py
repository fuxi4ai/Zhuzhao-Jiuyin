#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""信息差仓位加权（gap overlay）v0.2 —— gap≥3 活跃信号 → **主线级超配清单**
（CC 2026-06-10；依据：info_gap_level 校准——峰值超额随 gap 单调递增，gap≥3 显著更高，
 见 docs/产业逻辑发现模块.md §数据校准。Doctor 2026-06-10 批）

⚠️ v0.1→v0.2 口径修正（dry-run 实测裁决）：
  原设计"存在热主线→全市场风险偏好+1档"在样本期 91~99% 的交易日触发，无区分度
  （AI 长牛高 gap 信号常驻）——大盘维度伪加权，弃用。
  gap 的信息量在**横截面**（哪条主线超额天花板高），不在时序（今天该不该加仓）。
  故 v0.2 只产出主线级超配清单，position_risk_pref（小鲍档）保持不动。

规则（ETF 级，逐日）：
  活跃信号(D) = info_gap_level≥3 且 发现日 ∈ (D−60天, D] 且 (无 closed_date 或 closed_date>D)
  热主线(D)   = 同一 etf_anchor 主线下活跃信号 ≥2 条，按活跃数+最高gap排序
  → 写 dim4_trade_plan.gap_hot_themes（"主线:数量:最高gap" 逗号串，主线tilt/选股用）

写入列：gap_hot_themes。幂等可重跑。

用法：
  python3 tools/gap_position_overlay.py --dry-run    # 优先读库内 gap 列；缺列回退读审核表 TSV
  python3 tools/gap_position_overlay.py --apply      # 需 closure_engine --apply 已跑（库内有 gap 列）
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import sqlite3, argparse, csv, glob, shutil, datetime
from collections import defaultdict
import config
from lib.logger import get_logger
logger = get_logger(__name__)

GAP_MIN = 3        # 加权门槛（校准表：≥3 中位峰值超额显著抬升）
LOOKBACK = 60      # 活跃窗口（天）；防陈年 open 信号永久加权
HOT_N = 2          # 同主线活跃信号数门槛


def iso(d):  # '20260510' → '2026-05-10'
    return f"{d[:4]}-{d[4:6]}-{d[6:]}" if d and "-" not in d else d


def load_gap_signals(rc):
    """→ [(disc_iso, theme, gap_level, closed_iso|None)]（需 closure_engine --apply 已跑）"""
    cols = {r[1] for r in rc.execute("PRAGMA table_info(industry_signals)")}
    if not {"etf_anchor", "closed_date"} <= cols:
        logger.error("❌ 库内无 gap 列——先跑 closure_engine.py --apply")
        _sys.exit(1)
    rows = rc.execute(
        "SELECT date, etf_anchor, info_gap_level, closed_date FROM industry_signals "
        "WHERE info_gap_level>=? AND etf_anchor IS NOT NULL AND etf_anchor!=''",
        (GAP_MIN,)).fetchall()
    logger.info(f"gap≥{GAP_MIN} 已锚定信号：{len(rows)} 条")
    return [(iso(d), t, g, iso(c) if c else None) for d, t, g, c in rows]


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    rc = sqlite3.connect(config.RECAP_DB if args.apply
                         else f"file:{config.RECAP_DB}?mode=ro", uri=not args.apply)
    sigs = load_gap_signals(rc)
    days = rc.execute("SELECT date, position_risk_pref FROM dim4_trade_plan "
                      "WHERE position_risk_pref IS NOT NULL ORDER BY date").fetchall()
    logger.info(f"dim4 待覆盖 {len(days)} 日（{days[0][0]}→{days[-1][0]}）")

    plan, stats = [], defaultdict(int)
    for D, _pref in days:
        lo = (datetime.date.fromisoformat(D)
              - datetime.timedelta(days=LOOKBACK)).isoformat()
        cnt, gmax = defaultdict(int), defaultdict(int)
        for disc, theme, g, closed in sigs:
            if lo < disc <= D and (closed is None or closed > D):
                cnt[theme] += 1
                gmax[theme] = max(gmax[theme], g)
        # 排序：最高gap优先，再按活跃数——横截面"谁的天花板高"
        hot = sorted((t for t, n in cnt.items() if n >= HOT_N),
                     key=lambda t: (-gmax[t], -cnt[t]))
        plan.append((D, ",".join(f"{t}:{cnt[t]}:g{gmax[t]}" for t in hot)))
        stats[f"n_hot={len(hot)}"] += 1
        for t in hot[:1]:
            stats[f"top1:{t.split('/')[0]}"] += 1

    logger.info("📊 " + " | ".join(f"{k}={v}" for k, v in sorted(stats.items())))
    for D, hot in plan[-3:]:
        logger.info(f"  {D} → [{hot}]")

    if args.apply:
        bak = config.RECAP_DB + f".bak_{datetime.date.today():%Y%m%d}_gapoverlay"
        shutil.copy2(config.RECAP_DB, bak)
        logger.info(f"📦 备份 → {bak}")
        have = {r[1] for r in rc.execute("PRAGMA table_info(dim4_trade_plan)")}
        if "gap_hot_themes" not in have:
            rc.execute("ALTER TABLE dim4_trade_plan ADD COLUMN gap_hot_themes TEXT")
        rc.executemany("UPDATE dim4_trade_plan SET gap_hot_themes=? WHERE date=?",
                       [(h, D) for D, h in plan])
        rc.commit()
        logger.info(f"✅ 回填 {len(plan)} 日（仅 gap_hot_themes，小鲍档位未动）")
    else:
        logger.info("🔍 dry-run 完成，未写库。")


if __name__ == "__main__":
    main()
