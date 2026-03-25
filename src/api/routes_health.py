"""
Data Health Check API
Reports staleness and status of all data sources.
"""
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.api.dependencies import get_db
from src.config import get_settings
from src.services.kline_service import KlineService
from src.models import SymbolType, KlineTimeframe
from src.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()

# Timeout for legitimate external calls (park-intel)
_EXTERNAL_TIMEOUT = 5.0


async def _check_index_realtime() -> Dict[str, Any]:
    """Check A-share index realtime data freshness by calling the route handler directly."""
    try:
        from src.api.routes_index import get_index_realtime

        t0 = time.monotonic()
        data = await get_index_realtime("000001.SH")
        latency_ms = round((time.monotonic() - t0) * 1000)
        return {
            "status": "ok",
            "last_update": data.get("last_update", "unknown"),
            "price": data.get("price"),
            "latency_ms": latency_ms,
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


async def _check_commodities_realtime() -> Dict[str, Any]:
    """Check commodities realtime data freshness by calling the route handler directly."""
    try:
        from src.api.routes_commodities import get_commodities_realtime

        t0 = time.monotonic()
        result = await get_commodities_realtime()
        latency_ms = round((time.monotonic() - t0) * 1000)
        return {
            "status": "ok",
            "last_update": result.last_update,
            "count": result.count,
            "latency_ms": latency_ms,
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def _check_crypto_ws() -> Dict[str, Any]:
    """Check crypto WebSocket data freshness from in-memory state."""
    try:
        from src.services.crypto_ws import get_crypto_ws_manager

        t0 = time.monotonic()
        manager = get_crypto_ws_manager()
        tickers = manager.get_all_tickers()
        latency_ms = round((time.monotonic() - t0) * 1000)

        total = len(tickers)
        stale_count = sum(1 for t in tickers.values() if t.is_stale)
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


async def _check_commodity_klines_with_timeout(symbol: str, label: str, timeout_s: float = 3.0) -> Dict[str, Any]:
    """Check commodity kline freshness via yfinance with a hard timeout.
    Falls back to 'unavailable' if the external API is slow — never blocks the health endpoint.
    """
    import asyncio

    async def _fetch():
        import yfinance as yf
        t0 = time.monotonic()
        ticker = yf.Ticker(symbol)
        df = await asyncio.get_event_loop().run_in_executor(
            None, lambda: ticker.history(period="3mo", interval="1d")
        )
        latency_ms = round((time.monotonic() - t0) * 1000)
        if df.empty:
            return {"status": "error", "detail": f"No kline data for {label}", "latency_ms": latency_ms}
        last_date = df.index[-1].strftime("%Y-%m-%d")
        return {"status": "ok", "latest_date": last_date, "latency_ms": latency_ms}

    try:
        return await asyncio.wait_for(_fetch(), timeout=timeout_s)
    except asyncio.TimeoutError:
        return {"status": "unavailable", "detail": f"{label}: yfinance timeout ({timeout_s}s)"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


async def _check_crypto_klines(symbol: str, interval: str, limit: int, label: str) -> Dict[str, Any]:
    """Check crypto kline freshness by calling the service directly."""
    try:
        from src.services.crypto_service import get_crypto_service

        t0 = time.monotonic()
        service = get_crypto_service()
        klines = await service.get_klines(symbol, interval, limit)
        latency_ms = round((time.monotonic() - t0) * 1000)
        if not klines:
            return {"status": "error", "detail": f"No kline data for {label}", "latency_ms": latency_ms}
        last = klines[-1]
        date_str = last.get("time", "unknown") if isinstance(last, dict) else str(last.time)
        date_part = str(date_str)[:10]
        return {
            "status": "ok",
            "latest_date": date_part,
            "count": len(klines),
            "latency_ms": latency_ms,
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@router.get("/freshness")
async def freshness_check(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Fast local-only freshness check for health monitoring (trading-ctl.sh, OpenClaw cron).

    Only checks LOCAL state (DB, in-memory). No external API calls (yfinance, Sina).
    Guaranteed to respond within milliseconds. Use /data or /unified for full external checks.
    """
    t0 = time.monotonic()
    now = datetime.now(timezone.utc)
    sources: Dict[str, Any] = {}

    # 1. Crypto WebSocket — in-memory, instant
    sources["crypto_ws"] = _check_crypto_ws()

    # 2. Index klines from DB
    sources["index_klines"] = _check_klines_db(
        db, SymbolType.INDEX, "000001.SH", KlineTimeframe.DAY, "上证指数 daily"
    )

    # 3. DB connectivity check (simple query)
    try:
        db.execute(text("SELECT 1"))
        sources["database"] = {"status": "ok"}
    except Exception as e:
        sources["database"] = {"status": "error", "detail": str(e)}

    # Overall
    statuses = [s.get("status", "error") for s in sources.values()]
    if all(s == "ok" for s in statuses):
        overall = "healthy"
    elif any(s == "error" for s in statuses):
        overall = "unhealthy"
    else:
        overall = "degraded"

    latency_ms = round((time.monotonic() - t0) * 1000)

    return {
        "status": overall,
        "sources": sources,
        "latency_ms": latency_ms,
        "timestamp": now.isoformat(),
    }


@router.get("/data")
async def data_health_check(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Comprehensive data health check.
    Reports status and freshness of all data sources.
    """
    checks: Dict[str, Any] = {}

    # Realtime checks
    checks["index_realtime"] = await _check_index_realtime()
    checks["commodities_realtime"] = await _check_commodities_realtime()
    checks["crypto_ws"] = _check_crypto_ws()

    # Kline checks
    checks["index_klines"] = _check_klines_db(
        db, SymbolType.INDEX, "000001.SH", KlineTimeframe.DAY, "上证指数 daily"
    )
    checks["commodity_klines"] = await _check_commodity_klines_with_timeout("GC=F", "Gold daily")
    checks["crypto_klines"] = await _check_crypto_klines("BTC", "1d", 10, "BTC daily")

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


@router.get("/unified")
async def unified_health_check(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Unified health dashboard aggregating quant + qualitative data sources.
    """
    from src.api.routes_status import get_data_freshness

    now = datetime.now(timezone(timedelta(hours=8)))

    # 1. Quant realtime checks
    quant: Dict[str, Any] = {}
    quant["index_realtime"] = await _check_index_realtime()
    quant["commodities_realtime"] = await _check_commodities_realtime()
    quant["crypto_ws"] = _check_crypto_ws()

    # 2. Quant kline/file freshness
    freshness = get_data_freshness(db)
    for key, info in freshness.get("sources", {}).items():
        # Mark never-loaded sources as unconfigured instead of error
        if info.get("status") == "no_data" or (info.get("status") == "missing" and not info.get("exists")):
            info["status"] = "unconfigured"
        quant[key] = info

    # 3. Qualitative sources from park-intel
    qualitative: Dict[str, Any] = {}
    park_intel_url = get_settings().park_intel_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=_EXTERNAL_TIMEOUT) as client:
            resp = await client.get(f"{park_intel_url}/api/articles/sources")
        if resp.status_code == 200:
            for src in resp.json():
                qualitative[src["source"]] = {
                    "status": "ok",
                    "count": src.get("count", 0),
                    "last_collected_at": src.get("last_collected_at"),
                    "latest_published_at": src.get("latest_published_at"),
                    "articles_last_24h": src.get("articles_last_24h", 0),
                }
            qualitative["service_status"] = "ok"
        else:
            qualitative["service_status"] = "unavailable"
    except (httpx.ConnectError, httpx.TimeoutException):
        qualitative["service_status"] = "unavailable"

    # 4. Overall status (skip unconfigured sources)
    all_statuses = []
    for v in quant.values():
        if isinstance(v, dict) and v.get("status") != "unconfigured":
            all_statuses.append(v.get("status", "ok"))
    for k, v in qualitative.items():
        if isinstance(v, dict) and v.get("status") != "unconfigured":
            all_statuses.append(v.get("status", "ok"))
    if qualitative.get("service_status") == "unavailable":
        all_statuses.append("error")

    if all(s == "ok" for s in all_statuses):
        overall = "healthy"
    elif any(s == "error" for s in all_statuses):
        overall = "unhealthy"
    else:
        overall = "degraded"

    return {
        "status": overall,
        "timestamp": now.isoformat(),
        "quant": quant,
        "qualitative": qualitative,
    }
