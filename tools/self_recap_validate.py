#!/usr/bin/env python3
"""自复盘 · 记录校验器（PRD「烛照九阴自复盘取代课件」R3、N1、N2、X1 · 2026-11-17）

校验 data/self_recap/<交易日>/records.json。任何一条不过，退出码 1，不落任何东西。

管四件事：
  1. 每条记录字段齐全，取值在词表内；
  2. 日期、时刻、数值是真的：交易日是真实日期，写记录的时刻带时区，证据的日期不晚于写记录的时刻，
     数值不是 NaN 或无穷大，记录绑定的输入包就是同一交易日的那一份；
  3. 证据只来自独立来源：行情库的行情表、同目录输入包、网址，不指向课件、课件派生表、复盘库；
  4. 已裁定舍弃的东西（均线闸门、成数与仓位百分比、成交额阈值、固定天数止损、课件周期与涨停类依据）
     不出现在记录的任何文字里——包括证据的备注、local_only、no_change_note。

方向词只有四个：可加、宜减、不动、观察。没有幅度。

边界：第 4 项按字面拦常见写法，拦不住所有改写。校验通过只说明格式与来源合规，
不说明证据足以支撑判断；那一步要人读。（V.V. 2026-11-17 复核 · EAL 工作日志）
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import argparse, datetime, hashlib, json, math, re, unicodedata
from pathlib import Path

SCHEMA_VERSION = 2          # 1 是 2026-11-17 复核前的写法，本版不校验
INPUT_SCHEMAS = {1, 2}
SESSIONS = {"盘后"}
CARDS = {"卡一", "卡二", "卡三", "卡四", "卡五", "卡六", "卡七"}
# 锚相对对象的关系。「本地确认」是流程里的一步（local_confirmation 字段），不是锚的角色
ROLES = {"同向印证", "温度计", "反向或替代", "事件或预期"}
DIRECTIONS = {"可加", "宜减", "不动", "观察"}
CONFIRM = {"已确认", "未确认", "待确认"}
EVIDENCE_KINDS = {"market_data", "eal", "yuantu", "url", "inputs"}
BODY_READ = {"已读正文", "仅标题"}
UNKNOWN = "未核"
# 传导链与商业暴露核到什么程度。「不适用」只给温度计：它与对象没有直接商业关系
TRANSMISSION = {"已核", "部分已核", "未核", "不适用"}
# 完备度。锚跟随技能还有第三档「具备执行条件」，要入场价格、仓位依据与账户约束，
# Doctor 裁定自复盘只提示方向，所以这里没有那一档
STAGES = {"观察", "条件草案"}
CARRY_OUTCOMES = {"已结", "搁置"}

# 行情库里可以当证据引用的表。涨停名单、新股表不在内
MARKET_TABLES = {"daily_market", "theme_etf_daily", "us_anchor_daily", "intl_index_daily", "cn_index_daily",
                 "market_amount_daily", "stock_daily", "fred_ust_daily", "cn_liquidity_daily",
                 "cn_macro_monthly", "margin_daily", "margin_guarantee_ratio", "north_flow", "trade_cal"}

# 任何文字都不得指向课件、课件派生表或复盘库（复盘库里的表都在课件线上，见 docs/2026-11-17-课件依赖清单.md）
LESSON_REFS = re.compile(
    r"recap\.db|industry_signals|dim[1234]p?_|recap_daily|recap_guide|recap_summary|processed_kejian|"
    r"hot_sectors|information_gap|cycle_comparison|cycle_quant|bt_xiaobao|xiaobao_echo|stock_tracking|"
    r"raw-recap|课件|小鲍|xiaobao|xb-[0-9a-f]{6}")

_N = r"(?:\d+(?:\.\d+)?|[一二两三四五六七八九十半]+)"
_SEP = r"[^，。；,;]"
_CMP = r"(?:低于|高于|不足|超过|跌破|突破|站上|站稳|小于|大于|达到|回到|降到|升到|[<>≤≥])"
_EXIT = r"(?:止损|止盈|退出|离场|清仓|出局|则撤|就撤|则退|就退|即撤|即退)"
# 已舍弃的写法。匹配前先把全角转半角、转小写、去掉空白
_BANNED_COMMON = [
    r"ma-?60|60日|六十日|60天线|均线|年线|半年线|季线",                                  # 均线闸门
    _N + r"成(?!交|本|为|立|熟|功|长|果|员|分|品|都)|半仓|满仓|空仓|重仓|轻仓",          # 成数
    r"仓位" + _SEP + r"{0,10}\d+(?:\.\d+)?%|\d+(?:\.\d+)?%" + _SEP + r"{0,6}仓位|[加减]仓(?:到|至)?" + _N,   # 仓位百分比
    # 固定天数止损。「下一交易日」「当日」「11月16日」这类不是天数；「20日超额」「5日涨幅」是读数窗口
    r"(?<![\d.一二两三四五六七八九十半下前上同当次每第月])" + _N + r"个?(?:交易)?[日天](?!超额|涨|跌|累计|窗口|收益|均|线|前|新高|新低|的)"
    r"(?:内|之内|以内)?" + _SEP + r"{0,10}" + _EXIT,
    r"(?<![\d.一二两三四五六七八九十半下前上同当次每第月])" + _N + r"个?(?:交易)?[日天](?:内|之内|以内)?(?:不涨|不跌|未涨|没涨|不反弹|不修复|不收回|收不回|不创新高)",
    r"三日|三天|五天",
    r"连板|涨停|跌停|封板|封单|打板|炸板|情绪周期|掉期",
]
# 成交额阈值：判断文字里不得出现；证据里可以如实记成交额的数字与前后比较
_BANNED_AMOUNT = [
    r"(?:成交额|成交量|量能|两市成交)" + _SEP + r"{0,16}" + _CMP,
    _CMP + _SEP + r"{0,8}\d[\d.]*万?亿",
    r"万亿",
]
BANNED = re.compile("|".join(_BANNED_COMMON + _BANNED_AMOUNT))
BANNED_IN_EVIDENCE = re.compile("|".join(_BANNED_COMMON))

TOP_FIELDS = ("schema_version", "trade_date", "observed_at", "session", "inputs_sha256", "blind", "records")
RECORD_FIELDS = ("id", "object", "main_issue", "anchor", "evidence", "transmission", "change", "direction",
                 "stage", "local_confirmation", "priced_in", "invalidation", "next_check", "prior")
# 这些键的值是引用或时间，不查舍弃词（课件引用照查）
_REF_KEYS = {"ref", "asof", "first_public_at", "inputs_sha256", "observed_at", "trade_date"}
# 盲写说明里要提到课件（「在看课件之前写成」），这一处不查课件引用
_LESSON_EXEMPT_KEYS = {"blind_note"}


def _norm(s):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", s)).lower()


def _walk(x, path="doc", key=None):
    """逐个给出 (路径, 所在键, 值)，值为字符串或数值。"""
    if isinstance(x, dict):
        for k, v in x.items():
            yield from _walk(v, f"{path}.{k}", k)
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from _walk(v, f"{path}[{i}]", key)
    else:
        yield path, key, x


def _parse_when(s):
    """日期或时刻 → (date, datetime 或 None)。认 YYYYMMDD、YYYY-MM-DD、带时区的 ISO 时刻。认不出返回 None。"""
    if not isinstance(s, str):
        return None
    s = s.strip()
    try:
        if re.fullmatch(r"\d{8}", s):
            return datetime.datetime.strptime(s, "%Y%m%d").date(), None
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            return datetime.date.fromisoformat(s), None
        t = datetime.datetime.fromisoformat(s[:-1] + "+00:00" if s.endswith(("Z", "z")) else s)
    except ValueError:
        return None
    if t.tzinfo is None:
        return None
    return t.astimezone(datetime.timezone.utc).date(), t


def _not_after(when, limit):
    """when 是否不晚于 limit（都是 _parse_when 的结果；limit 带时刻）。只有日期的，按日期比，放宽一天以容时区。"""
    d, t = when
    if t is not None:
        return t <= limit[1]
    return d <= limit[0] + datetime.timedelta(days=1)


def _load_json_strict(text):
    def bad(c):
        raise ValueError(f"数值 {c} 不是有限数")
    return json.loads(text, parse_constant=bad)


def previous_period(root, trade_date):
    """root 下早于 trade_date、离它最近、且有 records.json 的那一期。返回 (日期, 该期记录 id 的集合)；没有则 (None, set())。
    只读 id，不管那一期是哪个版本的格式。"""
    root = Path(root)
    days = sorted((d.name for d in root.iterdir() if d.is_dir() and re.fullmatch(r"\d{8}", d.name)
                   and d.name < str(trade_date) and (d / "records.json").is_file()), reverse=True) if root.is_dir() else []
    for day in days:
        try:
            doc = json.loads((root / day / "records.json").read_text(encoding="utf-8"))
            return day, {str(r["id"]) for r in doc.get("records", []) if isinstance(r, dict) and r.get("id")}
        except (ValueError, OSError, TypeError):
            return day, None          # 上一期读不出来：交给调用方报错，不往更早找
    return None, set()


def _check_carry(doc, recs, root, errs):
    """上一期的每条记录都要有去向：被本期某条记录的 prior.ref 接上，或写进顶层 carried_over。"""
    day, prev_ids = previous_period(root, doc["trade_date"])
    refs = {str(r["prior"]["ref"]) for r in recs
            if isinstance(r, dict) and isinstance(r.get("prior"), dict) and r["prior"].get("ref")}
    carried = {str(c["ref"]) for c in doc.get("carried_over") or [] if isinstance(c, dict) and c.get("ref")}
    if prev_ids is None:
        errs.append(f"doc: 上一期 {day} 的记录读不出来，无法核对承接")
        return
    for x in sorted((refs | carried) - prev_ids):
        errs.append(f"doc: 引用的上一期记录 {x} 不存在" + (f"（上一期是 {day}）" if day else "（没有上一期）"))
    for x in sorted(prev_ids - refs - carried):
        errs.append(f"doc: 上一期 {day} 的记录 {x} 没有去向——用某条记录的 prior.ref 接上，或写进 carried_over")
    for x in sorted(refs & carried):
        errs.append(f"doc.carried_over: {x} 已被本期记录接上，不要再列为已结或搁置")


def validate(doc, themes=None, inputs_path=None):
    """返回错误列表；空列表即通过。themes 为允许的主线名集合（None 则不查）。
    给了 inputs_path 时，还会到它上一级目录里找上一期记录，核对承接。"""
    errs = []
    if not isinstance(doc, dict):
        return ["doc: 须为对象"]
    for k in TOP_FIELDS:
        if k not in doc:
            errs.append(f"doc: 缺字段 {k}")
    if errs:
        return errs
    if doc["schema_version"] != SCHEMA_VERSION or isinstance(doc["schema_version"], bool):
        return [f"doc.schema_version: 本校验器只认 {SCHEMA_VERSION}（见 docs/自复盘-记录写法.md）"]
    if doc["session"] not in SESSIONS:
        errs.append(f"doc.session: 须为 {sorted(SESSIONS)} 之一")
    if not isinstance(doc["blind"], bool):
        errs.append("doc.blind: 须为 true 或 false（是否在看课件之前写成）")
    elif doc["blind"] is False and not str(doc.get("blind_note", "")).strip():
        errs.append("doc.blind_note: 非盲写时必须说明原因")
    td = _parse_when(doc["trade_date"]) if re.fullmatch(r"\d{8}", str(doc["trade_date"])) else None
    if td is None:
        errs.append("doc.trade_date: 须为真实日期，写成 YYYYMMDD")
    obs = _parse_when(doc["observed_at"])
    if obs is None or obs[1] is None:
        errs.append("doc.observed_at: 须为带时区的时刻，如 2026-11-17T08:00:00+00:00")
        obs = None
    elif td is not None and obs[0] < td[0]:
        errs.append("doc.observed_at: 早于交易日，盘后记录不可能在当日之前写成")
    for path, key, v in _walk(doc):
        if isinstance(v, float) and not math.isfinite(v):
            errs.append(f"{path}: 数值不是有限数")
    if inputs_path is not None:
        p = Path(inputs_path)
        if not p.is_file():
            errs.append(f"doc.inputs_sha256: 找不到输入包 {p}")
        else:
            raw = p.read_bytes()
            if hashlib.sha256(raw).hexdigest() != doc["inputs_sha256"]:
                errs.append("doc.inputs_sha256: 与同目录输入包的校验值不符")
            else:
                try:
                    pack = _load_json_strict(raw.decode("utf-8"))
                except (ValueError, UnicodeDecodeError) as e:
                    pack = None
                    errs.append(f"doc.inputs_sha256: 输入包读不出来（{e}）")
                if pack is not None:
                    if not isinstance(pack, dict) or pack.get("kind") != "self_recap_inputs":
                        errs.append("doc.inputs_sha256: 绑定的文件不是自复盘输入包")
                    elif pack.get("schema_version") not in INPUT_SCHEMAS:
                        errs.append(f"doc.inputs_sha256: 输入包的 schema_version 不在 {sorted(INPUT_SCHEMAS)} 内")
                    elif str(pack.get("trade_date")) != str(doc["trade_date"]):
                        errs.append(f"doc.trade_date: 与输入包的交易日 {pack.get('trade_date')} 不一致")
    recs = doc["records"]
    if not isinstance(recs, list):
        return errs + ["doc.records: 须为列表"]
    co = doc.get("carried_over", [])
    if not isinstance(co, list):
        errs.append("doc.carried_over: 须为列表")
    else:
        for i, c in enumerate(co):
            if (not isinstance(c, dict) or not c.get("ref") or c.get("outcome") not in CARRY_OUTCOMES
                    or not str(c.get("note", "")).strip()):
                errs.append(f"doc.carried_over[{i}]: 须含 ref、outcome（{sorted(CARRY_OUTCOMES)}）与 note")
    if inputs_path is not None and td is not None:
        _check_carry(doc, recs, Path(inputs_path).parent.parent, errs)
    if not recs and not str(doc.get("no_change_note", "")).strip():
        errs.append("doc: 没有记录时必须写 no_change_note，说明当日为何无变化")

    # 课件引用与舍弃词：整份文件的每一段文字都查，不留旁路
    for path, key, v in _walk(doc):
        if not isinstance(v, str) or not v:
            continue
        n = _norm(v)
        if key not in _LESSON_EXEMPT_KEYS and LESSON_REFS.search(n):
            errs.append(f"{path}: 指向了课件、课件派生表或复盘库")
        if key in _REF_KEYS:
            continue
        m = (BANNED_IN_EVIDENCE if ".evidence[" in path else BANNED).search(n)
        if m:
            errs.append(f"{path}: 出现已舍弃的写法「{m.group(0)}」")

    seen = set()
    for i, r in enumerate(recs):
        tag = f"records[{i}]"
        if not isinstance(r, dict):
            errs.append(f"{tag}: 须为对象")
            continue
        missing = [k for k in RECORD_FIELDS if k not in r or r[k] in (None, "", [], {})]
        if missing:
            errs.extend(f"{tag}: 缺字段或为空 {k}" for k in missing)
            continue
        tag = f"records[{i}]({r['id']})"
        if r["id"] in seen:
            errs.append(f"{tag}: id 重复")
        seen.add(r["id"])
        a = r["anchor"]
        if not isinstance(a, dict) or not a.get("name"):
            errs.append(f"{tag}.anchor: 须含 name")
        else:
            if a.get("card") not in CARDS:
                errs.append(f"{tag}.anchor.card: 须为 {sorted(CARDS)} 之一")
            if a.get("role") not in ROLES:
                errs.append(f"{tag}.anchor.role: 须为 {sorted(ROLES)} 之一（本地确认写在 local_confirmation，不是锚的角色）")
        if r["direction"] not in DIRECTIONS:
            errs.append(f"{tag}.direction: 须为 {sorted(DIRECTIONS)} 之一（没有幅度）")
        tr = r["transmission"]
        if (not isinstance(tr, dict) or not str(tr.get("chain", "")).strip() or not str(tr.get("exposure", "")).strip()
                or tr.get("status") not in TRANSMISSION):
            errs.append(f"{tag}.transmission: 须含 chain（传导链）、exposure（商业暴露）与 status（{sorted(TRANSMISSION)}）")
            tr = None
        elif tr["status"] == "不适用" and isinstance(a, dict) and a.get("role") != "温度计":
            errs.append(f"{tag}.transmission.status: 「不适用」只用于温度计；其余角色没核到就写「未核」")
        elif tr["status"] == "未核" and r["direction"] == "可加":
            errs.append(f"{tag}: 传导与商业暴露未核时方向不得为「可加」")
        if r["stage"] not in STAGES:
            errs.append(f"{tag}.stage: 须为 {sorted(STAGES)} 之一")
        elif r["stage"] == "观察" and r["direction"] in ("可加", "宜减"):
            errs.append(f"{tag}: 给了「{r['direction']}」就不是观察，stage 写「条件草案」并在 stage_basis 里写明条件")
        elif r["stage"] == "条件草案" and not str(r.get("stage_basis", "")).strip():
            errs.append(f"{tag}.stage_basis: 条件草案须写明方向依赖哪些可观察的条件、还差什么")
        elif r["stage"] == "条件草案" and r["direction"] == "观察":
            errs.append(f"{tag}: 方向为「观察」时 stage 写「观察」")
        pr = r["prior"]
        if not isinstance(pr, dict) or "ref" not in pr or not str(pr.get("carry", "")).strip():
            errs.append(f"{tag}.prior: 须含 ref（上一期记录的 id，没有写 null）与 carry（上一期留下的事项这一期怎样了）")
        lc = r["local_confirmation"]
        if not isinstance(lc, dict) or lc.get("status") not in CONFIRM or not lc.get("basis"):
            errs.append(f"{tag}.local_confirmation: 须含 status（{sorted(CONFIRM)}）与 basis")
        elif r["direction"] == "可加" and lc["status"] != "已确认":
            errs.append(f"{tag}: 本地未确认时方向不得为「可加」")
        ch = r["change"]
        if not isinstance(ch, dict) or not ch.get("baseline") or not ch.get("delta"):
            errs.append(f"{tag}.change: 须含 baseline 与 delta；基线未核写「基线未核」")
        th = r.get("theme")
        if th is not None and themes is not None and th not in themes:
            errs.append(f"{tag}.theme: 不是已登记的主线名；没有对应主线写 null")
        ev = r["evidence"]
        if not isinstance(ev, list):
            errs.append(f"{tag}.evidence: 须为列表")
            ev = []
        for j, e in enumerate(ev):
            et = f"{tag}.evidence[{j}]"
            if not isinstance(e, dict) or e.get("kind") not in EVIDENCE_KINDS or not e.get("ref"):
                errs.append(f"{et}: 须含 kind（{sorted(EVIDENCE_KINDS)}）与 ref")
                continue
            ref = str(e["ref"])
            when = _parse_when(e.get("asof"))
            if not e.get("asof"):
                errs.append(f"{et}: 缺 asof（证据的日期或时刻）")
            elif when is None:
                errs.append(f"{et}.asof: 须为 YYYYMMDD、YYYY-MM-DD 或带时区的时刻")
            elif obs is not None and not _not_after(when, obs):
                errs.append(f"{et}.asof: 晚于写记录的时刻，写记录时还不可能知道")
            if e["kind"] == "market_data":
                m = re.match(r"market_data\.db:([a-z_]+):", ref)
                if not m or m.group(1) not in MARKET_TABLES:
                    errs.append(f"{et}.ref: kind=market_data 时须写成 market_data.db:<行情表>:…，表须在允许清单内")
            elif e["kind"] == "inputs":
                if not ref.startswith("inputs.json:"):
                    errs.append(f"{et}.ref: kind=inputs 时须写成 inputs.json:<块内路径>")
            elif e["kind"] == "url":
                if not re.match(r"https?://[^/\s]+/\S+", ref):
                    errs.append(f"{et}.ref: kind=url 时须为带路径的完整网址（只有站点首页不算）")
                if e.get("body_read") not in BODY_READ:
                    errs.append(f"{et}.body_read: 须为 {sorted(BODY_READ)} 之一")
                fp = e.get("first_public_at")
                if fp != UNKNOWN:
                    w = _parse_when(fp)
                    if w is None or w[1] is None:
                        errs.append(f"{et}.first_public_at: 须为带时区的时刻；不知道就写「{UNKNOWN}」，不要假设已公开")
                    elif obs is not None and w[1] > obs[1]:
                        errs.append(f"{et}.first_public_at: 晚于写记录的时刻")
    return errs


def main():
    ap = argparse.ArgumentParser(description="校验自复盘记录")
    ap.add_argument("records", type=Path, help="records.json 路径")
    a = ap.parse_args()
    try:
        doc = _load_json_strict(a.records.read_text(encoding="utf-8"))
    except ValueError as e:
        print(f"未通过：文件读不出来（{e}）")
        raise SystemExit(1)
    themes = None
    try:
        import config
        _sys.path.insert(0, str(config.PROJECT_ROOT / "scripts"))
        from fetch_theme_etf import THEME_ETF
        themes = set(THEME_ETF)
    except Exception as e:  # 主线词表取不到就不查这一项，但要说出来
        print(f"提示：主线词表未加载（{e}），theme 字段未校验")
    errs = validate(doc, themes, a.records.parent / "inputs.json")
    if errs:
        print(f"未通过：{len(errs)} 处")
        for e in errs:
            print("  -", e)
        raise SystemExit(1)
    print(f"通过：{len(doc['records'])} 条记录，交易日 {doc['trade_date']}（格式与来源合规；证据是否足以支撑判断要人读）")


if __name__ == "__main__":
    main()
