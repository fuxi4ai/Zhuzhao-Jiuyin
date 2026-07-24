"""S2 计温 function · 单一真源（触发层 × 环境层）

PRD: brain/logs/checkpoints/2026-07-19_S2计温function重构_PRD.md
设计参考: docs/S2温度卡设计参考_20260719.html

生产端 gen_daily_report.py 与回测端 calibrate_risk_factors.py 共用本模块——
两端口径强制一致（G-X73：只改一端，校准报告会拿生产里不存在的判据出数）。

结构（Doctor 2026-07-19 四拍板）:
  触发层 T = F4(IPO虹吸) OR F5(油价急涨)      —— 事件型，决定"有没有警"
  环境层 E = count(F1外盘, A6量能, B6集中度)   —— 状态型，决定"警多重"
  T=0            -> calm  平静（环境灯照常显示，不定级）
  T>0 且 E=0     -> alert 触发·无共振（历史该态未现冰点）
  T>0 且 E>=1    -> resonance 共振N（灯数入文案，不另分档）

实证依据（研究快照 2026-07-19, bt_combo.py 三环境块 F1/A6/B6; 以校准端实算为准）:
  触发×环境0盏 = 0/24 冰点(fwd3 +1.64%) · 触发×环境>=1盏 = 3/20（关键格2盏 3/10=30%）
  （二环境块 A6/B6 为 0/31·3/13，另见 combo_out.txt；20260719 复核订正误引）
  A6 双尾（冰点x2.06 且暴涨x2.2, 53事件）——禁作看空计温, 只当环境;
  B6 lift 2.20(24事件); 两者有效性锁 2020s 区制（区制条款见 config a6/b6.desc）。

纯 python + sqlite3, 只读, 无第三方依赖。
"""
import json
import sqlite3
from bisect import insort, bisect_left

WINDOW = 252          # 滚动分位窗（交易日）
MIN_PERIODS = 200     # 分位可评最少样本
F1_MAX_AGE_DAYS = 5   # B4 后半句（PRD 2026-07-19·20260719 复核补丁）：外盘场次距数据日
                      # 超此日历日数 → F1 不可评（断更时不得继续参与共振判定，ERR-20260719-002 同族）


def calendar_gap(d_a, d_b):
    """YYYYMMDD 字符串日历日差 |d_a - d_b|。任一为 None/坏格式 → None（调用方按不可评处理）。
    生产端与回测端共用（G-X73：陈旧判定不得两端各写一份）。"""
    import datetime as _dt
    try:
        a = _dt.date(int(d_a[:4]), int(d_a[4:6]), int(d_a[6:8]))
        b = _dt.date(int(d_b[:4]), int(d_b[4:6]), int(d_b[6:8]))
    except (TypeError, ValueError):
        return None
    return abs((a - b).days)


def resolve_temp(trigger_n, env_hits, env_evaluable, version="s2"):
    """三态映射（仅 s2；v1 分支由调用方保留旧逻辑）。
    返回 (state_key, label)。state_key ∈ calm/alert/resonance（对齐 config temp_states）。
    B3 纪律：环境层可评盏数如实入分母；全不可评时不得默认按 0 盏处理成"无共振"。"""
    if version != "s2":
        raise ValueError("resolve_temp 仅服务 s2；v1 请走调用方旧逻辑分支")
    if trigger_n <= 0:
        return "calm", "平静"
    if env_evaluable <= 0:
        return "alert", "触发·环境层不可评"
    if env_hits <= 0:
        return "alert", "触发·无共振"
    suffix = f"/{env_evaluable}" if env_evaluable < 3 else ""
    return "resonance", f"共振{env_hits}{suffix}"


def f4_ratio_trigger(funds_win, avg_turnover, cfg):
    """F4 IPO 虹吸触发（相对口径·单一真源，G-X73：生产端 gen_daily_report 与回测端 calibrate 共用）。
    口径：滚动 raise_win_days 日历日募资合计（funds_win，亿）÷ 近 turnover_avg_days 交易日
    日均全市场成交额（avg_turnover，亿）≥ ratio_th → 触发。语义＝「IPO 抽走≈几天成交额」。
    2026-07-23 由绝对 funds_win_th(200亿) 换相对（选型B·p95·2020-02→2026 校准 lift2.68/14事件·
    Q6过[低成交额alone lift0]·跨4年散布；见 docs/五因回测校准_F4相对_20260723.md）。旧绝对键降级留注、可回滚。
    数据不足（募资或成交额缺）→ None（不可评，绝不当"未触发"·G-X75）。"""
    if funds_win is None or avg_turnover is None or avg_turnover <= 0:
        return None
    return bool(funds_win / avg_turnover >= float(cfg.get("ratio_th", 0.045)))


