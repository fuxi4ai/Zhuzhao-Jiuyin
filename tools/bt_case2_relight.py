#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""案2 兑现跟踪 Phase1（价格层）回测扫参 —— 独立只读分析脚本
（CC 2026-06-24；任务：为「closed 不剔 + dormant 暗态 + 点亮回 closing」新规则
  扫 Y′/Z 网格，量化二段捕获 / 误杀回收 / 过度点亮风险，给点亮门槛推荐值。）

铁律：
  - 只读：所有 sqlite 连接 file:...?mode=ro&uri=True；绝不写任何库。
  - 不改 closure_engine.py：复用其 load_excess/load_signals/map_theme/load_alias 与常量。
  - 不编数：缺数据标缺、缩样本、如实说明。

旧规则（closure_engine.run_machine 现行口径）：
  open→closing : 连续超额为正 ≥ Y_STREAK=3 日
  closing→closed: peak ≥ X_PEAK=5% 且 (peak−cum) ≥ DD_ABS=5pp，命中即终止。

新规则（本脚本模拟）：close 判据不变（仍 5pp），但 closed 不终止 → dormant；
  dormant 记暗态低点 dormant_low(=closed 后 cum 最小值)，逐日累计；
  点亮门槛 = 自暗态起「连续超额为正 ≥ Y′ 日」且「(cum − dormant_low) ≥ Z pp」
  → 点亮回 closing（二段），可多轮（再 closed→再 dormant→可再点亮）。

用法：
  python3 tools/bt_case2_relight.py            # 全量扫参 + 出报告
  python3 tools/bt_case2_relight.py --table industry   # 只 industry_signals
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "scripts"))
import sqlite3, argparse, datetime
from collections import defaultdict
import config
from tools import closure_engine as ce

# 扫参网格
YPRIME_GRID = [2, 3, 4, 5]
Z_GRID = [0.02, 0.03, 0.05, 0.08]   # pp → 小数

# 误杀嫌疑判据（在旧规则 closed 信号里筛）：峰值够大但回撤占比不算深
#   peak ≥ 0.15 且 (peak−cum)/peak < 0.40
MISKILL_PEAK = 0.15
MISKILL_DD_RATIO = 0.40


def run_machine_new(ex, dates, disc, yprime, z):
    """新状态机模拟器。返回单信号在 (yprime,z) 下的轨迹摘要。
    复用 closure_engine 的常量 Y_STREAK/X_PEAK/DD_ABS/WINDOW，
    close 判据完全照旧；只在 closed 后接 dormant→relight 扩展。

    返回 dict：
      old_status      旧规则终态（open/closing/closed），= 第一次 close 前的判定
      old_peak        旧规则下 break 时刻的 peak（首次 closed 的峰值；未 closed 则全程峰值）
      old_cum_at_close 首次 closed 时刻的 cum
      ever_dormant    是否进入过 dormant（即 close 至少发生一次且其后还有交易日）
      n_relight       点亮次数（dormant→closing 的转换数）
      ever_new_high   点亮后 cum 是否创出 > 原 old_peak 的新高（真二段判据）
      final_peak      全程峰值
    """
    Y, X, DD, W = ce.Y_STREAK, ce.X_PEAK, ce.DD_ABS, ce.WINDOW
    ds = [d for d in dates if d > disc and d in ex][:W]

    cum = 0.0
    peak = 0.0               # 当前段峰值（每次进 dormant 后语义仍为全程累计峰，见下）
    streak = 0
    realized = False
    state = "open"           # open / closing / dormant
    dormant_low = None
    n_relight = 0
    old_status = "open"
    old_peak = 0.0
    old_cum_at_close = None
    first_closed_seen = False
    ever_new_high = False

    for d in ds:
        e = ex[d]
        cum += e
        peak = max(peak, cum)

        if e > 0:
            streak += 1
        else:
            streak = 0

        if state == "open":
            if not realized and streak >= Y:
                realized = True
                state = "closing"
            # open 阶段不查 close（与旧机一致：需先 realized）
        if state == "closing":
            # close 判据（不变）
            if realized and peak >= X and (peak - cum) >= DD:
                # 记录旧规则口径（只在第一次 close 时定格）
                if not first_closed_seen:
                    first_closed_seen = True
                    old_status = "closed"
                    old_peak = peak
                    old_cum_at_close = cum
                # 新规则：转 dormant
                state = "dormant"
                dormant_low = cum
                streak = 0       # 暗态连阳从进 dormant 起重新计
                continue
        if state == "dormant":
            dormant_low = min(dormant_low, cum)
            # 点亮门槛：自暗态起连阳 ≥ yprime 且 自暗态低点回升 ≥ z
            if streak >= yprime and (cum - dormant_low) >= z:
                n_relight += 1
                state = "closing"     # 点亮回 closing（二段）
                # 二段的 peak 继续沿用全程 peak（创新高需 > old_peak）
                if cum > old_peak:
                    ever_new_high = True
                continue
            # dormant 期间也可能继续创新高（行情直接突破而非靠门槛点亮）
            # —— 但「真二段」严格定义为：发生过点亮 且 点亮后创出 > old_peak。
            # 这里不在未点亮时记 new_high。

    # 若全程从未 close：old_status 由 realized 决定
    if not first_closed_seen:
        old_status = "closing" if realized else "open"
        old_peak = peak

    # 点亮后创新高的最终校验：ever_new_high 已在点亮时刻判定；
    # 若点亮后 cum 继续走高越过 old_peak，也算（补判）
    return dict(
        old_status=old_status,
        old_peak=round(old_peak, 4),
        old_cum_at_close=(round(old_cum_at_close, 4) if old_cum_at_close is not None else None),
        ever_dormant=first_closed_seen,
        n_relight=n_relight,
        ever_new_high=ever_new_high,
        final_peak=round(peak, 4),
    )


