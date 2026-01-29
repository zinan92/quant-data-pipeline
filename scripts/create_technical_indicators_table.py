#!/usr/bin/env python3
"""创建技术指标表"""
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database import engine
from sqlalchemy import text

def create_table():
    with engine.connect() as conn:
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS technical_indicators (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker VARCHAR(16) NOT NULL,
            trade_date VARCHAR(8) NOT NULL,
            
            -- 移动平均线
            ma5 FLOAT,
            ma10 FLOAT,
            ma20 FLOAT,
            ma60 FLOAT,
            
            -- MACD
            macd_dif FLOAT,
            macd_dea FLOAT,
            macd_hist FLOAT,
            
            -- RSI
            rsi6 FLOAT,
            rsi12 FLOAT,
            rsi24 FLOAT,
            
            -- 布林带
            boll_upper FLOAT,
            boll_mid FLOAT,
            boll_lower FLOAT,
            
            -- 其他
            volume_ratio FLOAT,  -- 量比
            turnover_rate FLOAT, -- 换手率
            
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            
            UNIQUE(ticker, trade_date)
        )
        """))
        
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ti_ticker ON technical_indicators(ticker)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ti_date ON technical_indicators(trade_date)"))
        conn.commit()
        
    print("✅ technical_indicators 表创建成功")

if __name__ == '__main__':
    create_table()
