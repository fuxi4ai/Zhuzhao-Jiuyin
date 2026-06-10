# 📰 新闻模块 · STATUS

> **最后更新**: 2026-06-06（大修，对齐 D7 信源收窄）
> **模块版本**: v2.0 · 库: 已归档 `Database/烛照九阴/archive/news_财新试验_20260511.db`（2026-06-10）

---

## 数据库状态（实测）

| 指标 | 值 |
|------|-----|
| news_raw | 17 条 |
| news_cleaned | 17 条 |
| news_events | 0 条（不再启用，课件管线落 recap.db 维度表） |
| source_config | 3 条 |
| fetch_log | 0 条 |

---

## 信源状态（D7 收窄后）

| 信源 | 状态 | 说明 |
|------|------|------|
| **小鲍四维度课件** | ✅ 现役·唯一源 | 复盘老师解读语料，置信度统一 **P2**（非一手源）。语料在 `Database/烛照九阴/Raw-Recap/`，由 `xiaobao_extractor` 处理。 |
| 财新（数据通/PRO） | ⏸️ 搁置 | 已娱乐化、价值低，备查不删。`_legacy/news/caixin_bridge.py` |
| 冈底斯投研（GTS） | ❌ 弃用 | 弃桥。`_legacy/news/gangtise_*` |

---

## 现役代码

| 文件 | 说明 |
|------|------|
| `news/tools/recap_bridge_v2.py` | 新闻 → recap Dim1/2/3 桥（已 repoint config） |
| `news/cleaners/news_cleaner.py` | 去重/分类/评分/提取（已 repoint config） |
| `news/schema/news_schema.sql` | 5 表 schema |

> 已退役并移入 `_legacy/news/`：caixin_bridge、gangtise_bridge、gangtise_recap_bridge、recap_bridge(v1)、import_fetch_results。

---

## 待办

| 项 | 说明 |
|----|------|
| ~~news_events 落数据~~ | 已裁决不启用：单源课件→recap.db 维度表（2026-06-10） |
| BAILIAN 去除 | LLM 步骤改由九儿亲做（D7），脚本只做取数+正则+落库 |

---

*news/STATUS.md · 2026-06-06 · CC*
