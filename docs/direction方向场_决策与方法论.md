---
title: direction 方向场 · 决策与方法论
tags: [烛照九阴, direction, 决策, 方法论]
created: 2026-06-25
updated: 2026-06-25
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
