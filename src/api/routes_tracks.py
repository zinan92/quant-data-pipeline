"""
自定义赛道 API
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict
from sqlalchemy import select

from ..database import session_scope
from ..models import BoardMapping, SymbolMetadata

# ===========================================
# 自定义赛道配置
# key: 赛道显示名称
# value: 对应的概念板块名称列表（数据库中的board_name）
# ===========================================
CUSTOM_TRACKS: Dict[str, List[str]] = {
    "人形机器人": ["人形机器人"],
    "PCB": ["PCB概念"],
    "液冷": ["液冷服务器"],
    "储能": ["储能"],
}

TRACK_ORDER: List[str] = ["人形机器人", "PCB", "液冷", "储能"]


def get_all_tracks() -> List[Dict]:
    """获取所有赛道配置"""
    result = []
    for track_name in TRACK_ORDER:
        if track_name in CUSTOM_TRACKS:
            result.append({
                "name": track_name,
                "concepts": CUSTOM_TRACKS[track_name]
            })
    return result


def get_track_concepts(track_name: str) -> List[str]:
    """获取某个赛道包含的概念板块"""
    return CUSTOM_TRACKS.get(track_name, [])

router = APIRouter()


class TrackInfo(BaseModel):
    name: str
    concepts: List[str]
    total_stocks: int


class TrackListResponse(BaseModel):
    tracks: List[TrackInfo]


class TrackSymbol(BaseModel):
    ticker: str
    name: str
    industry: Optional[str] = None
    total_mv: Optional[float] = None
    pe_ttm: Optional[float] = None


class TrackDetailResponse(BaseModel):
    name: str
    concepts: List[str]
    symbols: List[TrackSymbol]
    total_count: int


@router.get("", response_model=TrackListResponse)
def list_tracks():
    """
    获取所有自定义赛道列表
    """
    tracks_config = get_all_tracks()
    result = []

    with session_scope() as session:
        for track in tracks_config:
            track_name = track["name"]
            concept_names = track["concepts"]

            # 收集所有概念的成分股
            all_tickers = set()
            for concept_name in concept_names:
                board = session.execute(
                    select(BoardMapping).where(
                        BoardMapping.board_name == concept_name,
                        BoardMapping.board_type == "concept"
                    )
                ).scalar_one_or_none()

                if board and board.constituents:
                    all_tickers.update(board.constituents)

            result.append(TrackInfo(
                name=track_name,
                concepts=concept_names,
                total_stocks=len(all_tickers)
            ))

    return TrackListResponse(tracks=result)


@router.get("/{track_name}", response_model=TrackDetailResponse)
def get_track_detail(track_name: str):
    """
    获取某个赛道的详细信息，包括所有成分股
    """
    if track_name not in CUSTOM_TRACKS:
        raise HTTPException(status_code=404, detail=f"Track '{track_name}' not found")

    concept_names = get_track_concepts(track_name)

    with session_scope() as session:
        # 收集所有概念的成分股
        all_tickers = set()
        for concept_name in concept_names:
            board = session.execute(
                select(BoardMapping).where(
                    BoardMapping.board_name == concept_name,
                    BoardMapping.board_type == "concept"
                )
            ).scalar_one_or_none()

            if board and board.constituents:
                all_tickers.update(board.constituents)

        # 获取股票元数据
        symbols = []
        if all_tickers:
            # 转换ticker格式 (000001 -> 000001.SZ)
            ticker_list = list(all_tickers)

            # 查询元数据
            metas = session.execute(
                select(SymbolMetadata).where(
                    SymbolMetadata.ticker.in_(ticker_list)
                )
            ).scalars().all()

            for meta in metas:
                symbols.append(TrackSymbol(
                    ticker=meta.ticker,
                    name=meta.name or "",
                    industry=meta.industry_lv1,
                    total_mv=meta.total_mv,
                    pe_ttm=meta.pe_ttm
                ))

        # 按市值排序
        symbols.sort(key=lambda x: x.total_mv or 0, reverse=True)

        return TrackDetailResponse(
            name=track_name,
            concepts=concept_names,
            symbols=symbols,
            total_count=len(symbols)
        )


@router.get("/{track_name}/symbols")
def get_track_symbols(track_name: str):
    """
    获取某个赛道的成分股列表（与boards API格式一致，便于复用ChartGrid组件）
    """
    if track_name not in CUSTOM_TRACKS:
        raise HTTPException(status_code=404, detail=f"Track '{track_name}' not found")

    concept_names = get_track_concepts(track_name)

    with session_scope() as session:
        # 收集所有概念的成分股
        all_tickers = set()
        for concept_name in concept_names:
            board = session.execute(
                select(BoardMapping).where(
                    BoardMapping.board_name == concept_name,
                    BoardMapping.board_type == "concept"
                )
            ).scalar_one_or_none()

            if board and board.constituents:
                all_tickers.update(board.constituents)

        # 获取股票元数据
        result = []
        if all_tickers:
            ticker_list = list(all_tickers)

            metas = session.execute(
                select(SymbolMetadata).where(
                    SymbolMetadata.ticker.in_(ticker_list)
                )
            ).scalars().all()

            for meta in metas:
                result.append({
                    "ticker": meta.ticker,
                    "name": meta.name,
                    "industryLv1": meta.industry_lv1,
                    "superCategory": meta.super_category,
                    "totalMv": meta.total_mv,
                    "circMv": meta.circ_mv,
                    "peTtm": meta.pe_ttm,
                    "pb": meta.pb,
                    "concepts": meta.concepts,
                })

        # 按市值排序
        result.sort(key=lambda x: x.get("totalMv") or 0, reverse=True)

        return result