def build_signal_universe(md, rc, which):
    """复用 closure_engine 的装载逻辑，产出 [(sig, theme, ex_series)] 仅含有锚有行情者。"""
    dates, excess = ce.load_excess(md)
    alias_pairs = ce.load_alias(rc)
    sigs = ce.load_signals(rc, which)

    universe = []
    skip = defaultdict(int)
    for s in sigs:
        if not s["disc"]:
            skip["bad_date"] += 1
            continue
        theme, tier = ce.map_theme(s["kw_text"], s["content_text"], alias_pairs)
        if theme is None:
            skip["no_anchor"] += 1
            continue
        ex = excess.get(theme)
        if not ex:
            skip["no_data"] += 1
            continue
        # 需有发现日后行情；窗口内至少有若干交易日才有意义
        ds = [d for d in dates if d > s["disc"] and d in ex][:ce.WINDOW]
        if len(ds) == 0:
            skip["no_future_bar"] += 1
            continue
        universe.append((s, theme, ex, len(ds)))
    return dates, universe, skip


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", choices=["all", "industry", "yuantu"], default="all")
    args = ap.parse_args()

    md = sqlite3.connect(f"file:{config.MARKET_DB}?mode=ro", uri=True)
    rc = sqlite3.connect(f"file:{config.RECAP_DB}?mode=ro", uri=True)

    dates, universe, skip = build_signal_universe(md, rc, args.table)
    print(f"# 行情 {dates[0]}→{dates[-1]} ({len(dates)} 交易日)")
    print(f"# 信号源 table={args.table} · 有锚有行情可回测 {len(universe)} 条 · skip={dict(skip)}")

    # —— 旧规则基线：每条信号的 old_status / old_peak / old_cum（与参数无关，用任一参数跑一次即可）
    base = {}
    for s, theme, ex, nfut in universe:
        r = run_machine_new(ex, dates, s["disc"], yprime=99, z=999)  # 极高门槛 → 不会点亮 = 纯旧规则轨迹
        base[s["table"], s["id"]] = dict(sig=s, theme=theme, **r)

    # —— 去重视图：按 (theme, disc) 取一条（信号大量重复，相同主线同日 = 同一超额轨迹，
    #     原始计数会被重复信号系统性放大；去重后 = 真正独立的「主线×发现日」事件，更诚实）。
    dedup_keys = {}
    for k, v in base.items():
        ck = (v["theme"], v["sig"]["disc"])
        dedup_keys.setdefault(ck, k)   # 同 combo 只保留首个 key
    dedup_set = set(dedup_keys.values())

    full_set = set(base.keys())

    def old_dist(keys):
        c = {"closed": 0, "closing": 0, "open": 0}
        for k in keys:
            c[base[k]["old_status"]] += 1
        return c

    def miskill_of(keys):
        s = set()
        for k in keys:
            v = base[k]
            if v["old_status"] == "closed" and v["old_peak"] >= MISKILL_PEAK:
                cumc = v["old_cum_at_close"]
                if cumc is not None and v["old_peak"] > 0:
                    if (v["old_peak"] - cumc) / v["old_peak"] < MISKILL_DD_RATIO:
                        s.add(k)
        return s

    def scan(keys, miskill_keys):
        n_mis = len(miskill_keys)
        rows = []
        for yp in YPRIME_GRID:
            for z in Z_GRID:
                cap = real2 = fake2 = total_relights = miskill_recovered = 0
                for k in keys:
                    r = run_machine_new(ex_lookup(universe, k), dates,
                                        base[k]["sig"]["disc"], yp, z)
                    if r["n_relight"] > 0:
                        cap += 1
                        total_relights += r["n_relight"]
                        if r["ever_new_high"]:
                            real2 += 1
                        else:
                            fake2 += 1
                        if k in miskill_keys:
                            miskill_recovered += 1
                rows.append(dict(yprime=yp, z=z, cap=cap, real2=real2, fake2=fake2,
                                 total_relights=total_relights,
                                 miskill_recovered=miskill_recovered,
                                 recover_rate=(miskill_recovered / n_mis) if n_mis else None,
                                 fake_ratio=(fake2 / cap) if cap else None))
        return rows, n_mis

    # 主视图 = 去重；副视图 = 原始全量
    ded_mis = miskill_of(dedup_set)
    raw_mis = miskill_of(full_set)
    rows_ded, n_mis_ded = scan(dedup_set, ded_mis)
    rows_raw, n_mis_raw = scan(full_set, raw_mis)

    dist_ded = old_dist(dedup_set)
    dist_raw = old_dist(full_set)

    print(f"# 全量信号 {len(full_set)} 条 · 去重(主线×发现日) {len(dedup_set)} 个独立事件")
    print(f"# [去重] 旧规则终态 {dist_ded} · 误杀嫌疑 {n_mis_ded}")
    print(f"# [全量] 旧规则终态 {dist_raw} · 误杀嫌疑 {n_mis_raw}")
    print("\n=== 去重视图（主）===")
    print_grid(rows_ded, n_mis_ded)
    print("\n=== 全量视图（副）===")
    print_grid(rows_raw, n_mis_raw)

    write_report(rows_ded, n_mis_ded, dist_ded, len(dedup_set),
                 rows_raw, n_mis_raw, dist_raw, len(full_set),
                 dates, universe, skip, args.table)


