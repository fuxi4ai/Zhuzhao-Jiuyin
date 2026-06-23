# 烛照九阴 · PRD（现状版）

> **版本**: v4（现状·迁移后）｜ **更新**: 2026-06-24
> **数据库**: `Database/烛照九阴/recap.db`（SQLite·31 表·~4.1 MB）｜路径单一真源 = 项目根 `config.py`（**无 MySQL**）
> **历史**: 迁移前 v3.1 旧 PRD 已归档 `PRD_v3.1_pre-migration.md`（MySQL/db 软链/daily_input 等均已不成立）。

---

## 一 · 定位

烛照九阴 = 历史复盘 + 量化指标 + 行情回测的 **A股情绪周期决策工具**（数灵烛阴/九儿的复盘线）。把小鲍复盘课件 + 公共行情 + 渊图产业逻辑，融成「四维复盘 + 情绪周期 + 兑现回测」，每日产出**暖色日报**。

## 二 · 数据与路径（单一真源）

- **库**: `Database/烛照九阴/recap.db`（31 表）。路径一律走项目根 `config.py`（`python3 config.py` 自检），**不用 MySQL、不用 Path.home()**。
- **课件源**: `Database/烛照九阴/Raw-Recap/`（小鲍复盘课件·只读第三方语料·215 份）。
- **公共行情**: `Database/Market-Data/market_data.db`（句芒维护·只读；sector_daily 已退役，高低切改 `theme_etf_daily` 主线ETF）。
- **渊图先验**: `行业研究/mapping/latest.json`（只读契约）。

## 三 · 核心管线（每日）

| 步 | 内容 | 落表 | 触发 |
|---|---|---|---|
| 课件入库 | 小鲍课件四维抽取（市场数据/行业主线/产业逻辑/情绪/仓位）；**去重由 `tools/dedup_kejian.py` 唯一管**（filename+md5·scan 列待处理/record 标已处理/prune 清陈旧） | dim1/dim2/industry_signals/recap_daily/dim3/dim4 | SKILL `recap-kejian-daily-ingest`（06:00） |
| 行情/派生 | 句芒刷公共行情 → 四表 | Market-Data | `market-data-daily-update`（06:15） |
| 情绪引擎 | emotion_cycle 评分/季节/周期 | emotion_cycle | 随日报链（emotion_engine_v2 --apply） |
| 渊图入库+兑现 | 渊图买入信号 / info_gap 分 / 兑现状态机 / 标的池 | yuantu_buy_signals / industry_signals(gap) / stock_tracking | 随 07:00 日报链（closure auto-apply + 回滚锚） |
| 日报 | 暖色日报 v2（gen_daily_report.py） | `AI4ME/烛照九阴-outputs/` | `zhuzhao-market-fetch-daily-report`（07:00） |

## 四 · 关键表（现状行数·2026-06-24 实测）

recap_daily 163 · dim1 132 · dim2 167 · dim2p 32 · dim3 164 · dim4_trade 179 · dim4_stock 248 · emotion_cycle **365** · industry_signals 1299 · yuantu_buy_signals 102 · **stock_tracking 2527** · processed_kejian 215 · tushare_limit 6000。

## 五 · 现役工具链（均经 config.py 取路径）

- 查询/录入: `tools/recap_cli.py`(CLI)·`recap_db.py`(keystone)·`recap_import.py`
- 课件: `dedup_kejian.py`(去重·**processed_kejian 之主**)·`xiaobao_extractor.py`(正则提取)
- 情绪/周期: `emotion_engine_v2.py`·`cycle_quant.py`·`cycle_compare.py`
- 渊图消费: `yuantu_client.py`·`ticker_resolver.py`·`sync_buy_signals.py`·`logic_discovery.py`
- 标的级回测: `migrate_stock_tracking_backtest.py`·`populate_signal_targets.py`·`signal_winrate_backtest.py`（详 PRD `brain/logs/checkpoints/2026-06-15_标的级胜率回测_PRD.md`）

## 六 · 铁律 / 验收口径

- **红涨绿跌**（中式）: `--red:#a94e3f`/`--grn:#2f7d63`。
- **标的级两池隔离**: 自有池(industry_signals + yuantu_buy_signals) vs dim4 池(小鲍逐股)，**绝不并入同一胜率分母**；命中=next3d 超额(−沪深300·pct_chg)>0。
- **只增不减 / 不造假**: 缺标缺、不编造；写库防空壳。
- **ETF 未复权**: 日收益一律用 `pct_chg`，禁 close 环比（GOTCHA 2026-06-10）。
- **沙箱不写 db / 不跑 git 写**: 写 recap.db 在能写库环境跑；git 命令贴 Doctor 终端。

## 七 · 待办

- [ ] **标的级回测落地**: 工具齐，待跑 `populate_signal_targets → signal_winrate_backtest`（写 recap.db·Mac），跑后 stock_tracking 收益列(现 0/2527)落地，出分池胜率。
- [ ] STATUS.md 见 `STATUS.md`（数据库状态实测快照）。
