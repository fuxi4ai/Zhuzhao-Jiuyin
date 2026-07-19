#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""叙事状态（narrative_regime）· 候选扫描器（只读 · 不自动落表）
（CC 2026-07-17；Doctor 裁定：只提取「有长期指导意义的逻辑」——AI Capex 叙事转向这类"大事"；
  当天的下跌原因已过时、不再重要，故**不做日度原因标注**）

设计要点（为什么不写解析器）：
  实测 dim1_external_pricing 的 pricing_direction 93 条里，绝大多数是**日度战术判读**
  （"中性偏多(等待6/18美联储)"「外盘修复预期(高开不宜追涨)」），9 个月只有 2~3 条够得上结构级。
  产出率低到不值得自动解析，且误判成本高（把战术噪声当叙事转向＝给 F1 放大器塞假信号）。
  故采「**扫描→候选→人确认→落表**」，本脚本只负责扫描与出候选，**绝不写库**。

用法：
  python3 tools/scan_narrative_regime.py                 # 扫候选（只读，沙箱可跑）
  python3 tools/scan_narrative_regime.py --since 2026-01-01
  python3 tools/scan_narrative_regime.py --ddl           # 打印建表 DDL + 首批种子 INSERT（给 Doctor 终端跑）
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from lib.logger import get_logger
logger = get_logger(__name__)
import sqlite3, argparse
import config

# 结构级用语（指向持久的叙事/范式变化），刻意不含「今日/明日/短线/等待/靴子」等战术词
STRUCT_KW = [
    "叙事", "范式", "逻辑变", "转向", "拐点", "重估", "估值体系", "泡沫", "破裂",
    "去杠杆", "capex", "Capex", "资本开支", "产能周期", "供需格局", "结构性",
    "中长期", "长期", "政策路径", "危机", "外溢", "系统性",
]
# 战术噪声词：命中这些且未命中强结构词的，降级为「疑似战术」
TACTICAL_KW = ["今日", "明日", "短线", "等待", "靴子", "高开", "低开", "尾盘", "追涨", "节点"]


def scan(since):
    rc = sqlite3.connect(f"file:{config.RECAP_DB}?mode=ro", uri=True)
    cands = []
    # 源①：dim1 外部定价（定性文字）
    try:
        for d, pd, ks, ml in rc.execute(
                "SELECT date,pricing_direction,key_signals,market_linkage FROM dim1_external_pricing "
                "WHERE date>=? ORDER BY date", (since,)):
            blob = " ".join(x for x in (pd, ks, ml) if x)
            hits = [k for k in STRUCT_KW if k in blob]
            if not hits:
                continue
            tac = [k for k in TACTICAL_KW if k in (pd or "")]
            cands.append({"date": d, "src": "dim1", "hits": hits, "tactical": tac,
                          "text": (pd or ks or "")[:110]})
    except sqlite3.OperationalError as e:
        logger.warning(f"dim1 扫描跳过：{e}")
    # 源②：渊图/产业信号（结构级产业逻辑本就住这里）
    try:
        for d, cat, kw, sc, lt in rc.execute(
                "SELECT date,category,keyword,signal_content,logic_type FROM industry_signals "
                "WHERE date>=? ORDER BY date", (since,)):
            blob = " ".join(x for x in (cat, kw, sc) if x)
            hits = [k for k in STRUCT_KW if k in blob]
            if not hits:
                continue
            cands.append({"date": d, "src": f"industry_signals/{lt or '—'}", "hits": hits,
                          "tactical": [], "text": (kw or sc or "")[:110]})
    except sqlite3.OperationalError as e:
        logger.warning(f"industry_signals 扫描跳过：{e}")
    return cands


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2025-01-01")
    ap.add_argument("--ddl", action="store_true", help="打印建表+种子 SQL（Doctor 终端跑，CC 不写库）")
    args = ap.parse_args()

    if args.ddl:
        print(DDL_AND_SEED)
        return
    c = scan(args.since)
    strong = [x for x in c if not x["tactical"]]
    weak = [x for x in c if x["tactical"]]
    print(f"\n候选 {len(c)} 条（强 {len(strong)} / 疑似战术 {len(weak)}）· 起 {args.since}")
    print("=" * 96)
    print("\n【强候选】——命中结构级用语、无战术词，优先判读：")
    for x in strong:
        print(f"  {x['date']}  [{x['src']:26s}] {'/'.join(x['hits'][:3]):18s} {x['text']}")
    print("\n【疑似战术】——同时含战术词，多半是日度判读，谨慎：")
    for x in weak[:15]:
        print(f"  {x['date']}  [{x['src']:26s}] {'/'.join(x['hits'][:2]):12s} {x['text']}")
    print("\n" + "=" * 96)
    print("判读准则：只有『其后数周仍成立、能改变对市场的先验』的才算叙事转向；")
    print("         『今天为什么跌』一律不收——当天原因过期极快、无长期指导意义（Doctor 2026-07-17）。")
    print("确认后：python3 tools/scan_narrative_regime.py --ddl  → 把 SQL 贴到 Mac 终端跑（CC 不写 recap.db）")


DDL_AND_SEED = """-- narrative_regime · 叙事状态表（recap.db）
-- ⚠️ CC 不在沙箱写 recap.db（G019/FUSE），以下请 Doctor 在 Mac 终端执行：
--    sqlite3 ~/Documents/Database/烛照九阴/recap.db < 本段
CREATE TABLE IF NOT EXISTS narrative_regime (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date_start  TEXT NOT NULL,          -- 叙事转向起始日 YYYY-MM-DD
    tag         TEXT NOT NULL,          -- 稳定键，如 tech_valuation_bubble_burst
    direction   TEXT NOT NULL,          -- bearish / bullish
    summary     TEXT NOT NULL,          -- 一句话叙事（长期指导意义）
    source      TEXT,                   -- 证据来源（dim1:2026-07-13 等）
    status      TEXT DEFAULT 'active',  -- active / superseded / expired
    date_end    TEXT,                   -- 失效日（superseded/expired 时填）
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_narrative_active ON narrative_regime(status, date_start);

-- 首批种子（据 dim1 2026-07-13 / 07-16 实证文本，Doctor 确认后落）
INSERT INTO narrative_regime(date_start,tag,direction,summary,source) VALUES
 ('2026-07-13','tech_valuation_bubble_burst','bearish',
  '科技/AI 估值泡沫破裂——全球科技股进入估值重估，A股科技主线被动跟随而非自身体系崩塌',
  'dim1:2026-07-13 pricing_direction'),
 ('2026-07-13','asia_deleveraging_spillover','bearish',
  '亚洲去杠杆外溢——韩国主动刺破杠杆泡沫、资金赴美，亚洲流动性持续紧张',
  'dim1:2026-07-13/2026-07-16 pricing_direction');
"""


if __name__ == "__main__":
    main()
