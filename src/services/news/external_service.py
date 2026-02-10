"""
外部信息流服务
整合 Twitter 和 RSS feeds
"""
import subprocess
import json
from typing import List, Dict, Any, Optional
from datetime import datetime

from src.utils.logging import get_logger

logger = get_logger(__name__)


class ExternalInfoService:
    """外部信息流服务（Twitter + RSS）"""
    
    # 推荐关注的财经 Twitter 账号
    RECOMMENDED_TWITTER_ACCOUNTS = [
        # 宏观/市场
        'zaborsky',       # Peter Zaborsky - 宏观
        'DeItaone',       # Walter Bloomberg - 快讯
        'unusual_whales', # 异动监控
        'CNBC',           # CNBC
        'MarketWatch',    # MarketWatch
        'WSJ',            # Wall Street Journal
        'business',       # Bloomberg Business
        'Reuters',        # Reuters
        # AI/科技
        'sama',           # Sam Altman
        'elonmusk',       # Elon Musk
        'sataborsky',     # Satya Nadella
        'ylecun',         # Yann LeCun
        # 中国市场
        'CGTNOfficial',   # CGTN
        'XHNews',         # 新华社
    ]
    
    # 推荐的 RSS feeds
    RECOMMENDED_RSS_FEEDS = [
        # 财经
        {'name': 'Bloomberg Markets', 'url': 'https://feeds.bloomberg.com/markets/news.rss'},
        {'name': 'Reuters Business', 'url': 'https://feeds.reuters.com/reuters/businessNews'},
        {'name': 'WSJ Markets', 'url': 'https://feeds.wsj.com/xml/rss/3_7031.xml'},
        # 科技
        {'name': 'TechCrunch', 'url': 'https://techcrunch.com/feed/'},
        {'name': 'The Verge', 'url': 'https://www.theverge.com/rss/index.xml'},
        # 中文
        {'name': '36氪', 'url': 'https://36kr.com/feed'},
        {'name': '虎嗅', 'url': 'https://www.huxiu.com/rss/0.xml'},
    ]
    
    def __init__(self):
        self._bird_available = self._check_bird()
        self._blogwatcher_available = self._check_blogwatcher()
    
    def _check_bird(self) -> bool:
        """检查 bird CLI 是否可用"""
        try:
            result = subprocess.run(
                ['bird', 'whoami'],
                capture_output=True,
                text=True,
                timeout=10
            )
            available = result.returncode == 0 or '@' in result.stdout
            if available:
                logger.info("bird CLI available")
            return available
        except Exception as e:
            logger.warning(f"bird CLI not available: {e}")
            return False
    
    def _check_blogwatcher(self) -> bool:
        """检查 blogwatcher CLI 是否可用"""
        try:
            result = subprocess.run(
                ['blogwatcher', '--help'],
                capture_output=True,
                text=True,
                timeout=5
            )
            available = result.returncode == 0
            if available:
                logger.info("blogwatcher CLI available")
            return available
        except Exception as e:
            logger.warning(f"blogwatcher CLI not available: {e}")
            return False
    
    def fetch_twitter_timeline(
        self,
        username: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        获取 Twitter 用户时间线
        
        Args:
            username: Twitter 用户名（不含@）
            limit: 返回条数
        """
        if not self._bird_available:
            logger.warning("bird CLI not available")
            return []
        
        try:
            result = subprocess.run(
                ['bird', 'timeline', username, '--limit', str(limit), '--json'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                logger.error(f"bird timeline failed: {result.stderr}")
                return []
            
            # 解析 JSON 输出
            tweets = []
            for line in result.stdout.strip().split('\n'):
                if line:
                    try:
                        tweet = json.loads(line)
                        tweets.append({
                            'source': 'twitter',
                            'source_name': f'@{username}',
                            'title': '',
                            'content': tweet.get('text', ''),
                            'time': tweet.get('created_at', ''),
                            'url': tweet.get('url', ''),
                            'author': username,
                            'likes': tweet.get('favorite_count', 0),
                            'retweets': tweet.get('retweet_count', 0),
                        })
                    except json.JSONDecodeError:
                        continue
            
            return tweets[:limit]
            
        except Exception as e:
            logger.error(f"Error fetching Twitter timeline for {username}: {e}")
            return []
    
    def search_twitter(
        self,
        query: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        搜索 Twitter
        
        Args:
            query: 搜索关键词
            limit: 返回条数
        """
        if not self._bird_available:
            logger.warning("bird CLI not available")
            return []
        
        try:
            result = subprocess.run(
                ['bird', 'search', query, '--limit', str(limit), '--json'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                logger.error(f"bird search failed: {result.stderr}")
                return []
            
            tweets = []
            for line in result.stdout.strip().split('\n'):
                if line:
                    try:
                        tweet = json.loads(line)
                        tweets.append({
                            'source': 'twitter',
                            'source_name': 'Twitter Search',
                            'title': '',
                            'content': tweet.get('text', ''),
                            'time': tweet.get('created_at', ''),
                            'url': tweet.get('url', ''),
                            'author': tweet.get('user', {}).get('screen_name', ''),
                            'query': query,
                        })
                    except json.JSONDecodeError:
                        continue
            
            return tweets[:limit]
            
        except Exception as e:
            logger.error(f"Error searching Twitter for '{query}': {e}")
            return []
    
    def fetch_rss_feed(
        self,
        url: str,
        name: str = 'RSS Feed',
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        获取 RSS feed
        
        Args:
            url: RSS feed URL
            name: feed 名称
            limit: 返回条数
        """
        # 使用 Python feedparser（如果可用）
        try:
            import feedparser
            
            feed = feedparser.parse(url)
            
            if feed.bozo and not feed.entries:
                logger.error(f"Error parsing RSS feed {url}: {feed.bozo_exception}")
                return []
            
            items = []
            for entry in feed.entries[:limit]:
                items.append({
                    'source': 'rss',
                    'source_name': name,
                    'title': entry.get('title', ''),
                    'content': entry.get('summary', ''),
                    'time': entry.get('published', entry.get('updated', '')),
                    'url': entry.get('link', ''),
                })
            
            return items
            
        except ImportError:
            logger.warning("feedparser not installed, trying blogwatcher")
            return self._fetch_rss_via_blogwatcher(url, name, limit)
        except Exception as e:
            logger.error(f"Error fetching RSS feed {url}: {e}")
            return []
    
    def _fetch_rss_via_blogwatcher(
        self,
        url: str,
        name: str,
        limit: int
    ) -> List[Dict[str, Any]]:
        """使用 blogwatcher 获取 RSS"""
        if not self._blogwatcher_available:
            return []
        
        try:
            result = subprocess.run(
                ['blogwatcher', 'check', url, '--json', '--limit', str(limit)],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                return []
            
            items = []
            data = json.loads(result.stdout)
            for entry in data.get('entries', [])[:limit]:
                items.append({
                    'source': 'rss',
                    'source_name': name,
                    'title': entry.get('title', ''),
                    'content': entry.get('summary', ''),
                    'time': entry.get('published', ''),
                    'url': entry.get('link', ''),
                })
            
            return items
            
        except Exception as e:
            logger.error(f"blogwatcher error for {url}: {e}")
            return []
    
    def get_status(self) -> Dict[str, Any]:
        """获取服务状态"""
        return {
            'twitter': {
                'available': self._bird_available,
                'recommended_accounts': self.RECOMMENDED_TWITTER_ACCOUNTS,
            },
            'rss': {
                'available': True,  # feedparser always available
                'recommended_feeds': self.RECOMMENDED_RSS_FEEDS,
            }
        }


# 单例
_external_service: Optional[ExternalInfoService] = None

def get_external_service() -> ExternalInfoService:
    """获取外部信息服务单例"""
    global _external_service
    if _external_service is None:
        _external_service = ExternalInfoService()
    return _external_service
