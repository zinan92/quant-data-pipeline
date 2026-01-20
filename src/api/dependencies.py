from functools import lru_cache

from fastapi import Depends

from src.config import get_settings
from src.services.data_pipeline import MarketDataService


@lru_cache
def data_service() -> MarketDataService:
    return MarketDataService()


def get_data_service(service: MarketDataService = Depends(data_service)) -> MarketDataService:
    return service
