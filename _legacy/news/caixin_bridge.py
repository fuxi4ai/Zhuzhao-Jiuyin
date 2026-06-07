"""
财新 HTTP Bridge — 供 JVSClaw (百炼) 调用
POST /invoke  {"tool": "<name>", "args": {...}}
"""
import os
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any

API_KEY = os.environ.get("CAIXIN_API_KEY", "5B8898DE7ACE46E98BC0DCD7B79B9500")
BASE_A  = "https://cxdata.caixin.com"
BASE_HK = "https://stock.caixin.com"
HEADERS = {"Authorization": f"Bearer {API_KEY}", "Accept": "application/json"}

app = FastAPI(title="caixin-bridge", version="1.0.0")


async def get(base: str, path: str, params: dict = {}) -> Any:
    url = base + path
    clean = {k: v for k, v in params.items() if v is not None}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, params=clean, headers=HEADERS)
        r.raise_for_status()
        return r.json()


class InvokeReq(BaseModel):
    tool: str
    args: dict = {}


@app.post("/invoke")
async def invoke(req: InvokeReq):
    t, a = req.tool, req.args
    try:
        if t == "caixin_market_overview":
            return await get(BASE_A, "/api/stock/cgi/indexMarket")

        elif t == "caixin_search":
            return await get(BASE_A, "/api/dataplus/search/newAssociationPc",
                             {"keyword": a.get("keyword", "")})

        elif t == "caixin_hot_stocks":
            return await get(BASE_A, "/api/dataplus/search/hotSearch",
                             {"size": a.get("size", 10)})

        elif t == "caixin_stock_rank":
            return await get(BASE_A, "/api/stock/cgi/StockRank", {
                "page": 1,
                "size": a.get("size", 10),
                "isAsc": a.get("isAsc", False),
                "type": a.get("type", "totValue"),
            })

        elif t == "caixin_industry_rank":
            return await get(BASE_A, "/api/stock/cgi/StockInduRanks", {
                "page": 1,
                "size": a.get("size", 10),
                "isAsc": a.get("isAsc", False),
                "type": a.get("type", "totValue"),
            })

        elif t == "caixin_index_rank":
            return await get(BASE_A, "/api/stock/cgi/IndexRank", {
                "page": 1,
                "size": a.get("size", 8),
                "isAsc": False,
                "type": "indshortname",
            })

        elif t == "caixin_stock_news":
            return await get(BASE_A, "/api/stock/cgi/StockNews", {
                "id":   a["id"],
                "page": a.get("page", 1),
                "size": a.get("size", 5),
            })

        elif t == "caixin_hk_indices":
            return await get(BASE_HK, "/api/hkstock/indexQuotation/indexList")

        elif t == "caixin_hk_industry":
            return await get(BASE_HK, "/api/hkstock/industry/industryInfos", {
                "page": 1,
                "size": a.get("size", 10),
                "orderType": 1,
                "orderField": a.get("orderField", "totValue"),
            })

        else:
            raise HTTPException(400, f"Unknown tool: {t}")

    except httpx.HTTPStatusError as e:
        raise HTTPException(502, f"Caixin API error: {e.response.status_code}")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("CAIXIN_BRIDGE_PORT", 8765))
    uvicorn.run(app, host="0.0.0.0", port=port)
