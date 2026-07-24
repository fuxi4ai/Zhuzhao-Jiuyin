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

## G020 — `dedup_kejian.py` 在沙箱平铺挂载下 `_documents_root()` 越界崩溃

**日期**: 2026-07-01 | **发现人**: 九儿（recap-kejian-daily-ingest 定时任务） | **状态**: ⏳ 待解决（有等价 workaround，未改脚本）

**触发场景**: Cowork 沙箱内直接 `python3 tools/dedup_kejian.py scan`（已挂载 Database 与本项目）。

**错误信息**: `IndexError: 6`，出在 `_documents_root()` 兜底分支 `return here.parents[6]`——沙箱把各挂载目录**平铺**在 `/sessions/*/mnt/` 下（如 `mnt/烛照九阴`、`mnt/Database`），不是 Mac 上 `~/Documents/Claude/Projects/Financial/烛照九阴` 那种深层嵌套；脚本从 `__file__` 向上找名为 `Documents` 的祖先目录找不到，落到 `parents[6]` 时层数不够直接抛异常（**模块顶层执行，导入即崩**，无法在导入后再 monkeypatch）。

**解决方案** ✅（等价复现，未改脚本）: 不 import 该模块，改为内联重写 `scan()` 同款逻辑（filename+md5 对比 `processed_kejian`），路径直接用沙箱真实挂载点 `mnt/Database/烛照九阴/{recap.db,Raw-Recap}`。去重口径完全一致，结果可信（本次核验：223 课件、223 已处理、待处理 0，与真库一致）。

**预防 / 待办**: `config.py._find_database_root()` 已支持 `ZZJY_DATABASE_ROOT` 环境变量覆盖，但 `dedup_kejian._documents_root()` 是独立实现、没吃到这层。彻底修法：把 `dedup_kejian.py` 的 `RECAP_DB`/`RAW_DIR` 改为 `import config` 后取 `config.RECAP_DB`/`config.RAW_RECAP_DIR`（并让兜底分支判长度再取，不裸 `parents[6]`）。因涉及改脚本，按 propose-then-confirm 交哥哥拍板，本次仅记录、未动代码。

**补充解法**（2026-07-02·九儿）：找到一种**不改脚本、原脚本原样可跑**（含 `scan` 与 `record` 两条命令）的等价 workaround——伪造一段带字面量 `Documents` 祖先目录的路径树，把真实脚本**复制**（非软链，避免 `Path.resolve()` 把符号链接解析穿透丢失 `Documents` 这一级）过去，再用符号链接把 `Database/烛照九阴/{Raw-Recap, recap.db}` 分别指回真实 Raw-Recap（只读用）与 `/tmp/dbroot` 工作副本（可写）：
```bash
mkdir -p /tmp/fake/Documents/Claude/Projects/Financial/烛照九阴/tools
mkdir -p /tmp/fake/Documents/Database/烛照九阴
cp <项目根>/tools/dedup_kejian.py /tmp/fake/Documents/Claude/Projects/Financial/烛照九阴/tools/
cp <项目根>/config.py            /tmp/fake/Documents/Claude/Projects/Financial/烛照九阴/
ln -sfn <真实挂载>/Database/烛照九阴/Raw-Recap /tmp/fake/Documents/Database/烛照九阴/Raw-Recap
ln -sfn /tmp/dbroot/烛照九阴/recap.db          /tmp/fake/Documents/Database/烛照九阴/recap.db
cd /tmp/fake/Documents/Claude/Projects/Financial/烛照九阴 && python3 tools/dedup_kejian.py scan --json
```
`_documents_root()` 沿 `__file__.resolve()` 向上找到 `/tmp/fake/Documents`（真实目录，非软链，故不会被 resolve 穿透），`RAW_DIR`/`RECAP_DB` 由此拼出，I/O 时透明穿过符号链接读写目标。`record --all-new` 的 `config.connect_write()` 护栏对 `RECAP_DB` 路径 `.resolve()` 后落在 `/tmp/...`（非 `/sessions/`、`/mnt/`），正常放行写入 `/tmp/dbroot` 副本，无需 `ZZJY_ALLOW_MOUNT_WRITE`。比"内联重写 scan()"更完整：原脚本零改动，`scan`+`record` 全流程复用，去重口径与未来脚本更新自动同步。

---

## G021 — `ZZJY_DATABASE_ROOT=/tmp/dbroot` 会连带带偏渊图只读路径

**日期**: 2026-07-01 | **发现人**: 九儿（定时任务派生回填第四次触发） | **状态**: ✅ 已解决（workaround，未改代码）

**触发场景**: 沙箱内跑 recap.db 派生回填，`export ZZJY_DATABASE_ROOT=/tmp/dbroot` 后执行 `tools/sync_buy_signals.py`。

**错误信息**: `渊图 latest.json 不存在: /tmp/dbroot/行业研究/mapping/latest.json（检查软链 / config.YUANTU_KG）`，随后契约健康检查 `sys.exit(2)` 报 `NameError: name 'sys' is not defined`（`build()` 里用了 `sys.exit` 但顶部只 import 了 `_sys`，属另一个小 bug）。

