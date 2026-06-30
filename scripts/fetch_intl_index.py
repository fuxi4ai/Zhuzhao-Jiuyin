#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""外盘指数（隔夜·期货预期）拉取 → 公共 market_data.db.intl_index_daily
（烛阴 2026-06-29；为日报「外盘隔夜·期货预期」栏目供数）

定位：A 股开盘前的外部定价背景。三条读数都映射 AI/科技硬件链——
  • 纳斯达克综合（^IXIC）= 美股【隔夜回望】，宽科技 tone（Doctor 2026-06-29 定：美国不取硬件纯读数 SOX，用纳指）。
  • 日经225期货（NKD=F，CME）= 【期货预期】，近 24h 交易、亚盘开盘前有远期价；日股含东京电子/Advantest 等半导体设备权重。
  • 韩国 EWY（iShares MSCI Korea，美上市）= 【期货预期·ETF 代理】。免费源无 KOSPI 指数期货（yfinance KOSPI=F 404，2026-06-29 实测），
    EWY 在美时段交易→首尔开盘前的隔夜远期代理；三星/SK海力士存储芯权重高，是 AI 硬件（存储）代理。Doctor 拍板用 EWY。

信源：yfinance（白名单已开，沙箱直出；同 fetch_us_anchor 的 G014）。
铁律（数据真实性）：取不到的指数 → 直接跳过、不写、不编；上层日报按缺数诚实标注。

用法：
  python3 scripts/fetch_intl_index.py                  # 增量拉最新（默认近 10 日窗，算干净 pct）
  python3 scripts/fetch_intl_index.py --from 2025-01-01  # 回填
  python3 scripts/fetch_intl_index.py --dry-run          # 只列清单
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from lib.logger import get_logger
logger = get_logger(__name__)
import sqlite3, argparse, datetime
import config

MARKET_DB = config.MARKET_DB

# ── 外盘指数清单（单一可信源；与日报 render 的 INTL_ORDER 同步）──────────
# code: 内部稳定键 ｜ symbol: yfinance ｜ kind: overnight=隔夜回望 / futures=期货预期 / etf_proxy=ETF远期代理
INDICES = [
    # code,       symbol,  name,            kind,        note
    # —— 美股栏（隔夜回望）：纳指 + AI/科技硬件代表股 ——
    ("NASDAQ",   "QQQ",   "纳指100(QQQ)",   "overnight", "美股隔夜 · Nasdaq-100 ETF 代纳指"),
    ("NVDA",     "NVDA",  "英伟达",         "us_stock",  "AI 算力"),
    ("AVGO",     "AVGO",  "博通",           "us_stock",  "AI 网络 / ASIC"),
    ("LITE",     "LITE",  "Lumentum",       "us_stock",  "光模块 / CPO"),
    ("SPCX",     "SPCX",  "SpaceX",         "us_stock",  "商业航天 · 2026-06-12 纳指新上市（历史短·波动大）"),
    # —— 亚洲栏（期货预期）：日本开盘前的远期（韩国已移至 fetch_kr_stocks 直追三星/SK海力士）——
    ("JP_FUT",   "NKD=F", "日经225期货",    "futures",   "CME · 亚盘开盘前远期 · 含半导体设备权重"),
]
_LOOKBACK_DAYS = 10  # 向前回看，使窗口首日 pct 由真实前一交易日得出（同 fetch_us_anchor G014）


