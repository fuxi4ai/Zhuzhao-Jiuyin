#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""信息差等级自动评分器（gap_rater v1）
（CC 2026-06-10；口径=docs/产业逻辑发现模块.md §信息差评分：明确度15% + 直接性60% + 传播广度25%）

背景：info_gap_level 为 2026-05-12 九儿批量手工评分，此后新信号（6月起27条+历史空值）无评级，
      日报信号卡 gap 标缺失。本工具规则化三维度，**先与手工评分做一致性验证，过关才补评**。

规则（每维 1~5，加权合成后四舍五入到 1~5）：
  明确度(15%)：具体数字越多越明确（价格/产能/百分比/金额）→ 分越低
  直接性(60%)：传导链越深(→/传导/上游下游/卡点)、措辞越模糊(预计/或将/无论)→ 分越高
  传播广度(25%)：冷门环节词(检测/代工/中间体/衬底…)→ 高；全市场热词(龙头/英伟达/特斯拉…)→ 低

用法：
  python3 tools/gap_rater.py --validate          # 与手工评分对比一致率（不写库）
  python3 tools/gap_rater.py --apply             # 给 info_gap_level IS NULL 的补评（标 auto_v1）
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import sqlite3, argparse, re, shutil, datetime
import statistics as st
import config
from lib.logger import get_logger
logger = get_logger(__name__)

NUM_PAT = re.compile(r"\d+(?:\.\d+)?\s*(?:%|万吨|亿|万元|万台|万片|万支|元/|美元|GW|MW|万亿|千亿|倍|周|nm|G\b|T\b)")
CHAIN_WORDS = ["→", "传导", "带动", "推动", "上游", "下游", "卡点", "瓶颈", "环节", "间接", "受益方向"]
VAGUE_WORDS = ["预计", "或将", "有望", "无论", "可能", "潜在", "酝酿", "临近"]
DIRECT_WORDS = ["涨价", "订单", "中标", "停产", "减产", "缺口", "出货", "采购", "落地"]
NICHE_WORDS = ["检测", "测试", "代工", "中间体", "衬底", "载体", "夹具", "辅材", "靶材",
               "树脂", "钨", "锗", "铼", "光纤阵列", "调制器", "激光器", "电子布", "铜箔",
               "基板", "封装", "良率"]
HOT_WORDS = ["英伟达", "特斯拉", "华为", "全市场", "龙头", "涨停", "主线", "大涨",
             "AI算力", "机器人", "光模块", "字节", "苹果"]


def clamp(v, lo=1, hi=5):
    return max(lo, min(hi, v))


def rate(text):
    """→ (level 1-5, 分维明细)"""
    t = text or ""
    n_num = len(NUM_PAT.findall(t))
    clarity = clamp(5 - min(n_num, 4))                       # 数字越多越明确→分越低
    chain = sum(t.count(w) for w in CHAIN_WORDS)
    vague = sum(t.count(w) for w in VAGUE_WORDS)
    direct = sum(t.count(w) for w in DIRECT_WORDS)
    directness = clamp(1 + min(chain, 4) * 0.8 + min(vague, 3) * 0.5 - min(direct, 3) * 0.4)
    niche = sum(1 for w in NICHE_WORDS if w in t)
    hot = sum(1 for w in HOT_WORDS if w in t)
    breadth = clamp(2.5 + niche * 0.9 - hot * 0.7)
    score = 0.15 * clarity + 0.60 * directness + 0.25 * breadth
    return clamp(round(score)), dict(clarity=clarity, directness=round(directness, 1),
                                     breadth=round(breadth, 1), raw=round(score, 2))


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--validate", action="store_true")
    g.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    rc = sqlite3.connect(config.RECAP_DB if args.apply
                         else f"file:{config.RECAP_DB}?mode=ro", uri=not args.apply)

    if args.validate:
        rows = rc.execute("SELECT info_gap_level, keyword||' '||COALESCE(signal_content,'') "
                          "FROM industry_signals WHERE info_gap_level IS NOT NULL").fetchall()
        exact = within1 = 0
        diffs = []
        from collections import Counter
        pred_dist, man_dist = Counter(), Counter()
        for lvl, text in rows:
            p, _ = rate(text)
            pred_dist[p] += 1
            man_dist[lvl] += 1
            d = p - lvl
            diffs.append(d)
            exact += (d == 0)
            within1 += (abs(d) <= 1)
        n = len(rows)
        logger.info(f"验证样本 {n}（九儿手工评分）")
        logger.info(f"  完全一致 {exact/n:.0%} ｜ ±1 档内 {within1/n:.0%} ｜ 平均偏差 {st.fmean(diffs):+.2f}")
        logger.info(f"  手工分布 {dict(sorted(man_dist.items()))}")
        logger.info(f"  规则分布 {dict(sorted(pred_dist.items()))}")
        return

    # --apply：仅补 NULL，标 auto_v1，先备份
    bak = config.RECAP_DB + f".bak_{datetime.date.today():%Y%m%d}_gaprater"
    shutil.copy2(config.RECAP_DB, bak)
    logger.info(f"📦 备份 → {bak}")
    have = {r[1] for r in rc.execute("PRAGMA table_info(industry_signals)")}
    if "gap_level_src" not in have:
        rc.execute("ALTER TABLE industry_signals ADD COLUMN gap_level_src TEXT")
        rc.execute("UPDATE industry_signals SET gap_level_src='manual_九儿' "
                   "WHERE info_gap_level IS NOT NULL")
        logger.info("  + gap_level_src 列（manual_九儿 / auto_v1 溯源）")
    rows = rc.execute("SELECT id, keyword||' '||COALESCE(signal_content,'') "
                      "FROM industry_signals WHERE info_gap_level IS NULL").fetchall()
    n = 0
    for sid, text in rows:
        lvl, _ = rate(text)
        rc.execute("UPDATE industry_signals SET info_gap_level=?, gap_level_src='auto_v1' "
                   "WHERE id=?", (lvl, sid))
        n += 1
    rc.commit()
    logger.info(f"✅ 自动补评 {n} 条（auto_v1，与手工评分溯源隔离）")


if __name__ == "__main__":
    main()
