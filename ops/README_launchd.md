# ops/ · 本机 launchd 行情落库（三个 job 的分工）

> 本机时区 **America/Los_Angeles**（PDT/PST）。下表钟点一律指**本机墙钟**。
> ET 与 PT 同步换夏令时，故墙钟对美股收盘的相对位置全年稳定，换季无需调整。

## 为什么写库必须在 Mac 原生跑

Cowork 沙箱经 FUSE 直写挂载盘真盘是 **GOTCHAS G019** 明令禁止的——recap.db 曾被这样写坏，
且 `quick_check` 漏报（坏了看不出来）。`config.connect_write()` 就是为此立的中央护栏，
路径含 `/sessions/` 或 `/mnt/` 一律硬拒绝。Mac 原生路径 `/Users/...` 护栏放行，写入即 durable。

顶层程序一律用 `python3.13` 而非 `/bin/bash`：launchd 执行的顶层程序即 TCC（完全磁盘访问）
的授权主体。用 bash 跑则主体是未授 FDA 的 `/bin/bash`，写 `~/Documents` 会被拦；
用已授 FDA 的 python3.13 直接跑，整条链（含它 spawn 的 python 子进程）都被覆盖。
**三个 job 都别改回 .sh。**

## 三个 job

| Label | 钟点（本地） | 换算美东 | 入口 | 管什么 |
|---|---|---|---|---|
| `com.zhuzhao.marketdata` | 周一~五 **02:30** | 05:30 ET（**开盘前**） | `mac_daily_marketdata.py` | A 股五表 + 句芒派生 + intl_index/kr_stocks 隔夜读数 |
| `com.zhuzhao.usclose` | 周一~五 **14:00** | 17:00 ET（**收盘后 1h**） | `mac_us_close_backfill.py` | 补 `us_anchor_daily` + `intl_index_daily` 美股腿的**当日收盘价** |
| `com.zhuzhao.ipo-rolling` | 每日 **09:00** | —（北京日窗口，与时区无关） | `scripts/fetch_ipo_rolling.py` | IPO 滚动窗口 [D-29, D]（北京日）采集 + 覆盖证明，直写两表（不整库放回） |

**为什么要两个**：主班排在美股开盘前，它取到的美股腿天然是隔夜/盘中读数，
`us_anchor_daily` 因此结构性晚一天。补数班排在收盘后，专门消除这一天滞后。
顺序是 补数班 D 14:00 → 主班 D+1 02:30。

**第三班 ipo-rolling 为什么独立**（2026-09-13 VV 复核定案）：IPO 消费合同要求
「单条覆盖完整包含 [D-29, D] 窗口」，沙箱班整库放回会丢他人写入（VV 实测证伪），
分段续采的窄条又永远满足不了合同——故走 Mac 原生 launchd 滚动采集，每日 09:00 PT
覆盖周末（北京日的 D 每天都在前移，无交易日停跑之说），漏跑一天次日补扫仍覆盖。

**注意**：`fetch_us_anchor.py` **不在主班里**，`us_anchor_daily` 的唯一主人就是补数班。
补数班停摆 = 美股锚断更（2026-08-01 之前一直如此）。

**看门狗班（不在 launchd 里）**：Cowork 定时任务 `us-close-backfill` 于 **14:30 PT**
（补数班之后 30 分）跑**只读看门狗**——核对两表水位与新鲜度、出简报给 Doctor，
绝不写库。它是"告警直达人眼"的一层，launchd 自身的 ❌ 只落在日志里没人看。
两边的陈旧阈值必须一致，见下方铁律 7。

## 落地状态与日志

| | 主班 | 补数班 | IPO 班 |
|---|---|---|---|
| 脚本日志 | `logs/mac_marketdata_YYYYMMDD.log` | `logs/mac_usclose_YYYYMMDD.log` | （脚本内自管） |
| launchd 兜底 | `~/Library/Logs/com.zhuzhao.marketdata-{stdout,stderr}.log` | `~/Library/Logs/com.zhuzhao.usclose-{stdout,stderr}.log` | `/tmp/ipo_rolling.{log,err}`（plist StandardOut/ErrorPath） |

