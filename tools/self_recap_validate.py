#!/usr/bin/env python3
"""自复盘 · 记录校验器（PRD「烛照九阴自复盘取代课件」R3、N1、X1 · 2026-11-17）

校验 data/self_recap/<交易日>/records.json。任何一条不过，退出码 1，不落任何东西。

管三件事：
  1. 每条记录字段齐全，取值在词表内；
  2. 证据只来自独立来源，不指向课件、课件派生表；数值证据带日期；
  3. 已裁定舍弃的东西（均线闸门、成数、成交额阈值、固定天数止损、课件周期与涨停类依据）不出现在判断文字里。

方向词只有四个：可加、宜减、不动、观察。没有幅度。
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import argparse, hashlib, json, re
from pathlib import Path

CARDS = {"卡一", "卡二", "卡三", "卡四", "卡五", "卡六", "卡七"}
ROLES = {"同向印证", "温度计", "反向或替代", "本地确认的测试"}
DIRECTIONS = {"可加", "宜减", "不动", "观察"}
CONFIRM = {"已确认", "未确认", "待确认"}
EVIDENCE_KINDS = {"market_data", "eal", "yuantu", "url", "inputs"}

# 证据与正文都不得指向课件或课件派生表
LESSON_REFS = re.compile(
    r"industry_signals|dim[1234]p?_|recap_daily|recap_guide|recap_summary|processed_kejian|"
    r"Raw-Recap|课件|小鲍|xiaobao|XB-[0-9a-f]{6}", re.I)

# 判断文字里不得出现的舍弃项（证据栏不查：证据可以如实记成交额这类事实）
BANNED = re.compile(
    r"MA\s*60|60\s*日|均线|[0-9一二三四五六七八九十两半]\s*成(?!交|本|为|立|熟|功|长|果|员|分|品|都)|万亿|"
    r"连板|涨停|封板|封单|打板|情绪周期|三日|三天|五天|掉期")

RECORD_FIELDS = ("id", "object", "main_issue", "anchor", "evidence", "change", "direction",
                 "local_confirmation", "priced_in", "invalidation", "next_check")
JUDGEMENT_FIELDS = ("object", "main_issue", "priced_in", "invalidation", "next_check")


def _text(x):
    return x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)


def validate(doc, themes=None, inputs_path=None):
    """返回错误列表；空列表即通过。themes 为允许的主线名集合（None 则不查）。"""
    errs = []
    for k in ("schema_version", "trade_date", "observed_at", "session", "inputs_sha256", "records"):
        if k not in doc:
            errs.append(f"doc: 缺字段 {k}")
    if errs:
        return errs
    if not re.fullmatch(r"\d{8}", str(doc["trade_date"])):
        errs.append("doc.trade_date: 须为 YYYYMMDD")
    if inputs_path is not None:
        p = Path(inputs_path)
        if not p.is_file():
            errs.append(f"doc.inputs_sha256: 找不到输入包 {p}")
        elif hashlib.sha256(p.read_bytes()).hexdigest() != doc["inputs_sha256"]:
            errs.append("doc.inputs_sha256: 与同目录输入包的校验值不符")
    recs = doc["records"]
    if not isinstance(recs, list):
        return errs + ["doc.records: 须为列表"]
    if not recs and not str(doc.get("no_change_note", "")).strip():
        errs.append("doc: 没有记录时必须写 no_change_note，说明当日为何无变化")
    if LESSON_REFS.search(str(doc.get("no_change_note", ""))):
        errs.append("doc.no_change_note: 指向了课件或课件派生表")
    seen = set()
    for i, r in enumerate(recs):
        tag = f"records[{i}]"
        if not isinstance(r, dict):
            errs.append(f"{tag}: 须为对象")
            continue
        for k in RECORD_FIELDS:
            if k not in r or r[k] in (None, "", [], {}):
                errs.append(f"{tag}: 缺字段或为空 {k}")
        if any(e.startswith(tag + ":") for e in errs):
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
                errs.append(f"{tag}.anchor.role: 须为 {sorted(ROLES)} 之一")
        if r["direction"] not in DIRECTIONS:
            errs.append(f"{tag}.direction: 须为 {sorted(DIRECTIONS)} 之一（没有幅度）")
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
            if not e.get("asof"):
                errs.append(f"{et}: 缺 asof（证据的日期或时刻）")
            if e["kind"] == "url" and not re.match(r"https?://", str(e["ref"])):
                errs.append(f"{et}: kind=url 时 ref 须为网址")
            if LESSON_REFS.search(_text(e)):
                errs.append(f"{et}: 指向了课件或课件派生表")
        for k in JUDGEMENT_FIELDS:
            s = _text(r[k])
            if LESSON_REFS.search(s):
                errs.append(f"{tag}.{k}: 指向了课件或课件派生表")
            m = BANNED.search(s)
            if m:
                errs.append(f"{tag}.{k}: 出现已舍弃的写法「{m.group(0)}」")
        for k, s in (("anchor", _text(a)), ("change", _text(ch)), ("local_confirmation", _text(lc))):
            if LESSON_REFS.search(s):
                errs.append(f"{tag}.{k}: 指向了课件或课件派生表")
            m = BANNED.search(s)
            if m:
                errs.append(f"{tag}.{k}: 出现已舍弃的写法「{m.group(0)}」")
    return errs


def main():
    ap = argparse.ArgumentParser(description="校验自复盘记录")
    ap.add_argument("records", type=Path, help="records.json 路径")
    a = ap.parse_args()
    doc = json.loads(a.records.read_text(encoding="utf-8"))
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
    print(f"通过：{len(doc['records'])} 条记录，交易日 {doc['trade_date']}")


if __name__ == "__main__":
    main()
