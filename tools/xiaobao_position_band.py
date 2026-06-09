#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按 position_repr 给仓位分档+风险偏好(5-1)。幂等可重跑。
≥0.7 高/5 ｜ (0.5,0.7) 中高/4 ｜ =0.5 中/3 ｜ [0.3,0.5) 中低/2 ｜ <0.3 低/1"""
import sqlite3, sys
sys.path.insert(0,__file__.rsplit('/',2)[0]); import config
def band(r):
    if r is None: return (None,None)
    if r>=0.7: return ("高",5)
    if r>0.5:  return ("中高",4)
    if r==0.5: return ("中",3)
    if r>=0.3: return ("中低",2)
    return ("低",1)
def main():
    c=sqlite3.connect(config.RECAP_DB); cur=c.cursor()
    ex={r[1] for r in cur.execute("PRAGMA table_info(dim4_trade_plan)")}
    for col in ("position_band TEXT","position_risk_pref INTEGER"):
        if col.split()[0] not in ex: cur.execute(f"ALTER TABLE dim4_trade_plan ADD COLUMN {col}")
    n=0
    for d,r in cur.execute("select date,position_repr from dim4_trade_plan where position_repr is not null").fetchall():
        b,p=band(r); cur.execute("update dim4_trade_plan set position_band=?,position_risk_pref=? where date=?",(b,p,d)); n+=1
    c.commit(); print("分档更新",n,"行")
if __name__=="__main__": main()
