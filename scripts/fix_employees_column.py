"""
修复 employees 字段的数据类型问题
"""

from pathlib import Path
import sys
import struct

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from src.database import SessionLocal


def fix_employees_column():
    """修复 employees 列的数据类型"""
    session = SessionLocal()
    try:
        # 删除现有的 employees 列
        print("删除旧的 employees 列...")
        session.execute(text("ALTER TABLE symbol_metadata DROP COLUMN employees"))
        session.commit()

        # 重新添加正确类型的列
        print("添加新的 employees 列...")
        session.execute(text("ALTER TABLE symbol_metadata ADD COLUMN employees INTEGER"))
        session.commit()

        print("✅ employees 列已修复！")
    except Exception as e:
        print(f"❌ 错误: {e}")
        session.rollback()
    finally:
        session.close()


if __name__ == "__main__":
    fix_employees_column()
