#!/usr/bin/env python3
"""
烛照九阴 · 中央配置（路径单一可信源）
==========================================
数灵转移（2026-06-04 收官）后，数据已迁入公共数据层 `Database/`。
本模块是项目内所有脚本获取数据库/语料路径的**唯一入口**——
禁止任何脚本再写死 `/home/admin/openclaw/...` 或 `projects/烛照九阴/db/...`。

用法:
    import os, sys
    sys.path.insert(0, <项目根>)        # 见各脚本顶部 bootstrap
    import config
    conn = sqlite3.connect(config.RECAP_DB)

可用属性:
    PROJECT_ROOT   本项目根目录
    DATABASE_ROOT  公共数据层 Database/ 根（可用环境变量 ZZJY_DATABASE_ROOT 覆盖）
    RECAP_DB       四维度复盘 + 量化周期库（烛阴自有，可写）
    NEWS_DB        新闻原料/清洗/事件库（烛阴自有，可写）
    MARKET_DB      公共行情库 market_data.db（句芒维护，**只读**）
    RAW_RECAP_DIR  小鲍四维度课件第三方语料（只读）
    YUANTU_ROOT    渊图（行业研究）正源（CC 维护，烛阴**只读引用**）
    ENV_FILE       Database/.env（TUSHARE_TOKEN / FRED_API_KEY）
"""
import os
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent


def _find_database_root(start: Path) -> Path:
    """从项目向上找到含 `Database/烛照九阴` 的目录层，返回其 Database/ 路径。
    找不到则回退到 <Documents>/Database 的常规相对位（parents[3]）。"""
    env = os.environ.get("ZZJY_DATABASE_ROOT")
    if env:
        return Path(env)
    for p in [start, *start.parents]:
        cand = p / "Database" / "烛照九阴"
        if cand.exists():
            return p / "Database"
    # 回退：烛照九阴 -> Financial -> Projects -> Claude -> Documents/Database
    return start.parents[3] / "Database"


DATABASE_ROOT = _find_database_root(PROJECT_ROOT)

# ─── 输出/产物根（沙箱平铺挂载下用 env 覆盖，见通用教训 G-X45）──────
# AI4ME 报告输出根：ZZJY_OUTPUT_ROOT 覆盖；否则回退 <Documents>/AI4ME（parents[3]）
OUTPUT_ROOT = Path(os.environ.get("ZZJY_OUTPUT_ROOT") or (PROJECT_ROOT.parents[3] / "AI4ME"))
# Cowork Artifacts 根：ZZJY_ARTIFACT_ROOT 覆盖；否则回退 <Documents>/Claude/Artifacts
ARTIFACT_ROOT = Path(os.environ.get("ZZJY_ARTIFACT_ROOT") or (PROJECT_ROOT.parents[3] / "Claude" / "Artifacts"))

# ─── 烛阴自有库（可写）────────────────────────────────────────
RECAP_DB = str(DATABASE_ROOT / "烛照九阴" / "recap.db")
NEWS_DB = str(DATABASE_ROOT / "烛照九阴" / "archive" / "news_财新试验_20260511.db")  # 2026-06-10 归档，财新搁置

# ─── 公共/外部资源（只读引用）────────────────────────────────
MARKET_DB = str(DATABASE_ROOT / "Market-Data" / "market_data.db")
RAW_RECAP_DIR = str(DATABASE_ROOT / "烛照九阴" / "Raw-Recap")
YUANTU_ROOT = str(DATABASE_ROOT / "行业研究")          # 渊图正源，只读
YUANTU_KG = str(DATABASE_ROOT / "行业研究" / "mapping" / "latest.json")   # 渊图稳定入口（软链）
YUANTU_SCORES = str(DATABASE_ROOT / "行业研究" / "scoring")               # yuantu_scoring 标的分
ENV_FILE = str(DATABASE_ROOT / ".env")

# ─── 项目内本地目录 ──────────────────────────────────────────
LOG_DIR = str(PROJECT_ROOT / "logs")


def load_env(path: str = None) -> dict:
    """读取 Database/.env 到 os.environ（已存在的不覆盖），并返回解析字典。
    token 只存 .env / 环境变量，绝不入项目代码或库。"""
    path = path or ENV_FILE
    parsed = {}
    if not os.path.exists(path):
        return parsed
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            parsed[k] = v
            os.environ.setdefault(k, v)
    return parsed


def connect_write(db_path, **kw):
    """写连接中央护栏（硬拒绝）：路径落在沙箱挂载盘且未显式放行则拒写。
    Mac 原生路径(/Users/...)正常放行；沙箱内请设 ZZJY_DATABASE_ROOT=/tmp/dbroot
    走 /tmp 副本往返后整文件 cp 回。（GOTCHAS G019 · recap 反复损坏 2026-06-29）"""
    s = str(Path(db_path).resolve())
    if (("/sessions/" in s) or ("/mnt/" in s)) and not os.environ.get("ZZJY_ALLOW_MOUNT_WRITE"):
        raise RuntimeError(
            f"[connect_write] 拒绝直写挂载盘真盘: {db_path}\n"
            "  → 设 ZZJY_DATABASE_ROOT=/tmp/dbroot 走 /tmp 副本往返后整文件 cp 回；\n"
            "  → 或仅 Mac 原生终端显式 ZZJY_ALLOW_MOUNT_WRITE=1。（GOTCHAS G019）")
    return sqlite3.connect(db_path, **kw)


if __name__ == "__main__":
    print("PROJECT_ROOT  :", PROJECT_ROOT)
    print("DATABASE_ROOT :", DATABASE_ROOT)
    for name in ["RECAP_DB", "NEWS_DB", "MARKET_DB", "RAW_RECAP_DIR", "YUANTU_ROOT", "ENV_FILE"]:
        val = globals()[name]
        print(f"{name:14}: {val}  [{'✅' if os.path.exists(val) else '❌缺失'}]")
