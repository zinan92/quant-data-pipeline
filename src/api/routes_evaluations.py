"""
K线标注评估 API
用于收集K线训练数据
"""

import re
import base64
from datetime import datetime, date
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, desc

from ..database import session_scope
from ..models import KlineEvaluation

router = APIRouter()

# 截图保存目录
SCREENSHOT_DIR = Path(__file__).parent.parent.parent / "data" / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

# 预设标签关键词映射
TAG_KEYWORDS = {
    # 形态类
    "双底": ["双底", "W底", "w底"],
    "双顶": ["双顶", "M顶", "m顶"],
    "头肩底": ["头肩底"],
    "头肩顶": ["头肩顶"],
    "三角形": ["三角形", "收敛三角", "三角整理"],
    "箱体": ["箱体", "横盘", "震荡区间"],
    "突破": ["突破", "向上突破", "放量突破"],
    "跌破": ["跌破", "向下突破"],

    # 均线类
    "站上均线": ["站上均线", "突破均线", "上穿均线"],
    "跌破均线": ["跌破均线", "下穿均线"],
    "均线多头": ["均线多头", "多头排列"],
    "均线空头": ["均线空头", "空头排列"],
    "金叉": ["金叉", "均线金叉"],
    "死叉": ["死叉", "均线死叉"],

    # MACD类
    "MACD金叉": ["macd金叉", "dif上穿dea", "macd 金叉"],
    "MACD死叉": ["macd死叉", "dif下穿dea", "macd 死叉"],
    "MACD背离": ["macd背离", "底背离", "顶背离", "背离"],
    "MACD零轴上": ["零轴上", "macd零轴上"],
    "MACD零轴下": ["零轴下", "macd零轴下"],

    # 量能类
    "放量": ["放量", "量能放大", "成交量放大"],
    "缩量": ["缩量", "量能萎缩", "成交量萎缩"],
    "地量": ["地量", "极度缩量"],
    "天量": ["天量", "巨量"],

    # K线形态
    "大阳线": ["大阳线", "长阳", "涨停"],
    "大阴线": ["大阴线", "长阴", "跌停"],
    "十字星": ["十字星", "十字线"],
    "锤子线": ["锤子线", "锤头"],
    "吊颈线": ["吊颈线", "上吊线"],

    # 趋势类
    "上升趋势": ["上升趋势", "多头趋势", "上涨趋势"],
    "下降趋势": ["下降趋势", "空头趋势", "下跌趋势"],
    "反转": ["反转", "趋势反转", "见底反转"],
    "回调": ["回调", "回踩", "回落"],
    "反弹": ["反弹", "超跌反弹"],

    # 支撑阻力
    "支撑": ["支撑", "支撑位", "获得支撑"],
    "阻力": ["阻力", "阻力位", "压力位"],

    # 操作建议
    "可追高": ["追高", "可以追", "可追"],
    "低吸": ["低吸", "逢低买入"],
    "观望": ["观望", "等待"],
}


def extract_tags(description: str) -> List[str]:
    """从描述中自动提取标签"""
    if not description:
        return []

    description_lower = description.lower()
    found_tags = []

    for tag, keywords in TAG_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in description_lower:
                if tag not in found_tags:
                    found_tags.append(tag)
                break

    return found_tags


class EvaluationCreate(BaseModel):
    ticker: str = Field(..., description="股票代码")
    stock_name: Optional[str] = Field(None, description="股票名称")
    timeframe: str = Field("day", description="周期")
    kline_end_date: str = Field(..., description="K线截止日期 YYYY-MM-DD")
    description: Optional[str] = Field(None, description="文字描述")
    score: int = Field(..., ge=0, le=10, description="评分0-10")
    screenshot_base64: Optional[str] = Field(None, description="截图Base64编码")
    kline_data: Optional[dict] = Field(None, description="K线数据JSON")
    price_at_eval: Optional[float] = Field(None, description="评估时价格")


