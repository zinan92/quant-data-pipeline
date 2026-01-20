"""
添加公司信息字段到 symbol_metadata 表
"""

from pathlib import Path
import sys

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from src.database import SessionLocal


def add_company_info_columns():
    """添加公司信息相关的列到 symbol_metadata 表"""
    session = SessionLocal()
    try:
        # 检查列是否已存在 (SQLite)
        result = session.execute(text("PRAGMA table_info(symbol_metadata)"))
        existing_columns = {row[1] for row in result.fetchall()}

        if 'introduction' in existing_columns:
            print("✅ 公司信息列已存在，跳过迁移")
            return

        print("正在添加公司信息列...")

        # 添加所有新列
        columns_to_add = [
            ("introduction", "TEXT"),
            ("main_business", "TEXT"),
            ("business_scope", "TEXT"),
            ("chairman", "VARCHAR(64)"),
            ("manager", "VARCHAR(64)"),
            ("reg_capital", "FLOAT"),
            ("setup_date", "VARCHAR(10)"),
            ("province", "VARCHAR(32)"),
            ("city", "VARCHAR(32)"),
            ("employees", "INTEGER"),
            ("website", "VARCHAR(128)"),
        ]

        for column_name, column_type in columns_to_add:
            try:
                session.execute(text(f"""
                    ALTER TABLE symbol_metadata
                    ADD COLUMN {column_name} {column_type}
                """))
                print(f"  ✓ 添加列: {column_name}")
            except Exception as e:
                print(f"  ⚠ 跳过 {column_name}: {e}")

        session.commit()
        print("✅ 数据库迁移完成！")
    finally:
        session.close()


if __name__ == "__main__":
    add_company_info_columns()
