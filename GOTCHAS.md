# 📒 错题本 (Gotchas)

> 记录本项目使用中的错误、不足与改进，改正后打勾。

---

## G001 — 板块概念混淆：光模块 ≠ CPO

**日期**: 2026-05-07 | **发现人**: 天哥

**问题**: 初始设计把"光模块/CPO"归为一个标准板块

**根因**: 缺乏光通信行业知识，误认为两者是同一概念

**解法**: 严格区分为两个独立板块 ✅

---

## G002 — SQL 字段不存在 (key_points)

**日期**: 2026-05-07

**问题**: 批量导入时报错 `table dim3_sentiment_tech has no column named key_points`

**根因**: 使用了不存在的字段名，实际应使用 `support_level`

**解法**: 修正 INSERT 语句 ✅

---

## G003 — JOIN 列名歧义

**日期**: 2026-05-07

**问题**: JOIN 查询时报错 `ambiguous column name: date`

**根因**: 多表 JOIN 时未指定表名前缀

**解法**: 使用 `rd.date` 明确指定来源表 ✅

---

## G004 — UNION ORDER BY 不匹配

**日期**: 2026-05-07

**问题**: `1st ORDER BY term does not match any column in the result set`

**解法**: 改用 `ORDER BY 1` (按列位置排序) ✅

---

## G005 — 重复数据导入

**日期**: 2026-05-07

**问题**: Phase 2 和 Phase 3 导入时日期重叠，Dim3/Dim4 出现 107 条重复

**解法**: 执行去重 SQL，保留每个日期最新的 rowid ✅

---

## G006 — 量化指标不足导致偏差

**日期**: 2026-05-07

**问题**: 量化系统只有 3 个指标，全部判定为"冰点"

**解法**: 接入 tushare + 句芒数据，补全至 6 个指标 ✅

---

## G007 — NLP 提取噪音大

**日期**: 2026-05-07

**问题**: 四维度课件提取的"主线"字段包含大量无关文字

**解法**: 增加上下文窗口判断，在对应章节内提取 ⏳

---

## G008 — 文本标准化误替换

**日期**: 2026-05-07

**问题**: `standardize_text()` 产生乱码（子串匹配问题）

**解法**: 推荐使用 `extract_sectors()` 替代 `standardize_text()` ✅

---

## G009 — tushare 频率限制

**日期**: 2026-05-07

**问题**: `limit_list_d` 接口 200 次/分钟限制，批量拉取时触发

**解法**: 增加 sleep 间隔 + 分批执行，剩余后续补拉 ✅

---

## G010 — 量化阈值需适配实际指标数

**日期**: 2026-05-07

**问题**: 原阈值基于 7 指标满分 70 分，实际只有 4-6 个指标

**解法**: 调整阈值为 4 指标版本 (冰点≤10/复苏11-20/火热21-30/退潮>30) ✅

---

## G011 — cycle_compare 依赖已改名函数

**日期**: 2026-06-06 | **发现人**: CC（大修冒烟测试）

**问题**: `import cycle_compare` 报 `ImportError: cannot import name 'calculate_emotion_score' from 'cycle_quant'`

**根因**: `cycle_compare.py` 引用 `cycle_quant.calculate_emotion_score`（导入但从未调用）和 `compare_cycles`（实际使用），二者均在历史重构中丢失

**解法**: 删除无用的 `calculate_emotion_score` 导入；在 `cycle_quant.py` 补回 `normalize_stage`（4 大类归一）+ `compare_cycles`（双轨比较）。实测 import 通、`cycle_compare.py` 跑通真库 ✅

**附带发现**: 跑出来双轨一致率仅 37.6%，因 `cycle_quant` 表 85 条里 83 条判为『冰点』（量化阶段退化）——属历史数据/阈值问题（参见 G006/G010），非本次代码缺陷，待用公共行情库重算量化分后复核。

---

## G012 — 阿里云死路径全线硬编码（大修已清）

**日期**: 2026-06-06 | **发现人**: CC

