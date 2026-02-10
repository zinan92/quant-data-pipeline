"""
Real-time price proxy endpoint for Sina Finance API.
"""

import httpx
from fastapi import APIRouter, HTTPException, Query

from src.config import get_settings
from src.exceptions import ServiceUnavailableError
from src.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get("/prices")
async def get_realtime_prices(tickers: str = Query(..., description="Comma-separated ticker symbols")):
    """
    Proxy endpoint for fetching real-time prices from Sina Finance API.

    Args:
        tickers: Comma-separated ticker symbols (e.g., "000001,600000")

    Returns:
        Raw response text from Sina Finance API
    """
    if not tickers:
        raise HTTPException(status_code=400, detail="Tickers parameter is required")

    # Convert tickers to Sina format
    ticker_list = tickers.split(',')
    sina_format = []

    for ticker in ticker_list:
        ticker = ticker.strip()
        if ticker.startswith('6'):
            sina_format.append(f'sh{ticker}')
        elif ticker.startswith('0') or ticker.startswith('3'):
            sina_format.append(f'sz{ticker}')
        else:
            sina_format.append(ticker)

    sina_tickers = ','.join(sina_format)
    url = f'https://hq.sinajs.cn/list={sina_tickers}'

    try:
        # 添加浏览器请求头来避免被新浪API拒绝
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://finance.sina.com.cn/'
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=10.0)
            response.raise_for_status()
            return {"data": response.text}
    except httpx.HTTPStatusError as e:
        logger.exception("Sina API HTTP error")
        detail = str(e) if get_settings().debug else "Internal server error"
        raise HTTPException(status_code=e.response.status_code, detail=detail)
    except httpx.RequestError as e:
        logger.exception("Failed to connect to Sina API")
        raise ServiceUnavailableError(service="sina_realtime_prices", reason=str(e) if get_settings().debug else "Service unavailable")
