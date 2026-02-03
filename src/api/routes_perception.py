"""Perception Layer API endpoints.

- POST /api/perception/scan            — trigger a scan cycle
- GET  /api/perception/signals         — current aggregated signals
- GET  /api/perception/health          — pipeline health status
- POST /api/perception/trading-signals — get trading-ready signals
- GET  /api/perception/market-context  — current market context
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

from src.perception.pipeline import PerceptionPipeline, PipelineConfig
from src.perception.integration.trading_bridge import TradingBridge, BridgeConfig
from src.perception.integration.market_context import MarketContextBuilder, ContextConfig

logger = logging.getLogger(__name__)

router = APIRouter()

# Module-level singletons — lazy-initialised on first request
_pipeline: Optional[PerceptionPipeline] = None
_bridge: Optional[TradingBridge] = None
_context_builder: Optional[MarketContextBuilder] = None


def _get_pipeline() -> PerceptionPipeline:
    """Return the global pipeline instance, creating it if needed."""
    global _pipeline
    if _pipeline is None:
        _pipeline = PerceptionPipeline()
    return _pipeline


def _get_bridge() -> TradingBridge:
    """Return the global trading bridge instance."""
    global _bridge
    if _bridge is None:
        _bridge = TradingBridge()
    return _bridge


def _get_context_builder() -> MarketContextBuilder:
    """Return the global context builder instance."""
    global _context_builder
    if _context_builder is None:
        _context_builder = MarketContextBuilder()
    return _context_builder


def set_pipeline(pipeline: PerceptionPipeline) -> None:
    """Allow external code (e.g. tests) to inject a custom pipeline."""
    global _pipeline
    _pipeline = pipeline


def set_bridge(bridge: TradingBridge) -> None:
    """Allow external code (e.g. tests) to inject a custom bridge."""
    global _bridge
    _bridge = bridge


def set_context_builder(builder: MarketContextBuilder) -> None:
    """Allow external code (e.g. tests) to inject a custom context builder."""
    global _context_builder
    _context_builder = builder


@router.post("/scan")
async def trigger_scan() -> Dict[str, Any]:
    """Trigger a perception scan cycle.

    Returns the full scan result including aggregation report,
    health status, and any errors.
    """
    pipeline = _get_pipeline()

    if not pipeline.is_running:
        await pipeline.start()

    try:
        result = await pipeline.scan()
        return {
            "status": "ok",
            "data": result.to_dict(),
        }
    except Exception as exc:
        logger.exception("Scan failed")
        raise HTTPException(status_code=500, detail=f"Scan failed: {exc}")


@router.get("/signals")
async def get_signals(limit: int = 50) -> Dict[str, Any]:
    """Get current aggregated signals.

    Parameters
    ----------
    limit : int
        Max number of signals to return (default 50).
    """
    pipeline = _get_pipeline()
    signals = pipeline.get_current_signals(limit=limit)
    return {
        "status": "ok",
        "count": len(signals),
        "signals": signals,
    }


@router.get("/health")
async def get_health() -> Dict[str, Any]:
    """Get pipeline and source health status."""
    pipeline = _get_pipeline()
    health = pipeline.get_health()
    return {
        "status": "ok",
        **health,
    }


@router.post("/trading-signals")
async def get_trading_signals(
    min_confidence: float = 0.4,
    limit: int = 50,
) -> Dict[str, Any]:
    """Trigger a scan and return trading-ready signals.

    Parameters
    ----------
    min_confidence : float
        Minimum confidence for actionable signals (default 0.4).
    limit : int
        Max signals to return (default 50).
    """
    pipeline = _get_pipeline()
    bridge = _get_bridge()

    if not pipeline.is_running:
        await pipeline.start()

    try:
        result = await pipeline.scan()
        trading_signals = bridge.get_trading_signals(result)

        # Filter by confidence
        filtered = [
            s for s in trading_signals if s.confidence >= min_confidence
        ][:limit]

        return {
            "status": "ok",
            "count": len(filtered),
            "actionable": sum(1 for s in filtered if s.is_actionable),
            "signals": [s.to_dict() for s in filtered],
            "scan_duration_ms": round(result.duration_ms, 2),
        }
    except Exception as exc:
        logger.exception("Trading signals endpoint failed")
        raise HTTPException(
            status_code=500, detail=f"Failed to generate trading signals: {exc}"
        )


@router.get("/market-context")
async def get_market_context() -> Dict[str, Any]:
    """Get the current market context derived from perception data.

    Returns overall market sentiment, risk factors, sector rotation
    signals, and per-market stats.
    """
    pipeline = _get_pipeline()
    builder = _get_context_builder()

    last_result = pipeline.last_result
    if last_result is None:
        # No scan has run yet — trigger one
        if not pipeline.is_running:
            await pipeline.start()
        try:
            last_result = await pipeline.scan()
        except Exception as exc:
            logger.exception("Market context scan failed")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to build market context: {exc}",
            )

    ctx = builder.build(last_result)
    return {
        "status": "ok",
        **ctx.to_dict(),
    }
