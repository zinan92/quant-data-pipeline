"""
美股服务测试
"""
import pytest
from unittest.mock import Mock, patch

from src.services.us_stock.us_stock_service import USStockService, get_us_stock_service


class TestUSStockService:
    """美股服务测试"""
    
    def test_init(self):
        """测试初始化"""
        service = USStockService()
        assert service is not None
        assert service.provider is not None
    
    def test_watchlists_config(self):
        """测试监控列表配置"""
        service = USStockService()
        
        assert 'indexes' in service.WATCHLISTS
        assert 'tech' in service.WATCHLISTS
        assert 'china_adr' in service.WATCHLISTS
        assert 'ai' in service.WATCHLISTS
        
        # 检查指数
        assert '^GSPC' in service.WATCHLISTS['indexes']
        assert '^DJI' in service.WATCHLISTS['indexes']
        
        # 检查科技股
        assert 'AAPL' in service.WATCHLISTS['tech']
        assert 'NVDA' in service.WATCHLISTS['tech']
        
        # 检查中概股
        assert 'BABA' in service.WATCHLISTS['china_adr']
        assert 'PDD' in service.WATCHLISTS['china_adr']
    
    def test_get_available_watchlists(self):
        """测试获取可用监控列表"""
        service = USStockService()
        watchlists = service.get_available_watchlists()
        
        assert isinstance(watchlists, dict)
        assert 'indexes' in watchlists
        assert 'tech' in watchlists
        assert isinstance(watchlists['indexes'], list)
    
    def test_get_us_stock_service_singleton(self):
        """测试单例模式"""
        service1 = get_us_stock_service()
        service2 = get_us_stock_service()
        assert service1 is service2
    
    @patch.object(USStockService, 'get_quote')
    def test_get_watchlist_quotes(self, mock_get_quote):
        """测试获取监控列表报价"""
        mock_get_quote.return_value = {
            'symbol': 'AAPL',
            'name': 'Apple Inc.',
            'price': 150.0,
            'change': 1.5,
            'change_pct': 1.0,
        }
        
        service = USStockService()
        quotes = service.get_watchlist_quotes('tech')
        
        assert len(quotes) > 0
        assert mock_get_quote.called
    
    def test_get_watchlist_quotes_invalid(self):
        """测试无效监控列表"""
        service = USStockService()
        quotes = service.get_watchlist_quotes('invalid_list')
        assert quotes == []
    
    def test_cache_validity(self):
        """测试缓存有效性"""
        from datetime import datetime, timedelta
        
        service = USStockService()
        
        # 没有缓存
        assert service._is_cache_valid('test_key') == False
        
        # 添加缓存
        service._cache['test_key'] = {
            'data': 'test',
            'timestamp': datetime.now()
        }
        assert service._is_cache_valid('test_key') == True
        
        # 过期缓存
        service._cache['old_key'] = {
            'data': 'test',
            'timestamp': datetime.now() - timedelta(seconds=service._cache_ttl + 10)
        }
        assert service._is_cache_valid('old_key') == False


class TestUSStockServiceIntegration:
    """美股服务集成测试（需要网络）"""
    
    @pytest.mark.integration
    def test_get_quote_real(self):
        """测试获取真实报价"""
        service = USStockService()
        quote = service.get_quote('AAPL')
        
        if quote:  # 可能因网络问题返回 None
            assert 'symbol' in quote
            assert 'price' in quote
            assert quote['symbol'] == 'AAPL'
    
    @pytest.mark.integration
    def test_get_indexes_real(self):
        """测试获取真实指数"""
        service = USStockService()
        indexes = service.get_indexes()
        
        # 至少应该有一些数据
        assert isinstance(indexes, list)
    
    @pytest.mark.integration
    def test_get_kline_real(self):
        """测试获取真实K线"""
        service = USStockService()
        klines = service.get_kline('AAPL', period='5d', interval='1d')
        
        if klines:
            assert isinstance(klines, list)
            assert len(klines) > 0
            assert 'open' in klines[0]
            assert 'close' in klines[0]


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
