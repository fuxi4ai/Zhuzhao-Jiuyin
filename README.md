# 🕯️ 烛照九阴

> 基于历史复盘数据 + 量化指标 + 行情回测的 **A 股情绪周期决策工具**
>
> **命名由来**: 天哥于 2026-05-10 正式命名，与九儿（烛阴）名字呼应
> 对标：白泽观星、白泽大宗 / 龙鱼五力

---

## 🧭 项目定位（数灵转移后，2026-06-04 收官）

烛照九阴是**烛阴（九儿）的复盘工作项目**：脚本/工具住在本项目，数据落在公共数据层，记忆/性格在 brain。三者分工：

| 层 | 位置 | 谁的 |
|----|------|------|
| **工作脚本/工具** | 本项目 `tools/` `scripts/` `news/` | 烛阴（本项目） |
| **数据** | `Database/烛照九阴/`（recap.db；news.db 财新试验已归档 archive/，2026-06-10）+ `Database/Market-Data/`（公共行情，只读） | 单一可信源 |
| **记忆/方法论/性格** | `brain/agents/烛阴/` | brain 记忆系统 |
| **产业逻辑（渊图）** | `Database/行业研究/` | CC 渊图正源，烛阴**只读引用** |

> ⚠️ 路径单一可信源：所有脚本经根目录 **`config.py`** 取数据库路径，**不得**再写死 `/home/admin/openclaw/...` 或项目内 `db/recap.db`。

---

## 📊 核心数据（实测 2026-06-06）

| 指标 | 值 |
|------|-----|
| 复盘主表 recap_daily | 152 条（2025-10-14 → 2026-06-03） |
| 情绪技术 dim3 | 153 条 |
| 量化情绪周期 cycle_quant | 103 条 |
| 产业信号 industry_signals | 1231 条（统一 P2×0.7，小鲍课件源） |
| 重点标的 dim4_stock_analysis | 182 条 |
| recap.db 总表数 | 29 |

## 四维度框架

| 维度 | 内容 |
|------|------|
| Dim1 · 外围定价 | 美股/港股/汇率/原油/掉期 |
| Dim2 · 行业主线 | 板块/产业链/供需/涨价逻辑（结论层以渊图为准） |
| Dim3 · 情绪技术 | 情绪周期/涨跌停/催化/政策 |
| Dim4 · 交易策略 | 预案/仓位/标的分析 |

## 快速开始

```bash
cd Claude/Projects/Financial/烛照九阴

# 0) 自检：确认 config 指向 Database/ 真库（全 ✅ 才继续）
python3 config.py

# 查询（CLI 12 命令）
python3 tools/recap_cli.py stats         # 统计概览
python3 tools/recap_cli.py emotion        # 情绪周期
python3 tools/recap_cli.py by-date 2026-06-03
python3 tools/recap_cli.py by-sector 光模块

# 快速录入
python3 tools/recap_import.py

# 课件提取（小鲍语料 → recap.db；产业逻辑交九儿）
python3 tools/xiaobao_extractor.py
```

## 文档导航

| 文档 | 说明 |
|------|------|
| [PRD.md](PRD.md) | 产品需求文档（架构/规划） |
| [INDEX.md](INDEX.md) | 项目索引（目录结构） |
| [STATUS.md](STATUS.md) | 数据库状态（实测填充率/Gap） |
| [GOTCHAS.md](GOTCHAS.md) | 错题本 |
| [外部资源对接.md](外部资源对接.md) | 外部数据源对接状态 |
| [_legacy/MANIFEST.md](_legacy/MANIFEST.md) | 退役脚本归档说明 |

> 方法论/置信度规则（渊图主从、小鲍 P2）以 `brain/agents/烛阴/` 为准，不在本项目重复维护。

---

*README.md · 2026-06-06 大修 · CC*