def _rolling_pct(dates, values, window=WINDOW, min_periods=MIN_PERIODS):
    """逐日滚动分位: pct[d] = 窗内 <= 当日值的占比。有序插入维护窗口，O(N·logW+N·W/删)。
    返回 {date: pct(0..1)}。前 min_periods-1 日不可评（不入结果）。"""
    out = {}
    win = []          # sorted values
    buf = []          # fifo of values（与 dates 对齐）
    for d, v in zip(dates, values):
        if v is None:
            continue
        insort(win, v)
        buf.append(v)
        if len(buf) > window:
            old = buf.pop(0)
            win.pop(bisect_left(win, old))
        if len(buf) >= min_periods:
            # <= v 的占比（含自身，与研究口径 (x<=x[-1]).mean() 一致）
            import bisect as _b
            out[d] = _b.bisect_right(win, v) / len(win)
    return out


def a6_percentiles(index_db, code="399006.SZ", window=WINDOW, min_periods=MIN_PERIODS):
    """A6 量能: 创业板成交额滚动分位全序列。
    数据源 index_research.db（adjustment_grade --update 日更维护）。
    返回 ({date: pct}, last_date)。库缺/表缺返回 ({}, None) —— 调用方按不可评处理。"""
    try:
        db = sqlite3.connect(f"file:{index_db}?mode=ro", uri=True)
        rows = db.execute(
            "SELECT trade_date, amount FROM index_daily "
            "WHERE ts_code=? AND amount IS NOT NULL ORDER BY trade_date", (code,)).fetchall()
        db.close()
    except sqlite3.OperationalError:
        return {}, None
    if not rows:
        return {}, None
    dates = [r[0] for r in rows]
    vals = [r[1] for r in rows]
    return _rolling_pct(dates, vals, window, min_periods), dates[-1]


def b6_percentiles(market_db, universe_path, top_frac=0.05,
                   window=WINDOW, min_periods=MIN_PERIODS):
    """B6 集中度: 729 固定宇宙 top{top_frac} 个股成交额占比 的滚动分位全序列。
    锁固定宇宙＝ERR-20260719-001 防线（stock_daily 2026-06-03 扩容，跨期截面必须锁池）。
    方案甲（Doctor 批 2026-07-19）: 每次全量重算，零缓存零新日更链，天然幂等。
    返回 ({date: pct}, last_date, share_last)。"""
    try:
        uni = json.load(open(universe_path, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}, None, None
    if not uni:
        return {}, None, None
    try:
        db = sqlite3.connect(f"file:{market_db}?mode=ro", uri=True)
        ph = ",".join("?" * len(uni))
        rows = db.execute(
            f"SELECT trade_date, amount FROM stock_daily "
            f"WHERE ts_code IN ({ph}) AND amount IS NOT NULL ORDER BY trade_date",
            list(uni)).fetchall()
        db.close()
    except sqlite3.OperationalError:
        return {}, None, None
    if not rows:
        return {}, None, None
    # 逐日聚合 top5% 占比（宇宙内当日有数的个股参与；k 按当日样本数取整，至少 1）
    by_day, cur_d, cur_v = {}, None, []
    for d, a in rows:
        if d != cur_d:
            if cur_d is not None and cur_v:
                by_day[cur_d] = cur_v
            cur_d, cur_v = d, []
        cur_v.append(a)
    if cur_d is not None and cur_v:
        by_day[cur_d] = cur_v
    dates, shares = [], []
    for d in sorted(by_day):
        v = by_day[d]
        if len(v) < 50:        # 当日截面过稀（宇宙覆盖不足）不计入
            continue
        v.sort(reverse=True)
        k = max(1, int(len(v) * top_frac))
        tot = sum(v)
        if tot <= 0:
            continue
        dates.append(d)
        shares.append(sum(v[:k]) / tot)
    if not dates:
        return {}, None, None
    return (_rolling_pct(dates, shares, window, min_periods),
            dates[-1], shares[-1])
