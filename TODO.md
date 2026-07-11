# TODO — 烛照九阴（烛阴/九儿 · 复盘/新闻线）

## Active

- [x] 🧭【容量闸按强弱重构 · 第四栏】✅ 2026-07-10 完成。原**组合层全局闸**（`kday≥kcap`⇒满载一刀切）改为**强度排位制**（Doctor 裁定）：确认走强候选按 `e20`（20日累计超额=强弱）降序，市场只供养最强 `round(K_cap)` 条 → 前 K_cap 名「容量允许」入栏、余者排位靠后不列；强新线自然挤掉走弱旧线＝轮动。「新线 vs 在场强线」（e20>5 已入强线篮）仅作标签、不决定放行；缺成交额(K_cap=None)标「容量未知」照列。落 `tools/gen_daily_report.py:gather()` 机会块 + 第四栏 header 注记。合成数据五情形单测通过（排位/满载收紧/轮动挤入/缺数/极稀成交空栏）。

- [ ] ⚡【更新健康埋点·派工v1】复盘入库跑批收尾，写 `~/Documents/Database/烛照九阴/_health.json`（`updated_at` + `update_ok`），并在 `Claude/Projects/海螺姑娘/data/asset_manifest.json` 的 recap.db 节点补 `"health_file": "Database/烛照九阴/_health.json"`（补完全局资产看板自动点亮）。详 `Claude/Projects/海螺姑娘/dashboard/UPDATE_HEALTH_派工_v1.md`（任务卡 ③）