> **⚠️ stdio 必须在 TCC 保护区之外（2026-09-18 迁 · GOTCHA `brain/剑酒青丘/GOTCHAS.md` NOTE-20260918-001）**
> 旧址 `logs/launchd_{marketdata,usclose}.{out,err}` 落在 `~/Documents`（TCC 区）内。launchd 在 spawn 前**自己**去 open 这两个文件，被 TCC/macl 拒 → **进程根本没被创建**，零 stdout 零 stderr、只留 `last exit code = 78: EX_CONFIG`，整族 agent 静默停摆（触发点＝系统重启 TCC 重评）。
> 实绩：本班 09-17/09-18 两次 02:30 排期未点火（`.last_run_status` 停 09-16 02:31）；usclose 缺 09-17 14:00 一次。
> **bootout/bootstrap 单独治不好这个病——计数器归零不等于修复**（`runs = 0 / never exited` 只是新载入）。
> 修复＝把带 macl 的日志件改名留档让 launchd 重建；**治本＝ stdio 迁出保护区**（`~/Library/Logs/`，系统既有目录，launchd 不会替我们建目录）。IPO 班的 `/tmp` 亦在区外，但重启即失、不留史。
| 状态文件 | `ops/.last_run_status` | `ops/.last_run_status_usclose` | `ipo_coverage` 表内覆盖证明（scan_start/scan_end/events_hash） |

状态文件内容为 `OK <时间戳>` 或 `FAIL <时间戳>`，一行，供快速检查/看板消费。
IPO 班不设状态文件——其覆盖证明落在数据库 `ipo_coverage` 表，比文件更接近消费端。

## 安装 / 验证 / 卸载

```bash
# 安装（实体拷贝，与 marketdata 同模式；软链曾致 usclose 失载停摆——2026-08-12。
# 代价：改仓内 plist 后需重新 cp + bootstrap 才生效）
cp ~/Documents/Claude/Projects/Financial/烛照九阴/ops/com.zhuzhao.usclose.plist \
   ~/Library/LaunchAgents/com.zhuzhao.usclose.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.zhuzhao.usclose.plist

# 立刻跑一次验证（不等日历触发）
launchctl kickstart -k gui/$(id -u)/com.zhuzhao.usclose
tail -f ~/Documents/Claude/Projects/Financial/烛照九阴/logs/mac_usclose_$(date +%Y%m%d).log

# 查状态 / 下次触发
launchctl print gui/$(id -u)/com.zhuzhao.usclose | head -30

# 卸载
launchctl bootout gui/$(id -u)/com.zhuzhao.usclose

# IPO 班（2026-09-12 部署 · 源 = ops/com.zhuzhao.ipo-rolling.plist，同为实体拷贝模式）
cp ~/Documents/Claude/Projects/Financial/烛照九阴/ops/com.zhuzhao.ipo-rolling.plist \
   ~/Library/LaunchAgents/com.zhuzhao.ipo-rolling.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.zhuzhao.ipo-rolling.plist
launchctl kickstart -k gui/$(id -u)/com.zhuzhao.ipo-rolling
launchctl print gui/$(id -u)/com.zhuzhao.ipo-rolling | head -30
launchctl bootout gui/$(id -u)/com.zhuzhao.ipo-rolling   # 卸载
```

手动直跑（绕过 launchd，排障用）：

```bash
cd ~/Documents/Claude/Projects/Financial/烛照九阴
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13 ops/mac_us_close_backfill.py
```

## 补数班的几条铁律（改它之前先读）

1. **绝不编数**。取数脚本自带盘中守卫（纯数据驱动、不看系统钟）。守卫判定末根是盘中快照就
   丢弃 → 本班少写一天，下一班 `--from=max+1` 自愈。**宁可少一天，不可假一天。**
   推论：跑早了、漏跑了、合着盖子跑不成，都不会产生坏数据，只会晚一轮补上。