**更新 2026-07-05（九儿·07-03 补报）**: `sync_buy_signals.py:74` 的 `sys.exit(2)` → `_sys.exit(2)` **已改代码修掉**（此前失败路径会 NameError 掩盖"渊图未接入"真因，现能干净退出并打印 healthcheck 错误）。软链 workaround 仍照旧（渊图只读不入 /tmp）。

**根因**: `config.py` 的 `DATABASE_ROOT` 是单一变量，`RECAP_DB`（可写）与 `YUANTU_ROOT`（只读引用）共用同一根；为让 recap.db 走 /tmp 副本设的 `ZZJY_DATABASE_ROOT` 会把渊图路径也一并指向 /tmp，而渊图 KG 按规矩不拷进 /tmp（只读外部源），于是路径下空空如也。

**解法**: `ln -sf ~/Documents/Database/行业研究 /tmp/dbroot/行业研究`——只读符号链接指回真实挂载盘，不拷贝任何数据，满足"渊图只读、不入 /tmp 副本"的铁律，同时让 `config.YUANTU_ROOT`/`YUANTU_KG` 解析成功。跑完 sync_buy_signals 后无需清理（/tmp 会话结束即消失）。

**预防**: 以后凡设 `ZZJY_DATABASE_ROOT=/tmp/dbroot` 走 recap.db 副本往返时，若同一轮还要跑依赖渊图只读源的脚本（sync_buy_signals 等），记得先补一条渊图目录软链，否则会误判"渊图未接入"。

---

## G022 — 回测 logic_type 与渊图 signal_type 是两套机制词表（仅 3 交集）

**日期**: 2026-07-08 | **发现人**: CC（Doctor 问"其他机制里没信号么"追出） | **状态**: ✅ 已解决

**触发场景**: 日报「机制排行」按 own 标的池回测 logic_type（agg_stock.json）列 5 机制，用 `signal_type LIKE '%event_driven%'` 统计各机制在途渊图信号数，结果 event_driven/price_driven/tech_innovation 恒为「在途 0」，被误读成「暂时没信号」。

**根因**: 回测胜率来自 **own 标的池 logic_type**（`stock_tracking`/`dim4` 给标的分类），在途数来自 **渊图 `yuantu_buy_signals.signal_type`**（给灯亮买入信号打的机制标签）——两套词表只有 supply_shock / demand_surge / persistent_imbalance 三个交集；event_driven / price_driven / tech_innovation 渊图侧**根本不存在**，LIKE 匹配恒 0（全表 distinct 核实：signal_type 只有这三词及其逗号组合）。

**解法**: 机制排行只列渊图 signal_type 实有的机制（供给冲击 / 持续失衡；需求爆发在 glow 卡置顶），去掉三个渊图无标签的机制防误读。

**预防**: 凡把「回测 logic_type 口径」的结论与「渊图 signal_type 口径」的实时数放同一处展示，先核两套词表交集；非交集机制别用 LIKE 硬匹配（会恒 0 且误导）。要纳入 event_driven 等标的池机制须先在渊图信号侧建标签映射（数据层活）。

---

## G023 — gen_daily_report._deploy_to_artifact 绕过 manifest，卡片时间戳不刷新

**日期**: 2026-07-08 | **发现人**: CC（Doctor「推一下 artifact」时查出） | **状态**: ✅ 已解决（workaround·手动 update_artifact）

**触发场景**: 改完日报脚本、`python3 tools/gen_daily_report.py` 出正式报后，Cowork artifact `zhuzhao-jiuyin-daily` 内容已更新、但卡片列表「更新时间」停在旧值。

**根因**: `_deploy_to_artifact` 直接写 `Artifacts/zhuzhao-jiuyin-daily/index.html`（绕过 `mcp__cowork__update_artifact`），渲染读文件本身故内容照常更新，但 manifest 的 `updatedAt` 不刷新（函数 docstring 自陈）。另注：Cowork「Claude's workspace」= `~/Documents/Claude` 的显示名，manifest path 与脚本写入 path 是同一物理位置。

**解法**: 改完出报后手动调 `mcp__cowork__update_artifact(id=zhuzhao-jiuyin-daily, html_path=AI4ME 正式产物)` 刷新 manifest。

**预防**: Doctor 偏好「每次改完 Artifact 都更新」——出正式报后固定补一步 update_artifact。根治需让脚本改走 update_artifact（另立改动）。

