"""
异动提醒服务
监控盘口异动：大笔买入、大笔卖出、封涨停板、打开涨停板等
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
import akshare as ak
import pandas as pd

from src.utils.logging import get_logger

logger = get_logger(__name__)


class AlertsService:
    """异动提醒服务"""
    
    # 异动类型
    ALERT_TYPES = {
        '大笔买入': 'big_buy',
        '大笔卖出': 'big_sell',
        '封涨停板': 'limit_up',
        '封跌停板': 'limit_down',
        '打开涨停板': 'open_limit_up',
        '打开跌停板': 'open_limit_down',
        '有大买盘': 'large_bid',
        '有大卖盘': 'large_ask',
        '竞价上涨': 'auction_up',
        '竞价下跌': 'auction_down',
        '高开5日线': 'gap_up_ma5',
        '低开5日线': 'gap_down_ma5',
        '向上缺口': 'gap_up',
        '向下缺口': 'gap_down',
        '60日新高': 'high_60d',
        '60日新低': 'low_60d',
        '60日大幅上涨': 'surge_60d',
        '60日大幅下跌': 'plunge_60d',
    }
    
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl = 10  # 缓存10秒（盘中数据变化快）
    
    def _is_cache_valid(self, alert_type: str) -> bool:
        """检查缓存是否有效"""
        if alert_type not in self._cache:
            return False
        cached = self._cache[alert_type]
        elapsed = (datetime.now() - cached['timestamp']).total_seconds()
        return elapsed < self._cache_ttl
    
    def fetch_alerts(
        self,
        alert_type: str = '大笔买入',
        use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        """
        获取异动提醒
        
        Args:
            alert_type: 异动类型
            use_cache: 是否使用缓存
            
        Returns:
            异动列表
        """
        if alert_type not in self.ALERT_TYPES:
            raise ValueError(f"Unknown alert type: {alert_type}. Available: {list(self.ALERT_TYPES.keys())}")
        
        # 检查缓存
        if use_cache and self._is_cache_valid(alert_type):
            return self._cache[alert_type]['data']
        
        try:
            logger.info(f"Fetching alerts: {alert_type}")
            df = ak.stock_changes_em(symbol=alert_type)
            
            if df is None or df.empty:
                logger.warning(f"No alerts for {alert_type}")
                return []
            
            alerts = self._normalize_alerts(df, alert_type)
            
            # 更新缓存
            self._cache[alert_type] = {
                'data': alerts,
                'timestamp': datetime.now()
            }
            
            logger.info(f"Fetched {len(alerts)} alerts for {alert_type}")
            return alerts
            
        except Exception as e:
            logger.error(f"Error fetching alerts for {alert_type}: {e}")
            return []
    
    def _normalize_alerts(self, df: pd.DataFrame, alert_type: str) -> List[Dict[str, Any]]:
        """标准化异动数据"""
        alerts = []
        
        for _, row in df.iterrows():
            # 解析相关信息
            info = str(row.get('相关信息', ''))
            info_parts = info.split(',') if info else []
            
            alert = {
                'type': alert_type,
                'type_code': self.ALERT_TYPES.get(alert_type, 'unknown'),
                'time': str(row.get('时间', '')),
                'code': str(row.get('代码', '')),
                'name': str(row.get('名称', '')),
                'info': info,
            }
            
            # 尝试解析详细信息
            if len(info_parts) >= 4:
                try:
                    alert['volume'] = float(info_parts[0])  # 成交量
                    alert['price'] = float(info_parts[1])   # 价格
                    alert['change_pct'] = float(info_parts[2])  # 涨跌幅
                    alert['amount'] = float(info_parts[3])  # 成交额
                except (ValueError, IndexError):
                    pass
            
            alerts.append(alert)
        
        return alerts
    
    def fetch_multiple_types(
        self,
        types: Optional[List[str]] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        获取多种类型的异动
        
        Args:
            types: 异动类型列表，默认获取常用类型
            
        Returns:
            {异动类型: 异动列表}
        """
        if types is None:
            types = ['大笔买入', '大笔卖出', '封涨停板', '打开涨停板']
        
        result = {}
        for alert_type in types:
            try:
                alerts = self.fetch_alerts(alert_type)
                result[alert_type] = alerts
            except Exception as e:
                logger.error(f"Error fetching {alert_type}: {e}")
                result[alert_type] = []
        
        return result
    
    def get_all_types(self) -> List[str]:
        """获取所有支持的异动类型"""
        return list(self.ALERT_TYPES.keys())
    
    def fetch_summary(self) -> Dict[str, Any]:
        """
        获取异动摘要
        
        Returns:
            {
                '大笔买入': {'count': 10, 'top': [...]},
                '大笔卖出': {'count': 5, 'top': [...]},
                ...
            }
        """
        key_types = ['大笔买入', '大笔卖出', '封涨停板', '封跌停板']
        summary = {}
        
        for alert_type in key_types:
            try:
                alerts = self.fetch_alerts(alert_type)
                summary[alert_type] = {
                    'count': len(alerts),
                    'top': alerts[:5] if alerts else [],
                }
            except Exception as e:
                logger.error(f"Error in summary for {alert_type}: {e}")
                summary[alert_type] = {'count': 0, 'top': []}
        
        return summary


# 单例
_alerts_service: Optional[AlertsService] = None

def get_alerts_service() -> AlertsService:
    """获取异动服务单例"""
    global _alerts_service
    if _alerts_service is None:
        _alerts_service = AlertsService()
    return _alerts_service
