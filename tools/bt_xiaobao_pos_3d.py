#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小鲍仓位风险偏好 · 3日前瞻回测。
i=建议日，看 i→i+3 上证(sh_close)累计涨跌→市场5档(m)；与风偏(rp,1-5)匹配打分(1-5)。
打分：a=rp-3, b=m-3；a==0或b==0→中性3；同向→成功4(两端极端→大成功5)；反向→失败2(两端极端→大失败1)。"""
import sqlite3, statistics, argparse, os

import os as _os
def _docs():  # 向上找 Documents（Mac 与任意 Cowork 沙箱会话都适用，勿写死 /sessions/xxx）
    p=_os.path.dirname(_os.path.abspath(__file__))
    while p!='/':
        if _os.path.basename(p)=='Documents': return p
        p=_os.path.dirname(p)
    return _os.path.expanduser('~/Documents')
RECAP=_os.path.join(_docs(),"Database/烛照九阴/recap.db")
MKT=_os.path.join(_docs(),"Database/Market-Data/market_data.db")
OUT=os.path.dirname(__file__)

# 市场5档阈值（上证3日累计%）
def mkt_score(ret):
    if ret>= 2.5: return 5,"大涨"
    if ret>= 0.7: return 4,"涨"
    if ret> -0.7: return 3,"平"
    if ret> -2.5: return 2,"跌"
    return 1,"大跌"

def match(rp,m):
    a,b=rp-3,m-3
    if a==0 or b==0: return 3,"中性"
    if a*b>0: return (5,"大成功") if (abs(a)==2 and abs(b)==2) else (4,"成功")
    return (1,"大失败") if (abs(a)==2 and abs(b)==2) else (2,"失败")

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--commit",action="store_true"); A=ap.parse_args()
    # 上证日序列（recap.db tushare_index 000001.SH，收盘价齐全）
    m=sqlite3.connect(RECAP)
    idx=[(r[0], r[1]) for r in m.execute("select trade_date,close from tushare_index where ts_code='000001.SH' and close is not null order by trade_date")]
    pos={d:i for i,(d,_) in enumerate(idx)}   # YYYYMMDD -> ordinal
    close=[c for _,c in idx]
    c=sqlite3.connect(RECAP)
    rows=c.execute("select date,position_repr,position_risk_pref,position_band,position_stance,position_conf from dim4_trade_plan where position_risk_pref is not null order by date").fetchall()
    results=[]; rets=[]
    for d,rp_repr,rp,band,stance,conf in rows:
        key=d.replace('-','')
        if key not in pos:
            # 建议日非交易日：取其后第一个交易日为 i
            after=[k for k in pos if k>key]
            if not after: results.append((d,rp,band,None,None,None,None,None,"无行情")); continue
            i=pos[min(after)]
        else:
            i=pos[key]
        if i+3>=len(close):
            results.append((d,rp,band,None,None,None,None,None,"前瞻不足")); continue
        ret=round((close[i+3]/close[i]-1)*100,2)
        rets.append(ret)
        ms,ml=mkt_score(ret); sc,sl=match(rp,ms)
        results.append((d,rp,band,ret,ms,ml,sc,sl,"ok"))
    # 分布
    ok=[r for r in results if r[8]=="ok"]
    print(f"参与回测 {len(ok)} 天 / 共 {len(results)}（剔除前瞻不足/无行情 {len(results)-len(ok)}）")
    print(f"3日上证涨跌 分布: min {min(rets):.2f}  p25 {statistics.quantiles(rets,n=4)[0]:.2f}  中位 {statistics.median(rets):.2f}  p75 {statistics.quantiles(rets,n=4)[2]:.2f}  max {max(rets):.2f}")
    from collections import Counter
    mdist=Counter(r[5] for r in ok); sdist=Counter(r[7] for r in ok)
    print("市场档分布:",{k:mdist[k] for k in ['大涨','涨','平','跌','大跌']})
    print("匹配档分布:",{k:sdist[k] for k in ['大成功','成功','中性','失败','大失败']})
    succ=sum(sdist[k] for k in ['大成功','成功']); fail=sum(sdist[k] for k in ['失败','大失败'])
    n=len(ok)
    print(f"成功率(4-5): {succ}/{n} = {succ/n*100:.1f}% | 失败率(1-2): {fail}/{n} = {fail/n*100:.1f}% | 中性 {sdist['中性']}")
    avg=statistics.mean(r[6] for r in ok)
    print(f"平均匹配分: {avg:.2f}")
    # 仅看高/中置信
    okc=[r for r in ok if dict((x[0],x[5]) for x in [(rr[0],rr) for rr in []]) or True]
    # 落表
    if A.commit:
        c.execute("drop table if exists bt_xiaobao_pos_3d")
        c.execute("""create table bt_xiaobao_pos_3d(date TEXT, risk_pref INT, band TEXT,
            fwd3_ret REAL, mkt_score INT, mkt_label TEXT, match_score INT, match_label TEXT, note TEXT)""")
        c.executemany("insert into bt_xiaobao_pos_3d values(?,?,?,?,?,?,?,?,?)", results)
        c.commit(); print("已落表 bt_xiaobao_pos_3d")
    # 导出
    hdr="日期\t风偏\t档位\t3日涨跌%\t市场\t匹配分\t匹配档\t备注"
    lines=[hdr]+["\t".join(str(x) if x is not None else "" for x in (r[0],r[1],r[2],r[3],r[5],r[6],r[7],r[8])) for r in results]
    open(os.path.join(OUT,"小鲍仓位回测_3日.tsv"),"w",encoding="utf-8").write("\n".join(lines))
    return results,ok,sdist,mdist,n,succ,fail,avg,rets

if __name__=="__main__": main()