**⚠️ 更正待复核（2026-07-10 · CC）**: 本条原「另注」称 Cowork「Claude's workspace」＝ `~/Documents/Claude` 显示名、manifest path 与脚本写入 path 是**同一物理位置**——今日观察**与此冲突**：同一时刻读两处内容分叉——`~/Documents/Claude/Artifacts/…/index.html`（生成器 `_deploy_to_artifact` 目标）已是新口径「排位 1/5」，而 `~/Claude's workspace/Artifacts/…/index.html`（Cowork manifest 读取路径，`list_artifacts` 返回值）仍旧口径「容量满载」。同刻两文件内容不同 ⇒ 大概率**非同一物理文件**，「同一物理位置」论断存疑。若属实，则本坑不止「时间戳不刷新」，而是**内容根本不同步**（量级更重）：跑完生成器后必须手动 `update_artifact(html_path=生成器部署产物)` 才能把新内容搬到 Cowork 读取的那份。**待复核**：下次把 `~/Claude's workspace` 挂进来，比对两路径 inode/内容确证是否两处物理位置；确证后据实改写本条定性 + 评估根治（让 `ZZJY_ARTIFACT_ROOT` 直指 Cowork 读取目录，一步到位免手动推）。

---

## G024 — `/tmp/dbroot` 跨会话残留、属主不同致 Permission denied

**日期**: 2026-07-08 | **发现人**: 九儿（课件入库定时任务·同日二次触发） | **状态**: ✅ 已解决（workaround）

**触发场景**: 沙箱内按惯例 `mkdir -p /tmp/dbroot/烛照九阴 && cp $REAL_DB /tmp/dbroot/...`，cp 报 `Permission denied`。

**根因**: `/tmp` 跨沙箱会话持久，但每个会话的 uid 不同。同日早前会话创建的 `/tmp/dbroot` 属主是那个会话的用户（本会话视角显示 `nobody`），目录权限 755，本会话无写权。mkdir -p 对已存在目录静默成功，掩盖了不可写的事实。

**解法**: 副本根改用 `$HOME/dbroot`（每会话独立 HOME，必可写）：`export ZZJY_DATABASE_ROOT=$HOME/dbroot`。config.py 只认环境变量，路径任意，脚本零改动。Raw-Recap / 渊图等只读源照旧软链指回挂载盘（同 G021）。

**预防**: 定时任务写库前勿盲信 `/tmp/dbroot` 可写；统一改用 `$HOME/dbroot` 作副本根即可根除（G-X33 铁律的"/tmp 副本"本质是"本地盘副本"，不必拘泥 /tmp 字面）。

---

## G025 — data_day 跟②烛照四表线、领先①公共行情线一天 → 涨跌家数当天缺「待回填」

**日期**: 2026-07-09 | **发现人**: CC（Doctor 报涨跌家数待回填） | **状态**: ✅ 已解决（workaround·手动补①）

**触发场景**: 日报按 data_day=07-08 出，但「涨跌家数比」显示「待回填 / stock_daily 当日缺数」。

**根因**: `data_day = theme_etf_daily 最新交易日`（②烛照四表线，烛阴 16:00 任务·按**当日收盘**入库），而涨跌家数从 `stock_daily`（①公共行情线，句芒 `market-data-daily-update`·SKILL 设计只**更到「前一交易日」**）算。两条线口径差一天：②到 07-08、①到 07-07，data_day 跟②走就领先①一天，个股全量宽度当天必缺。**非 bug，是两任务时序口径不同**（个股全量日线当天收盘后才出、次日 06:15 才补；ETF/成交额当天可得）。

**解法**: 现在（收盘后、Tushare 数据齐）手动触发一次①任务补当日 stock_daily/daily_market/north_flow + aggregate_derived 派生 → 重出日报，涨跌家数落地。本次排即时任务 `market-data-backfill-0708` 让句芒补。

**预防**: ①线设计到「前一交易日」是既定行为，别当故障；当天出报个股宽度天然滞后 ETF 一天，缺数「待回填」是诚实标注。根治需统一 data_day 口径（以①为准 / 缺个股宽度时回退一日），属另立改动。CC 不代跑句芒取数（Tushare 下载硬约束 + 职责分工），改排即时任务让句芒补。

**根因辨析（2026-07-09 补·别再走弯路）**: 这是**数据可得时点的物理约束**，不是排序问题——当日全市场涨跌家数在 07:00 出报时物理上还不存在（Tushare 全市场量价要等 A股收盘后晚间才出）。去年已把①从 08:00 提前到 06:15 试图修，**没用也不可能有用**。别再去调 cron 顺序。

**落地补充（2026-07-09·渲染层最小版）**: 已实现「缺个股宽度时回退一日」——涨跌家数取数改 `MAX(trade_date)<=data_day` 回退最新可得日 + 记 `ud_vintage/ud_stale`；渲染 T-1 时标「T-1·昨日宽度（截至 X，当日待收盘）」角标，连 T-1 都无才「待回填」。抄成交额栏(L280-284)现成 vintage 范式。手动补①仍是拿当日真宽度的路径，但早报缺当日时已诚实展示 T-1 而非空显待回填。真需求（诚实标注）缩为单文件<10处、撤了 PRD。

## G026 — stock_tracking 系全量重建池，派生回填「只增不减」守门会误判其自然缩水

