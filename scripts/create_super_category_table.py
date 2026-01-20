"""创建 super_category_daily 表"""

from sqlalchemy import text
from src.database import SessionLocal, engine
from src.models import SuperCategoryDaily, Base


def create_super_category_table():
    """创建超级行业组每日数据表"""
    print("Creating super_category_daily table...")

    # 创建表
    Base.metadata.create_all(engine, tables=[SuperCategoryDaily.__table__])

    # 验证表是否创建成功
    session = SessionLocal()
    try:
        result = session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='super_category_daily';")
        )
        table_exists = result.fetchone()

        if table_exists:
            print("✓ Table 'super_category_daily' created successfully!")

            # 显示表结构
            result = session.execute(text("PRAGMA table_info(super_category_daily);"))
            columns = result.fetchall()

            print("\nTable structure:")
            print("=" * 60)
            for col in columns:
                print(f"  {col[1]:<30} {col[2]:<15} {'NOT NULL' if col[3] else 'NULL'}")
            print("=" * 60)
        else:
            print("✗ Failed to create table")
    finally:
        session.close()


if __name__ == "__main__":
    create_super_category_table()
