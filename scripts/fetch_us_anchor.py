#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""主线美股锚行情拉取 → 公共 market_data.db.us_anchor_daily
（CC 2026-06-10；映射草案 docs/主线美股锚映射_draft_20260610.md）

信源（2026-06-23 实测重定级，见 GOTCHAS G018）：
  Cowork 沙箱（日更主路）：agent 用 web_fetch 取 stockanalysis.com/stocks/{t}/，
       解析「At close 日期 / 收盘 / 1D%」后经 `--source stockanalysis --infile <json>` 喂入。
       绕开 stooq（JS 验证墙 + 沙箱出口 IP 被拒）与 yahoo（装包 + 403），零成本。
       注：close 为不复权价——展示锚只做隔夜参照，单日涨幅自洽，不复权无碍。
  Mac 终端（手动备胎/历史回填）：yfinance 主（auto_adjust=True 复权价，免 key）→ Stooq 备。

stockanalysis JSON 格式（agent 产出，按页面「At close」真实日期 tag；
冷门票若回 CDN 陈旧页，落其真实旧日期、绝不顶目标日 → 结构上杜绝编数）：
  {"NVDA": {"date": "2026-06-22", "close": 208.65, "pct": -0.968}, ...}
依赖：pip3 install yfinance --break-system-packages（仅 Mac 备胎路用）

用法：
  python3 scripts/fetch_us_anchor.py --source stockanalysis --infile /tmp/us_anchor_sa.json  # 沙箱日更主路
  python3 scripts/fetch_us_anchor.py --source yfinance --from 2025-01-01  # Mac 备胎/全量回填
  python3 scripts/fetch_us_anchor.py --dry-run                  # 只列清单
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from lib.logger import get_logger
logger = get_logger(__name__)
import sqlite3, argparse, time, datetime
import config

MARKET_DB = config.MARKET_DB

# ── 主线 → 美股锚（单一可信源；与 docs/主线美股锚映射 同步改）──────────
# anchor_kind: echo=同向印证锚 ｜ thermo=行业温度计（国产替代/对手盘，不作同向印证）
THEME_US = {
    "光模块/CPO/光通信/光纤":      ("LITE", "echo"),    # Lumentum·英伟达战投
    "AI算力/AI硬件/科技硬件":      ("NVDA", "echo"),
    "半导体/芯片/半导体材料":       ("TSM",  "thermo"),  # A股=国产替代，TSM=景气温度计
    "机器人":                     ("TSLA", "echo"),    # Optimus 叙事源
    "光伏":                       ("FSLR", "echo"),
    "新能源电池/锂电/储能/固态":     ("ALB",  "echo"),    # 锂价锚
    "电力/电网/算电协同/燃气轮机":   ("GEV",  "echo"),    # 电网设备+燃气轮机
    "创新药/医药/CRO":             ("LLY",  "thermo"),  # BD 出海买方侧
    "军工":                       ("LMT",  "thermo"),  # 对手盘性质
    "商业航天/卫星":               ("RKLB", "echo"),
    "消费电子/华为/鸿蒙":           ("AAPL", "thermo"),  # 华为对手盘
    "AI软件/应用":                ("PLTR", "echo"),
    "券商/金融":                  ("GS",   "thermo"),
    # "白酒/消费": 无美股锚，降级（见映射文档）
    "黄金/贵金属":                ("NEM",  "echo"),    # 矿业β
    "稀土":                       ("MP",   "echo"),
    "钨/小金属":                  ("ALM",  "echo"),    # Almonty·2025-07 上市，历史短
    "有色金属":                   ("FCX",  "echo"),    # 铜锚
}
BENCHMARK_US = "SPY"
EXTRA = ["QQQ"]          # 科技主线扣β备选基准，一并入库


def all_tickers():
    return sorted({t for t, _ in THEME_US.values()} | {BENCHMARK_US, *EXTRA})