class EvaluationResponse(BaseModel):
    id: int
    ticker: str
    stock_name: Optional[str]
    timeframe: str
    eval_date: str
    kline_end_date: str
    description: Optional[str]
    score: int
    tags: Optional[List[str]]
    screenshot_path: Optional[str]
    price_at_eval: Optional[float]
    price_1d: Optional[float]
    price_5d: Optional[float]
    return_1d: Optional[float]
    return_5d: Optional[float]
    verified: bool
    created_at: str

    class Config:
        from_attributes = True


class EvaluationListResponse(BaseModel):
    evaluations: List[EvaluationResponse]
    total: int


@router.post("", response_model=EvaluationResponse)
def create_evaluation(data: EvaluationCreate):
    """创建新的K线评估标注"""

    # 自动提取标签
    tags = extract_tags(data.description) if data.description else []

    # 保存截图
    screenshot_path = None
    if data.screenshot_base64:
        try:
            # 去掉data:image/png;base64,前缀
            base64_data = data.screenshot_base64
            if "," in base64_data:
                base64_data = base64_data.split(",")[1]

            image_data = base64.b64decode(base64_data)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{data.ticker}_{timestamp}.png"
            filepath = SCREENSHOT_DIR / filename

            with open(filepath, "wb") as f:
                f.write(image_data)

            screenshot_path = f"screenshots/{filename}"
        except Exception as e:
            print(f"Failed to save screenshot: {e}")

    eval_date = date.today().isoformat()

    with session_scope() as session:
        evaluation = KlineEvaluation(
            ticker=data.ticker,
            stock_name=data.stock_name,
            timeframe=data.timeframe,
            eval_date=eval_date,
            kline_end_date=data.kline_end_date,
            description=data.description,
            score=data.score,
            tags=tags,
            screenshot_path=screenshot_path,
            kline_data=data.kline_data,
            price_at_eval=data.price_at_eval,
            verified=False,
        )
        session.add(evaluation)
        session.flush()

        return EvaluationResponse(
            id=evaluation.id,
            ticker=evaluation.ticker,
            stock_name=evaluation.stock_name,
            timeframe=evaluation.timeframe,
            eval_date=evaluation.eval_date,
            kline_end_date=evaluation.kline_end_date,
            description=evaluation.description,
            score=evaluation.score,
            tags=evaluation.tags,
            screenshot_path=evaluation.screenshot_path,
            price_at_eval=evaluation.price_at_eval,
            price_1d=evaluation.price_1d,
            price_5d=evaluation.price_5d,
            return_1d=evaluation.return_1d,
            return_5d=evaluation.return_5d,
            verified=evaluation.verified,
            created_at=evaluation.created_at.isoformat() if evaluation.created_at else "",
        )


