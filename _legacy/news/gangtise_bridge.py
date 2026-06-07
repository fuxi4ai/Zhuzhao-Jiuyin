"""
钢铁社 HTTP Bridge — 供 JVSClaw (百炼) 调用
POST /invoke  {"tool": "<name>", "args": {...}}

env vars:
  GTS_ACCESS_KEY      ak (优先)
  GTS_SECRET_KEY      sk (优先)
  GTS_TOKEN           长期 token（备用，与 ak/sk 二选一）
  GTS_BRIDGE_PORT     端口，默认 8766
"""
import os, time, datetime
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any

# ── 配置 ──────────────────────────────────────────────────────────────────────

AK    = os.environ.get("GTS_ACCESS_KEY",  "mv9lhs4iqwrg")
SK    = os.environ.get("GTS_SECRET_KEY",  "1b35e454-a292-45fa-99c1-94d94c9fd6d5")
TOKEN = os.environ.get("GTS_TOKEN",       "ac0aa901-4fec-41c2-a811-3cbb7d544cb3")

BASE      = "https://open.gangtise.com/application"
AUTH_URL  = f"{BASE}/auth/oauth/open/loginV2"
QUOTE     = f"{BASE}/open-quote"
FUND      = f"{BASE}/open-fundamental"
INSIGHT   = f"{BASE}/open-insight"
DATA      = f"{BASE}/open-data"

# ── Auth ──────────────────────────────────────────────────────────────────────

_bearer:     str   = ""
_token_exp:  float = 0.0      # epoch seconds

async def _get_bearer() -> str:
    global _bearer, _token_exp
    if _bearer and time.time() < _token_exp - 60:
        return _bearer
    if AK and SK:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(AUTH_URL, json={"accessKey": AK, "secretAccessKey": SK})
            r.raise_for_status()
            token = r.json()["data"]["accessToken"]
            _bearer    = token if token.startswith("Bearer ") else "Bearer " + token
            _token_exp = time.time() + 7200          # token 有效期约 2h
            return _bearer
    _bearer = TOKEN if TOKEN.startswith("Bearer ") else "Bearer " + TOKEN
    return _bearer

async def _headers() -> dict:
    return {"Authorization": await _get_bearer(), "Content-Type": "application/json"}

# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _ts(date_str: str | None) -> int | None:
    """'2026-01-01' → ms timestamp"""
    if not date_str:
        return None
    return int(datetime.datetime.strptime(date_str, "%Y-%m-%d").timestamp() * 1000)

async def post(url: str, payload: dict) -> Any:
    h = await _headers()
    clean = {k: v for k, v in payload.items() if v is not None}
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(url, headers=h, json=clean)
        r.raise_for_status()
        return r.json()

async def get(url: str, params: dict = {}) -> Any:
    h = await _headers()
    clean = {k: v for k, v in params.items() if v is not None}
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.get(url, headers=h, params=clean)
        r.raise_for_status()
        return r.json()

# ── FastAPI ───────────────────────────────────────────────────────────────────

app = FastAPI(title="gangtise-bridge", version="1.0.0")

class InvokeReq(BaseModel):
    tool: str
    args: dict = {}


@app.post("/invoke")
async def invoke(req: InvokeReq):
    t, a = req.tool, req.args
    try:
        # ── 行情 ──
        if t == "gts_quote":
            return await post(f"{QUOTE}/kline/daily", {
                "securityList": a.get("securities", []),
                "startDate":    a.get("start_date"),
                "endDate":      a.get("end_date", datetime.date.today().isoformat()),
                "limit":        a.get("limit", 250),
            })

        # ── 估值分位 ──
        elif t == "gts_valuation":
            return await post(f"{FUND}/valuation-analysis", {
                "securityCode": a["security_code"],
                "startDate":    a.get("start_date"),
                "endDate":      a.get("end_date"),
            })

        # ── 财务报表 ──
        elif t == "gts_financial":
            stmt = a.get("statement", "income")   # income | balance | cashflow
            period = a.get("period", "annual")     # annual | quarterly
            url_map = {
                ("income",   "annual"):    f"{FUND}/financial-report/income-statement/accumulated",
                ("income",   "quarterly"): f"{FUND}/financial-report/income-statement/quarterly",
                ("balance",  "annual"):    f"{FUND}/financial-report/balance-sheet/accumulated",
                ("cashflow", "annual"):    f"{FUND}/financial-report/cash-flow-statement/accumulated",
                ("cashflow", "quarterly"): f"{FUND}/financial-report/cash-flow-statement/quarterly",
            }
            url = url_map.get((stmt, period)) or url_map[("income", "annual")]
            return await post(url, {
                "securityCode": a["security_code"],
                "reportType":   a.get("report_type"),
            })

        # ── 外资研报 ──
        elif t == "gts_foreign_report":
            return await post(f"{INSIGHT}/foreign-report/getList", {
                "keyword":      a.get("keyword"),
                "securityList": a.get("securities"),
                "startTime":    _ts(a.get("start_date")),
                "endTime":      _ts(a.get("end_date")),
                "from":         (a.get("page", 1) - 1) * a.get("size", 10),
                "size":         a.get("size", 10),
            })

        # ── 国内研报 ──
        elif t == "gts_report":
            return await post(f"{INSIGHT}/broker-report/getList", {
                "keyword":      a.get("keyword"),
                "securityList": a.get("securities"),
                "startTime":    _ts(a.get("start_date")),
                "endTime":      _ts(a.get("end_date")),
                "from":         (a.get("page", 1) - 1) * a.get("size", 10),
                "size":         a.get("size", 10),
            })

        # ── 会议纪要 ──
        elif t == "gts_summary":
            return await post(f"{INSIGHT}/summary/v2/getList", {
                "keyword":      a.get("keyword"),
                "securityList": a.get("securities"),
                "startTime":    _ts(a.get("start_date")),
                "endTime":      _ts(a.get("end_date")),
                "from":         (a.get("page", 1) - 1) * a.get("size", 10),
                "size":         a.get("size", 10),
            })

        # ── 语义检索 KB ──
        elif t == "gts_kb":
            FILE_TYPE_MAP = {
                "外资研报": "FOREIGN_REPORT",
                "国内研报": "BROKER_REPORT",
                "会议纪要": "SUMMARY",
                "公告":     "ANNOUNCEMENT",
                "产业公众号": "INDUSTRY_WECHAT",
            }
            file_types = a.get("file_types")
            resource_types = (
                [FILE_TYPE_MAP[ft] for ft in file_types if ft in FILE_TYPE_MAP]
                if file_types else None
            )
            return await post(f"{DATA}/ai/search/knowledge_base", {
                "query":         a["query"],
                "startTime":     _ts(a.get("start_date")),
                "endTime":       _ts(a.get("end_date")),
                "resourceTypes": resource_types,
                "top":           a.get("limit", 5),
            })

        else:
            raise HTTPException(400, f"Unknown tool: {t}")

    except httpx.HTTPStatusError as e:
        raise HTTPException(502, f"Gangtise API error {e.response.status_code}: {e.response.text[:200]}")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("GTS_BRIDGE_PORT", 8766))
    uvicorn.run(app, host="0.0.0.0", port=port)
