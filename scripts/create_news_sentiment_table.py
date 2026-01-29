#!/usr/bin/env python3
"""创建新闻情绪分析表"""
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database import engine
from sqlalchemy import text

def create_table():
    with engine.connect() as conn:
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS news_sentiment (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            news_id VARCHAR(64) UNIQUE,
            publish_time DATETIME,
            source VARCHAR(32),
            title TEXT,
            content TEXT,
            
            -- 情绪分析
            sentiment VARCHAR(16),  -- 'positive', 'negative', 'neutral'
            sentiment_score FLOAT,   -- -1 到 1
            confidence FLOAT,        -- 置信度 0-1
            
            -- 关联标的
            related_stocks TEXT,     -- JSON: ["000001", "600519"]
            related_sectors TEXT,    -- JSON: ["白酒", "芯片"]
            
            -- 关键词
            keywords TEXT,           -- JSON
            
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """))
        
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ns_time ON news_sentiment(publish_time)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ns_sentiment ON news_sentiment(sentiment)"))
        conn.commit()
        
    print("✅ news_sentiment 表创建成功")

if __name__ == '__main__':
    create_table()
