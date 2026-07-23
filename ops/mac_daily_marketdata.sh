#!/bin/bash
# =====================================================================
# Mac 原生 · 每日行情落库 wrapper
# 根治：沙箱经 FUSE 整库写回丢大表(stock_daily)导致日报隔天退回。
# 在本机原生文件系统上按序落 market_data.db，写入即 durable。
# 由 launchd (com.zhuzhao.marketdata) 周一~五 02:30(本地时区) 触发；
# 也可手动直接跑本脚本做验证。
# 失败可见性铁律：任一步非零退出 → 日志标 ❌ 且脚本退出码非 0，绝不静默。
# =====================================================================
set -o pipefail

PY="/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13"
ZZ="$HOME/Documents/Claude/Projects/Financial/烛照九阴"
JQ="$HOME/Documents/Claude/Projects/Financial/剑酒青丘/infrastructure/取数工具"
DB="$HOME/Documents/Database/Market-Data/market_data.db"
LOGDIR="$ZZ/logs"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/mac_marketdata_$(date +%Y%m%d).log"
STATUS="$ZZ/ops/.last_run_status"

FAIL=0
ts(){ date "+%Y-%m-%d %H:%M:%S %Z"; }
log(){ echo "[$(ts)] $*" | tee -a "$LOG"; }

run(){                       # run "名称" 命令...
  local name="$1"; shift
  log "▶ $name"
  if "$@" >>"$LOG" 2>&1; then
    log "✅ $name 完成"
  else
    local rc=$?
    log "❌ $name 失败 (exit $rc)（详见上方日志）"
    FAIL=1
  fi
}

log "==================== Mac 原生行情落库 开始 ===================="
if [ ! -x "$PY" ]; then log "❌ 找不到 python: $PY"; echo "FAIL no-python $(ts)" >"$STATUS"; exit 1; fi
cd "$ZZ" || { log "❌ 进不去项目目录 $ZZ"; echo "FAIL no-projdir $(ts)" >"$STATUS"; exit 1; }

# 五表增量的起点：回看 7 天（INSERT OR IGNORE 幂等，重叠无害）
FROM="$(date -v-7d +%Y%m%d 2>/dev/null || date -d '7 days ago' +%Y%m%d)"
log "五表 --from=$FROM（回看 7 天，去重幂等）"

# ① 公共层：stock_daily（锚点大表，FUSE 下最易丢的就是它）
run "stock_daily 落库"      "$PY" "$ZZ/ops/ingest_stock_daily.py"
# ② 句芒派生：daily_market 派生列 + 指数/北向补缺（只填空不覆盖）
run "aggregate_derived"     "$PY" "$JQ/aggregate_derived.py"
run "fill_index_north"      "$PY" "$JQ/fill_index_north.py"
# ③ 烛照五表
run "theme_etf"             "$PY" "$ZZ/scripts/fetch_theme_etf.py"     --from "$FROM"
run "market_amount"         "$PY" "$ZZ/scripts/fetch_market_amount.py" --from "$FROM"
run "limit_list"            "$PY" "$ZZ/scripts/fetch_limit_list.py"    --from "$FROM"
run "margin"               "$PY" "$ZZ/scripts/fetch_margin.py"        --from "$FROM"
run "intl_index"            "$PY" "$ZZ/scripts/fetch_intl_index.py"
run "kr_stocks"             "$PY" "$ZZ/scripts/fetch_kr_stocks.py"

# ④ 收尾：核各表 max 落日志 + 写状态文件（供快速检查 / 看板）
log "---- 各表 MAX(trade_date) ----"
"$PY" - "$DB" >>"$LOG" 2>&1 <<'PY'
import sqlite3, sys
con = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro&immutable=1", uri=True)
for t in ["stock_daily","daily_market","theme_etf_daily","market_amount_daily",
          "limit_list_daily","margin_daily","us_anchor_daily","intl_index_daily"]:
    try:
        print(f"  {t:22s}", con.execute(f"SELECT MAX(trade_date) FROM {t}").fetchone()[0])
    except Exception as e:
        print(f"  {t:22s} ERR {e}")
PY

if [ "$FAIL" -eq 0 ]; then
  log "==================== 全部完成 · 无 ❌ ===================="
  echo "OK $(ts)" >"$STATUS"
  exit 0
else
  log "==================== 完成但有 ❌ · 见日志 ===================="
  echo "FAIL $(ts)" >"$STATUS"
  exit 1
fi
