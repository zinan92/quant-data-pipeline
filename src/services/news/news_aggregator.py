"""
新闻聚合器
- 合并多数据源
- 去重
- 关键词过滤
- 新消息追踪
"""
import hashlib
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timedelta
from collections import deque

from .news_service import NewsService, get_news_service
from src.utils.logging import get_logger

logger = get_logger(__name__)


class NewsAggregator:
    """新闻聚合器"""
    
    def __init__(
        self,
        news_service: Optional[NewsService] = None,
        history_size: int = 500,
    ):
        self.news_service = news_service or get_news_service()
        self._seen_hashes: Set[str] = set()
        self._history: deque = deque(maxlen=history_size)
        self._keywords: List[str] = []
        self._exclude_keywords: List[str] = []
    
    def _hash_news(self, news: Dict[str, Any]) -> str:
        """生成新闻的唯一哈希"""
        content = f"{news.get('source', '')}{news.get('title', '')}{news.get('content', '')[:100]}"
        return hashlib.md5(content.encode()).hexdigest()[:16]
    
    def set_keywords(
        self,
        include: Optional[List[str]] = None,
        exclude: Optional[List[str]] = None
    ):
        """
        设置关键词过滤
        
        Args:
            include: 包含关键词（任一匹配即通过）
            exclude: 排除关键词（任一匹配即排除）
        """
        if include is not None:
            self._keywords = [k.lower() for k in include]
        if exclude is not None:
            self._exclude_keywords = [k.lower() for k in exclude]
        
        logger.info(f"Keywords set: include={self._keywords}, exclude={self._exclude_keywords}")
    
    def _matches_filter(self, news: Dict[str, Any]) -> bool:
        """检查新闻是否匹配过滤条件"""
        text = f"{news.get('title', '')} {news.get('content', '')}".lower()
        
        # 排除关键词检查
        for kw in self._exclude_keywords:
            if kw in text:
                return False
        
        # 包含关键词检查（如果设置了）
        if self._keywords:
            for kw in self._keywords:
                if kw in text:
                    return True
            return False
        
        return True
    
    def fetch_latest(
        self,
        sources: Optional[List[str]] = None,
        limit: int = 30,
        only_new: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        获取最新快讯
        
        Args:
            sources: 数据源列表，默认 ['cls', 'ths']
            limit: 返回条数
            only_new: 仅返回新消息（未见过的）
            
        Returns:
            新闻列表
        """
        if sources is None:
            sources = ['cls', 'ths']
        
        all_news = []
        
        for source in sources:
            try:
                news = self.news_service.fetch_news(source=source, limit=limit)
                all_news.extend(news)
            except Exception as e:
                logger.error(f"Error fetching from {source}: {e}")
        
        # 去重
        unique_news = []
        seen_in_batch = set()
        
        for news in all_news:
            news_hash = self._hash_news(news)
            
            # 批次内去重
            if news_hash in seen_in_batch:
                continue
            seen_in_batch.add(news_hash)
            
            # 历史去重（如果only_new）
            if only_new and news_hash in self._seen_hashes:
                continue
            
            # 关键词过滤
            if not self._matches_filter(news):
                continue
            
            # 标记为已见
            news['hash'] = news_hash
            news['is_new'] = news_hash not in self._seen_hashes
            self._seen_hashes.add(news_hash)
            
            unique_news.append(news)
        
        # 按时间排序
        unique_news.sort(key=lambda x: x.get('time', ''), reverse=True)
        
        # 更新历史
        for news in unique_news[:limit]:
            self._history.append(news)
        
        return unique_news[:limit]
    
    def get_new_alerts(
        self,
        sources: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        获取新的快讯提醒（仅未见过的）
        适合定时轮询使用
        
        Returns:
            新消息列表
        """
        return self.fetch_latest(sources=sources, only_new=True)
    
    def get_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取历史记录"""
        return list(self._history)[-limit:]
    
    def clear_history(self):
        """清空历史记录（重新开始追踪）"""
        self._seen_hashes.clear()
        self._history.clear()
        logger.info("News history cleared")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            'total_seen': len(self._seen_hashes),
            'history_size': len(self._history),
            'keywords': self._keywords,
            'exclude_keywords': self._exclude_keywords,
        }


# 单例
_aggregator: Optional[NewsAggregator] = None

def get_news_aggregator() -> NewsAggregator:
    """获取聚合器单例"""
    global _aggregator
    if _aggregator is None:
        _aggregator = NewsAggregator()
    return _aggregator