@router.get("", response_model=EvaluationListResponse)
def list_evaluations(
    ticker: Optional[str] = Query(None, description="按股票代码筛选"),
    min_score: Optional[int] = Query(None, ge=0, le=10, description="最低评分"),
    tag: Optional[str] = Query(None, description="按标签筛选"),
    limit: int = Query(50, ge=1, le=500, description="返回数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
):
    """获取评估列表"""
    with session_scope() as session:
        query = select(KlineEvaluation).order_by(desc(KlineEvaluation.created_at))

        if ticker:
            query = query.where(KlineEvaluation.ticker == ticker)
        if min_score is not None:
            query = query.where(KlineEvaluation.score >= min_score)

        # 获取总数
        count_query = select(KlineEvaluation)
        if ticker:
            count_query = count_query.where(KlineEvaluation.ticker == ticker)
        if min_score is not None:
            count_query = count_query.where(KlineEvaluation.score >= min_score)
        total = len(session.execute(count_query).scalars().all())

        # 分页
        query = query.offset(offset).limit(limit)
        evaluations = session.execute(query).scalars().all()

        # 按标签筛选（JSON字段需要在Python中处理）
        if tag:
            evaluations = [e for e in evaluations if e.tags and tag in e.tags]
            total = len(evaluations)

        return EvaluationListResponse(
            evaluations=[
                EvaluationResponse(
                    id=e.id,
                    ticker=e.ticker,
                    stock_name=e.stock_name,
                    timeframe=e.timeframe,
                    eval_date=e.eval_date,
                    kline_end_date=e.kline_end_date,
                    description=e.description,
                    score=e.score,
                    tags=e.tags,
                    screenshot_path=e.screenshot_path,
                    price_at_eval=e.price_at_eval,
                    price_1d=e.price_1d,
                    price_5d=e.price_5d,
                    return_1d=e.return_1d,
                    return_5d=e.return_5d,
                    verified=e.verified,
                    created_at=e.created_at.isoformat() if e.created_at else "",
                )
                for e in evaluations
            ],
            total=total,
        )


@router.get("/tags")
def list_available_tags():
    """获取所有可用的预设标签"""
    return {"tags": list(TAG_KEYWORDS.keys())}


@router.get("/stats")
def get_evaluation_stats():
    """获取评估统计信息"""
    with session_scope() as session:
        evaluations = session.execute(select(KlineEvaluation)).scalars().all()

        total = len(evaluations)
        score_distribution = {}
        for e in evaluations:
            score_distribution[e.score] = score_distribution.get(e.score, 0) + 1

        actionable = len([e for e in evaluations if e.score >= 8])
        verified = len([e for e in evaluations if e.verified])

        # 计算8分以上的平均收益
        verified_high_score = [e for e in evaluations if e.score >= 8 and e.verified]
        avg_return_1d = None
        avg_return_5d = None
        if verified_high_score:
            returns_1d = [e.return_1d for e in verified_high_score if e.return_1d is not None]
            returns_5d = [e.return_5d for e in verified_high_score if e.return_5d is not None]
            if returns_1d:
                avg_return_1d = sum(returns_1d) / len(returns_1d)
            if returns_5d:
                avg_return_5d = sum(returns_5d) / len(returns_5d)

        return {
            "total": total,
            "actionable": actionable,  # 8分以上
            "verified": verified,
            "score_distribution": score_distribution,
            "avg_return_1d": avg_return_1d,
            "avg_return_5d": avg_return_5d,
        }


@router.get("/{evaluation_id}", response_model=EvaluationResponse)
def get_evaluation(evaluation_id: int):
    """获取单个评估详情"""
    with session_scope() as session:
        evaluation = session.get(KlineEvaluation, evaluation_id)
        if not evaluation:
            raise HTTPException(status_code=404, detail="Evaluation not found")

        return EvaluationResponse(
            id=evaluation.id,
            ticker=evaluation.ticker,
            stock_name=evaluation.stock_name,
            timeframe=evaluation.timeframe,
            eval_date=evaluation.eval_date,
            kline_end_date=evaluation.kline_end_date,
            description=evaluation.description,
            score=evaluation.score,
            tags=evaluation.tags,
            screenshot_path=evaluation.screenshot_path,
            price_at_eval=evaluation.price_at_eval,
            price_1d=evaluation.price_1d,
            price_5d=evaluation.price_5d,
            return_1d=evaluation.return_1d,
            return_5d=evaluation.return_5d,
            verified=evaluation.verified,
            created_at=evaluation.created_at.isoformat() if evaluation.created_at else "",
        )


@router.delete("/{evaluation_id}")
def delete_evaluation(evaluation_id: int):
    """删除评估"""
    with session_scope() as session:
        evaluation = session.get(KlineEvaluation, evaluation_id)
        if not evaluation:
            raise HTTPException(status_code=404, detail="Evaluation not found")

        # 删除截图文件
        if evaluation.screenshot_path:
            filepath = Path(__file__).parent.parent.parent / "data" / evaluation.screenshot_path
            if filepath.exists():
                filepath.unlink()

        session.delete(evaluation)
        return {"message": "Evaluation deleted"}
