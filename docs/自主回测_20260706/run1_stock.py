import sys, json, sqlite3
sys.path.insert(0,'/tmp/bt'); from common import *
from datetime import date as D
r, m = conn(R), conn(M)
cal = load_cal(m); bench = load_bench(m)
rows = r.execute("""SELECT id, signal_date, stock_code, target_pool, info_gap_level, logic_type, resolve_status
                    FROM stock_tracking WHERE stock_code IS NOT NULL AND stock_code != ''""").fetchall()
codes = sorted({x[2] for x in rows})
# 批量拉行情
px = {}
for i in range(0, len(codes), 400):
    chunk = codes[i:i+400]
    qs = ",".join("?"*len(chunk))
    for c, d, p in m.execute(f"SELECT ts_code, trade_date, pct_chg FROM stock_daily WHERE ts_code IN ({qs}) AND trade_date>='20251001'", chunk):
        px.setdefault(c, {})[d] = p
out = []
skip = {"no_px":0, "gap_far":0, "window_short":0}
for sid, sdate, code, pool, lvl, lt, rs in rows:
    sd = ymd(sdate)
    if len(sd) != 8 or not sd.isdigit(): skip["window_short"] += 1; continue
    if code not in px: skip["no_px"] += 1; continue
    i0 = first_td_after(cal, sd)
    if i0 is None: skip["window_short"] += 1; continue
    # ADJ_MAX_DAYS=10 自然日守卫
    d0 = cal[i0]
    if (D(int(d0[:4]),int(d0[4:6]),int(d0[6:8])) - D(int(sd[:4]),int(sd[4:6]),int(sd[6:8]))).days > 10:
        skip["gap_far"] += 1; continue
    rec = {"pool":pool,"lvl":lvl or "无","lt":lt or "无","date":sd}
    ok = False
    for n in (1,3,5,10):
        s = fwd_cum(px[code], cal, i0, n); b = fwd_cum(bench, cal, i0, n)
        rec[f"ex{n}"] = (s-b) if (s is not None and b is not None) else None
        ok = ok or rec[f"ex{n}"] is not None
    if ok: out.append(rec)
    else: skip["window_short"] += 1
json.dump({"rows":out,"skip":skip}, open('/tmp/bt/stock_rows.json','w'))
print("样本:", len(out), "skip:", skip)
