"""
智能推送系统
监控新闻和异动，根据规则触发推送
"""
import re
from typing import List, Dict, Any, Optional, Callable, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, field

from .news_service import get_news_service
from .news_aggregator import get_news_aggregator
from .alerts_service import get_alerts_service
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class AlertRule:
    """告警规则"""
    name: str
    rule_type: str  # 'keyword' | 'stock' | 'alert_type' | 'custom'
    condition: Any  # 关键词列表 / 股票代码 / 异动类型 / 自定义函数
    priority: str = 'normal'  # 'low' | 'normal' | 'high' | 'urgent'
    cooldown_minutes: int = 5  # 同一规则触发间隔
    enabled: bool = True
    last_triggered: Optional[datetime] = None


@dataclass 
class Alert:
    """告警消息"""
    rule_name: str
    priority: str
    title: str
    content: str
    source: str
    time: str
    data: Dict[str, Any] = field(default_factory=dict)
    

class SmartAlertSystem:
    """智能告警系统"""
    
    def __init__(self):
        self.rules: List[AlertRule] = []
        self.triggered_alerts: List[Alert] = []
        self._callbacks: List[Callable[[Alert], None]] = []
        self._seen_hashes: Set[str] = set()
        
        # 初始化默认规则
        self._init_default_rules()
    
    def _init_default_rules(self):
        """初始化默认规则"""
        # 关键词规则
        self.add_keyword_rule(
            name="AI热点",
            keywords=['DeepSeek', 'OpenAI', 'ChatGPT', 'Claude', 'Anthropic', 'AI芯片', '大模型'],
            priority='high'
        )
        self.add_keyword_rule(
            name="芯片半导体",
            keywords=['英伟达', 'NVIDIA', '芯片', '半导体', '光刻机', 'ASML'],
            priority='normal'
        )
        self.add_keyword_rule(
            name="新能源",
            keywords=['特斯拉', 'Tesla', '宁德时代', '比亚迪', '锂电池', '储能'],
            priority='normal'
        )
        self.add_keyword_rule(
            name="贵金属",
            keywords=['黄金', '白银', 'gold', 'silver', '贵金属'],
            priority='normal'
        )
        
        # 异动规则
        self.add_alert_type_rule(
            name="涨停提醒",
            alert_types=['封涨停板'],
            priority='high'
        )
        self.add_alert_type_rule(
            name="跌停提醒", 
            alert_types=['封跌停板'],
            priority='high'
        )
    
    def add_keyword_rule(
        self,
        name: str,
        keywords: List[str],
        priority: str = 'normal',
        cooldown_minutes: int = 5
    ):
        """添加关键词规则"""
        rule = AlertRule(
            name=name,
            rule_type='keyword',
            condition=[k.lower() for k in keywords],
            priority=priority,
            cooldown_minutes=cooldown_minutes
        )
        self.rules.append(rule)
        logger.info(f"Added keyword rule: {name} with {len(keywords)} keywords")
    
    def add_stock_rule(
        self,
        name: str,
        stock_codes: List[str],
        priority: str = 'high',
        cooldown_minutes: int = 3
    ):
        """添加股票规则（自选股相关新闻）"""
        rule = AlertRule(
            name=name,
            rule_type='stock',
            condition=stock_codes,
            priority=priority,
            cooldown_minutes=cooldown_minutes
        )
        self.rules.append(rule)
        logger.info(f"Added stock rule: {name} for {len(stock_codes)} stocks")
    
    def add_alert_type_rule(
        self,
        name: str,
        alert_types: List[str],
        priority: str = 'normal',
        cooldown_minutes: int = 10
    ):
        """添加异动类型规则"""
        rule = AlertRule(
            name=name,
            rule_type='alert_type',
            condition=alert_types,
            priority=priority,
            cooldown_minutes=cooldown_minutes
        )
        self.rules.append(rule)
        logger.info(f"Added alert type rule: {name}")
    
    def register_callback(self, callback: Callable[[Alert], None]):
        """注册告警回调（用于推送）"""
        self._callbacks.append(callback)
        logger.info(f"Registered alert callback: {callback.__name__}")
    
    def _can_trigger(self, rule: AlertRule) -> bool:
        """检查规则是否可以触发（冷却时间）"""
        if not rule.enabled:
            return False
        if rule.last_triggered is None:
            return True
        elapsed = (datetime.now() - rule.last_triggered).total_seconds() / 60
        return elapsed >= rule.cooldown_minutes
    
    def _check_keyword_rule(self, rule: AlertRule, news: Dict[str, Any]) -> Optional[Alert]:
        """检查关键词规则"""
        text = f"{news.get('title', '')} {news.get('content', '')}".lower()
        
        for keyword in rule.condition:
            if keyword in text:
                return Alert(
                    rule_name=rule.name,
                    priority=rule.priority,
                    title=f"[{rule.name}] {news.get('title', '')[:50]}",
                    content=news.get('content', '')[:200],
                    source=news.get('source_name', ''),
                    time=news.get('time', ''),
                    data={'keyword': keyword, 'news': news}
                )
        return None
    
    def _check_stock_rule(self, rule: AlertRule, news: Dict[str, Any]) -> Optional[Alert]:
        """检查股票规则"""
        text = f"{news.get('title', '')} {news.get('content', '')}".lower()
        
        for code in rule.condition:
            # 检查股票代码或名称
            if code.lower() in text:
                return Alert(
                    rule_name=rule.name,
                    priority=rule.priority,
                    title=f"[自选股] {news.get('title', '')[:50]}",
                    content=news.get('content', '')[:200],
                    source=news.get('source_name', ''),
                    time=news.get('time', ''),
                    data={'stock': code, 'news': news}
                )
        return None
    
    def check_news(self, news_list: List[Dict[str, Any]]) -> List[Alert]:
        """检查新闻列表，返回触发的告警"""
        alerts = []
        
        for news in news_list:
            # 生成唯一标识
            news_hash = f"{news.get('source', '')}-{news.get('title', '')[:30]}"
            if news_hash in self._seen_hashes:
                continue
            self._seen_hashes.add(news_hash)
            
            for rule in self.rules:
                if not self._can_trigger(rule):
                    continue
                
                alert = None
                if rule.rule_type == 'keyword':
                    alert = self._check_keyword_rule(rule, news)
                elif rule.rule_type == 'stock':
                    alert = self._check_stock_rule(rule, news)
                
                if alert:
                    rule.last_triggered = datetime.now()
                    alerts.append(alert)
                    self.triggered_alerts.append(alert)
                    
                    # 触发回调
                    for callback in self._callbacks:
                        try:
                            callback(alert)
                        except Exception as e:
                            logger.error(f"Callback error: {e}")
        
        return alerts
    
    def check_market_alerts(self, market_alerts: Dict[str, List[Dict]]) -> List[Alert]:
        """检查市场异动"""
        alerts = []
        
        for rule in self.rules:
            if rule.rule_type != 'alert_type':
                continue
            if not self._can_trigger(rule):
                continue
            
            for alert_type in rule.condition:
                if alert_type in market_alerts:
                    type_alerts = market_alerts[alert_type]
                    if type_alerts:
                        # 只取前5个
                        top_alerts = type_alerts[:5]
                        summary = "\n".join([
                            f"• {a['code']} {a['name']}" 
                            for a in top_alerts
                        ])
                        
                        alert = Alert(
                            rule_name=rule.name,
                            priority=rule.priority,
                            title=f"[{alert_type}] {len(type_alerts)} 只股票",
                            content=summary,
                            source='异动提醒',
                            time=datetime.now().strftime('%H:%M:%S'),
                            data={'type': alert_type, 'count': len(type_alerts), 'top': top_alerts}
                        )
                        
                        rule.last_triggered = datetime.now()
                        alerts.append(alert)
                        self.triggered_alerts.append(alert)
                        
                        for callback in self._callbacks:
                            try:
                                callback(alert)
                            except Exception as e:
                                logger.error(f"Callback error: {e}")
        
        return alerts
    
    def scan(self) -> List[Alert]:
        """
        执行一次扫描，检查新闻和异动
        返回触发的告警列表
        """
        all_alerts = []
        
        # 检查新闻
        try:
            aggregator = get_news_aggregator()
            news = aggregator.get_new_alerts()
            if news:
                alerts = self.check_news(news)
                all_alerts.extend(alerts)
        except Exception as e:
            logger.error(f"Error scanning news: {e}")
        
        # 检查异动
        try:
            alerts_service = get_alerts_service()
            market_alerts = alerts_service.fetch_multiple_types()
            alerts = self.check_market_alerts(market_alerts)
            all_alerts.extend(alerts)
        except Exception as e:
            logger.error(f"Error scanning market alerts: {e}")
        
        return all_alerts
    
    def get_rules(self) -> List[Dict[str, Any]]:
        """获取所有规则"""
        return [
            {
                'name': r.name,
                'type': r.rule_type,
                'priority': r.priority,
                'enabled': r.enabled,
                'cooldown_minutes': r.cooldown_minutes,
                'last_triggered': r.last_triggered.isoformat() if r.last_triggered else None,
            }
            for r in self.rules
        ]
    
    def get_recent_alerts(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取最近的告警"""
        return [
            {
                'rule_name': a.rule_name,
                'priority': a.priority,
                'title': a.title,
                'content': a.content,
                'source': a.source,
                'time': a.time,
            }
            for a in self.triggered_alerts[-limit:]
        ]
    
    def clear_seen(self):
        """清空已见记录"""
        self._seen_hashes.clear()
        logger.info("Cleared seen news hashes")


# 单例
_smart_alert_system: Optional[SmartAlertSystem] = None

def get_smart_alert_system() -> SmartAlertSystem:
    """获取智能告警系统单例"""
    global _smart_alert_system
    if _smart_alert_system is None:
        _smart_alert_system = SmartAlertSystem()
    return _smart_alert_system
