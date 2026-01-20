from typing import List, Optional
import threading
import uuid
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from src.config import get_settings

router = APIRouter()


class RefreshRequest(BaseModel):
    tickers: Optional[List[str]] = None


@router.post("/refresh", status_code=202)
def trigger_refresh(
    payload: RefreshRequest,
) -> dict[str, str]:
    """
    Trigger a full data refresh (async):
      1) Refresh industry daily data
      2) Refresh super category daily data
      3) Update ETF data

    Returns a job_id for progress polling.
    """
    settings = get_settings()

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "status": "started",
        "progress": 0,
        "message": "开始刷新",
        "started_at": datetime.utcnow().isoformat(),
        "finished_at": None,
    }

    worker = threading.Thread(
        target=_run_full_refresh,
        kwargs={
            "job_id": job_id,
            "settings": settings,
        },
        daemon=True,
    )
    worker.start()

    return {"job_id": job_id, "status": "started"}


@router.get("/refresh/{job_id}")
def get_refresh_status(job_id: str) -> dict[str, str | int | None]:
    job = _jobs.get(job_id)
    if not job:
        return {"status": "not_found", "progress": 0}
    return job


def _run_script(script_name: str) -> None:
    """Run a helper script synchronously (same behavior as scheduler)."""
    import subprocess
    from pathlib import Path

    script_path = Path(__file__).parent.parent.parent / "scripts" / script_name
    result = subprocess.run(
        ["python", str(script_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # log to stderr so uvicorn logs it; avoid raising to keep other tasks going
        print(f"[refresh] {script_name} failed: {result.stderr}", flush=True)


def _run_full_refresh(
    job_id: str,
    settings,
) -> None:
    def update(status: str | None = None, progress: int | None = None, message: str | None = None):
        job = _jobs.get(job_id)
        if not job:
            return
        if status:
            job["status"] = status
        if progress is not None:
            job["progress"] = progress
        if message:
            job["message"] = message
        if status in ("completed", "failed"):
            job["finished_at"] = datetime.utcnow().isoformat()

    try:
        update(progress=10, message="更新行业数据")
        _run_script("update_industry_daily.py")

        update(progress=80, message="更新超级行业数据")
        _run_script("update_super_category_daily.py")

        update(progress=82, message="更新ETF日度汇总")
        _run_script("update_etf_daily_summary.py")

        update(progress=85, message="构建ETF精选列表")
        _run_script("build_etf_filtered.py")

        update(progress=86, message="更新ETF每日资金流")
        _run_script("update_etf_daily_flow.py")

        update(progress=88, message="更新ETF K线数据")
        _run_script("download_etf_klines.py")

        update(progress=95, message="计算ETF资金流")
        _run_script("calc_etf_flow_history.py")

        update(status="completed", progress=100, message="刷新完成")
    except Exception as exc:  # pragma: no cover
        update(status="failed", progress=100, message=f"刷新失败: {exc}")


# In-memory job store (best-effort)
_jobs: dict[str, dict[str, str | int | None]] = {}