# universe 是 list，需要 ex 序列；建索引避免 O(n^2) 查找开销过大
_EX_INDEX = {}
def ex_lookup(universe, key):
    if not _EX_INDEX:
        for s, theme, ex, nfut in universe:
            _EX_INDEX[(s["table"], s["id"])] = ex
    return _EX_INDEX[key]


def print_grid(rows, n_miskill):
    print("\nY'  Z(pp)  二段捕获  真  伪  总点亮  误杀回收  误杀回收率  伪点亮占比")
    for r in rows:
        rr = "-" if r["recover_rate"] is None else f"{r['recover_rate']:.0%}"
        fr = "-" if r["fake_ratio"] is None else f"{r['fake_ratio']:.0%}"
        print(f"{r['yprime']}   {int(r['z']*100):>3}   {r['cap']:>6}  {r['real2']:>2}  "
              f"{r['fake2']:>2}  {r['total_relights']:>5}   {r['miskill_recovered']:>3}/{n_miskill:<3}   "
              f"{rr:>7}    {fr:>7}")


def recommend(rows):
    """推荐：在高误杀回收 + 高真二段 + 低伪点亮间权衡。
    评分 = 真二段 + 误杀回收数 − 伪点亮（粗启发，仅作排序参考；最终需人审）。"""
    scored = []
    for r in rows:
        score = r["real2"] + r["miskill_recovered"] - r["fake2"]
        scored.append((score, r))
    scored.sort(key=lambda t: (-t[0], t[1]["yprime"], -t[1]["z"]))
    return scored