def ensure_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS intl_index_daily (
            trade_date TEXT,            -- YYYYMMDD（该指数自身最新交易日）
            code       TEXT,            -- NASDAQ / JP_FUT / KR_PROXY（内部稳定键）
            symbol     TEXT,            -- yfinance 代码（^IXIC / NKD=F / EWY）
            name       TEXT,
            kind       TEXT,            -- overnight / futures / etf_proxy / us_stock
            close      REAL,
            pct_chg    REAL,            -- 日涨幅%
            note       TEXT,            -- 该行映射说明（随源不同，render 直接显示）
            source     TEXT,            -- yfinance / stockanalysis
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (trade_date, code)
        )
    """)
    # 老库已有 intl_index_daily 但缺 note 列时，补列（幂等）
    cols = {r[1] for r in conn.execute("PRAGMA table_info(intl_index_daily)")}
    if "note" not in cols:
        conn.execute("ALTER TABLE intl_index_daily ADD COLUMN note TEXT")
    conn.commit()


def _lookback_start(start):
    return (datetime.date.fromisoformat(start)
            - datetime.timedelta(days=_LOOKBACK_DAYS)).isoformat()


def fetch_yf(symbol, start, end):
    """Yahoo Finance chart API（urllib 直取，**不依赖 yfinance 包**；白名单已开、沙箱直达，
    2026-06-30 实测 LITE/日经/纳指/韩股皆新鲜，根治 stockanalysis CDN 陈旧坑）。
    返回 [(YYYYMMDD, close, pct)] 升序，裁回 >= start（回看日仅用于算首日 pct）。"""
    import urllib.request as _u, urllib.parse as _up, json as _j
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           + _up.quote(symbol) + "?range=1mo&interval=1d")
    req = _u.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with _u.urlopen(req, timeout=15) as r:
        data = _j.loads(r.read().decode())
    res = (data.get("chart", {}).get("result") or [None])[0]
    if not res:
        return None
    ts = res.get("timestamp") or []
    closes = res.get("indicators", {}).get("quote", [{}])[0].get("close") or []
    sc = start.replace("-", "")
    out, prev = [], None
    for t, c in zip(ts, closes):
        if c is None:
            continue
        d = datetime.datetime.utcfromtimestamp(t).strftime("%Y%m%d")
        pct = (c / prev - 1) * 100 if prev else None
        if d >= sc:
            out.append((d, round(float(c), 2), round(pct, 4) if pct is not None else None))
        prev = c
    return out or None


# ── stockanalysis 源（生产主路：沙箱 yahoo 403，同 fetch_us_anchor G018）──────
# 九儿在 SKILL 里逐个 web_fetch 下列 URL，解析「At close: 日期 / 收盘 / 1D%」写成 JSON：
#   {"NASDAQ":{"date":"2026-06-26","close":..,"pct":..}, "NVDA":{..}, ..., "JP_FUT":{..EWJ..}}
# 再 `--source stockanalysis --infile <json>`。键＝code，本表定义各 code 在 SA 下的真实标的与口径。
# ⚠️ SA 无 CME 期货：NASDAQ→QQQ(纳指100ETF)、JP_FUT→EWJ(日本ETF隔夜代理)；二者口径如实记 symbol/kind。
SA_SOURCES = {
    # code:      (sa_symbol, kind,        name,             note,                                     url_path)
    "NASDAQ":   ("QQQ",  "overnight", "纳指100(QQQ)",   "美股隔夜 · Nasdaq-100 ETF 代纳指",        "etf/qqq"),
    "NVDA":     ("NVDA", "us_stock",  "英伟达",          "AI 算力",                                 "stocks/nvda"),
    "AVGO":     ("AVGO", "us_stock",  "博通",            "AI 网络 / ASIC",                          "stocks/avgo"),
    "LITE":     ("LITE", "us_stock",  "Lumentum",        "光模块 / CPO",                            "stocks/lite"),
    "SPCX":     ("SPCX", "us_stock",  "SpaceX",          "商业航天 · 新上市",                       "stocks/spcx"),
    "JP_FUT":   ("EWJ",  "etf_proxy", "日本(EWJ代理)",   "MSCI日本ETF · 隔夜远期代理（生产无NKD=F源）", "etf/ewj"),
    "KR_PROXY": ("EWY",  "etf_proxy", "韩国(EWY代理)",   "MSCI韩国ETF · 三星/SK海力士存储芯 · 隔夜代理", "etf/ewy"),
}


def fetch_stockanalysis(infile):
    """读九儿 web_fetch 解析好的 JSON（键＝code）→ {code: [(date,close,pct)]}。
    每个 code 按 SA_SOURCES 记其真实 symbol/kind/name/note。缺字段直接不返回（上层标缺）。"""
    import json
    data = json.load(open(infile, encoding="utf-8"))
    out = {}
    for code in SA_SOURCES:
        d = data.get(code)
        if not d or d.get("close") is None or not d.get("date"):
            continue
        try:
            date = str(d["date"]).replace("-", "")
            close = round(float(d["close"]), 2)
            pct = round(float(d["pct"]), 4) if d.get("pct") is not None else None
        except (TypeError, ValueError):
            continue
        out[code] = (date, close, pct)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="from_date",
                    default=(datetime.date.today() - datetime.timedelta(days=12)).isoformat())
    ap.add_argument("--to", dest="to_date",
                    default=(datetime.date.today() + datetime.timedelta(days=1)).isoformat())
    ap.add_argument("--source", choices=["yfinance", "stockanalysis"], default="yfinance",
                    help="yfinance=Mac/白名单沙箱主路；stockanalysis=生产沙箱(yahoo 403)主路，需 --infile")
    ap.add_argument("--infile", help="--source stockanalysis 时九儿产出的 JSON 路径")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.dry_run:
        src = SA_SOURCES if args.source == "stockanalysis" else {c: (s, k, n, note, "")
                                                                  for c, s, n, k, note in INDICES}
        logger.info(f"[{args.source}] 待拉 {len(src)} 个:")
        for code, v in src.items():
            logger.info(f"  {code:9s} {v[0]:7s} {v[2]}  [{v[1]}]  {v[3]}")
        return

    conn = sqlite3.connect(MARKET_DB)
    ensure_table(conn)
    total = miss = 0

    if args.source == "stockanalysis":
        if not args.infile:
            raise SystemExit("--source stockanalysis 需 --infile <json>（九儿 web_fetch 解析产出）")
        sa = fetch_stockanalysis(args.infile)
        for code, (sym, kind, name, note, _url) in SA_SOURCES.items():
            row = sa.get(code)
            if not row:
                logger.error(f"  ✗ {code}: stockanalysis 无数据 → 标缺（保留旧行，绝不编数）")
                miss += 1
                continue
            d, c, p = row
            conn.execute(
                "INSERT OR REPLACE INTO intl_index_daily"
                "(trade_date,code,symbol,name,kind,close,pct_chg,note,source) "
                "VALUES (?,?,?,?,?,?,?,?,?)", (d, code, sym, name, kind, c, p, note, "stockanalysis"))
            conn.commit()
            total += 1
            logger.info(f"  ✓ {code:9s} {sym:7s} 最新 {d} close={c} pct={p}")
        logger.info(f"\n✅ stockanalysis 完成：写 {total} 行；缺 {miss}/{len(SA_SOURCES)}")
        conn.close()
        return

    # —— yfinance 主路（Mac / 白名单沙箱）——
    logger.info(f"[yfinance] 待拉外盘指数 {len(INDICES)} 个 [{args.from_date}→{args.to_date}]: "
                f"{[c for c, *_ in INDICES]}")
    for code, sym, name, kind, note in INDICES:
        try:
            rows = fetch_yf(sym, args.from_date, args.to_date)
        except Exception as e:
            logger.warning(f"  yfinance ✗ {code}({sym}): {e}")
            rows = None
        if not rows:
            logger.error(f"  ✗ {code}({sym}): 无数据 → 标缺（保留旧行，绝不编数）")
            miss += 1
            continue
        conn.executemany(
            "INSERT OR REPLACE INTO intl_index_daily"
            "(trade_date,code,symbol,name,kind,close,pct_chg,note,source) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            [(d, code, sym, name, kind, c, p, note, "yahoo") for d, c, p in rows])
        conn.commit()
        total += len(rows)
        last = rows[-1]
        logger.info(f"  ✓ {code:9s} {sym:7s} 最新 {last[0]} close={last[1]} pct={last[2]} ({len(rows)}行)")
    logger.info(f"\n✅ yfinance 完成：写 {total} 行 → market_data.db.intl_index_daily；缺 {miss}/{len(INDICES)}")
    conn.close()


if __name__ == "__main__":
    main()