**问题**: 数灵转移后，旧项目树所有脚本仍写死 `/home/admin/openclaw/...` 及项目内 `db/recap.db`，且 `from .lib.logger` 相对导入使脚本无法直接运行——整条工具链对新数据层 `Database/` 不可用

**根因**: 迁移只搬了数据，未 repoint 代码

**解法**: 建根目录 `config.py` 单一可信源，16 个现役脚本统一经 config 取库路径、修 logger 导入、删阿里 sys.path；一次性脚本归档 `_legacy/`。recap_cli 实测连通真库 ✅

---

## G013 — 日报自动化漏「情绪引擎回填」一步（提案改 SKILL）⏳

**日期**: 2026-06-14 | **发现人**: CC + 烛阴（手动补跑暴露）

**问题**: 定时任务 `zhuzhao-market-fetch-daily-report` 的 SKILL 第 6 步只写「跑 `tools/gen_daily_report.py`」，但 `gen_daily_report` **不自管情绪回填**——它只读 recap.db 里 `emotion_cycle` 现有值。四表行情更新到新交易日后，若不先跑情绪引擎，日报情绪周期会**卡在上一已回填日**。

**根因**: SKILL 把「拉行情 → 出日报」当成两步，漏了中间的「情绪引擎按新行情回填 emotion_cycle」。手动补跑时必须显式 `python3 tools/emotion_engine_v2.py --apply` 才把 06-12 评分（51.8·春）算出来。

**影响（待验证）**: 周一 06-15 07:00 定时任务按现 SKILL 跑，**情绪周期大概率同样卡旧日**——日报行情是新日、情绪分是旧日，口径错位。

**提案解法（propose-then-confirm，未直改）**: 在 zhuzhao SKILL 第 6 步「生成日报」**之前**插入一步：`python3 tools/emotion_engine_v2.py --apply`（沙箱写 recap.db 实测无 I/O 错，引擎自带备份）。待 Doctor 批准后改 SKILL。⏳

---

## G014 — 美股锚补不动＝网络白名单，非缺依赖

**日期**: 2026-06-14 | **发现人**: CC（实测确认）

**问题**: 沙箱里 `fetch_us_anchor.py` 三信源全失败，易误判为缺包。

**根因（实测）**: **不是缺依赖**——yfinance / tushare 都能现场 `pip install --break-system-packages` 装上。真因是**网络白名单**：
- Yahoo 主机 `query1.finance.yahoo.com` / `query2.finance.yahoo.com` / `fc.yahoo.com` / `finance.yahoo.com` → 代理 **403 Forbidden**（yfinance 装上也连不出去，取 0 行）
- `stooq.com` → 同样 403
- 仅 `api.waditu.com`（tushare）通，但 `us_daily_adj` 试用态限频 **1次/分钟**，19 只票 ~20 分钟，撞沙箱单条 bash **45s 上限** + 后台进程不跨调用存活 → 一次拉不全（只抢到首票 AAPL）。

**解法**:
- 沙箱要补 → 需把 Yahoo（query1/2.finance.yahoo.com、fc.yahoo.com）或 stooq.com 加进网络白名单。
- 不加白名单 → Mac 本地 `python3 scripts/fetch_us_anchor.py --from YYYY-MM-DD`（yfinance 不走该代理，秒回）= 当前唯一可靠路。
- A股四表无此问题，api.waditu.com 够用。⏳

---

## 统计

| 类别 | 总数 | 已改正 | 待处理 |
|------|------|--------|--------|
| 概念 | 1 | 1 | 0 |
| SQL | 3 | 3 | 0 |
| 数据质量 | 2 | 2 | 0 |
| NLP | 2 | 1 | 1 |
| 外部 API | 2 | 1 | 1 |
| 算法 | 1 | 1 | 0 |
| 路径/迁移 | 1 | 1 | 0 |
| 代码接口 | 1 | 0 | 1 |
| 自动化/流程 | 1 | 0 | 1 |
| **总计** | **14** | **10** | **4** |
