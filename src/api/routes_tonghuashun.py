"""
API routes for Tonghuashun board data
"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict
from pydantic import BaseModel
from src.services.tonghuashun_service import tonghuashun_service


router = APIRouter(prefix="/ths", tags=["tonghuashun"])


class BoardData(BaseModel):
    """Board data response model"""
    code: str
    name: str
    change_pct: float  # 涨幅 (%)
    money_inflow: float  # 主力金额 (亿元)
    up_count: int  # 涨家数
    down_count: int  # 跌家数
    turnover: float  # 成交额 (亿元)
    volume: float  # 成交量 (万手)
    open: float  # 今开
    high: float  # 最高
    low: float  # 最低
    prev_close: float  # 昨收
    rank: int  # 涨幅排名
    total_boards: int  # 板块总数
    update_time: str  # 更新时间


class BoardListResponse(BaseModel):
    """Board list response model"""
    boards: List[BoardData]
    total: int


class BoardNameItem(BaseModel):
    """Board name and code"""
    name: str
    code: str


class BoardNamesResponse(BaseModel):
    """Board names list response"""
    boards: List[BoardNameItem]
    total: int


@router.get("/concepts/names", response_model=BoardNamesResponse)
async def get_concept_names():
    """
    Get list of all concept board names and codes (372 boards)

    Returns:
        List of concept board names and codes
    """
    try:
        df = tonghuashun_service.get_all_concept_boards()

        boards = []
        for _, row in df.iterrows():
            boards.append({
                'name': row['name'],
                'code': row['code']
            })

        return {
            'boards': boards,
            'total': len(boards)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取概念板块列表失败: {str(e)}")


@router.get("/industries/names", response_model=BoardNamesResponse)
async def get_industry_names():
    """
    Get list of all industry board names and codes (90 boards)

    Returns:
        List of industry board names and codes
    """
    try:
        df = tonghuashun_service.get_all_industry_boards()

        boards = []
        for _, row in df.iterrows():
            boards.append({
                'name': row['name'],
                'code': row['code']
            })

        return {
            'boards': boards,
            'total': len(boards)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取行业板块列表失败: {str(e)}")


@router.get("/concepts/{name}", response_model=BoardData)
async def get_concept_board(name: str):
    """
    Get real-time data for a single concept board

    Args:
        name: Board name (e.g., "先进封装")

    Returns:
        Board real-time data
    """
    try:
        # Get board code first
        df_names = tonghuashun_service.get_all_concept_boards()
        board_row = df_names[df_names['name'] == name]

        if board_row.empty:
            raise HTTPException(status_code=404, detail=f"概念板块 '{name}' 不存在")

        code = board_row.iloc[0]['code']

        # Get detailed data
        raw_data = tonghuashun_service.get_concept_board_info(name)

        if not raw_data:
            raise HTTPException(status_code=500, detail=f"获取板块 '{name}' 数据失败")

        # Parse and return
        parsed_data = tonghuashun_service.parse_board_data(code, name, raw_data)
        return parsed_data

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取概念板块数据失败: {str(e)}")


@router.get("/industries/{name}", response_model=BoardData)
async def get_industry_board(name: str):
    """
    Get real-time data for a single industry board

    Args:
        name: Board name (e.g., "半导体")

    Returns:
        Board real-time data
    """
    try:
        # Get board code first
        df_names = tonghuashun_service.get_all_industry_boards()
        board_row = df_names[df_names['name'] == name]

        if board_row.empty:
            raise HTTPException(status_code=404, detail=f"行业板块 '{name}' 不存在")

        code = board_row.iloc[0]['code']

        # Get detailed data
        raw_data = tonghuashun_service.get_industry_board_info(name)

        if not raw_data:
            raise HTTPException(status_code=500, detail=f"获取板块 '{name}' 数据失败")

        # Parse and return
        parsed_data = tonghuashun_service.parse_board_data(code, name, raw_data)
        return parsed_data

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取行业板块数据失败: {str(e)}")


@router.get("/concepts", response_model=BoardListResponse)
async def get_all_concepts(
    limit: int = Query(default=20, ge=1, le=100, description="返回结果数量限制"),
    sort_by: str = Query(default="change_pct", description="排序字段 (change_pct, money_inflow, turnover)"),
    ascending: bool = Query(default=False, description="是否升序排列")
):
    """
    Get real-time data for all concept boards (372 boards)

    Warning:
        This endpoint takes 5-10 minutes to complete as it fetches data for all 372 boards
        Consider using cached data or background tasks for production

    Args:
        limit: Number of results to return (1-100)
        sort_by: Sort field (change_pct, money_inflow, turnover)
        ascending: Sort order

    Returns:
        List of concept board data
    """
    try:
        # Get all concept data
        all_data = tonghuashun_service.get_all_concept_realtime_data()

        # Sort
        all_data.sort(key=lambda x: x.get(sort_by, 0), reverse=not ascending)

        # Limit
        limited_data = all_data[:limit]

        return {
            'boards': limited_data,
            'total': len(all_data)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取概念板块数据失败: {str(e)}")


@router.get("/industries", response_model=BoardListResponse)
async def get_all_industries(
    limit: int = Query(default=20, ge=1, le=100, description="返回结果数量限制"),
    sort_by: str = Query(default="change_pct", description="排序字段 (change_pct, money_inflow, turnover)"),
    ascending: bool = Query(default=False, description="是否升序排列")
):
    """
    Get real-time data for all industry boards (90 boards)

    Note:
        This endpoint takes 1-2 minutes to complete as it fetches data for all 90 boards

    Args:
        limit: Number of results to return (1-100)
        sort_by: Sort field (change_pct, money_inflow, turnover)
        ascending: Sort order

    Returns:
        List of industry board data
    """
    try:
        # Get all industry data
        all_data = tonghuashun_service.get_all_industry_realtime_data()

        # Sort
        all_data.sort(key=lambda x: x.get(sort_by, 0), reverse=not ascending)

        # Limit
        limited_data = all_data[:limit]

        return {
            'boards': limited_data,
            'total': len(all_data)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取行业板块数据失败: {str(e)}")