**日期**: 2026-07-14 | **发现人**: 九儿（烛阴·定时班） | **状态**: ✅ 已解决（本班按可逆优先保留原库·未放回）

**触发场景**: 定时行情班派生回填后，`populate_signal_targets.py` 重建 `recap.stock_tracking` 池，行数由 2998 → 2852。SKILL 5d「recap 关键表放回前只增不减校验」把这 5% 缩水判成潜在数损。

**根因**: stock_tracking **不是 append-only 表，是每次 populate 全量重建的标的池**（去重「一股一日一行·own 优先」）。其行数随当日活跃信号 / dim4 解析情况日间自然波动——本班缩水的直接诱因还叠了个小坑：首跑 populate 时 /tmp 缺渊图 KG（见 G020），dim4 仅 0 解析；补 KG 后重跑正确解析 33 只 dim4，去重后 own 池相应变化。所以 2852 才是**当日正确完整重建**，2998 是早前缺 KG 的旧值。

**解法（本班）**: 因实质派生表（emotion_cycle/yuantu_buy_signals/industry_signals/fx_cnh 全 delta=0，真库 09:04 已今日完整态）无变化，唯一 delta 是 stock_tracking rebuild churn，按可逆优先**保留原 recap.db、不放回** /tmp 缩水副本，日报读真库、数据完整。

**预防 / 待改（提案·Doctor 2026-07-14 批方向）**: SKILL 5d 的「只增不减」守门对 append-only 表（emotion_cycle 等）适用，但对 **stock_tracking 这类全量重建池不适用**——应改用「非空 + 行数落在合理区间（如 ≥ 前次 ×0.7）」校验，避免把正常 rebuild churn 误判成数损而阻断放回。具体 SKILL 措辞改动待 Doctor 在定时任务定义里落地（沙箱只读改不了）。另：设 `ZZJY_DATABASE_ROOT=/tmp` 跑 populate 前，务必先补渊图 KG 软链/快照（G020），否则 dim4 解析残缺、池会偏小。

---

## G027 — 生成器部署路径 ≠ Cowork artifact 注册表路径，磁盘覆盖不刷新视图

**日期**: 2026-07-15 | **发现人**: CC | **状态**: ✅ 已定位（临时解：部署后手动 update_artifact；根治待改 config）

**触发场景**: 改完 `gen_daily_report.py` 跑生成器，日志显示「🚀 已部署到 Cowork artifact」，但 Doctor 端 artifact「烛照九阴·复盘日报」没更新。

**根因**: 生成器 `config.ARTIFACT_ROOT` 部署目标是 `~/Documents/Claude/Artifacts/zhuzhao-jiuyin-daily/index.html`，而 **Cowork 注册表（`list_artifacts`）里该 artifact 的实际路径是 `~/Claude's workspace/Artifacts/zhuzhao-jiuyin-daily/index.html`——两处不同目录**。生成器只覆盖了前者的磁盘文件，Cowork 服务的是后者，故视图不刷新。直接写磁盘 ≠ 刷新注册表。

**解法（临时）**: 部署后把生成的 index.html 拷进工作区，调 `mcp__cowork__update_artifact(id="zhuzhao-jiuyin-daily", html_path=...)` 正式推进注册表才生效。ECharts 已内联（非 CDN），满足 update_artifact 自包含约束。

**预防 / 待改（提案）**: 长期应把 `config.ARTIFACT_ROOT` 指向 Cowork 注册表实际路径（`~/Claude's workspace/Artifacts`），或在生成器部署步骤末尾自动调 update_artifact，免每次手动。**注意 07:00 定时链**同样受此影响——定时跑只写了 Documents 侧磁盘、Cowork 视图不会自动刷新，须一并核。config 改动待 Doctor 拍板。

---

## G028 — Yahoo chart API 末根 bar＝盘中实时价，非收盘价；交易所开盘时段跑取数会把盘中价当日线入库

**日期**: 2026-07-16 | **发现人**: 九儿（烛阴·无人值守班） | **状态**: ✅ 已解决（当班剔除盘中条·班后自愈）

**触发场景**: 本班跑在美东 13:07（美股盘中）。美股锚改道 Yahoo chart API（G-X57 provenance 拦 stockanalysis 后的白名单路）与 fetch_intl_index/fetch_kr_stocks 同源取数，us_anchor_daily 与 intl_index_daily 的美股码 + JP_FUT 全部多出一根 `20260716` 的"日线"——实为**盘中实时快照**，非收盘价。若不处理即以盘中充收盘入库（违「At close」口径，且次日真收盘会 REPLACE 掉它掩盖问题）。

**根因**: Yahoo `/v8/finance/chart/…?interval=1d` 在该市场**开盘时段**返回的最后一根 bar 是当日进行中的实时 bar，与已收盘 bar 无字段区分。既有脚本历来跑在北京 16:00（美东凌晨、美股已收），从未暴露；本班时点异常（美西上午）才触发。