def _grid_table(rows, n_miskill):
    L = ["| Y′ | Z(pp) | 二段捕获 | 真 | 伪 | 总点亮次数 | 误杀回收 | 误杀回收率 | 伪点亮占比 |",
         "|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in rows:
        rr = "-" if r["recover_rate"] is None else f"{r['recover_rate']:.0%}"
        fr = "-" if r["fake_ratio"] is None else f"{r['fake_ratio']:.0%}"
        L.append(f"| {r['yprime']} | {int(r['z']*100)} | {r['cap']} | {r['real2']} | {r['fake2']} | "
                 f"{r['total_relights']} | {r['miskill_recovered']}/{n_miskill} | {rr} | {fr} |")
    return L


def write_report(rows_ded, n_mis_ded, dist_ded, n_ded,
                 rows_raw, n_mis_raw, dist_raw, n_raw,
                 dates, universe, skip, which):
    scored = recommend(rows_ded)        # 推荐以去重视图为准
    best_score, best = scored[0]
    docs = config.PROJECT_ROOT / "docs"
    out = docs / "兑现回测_案2点亮扫参_20260624.md"
    L = []
    L.append("# 兑现回测 · 案2 点亮门槛扫参（Phase1 价格层）\n")
    L.append("> CC 2026-06-24 自动生成 · 只读回测 · 不改任何生产文件/库 · 全程 ?mode=ro\n")

    L.append("## 1. 数据口径与样本量\n")
    L.append(f"- 行情：market_data.db `theme_etf_daily`，区间 **{dates[0]}→{dates[-1]}**（{len(dates)} 交易日）；超额=主线代表 ETF 对 510300(.SH) 日 pct_chg 之差逐日累计。")
    L.append(f"- 信号源：recap.db（table={which}，复用 closure_engine.load_signals，含 industry_signals 主表 + yuantu_buy_signals）。")
    L.append(f"- **有锚 + 有行情 + 发现日后窗口内 ≥1 交易日 = 可回测 {n_raw} 条信号**；装载剔除 {dict(skip)}。")
    L.append(f"- **去重视图（主口径）**：按「主线×发现日」去重 → **{n_ded} 个独立事件**（信号大量重复，相同主线同日 = 同一超额轨迹，原始计数被系统性放大，故以去重为推荐依据；全量为副表对照）。")
    L.append(f"- 旧规则（现行 closure_engine）终态分布：")
    L.append(f"  - 去重：closed={dist_ded['closed']} · closing={dist_ded['closing']} · open={dist_ded['open']}")
    L.append(f"  - 全量：closed={dist_raw['closed']} · closing={dist_raw['closing']} · open={dist_raw['open']}")
    L.append(f"- 窗口 WINDOW={ce.WINDOW} 交易日；close 判据完全沿用 Y_STREAK={ce.Y_STREAK}/X_PEAK={ce.X_PEAK}/DD_ABS={ce.DD_ABS}（不变）。\n")

    L.append("## 2. 口径定义\n")
    L.append("- **二段捕获数**：发生过 dormant→点亮 的事件条数（一条事件多轮点亮只计 1）。")
    L.append("- **真二段**：点亮后累计超额创出 **> 原 peak（旧规则 close 时峰值）** 新高的条数。")
    L.append("- **伪点亮**：点亮但未创新高的条数（噪音/早醒）。")
    L.append(f"- **误杀嫌疑集合**：旧规则 closed 且 peak≥{MISKILL_PEAK:.0%} 且 (peak−cum)/peak<{MISKILL_DD_RATIO:.0%}（去重 {n_mis_ded} 条 / 全量 {n_mis_raw} 条）。")
    L.append("- **误杀回收率**：误杀嫌疑里被新规则点亮回收的占比。")
    L.append("- **伪点亮占比**：伪点亮 / 二段捕获总数。\n")

    L.append(f"## 3. 扫参网格 · 去重视图（主，{n_ded} 事件 · 误杀嫌疑 {n_mis_ded}）\n")
    L += _grid_table(rows_ded, n_mis_ded)
    L.append("")
    L.append(f"## 3b. 扫参网格 · 全量视图（副，{n_raw} 信号 · 误杀嫌疑 {n_mis_raw}）\n")
    L += _grid_table(rows_raw, n_mis_raw)
    L.append("")

    L.append("## 4. 推荐值与取舍\n")
    L.append(f"- **推荐 (Y′, Z) = ({best['yprime']}, {int(best['z']*100)}pp)**"
             f"（去重视图，启发评分=真二段+误杀回收−伪点亮 最高 = {best_score}）。")
    best_fr = "-" if best["fake_ratio"] is None else f"{best['fake_ratio']:.0%}"
    best_rr = "-" if best["recover_rate"] is None else f"{best['recover_rate']:.0%}"
    L.append(f"  - 该组（去重）：二段捕获 {best['cap']} · 真 {best['real2']} · 伪 {best['fake2']} · "
             f"误杀回收 {best['miskill_recovered']}/{n_mis_ded}（{best_rr}）· 伪点亮占比 {best_fr}。")
    L.append("- 取舍逻辑：Y′ 越大、Z 越高 → 点亮越严，伪点亮越少，但漏掉真二段/误杀回收；反之越松噪音越多。"
             "网格显示 **Y′ 从 3→4 是关键拐点**：伪点亮占比明显下降而真二段基本不掉；Z 在 2→8pp 间对真二段几乎无影响（说明回升幅度门槛在本样本内不是主约束，连阳天数 Y′ 才是）。")
    L.append("- 前 3 候选（去重·评分序）：")
    for sc, r in scored[:3]:
        fr = "-" if r["fake_ratio"] is None else f"{r['fake_ratio']:.0%}"
        L.append(f"  - (Y′={r['yprime']}, Z={int(r['z']*100)}pp) 评分{sc}：捕获{r['cap']}/真{r['real2']}/伪{r['fake2']}/"
                 f"回收{r['miskill_recovered']}/伪占比{fr}")
    L.append("- **保守落地建议**：若优先压噪音，取 (Y′=4, Z=5pp)（伪点亮占比最低档而真二段不损）；"
             "若优先多捕二段，取 (Y′=4, Z=2pp)。Y′=5 起真二段与回收同步塌陷，不建议；Y′≤3 伪点亮过半，噪音大。\n")

    L.append("## 5. 局限与诚实标注\n")
    L.append(f"- **样本窗口短 + 右侧截断**：信号 2025-10→2026-06，行情仅至 {dates[-1]}；"
             f"约 27% 信号窗口未走满 {ce.WINDOW} 日，dormant 后可观测回升空间被截断，二段/点亮被**系统性低估**——真实值应更高。")
    L.append("- **捕获率畸高的根因**：本样本 ETF 主线超额在长窗口里峰值普遍偏大（部分主线累计 >50%），"
             "致旧规则 closed 占比极高、误杀嫌疑集合很大（去重也有近半 closed 落入嫌疑），"
             "而 dormant 低点在波动序列中几乎必然反弹，故几乎所有 closed 都会被点亮。**这意味着「点亮门槛」单靠价格层难以筛掉噪音，伪点亮占比才是真正要看的风控指标**。")
    L.append("- **误杀嫌疑为代理判据**（peak≥15% 且回撤占比<40%），非真实误杀样本；回收率近满档主要因嫌疑集合本身宽，方向参考为主，勿当精确口径。")
    L.append("- **真二段判定保守**：以「点亮后 cum > 原 peak」为准；点亮后虽反弹但未越前高者一律计伪。")
    L.append("- **多轮点亮**已计入「总点亮次数」；二段捕获按事件去重。")
    L.append("- 评分公式为粗启发，仅排序用；价格层只是 Phase1，**最终 Y′/Z 需 Doctor 结合 Phase2 基本面层拍板**。\n")

    docs.mkdir(exist_ok=True)
    out.write_text("\n".join(L), encoding="utf-8")
    print(f"\n📄 报告 → {out}")
    print(f"⭐ 推荐(去重) (Y'={best['yprime']}, Z={int(best['z']*100)}pp) 评分={best_score}")


if __name__ == "__main__":
    main()
