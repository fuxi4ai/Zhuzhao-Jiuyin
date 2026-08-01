#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""C2 · dim4_stock_analysis.confidence 拆两列（方案甲 · 哥哥 2026-07-30 定）

## 病灶
`confidence` 一列被塞了两个正交轴：
  · 「高/中」= 小鲍对该个股判断的**把握度**（conviction）—— 原 DDL 注释即 `-- 置信度: 高/中/低`
  · 「P2」   = **信源分级**（P0/P1/P2）—— 2026-06-30 起新脚本塞入，与原注释矛盾
按 source 切即现形：`小鲍老师` 350 行全是高/中、零 P2；`小鲍复盘课件` 109 行里 99 行是 P2。
后果：任何按 confidence 的比较/筛选都在拿"判断强度"和"信源等级"比大小。

## 方案甲（全库口径统一优先）
`confidence` 归一为**信源轴**（与 recap_daily / industry_signals 同义，小鲍全线 P2）；
新增 `conviction` 列承接**判断强度**（高/中/低）。

之所以不选"反向"方案（守住本表 DDL 原意、另建 credibility）：跨表同名列**同义**是更重要的性质，
本表是全库唯一例外，迁移量大不等于风险大（有备份、可校验、下游仅 1 处透传）。代价是原 DDL 注释作废——
故本脚本走**整表重建**把注释一并改正，避免留下"注释说高/中低、实际存 P2"的新陷阱（正是它坑了这次排查）。

## 迁移映射
  confidence ∈ ('高','中')  → conviction = 原值；confidence = 'P2'
  confidence == 'P2'        → conviction = NULL（该批本就没记判断强度，**留空不臆造**）；confidence = 'P2'
预期：conviction 高 208 / 中 151 / NULL 99；confidence 全 458 行 = 'P2'

沙箱须走 /tmp 副本往返（G-X33）。
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import sqlite3
import config

DDL_NEW = """
CREATE TABLE dim4_stock_analysis_new (
    date TEXT,
    stock_name TEXT,              -- 个股名称
    stock_code TEXT,              -- 股票代码 (可选)
    sector TEXT,                  -- 所属板块
    bull_reason TEXT,             -- 看好原因/逻辑
    bear_reason TEXT,             -- 看空原因/风险
    position_suggestion TEXT,     -- 仓位建议
    confidence TEXT,              -- 【信源轴】信源可信度分级: P0/P1/P2（与 recap_daily、industry_signals 同义）
    conviction TEXT,              -- 【判断轴】观点持有者对该股判断的把握度: 高/中/低（2026-07-30 从 confidence 拆出）
    source TEXT,                  -- 来源: 小鲍/天哥/综合
    related_news TEXT,            -- 关联消息/催化
    price_target TEXT,            -- 目标价/预期空间
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (date, stock_name)
)
"""

con = sqlite3.connect(config.RECAP_DB)
c = con.cursor()

before_n = c.execute("SELECT COUNT(*) FROM dim4_stock_analysis").fetchone()[0]
before_dist = c.execute("SELECT confidence, COUNT(*) FROM dim4_stock_analysis GROUP BY 1").fetchall()
print(f"迁移前: {before_n} 行, confidence 分布 {before_dist}")

# 护栏：本表 source 若出现非小鲍来源，信源分级不能一律 P2 → 中止交回人工
odd = c.execute("SELECT DISTINCT source FROM dim4_stock_analysis WHERE source NOT LIKE '%小鲍%'").fetchall()
assert not odd, f"🛑 出现非小鲍来源 {odd}，信源分级不可一律 P2，中止迁移交回人工判定"

c.execute("PRAGMA foreign_keys=OFF")
c.execute("DROP TABLE IF EXISTS dim4_stock_analysis_new")
c.execute(DDL_NEW)
c.execute("""
INSERT INTO dim4_stock_analysis_new
 (date, stock_name, stock_code, sector, bull_reason, bear_reason, position_suggestion,
  confidence, conviction, source, related_news, price_target, updated_at)
SELECT date, stock_name, stock_code, sector, bull_reason, bear_reason, position_suggestion,
       'P2',
       CASE WHEN confidence IN ('高','中','低') THEN confidence ELSE NULL END,
       source, related_news, price_target, updated_at
FROM dim4_stock_analysis
""")
mid_n = c.execute("SELECT COUNT(*) FROM dim4_stock_analysis_new").fetchone()[0]
assert mid_n == before_n, f"🛑 行数不符 {before_n} → {mid_n}，中止"

c.execute("DROP TABLE dim4_stock_analysis")
c.execute("ALTER TABLE dim4_stock_analysis_new RENAME TO dim4_stock_analysis")
c.execute("CREATE INDEX IF NOT EXISTS idx_stock_sector ON dim4_stock_analysis(sector)")
c.execute("CREATE INDEX IF NOT EXISTS idx_stock_reason ON dim4_stock_analysis(bull_reason)")
con.commit()

print(f"迁移后: {c.execute('SELECT COUNT(*) FROM dim4_stock_analysis').fetchone()[0]} 行")
print("  confidence:", c.execute("SELECT confidence, COUNT(*) FROM dim4_stock_analysis GROUP BY 1").fetchall())
print("  conviction:", c.execute("SELECT conviction, COUNT(*) FROM dim4_stock_analysis GROUP BY 1").fetchall())
print("  索引:", [r[1] for r in c.execute("PRAGMA index_list(dim4_stock_analysis)")])
print("  integrity:", c.execute("PRAGMA integrity_check").fetchone())
con.close()