**解法（本班）**: 按各市场时钟判定「该 bar 所属 session 是否已收」：美股 5 码 + NKD=F（CME 17:00 ET 收）未收 → `DELETE` 当日盘中条（us_anchor 19 条 + intl_index 6 条），保留 0715 真实收盘（恰为 A 股 0716 隔夜锚，口径正确）；韩股当日已收、保留。次日班 `--from` 自愈补真收盘。

**预防 / 待改（提案）**: ① fetch_intl_index/fetch_kr_stocks/美股锚 yahoo 路统一加「末根时效守门」：用交易所时区（zoneinfo）判断当前是否盘中，盘中则丢弃当日 bar（或比对 meta.regularMarketTime 与收盘时刻）；② 定时班若在非常规时点补跑，放回前必查最新 bar 是否盘中。与 G-X58④（沙箱钟=美西）同族。

---

## G029 — 分组回测缺同期窗对照与截断率标注，会把「组只活在好月份+长窗幸存者」读成 alpha

**日期**: 2026-07-16 | **发现人**: CC（B4 悖论排查） | **状态**: ✅ 已定性（纪律条·后续分组回测执行）

**触发场景**: `docs/自主回测_20260706/` own 池分信息差等级统计，「未评级」组 10d 超额 +8.49 全场最高，被日报综合评估列为 B4 悖论（评分器疑似错杀新信息）。

**根因**: 三层伪象叠加，无一是信息差效应——① 身份：未评级=渊图/dim4 管线信号（gap_rater 只评 industry_signals，覆盖缺口非评分滞后）；② 期窗混杂：该组 2026-04 才出生，天然避开 202510/11 坑月，同期窗下 lvl 3（+10.90/胜率88.2%）反超；lvl 1 全期垫底同因（31% 样本落坑月，剔除后 +5.56）；③ 10d 窗截断构成漂移：85→40（截断率 53%），被截 45 条里 22 条是最差的 persistent，被截部分 ex3 中位 −3.48 vs 走完部分 +4.05——+8.49 是幸存者的数字。与股性回测「E1 波动尖峰幸存偏差」同族。

**解法**: 排查报告 `AI4ME/CC-B4未评级组悖论排查-20260716.md`（同期窗复算+同逻辑对照+截断拆解全套数字）。

**预防**: 分组回测三件套强制：① 各组样本期重叠检查（不重叠先切同期窗再比较）；② 长窗数字必标 n_win/n 截断率，<70% 加警示；③ 组间比较前核组的「身份」（分组变量是否与管线来源/时段结构性纠缠）。gap 数值等级证实无单调排序力（剔坑月后 1:+5.56/2:+4.22/3:+7.13），不作日报权重，仅作入选门槛（>=3 门槛与 lvl3 证据恰好对齐，保留）。

---

## G030 — ticker_resolver 种子源失联静默降级，populate 重灌把 2311 码打回 165、当日胜率腿残缺

**日期**: 2026-07-16 | **发现人**: CC（B4 排查副产品） | **状态**: ✅ 已解决（fail-loud 守卫 + warning 升级）

**触发场景**: 对比 predaily 备份：07-14/15 均 stock_code 非空 2311，07-16 骤降 165（幸存者全是自带码：渊图 beneficiaries_ts 49 + dim4 21 + 渊图 KG 命中 95）。当日日报胜率/追踪腿在 165/2952 残缺样本上计算。

**根因**: `stock_tracking` 每日由 populate DELETE+全量重灌，名→码靠 `ticker_resolver._index()`；其主种子 `tushare-cache/tushare.db`（stock_basic 5529 行）当次读取失败，异常仅 `logger.debug` **静默吞掉**，索引近乎空建 → 2787 行 unresolved 照样灌库。沙箱事后复测 resolver 正常 → 定时跑批时的环境性/竞态故障，会无声重演。

**解法**: ① `ticker_resolver.py`：种子源失败 debug→warning；索引 <1000 条时 warning。② `populate_signal_targets.py`：DELETE 前守卫——本次 resolve 率 < 0.6×现表率则 abort 保留现表、exit(3)，`--force` 逃生门。用**比率**不用绝对行数（G026：全量重建池行数自然波动）。

**预防**: 每日班次留意 populate exit(3) 报错即上游种子失联，先修种子再 --force；07-23 escalation 影子复核时顺带核 code 数是否回 ~2300 量级（自愈确认）。

---

## 统计

| 类别 | 总数 | 已改正 | 待处理 |
|------|------|--------|--------|
| 概念 | 1 | 1 | 0 |
| SQL | 3 | 3 | 0 |
| 数据质量 | 4 | 4 | 0 |
| NLP | 2 | 1 | 1 |
| 外部 API | 2 | 2 | 0 |
| 算法 | 2 | 2 | 0 |
| 路径/迁移 | 1 | 1 | 0 |
| 代码接口 | 1 | 0 | 1 |
| 自动化/流程 | 8 | 7 | 1 |
| 回测/数据覆盖 | 4 | 3 | 1 |
| 沙箱环境 | 3 | 2 | 1 |
| **总计** | **30** | **25** | **5** |


