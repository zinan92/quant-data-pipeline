"""
财经新闻情绪分析 API
"""
from fastapi import APIRouter, Query
from typing import Dict, List, Optional
from pydantic import BaseModel

from src.config import get_settings
from src.exceptions import DatabaseError
from src.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/sentiment", tags=["sentiment"])


class NewsItem(BaseModel):
    title: str
    sentiment: str
    sentiment_score: float
    confidence: float
    related_sectors: List[str]
    related_stocks: List[str]
    publish_time: Optional[str]
    source: str


class HotSector(BaseModel):
    sector: str
    count: int


class SentimentAnalysis(BaseModel):
    analyzed: int
    positive: int
    negative: int
    neutral: int
    sentiment_ratio: float
    items: List[NewsItem]
    hot_sectors: List[HotSector]


@router.get("/analyze", response_model=SentimentAnalysis)
async def analyze_news_sentiment(
    limit: int = Query(default=50, le=100, description="分析新闻数量")
):
    """
    分析最近新闻的情绪
    
    Returns:
        - positive/negative/neutral: 各类新闻数量
        - sentiment_ratio: 多空比 (正面/(正面+负面))
        - items: 新闻详情及分析结果
        - hot_sectors: 热门行业
    """
    try:
        from src.services.news_sentiment import get_news_sentiment_analysis
        return get_news_sentiment_analysis(limit)
    except Exception as e:
        logger.exception("分析新闻情绪失败")
        raise DatabaseError(operation="analyze_news_sentiment", reason=str(e) if get_settings().debug else "Internal server error")


@router.get("/analyze-text")
async def analyze_text_sentiment(text: str = Query(..., description="要分析的文本")):
    """
    分析单条文本的情绪
    """
    try:
        from src.services.news_sentiment import NewsSentimentAnalyzer
        analyzer = NewsSentimentAnalyzer()
        try:
            result = analyzer.analyze_news({'title': text, 'content': text})
            return result
        finally:
            analyzer.close()
    except Exception as e:
        logger.exception("分析文本情绪失败")
        raise DatabaseError(operation="analyze_text_sentiment", reason=str(e) if get_settings().debug else "Internal server error")


@router.get("/market-mood")
async def get_market_mood():
    """
    获取市场情绪指标
    
    基于最近50条新闻计算市场情绪
    """
    try:
        from src.services.news_sentiment import get_news_sentiment_analysis
        analysis = get_news_sentiment_analysis(50)
        
        ratio = analysis.get('sentiment_ratio', 0.5)
        
        if ratio > 0.7:
            mood = '极度乐观'
            emoji = '🚀'
        elif ratio > 0.55:
            mood = '偏乐观'
            emoji = '😊'
        elif ratio > 0.45:
            mood = '中性'
            emoji = '😐'
        elif ratio > 0.3:
            mood = '偏悲观'
            emoji = '😟'
        else:
            mood = '极度悲观'
            emoji = '😱'
        
        return {
            'mood': mood,
            'emoji': emoji,
            'ratio': ratio,
            'positive_count': analysis['positive'],
            'negative_count': analysis['negative'],
            'hot_sectors': analysis['hot_sectors']
        }
        
    except Exception as e:
        logger.exception("获取市场情绪指标失败")
        raise DatabaseError(operation="get_market_mood", reason=str(e) if get_settings().debug else "Internal server error")
