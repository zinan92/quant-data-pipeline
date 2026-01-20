from fastapi import APIRouter, HTTPException, Query, Path

from src.services.etf_flow_service import EtfFlowService
from src.utils.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.get("/flows")
def get_etf_flows(limit: int = Query(default=5, ge=1, le=20)):
    """Expose ETF净流入/流出快照，基于本地CSV."""
    service = EtfFlowService()
    try:
        return service.get_flow_summary(top_n=limit)
    except FileNotFoundError as exc:
        logger.error("ETF summary file not found: %s", exc)
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        logger.error("ETF summary file invalid: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Unexpected error when loading ETF flows")
        raise HTTPException(status_code=500, detail="Failed to load ETF flow summary") from exc


@router.get("/kline/{ticker}")
def get_etf_kline(
    ticker: str = Path(..., description="ETF代码，如 510300.SH"),
    limit: int = Query(default=30, ge=5, le=200, description="K线数量"),
):
    """获取单个ETF的K线数据."""
    service = EtfFlowService()
    try:
        klines = service.get_etf_kline(ticker, limit=limit)
        if klines is None:
            raise HTTPException(status_code=404, detail=f"K线数据未找到: {ticker}")
        return {
            "ticker": ticker,
            "count": len(klines),
            "klines": klines,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error when loading ETF kline")
        raise HTTPException(status_code=500, detail="Failed to load ETF kline") from exc
