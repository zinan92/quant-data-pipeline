#!/usr/bin/env python3
"""为 watchlist 表添加 category 分类字段"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
from src.config import get_settings

settings = get_settings()

# 从 database_url 中提取数据库文件路径
database_path = settings.database_url.replace("sqlite:///", "")

def add_category_field():
    """给 watchlist 表添加 category 字段"""
    conn = sqlite3.connect(database_path)
    cursor = conn.cursor()

    try:
        # 检查字段是否已存在
        cursor.execute("PRAGMA table_info(watchlist)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'category' in columns:
            print("⚠️  category 字段已存在，无需添加")
            return

        # 添加 category 字段
        cursor.execute("""
            ALTER TABLE watchlist
            ADD COLUMN category VARCHAR(64) DEFAULT '未分类'
        """)

        conn.commit()
        print("✅ 成功添加 category 字段到 watchlist 表")

        # 显示新的表结构
        cursor.execute("PRAGMA table_info(watchlist)")
        print("\n新的表结构:")
        for col in cursor.fetchall():
            print(f"  {col[1]}: {col[2]}")

    except Exception as e:
        conn.rollback()
        print(f"❌ 添加字段失败: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    add_category_field()
