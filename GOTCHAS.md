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

## G013 — 日报自动化漏「情绪引擎回填」一步（已实装 SKILL）✅

**日期**: 2026-06-14 | **发现人**: CC + 烛阴（手动补跑暴露）

**问题**: 定时任务 `zhuzhao-market-fetch-daily-report` 的 SKILL 第 6 步只写「跑 `tools/gen_daily_report.py`」，但 `gen_daily_report` **不自管情绪回填**——它只读 recap.db 里 `emotion_cycle` 现有值。四表行情更新到新交易日后，若不先跑情绪引擎，日报情绪周期会**卡在上一已回填日**。

**根因**: SKILL 把「拉行情 → 出日报」当成两步，漏了中间的「情绪引擎按新行情回填 emotion_cycle」。手动补跑时必须显式 `python3 tools/emotion_engine_v2.py --apply` 才把 06-12 评分（51.8·春）算出来。

**影响（待验证）**: 周一 06-15 07:00 定时任务按现 SKILL 跑，**情绪周期大概率同样卡旧日**——日报行情是新日、情绪分是旧日，口径错位。

**解法（2026-06-23 已实装）**: zhuzhao SKILL「放回行情」与「出日报」之间已插「5.x 派生与兑现回填」段，第 1 步即 `python3 tools/emotion_engine_v2.py --apply`（随渊图入库/gap/closure/标的池一并补，recap.db 走 /tmp 副本防挂载盘 I/O）。Doctor 2026-06-23 批，三线核实后落 SKILL。✅

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
- A股四表无此问题，api.waditu.com 够用。

**更新（2026-06-14·白名单已开）**: ✅ Doctor 开白名单后实测——Yahoo 由 403 转 429（限频，但已能连出），`fetch_us_anchor.py --source yfinance` 沙箱秒回。本次 19 只美股锚 06-10→06-12 全量补齐（/tmp 副本作业＋整库放回，其余 7 表只增不减、integrity ok）。stooq.com 仍 000 不通，tushare 200。**沙箱 yfinance 补跑路现已打通**，Mac 本地不再是唯一路。⏳→✅

---

## G015 — fetch_yf 增量首日 pct_chg=None（窗口边界）

**日期**: 2026-06-14 | **发现人**: CC（补跑美股锚时实测）

**问题**: `fetch_us_anchor.py --from 2026-06-10` 增量补跑后，每只票窗口首日 06-10 的 `pct_chg` 全为 `None`，REPLACE 入库后该日真实涨幅被洗空（如 NVDA 06-10 实为 −3.73% 却写成 None）。

**根因**: `rows_from_closes` 用「下载窗口内」环比算 pct，窗口首日无前一行 → pct=None；库里已有的前一交易日（06-09）真前收没被用上。tushare 路早已规避（直接用接口自带 pct_change），但 yfinance/stooq 路（共用 `rows_from_closes`）没规避。

**解法**: `fetch_yf`/`fetch_stooq` 下载起点向前回看 `_LOOKBACK_DAYS=10` 个日历日，全序列算完 pct 后裁回 `from_date`——首日 pct 由真实前一交易日得出，回看行不入库。已实测：NVDA from 06-10 返回 3 行、首日 pct=−3.7322。✅

---

## G016 — 个股前向回测：覆盖断层致窗口"跳"数月＝假收益

**日期**: 2026-06-15 | **发现人**: CC（标的级胜率回测自审）

**问题**: `signal_winrate_backtest.py` 算前向 next3d 时，天孚通信信号日 2025-11-11 取到的"前向 3 日"竟是 2026-06-03/04/05（7 个月后），收益完全错。

**根因**: `Market-Data.stock_daily` **全市场口径只从 20260603 起**（项目已知 GOTCHA·行情口径断裂；早于此个股多无行情）。"信号后第一个有数据的交易日"逻辑会静默跳到数月后的首个可用日，算出无意义收益。

**解法**: 加**邻近守卫**——首个前向交易日距信号日须 ≤ `ADJ_MAX_DAYS=10` 自然日，否则判该股信号期无行情、跳过（计入 `n_gap`、收益列留 NULL 不计胜率分母）。实测 114 个早于 20260603 的信号被正确跳过。✅ 教训：**任何"信号后 N 日"回测都要校验前向日与信号日邻近**，不能信"第一个可用日"。

---

## G017 — ticker_resolver 种子覆盖窄 → 标的级回测样本受限

**日期**: 2026-06-15 | **发现人**: CC（标的级胜率回测）

**问题**: `industry_signals` 标的 name→ts_code resolve 仅 8%（dim4 17%、yuantu 100%），自有池真正进胜率分母只剩 ~103，样本偏小、胜率代表性弱。

**根因**: `ticker_resolver` 名→码索引种子仅 ~35 条（tushare-cache `stocks` 小表 + valuation + 渊图自带码），全量 A 股名↔码缺 `stock_basic`（句芒 tushare 模块未 populate）。

**解法（待办·归口句芒）**: 句芒在真机跑 tushare `stock_basic` 写入 `Market-Data/tushare-cache/tushare.db`（命令见 `ticker_resolver.py how-to-populate`）——解析器自动吃、无需改代码。烛阴沙盒不抓 tushare（守取数归口）。⏳ 补后回测样本量与代表性显著改善。

---

## 统计

| 类别 | 总数 | 已改正 | 待处理 |
|------|------|--------|--------|
| 概念 | 1 | 1 | 0 |
| SQL | 3 | 3 | 0 |
| 数据质量 | 3 | 3 | 0 |
| NLP | 2 | 1 | 1 |
| 外部 API | 2 | 2 | 0 |
| 算法 | 2 | 2 | 0 |
| 路径/迁移 | 1 | 1 | 0 |
| 代码接口 | 1 | 0 | 1 |
| 自动化/流程 | 1 | 0 | 1 |
| 回测/数据覆盖 | 2 | 1 | 1 |
| **总计** | **17** | **13** | **4** |
