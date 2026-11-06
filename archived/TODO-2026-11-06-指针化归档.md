# TODO — 烛照九阴（烛阴/九儿 · 复盘/新闻线）

## Active

- [x] 🧭【容量闸按强弱重构 · 第四栏】✅ 2026-07-10 完成。原**组合层全局闸**（`kday≥kcap`⇒满载一刀切）改为**强度排位制**（Doctor 裁定）：确认走强候选按 `e20`（20日累计超额=强弱）降序，市场只供养最强 `round(K_cap)` 条 → 前 K_cap 名「容量允许」入栏、余者排位靠后不列；强新线自然挤掉走弱旧线＝轮动。「新线 vs 在场强线」（e20>5 已入强线篮）仅作标签、不决定放行；缺成交额(K_cap=None)标「容量未知」照列。落 `tools/gen_daily_report.py:gather()` 机会块 + 第四栏 header 注记。合成数据五情形单测通过（排位/满载收紧/轮动挤入/缺数/极稀成交空栏）。

- [x] ⚡【更新健康埋点·派工v1】✅ **2026-07-31 核实已达成 · Doctor 裁定销账**（功能实际在 **2026-07-01「G-X45 第三批」**就位，早于本 TODO 文件上次更新的 07-10，属**做完未销账**）。
  **两项诉求均已兑现**：① `_health.json` 由 `scripts/recap_health.py` 产出并入定时链（`recap-kejian-review` 班末步必跑）；② `asset_manifest.json` 的 recap.db 节点已有 `"health_file": "${CONCH_DATABASE_MOUNT}/烛照九阴/_health.json"`，全局资产看板已能自动点亮——2026-07-31 实测该节点随体检修复由 `stale` 翻回 `healthy`、`global-asset-inventory` artifact 已同步。
  **⚠ 字段名与派工单不同，这很可能就是当初没销账的原因**：派工单写 `updated_at` + `update_ok`，实际实现用的是 `generated` + `overall`（语义等价）。若下游有代码按派工单字段名取值，需改读实际字段。
  **2026-07-31 另加固**（本次自查根因修）：`_health.json` 新增 `phase`（`ingest-check` 初检 / `eod-final` 当日终检）与 `db_mtime_at_check`（比对 recap.db 当前 mtime 即可判本报告是否已被后续写库作废）；`zhuzhao-market-fetch-daily-report` 班补 5f 步终检——原先体检钉在 15:30 而写库延续到 16:00，报告结构上永远差一轮。详 `Database/烛照九阴/_索引.md` §三「体检轮次」。