def ensure_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS us_anchor_daily (
            trade_date TEXT,            -- YYYYMMDD（美东收盘日；A股 T+1 开盘前可用）
            ticker     TEXT,
            close_adj  REAL,            -- 复权收盘
            pct_chg    REAL,            -- 日涨幅%（由复权价计算，干净）
            is_benchmark INTEGER DEFAULT 0,
            source     TEXT,            -- yfinance / stooq
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (trade_date, ticker)
        )
    """)
    conn.commit()


def rows_from_closes(tkr, closes, src):
    """[(date,close)] 升序 → 入库行；pct 由复权价环比得出"""
    out, prev = [], None
    isb = 1 if tkr == BENCHMARK_US else 0
    for d, c in closes:
        pct = (c / prev - 1) * 100 if prev else None
        out.append((d.replace("-", ""), tkr, float(c),
                    round(pct, 4) if pct is not None else None, isb, src))
        prev = c
    return out


def get_pro():
    """token：env TUSHARE_TOKEN / Keychain(tushare_pro) / ~/.tushare/token（同 fetch_theme_etf）"""
    import tushare as ts
    tok = _os.environ.get("TUSHARE_TOKEN")
    if not tok:
        try:
            import subprocess
            tok = subprocess.check_output(
                ["security", "find-generic-password", "-s", "tushare_pro", "-w"],
                text=True).strip()
        except Exception:
            pass
    if not tok:
        p = _os.path.expanduser("~/.tushare/token")
        if _os.path.exists(p):
            tok = open(p).read().strip()
    if not tok:
        raise RuntimeError("未找到 TUSHARE_TOKEN")
    ts.set_token(tok)
    return ts.pro_api()


_PRO = None


def fetch_ts(tkr, start, end):
    """tushare us_daily_adj：close×adj_factor=前复权价"""
    global _PRO
    if _PRO is None:
        _PRO = get_pro()
    df = _PRO.us_daily_adj(ts_code=tkr, start_date=start.replace("-", ""),
                           end_date=end.replace("-", ""))
    if df is None or df.empty:
        return None
    # 直接用接口自带 pct_change（%口径），不经 rows_from_closes 环比重算——
    # 增量拉取时窗口首日无前收会得 pct=None，REPLACE 会把库内好数据洗掉（CC 2026-06-12）。
    isb = 1 if tkr == BENCHMARK_US else 0
    return [(r.trade_date, tkr, float(r.close) * float(r.adj_factor or 1.0),
             round(float(r.pct_change), 4) if r.pct_change is not None else None,
             isb, "tushare")
            for r in sorted(df.itertuples(), key=lambda x: x.trade_date)]


# 增量拉取时，rows_from_closes 用窗口内环比算 pct，窗口首日无前收→pct=None，
# REPLACE 会把该日真实涨幅洗成空（CC 2026-06-14 实测 G014）。解法：下载起点
# 向前回看 _LOOKBACK_DAYS 个日历日，全序列算完 pct 再裁回 from_date，
# 使首日 pct 由真实前一交易日得出。
_LOOKBACK_DAYS = 10


def _lookback_start(start):
    return (datetime.date.fromisoformat(start)
            - datetime.timedelta(days=_LOOKBACK_DAYS)).isoformat()


def fetch_yf(tkr, start, end):
    import yfinance as yf
    df = yf.download(tkr, start=_lookback_start(start), end=end, auto_adjust=True,
                     progress=False, threads=False)
    if df is None or df.empty:
        return None
    closes = [(idx.strftime("%Y-%m-%d"), float(row))
              for idx, row in df["Close"][tkr].items()] \
        if hasattr(df["Close"], "columns") else \
        [(idx.strftime("%Y-%m-%d"), float(v)) for idx, v in df["Close"].items()]
    rows = rows_from_closes(tkr, closes, "yfinance")
    sc = start.replace("-", "")                 # 裁回请求窗口，回看日仅用于算首日 pct
    return [r for r in rows if r[0] >= sc]


def fetch_stooq(tkr, start, end):
    import requests, csv, io
    url = (f"https://stooq.com/q/d/l/?s={tkr.lower()}.us"
           f"&d1={_lookback_start(start).replace('-','')}&d2={end.replace('-','')}&i=d")
    r = requests.get(url, timeout=30)
    if r.status_code != 200 or "Date" not in r.text:
        return None
    closes = [(row["Date"], float(row["Close"]))
              for row in csv.DictReader(io.StringIO(r.text)) if row.get("Close")]
    rows = rows_from_closes(tkr, sorted(closes), "stooq")
    sc = start.replace("-", "")
    return [r for r in rows if r[0] >= sc]


def fetch_stockanalysis(infile):
    """读 agent 经 web_fetch 解析好的 JSON → {ticker: [入库行]}。
    每只按页面「At close」真实日期 tag（冷门票回 CDN 陈旧页时落其真实旧日期、
    绝不顶目标日 → 结构上杜绝编数）。close 为不复权价（展示锚）。
    JSON: {"NVDA": {"date":"2026-06-22","close":208.65,"pct":-0.968}, ...}
    缺字段/解析失败的 ticker 直接不返回（上层按缺处理）。"""
    import json
    data = json.load(open(infile, encoding="utf-8"))
    out = {}
    for tkr in all_tickers():
        d = data.get(tkr) or data.get(tkr.upper()) or data.get(tkr.lower())
        if not d or d.get("close") is None or not d.get("date"):
            continue
        try:
            date = str(d["date"]).replace("-", "")
            close = float(d["close"])
            pct = round(float(d["pct"]), 4) if d.get("pct") is not None else None
        except (TypeError, ValueError):
            continue
        isb = 1 if tkr == BENCHMARK_US else 0
        out[tkr] = [(date, tkr, close, pct, isb, "stockanalysis")]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="from_date", default="2025-01-01")
    ap.add_argument("--to", dest="to_date",
                    default=datetime.date.today().isoformat())
    ap.add_argument("--source", choices=["yfinance", "stooq", "tushare", "stockanalysis"],
                    default="yfinance")
    ap.add_argument("--infile", help="--source stockanalysis 时 agent 产出的 JSON 路径")
    ap.add_argument("--interval", type=float, default=0.5,
                    help="每只标的间隔秒数（tushare us_daily_adj 试用态限频 1次/分钟，沙箱跑请 --interval 62）")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    tickers = all_tickers()
    logger.info(f"待拉美股锚 {len(tickers)} 只 [{args.from_date}→{args.to_date}]: {tickers}")
    if args.dry_run:
        logger.info("dry-run，仅列出，不写库")
        return

    conn = sqlite3.connect(MARKET_DB)
    ensure_table(conn)
    total = 0

    # ── 沙箱日更主路：agent web_fetch + 解析后喂 JSON，按真实「At close」日期入库 ──
    if args.source == "stockanalysis":
        if not args.infile:
            raise SystemExit("--source stockanalysis 需 --infile <json>（agent 解析产出）")
        sa = fetch_stockanalysis(args.infile)
        newest = max((rows[0][0] for rows in sa.values()), default=None)  # 最鲜票定基准
        fresh = stale = 0
        for t in tickers:
            rows = sa.get(t)
            if not rows:
                logger.error(f"  ✗ {t}: stockanalysis 无数据 → 标缺（保留旧锚）")
                continue
            conn.executemany(
                "INSERT OR REPLACE INTO us_anchor_daily"
                "(trade_date,ticker,close_adj,pct_chg,is_benchmark,source) "
                "VALUES (?,?,?,?,?,?)", rows)
            conn.commit()
            total += len(rows)
            d = rows[0][0]
            if newest and d == newest:
                fresh += 1; tag = "✓"
            else:
                stale += 1; tag = f"⚠陈旧({d})"
            logger.info(f"  {tag} {t}: close={rows[0][2]} pct={rows[0][3]} @ {d}")
        miss = len(tickers) - fresh - stale
        logger.info(f"\n✅ stockanalysis 完成：写 {total} 行；基准日 {newest}；"
                    f"新鲜 {fresh} / 陈旧 {stale} / 缺 {miss}")
        conn.close()
        return

    chain = {"yfinance": [fetch_yf, fetch_stooq],
             "stooq": [fetch_stooq],
             "tushare": [fetch_ts, fetch_yf, fetch_stooq]}[args.source]
    for t in tickers:
        rows = None
        for fn in chain:
            try:
                rows = fn(t, args.from_date, args.to_date)
                if rows:
                    break
            except Exception as e:
                logger.warning(f"  {fn.__name__} ✗ {t}: {e} → 降级下一信源")
        if not rows:
            logger.error(f"  ✗ {t}: 两源皆无数据")
            continue
        conn.executemany(
            "INSERT OR REPLACE INTO us_anchor_daily"
            "(trade_date,ticker,close_adj,pct_chg,is_benchmark,source) "
            "VALUES (?,?,?,?,?,?)", rows)
        conn.commit()
        total += len(rows)
        logger.info(f"  ✓ {t}: {len(rows)} 行 ({rows[0][5]})")
        time.sleep(args.interval)
    logger.info(f"\n✅ 完成，写入 {total} 行 → market_data.db.us_anchor_daily")
    conn.close()


if __name__ == "__main__":
    main()
