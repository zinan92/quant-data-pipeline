from typing import List, Dict, Any

from fastapi import APIRouter, Depends

from src.api.dependencies import get_data_service
from src.schemas import SymbolMeta
from src.services.data_pipeline import MarketDataService

router = APIRouter()

@router.get("", response_model=List[SymbolMeta])
def list_symbols(service: MarketDataService = Depends(get_data_service)) -> List[SymbolMeta]:
    """Return watchlist metadata sorted by market cap."""
    return service.list_symbols()


@router.get("/search")
def search_symbols(q: str) -> List[SymbolMeta]:
    """搜索股票（支持ticker或名称）"""
    from src.database import session_scope
    from src.models import SymbolMetadata

    with session_scope() as session:
        # 搜索ticker或名称包含查询字符串的股票
        symbols = session.query(SymbolMetadata).filter(
            (SymbolMetadata.ticker.like(f"%{q}%")) |
            (SymbolMetadata.name.like(f"%{q}%"))
        ).limit(20).all()

        return [SymbolMeta.model_validate(s) for s in symbols]


@router.get("/industries")
def list_industries(service: MarketDataService = Depends(get_data_service)) -> Dict[str, Any]:
    """Return list of industries from database (Tushare 90 industries with OHLC data)."""
    from src.database import session_scope
    from src.models import IndustryDaily
    from sqlalchemy import func

    with session_scope() as session:
        # 获取最新交易日的数据
        latest_date = session.query(
            func.max(IndustryDaily.trade_date)
        ).scalar()

        # 查询最新交易日的所有行业数据
        industries = session.query(IndustryDaily).filter(
            IndustryDaily.trade_date == latest_date
        ).all()

        # 构建结果
        result = []
        for ind in industries:
            result.append({
                "板块名称": ind.industry,
                "板块代码": ind.ts_code,
                "股票数量": ind.company_num,
                "总市值": ind.total_mv if ind.total_mv else 0,
                "涨跌幅": float(ind.pct_change),
                "上涨家数": ind.up_count if ind.up_count is not None else 0,
                "下跌家数": ind.down_count if ind.down_count is not None else 0,
                "行业PE": ind.industry_pe,
                "收盘指数": float(ind.close),
                "领涨股": ind.lead_stock,
                "领涨股涨跌幅": float(ind.pct_change_stock) if ind.pct_change_stock else None,
                "净流入资金": float(ind.net_amount) if ind.net_amount else None,
                "交易日期": ind.trade_date
            })

        # 按涨跌幅降序排序
        result.sort(key=lambda x: x["涨跌幅"], reverse=True)

        return {
            "data": result,
            "last_update_time": latest_date
        }
