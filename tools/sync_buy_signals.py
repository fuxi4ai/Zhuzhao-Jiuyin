#!/usr/bin/env python3
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import config
from lib.logger import get_logger
logger = get_logger(__name__)
"""
🕯️ sync_buy_signals.py — 「产业逻辑：买入」信号自动同步（渊图派生）

落实主从倒置：买入信号 = 渊图市场信号(conf≥0.7) + 受益传导链 + 标的(ts_code)；
小鲍课件作第二印证（看同期有没有同步喊）。写入 recap.db.yuantu_buy_signals。

用法:
  python3 sync_buy_signals.py --dry-run        # 只看不写
  python3 sync_buy_signals.py                  # 写库（INSERT OR REPLACE by signal_node）
"""
import sqlite3, argparse, json
from datetime import datetime, timedelta

import yuantu_client as yc
import ticker_resolver as tr

DDL = """
CREATE TABLE IF NOT EXISTS yuantu_buy_signals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  signal_node TEXT UNIQUE,
  date TEXT,
  signal_type TEXT,
  yuantu_confidence REAL,
  source_plevel TEXT,
  industry_chain TEXT,
  beneficiaries TEXT,
  beneficiaries_detail TEXT,
  beneficiaries_ts TEXT,
  beneficiary_count INTEGER,
  ts_resolved INTEGER,
  xiaobao_echo INTEGER,
  echo_count INTEGER,
  verify_status TEXT DEFAULT '待验证',
  verify_return REAL,
  created_at TEXT
);
"""

TOP_BENE = 8           # 每信号取前 N 个受益公司（按 hop）
ECHO_WINDOW = 14       # 小鲍第二印证：±N 天内提及同行业


def _xiaobao_echo(conn, industry, date):
    """小鲍观点层是否在 date 附近同步喊过该行业 → (echo 0/1, 命中数)。"""
    if not industry or not date:
        return 0, 0
    try:
        d0 = datetime.strptime(date[:10], "%Y-%m-%d")
    except Exception:
        return 0, 0
    lo = (d0 - timedelta(days=ECHO_WINDOW)).strftime("%Y-%m-%d")
    hi = (d0 + timedelta(days=ECHO_WINDOW)).strftime("%Y-%m-%d")
    # 行业名取前 4 字做模糊（去英文/括注已在 industry 内）
    kw = industry[:4]
    n = conn.execute(
        """SELECT COUNT(*) FROM industry_signals
           WHERE date BETWEEN ? AND ?
             AND (category LIKE ? OR keyword LIKE ? OR signal_content LIKE ?)""",
        (lo, hi, f"%{kw}%", f"%{kw}%", f"%{kw}%")).fetchone()[0]
    return (1 if n > 0 else 0), n


def build(dry_run=False):
    hc = yc.healthcheck()
    if not hc.get("ok"):
        logger.error(f"❌ 渊图契约 healthcheck 失败，中止: {hc}")
        sys.exit(2)
    logger.info(f"✅ 渊图契约 OK：{hc['node_count']}节点/{hc['edge_count']}边/{hc['signal_count']}信号")

    conn = sqlite3.connect(config.RECAP_DB)
    conn.executescript(DDL)
    # 既有库补列（CREATE IF NOT EXISTS 不会加列）
    if "beneficiaries_detail" not in {r[1] for r in conn.execute("PRAGMA table_info(yuantu_buy_signals)")}:
        conn.execute("ALTER TABLE yuantu_buy_signals ADD COLUMN beneficiaries_detail TEXT")

    signals = yc.get_signals(min_conf=0.7)
    rows, tot_ben, tot_ts, tot_echo = [], 0, 0, 0
    for s in signals:
        bens = yc.beneficiaries(s["signal_id"])[:TOP_BENE]
        names = [b["name"] for b in bens if b.get("name")]
        codes = []
        for b in bens:
            code = tr.resolve(b["name"])
            if code:
                codes.append(f"{b['name']}:{code}")
        # 图谱口径受益度明细（2026-06-25 轻档）：hop→直接/间接；weight→强/中/弱；fin 财务标注（有则取）
        detail = []
        for b in bens:
            w = b.get("weight", 1.0) or 1.0
            detail.append({"name": b.get("name"), "ts": tr.resolve(b.get("name")) or "",
                           "hop": b.get("hop"), "weight": w,
                           "tier": "直接" if b.get("hop") == 1 else "间接",
                           "tier_w": "强" if w >= 0.8 else ("中" if w >= 0.5 else "弱"),
                           "fin": b.get("fin") or {}})
        echo, ecnt = _xiaobao_echo(conn, s["industry"], s["date"])
        tot_ben += len(names); tot_ts += len(codes); tot_echo += echo
        rows.append((s["signal_id"], s["date"], ",".join(s["categories"]),
                     s["signal_conf"], s["source_plevel"], s["industry"],
                     " / ".join(names), " / ".join(codes), len(names), len(codes),
                     echo, ecnt, "待验证", None, datetime.now().isoformat(timespec="seconds"),
                     json.dumps(detail, ensure_ascii=False)))

    logger.info(f"\n拟写入 {len(rows)} 条买入信号 | 受益公司合计 {tot_ben} | "
                f"解析到 ts_code {tot_ts} | 小鲍有第二印证 {tot_echo} 条")
    # 预览前 8
    for r in rows[:8]:
        logger.info(f"  [{r[1]}] {r[2]} conf={r[3]} {r[5]} → 受益{r[8]}/解析{r[9]} "
                    f"小鲍印证={'✓' if r[10] else '—'}")
        if r[7]:
            logger.info(f"        标的: {r[7]}")

    if dry_run:
        logger.info("\n[dry-run] 未写库。")
        conn.close()
        return

    conn.executemany("""
        INSERT INTO yuantu_buy_signals
          (signal_node,date,signal_type,yuantu_confidence,source_plevel,industry_chain,
           beneficiaries,beneficiaries_ts,beneficiary_count,ts_resolved,xiaobao_echo,
           echo_count,verify_status,verify_return,created_at,beneficiaries_detail)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(signal_node) DO UPDATE SET
          date=excluded.date, signal_type=excluded.signal_type,
          yuantu_confidence=excluded.yuantu_confidence, source_plevel=excluded.source_plevel,
          industry_chain=excluded.industry_chain, beneficiaries=excluded.beneficiaries,
          beneficiaries_ts=excluded.beneficiaries_ts, beneficiary_count=excluded.beneficiary_count,
          ts_resolved=excluded.ts_resolved, xiaobao_echo=excluded.xiaobao_echo,
          echo_count=excluded.echo_count, created_at=excluded.created_at,
          beneficiaries_detail=excluded.beneficiaries_detail
    """, rows)
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM yuantu_buy_signals").fetchone()[0]
    conn.close()
    logger.info(f"✅ 已写入 recap.db.yuantu_buy_signals，现共 {n} 条。")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    build(dry_run=a.dry_run)
