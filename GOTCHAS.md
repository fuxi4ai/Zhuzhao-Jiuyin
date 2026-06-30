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

## G018 — 美股锚信源迁 web_fetch/stockanalysis（stooq 沙箱彻底死透）✅

**日期**: 2026-06-23 | **发现人**: 九儿（Doctor 开 stooq 白名单后实测）

**问题**: G014「更新（白名单已开）」记 yfinance 沙箱已通；但 06-23 实测三源全废：yfinance 沙箱 pip 装不上 + yahoo 403；stooq 403；tushare `us_daily_adj` 无权限（code 40203，试用接口已不可用）。Doctor 遂开 `stooq.com` 白名单想救免费路。

**根因（逐层实测）**:
- 开白名单后 stooq 19 只 **403→200**（代理确放行），但回的不是 CSV 而是 **JS 验证墙**（"requires JavaScript to verify your browser"，一段 SHA-256 PoW → POST `/__verify` 拿 cookie）。
- 九儿把整套墙跑通：解出 PoW（n≈25109 秒级）+ 拿到合法 `auth` cookie（`Max-Age=86400`＝24h），带 cookie 重拉 CSV 仍 **`Access denied`**。→ 墙不止 JS 层，更深一层**认 IP**，沙箱出口代理 IP 被拒。手搬 Mac 浏览器 cookie 进沙箱（IP/UA 变）同样会被拒，且 cookie 仅 24h。
- 故 **stooq 从沙箱彻底死透**：白名单解决「连得上」，解决不了「认不认沙箱 IP」。

**解法（现行·零成本·沙箱原生）**: 美股锚改 **agent web_fetch `stockanalysis.com/stocks/{t}/`**（服务端渲染、绕 JS 墙、换出口避开沙箱 IP 封禁），解析「At close 日期/收盘/1D%」→ `fetch_us_anchor.py --source stockanalysis --infile <json>`。已验 3/3 含冷门 ALM。SKILL 步骤 3 + 脚本已实装。
- **close 不复权**：展示锚只做隔夜参照，单日涨幅自洽，不复权无碍。
- **CDN 陈旧坑**：冷门票回缓存旧页（实测 RKLB 停 Jun18 / NVDA·ALM 到 Jun22）——**按页面真实「At close」日期入库**、绝不顶目标日，结构上杜绝把陈旧数伪装成新日期；脚本日志报「新鲜/陈旧/缺」。
- stooq/yfinance/tushare 函数**保留不删**，仅作 Mac 端手动备胎/历史回填。✅

---

## G019 — recap.db 被挂载盘回写写坏（quick_check 漏报）✅

**日期**: 2026-06-29 | **发现人**: 九儿（手动补 6/26 报时 integrity_check 揪出）

**问题**: recap.db 结构损坏——`PRAGMA integrity_check` 报 `2nd reference to page 959…` 一串 b-tree 自指环；直连报 `disk I/O error`。industry_signals 1299→1316（多 17 条），行数据未丢但骨架坏。

**根因**:
- 6/27 课件入库回写 recap：走了 /tmp 副本 + 整文件 cp 回挂载盘（套路对），但**整文件 cp 写挂载盘偶发写坏**（flaky 挂载层），且回写后**只跑了 `quick_check=ok`**——quick_check 不逐页核对 b-tree 交叉引用，**漏报**结构损坏 → 坏了没人知道。
- 二号潜雷：`tools/_ingest_九儿_*.py` 默认 `DB=~/Documents/Database/烛照九阴/recap.db`（直指挂载盘真盘）+ 裸 `con.commit()`，沙箱误跑即当场 disk I/O 损坏。
- 关键实测：cp 写**新文件名**到挂载盘 OK（integrity ok），但 cp **覆盖**既有 recap.db **必坏**（3/3 失败）→ 真盘换库只能在 **Mac 原生终端**做。

**解法** ✅:
- 校验铁律：凡 db 回写挂载盘后**必跑 `integrity_check`（非 `quick_check`）**才算成功；失败即回退备份。
- `_ingest_九儿_*.py` 已加固：认 `ZZJY_DATABASE_ROOT`、沙箱拒写挂载盘真盘（除非显式 `ZZJY_ALLOW_MOUNT_WRITE`）、写后强 integrity_check。
- 恢复手法：逐表 `SELECT*→INSERT` 重建干净库（损坏多在索引/页指针，行数据可全救），integrity ok 后落 `recap.db.recovered_*`；真盘换库走 Mac 终端 `cp 恢复件→recap.db` + integrity 复核（沙箱覆盖既有库必坏）。损坏件隔离留证 `recap.db.CORRUPT_*`。

