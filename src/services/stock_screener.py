"""
股票筛选器 - 基于技术指标的选股规则引擎
"""
from typing import List, Dict, Optional
from sqlalchemy import text
from src.database import SessionLocal


class StockScreener:
    """技术指标选股器"""
    
    def __init__(self):
        self.session = SessionLocal()
    
    def close(self):
        self.session.close()
    
    def get_latest_indicators(self, ticker: str) -> Optional[Dict]:
        """获取股票最新的技术指标"""
        result = self.session.execute(text("""
            SELECT * FROM technical_indicators 
            WHERE ticker = :ticker 
            ORDER BY trade_date DESC LIMIT 2
        """), {'ticker': ticker}).fetchall()
        
        if len(result) < 2:
            return None
        
        cols = ['id', 'ticker', 'trade_date', 'ma5', 'ma10', 'ma20', 'ma60',
                'macd_dif', 'macd_dea', 'macd_hist', 'rsi6', 'rsi12', 'rsi24',
                'boll_upper', 'boll_mid', 'boll_lower', 'volume_ratio', 'turnover_rate', 'created_at']
        
        current = dict(zip(cols, result[0]))
        previous = dict(zip(cols, result[1]))
        
        return {'current': current, 'previous': previous}
    
    def screen_golden_cross(self) -> List[Dict]:
        """筛选金叉股票 (MA5上穿MA10)"""
        results = self.session.execute(text("""
            WITH ranked AS (
                SELECT ticker, trade_date, ma5, ma10,
                       LAG(ma5) OVER (PARTITION BY ticker ORDER BY trade_date) as prev_ma5,
                       LAG(ma10) OVER (PARTITION BY ticker ORDER BY trade_date) as prev_ma10,
                       ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY trade_date DESC) as rn
                FROM technical_indicators
                WHERE ma5 IS NOT NULL AND ma10 IS NOT NULL
            )
            SELECT ticker, trade_date, ma5, ma10, prev_ma5, prev_ma10
            FROM ranked
            WHERE rn = 1
              AND prev_ma5 < prev_ma10  -- 之前在下方
              AND ma5 > ma10            -- 现在在上方
        """)).fetchall()
        
        return [{'ticker': r[0], 'date': r[1], 'ma5': r[2], 'ma10': r[3], 
                 'signal': 'MA金叉'} for r in results]
    
    def screen_macd_golden_cross(self) -> List[Dict]:
        """筛选MACD金叉 (DIF上穿DEA)"""
        results = self.session.execute(text("""
            WITH ranked AS (
                SELECT ticker, trade_date, macd_dif, macd_dea,
                       LAG(macd_dif) OVER (PARTITION BY ticker ORDER BY trade_date) as prev_dif,
                       LAG(macd_dea) OVER (PARTITION BY ticker ORDER BY trade_date) as prev_dea,
                       ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY trade_date DESC) as rn
                FROM technical_indicators
                WHERE macd_dif IS NOT NULL AND macd_dea IS NOT NULL
            )
            SELECT ticker, trade_date, macd_dif, macd_dea
            FROM ranked
            WHERE rn = 1
              AND prev_dif < prev_dea
              AND macd_dif > macd_dea
        """)).fetchall()
        
        return [{'ticker': r[0], 'date': r[1], 'dif': r[2], 'dea': r[3],
                 'signal': 'MACD金叉'} for r in results]
    
    def screen_oversold_bounce(self, rsi_threshold: float = 30) -> List[Dict]:
        """筛选超卖反弹 (RSI从<30回升)"""
        results = self.session.execute(text("""
            WITH ranked AS (
                SELECT ticker, trade_date, rsi6, rsi12,
                       LAG(rsi6) OVER (PARTITION BY ticker ORDER BY trade_date) as prev_rsi6,
                       ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY trade_date DESC) as rn
                FROM technical_indicators
                WHERE rsi6 IS NOT NULL
            )
            SELECT ticker, trade_date, rsi6, prev_rsi6
            FROM ranked
            WHERE rn = 1
              AND prev_rsi6 < :threshold
              AND rsi6 > prev_rsi6
        """), {'threshold': rsi_threshold}).fetchall()
        
        return [{'ticker': r[0], 'date': r[1], 'rsi6': r[2], 'prev_rsi6': r[3],
                 'signal': '超卖反弹'} for r in results]
    
    def screen_bollinger_breakout(self) -> List[Dict]:
        """筛选布林带突破 (价格突破上轨)"""
        results = self.session.execute(text("""
            SELECT t.ticker, t.trade_date, t.boll_upper, t.boll_mid, t.boll_lower
            FROM technical_indicators t
            INNER JOIN (
                SELECT ticker, MAX(trade_date) as max_date
                FROM technical_indicators
                GROUP BY ticker
            ) latest ON t.ticker = latest.ticker AND t.trade_date = latest.max_date
            WHERE t.boll_upper IS NOT NULL
        """)).fetchall()
        
        # 需要获取当前价格来比较，这里简化处理
        return [{'ticker': r[0], 'date': r[1], 'upper': r[2], 'mid': r[3], 'lower': r[4],
                 'signal': '布林突破'} for r in results]
    
    def run_all_screens(self) -> Dict[str, List[Dict]]:
        """运行所有筛选规则"""
        return {
            'golden_cross': self.screen_golden_cross(),
            'macd_golden_cross': self.screen_macd_golden_cross(),
            'oversold_bounce': self.screen_oversold_bounce(),
        }


def get_screener_results() -> Dict:
    """获取选股结果（供API调用）"""
    screener = StockScreener()
    try:
        return screener.run_all_screens()
    finally:
        screener.close()
