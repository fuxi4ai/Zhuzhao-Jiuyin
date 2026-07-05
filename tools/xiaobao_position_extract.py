#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抽取每日"真·仓位句"——成数/百分比必须紧贴仓位锚词。输出紧凑 bundle 供人工判读。"""
import re, glob, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # 路径单一可信源（G-X45：不再写死 /sessions/xxx 会话 id）

SRC_DIR = os.path.join(str(config.PROJECT_ROOT), "raw", "4-dims")

def fdate(fn):
    b=os.path.basename(fn)
    m=re.match(r'(\d{6})',b)
    if m:
        s=m.group(1); return f"20{s[0:2]}-{s[2:4]}-{s[4:6]}"
    m=re.match(r'(\d{1,2})\.(\d{1,2})',b)
    if m: return f"2025-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return None

# 仓位锚词（句必须含其一才进入候选）
ANCHOR = re.compile(r'(仓位|持仓|空仓|满仓|半仓|轻仓|重仓|建仓|加仓|减仓|降仓|成仓|打满|中性偏多|进可攻|空仓踏空|持币|现金为王)')
# 明确"整体/总体"仓位语境（优先级最高）
OVERALL = re.compile(r'(整体仓位|总仓位|总体仓位|总体.{0,4}仓|建议.{0,4}仓位|仓位控制|仓位管理|仓位策略|仓位铁律|保持.{0,6}仓位|维持.{0,6}仓位|可保持.{0,6}仓|控制在.{0,6}(成|%)|最低可接受仓位|不宜满仓|不要满仓|空仓|满仓|中性偏多)')
# 板块特定（降权）
SECTOR = re.compile(r'(科技股|电池|光模块|储能|锂|煤化|保险|银行|单一(板块|题材|热点)|某板块|该板块|单票|单个方向|单一标的)')

# 成数/百分比 紧贴仓位锚 的窗口判定
FRAC_NEAR = re.compile(
    r'(仓位|持仓|配置|加仓|减仓|建仓|成仓|打满|降至|降到|保持|维持|控制在|提升至|加到|减至|收缩仓位)'
    r'[^，。；、]{0,8}?([一二三四五六七八九两\d]\s*(?:[-到至~]\s*[一二三四五六七八九两\d])?\s*成|\d{1,3}\s*%(?:\s*[-到至~]\s*\d{1,3}\s*%)?)'
)
FRAC_NEAR2 = re.compile(  # 成数在前、仓位在后： "X成仓位" "X成仓"
    r'([一二三四五六七八九两\d]\s*(?:[-到至~]\s*[一二三四五六七八九两\d])?\s*成|\d{1,3}\s*%)\s*(?:左右|以内|以下)?\s*(仓位|仓|持仓|配置)'
)

def sentences(text):
    t=re.sub(r'[ \t]+',' ',text).replace('\n','')
    return [s.strip() for s in re.split(r'(?<=[。！？；])', t) if len(s.strip())>=5]

def has_pos_frac(s):
    return bool(FRAC_NEAR.search(s) or FRAC_NEAR2.search(s) or re.search(r'(半仓|空仓|满仓|轻仓|重仓)',s))

def score(s):
    sc=0
    if OVERALL.search(s): sc+=4
    if has_pos_frac(s): sc+=3
    if re.search(r'(建议|应|需|可|保持|维持|控制|不宜|不要)',s): sc+=1
    if SECTOR.search(s) and not OVERALL.search(s): sc-=3
    if len(s)>130: sc-=1
    return sc

def process(fn):
    text=open(fn,encoding='utf-8',errors='ignore').read()
    cand=[s for s in sentences(text) if ANCHOR.search(s)]
    seen=set(); uniq=[]
    for s in cand:
        if s not in seen: seen.add(s); uniq.append(s)
    ranked=sorted(uniq, key=score, reverse=True)
    top=[s for s in ranked if score(s)>=3][:6] or ranked[:4]
    return {'date':fdate(fn),'source':os.path.basename(fn),'n_anchor':len(uniq),'top':top}

def main():
    files=sorted(glob.glob(os.path.join(SRC_DIR,'*总结*.md')))
    out=[process(fn) for fn in files if fdate(fn)]
    out.sort(key=lambda x:x['date'])
    with open(os.path.join(os.path.dirname(__file__),'pos_bundle.json'),'w',encoding='utf-8') as f:
        json.dump(out,f,ensure_ascii=False,indent=1)
    print('天数:',len(out))
    return out

if __name__=='__main__':
    main()