**更新（2026-06-29 · 探针复测 + 护栏集中化 Phase-1）**:
- **归因修正**：沙箱探针实测——文件级 `cp` 覆盖 / `cp 新名 + mv 原子替换` 整库放回挂载盘**都安全（各 10/10 ok）**，没复现「cp 覆盖必坏 3/3」。真凶是**对挂载盘上的库直接 live `commit`：8/8 `disk I/O error` + 甩下热 `-journal`** → 下一个进程开库触发 journal 回放，回放成「孤儿索引 / 页双引用」。即：腐化源是 live 写、不是 cp。
- **审计**：扫全仓写入口，护栏当时只在 `_ingest_九儿_2026-06-25/26.py`（复制粘贴），连同胞 `_ingest_28` 都漏。完整清单见 `docs/审计_DB写入口越界清单_20260629.md`（Tier-1 硬编码真盘无护栏 4 个 / Tier-2 走 config 无强制 15 个）。
- **Phase-1 已落地**：`config.py` 加中央硬拒绝护栏 `connect_write(path)`（路径含 `/sessions//mnt/` 且未设 `ZZJY_ALLOW_MOUNT_WRITE` 即拒写）；4 个 Tier-1 迁移之（`_ingest_九儿_2026-06-28` / `dedup_kejian` / `xiaobao_position_write` / `bt_xiaobao_pos_3d`）。py_compile + 护栏单测过。
- **Phase-2 待办**：Tier-2 共 15 文件写连接收口到 `connect_write`；中央生效后删 `_ingest_25/26` 旧护栏；cp-back 卫生写进 SKILL（放回前确认无 `-wal/-journal`、`cp 新名 + mv 原子替换`、放回后强制 `integrity_check` + 失败自动回滚）。

---

## G018 — `_health.json` 每日假红：体检跑在末位装表之前

**日期**: 2026-06-30 | **发现人**: Doctor/CC | **状态**: 已修 ✓

**问题**: 公共行情库 `_health.json` 每日报 `overall:fail`（limit_list_daily/theme_etf_daily 显示落后），实为误报。根因＝句芒 `market-data-daily-update`(06:15) 末步跑 `market_health.py` 生成 health，但 limit_list/theme_etf 由九儿 `zhuzhao-market-fetch-daily-report`(07:00) 才装，且九儿不补跑体检 → health 永远在「这俩表还停昨日」的瞬间被冻成红灯，海螺看板会误标红。

**解法** ✅: 把 `market_health.py` 追加为九儿任务末步（zhuzhao SKILL.md 步骤 5.5）——谁最后写库谁亮灯。句芒第 9 步那次 06:2x 体检成冗余（无害、约 45 分钟后被九儿覆正），本轮不动句芒。

**预防**: 多写库者共用一个健康产物时，体检必须挂在**最后一个写库者**末步，否则中途快照必假。

---

## G019 — Cowork Artifact 部署须注入 color-scheme:light

**日期**: 2026-06-30 | **发现人**: Doctor/CC | **状态**: 已修 ✓

**问题**: `gen_daily_report._deploy_to_artifact` 直写 `Artifacts/zhuzhao-jiuyin-daily/index.html`（绕过 `update_artifact`、manifest 不刷但渲染读文件本身）。但报告 HTML 的 `:root` 没有 `color-scheme`，Cowork artifact 渲染器会随系统转暗模式，暖色范式在暗底下发灰。

**解法** ✅: `_deploy_to_artifact` 写文件前注入 `:root{color-scheme:light;...}`（已有则跳过）。以后每天自动部署的 Artifact 都强制亮色。

**预防**: 凡自包含 HTML 要在 Cowork artifact 渲染、且设计是固定亮色范式 → `:root` 必带 `color-scheme:light`。

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
| 自动化/流程 | 3 | 2 | 1 |
| 回测/数据覆盖 | 2 | 1 | 1 |
| **总计** | **19** | **15** | **4** |
