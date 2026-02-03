"""Perception Layer API endpoints.

- POST /api/perception/scan   — trigger a scan cycle
- GET  /api/perception/signals — current aggregated signals
- GET  /api/perception/health  — pipeline health status
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

from src.perception.pipeline import PerceptionPipeline, PipelineConfig

logger = logging.getLogger(__name__)

router = APIRouter()

# Module-level singleton — lazy-initialised on first request
_pipeline: Optional[PerceptionPipeline] = None


def _get_pipeline() -> PerceptionPipeline:
    """Return the global pipeline instance, creating it if needed."""
    global _pipeline
    if _pipeline is None:
        _pipeline = PerceptionPipeline()
    return _pipeline


def set_pipeline(pipeline: PerceptionPipeline) -> None:
    """Allow external code (e.g. tests) to inject a custom pipeline."""
    global _pipeline
    _pipeline = pipeline


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
