from datetime import datetime
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.api.dependencies import get_data_service, get_db
from src.models import Kline
from src.services.data_pipeline import MarketDataService
from src.services.kline_scheduler import get_scheduler
from src.utils.logging import get_logger

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
logger = get_logger(__name__)

router = APIRouter()


@router.get("", response_model=dict[str, Optional[datetime]])
def get_status(
    service: MarketDataService = Depends(get_data_service),
) -> dict[str, Optional[datetime]]:
    """Expose last refresh timestamp used for UI badges."""
    return {"last_refreshed": service.last_refresh_time()}


@router.get("/update-times")
def get_update_times(
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    获取各数据源的更新时间信息
    包括最后更新时间和下次更新时间
    """
    try:
        scheduler = get_scheduler()
        jobs = scheduler.get_jobs() if scheduler._is_running else []

        # 获取最新的K线数据时间
        kline_times = {}
        for symbol_type in ["index", "concept", "stock"]:
            for timeframe in ["day", "30m"]:
                latest = (
                    db.query(func.max(Kline.trade_time))
                    .filter(
                        Kline.symbol_type == symbol_type,
                        Kline.timeframe == timeframe
                    )
                    .scalar()
                )

                # 将字符串时间转换为带时区的datetime
                last_update_iso = None
                if latest:
                    try:
                        # 尝试解析不同的时间格式
                        if len(latest) == 10:  # YYYY-MM-DD
                            dt = datetime.strptime(latest, "%Y-%m-%d")
                            # 日线数据假设是当天收盘时间 15:00
                            dt = dt.replace(hour=15, minute=0, second=0)
                        elif len(latest) == 19:  # YYYY-MM-DD HH:MM:SS
                            dt = datetime.strptime(latest, "%Y-%m-%d %H:%M:%S")
                        else:
                            dt = datetime.fromisoformat(latest.replace(' ', 'T'))

                        # 添加时区信息（上海时区）
                        dt = dt.replace(tzinfo=SHANGHAI_TZ)
                        last_update_iso = dt.isoformat()
                    except Exception as e:
                        logger.warning(f"Failed to parse trade_time: {latest}, error: {e}")
                        last_update_iso = latest  # 保留原始字符串

                key = f"{symbol_type}_{timeframe}"
                kline_times[key] = {
                    "symbol_type": symbol_type,
                    "timeframe": timeframe,
                    "last_update": last_update_iso,
                }

        # 添加调度任务的下次运行时间
        job_next_run = {}
        for job in jobs:
            job_next_run[job["id"]] = job.get("next_run")

        # 返回当前时间（带时区）
        current_time_with_tz = datetime.now(SHANGHAI_TZ)

        return {
            "current_time": current_time_with_tz.isoformat(),
            "kline_times": kline_times,
            "scheduled_jobs": {
                "daily_update": {
                    "description": "日线更新 (交易日 15:30)",
                    "next_run": job_next_run.get("daily_update"),
                    "applies_to": ["index_day", "concept_day", "stock_day"]
                },
                "30m_update": {
                    "description": "30分钟更新 (交易时间每30分钟)",
                    "next_run": job_next_run.get("30m_update"),
                    "applies_to": ["index_30m", "concept_30m", "stock_30m"]
                },
                "all_stock_daily": {
                    "description": "全市场日线更新 (交易日 16:00)",
                    "next_run": job_next_run.get("all_stock_daily"),
                    "applies_to": ["all_stock_day"]
                }
            }
        }

    except Exception as e:
        logger.exception("获取更新时间失败")
        raise HTTPException(status_code=500, detail=str(e))
