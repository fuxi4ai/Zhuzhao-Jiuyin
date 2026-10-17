import json, statistics as st
data = json.load(open('/tmp/bt/stock_rows.json'))
rows = data["rows"]
def agg(sel, key):
    g = {}
    for r in rows:
        if not sel(r): continue
        g.setdefault(key(r), []).append(r)
    out = []
    for k, rs in sorted(g.items(), key=lambda x:-len(x[1])):
        line = {"组":k, "n":len(rs)}
        for n in (1,3,5,10):
            v = [x[f"ex{n}"] for x in rs if x[f"ex{n}"] is not None]
            if v:
                line[f"胜率{n}d"] = round(100*sum(1 for x in v if x>0)/len(v),1)
                line[f"均超额{n}d"] = round(st.mean(v),2)
                line[f"中位{n}d"] = round(st.median(v),2)
                line[f"n{n}"] = len(v)
        out.append(line)
    return out
res = {
 "总体_分池": agg(lambda r: True, lambda r: r["pool"]),
 "own_分信息差": agg(lambda r: r["pool"]=="own", lambda r: r["lvl"]),
 "own_分逻辑": agg(lambda r: r["pool"]=="own", lambda r: r["lt"]),
 "own_信息差x逻辑_top": agg(lambda r: r["pool"]=="own", lambda r: f'{r["lvl"]}|{r["lt"]}')[:12],
 "own_分月": agg(lambda r: r["pool"]=="own", lambda r: r["date"][:6]),
}
json.dump(res, open('/tmp/bt/agg_stock.json','w'), ensure_ascii=False)
for k, v in res.items():
    print("##", k)
    for line in v[:14]: print("  ", line)
