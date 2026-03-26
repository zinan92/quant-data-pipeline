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


@router.get("/gaps")
def get_health_gaps(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Gap detection endpoint: cross-references trade_calendar with klines to find missing trading days.
    
    Only counts gaps AFTER a stock's listing date (from stock_basic) or after the backfill start date
    (2021-01-04), whichever is later. This prevents false gaps for stocks that IPO'd after the 
    backfill start date.
    
    Returns:
        - total_gaps: Total count of missing trading days across all symbols
        - by_type: Breakdown by symbol type (STOCK/INDEX)
        - details: Top 50 symbols with most gaps (symbol_code, symbol_type, gap_count, missing_dates)
        - calendar_coverage: Trade calendar metadata (min_date, max_date, trading_days)
        - total_tracked_stocks: Total number of tracked stocks (for frontend summary)
        - stocks_with_zero_gaps: Number of stocks with no gaps (healthy)
    """
    from src.models import TradeCalendar, Kline, SymbolType, KlineTimeframe
    from sqlalchemy import func, select, text
    
    BACKFILL_START_DATE = "2021-01-04"
    
    # 1. Get calendar coverage
    cal_min = db.execute(select(func.min(TradeCalendar.date)).filter(TradeCalendar.is_trading_day == 1)).scalar()
    cal_max = db.execute(select(func.max(TradeCalendar.date)).filter(TradeCalendar.is_trading_day == 1)).scalar()
    trading_day_count = db.execute(select(func.count()).select_from(TradeCalendar).filter(TradeCalendar.is_trading_day == 1)).scalar()
    
    calendar_coverage = {
        "min_date": cal_min or "unknown",
        "max_date": cal_max or "unknown",
        "trading_days": trading_day_count or 0
    }
    
    # 2. Get all trading days from calendar (2021-01-04 onwards)
    trading_days_result = db.execute(
        select(TradeCalendar.date)
        .filter(TradeCalendar.is_trading_day == 1, TradeCalendar.date >= BACKFILL_START_DATE)
        .order_by(TradeCalendar.date)
    ).fetchall()
    all_trading_days = {row[0] for row in trading_days_result}
    
    # 3. Get all tracked symbols (both STOCK and INDEX) with their names
    # Use GROUP BY to get one row per (symbol_code, symbol_type) with the first non-null name
    symbols_query = text("""
        SELECT symbol_code, 
               COALESCE(MAX(symbol_name), symbol_code) as symbol_name,
               symbol_type
        FROM klines 
        WHERE timeframe = 'DAY' 
          AND symbol_type IN ('STOCK', 'INDEX')
        GROUP BY symbol_code, symbol_type
    """)
    symbols_result = db.execute(symbols_query).fetchall()
    
    # 4. Get stock listing dates from stock_basic (for filtering gaps)
    # Map symbol_code (e.g., "000001") to list_date
    # stock_basic uses ts_code format like "000001.SZ", so we need to match the plain symbol part
    stock_list_dates = {}
    try:
        list_dates_result = db.execute(text(
            "SELECT ts_code, list_date FROM stock_basic WHERE list_date IS NOT NULL"
        )).fetchall()
        
        for ts_code, list_date in list_dates_result:
            if not list_date:
                continue
            # Extract plain symbol from ts_code (e.g., "000001.SZ" -> "000001")
            plain_symbol = ts_code.split('.')[0] if '.' in ts_code else ts_code
            # Convert list_date from YYYYMMDD to YYYY-MM-DD format
            if len(list_date) == 8 and list_date.isdigit():
                formatted_date = f"{list_date[:4]}-{list_date[4:6]}-{list_date[6:8]}"
                stock_list_dates[plain_symbol] = formatted_date
    except Exception as e:
        logger.warning(f"Failed to load stock listing dates: {e}")
        # Continue without listing dates (will use backfill start date for all stocks)
    
    # 5. For each symbol, find gaps (considering listing dates for stocks)
    gap_details = []
    by_type = {
        "STOCK": {"symbols_with_gaps": 0, "total_missing_days": 0},
        "INDEX": {"symbols_with_gaps": 0, "total_missing_days": 0}
    }
    
    total_tracked_stocks = 0
    stocks_with_zero_gaps = 0
    
    for symbol_code, symbol_name, symbol_type_str in symbols_result:
        # symbol_type_str is a string when using raw SQL
        # Count tracked stocks
        if symbol_type_str == 'STOCK':
            total_tracked_stocks += 1
        
        # Get all kline dates for this symbol
        # Convert symbol_type_str back to enum for query
        symbol_type_enum = SymbolType.STOCK if symbol_type_str == 'STOCK' else SymbolType.INDEX
        kline_dates_result = db.execute(
            select(Kline.trade_time)
            .filter(
                Kline.symbol_code == symbol_code,
                Kline.symbol_type == symbol_type_enum,
                Kline.timeframe == KlineTimeframe.DAY
            )
        ).fetchall()
        
        # Extract date part (first 10 chars: YYYY-MM-DD)
        kline_dates = {row[0][:10] for row in kline_dates_result if row[0]}
        
        # Determine expected start date for this symbol
        # For stocks: MAX(list_date, BACKFILL_START_DATE)
        # For indices: BACKFILL_START_DATE
        if symbol_type_str == 'STOCK':
            list_date = stock_list_dates.get(symbol_code)
            if list_date and list_date > BACKFILL_START_DATE:
                expected_start_date = list_date
            else:
                expected_start_date = BACKFILL_START_DATE
        else:
            # Indices should have data from backfill start
            expected_start_date = BACKFILL_START_DATE
        
        # Filter trading days to only those >= expected_start_date
        expected_trading_days = {d for d in all_trading_days if d >= expected_start_date}
        
        # Find missing dates
        missing = expected_trading_days - kline_dates
        
        if missing:
            missing_sorted = sorted(list(missing))
            # symbol_type_str is already uppercase from SQL query
            gap_details.append({
                "symbol_code": symbol_code,
                "symbol_name": symbol_name or symbol_code,
                "symbol_type": symbol_type_str,
                "gap_count": len(missing),
                "missing_dates": missing_sorted
            })
            
            # Update by_type stats
            by_type[symbol_type_str]["symbols_with_gaps"] += 1
            by_type[symbol_type_str]["total_missing_days"] += len(missing)
        else:
            # No gaps for this symbol
            if symbol_type_str == 'STOCK':
                stocks_with_zero_gaps += 1
    
    # 6. Sort by gap_count descending, limit to top 50 for performance
    gap_details.sort(key=lambda x: x["gap_count"], reverse=True)
    top_50_details = gap_details[:50]
    
    # 7. Calculate total_gaps
    total_gaps = sum(detail["gap_count"] for detail in gap_details)
    
    return {
        "total_gaps": total_gaps,
        "by_type": by_type,
        "details": top_50_details,
        "calendar_coverage": calendar_coverage,
        "total_tracked_stocks": total_tracked_stocks,
        "stocks_with_zero_gaps": stocks_with_zero_gaps
    }


@router.get("/consistency")
async def get_health_consistency(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Data consistency endpoint: runs DataConsistencyValidator and returns results.
    
    Returns:
        - summary: total_validated, total_inconsistencies, consistency_rate, is_healthy
        - indexes: List of index validation results
        - concepts: List of concept validation results
        - inconsistencies: List of items with inconsistencies
    """
    from src.services.data_consistency_validator import DataConsistencyValidator
    
    validator = DataConsistencyValidator.create_with_session(db)
    results = await validator.validate_all()
    
    return results


@router.get("/failures")
def get_health_failures(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Recent failures endpoint: returns last 50 DataUpdateLog failures ordered by recency.
    
    Returns:
        - failures: List of failed updates with update_type, error_message, started_at, etc.
        - count: Total number of failures returned
    """
    from src.models import DataUpdateLog, DataUpdateStatus
    from sqlalchemy import desc, select
    
    failed_logs = db.execute(
        select(DataUpdateLog)
        .filter(DataUpdateLog.status == DataUpdateStatus.FAILED)
        .order_by(desc(DataUpdateLog.started_at))
        .limit(50)
    ).scalars().all()
    
    failures = []
    for log in failed_logs:
        failures.append({
            "id": log.id,
            "update_type": log.update_type,
            "symbol_type": log.symbol_type,
            "timeframe": log.timeframe,
            "status": log.status.value.upper(),  # Convert to uppercase for consistency
            "records_updated": log.records_updated,
            "error_message": log.error_message,
            "started_at": log.started_at.isoformat() if log.started_at else None,
            "completed_at": log.completed_at.isoformat() if log.completed_at else None
        })
    
    return {
        "failures": failures,
        "count": len(failures)
    }