## [GOTCHA-20260718-001] stock_daily 历史段非全市场——跨期宽度/截面占比统计必锁固定宇宙
- **发现日期**: 2026-07-18(回调级别判别器建设中,CC 核出)
- **现象**: 跨期宽度统计(新低占比/涨跌比/≤−9%家数占比等)历史与当下数量级打架;新低占比一度被砍 10 倍。
- **根因**: `market_data.stock_daily` 2020–2026.06 仅 ~730–880 只研究票池,2026-06 末后才扩全市场 5500+。宇宙切换污染一切跨期截面占比;新进票无 60/252 日历史,rolling 类指标静默 NaN。
- **修复方式**: 锁固定研究宇宙(2020–2025 出现率 ≥90% 的 729 只,`AI4ME/回调级别判别/outputs/universe_fixed.json`),全窗一把尺;短窗票加 min_periods 门槛。
- **预防规则**: ①任何用 stock_daily 做跨期截面统计,先查当期宇宙规模;②float32 价格矩阵禁用绝对容差(1e-9 会因舍入漏计等值,用相对容差)。
- **状态**: ✅ 判别器侧已修 · 本条为下游预警(日报/回测同踩此库者自查)

## [GOTCHA-20260718-002] gateway 挂载上 sqlite 原地写必失败，且残留 hot journal 会把 cp 回去的新库**悄悄回滚**
- **发现日期**: 2026-07-18（句芒课件入库审核后执行 dim4 修正时踩中）
- **状态**: ✅ 已解决 ｜ **优先级**: 🔴 高（会静默丢失改动，且看不出报错）
- **触发场景**: 在沙箱内直接对挂载点 `mnt/Database/烛照九阴/recap.db` 开 sqlite 连接执行 `UPDATE`。
- **错误信息**: `sqlite3.OperationalError: disk I/O error`（发生在 commit/写页时，**建连与只读查询均正常**，极具迷惑性）。
- **真正的坑（第二段，比报错本身危险得多）**:
  1. 那次失败的原地写会在挂载点留下 `recap.db-journal`（hot journal）。
  2. 随后按正常套路 `/tmp` 改好再 `cp` 回真库——`md5sum` 当场比对**是一致的**，看起来完全成功。
  3. 但下一次任何进程打开 `recap.db`，sqlite 检测到 hot journal 会**自动执行回滚**，把刚 cp 进去的新库还原回旧内容。md5 悄悄变回原值，改动**全部蒸发且无任何报错**。
  4. 更麻烦的是 `rm` 该 journal 会被挂载拒绝：`Operation not permitted`。
- **解决方案**:
  1. **永远不要在挂载点直接对 sqlite 库执行写操作**。一律 `cp` 到 `/tmp` → 在 `/tmp` 改并 `commit` → 确认 `/tmp` 库 `integrity_check=ok` 且无 `-journal`/`-wal` → 再 `cp` 回真库。（九儿既有流程正确，本条是给"图省事想原地改"的后来者立的碑）
  2. 若已踩坑留下 journal：先 `mcp__cowork__allow_cowork_file_delete` 拿到删除权 → `rm` 掉 `recap.db-journal` → **然后才** `cp` 新库回去。顺序颠倒则前功尽弃。
  3. **放回后不要在挂载点直接开 sqlite 验证**（验证性打开同样可能触发写/建 journal）。改为 `cp` 到 `/tmp` 验证，挂载点只用 `md5sum` + `ls | grep journal` 核对。
- **预防措施**:
  - 判据口诀：**挂载点只读、/tmp 才写、放回前先清 journal、验证走副本**。
  - 每次放回后固定跑两条：`md5sum $R/recap.db`（应等于 /tmp 版）与 `ls $R/ | grep -E 'journal|wal'`（应为空）。**两条都过才算落库成功**，只看 md5 会被回滚骗过。
  - 写操作前先 `cp` 一份 `recap.db.bak_YYYYMMDD_{事由}`，可逆优先。

## [GOTCHA-20260720-001] /tmp/dbroot 被前次会话残留占住（属主 nobody）→ 副本根不可写；且副本根缺 Raw-Recap 时 scan 假报 0 课件
- **发现日期**: 2026-07-20（九儿课件入库定时班）
- **状态**: ✅ 已解决 ｜ **优先级**: 🟡 中
- **触发场景**: 定时任务按惯例 `mkdir -p /tmp/dbroot/烛照九阴` 后 cp recap.db。
- **错误信息**: `cp: cannot create regular file '/tmp/dbroot/烛照九阴/recap.db': Permission denied` —— /tmp 是 sticky 共享目录，前次会话（不同 uid，nobody:nogroup）建的 `/tmp/dbroot` 残留至今：当前会话对它无写权、也删不掉。
- **连带坑**: ① 换根后若只拷 recap.db，`dedup_kejian.py scan` 扫 `$ZZJY_DATABASE_ROOT/烛照九阴/Raw-Recap`——目录不存在时**假报「共 0 个课件」**（酷似"今日无新课件"，实为路径缺失，务必甄别）；② 沙箱无 sqlite3 CLI，校验改用 `python3 -c "import sqlite3; ..."`。
- **解决方案**: 副本根改 `/var/tmp/dbroot`（会话属主可写；任何本地非挂载目录均可），`export ZZJY_DATABASE_ROOT=/var/tmp/dbroot`；再 `ln -s $REAL/Raw-Recap /var/tmp/dbroot/烛照九阴/Raw-Recap`（Raw-Recap 只读，symlink 指挂载盘安全）。
- **预防措施**: 定时工序开头固定三步：① 副本根用 /var/tmp/dbroot（勿赖 /tmp）；② cp 库后 symlink Raw-Recap；③ scan 报 0 课件时先核 Raw-Recap 路径真实可达，再下「无新课件」结论。

