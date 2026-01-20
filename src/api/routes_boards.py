"""板块映射相关API端点"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import csv
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func

from src.api.dependencies import get_data_service
from src.services.board_mapping_service import BoardMappingService
from src.services.data_pipeline import MarketDataService
from src.database import session_scope
from src.models import IndustryDaily, SymbolMetadata, BoardMapping, SuperCategoryDaily
from src.schemas import SymbolMeta

router = APIRouter()


class BuildMappingsRequest(BaseModel):
    board_types: Optional[List[str]] = ["industry"]  # ['industry', 'concept']


class BuildMappingsResponse(BaseModel):
    status: str
    stats: dict
    message: str


class VerifyChangesRequest(BaseModel):
    board_name: str
    board_type: str = "industry"  # 'industry' or 'concept'


class VerifyChangesResponse(BaseModel):
    board_name: str
    board_type: str
    has_changes: bool
    added: List[str]
    removed: List[str]
    current_count: int
    previous_count: int
    error: Optional[str] = None


class StockConceptsResponse(BaseModel):
    ticker: str
    concepts: List[str]


@router.post("/build", response_model=BuildMappingsResponse)
def build_board_mappings(
    payload: BuildMappingsRequest,
) -> BuildMappingsResponse:
    """
    一次性构建板块映射

    WARNING: 如果包含 'concept'，可能需要1-2小时！
    建议只构建 'industry'（90个板块，约15-20分钟）
    """
    service = BoardMappingService()

    try:
        stats = service.build_all_mappings(board_types=payload.board_types)

        total = sum(stats.values())
        message = f"Successfully built {total} board mappings"

        if 'industry' in stats:
            message += f" (Industry: {stats['industry']})"
        if 'concept' in stats:
            message += f" (Concept: {stats['concept']})"

        return BuildMappingsResponse(
            status="success",
            stats=stats,
            message=message
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to build board mappings: {str(e)}"
        )


@router.post("/verify", response_model=VerifyChangesResponse)
def verify_board_changes(
    payload: VerifyChangesRequest,
) -> VerifyChangesResponse:
    """
    验证单个板块的成分股是否有变化

    快速检查，不重新遍历所有板块
    """
    service = BoardMappingService()

    try:
        result = service.verify_changes(
            board_name=payload.board_name,
            board_type=payload.board_type
        )

        return VerifyChangesResponse(
            board_name=payload.board_name,
            board_type=payload.board_type,
            **result
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to verify board changes: {str(e)}"
        )


@router.get("/concepts/{ticker}", response_model=StockConceptsResponse)
def get_stock_concepts(
    ticker: str,
) -> StockConceptsResponse:
    """
    获取某只股票所属的概念板块列表
    """
    service = BoardMappingService()

    try:
        concepts = service.get_stock_concepts(ticker)
        return StockConceptsResponse(
            ticker=ticker,
            concepts=concepts
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get stock concepts: {str(e)}"
        )


@router.get("/list")
def list_board_mappings(
    board_type: Optional[str] = None,
) -> dict:
    """
    列出所有板块映射

    Args:
        board_type: 筛选类型 ('industry', 'concept', 或 None 表示全部)
    """
    from sqlalchemy import select

    with session_scope() as session:
        stmt = select(BoardMapping)
        if board_type:
            stmt = stmt.where(BoardMapping.board_type == board_type)

        mappings = session.scalars(stmt).all()

        return {
            "total": len(mappings),
            "boards": [
                {
                    "name": m.board_name,
                    "type": m.board_type,
                    "code": m.board_code,
                    "stock_count": len(m.constituents),
                    "last_updated": m.last_updated.isoformat() if m.last_updated else None
                }
                for m in mappings
            ]
        }


def calculate_market_cap_growth(session, board_name: str) -> Dict[str, float | None]:
    """计算板块市值增长率"""
    # 首先从 IndustryDaily 获取板块代码
    latest_date_subq = session.query(
        func.max(IndustryDaily.trade_date)
    ).scalar_subquery()

    board_info = session.query(IndustryDaily).filter(
        IndustryDaily.industry == board_name,
        IndustryDaily.trade_date == latest_date_subq
    ).first()

    if not board_info:
        return {
            "5d": None, "2w": None, "30d": None, "3m": None, "6m": None
        }

    ts_code = board_info.ts_code
    current_mv = board_info.total_mv

    if not current_mv:
        return {
            "5d": None, "2w": None, "30d": None, "3m": None, "6m": None
        }

    # 获取所有历史数据，按日期降序排序
    history = session.query(IndustryDaily).filter(
        IndustryDaily.ts_code == ts_code
    ).order_by(IndustryDaily.trade_date.desc()).limit(150).all()

    # 转换为字典方便查询
    mv_by_date = {rec.trade_date: rec.total_mv for rec in history if rec.total_mv}
    dates = sorted(mv_by_date.keys(), reverse=True)

    if not dates:
        return {
            "5d": None, "2w": None, "30d": None, "3m": None, "6m": None
        }

    latest_date_str = dates[0]
    latest_date = datetime.strptime(latest_date_str, "%Y%m%d")

    def get_growth(days: int) -> float | None:
        target_date = latest_date - timedelta(days=days)
        target_date_str = target_date.strftime("%Y%m%d")

        # 找到最接近目标日期的交易日
        closest_date = None
        for date_str in reversed(dates):
            if date_str <= target_date_str:
                closest_date = date_str
                break

        if closest_date and closest_date in mv_by_date:
            past_mv = mv_by_date[closest_date]
            if past_mv and past_mv > 0:
                return ((current_mv - past_mv) / past_mv) * 100

        return None

    return {
        "5d": get_growth(5),
        "2w": get_growth(14),
        "30d": get_growth(30),
        "3m": get_growth(90),
        "6m": get_growth(180)
    }


@router.get("/super-categories")
def get_super_categories() -> Dict[str, Any]:
    """获取超级行业组分类，按进攻性/防守性分组（包含市值和涨跌幅）"""
    csv_path = Path(__file__).parent.parent.parent / "data" / "super_category_mapping.csv"

    if not csv_path.exists():
        raise HTTPException(status_code=404, detail="Super category mapping file not found")

    with session_scope() as session:
        # 获取最新的超级组每日数据
        latest_date = session.query(
            func.max(SuperCategoryDaily.trade_date)
        ).scalar()

        # 查询所有超级组的最新数据
        daily_data = {}
        if latest_date:
            super_categories_daily = session.query(SuperCategoryDaily).filter(
                SuperCategoryDaily.trade_date == latest_date
            ).all()

            for cat in super_categories_daily:
                daily_data[cat.super_category_name] = {
                    "total_mv": cat.total_mv,
                    "pct_change": cat.pct_change,
                    "trade_date": cat.trade_date
                }

        # 读取CSV并分组
        offensive_categories = {}  # 进攻性 > 50
        defensive_categories = {}  # 防守性 <= 50

        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                category_name = row['超级行业组']
                score = int(row['进攻性评分'])
                industry = row['行业名称']
                note = row['备注']

                # 选择分组
                target_dict = offensive_categories if score > 50 else defensive_categories

                # 初始化分组
                if category_name not in target_dict:
                    # 获取每日数据
                    cat_daily = daily_data.get(category_name, {})

                    target_dict[category_name] = {
                        "name": category_name,
                        "score": score,
                        "industries": [],
                        "total_mv": cat_daily.get("total_mv"),
                        "pct_change": cat_daily.get("pct_change"),
                        "trade_date": cat_daily.get("trade_date")
                    }

                # 添加行业
                target_dict[category_name]["industries"].append({
                    "name": industry,
                    "note": note
                })

        # 转换为列表并按评分排序
        offensive_list = sorted(offensive_categories.values(), key=lambda x: x['score'], reverse=True)
        defensive_list = sorted(defensive_categories.values(), key=lambda x: x['score'], reverse=True)

        return {
            "offensive": offensive_list,  # 进攻性板块（评分 > 50）
            "defensive": defensive_list,  # 防守性板块（评分 <= 50）
            "total_categories": len(offensive_list) + len(defensive_list),
            "offensive_count": len(offensive_list),
            "defensive_count": len(defensive_list),
            "last_update_time": latest_date  # 数据最后更新时间
        }

# Helper to load symbols for a board (industry priority)
def _load_board_symbols(session, board_name: str) -> list[SymbolMetadata]:
    """
    获取板块成分股

    优先级:
    1. BoardMapping 表（如果有数据）
    2. 从 IndustryDaily 获取 ts_code，然后调用 Tushare API 获取同花顺成分股
    3. 回退到 industry_lv1（现在存储的是同花顺行业，由 update_industry_daily.py 维护）
    """
    # 1. 尝试从 BoardMapping 获取
    board_mapping = session.query(BoardMapping).filter(
        BoardMapping.board_name == board_name,
        BoardMapping.board_type == "industry"
    ).first()

    if board_mapping and board_mapping.constituents:
        return session.query(SymbolMetadata).filter(
            SymbolMetadata.ticker.in_(board_mapping.constituents)
        ).all()

    # 2. 从同花顺 API 获取成分股（使用 IndustryDaily 中的 ts_code）
    industry_daily = session.query(IndustryDaily).filter(
        IndustryDaily.industry == board_name
    ).first()

    if industry_daily and industry_daily.ts_code:
        try:
            from src.services.tushare_client import TushareClient
            from src.config import get_settings

            settings = get_settings()
            client = TushareClient(
                token=settings.tushare_token,
                points=settings.tushare_points
            )

            # 获取同花顺成分股
            members_df = client.fetch_ths_member(ts_code=industry_daily.ts_code)

            if not members_df.empty:
                code_field = 'con_code' if 'con_code' in members_df.columns else 'code'
                tickers = set()
                for stock_code in members_df[code_field].dropna():
                    # 标准化股票代码（去掉交易所后缀）
                    if '.' in str(stock_code):
                        ticker = str(stock_code).split('.')[0]
                    else:
                        ticker = str(stock_code)
                    tickers.add(ticker)

                if tickers:
                    return session.query(SymbolMetadata).filter(
                        SymbolMetadata.ticker.in_(list(tickers))
                    ).all()
        except Exception as e:
            import logging
            logging.warning(f"Failed to fetch THS members for {board_name}: {e}")

    # 3. 回退到 industry_lv1（现在存储的是同花顺行业）
    symbols = session.query(SymbolMetadata).filter(
        SymbolMetadata.industry_lv1 == board_name
    ).all()

    if not symbols:
        symbols = session.query(SymbolMetadata).filter(
            SymbolMetadata.industry_lv2 == board_name
        ).all()

    if not symbols:
        symbols = session.query(SymbolMetadata).filter(
            SymbolMetadata.industry_lv3 == board_name
        ).all()

    return symbols


@router.get("/{board_name}/stats")
def get_board_stats(board_name: str) -> Dict[str, Any]:
    """获取板块详细统计信息"""
    with session_scope() as session:
        # 获取最新交易日的板块数据
        latest_date_subq = session.query(
            func.max(IndustryDaily.trade_date)
        ).scalar_subquery()

        board_daily = session.query(IndustryDaily).filter(
            IndustryDaily.industry == board_name,
            IndustryDaily.trade_date == latest_date_subq
        ).first()

        if not board_daily:
            raise HTTPException(status_code=404, detail=f"板块 '{board_name}' 不存在")

        symbols = _load_board_symbols(session, board_name)

        # 计算 PE 中位数
        pe_values = [s.pe_ttm for s in symbols if s.pe_ttm is not None and s.pe_ttm > 0]
        pe_median = None
        if pe_values:
            pe_values.sort()
            n = len(pe_values)
            if n % 2 == 0:
                pe_median = (pe_values[n//2 - 1] + pe_values[n//2]) / 2
            else:
                pe_median = pe_values[n//2]

        # 找到龙头公司（按市值）
        leading_company = None
        if symbols:
            symbols_with_mv = [s for s in symbols if s.total_mv is not None]
            if symbols_with_mv:
                symbols_with_mv.sort(key=lambda x: x.total_mv, reverse=True)
                leader = symbols_with_mv[0]
                leading_company = {
                    "ticker": leader.ticker,
                    "name": leader.name,
                    "market_cap": leader.total_mv
                }

        # 计算市值增长
        mv_growth = calculate_market_cap_growth(session, board_name)

        # 构建响应
        return {
            "板块名称": board_name,
            "板块代码": board_daily.ts_code,
            "股票数量": board_daily.company_num,
            "上涨家数": board_daily.up_count or 0,
            "下跌家数": board_daily.down_count or 0,
            "平仓家数": board_daily.company_num - (board_daily.up_count or 0) - (board_daily.down_count or 0),
            "加权平均PE": board_daily.industry_pe,
            "PE中位数": round(pe_median, 2) if pe_median else None,
            "总市值": board_daily.total_mv,
            "涨跌幅": board_daily.pct_change,
            "龙头公司": leading_company,
            "市值增长": {
                "5天": round(mv_growth["5d"], 2) if mv_growth["5d"] is not None else None,
                "2周": round(mv_growth["2w"], 2) if mv_growth["2w"] is not None else None,
                "30天": round(mv_growth["30d"], 2) if mv_growth["30d"] is not None else None,
                "3个月": round(mv_growth["3m"], 2) if mv_growth["3m"] is not None else None,
                "6个月": round(mv_growth["6m"], 2) if mv_growth["6m"] is not None else None
            },
            "交易日期": board_daily.trade_date
        }


@router.get("/{board_name}/symbols", response_model=list[SymbolMeta])
def list_board_symbols(board_name: str) -> list[SymbolMeta]:
    """获取板块成分股（优先使用映射表，其次 industry_lv1/2/3）"""
    with session_scope() as session:
        symbols = _load_board_symbols(session, board_name)
        return [SymbolMeta.model_validate(s) for s in symbols]


@router.get("/super-categories/daily")
def get_super_categories_daily(trade_date: Optional[str] = None) -> Dict[str, Any]:
    """获取超级行业组的每日数据（包含市值和涨跌幅）

    Args:
        trade_date: 交易日期 YYYYMMDD，如果为空则使用最新日期

    Returns:
        {
            "trade_date": "20251105",
            "offensive": [...],  # 进攻性板块数据
            "defensive": [...],  # 防守性板块数据
        }
    """
    with session_scope() as session:
        # 如果没有指定日期，使用最新日期
        if not trade_date:
            trade_date = session.query(
                func.max(SuperCategoryDaily.trade_date)
            ).scalar()

            if not trade_date:
                raise HTTPException(
                    status_code=404,
                    detail="No super category data found"
                )

        # 获取指定日期的所有超级组数据
        super_categories = session.query(SuperCategoryDaily).filter(
            SuperCategoryDaily.trade_date == trade_date
        ).all()

        if not super_categories:
            raise HTTPException(
                status_code=404,
                detail=f"No data found for trade_date {trade_date}"
            )

        # 分组：进攻性 vs 防守性
        offensive = []
        defensive = []

        for cat in super_categories:
            cat_data = {
                "name": cat.super_category_name,
                "score": cat.score,
                "total_mv": cat.total_mv,
                "pct_change": cat.pct_change,
                "industry_count": cat.industry_count,
                "up_count": cat.up_count,
                "down_count": cat.down_count,
                "avg_pe": cat.avg_pe,
                "leading_industry": cat.leading_industry,
            }

            if cat.score > 50:
                offensive.append(cat_data)
            else:
                defensive.append(cat_data)

        # 按评分排序
        offensive.sort(key=lambda x: x['score'], reverse=True)
        defensive.sort(key=lambda x: x['score'], reverse=True)

        return {
            "trade_date": trade_date,
            "offensive": offensive,
            "defensive": defensive,
            "total_categories": len(super_categories),
            "offensive_count": len(offensive),
            "defensive_count": len(defensive),
        }


@router.get("/market-style-index")
def get_market_style_index(trade_date: Optional[str] = None) -> Dict[str, Any]:
    """计算市场资金风格指数（进攻vs防守）

    使用资金流向加权法：
    - 只统计上涨的超级组（资金流入）
    - 指数 = Σ(评分ᵢ × 市值ᵢ × 涨跌幅ᵢ) / Σ(市值ᵢ × 涨跌幅ᵢ)
    - 范围：10-95（对应最低到最高的进攻性评分）

    Args:
        trade_date: 交易日期 YYYYMMDD，如果为空则使用最新日期

    Returns:
        {
            "index": 75.5,  # 进攻防守指数
            "trade_date": "20251105",
            "interpretation": "偏进攻",
            "details": {
                "rising_categories": 10,
                "falling_categories": 4,
                "total_rising_mv": 1234567,
                "offensive_strength": 0.65,
                "defensive_strength": 0.35
            },
            "top_performers": [...]
        }
    """
    with session_scope() as session:
        # 如果没有指定日期，使用最新日期
        if not trade_date:
            trade_date = session.query(
                func.max(SuperCategoryDaily.trade_date)
            ).scalar()

            if not trade_date:
                raise HTTPException(
                    status_code=404,
                    detail="No super category data found"
                )

        # 获取所有超级组数据
        super_categories = session.query(SuperCategoryDaily).filter(
            SuperCategoryDaily.trade_date == trade_date
        ).all()

        if not super_categories:
            raise HTTPException(
                status_code=404,
                detail=f"No data found for trade_date {trade_date}"
            )

        # 计算资金流向加权指数
        rising_categories = []
        falling_categories = []

        numerator = 0  # Σ(评分 × 市值 × 涨跌幅)
        denominator = 0  # Σ(市值 × 涨跌幅)

        offensive_inflow = 0  # 进攻性板块资金流入
        defensive_inflow = 0  # 防守性板块资金流入
        total_inflow = 0

        for cat in super_categories:
            # 跳过涨跌幅为None的数据
            if cat.pct_change is None:
                continue

            # 计算资金流入量（市值变化）= 市值 × 涨跌幅
            money_flow = cat.total_mv * cat.pct_change

            if cat.pct_change > 0:
                # 上涨的板块（资金流入）
                rising_categories.append({
                    "name": cat.super_category_name,
                    "score": cat.score,
                    "pct_change": cat.pct_change,
                    "total_mv": cat.total_mv,
                    "money_flow": money_flow
                })

                # 累加到加权指数计算
                weight = money_flow  # 使用资金流入量作为权重
                numerator += cat.score * weight
                denominator += weight
                total_inflow += money_flow

                # 分类统计进攻/防守资金
                if cat.score > 50:
                    offensive_inflow += money_flow
                else:
                    defensive_inflow += money_flow

            else:
                # 下跌的板块（资金流出）
                falling_categories.append({
                    "name": cat.super_category_name,
                    "score": cat.score,
                    "pct_change": cat.pct_change,
                    "total_mv": cat.total_mv
                })

        # 计算最终指数
        if denominator > 0:
            index = numerator / denominator
        else:
            # 没有上涨的板块，极度防守
            index = 0

        # 解释指数
        if index >= 80:
            interpretation = "极度进攻"
        elif index >= 65:
            interpretation = "偏进攻"
        elif index >= 45:
            interpretation = "均衡"
        elif index >= 30:
            interpretation = "偏防守"
        else:
            interpretation = "极度防守"

        # 计算进攻/防守资金占比
        offensive_strength = offensive_inflow / total_inflow if total_inflow > 0 else 0
        defensive_strength = defensive_inflow / total_inflow if total_inflow > 0 else 0

        # 按资金流入量排序
        rising_categories.sort(key=lambda x: x['money_flow'], reverse=True)

        return {
            "index": round(index, 2),
            "trade_date": trade_date,
            "interpretation": interpretation,
            "details": {
                "rising_categories": len(rising_categories),
                "falling_categories": len(falling_categories),
                "total_rising_mv": round(total_inflow / 1e4, 2),  # 转换为亿元
                "offensive_strength": round(offensive_strength, 4),
                "defensive_strength": round(defensive_strength, 4),
            },
            "top_performers": rising_categories[:5],  # 资金流入最多的5个板块
            "worst_performers": falling_categories[:5] if falling_categories else []
        }
