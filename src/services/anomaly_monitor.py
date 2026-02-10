"""
异动实时监控服务
检测涨停、跌停、大单、放量等异动
"""
from typing import List, Dict, Optional
from datetime import datetime
import json
from sqlalchemy import text
from src.database import SessionLocal
from src.utils.logging import get_logger
import tushare as ts

LOGGER = get_logger(__name__)
from src.config import get_settings


# 异动类型定义
ANOMALY_TYPES = {
    'limit_up': '涨停',
    'limit_down': '跌停', 
    'near_limit_up': '触及涨停',
    'near_limit_down': '触及跌停',
    'large_buy': '大单买入',
    'large_sell': '大单卖出',
    'volume_spike': '放量异动',
    'price_spike': '急涨急跌'
}


class AnomalyMonitor:
    """异动监控器"""
    
    def __init__(self):
        self.session = SessionLocal()
        settings = get_settings()
        self.pro = ts.pro_api(settings.tushare_token)
    
    def close(self):
        self.session.close()
    
    def get_watchlist_tickers(self) -> List[str]:
        """获取自选股列表"""
        result = self.session.execute(text("SELECT ticker FROM watchlist")).fetchall()
        return [r[0] for r in result]
    
    def detect_limit_up_down(self, ticker: str) -> List[Dict]:
        """检测涨跌停"""
        anomalies = []
        
        try:
            if ticker.startswith('6'):
                ts_code = f"{ticker}.SH"
            elif ticker.startswith('0') or ticker.startswith('3'):
                ts_code = f"{ticker}.SZ"
            else:
                ts_code = f"{ticker}.BJ"
            
            df = self.pro.daily(ts_code=ts_code, limit=1)
            
            if df is None or df.empty:
                return []
            
            row = df.iloc[0]
            pct = row['pct_chg']
            
            # 涨停 (9.9%+)
            if pct >= 9.9:
                anomalies.append({
                    'ticker': ticker,
                    'type': 'limit_up',
                    'pct_change': pct,
                    'price': row['close'],
                    'date': row['trade_date']
                })
            # 跌停
            elif pct <= -9.9:
                anomalies.append({
                    'ticker': ticker,
                    'type': 'limit_down', 
                    'pct_change': pct,
                    'price': row['close'],
                    'date': row['trade_date']
                })
            # 触及涨停
            elif pct >= 7:
                anomalies.append({
                    'ticker': ticker,
                    'type': 'near_limit_up',
                    'pct_change': pct,
                    'price': row['close'],
                    'date': row['trade_date']
                })
            # 触及跌停
            elif pct <= -7:
                anomalies.append({
                    'ticker': ticker,
                    'type': 'near_limit_down',
                    'pct_change': pct,
                    'price': row['close'],
                    'date': row['trade_date']
                })
                
        except Exception as e:
            pass
        
        return anomalies
    
    def detect_volume_spike(self, ticker: str, threshold: float = 3.0) -> Optional[Dict]:
        """检测放量异动 (成交量超过5日均量N倍)"""
        try:
            if ticker.startswith('6'):
                ts_code = f"{ticker}.SH"
            elif ticker.startswith('0') or ticker.startswith('3'):
                ts_code = f"{ticker}.SZ"
            else:
                ts_code = f"{ticker}.BJ"
            
            df = self.pro.daily(ts_code=ts_code, limit=6)
            
            if df is None or len(df) < 6:
                return None
            
            df = df.sort_values('trade_date', ascending=False)
            today_vol = df.iloc[0]['vol']
            avg_vol = df.iloc[1:6]['vol'].mean()
            
            if avg_vol > 0 and today_vol / avg_vol >= threshold:
                return {
                    'ticker': ticker,
                    'type': 'volume_spike',
                    'volume': today_vol,
                    'avg_volume': avg_vol,
                    'ratio': today_vol / avg_vol,
                    'date': df.iloc[0]['trade_date']
                }
                
        except Exception as e:
            pass
        
        return None
    
    def scan_watchlist(self) -> Dict[str, List[Dict]]:
        """扫描自选股异动"""
        tickers = self.get_watchlist_tickers()
        
        results = {
            'limit_up': [],
            'limit_down': [],
            'near_limit_up': [],
            'near_limit_down': [],
            'volume_spike': []
        }
        
        for ticker in tickers[:50]:  # 限制数量避免API限流
            # 检测涨跌停
            anomalies = self.detect_limit_up_down(ticker)
            for a in anomalies:
                if a['type'] in results:
                    results[a['type']].append(a)
            
            # 检测放量
            vol_anomaly = self.detect_volume_spike(ticker)
            if vol_anomaly:
                results['volume_spike'].append(vol_anomaly)
        
        return results
    
    def save_anomaly(self, anomaly: Dict):
        """保存异动记录"""
        try:
            self.session.execute(text("""
                INSERT OR IGNORE INTO stock_anomaly 
                (ticker, trade_date, anomaly_type, price, pct_change, volume, details)
                VALUES (:ticker, :date, :type, :price, :pct, :vol, :details)
            """), {
                'ticker': anomaly.get('ticker'),
                'date': anomaly.get('date'),
                'type': anomaly.get('type'),
                'price': anomaly.get('price'),
                'pct': anomaly.get('pct_change'),
                'vol': anomaly.get('volume'),
                'details': json.dumps(anomaly)
            })
            self.session.commit()
        except Exception as e:
            LOGGER.warning(f"Failed to save anomaly for {anomaly.get('ticker')}: {e}")
    
    def get_today_anomalies(self) -> List[Dict]:
        """获取今日异动"""
        today = datetime.now().strftime('%Y%m%d')
        result = self.session.execute(text("""
            SELECT ticker, anomaly_type, price, pct_change, volume, details, created_at
            FROM stock_anomaly
            WHERE trade_date = :today
            ORDER BY created_at DESC
        """), {'today': today}).fetchall()
        
        return [{
            'ticker': r[0],
            'type': r[1],
            'type_name': ANOMALY_TYPES.get(r[1], r[1]),
            'price': r[2],
            'pct_change': r[3],
            'volume': r[4],
            'details': json.loads(r[5]) if r[5] else {},
            'time': str(r[6])
        } for r in result]


def scan_anomalies() -> Dict:
    """扫描异动（供API调用）"""
    monitor = AnomalyMonitor()
    try:
        results = monitor.scan_watchlist()
        
        # 保存异动
        for atype, anomalies in results.items():
            for a in anomalies:
                monitor.save_anomaly(a)
        
        return {
            'scanned_at': datetime.now().isoformat(),
            'results': results,
            'summary': {
                'limit_up': len(results.get('limit_up', [])),
                'limit_down': len(results.get('limit_down', [])),
                'near_limit_up': len(results.get('near_limit_up', [])),
                'near_limit_down': len(results.get('near_limit_down', [])),
                'volume_spike': len(results.get('volume_spike', []))
            }
        }
    finally:
        monitor.close()


def get_today_anomalies() -> List[Dict]:
    """获取今日异动（供API调用）"""
    monitor = AnomalyMonitor()
    try:
        return monitor.get_today_anomalies()
    finally:
        monitor.close()
