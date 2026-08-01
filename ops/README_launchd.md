# ops/ · 本机 launchd 行情落库（两个 job 的分工）

> 本机时区 **America/Los_Angeles**（PDT/PST）。下表钟点一律指**本机墙钟**。
> ET 与 PT 同步换夏令时，故墙钟对美股收盘的相对位置全年稳定，换季无需调整。

## 为什么写库必须在 Mac 原生跑

Cowork 沙箱经 FUSE 直写挂载盘真盘是 **GOTCHAS G019** 明令禁止的——recap.db 曾被这样写坏，
且 `quick_check` 漏报（坏了看不出来）。`config.connect_write()` 就是为此立的中央护栏，
路径含 `/sessions/` 或 `/mnt/` 一律硬拒绝。Mac 原生路径 `/Users/...` 护栏放行，写入即 durable。

顶层程序一律用 `python3.13` 而非 `/bin/bash`：launchd 执行的顶层程序即 TCC（完全磁盘访问）
的授权主体。用 bash 跑则主体是未授 FDA 的 `/bin/bash`，写 `~/Documents` 会被拦；
用已授 FDA 的 python3.13 直接跑，整条链（含它 spawn 的 python 子进程）都被覆盖。
**两个 job 都别改回 .sh。**

## 两个 job

| Label | 钟点（本地） | 换算美东 | 入口 | 管什么 |
|---|---|---|---|---|
| `com.zhuzhao.marketdata` | 周一~五 **02:30** | 05:30 ET（**开盘前**） | `mac_daily_marketdata.py` | A 股五表 + 句芒派生 + intl_index/kr_stocks 隔夜读数 |
| `com.zhuzhao.usclose` | 周一~五 **14:00** | 17:00 ET（**收盘后 1h**） | `mac_us_close_backfill.py` | 补 `us_anchor_daily` + `intl_index_daily` 美股腿的**当日收盘价** |

**为什么要两个**：主班排在美股开盘前，它取到的美股腿天然是隔夜/盘中读数，
`us_anchor_daily` 因此结构性晚一天。补数班排在收盘后，专门消除这一天滞后。
顺序是 补数班 D 14:00 → 主班 D+1 02:30。

**注意**：`fetch_us_anchor.py` **不在主班里**，`us_anchor_daily` 的唯一主人就是补数班。
补数班停摆 = 美股锚断更（2026-08-01 之前一直如此）。

## 落地状态与日志

| | 主班 | 补数班 |
|---|---|---|
| 脚本日志 | `logs/mac_marketdata_YYYYMMDD.log` | `logs/mac_usclose_YYYYMMDD.log` |
| launchd 兜底 | `logs/launchd_marketdata.{out,err}` | `logs/launchd_usclose.{out,err}` |
| 状态文件 | `ops/.last_run_status` | `ops/.last_run_status_usclose` |

状态文件内容为 `OK <时间戳>` 或 `FAIL <时间戳>`，一行，供快速检查/看板消费。

## 安装 / 验证 / 卸载

```bash
# 安装（软链，改仓内文件即生效，不必重装）
ln -sf ~/Documents/Claude/Projects/Financial/烛照九阴/ops/com.zhuzhao.usclose.plist \
       ~/Library/LaunchAgents/com.zhuzhao.usclose.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.zhuzhao.usclose.plist

# 立刻跑一次验证（不等日历触发）
launchctl kickstart -k gui/$(id -u)/com.zhuzhao.usclose
tail -f ~/Documents/Claude/Projects/Financial/烛照九阴/logs/mac_usclose_$(date +%Y%m%d).log

# 查状态 / 下次触发
launchctl print gui/$(id -u)/com.zhuzhao.usclose | head -30

# 卸载
launchctl bootout gui/$(id -u)/com.zhuzhao.usclose
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
