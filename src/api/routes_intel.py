"""
Intel proxy routes — proxies park-intel (port 8001) qualitative signal endpoints
into ashare's API namespace.

Endpoints:
  GET /api/intel/signals  → park-intel /api/articles/signals
  GET /api/intel/latest   → park-intel /api/articles/latest
  GET /api/intel/sources  → park-intel /api/articles/sources
"""

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
import httpx

from src.config import get_settings

router = APIRouter()

TIMEOUT = 10.0


async def _proxy(path: str, params: dict) -> JSONResponse:
    """Forward a GET request to park-intel and return its response."""
    base = get_settings().park_intel_url.rstrip("/")
    url = f"{base}{path}"
    # Strip None values from params
    params = {k: v for k, v in params.items() if v is not None}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url, params=params)
            return JSONResponse(content=resp.json(), status_code=resp.status_code)
    except (httpx.ConnectError, httpx.TimeoutException):
        return JSONResponse(
            content={"error": "park-intel unavailable", "data": []},
            status_code=503,
        )


@router.get("/signals")
async def intel_signals(
    hours: int = Query(24, ge=1, le=168),
    compare_hours: int = Query(24, ge=1, le=168),
    min_relevance: int = Query(1, ge=1, le=5),
    source: str | None = Query(None),
):
    return await _proxy("/api/articles/signals", {
        "hours": hours,
        "compare_hours": compare_hours,
        "min_relevance": min_relevance,
        "source": source,
    })


@router.get("/latest")
async def intel_latest(
    limit: int = Query(20, ge=1, le=200),
    source: str | None = Query(None),
    min_relevance: int | None = Query(None, ge=1, le=5),
):
    return await _proxy("/api/articles/latest", {
        "limit": limit,
        "source": source,
        "min_relevance": min_relevance,
    })


@router.get("/sources")
async def intel_sources():
    return await _proxy("/api/articles/sources", {})
