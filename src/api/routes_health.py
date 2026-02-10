"""
Data Health Check API
Reports staleness and status of all data sources.
"""
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.api.dependencies import get_db
from src.services.kline_service import KlineService
from src.models import SymbolType, KlineTimeframe
from src.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()

# Internal base URL for self-calls
_BASE = "http://127.0.0.1:8000"
_TIMEOUT = 5.0


async def _check_index_realtime() -> Dict[str, Any]:
    """Check A-share index realtime data freshness."""
    try:
        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{_BASE}/api/index/realtime/000001.SH")
        latency_ms = round((time.monotonic() - t0) * 1000)
        if resp.status_code != 200:
            return {"status": "error", "detail": f"HTTP {resp.status_code}", "latency_ms": latency_ms}
        data = resp.json()
        return {
            "status": "ok",
            "last_update": data.get("last_update", "unknown"),
            "price": data.get("price"),
            "latency_ms": latency_ms,
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


async def _check_commodities_realtime() -> Dict[str, Any]:
    """Check commodities realtime data freshness."""
    try:
        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{_BASE}/api/commodities/realtime")
        latency_ms = round((time.monotonic() - t0) * 1000)
        if resp.status_code != 200:
            return {"status": "error", "detail": f"HTTP {resp.status_code}", "latency_ms": latency_ms}
        data = resp.json()
        return {
            "status": "ok",
            "last_update": data.get("last_update", "unknown"),
            "count": data.get("count", 0),
            "latency_ms": latency_ms,
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


async def _check_crypto_ws() -> Dict[str, Any]:
    """Check crypto WebSocket data freshness."""
    try:
        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{_BASE}/api/crypto/realtime")
        latency_ms = round((time.monotonic() - t0) * 1000)
        if resp.status_code != 200:
            return {"status": "error", "detail": f"HTTP {resp.status_code}", "latency_ms": latency_ms}
        data = resp.json()
        stale_count = sum(1 for t in data.get("tickers", []) if t.get("is_stale", False))
        total = len(data.get("tickers", []))
        status = "ok" if stale_count == 0 and total > 0 else ("degraded" if total > 0 else "error")
        return {
            "status": status,
            "symbols": total,
            "stale": stale_count,
            "latency_ms": latency_ms,
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def _check_klines_db(db: Session, symbol_type: SymbolType, symbol_code: str, timeframe: KlineTimeframe, label: str) -> Dict[str, Any]:
    """Check kline data freshness for an index symbol (DB-backed)."""
    try:
        service = KlineService.create_with_session(db)
        latest_time = service.get_latest_trade_time(
            symbol_type=symbol_type,
            symbol_code=symbol_code,
            timeframe=timeframe,
        )
        if not latest_time:
            return {"status": "error", "detail": f"No kline data for {label}"}
        # Extract date part
        date_part = latest_time[:10] if len(latest_time) >= 10 else latest_time
        return {
            "status": "ok",
            "latest_date": date_part,
            "latest_time": latest_time,
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


async def _check_klines_api(url: str, label: str) -> Dict[str, Any]:
    """Check kline data freshness via API call (for commodities/crypto)."""
    try:
        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(f"{_BASE}{url}")
        latency_ms = round((time.monotonic() - t0) * 1000)
        if resp.status_code != 200:
            return {"status": "error", "detail": f"HTTP {resp.status_code}", "latency_ms": latency_ms}
        data = resp.json()
        klines = data.get("klines", [])
        if not klines:
            return {"status": "error", "detail": f"No kline data for {label}", "latency_ms": latency_ms}
        last = klines[-1]
        date_str = last.get("date", last.get("time", "unknown"))
        if isinstance(date_str, str):
            date_part = date_str[:10]
        else:
            date_part = str(date_str)
        return {
            "status": "ok",
            "latest_date": date_part,
            "count": len(klines),
            "latency_ms": latency_ms,
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@router.get("/data")
async def data_health_check(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Comprehensive data health check.
    Reports status and freshness of all data sources.
    """
    checks: Dict[str, Any] = {}

    # Realtime checks (async)
    checks["index_realtime"] = await _check_index_realtime()
    checks["commodities_realtime"] = await _check_commodities_realtime()
    checks["crypto_ws"] = await _check_crypto_ws()

    # Kline checks
    checks["index_klines"] = _check_klines_db(
        db, SymbolType.INDEX, "000001.SH", KlineTimeframe.DAY, "上证指数 daily"
    )
    checks["commodity_klines"] = await _check_klines_api(
        "/api/commodities/klines/GC%3DF?interval=1d", "Gold daily"
    )
    checks["crypto_klines"] = await _check_klines_api(
        "/api/crypto/kline/BTC?interval=1d&limit=10", "BTC daily"
    )

    # Overall status
    statuses = [c.get("status", "error") for c in checks.values()]
    if all(s == "ok" for s in statuses):
        overall = "healthy"
    elif any(s == "error" for s in statuses):
        overall = "degraded"
    else:
        overall = "degraded"

    now = datetime.now(timezone(timedelta(hours=8)))

    return {
        "status": overall,
        "checks": checks,
        "timestamp": now.isoformat(),
    }