2. 编排器**只调现成脚本 + 只读核对**，不改任何取数脚本、不改任何判定逻辑。
3. **失败可见**：任一步非零退出 → 日志标 ❌ 且退出码非 0，绝不静默重试到超时。
4. 只写 `us_anchor_daily` / `intl_index_daily`，不碰 recap.db、不生成日报。
5. 验收基准 **19 票 / 5 条美股腿**（`NASDAQ SPCX NVDA AVGO LITE`）硬编码在
   `mac_us_close_backfill.py` 顶部常量。**改票池时必须同步改这里**，否则正常扩票会被误报成 ❌。
   硬编码是刻意的——代价是扩票要记得改，好处是少一票一定看得见。
6. `US10Y` / `BRENT` / `JP_FUT` 属 **macro 读数语义腿**，按设计不开盘中守卫（服务日报 F5 外部
   紧缩因子，越新鲜越好），其 `close` 本就可能是取数时点快照而非收盘价——**这是刻意分层、
   不是缺陷**，见 GOTCHAS G033。本班只检查它们在不在，不核收盘，也不"修正"它们。
   ⚠ 下游若需美债/商品**真收盘**（事件归因、回测），一律另取官方源（H.15 / FRED DGS10 /
   官方结算价），**勿把 `intl_index_daily` 的 macro 腿 close 当收盘价用**。
7. **陈旧告警阈值 `STALE_WARN_DAYS=3` / `STALE_FAIL_DAYS=5`**（自然日）写在
   `mac_us_close_backfill.py` 顶部常量，Cowork 只读看门狗 SKILL 里另有一份**同值副本**——
   **改一处必须同步另一处**，否则两班口径打架。
   这条为什么存在：取数脚本**一票都没取到时仍然退出码 0**（写 0 行也算正常完成），
   只查"最新日票数够不够"的话，周末空跑与工作日数据源整体中断的日志一模一样，
   一次彻底中断会被静默上报成成功。2026-08-01 首次实跑即暴露此洞。
   允许在此处看系统钟不违背铁律 1——铁律 1 管的是**交易日锚点判定**（不许用系统钟推断
   "今天该写哪一天"，那会导致编数）；陈旧告警只是看门狗，不参与任何入库判定。

## 历史

- **2026-07-22** 主班 `com.zhuzhao.marketdata` 落地。根治沙箱经 FUSE 整库写回丢大表
  (`stock_daily`) 导致日报隔天退回。
- **2026-08-01** 补数班 `com.zhuzhao.usclose` 落地。此前补数跑在 Cowork 沙箱，
  两个取数脚本用裸 `sqlite3.connect(MARKET_DB)` 绕过了 `config.connect_write` 护栏，
  直奔挂载盘写；当日沙箱挂载收紧 unlink 权限，SQLite 提交时删不掉 rollback journal，
  报 `disk I/O error` 全线失败（残留 hot journal 一度令整库连只读都打不开）。
  迁本机原生后，护栏放行、写入 durable，且不必为此拆掉 G019 防线。
  同日 `mac_daily_marketdata.sh` 因与 `.py` 编排逻辑漂移（缺 guarantee_ratio 等）
  且 plist 只调 `.py`，改名 `_DEPRECATED_` 前缀弃用（未删）。
- **2026-08-12** 补数班停摆并恢复：launchd 报 service not found（job 未加载、软链仍在；
  失载机制为推断，同期 marketdata 实体文件存活）。重 bootstrap 复活，plist 改实体拷贝。
  另手动 `--from 2026-08-11` 回补当日缺口（6 锚票 ALM/GEV/LITE/MP/PLTR/RKLB + 美股腿
  LITE/SPCX）——编排器 max+1 起点不回头补部分缺失日，此洞未改代码、靠人工盯。
- **2026-09-12/13** IPO 班 `com.zhuzhao.ipo-rolling` 上线（VV 九轮验收 · Doctor 部署）：
  覆盖证明 + 滚动窗口 [D-29, D] 北京日 + python3.13 顶层入口（TCC/FDA 授权主体）。
  plist 由 VV 在复验证据目录生成、Doctor 直接部署——**装机后源未同步落 ops/**
  致巡检报「有装机无源」（NOTE-20260914-001），09-14 已归位并补本表登记。
