#!/usr/bin/env python3
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import config
from lib.logger import get_logger
logger = get_logger(__name__)
"""
🕯️ ticker_resolver.py — 公司中文名 → A股 ts_code 解析器

为什么需要：渊图公司节点有中文名但多数无 ts_code（382 仅 26 带码），
故烛阴侧自建名→码解析，把信号追到的受益公司落成可交易标的。

名→码索引来源（种子，按优先级）：
  1. Market-Data/tushare-cache/tushare.db  stocks(name, ts_code)
  2. Market-Data/.../valuation valuation_daily(stock_name, stock_code)
  3. 渊图 company 节点自带 ts_code（26）
  4. （可选）stock_basic 全量表 —— 由句芒 tushare 模块 populate（见 --how-to-populate）

⚠️ 覆盖度受限于种子；全量 A股名↔码需句芒 tushare stock_basic。本模块只读、不抓 tushare。

用法:
  python3 ticker_resolver.py resolve 先导
  python3 ticker_resolver.py coverage <names...>      # 报覆盖率
  python3 ticker_resolver.py how-to-populate
"""
import sqlite3, json, re, argparse
from functools import lru_cache
from pathlib import Path

_SUFFIX = re.compile(r"（[^）]*）|\([^)]*\)")          # 去渊图括注："先导（磷化铟衬底）"→"先导"
_ASCII = re.compile(r"^[\x00-\x7f]+$")                 # 纯英文名（外企，无 A 股码）


def _norm(name):
    if not name:
        return ""
    return _SUFFIX.sub("", str(name)).strip()


@lru_cache(maxsize=1)
def _index():
    """构建 名→ts_code 索引（仅 A 股 .SH/.SZ/.BJ）。"""
    idx = {}

    def add(name, code):
        n = _norm(name)
        if not n or not code:
            return
        if not re.search(r"\d{6}\.(SH|SZ|BJ)", str(code)):
            return
        idx.setdefault(n, code)

    # 1. tushare-cache stocks
    tdb = Path(config.DATABASE_ROOT) / "Market-Data" / "tushare-cache" / "tushare.db"
    if tdb.exists():
        try:
            c = sqlite3.connect(tdb)
            for name, code in c.execute("SELECT name, ts_code FROM stocks"):
                add(name, code)
            # 可选 stock_basic 全量表（句芒 populate 后存在）
            if c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='stock_basic'").fetchone():
                for name, code in c.execute("SELECT name, ts_code FROM stock_basic"):
                    add(name, code)
            c.close()
        except Exception as e:
            logger.warning(f"⚠️ tushare-cache 读取失败（名→码主种子 {tdb}）: {e} — 索引将残缺，解析率会骤降（G030）")

    # 2. valuation
    vdb = Path(config.DATABASE_ROOT) / "Market-Data" / "valuation" / "valuation.db"
    if vdb.exists():
        try:
            c = sqlite3.connect(vdb)
            for name, code in c.execute(
                    "SELECT DISTINCT stock_name, stock_code FROM valuation_daily WHERE stock_name IS NOT NULL"):
                code = code if "." in str(code) else None  # valuation 用纯数字码，跳过无后缀的
                add(name, code)
            c.close()
        except Exception:
            pass

    # 3. 渊图自带码
    try:
        sys_path = config.YUANTU_KG
        kg = json.loads(Path(sys_path).read_text(encoding="utf-8"))
        for n in kg["nodes"]:
            if str(n["id"]).startswith("company_"):
                p = n.get("properties", {}) or {}
                code = p.get("ts_code") or p.get("ticker")
                if not code:
                    m = re.search(r"(\d{6}\.(SH|SZ|BJ))", n.get("description", "") + str(p))
                    code = m.group(1) if m else None
                add(n.get("name"), code)
    except Exception:
        pass

    if len(idx) < 1000:
        logger.warning(f"⚠️ 名→码索引仅 {len(idx)} 条（stock_basic 正常时应 ≥5000）——疑似种子源缺失/失联（G030）")
    else:
        logger.info(f"名→码索引 {len(idx)} 条")
    return idx


def resolve(name):
    """名→ts_code，解析不到返回 None。纯英文名（外企）直接返回 None。"""
    n = _norm(name)
    if not n or _ASCII.match(n):
        return None
    idx = _index()
    if n in idx:
        return idx[n]
    # 宽松：去掉常见行业后缀词再试
    for kw in ("科技", "股份", "集团", "半导体", "电子", "材料", "新材"):
        if n.endswith(kw) and n[:-len(kw)] in idx:
            return idx[n[:-len(kw)]]
    # 含子串（谨慎，仅当唯一命中）
    cands = [code for nm, code in idx.items() if n in nm or nm in n]
    return cands[0] if len(cands) == 1 else None


def coverage(names):
    res = {nm: resolve(nm) for nm in names}
    hit = sum(1 for v in res.values() if v)
    cn = sum(1 for nm in names if not _ASCII.match(_norm(nm) or "x"))   # 中文名（应有码的）
    return {"total": len(names), "cn_names": cn, "resolved": hit,
            "rate_overall": round(hit / max(len(names), 1), 2),
            "rate_cn": round(hit / max(cn, 1), 2), "detail": res}


HOWTO = """\
渊图 ts_code 覆盖薄，全量名↔码需句芒 tushare stock_basic。可在 macOS 终端或沙箱内跑（需 TUSHARE_TOKEN；约 06-11 白名单开放后沙箱亦经代理+token 可调 Tushare）：

  # 句芒 tushare 模块拉 stock_basic 写入公共缓存（示意）
  python3 -c "import tushare as ts, sqlite3, os;
  pro=ts.pro_api(os.environ['TUSHARE_TOKEN']);
  df=pro.stock_basic(exchange='', list_status='L', fields='ts_code,name');
  con=sqlite3.connect('Database/Market-Data/tushare-cache/tushare.db');
  df.to_sql('stock_basic', con, if_exists='replace', index=False); con.close()"

写入后本解析器自动读取 stock_basic（无需改代码）。烛阴沙盒不抓 tushare（守句芒取数归口）。\
"""


def main():
    ap = argparse.ArgumentParser(description="公司名→ts_code 解析器")
    sub = ap.add_subparsers(dest="cmd")
    pr = sub.add_parser("resolve"); pr.add_argument("name")
    pc = sub.add_parser("coverage"); pc.add_argument("names", nargs="+")
    sub.add_parser("how-to-populate")
    sub.add_parser("index-size")
    a = ap.parse_args()
    if a.cmd == "resolve":
        logger.info(f"{a.name} → {resolve(a.name)}")
    elif a.cmd == "coverage":
        c = coverage(a.names)
        logger.info(f"覆盖 {c['resolved']}/{c['total']}（中文名口径 {c['rate_cn']:.0%}）")
        for k, v in c["detail"].items():
            logger.info(f"  {k} → {v}")
    elif a.cmd == "index-size":
        logger.info(f"名→码索引条目: {len(_index())}")
    elif a.cmd == "how-to-populate":
        logger.info(HOWTO)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
