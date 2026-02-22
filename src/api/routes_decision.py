"""
Decision Loop V1 API endpoints.

- POST /api/decision/run            — execute full decision loop
- GET  /api/decision/history        — recent decision runs
- GET  /api/decision/stats          — 7-day acceptance stats
- POST /api/decision/{run_id}/review — attach 23:00 review
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.auth import verify_api_key
from src.config import get_settings
from src.schemas.decision import ReviewEntry
from src.services.decision_loop import DecisionLoopService
from src.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


def _get_service() -> DecisionLoopService:
    """Create service with current settings."""
    settings = get_settings()
    return DecisionLoopService(
        base_url="http://127.0.0.1:8000",
        api_key=settings.api_key,
    )


@router.post("/run")
async def run_decision_loop(
    _: None = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Execute the full Decision Loop V1 cycle.

    Gathers market data → runs Claude analysis → produces decision → persists.
    """
    service = _get_service()
    try:
        result = await service.run()
        return {
            "status": "ok",
            "run_id": result.run_id,
            "timestamp": result.timestamp,
            "duration_ms": result.duration_ms,
            "analysis": result.analysis.model_dump(),
            "output": result.output.model_dump(),
            "execution_notes": result.execution_notes,
            "input_completeness": {
                "missing_fields": result.input_package.missing_fields,
                "is_low_confidence": result.input_package.is_low_confidence,
            },
        }
    except ValueError as exc:
        logger.error("Decision loop failed: %s", exc)
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.exception("Decision loop error")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/history")
def get_history(
    days: int = Query(7, ge=1, le=90, description="Look back N days"),
) -> Dict[str, Any]:
    """Get recent decision loop runs.

    Plain def — FastAPI runs sync handlers in a threadpool automatically.
    """
    service = _get_service()
    runs = service.get_history(days=days)
    return {
        "status": "ok",
        "count": len(runs),
        "runs": runs,
    }


@router.get("/stats")
def get_stats(
    days: int = Query(7, ge=1, le=90, description="Stats period in days"),
) -> Dict[str, Any]:
    """Get Decision Loop V1 acceptance stats.

    Plain def — FastAPI runs sync handlers in a threadpool automatically.
    """
    service = _get_service()
    stats = service.get_stats(days=days)
    return {
        "status": "ok",
        **stats,
    }


@router.post("/{run_id}/review")
def submit_review(
    run_id: str,
    review: ReviewEntry,
    _: None = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Attach a 23:00 review to an existing decision run.

    Plain def — sync DB operation, FastAPI runs in threadpool.
    """
    service = _get_service()
    ok = service.save_review(run_id, review)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return {
        "status": "ok",
        "run_id": run_id,
        "message": "Review saved",
    }
