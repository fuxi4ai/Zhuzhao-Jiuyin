# 归档说明 · 2026-07-30 批

> 本批共 **11 个 `.bak` 文件**，全部 `mv` 而来、**零删除**。
> 触发：Doctor 指派「审查并修复烛照九阴 · 清理 conch 标记的陈旧文件」（2026-07-31 北京 / 07-30 美西）。

## 两种来源，两套回滚方式

### A · conch archive 归档的 9 个（**平铺存放**）

由 `Projects/海螺姑娘/conch_engine.py archive --apply` 处理，**session_id `20260730T232432`**。

⚠ **conch 是平铺归档的**——不保留原目录结构，故 `risk_factors.json.bak_*` 虽原在 `config/`，现落在本目录根。**原路径不在文件名里，只在审计日志中**：

- 审计日志：`../../.conch_audit.log`（项目根）
- 精确回滚：`python3 ~/Documents/Claude/Projects/海螺姑娘/conch_engine.py rollback 20260730T232432`

| 归档后（本目录） | 原路径 |
|---|---|
| `gen_daily_report.py.bak_20260717-195826` | `tools/` |
| `gen_daily_report.py.bak_20260718` | `tools/` |
| `gen_daily_report.py.bak_20260718-mtab` | `tools/` |
| `gen_daily_report.py.bak_20260719-s2` | `tools/` |
| `gen_daily_report.py.bak_20260721-a6b6` | `tools/` |
| `calibrate_risk_factors.py.bak_20260719-s2` | `tools/` |
| `calibrate_risk_factors.py.bak_20260721-a6b6` | `tools/` |
| `emotion_engine_v2.py.bak_20260730` | `tools/` |
| **`risk_factors.json.bak_20260721-f5recal`** | **`config/`** ← 唯一非 tools/ 来源，平铺后易误判 |

### B · 手工补的 2 个（**保留原相对路径**）

**conch 规则盲区**：它按 `simple .bak (+2)` + `date suffix (+1)` 打分，而 `_audit20260728` 这种**带前缀的日期后缀匹配不上**，故这两个未被 conch 报出。本次实测项目内 `.bak` 实有 11 个、conch 只报 9 个，差额即此。

| 归档后（本目录） | 原路径 | 说明 |
|---|---|---|
| `STATUS.md.bak_audit20260728` | 项目根 | 2026-07-28 审计留 |
| `tools/gen_daily_report.py.bak_audit20260728` | `tools/` | 同上 |

这两个**不在 `.conch_audit.log` 里**，回滚靠本目录保留的相对路径自证（反向 `mv` 即还原）。

## 归档前的安全核实（逐个做过）

1. **主文件全部健在且都比备份新** —— `gen_daily_report.py` 197834 B（07-28）、`calibrate_risk_factors.py` 24781 B（07-23）、`emotion_engine_v2.py` 17915 B（07-30）、`risk_factors.json` 12415 B（07-24）、`STATUS.md` 5938 B（07-28）。无一是孤儿备份。
2. **全部零引用** —— 全项目 `.py/.md/.json/.sh` 无任何文件引用这些 `.bak` 名，归档不断链。
3. **`emotion_engine_v2.py.bak_20260730` 与主文件 diff 零行、字节数相同**（均 17915 B）——印证 `TODO.md`「情绪周期四季提前发现能力改造」条所记「叠加层已回退、**代码零改动**」，它是一份零信息副本，留作「回退确实执行过」的凭证。
4. 归档后 conch 复扫：`obsolete 9 → 0`，项目内（`archived/` 外）`.bak` 残留 **0**，主文件 mtime/体积全部未变。

## 关于目录名日期

本目录名 `2026-07-30` 取沙箱本地时间（美西），与被归档文件的 mtime 同一时区；**当时北京时间已是 2026-07-31**。归档是文件系统操作而非业务事件，故与 mtime 对齐、也避免与 conch 未来自动跑时产生两套命名。

## 相关

- 上一批归档：`../2026-07-17/`（当时按原目录结构分 `config/db/news/tools/` 存放，与本批 conch 的平铺方式不同）
- 项目错题本：`../../GOTCHAS.md`
