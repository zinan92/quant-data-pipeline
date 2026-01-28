"""
信息流服务测试
"""
import pytest
from unittest.mock import Mock, patch
import pandas as pd

from src.services.news.news_service import NewsService, get_news_service
from src.services.news.news_aggregator import NewsAggregator
from src.services.news.alerts_service import AlertsService
from src.services.news.smart_alerts import SmartAlertSystem, AlertRule


class TestNewsService:
    """新闻服务测试"""
    
    def test_init(self):
        """测试初始化"""
        service = NewsService()
        assert service is not None
        assert len(service.SOURCES) > 0
    
    def test_sources_config(self):
        """测试数据源配置"""
        service = NewsService()
        assert 'cls' in service.SOURCES
        assert 'ths' in service.SOURCES
        assert service.SOURCES['cls']['name'] == '财联社'
        assert service.SOURCES['ths']['name'] == '同花顺'
    
    @patch('src.services.news.news_service.ak')
    def test_fetch_news_cls(self, mock_ak):
        """测试获取财联社快讯"""
        # Mock AKShare 返回
        mock_df = pd.DataFrame({
            '标题': ['测试标题1', '测试标题2'],
            '内容': ['测试内容1', '测试内容2'],
            '发布日期': ['2026-01-28', '2026-01-28'],
            '发布时间': ['10:00:00', '10:01:00'],
        })
        mock_ak.stock_info_global_cls.return_value = mock_df
        
        service = NewsService()
        news = service.fetch_news('cls', limit=2, use_cache=False)
        
        assert len(news) == 2
        assert news[0]['source'] == 'cls'
        assert news[0]['source_name'] == '财联社'
        assert '测试标题1' in news[0]['title']
    
    def test_fetch_news_invalid_source(self):
        """测试无效数据源"""
        service = NewsService()
        with pytest.raises(ValueError):
            service.fetch_news('invalid_source')
    
    def test_get_news_service_singleton(self):
        """测试单例模式"""
        service1 = get_news_service()
        service2 = get_news_service()
        assert service1 is service2


class TestNewsAggregator:
    """新闻聚合器测试"""
    
    def test_init(self):
        """测试初始化"""
        agg = NewsAggregator()
        assert agg is not None
    
    def test_set_keywords(self):
        """测试设置关键词"""
        agg = NewsAggregator()
        agg.set_keywords(include=['AI', '芯片'], exclude=['广告'])
        
        assert 'ai' in agg._keywords
        assert '芯片' in agg._keywords
        assert '广告' in agg._exclude_keywords
    
    def test_matches_filter_include(self):
        """测试关键词过滤 - 包含"""
        agg = NewsAggregator()
        agg.set_keywords(include=['AI', '芯片'])
        
        news1 = {'title': 'AI行业大新闻', 'content': ''}
        news2 = {'title': '房地产新闻', 'content': ''}
        
        assert agg._matches_filter(news1) == True
        assert agg._matches_filter(news2) == False
    
    def test_matches_filter_exclude(self):
        """测试关键词过滤 - 排除"""
        agg = NewsAggregator()
        agg.set_keywords(exclude=['广告', '推广'])
        
        news1 = {'title': 'AI行业大新闻', 'content': ''}
        news2 = {'title': '这是广告内容', 'content': ''}
        
        assert agg._matches_filter(news1) == True
        assert agg._matches_filter(news2) == False
    
    def test_hash_news(self):
        """测试新闻哈希"""
        agg = NewsAggregator()
        
        news1 = {'source': 'cls', 'title': '标题1', 'content': '内容1'}
        news2 = {'source': 'cls', 'title': '标题1', 'content': '内容1'}
        news3 = {'source': 'ths', 'title': '标题2', 'content': '内容2'}
        
        hash1 = agg._hash_news(news1)
        hash2 = agg._hash_news(news2)
        hash3 = agg._hash_news(news3)
        
        assert hash1 == hash2  # 相同内容应该相同哈希
        assert hash1 != hash3  # 不同内容应该不同哈希
    
    def test_clear_history(self):
        """测试清空历史"""
        agg = NewsAggregator()
        agg._seen_hashes.add('test_hash')
        agg.clear_history()
        assert len(agg._seen_hashes) == 0


class TestAlertsService:
    """异动服务测试"""
    
    def test_init(self):
        """测试初始化"""
        service = AlertsService()
        assert service is not None
    
    def test_alert_types(self):
        """测试异动类型"""
        service = AlertsService()
        assert '大笔买入' in service.ALERT_TYPES
        assert '封涨停板' in service.ALERT_TYPES
        assert service.ALERT_TYPES['大笔买入'] == 'big_buy'
    
    def test_get_all_types(self):
        """测试获取所有类型"""
        service = AlertsService()
        types = service.get_all_types()
        assert len(types) > 0
        assert '大笔买入' in types
    
    def test_fetch_alerts_invalid_type(self):
        """测试无效异动类型"""
        service = AlertsService()
        with pytest.raises(ValueError):
            service.fetch_alerts('无效类型')


class TestSmartAlertSystem:
    """智能推送系统测试"""
    
    def test_init(self):
        """测试初始化"""
        system = SmartAlertSystem()
        assert system is not None
        assert len(system.rules) > 0  # 应该有默认规则
    
    def test_add_keyword_rule(self):
        """测试添加关键词规则"""
        system = SmartAlertSystem()
        initial_count = len(system.rules)
        
        system.add_keyword_rule(
            name='测试规则',
            keywords=['测试', 'test'],
            priority='high'
        )
        
        assert len(system.rules) == initial_count + 1
        new_rule = system.rules[-1]
        assert new_rule.name == '测试规则'
        assert new_rule.priority == 'high'
    
    def test_add_stock_rule(self):
        """测试添加股票规则"""
        system = SmartAlertSystem()
        initial_count = len(system.rules)
        
        system.add_stock_rule(
            name='自选股监控',
            stock_codes=['000001', '600000']
        )
        
        assert len(system.rules) == initial_count + 1
    
    def test_check_keyword_rule(self):
        """测试关键词规则检查"""
        system = SmartAlertSystem()
        
        rule = AlertRule(
            name='AI规则',
            rule_type='keyword',
            condition=['ai', 'chatgpt'],
            priority='high'
        )
        
        news_match = {'title': 'AI行业大新闻', 'content': '人工智能发展'}
        news_no_match = {'title': '房地产新闻', 'content': '楼市动态'}
        
        alert = system._check_keyword_rule(rule, news_match)
        assert alert is not None
        assert alert.rule_name == 'AI规则'
        
        alert = system._check_keyword_rule(rule, news_no_match)
        assert alert is None
    
    def test_can_trigger_cooldown(self):
        """测试冷却时间"""
        from datetime import datetime, timedelta
        
        system = SmartAlertSystem()
        rule = AlertRule(
            name='测试',
            rule_type='keyword',
            condition=['test'],
            cooldown_minutes=5
        )
        
        # 没有触发过，应该可以触发
        assert system._can_trigger(rule) == True
        
        # 刚触发过，应该不能触发
        rule.last_triggered = datetime.now()
        assert system._can_trigger(rule) == False
        
        # 超过冷却时间，应该可以触发
        rule.last_triggered = datetime.now() - timedelta(minutes=10)
        assert system._can_trigger(rule) == True
    
    def test_get_rules(self):
        """测试获取规则列表"""
        system = SmartAlertSystem()
        rules = system.get_rules()
        
        assert isinstance(rules, list)
        assert len(rules) > 0
        assert 'name' in rules[0]
        assert 'type' in rules[0]
        assert 'priority' in rules[0]


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
