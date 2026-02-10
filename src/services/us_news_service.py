"""
美股新闻 RSS 服务
从多个财经 RSS 源获取最新快讯
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
import time

from src.utils.logging import get_logger

logger = get_logger(__name__)

# RSS 源列表
RSS_FEEDS = [
    {'url': 'https://www.cnbc.com/id/100003114/device/rss/rss.html', 'source': 'CNBC'},
    {'url': 'https://www.cnbc.com/id/20910258/device/rss/rss.html', 'source': 'CNBC Markets'},
    {'url': 'https://feeds.marketwatch.com/marketwatch/topstories/', 'source': 'MarketWatch'},
    {'url': 'https://finance.yahoo.com/news/rss', 'source': 'Yahoo Finance'},
]


class USNewsService:
    """美股新闻 RSS 聚合"""

    def __init__(self):
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_ts: float = 0
        self._cache_ttl: int = 300  # 5分钟缓存

    def get_news(self, limit: int = 15) -> List[Dict[str, Any]]:
        """
        获取最新财经新闻

        Args:
            limit: 返回条数 (默认 15)

        Returns:
            [{title, source, url, published, published_ts}, ...]
        """
        now = time.time()
        if self._cache and (now - self._cache_ts) < self._cache_ttl:
            return self._cache['items'][:limit]

        items = self._fetch_all()
        # 按时间降序
        items.sort(key=lambda x: x.get('published_ts', 0), reverse=True)
        # 去重 (by title)
        seen_titles: set = set()
        unique: List[Dict[str, Any]] = []
        for item in items:
            title_lower = item['title'].lower().strip()
            if title_lower not in seen_titles:
                seen_titles.add(title_lower)
                unique.append(item)

        self._cache = {'items': unique}
        self._cache_ts = now
        return unique[:limit]

    def _fetch_all(self) -> List[Dict[str, Any]]:
        """从所有 RSS 源获取"""
        try:
            import feedparser
        except ImportError:
            logger.error("feedparser not installed – run: pip install feedparser")
            return []

        items: List[Dict[str, Any]] = []
        for feed_cfg in RSS_FEEDS:
            try:
                feed = feedparser.parse(feed_cfg['url'])
                for entry in feed.entries[:10]:
                    published_ts = 0
                    published_str = ''
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        try:
                            published_ts = time.mktime(entry.published_parsed)
                            published_str = datetime.fromtimestamp(published_ts).strftime('%Y-%m-%d %H:%M')
                        except Exception:
                            pass
                    elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                        try:
                            published_ts = time.mktime(entry.updated_parsed)
                            published_str = datetime.fromtimestamp(published_ts).strftime('%Y-%m-%d %H:%M')
                        except Exception:
                            pass

                    items.append({
                        'title': entry.get('title', ''),
                        'source': feed_cfg['source'],
                        'url': entry.get('link', ''),
                        'published': published_str,
                        'published_ts': published_ts,
                    })
            except Exception as e:
                logger.warning(f"Failed to parse RSS feed {feed_cfg['source']}: {e}")

        return items


# 单例
_us_news_service: Optional[USNewsService] = None


def get_us_news_service() -> USNewsService:
    global _us_news_service
    if _us_news_service is None:
        _us_news_service = USNewsService()
    return _us_news_service