## [GOTCHA-20260720-002] /tmp 遗留 package-lock.json 使 npm 认错项目根 → EACCES；npm 工作目录须避开 /tmp
- **发现日期**: 2026-07-20（九儿行情拉取与日报班 · Artifact echarts 安装步）
- **状态**: ✅ 已解决 ｜ **优先级**: 🟢 低
- **触发场景**: 按 SKILL 惯例 `cd /tmp && npm install echarts@5`（改在 /tmp/zz_run 子目录亦同）。
- **错误信息**: `EACCES: open '/tmp/package-lock.json'` —— npm 向上找项目根，撞到前次会话（nobody 属主）残留的 `/tmp/package-lock.json`，把 /tmp 当项目根且无写权。与 -001 同根：sticky /tmp 跨会话残留。
- **解决方案**: npm 工作目录放 `$HOME`（如 `~/zz_npm`），先 `npm init -y` 立本地 package.json 再装，向上探测即被截断。
- **预防措施**: 沙箱内一切 npm 操作不落 /tmp；固定 `mkdir -p ~/zz_npm && cd ~/zz_npm && npm init -y && npm install …`。

## [GOTCHA-20260720-003] Yahoo chart bars 全边缘陈旧（KR 双雄停 T-2）时，meta.regularMarketPrice/Time 仍新鲜——可作"已收盘终值"旁路
- **发现日期**: 2026-07-20（九儿行情拉取与日报班）
- **状态**: ✅ 已解决 ｜ **优先级**: 🟡 中
- **触发场景**: fetch_kr_stocks.py 收盘后 10h+ 取 005930.KS/000660.KS，timestamps 数组仍停 0716（周一 0720 bar 缺）；query1/query2 × range=15d/1mo/3mo × 重试共 12 次全陈旧（期间仅偶发命中一次新鲜边缘，不可复现）。
- **解决方案**: 同一响应的 `meta.regularMarketTime`（=当日 15:30 KST 收盘戳，证明该价为**终值**非盘中）+ `meta.regularMarketPrice`，query1/query2 双主机交叉一致 → 按脚本同 schema/写库路径落 0720 行，pct 由库内上一交易日真实前收算得。0717 韩市无 bar＝当日无交易，如实留空不编。
- **预防措施**: ① bars 陈旧 ≠ 数据不可得，先查 meta 再判缺；② 用 meta 兜底必须核 regularMarketTime 属**已收盘**时刻（防盘中价冒充收盘）；③ 反面纪律同班例证：美东盘中绝不跑美股腿（fetch_intl_index 无未收盘 bar 防护），停旧水位待下班自愈。

## [GOTCHA-20260721-001] /dev/shm 不跨 bash 调用持久（每次调用独立命名空间）→ 绝不可当库副本根；$HOME 又触 connect_write 护栏——副本根只剩 /var/tmp（/tmp 用户子目录等价）
- **发现日期**: 2026-07-21（九儿课件入库补班 · 260720 课件）
- **状态**: ✅ 已解决 ｜ **优先级**: 🟡 中
- **触发场景**: 绕 -001 的 /tmp/dbroot 残留时试了两条路，各撞一坑：① 副本放 `/dev/shm/dbroot`——同一 bash 调用内 cp/integrity/scan 全正常，**下一次调用文件即消失**（`unable to open database file`）；Cowork 沙箱 /dev/shm 是 per-call tmpfs，不跨调用持久，且无任何报错提示"会消失"。② 改放 `$HOME/dbroot`（本地 ext4，看似理想）——路径含 `/sessions/` 子串，触发 config.connect_write 护栏（G019）硬拒绝写，护栏按子串判挂载盘、无法区分 $HOME 实为本地盘。
- **错误信息**: ① `sqlite3.OperationalError: unable to open database file`（第二次调用时）；② `RuntimeError: [connect_write] 拒绝直写挂载盘真盘`。
- **解决方案**: 副本根用会话属主可写、跨调用持久、路径不含 /sessions|/mnt 的本地目录：`/var/tmp/dbroot`（-001 标准解）或 /tmp 下新建用户子目录（本班 `/tmp/dbroot_juer`，等价）。symlink Raw-Recap 照 -001。
- **预防措施**: ① 副本根三条件缺一不可：**可写 + 跨调用持久 + 路径干净**——/dev/shm 违②、$HOME 违③、/tmp/dbroot 违①；② 后续班次统一照 -001 用 `/var/tmp/dbroot`，勿再各起新名；③ 任何"上一步刚建的文件突然不见"，先怀疑 per-call 命名空间（/dev/shm、部分 /run），换持久盘复测再排查别的。

