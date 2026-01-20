from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends

from src.api.dependencies import get_data_service
from src.services.data_pipeline import MarketDataService

router = APIRouter()


@router.get("", response_model=dict[str, Optional[datetime]])
def get_status(
    service: MarketDataService = Depends(get_data_service),
) -> dict[str, Optional[datetime]]:
    """Expose last refresh timestamp used for UI badges."""
    return {"last_refreshed": service.last_refresh_time()}
