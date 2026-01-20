#!/usr/bin/env python
"""为watchlist表添加买入价格和日期字段"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database import engine
from sqlalchemy import text

def add_purchase_fields():
    print("=" * 60)
    print("  为watchlist表添加买入信息字段")
    print("=" * 60)

    with engine.connect() as conn:
        # 添加purchase_price字段（买入价格）
        try:
            conn.execute(text("""
                ALTER TABLE watchlist
                ADD COLUMN purchase_price FLOAT
            """))
            print("\n✅ 添加 purchase_price 字段")
        except Exception as e:
            if "duplicate column" in str(e).lower():
                print("\n⚠️  purchase_price 字段已存在")
            else:
                raise

        # 添加purchase_date字段（买入日期）
        try:
            conn.execute(text("""
                ALTER TABLE watchlist
                ADD COLUMN purchase_date DATETIME
            """))
            print("✅ 添加 purchase_date 字段")
        except Exception as e:
            if "duplicate column" in str(e).lower():
                print("⚠️  purchase_date 字段已存在")
            else:
                raise

        # 添加shares字段（持有股数，根据10000元计算）
        try:
            conn.execute(text("""
                ALTER TABLE watchlist
                ADD COLUMN shares FLOAT
            """))
            print("✅ 添加 shares 字段")
        except Exception as e:
            if "duplicate column" in str(e).lower():
                print("⚠️  shares 字段已存在")
            else:
                raise

        conn.commit()

    print("\n" + "=" * 60)
    print("  ✅ 数据库结构更新完成")
    print("=" * 60)

if __name__ == "__main__":
    add_purchase_fields()
