#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""主线相对强势持续性（research-CC 2026-06-09）

口径（Doctor 定）：theme_continuity_days = 截至当日，主线 ETF 相对沪深300(510300)
的「超额收益连续为正」的天数。复合主线用篮子（成分 ETF 超额等权平均）。

数据：公共 market_data.db.theme_etf_daily（trade_date,etf_code,pct_chg,is_benchmark）
依赖：sector_alias（小鲍主线自由文本 → 规范名）。

对外：
  resolve_theme_to_etfs(main_line_text, alias_rows) -> (theme_label, [etf_code,...])
  excess_positive_streak(etf_codes, as_of_date, series) -> int
  theme_continuity_days(main_line_text, as_of_date, conn_market, alias_rows) -> (days, theme, etfs)
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

BENCHMARK = "510300.SH"

# 主线规范名 → ETF（与 fetch_theme_etf.THEME_ETF 对应；篮子=多元素）
THEME_ETF = {
    "光通信":   ["515880.SH"], "光模块": ["515880.SH"], "CPO": ["515880.SH"], "光纤": ["515880.SH"],
    "半导体":   ["159995.SZ"], "芯片": ["159995.SZ"], "半导体材料": ["159995.SZ"],
    "机器人":   ["562500.SH"],
    "光伏":     ["515790.SH"],
    "新能源电池": ["159566.SZ"], "锂电": ["159566.SZ"], "储能": ["159566.SZ"], "固态电池": ["159566.SZ"],
    "电力":     ["159611.SZ"], "电网": ["159611.SZ"], "算电协同": ["159611.SZ"], "燃气轮机": ["159611.SZ"],
    "创新药":   ["159992.SZ"], "医药": ["159992.SZ"],
    "军工":     ["512660.SH"],
    "商业航天": ["563230.SH"], "卫星": ["563230.SH"],
    "消费电子": ["561600.SH"],
    "AI软件":   ["515230.SH"], "AI应用": ["515230.SH"],
    "白酒":     ["512690.SH"],
    "金融":     ["512880.SH"], "券商": ["512880.SH"],
    # 复合主线 → 篮子
    "AI算力":   ["515880.SH", "159995.SZ"], "AI硬件": ["515880.SH", "159995.SZ"],
    "科技硬件": ["515880.SH", "159995.SZ"], "算力": ["515880.SH", "159995.SZ"],
}


def resolve_theme_to_etfs(main_line_text, alias_rows=None):
    """main_line 自由文本 → (主线label, [etf...])。
    策略：先在文本里找 THEME_ETF 的关键词（按长度优先，避免'电力'误命中'电力设备'之外）；
    找不到再经 sector_alias 的别名兜底。返回第一个命中的主线（dim2 主线通常首词为主导）。"""
    if not main_line_text:
        return None, []
    text = main_line_text
    # 1) 命中 THEME_ETF 关键词，取「出现位置最靠前」者为主导（dim2 主线首词为主导）；
    #    同位置时长词优先（避免 通信/光通信 这类部分误命中）
    hits = [(text.index(kw), -len(kw), kw) for kw in THEME_ETF if kw in text]
    if hits:
        kw = min(hits)[2]
        return kw, THEME_ETF[kw]
    # 2) sector_alias 兜底：alias_rows = [(canonical, aliases_csv), ...]
    if alias_rows:
        for canon, aliases in alias_rows:
            cands = [canon] + [a.strip() for a in (aliases or "").split(",")]
            for a in cands:
                if a and a in text:
                    # canonical 再映射到 THEME_ETF
                    for kw in sorted(THEME_ETF, key=len, reverse=True):
                        if kw in canon or canon in kw:
                            return canon, THEME_ETF[kw]
    return None, []


def excess_positive_streak(etf_codes, as_of_date, series):
    """series: {etf_code: {date: pct_chg}}，含 BENCHMARK。
    返回截至 as_of_date（含）超额收益连续为正的交易日数。
    篮子：当日超额 = mean(成分 etf pct_chg) - bench pct_chg。"""
    bench = series.get(BENCHMARK, {})
    # 公共交易日轴：所有成分 + 基准都有数据的日期，且 <= as_of_date
    if not etf_codes:
        return 0
    dates = set(bench)
    for c in etf_codes:
        dates &= set(series.get(c, {}))
    dates = sorted(d for d in dates if d <= as_of_date)
    streak = 0
    for d in reversed(dates):           # 从 as_of_date 往前数
        comp = [series[c][d] for c in etf_codes]
        excess = (sum(comp) / len(comp)) - bench[d]
        if excess > 0:
            streak += 1
        else:
            break
    return streak


