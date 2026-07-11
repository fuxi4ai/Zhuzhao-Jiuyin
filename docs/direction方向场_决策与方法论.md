---
title: direction 方向场 · 决策与方法论
tags: [烛照九阴, direction, 决策, 方法论]
created: 2026-06-25
updated: 2026-07-10
type: decision
---

# direction 方向场 · 决策与方法论

> 2026-06-25 立。配套 PRD `brain/logs/checkpoints/2026-06-25_信号direction方向场_PRD.md`、日志 `agents/烛阴/logs/2026-06-25-信号方向场与星空D>S.md`。

## 一、方向判定方法论（★ 核心经验）

**信号方向（多/空）是语义判断，机械规则两头都会错。**

- 试过的机械规则、都失败：
  - **KG `trend`+`category`**：把「供给**约束/短缺**＝利好(多)」误判成空（如 DRAM 产能扩张约束，trend=↓ 指"产能增速↓"＝供给紧＝利好，实测 gap_desc「二段主升·累计+36.6%」）。
  - **关键词（过剩/压制/逆风…）**：把成本通胀两面信号误判（id60/62/88 一刀切判空）。
- **正确判据 = 看受益标的所处链位 + 成本/提价哪边胜**：
  - 受益标的在**上游 / 可提价转嫁** → 提价胜 → **多**（如 TEC 基板·富乐华；DRAM 约束·三星海力士）。
  - 明确**供给过剩 / 下游需求被压制** → 成本胜/过剩 → **空**（光伏玻璃过剩；存储涨价压制消费电子出货-12.9%）。
  - 成本通胀类**不摆烂"第三态"**（Doctor 否：第三态＝没结论）；要给"成本涨价 vs 产品提价哪边胜"的实质判断。

**落地口径 = 「规则出候选 + 逐条核 KG 描述定案」核定清单制**：
- 入库 direction 以 `CURATED_SHORT`（按 signal_node id 的核定空头清单）为准，仅明确过剩/下游承压入清单。
- auto 关键词规则**降级**为只对清单外新信号生成"疑似空头"候选打日志、**不直接入库**，待人工复核扩充清单（`tools/backfill_direction.py`）。
- 当前核定空头 2 条：`concept_SolarGlassOversupply`、`concept_ConsumerElectronicsMemoryHeadwind2026`。

## 二、direction 场架构（决策）

1. **schema**：`yuantu_buy_signals` 加 `direction` / `direction_src` / `direction_flip_date`（`tools/backfill_direction.py` 回填）。
2. **closure 方向感知**（`closure_engine.py`，多头主口径零回归）：
   - 多头(多)：原长头机器不动（open→closing→closed→dormant，Y=3/X=5%/DD=5pp）。
   - 空头纯卖出：清 `date_realized`、不判进入趋势、只风险提示。
   - 买入转卖出：记 `direction_flip_date`，`excess_peak − excess_cum ≥ 5pp` 触发停跟。
3. **日报分治**（`gen_daily_report.py`）：多头进正向台账（产业信号买入 / 进入趋势天数）；空头进「⚠️ 空头风险提示」块（不正向追踪、不计进入趋势），停跟标「🛑」。持续失衡标签回归守恒=41。
4. **星空同源**：正面星(D>S)=direction 多，与日报口径**一处定**，不另立；persistent_imbalance 改星空走 fallback（见 §三）。

## 三、为何 persistent_imbalance 改星空走 fallback

`persistent_imbalance` 是日报+星空**共享 canon tag**（日报渲染"持续失衡"41 处 + `yuantu_client.SIGNAL_CATS` 校验）。改本体语义会波及日报 → 走 fallback：不动本体、星空层派生 `persistent_imbalance (D>S)`、只改星空显示（只高亮正面星）。详见通用教训 G-X29。

## 四、第四栏容量闸 = 强度排位制（决策 · 2026-07-10）

**背景**：日报第四栏「确认走强（e20/e5>0），**且容量允许**」原用**组合层全局闸**——`D["capacity"]["state"]`（`kday≥kcap`⇒满载）一刀切套在所有确认走强的线上。查出两处病：① 白名单曾含「满载」，与栏标题/容量仪表（`can_new=kday<kcap`）/风险栏三处「满载＝不允许」自相矛盾（已止血去掉）；② 更深——**第四栏的线不一定是新线**，已在场的强线本就是凑成 `kday`、把容量顶满的那批，对它谈「满载不能开新线」是错位（持旧线 ≠ 开新线）。

**Doctor 裁定（AskUserQuestion 选型）＝强度排位制**，取代全局 state 闸：

1. **强弱度量 = `e20`**（20日累计超额，themes 已按 `-e20` 排序）。
2. **容量预算 = `round(K_cap)`**（当日成交额按经验表能供养的主线条数）。
3. **判定**：确认走强候选按 e20 降序，前 `round(K_cap)` 名「容量允许」入栏、余者排位靠后 `break` 不列 → **强新线自然挤掉走弱旧线＝轮动**。
4. **「新线 vs 在场强线」（`e20>5` 已入强线篮）仅作标签**，不决定放行；放行只由强度排位决定。
5. **缺成交额（K_cap=None）→ 标「容量未知」照列**（数据真实性铁律：缺数标注不臆断）。
6. note 显示 `排位 {rank}/{budget} · {role}`；「排位 3/5」的分母 5 ＝当日容量上限 `round(K_cap)`，非候选数。

**为何不选「在场恒列＋新线补位」**：旧线篮固定阈值 `e20>5` 会让满载下新线几乎永远挤不进（退化成止血现状），双阈值也更绕。强度排位制单参数 e20、口径最简、直接兑现「按强弱可轮动」。

**落点**：`tools/gen_daily_report.py:gather()` 机会块 + 第四栏 header vintage 注记。合成数据五情形单测通过（排位/满载收紧/轮动挤入/缺数照列/极稀成交空栏）。日志 `brain/logs/2026-07-10-烛照九阴容量闸强度排位制重构.md`。