## [GOTCHA-20260721-002] web_fetch 新增 provenance 限制：程序拼接的 URL 一律被拦 → stockanalysis 逐票路失效，us_anchor 切 Yahoo chart 备路
**状态**: ✅ 已解决
**优先级**: 🔴 高
**触发场景**: 2026-07-21 二班补拉 us_anchor，逐票 `web_fetch stockanalysis.com/stocks/{t}/`（19 只并发 5 只起手）
**错误信息**: `URL not in provenance set. web_fetch can only retrieve URLs that appeared in a user message, a prior web_fetch result, or a WebSearch result.`
**解决方案**: SKILL 模板里的占位符 URL 不算 verbatim，凡是 agent 自行拼出的 URL 都过不了 provenance 门。当班切 **Yahoo chart API 白名单路**：直接 `from fetch_intl_index import fetch_yf` 对 19 只跑（period1/period2 真区间 + G014 回看窗算 pct），只入 `trade_date == T_anchor` 的行，`source` 如实标 `yahoo-chart`（**不得**冒标 stockanalysis——数据随源走）。实测 19/19 全新鲜含冷门票 ALM/RKLB，比 stockanalysis CDN 更稳。
**预防措施**: ① us_anchor 日更主路建议就地改为 Yahoo chart（与 intl_index/kr_stocks 同源归一，SKILL ②a 待 Doctor 拍板改文案）；② 期货类 symbol（NKD=F/BZ=F）在亚洲时段会吐**当日进行中 bar**，入库后须 `DELETE trade_date > T_anchor`（本班清 JP_FUT/BRENT 各 1 根 0721 盘中 bar）；③ 若真需 web_fetch 某页，先 WebSearch 让目标 URL 进 provenance set 再 fetch。

## [GOTCHA-20260723-001] 跨项目脚本 adjustment_grade.py 的 `_mnt()` 硬走 `../×6`，沙箱平铺挂载下溢出到 `/` → 日报「级别读数」占位（grade_section 两分支皆败）
**状态**: ✅ 已解决
**优先级**: 🟡 中
**触发场景**: 九儿定时班（zhuzhao-market-fetch-daily-report，平铺挂载 Database/烛照九阴/AI4ME）出的日报「回调级别读数」栏显示"级别读数不可用"。`gen_daily_report.grade_section()` subprocess 调 `剑酒青丘/infrastructure/取数工具/adjustment_grade.py --update --json` 与 `--json` 两分支均败降级占位；app.log 无痕（stderr 的 `[grade_section]` 行进的是定时会话 stderr，不落 app.log）。手动/全树沙箱班正常＝易误判为一次性瞬态。
**错误信息**: 无显式栈——`adjustment_grade._mnt()` 用 `HERE + ../×6` 回推「Documents 等价根」。平铺挂载下 `剑酒青丘` 直挂 `/mnt/剑酒青丘`，`../×6` 溢出经 `/mnt`→`/sessions`→`/`，于是 `_mnt("Database",".env")`＝`/Database/.env`、`MKT`＝`/Database/Market-Data/market_data.db` 全落空 → --update 无 token、--json 无库，两败。姊妹脚本 market_health.py 未坑，因 SKILL 显式传 `MARKET_DATA_DIR` 绕开该逻辑；adjustment_grade 无此逃生口。
**解决方案**: 2026-07-23 改 `adjustment_grade.py`：`_mnt` 前置 `_find_root()`——① `ZZJY_MNT_ROOT` env 兜底优先（`<root>/Database` 存在才采）；② 自愈：从本文件逐级上找「含 Database 子目录的最近祖先」作根；③ 回退原 `../×6`。宿主机 Documents 本含 Database → 检测结果与旧逻辑**完全一致、正路零改动**；平铺沙箱落到 `/mnt`（Database/AI4ME 皆在其下）→ `--json` 只读分支命中真库、级别读数恢复。三布局隔离测试 + 真脚本 `--json`（L3·confirm True）均过。
**预防措施**: ① 跨项目脚本凡靠相对层级回推根目录的，一律换「探测含标志子目录的祖先」而非硬编码 `../×N`（G-X45 平铺挂载路径坑同族，跨项目复发）；② 定时班的静默降级要靠**产物**（占位/缺值）与 agent run log 反查，别指望 app.log；③ 修复生效点＝下一次工作日 10:00 定时班（本条不阻塞交付、日报其余内容完整）。