def load_series(conn_market, codes):
    """从 theme_etf_daily 读 {etf_code:{trade_date:pct_chg}}。trade_date 用 YYYY-MM-DD 归一。"""
    out = {}
    q = "SELECT trade_date, etf_code, pct_chg FROM theme_etf_daily WHERE etf_code IN (%s)" % \
        ",".join("?" * len(codes))
    for td, code, pct in conn_market.execute(q, codes):
        d = td if "-" in str(td) else f"{td[:4]}-{td[4:6]}-{td[6:]}"
        out.setdefault(code, {})[d] = pct
    return out


def theme_continuity_days(main_line_text, as_of_date, conn_market, alias_rows=None):
    theme, etfs = resolve_theme_to_etfs(main_line_text, alias_rows)
    if not etfs:
        return 0, theme, []            # 无锚主线 → 0（降级）
    series = load_series(conn_market, etfs + [BENCHMARK])
    days = excess_positive_streak(etfs, as_of_date, series)
    return days, theme, etfs


# ─────────────────────────── 自测（合成数据，无需 tushare）───────────────────────────
def _selftest():
    print("=== theme_strength 自测 ===")
    # 1) 主线解析
    cases = [
        ("光通信(绝对核心)+机器人由轻转重", "光通信", ["515880.SH"]),
        ("科技硬件+芯片双轮驱动",          "科技硬件", ["515880.SH", "159995.SZ"]),  # 篮子
        ("资金切向机器人+商业航天",         "机器人", ["562500.SH"]),
        ("电力(算电协同)+半导体材料",       "电力", ["159611.SZ"]),
        ("纯文本无主线",                  None, []),
    ]
    ok = True
    for text, exp_theme, exp_etf in cases:
        th, et = resolve_theme_to_etfs(text)
        flag = "✅" if (th == exp_theme and et == exp_etf) else "❌"
        if flag == "❌": ok = False
        print(f"  {flag} '{text[:20]}' → {th} {et}")

    # 2) 超额连板 streak（合成：单只 ETF）
    s = {
        "562500.SH": {"2026-03-20": 1.0, "2026-03-21": 2.0, "2026-03-24": -0.5,
                      "2026-03-25": 3.0, "2026-03-26": 1.5, "2026-03-27": 0.8},
        BENCHMARK:   {"2026-03-20": 0.5, "2026-03-21": 0.5, "2026-03-24": 0.5,
                      "2026-03-25": 0.5, "2026-03-26": 0.5, "2026-03-27": 1.0},
    }
    # 截至 03-27: 27日超额=0.8-1.0=-0.2<0 → streak=0
    st1 = excess_positive_streak(["562500.SH"], "2026-03-27", s)
    # 截至 03-26: 26(1.5-0.5=+),25(3-0.5=+),24(-0.5-0.5=-) → streak=2
    st2 = excess_positive_streak(["562500.SH"], "2026-03-26", s)
    print(f"  {'✅' if st1==0 else '❌'} streak@03-27 = {st1} (期望0)")
    print(f"  {'✅' if st2==2 else '❌'} streak@03-26 = {st2} (期望2)")

    # 3) 篮子超额
    s2 = {
        "515880.SH": {"2026-03-25": 2.0, "2026-03-26": 1.0},
        "159995.SZ": {"2026-03-25": 0.0, "2026-03-26": 3.0},
        BENCHMARK:   {"2026-03-25": 0.5, "2026-03-26": 0.5},
    }
    # 26: mean(1,3)=2 -0.5=+ ; 25: mean(2,0)=1 -0.5=+ → streak=2
    st3 = excess_positive_streak(["515880.SH", "159995.SZ"], "2026-03-26", s2)
    print(f"  {'✅' if st3==2 else '❌'} 篮子 streak@03-26 = {st3} (期望2)")

    ok = ok and st1 == 0 and st2 == 2 and st3 == 2
    print("=== 自测", "全通过 ✅" if ok else "有失败 ❌", "===")
    return ok


if __name__ == "__main__":
    _sys.exit(0 if _selftest() else 1)
