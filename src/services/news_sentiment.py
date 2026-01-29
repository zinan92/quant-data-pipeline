"""
财经新闻情绪分析服务
使用关键词匹配和规则进行快速情绪分析
"""
from typing import List, Dict, Optional, Tuple
import re
import json
from datetime import datetime
from sqlalchemy import text
from src.database import SessionLocal


# 情绪词典
POSITIVE_KEYWORDS = [
    '涨停', '大涨', '暴涨', '飙升', '新高', '突破', '利好', '增持', '回购',
    '盈利', '增长', '超预期', '签约', '中标', '扩产', '景气', '机构看好',
    '北向资金', '加仓', '龙头', '领涨', '强势', '放量', '反弹', '底部',
    '政策支持', '重大突破', '战略合作', '订单', '产能', '出口', '创新高'
]

NEGATIVE_KEYWORDS = [
    '跌停', '大跌', '暴跌', '闪崩', '跳水', '利空', '减持', '爆雷',
    '亏损', '下滑', '低于预期', '违规', '处罚', '退市', '风险', '警示',
    '资金流出', '减仓', '破位', '新低', '弱势', '缩量', '萎缩',
    '监管', '调查', '诉讼', '违约', '暴雷', '清仓', '离场'
]

# 行业关键词映射
SECTOR_KEYWORDS = {
    '白酒': ['白酒', '茅台', '五粮液', '酒企'],
    'AI': ['AI', '人工智能', '大模型', 'ChatGPT', '算力', 'DeepSeek', '智能体'],
    '芯片': ['芯片', '半导体', '光刻机', '晶圆', 'GPU', '国产替代'],
    '新能源': ['新能源', '光伏', '锂电', '储能', '充电桩', '电池'],
    '汽车': ['汽车', '新能源车', '电动车', '特斯拉', '比亚迪', '蔚来'],
    '医药': ['医药', '创新药', '生物医药', '疫苗', '医疗'],
    '军工': ['军工', '国防', '航空', '航天', '卫星'],
    '消费': ['消费', '零售', '电商', '食品', '餐饮'],
    '金融': ['银行', '券商', '保险', '金融', '降息', '降准'],
    '房地产': ['房地产', '房企', '楼市', '房价', '地产']
}


class NewsSentimentAnalyzer:
    """新闻情绪分析器"""
    
    def __init__(self):
        self.session = SessionLocal()
    
    def close(self):
        self.session.close()
    
    def analyze_sentiment(self, text: str) -> Tuple[str, float, float]:
        """
        分析文本情绪
        
        Returns:
            (sentiment, score, confidence)
            - sentiment: 'positive', 'negative', 'neutral'
            - score: -1 到 1
            - confidence: 0 到 1
        """
        text_lower = text.lower()
        
        pos_count = sum(1 for kw in POSITIVE_KEYWORDS if kw in text)
        neg_count = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text)
        
        total = pos_count + neg_count
        
        if total == 0:
            return 'neutral', 0, 0.3
        
        score = (pos_count - neg_count) / total
        
        if score > 0.2:
            sentiment = 'positive'
        elif score < -0.2:
            sentiment = 'negative'
        else:
            sentiment = 'neutral'
        
        # 置信度基于关键词数量
        confidence = min(1.0, total / 5)
        
        return sentiment, score, confidence
    
    def extract_related_sectors(self, text: str) -> List[str]:
        """提取相关行业"""
        sectors = []
        for sector, keywords in SECTOR_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                sectors.append(sector)
        return sectors
    
    def extract_stock_codes(self, text: str) -> List[str]:
        """提取股票代码"""
        # 匹配6位数字代码
        codes = re.findall(r'\b([036]\d{5})\b', text)
        return list(set(codes))
    
    def analyze_news(self, news_item: Dict) -> Dict:
        """分析单条新闻"""
        title = news_item.get('title', '')
        content = news_item.get('content', title)
        full_text = f"{title} {content}"
        
        sentiment, score, confidence = self.analyze_sentiment(full_text)
        sectors = self.extract_related_sectors(full_text)
        stocks = self.extract_stock_codes(full_text)
        
        return {
            'title': title,
            'sentiment': sentiment,
            'sentiment_score': score,
            'confidence': confidence,
            'related_sectors': sectors,
            'related_stocks': stocks,
            'publish_time': news_item.get('publish_time'),
            'source': news_item.get('source', 'unknown')
        }
    
    def get_recent_news(self, limit: int = 50) -> List[Dict]:
        """获取最近的新闻"""
        # 从现有的 news API 获取
        try:
            import requests
            resp = requests.get(f'http://127.0.0.1:8000/api/news/latest?limit={limit}', timeout=5)
            if resp.ok:
                data = resp.json()
                return data if isinstance(data, list) else data.get('news', [])
        except:
            pass
        return []
    
    def analyze_recent_news(self, limit: int = 50) -> Dict:
        """分析最近的新闻"""
        news_list = self.get_recent_news(limit)
        
        if not news_list:
            return {
                'analyzed': 0,
                'positive': 0,
                'negative': 0,
                'neutral': 0,
                'items': [],
                'hot_sectors': []
            }
        
        results = []
        sector_counts = {}
        sentiment_counts = {'positive': 0, 'negative': 0, 'neutral': 0}
        
        for news in news_list:
            analysis = self.analyze_news(news)
            results.append(analysis)
            
            sentiment_counts[analysis['sentiment']] += 1
            
            for sector in analysis['related_sectors']:
                sector_counts[sector] = sector_counts.get(sector, 0) + 1
        
        # 热门行业
        hot_sectors = sorted(sector_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        
        return {
            'analyzed': len(results),
            'positive': sentiment_counts['positive'],
            'negative': sentiment_counts['negative'],
            'neutral': sentiment_counts['neutral'],
            'sentiment_ratio': sentiment_counts['positive'] / max(1, sentiment_counts['positive'] + sentiment_counts['negative']),
            'items': results[:20],
            'hot_sectors': [{'sector': s, 'count': c} for s, c in hot_sectors]
        }


def get_news_sentiment_analysis(limit: int = 50) -> Dict:
    """获取新闻情绪分析（供API调用）"""
    analyzer = NewsSentimentAnalyzer()
    try:
        return analyzer.analyze_recent_news(limit)
    finally:
        analyzer.close()
