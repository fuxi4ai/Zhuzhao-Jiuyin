import sys, json, statistics as st
sys.path.insert(0,'/tmp/bt'); from common import *
r, m = conn(R), conn(M)
cal = load_cal(m); bench = load_bench(m)
# 主线 ETF 超额日序列
etf = {}
for c, d, p in m.execute("SELECT etf_code, trade_date, pct_chg FROM theme_etf_daily WHERE is_benchmark=0"):
    etf.setdefault(c, {})[d] = p
def ex_fwd(code, dymd, n):
    i0 = first_td_after(cal, dymd)
    if i0 is None or code not in etf: return None
    s = fwd_cum(etf[code], cal, i0, n); b = fwd_cum(bench, cal, i0, n)
    return (s-b) if (s is not None and b is not None) else None
# 事件集：relit(暗态点亮) / realized(一段) / dormant(转暗)
evs = {"relit":[], "realized":[], "dormant":[]}
for anchor, relit, realized, dorm in r.execute(
    "SELECT etf_anchor, relit_date, date_realized, dormant_since FROM industry_signals WHERE etf_anchor IS NOT NULL"):
    if relit: evs["relit"].append((anchor, ymd(relit)))
    if realized: evs["realized"].append((anchor, ymd(realized)))
    if dorm: evs["dormant"].append((anchor, ymd(dorm)))
# 去重（主线×日期）
for k in evs: evs[k] = sorted(set(evs[k]))
out = {}
for k, pairs in evs.items():
    res = {}
    for n in (3,5,10,20):
        v = [x for x in (ex_fwd(a,d,n) for a,d in pairs) if x is not None]
        if v: res[f"{n}d"] = {"n":len(v), "胜率":round(100*sum(1 for x in v if x>0)/len(v),1),
                              "均":round(st.mean(v),2), "中位":round(st.median(v),2)}
    out[k] = {"事件数":len(pairs), **res}
# 无条件基线：全部主线×全部交易日
import random
random.seed(42)
codes = list(etf.keys())
base = {}
for n in (3,5,10,20):
    v = []
    for _ in range(4000):
        c = random.choice(codes); i = random.randrange(0, len(cal)-n-1)
        d = cal[i]
        if d < '20250102': continue
        s = fwd_cum(etf[c], cal, i+1, n); b = fwd_cum(bench, cal, i+1, n)
        if s is not None and b is not None: v.append(s-b)
    base[f"{n}d"] = {"n":len(v), "胜率":round(100*sum(1 for x in v if x>0)/len(v),1),
                     "均":round(st.mean(v),2), "中位":round(st.median(v),2)}
out["无条件基线(随机主线×随机日)"] = base
json.dump(out, open('/tmp/bt/relit.json','w'), ensure_ascii=False)
for k,v in out.items(): print(k, "→", json.dumps(v, ensure_ascii=False))
