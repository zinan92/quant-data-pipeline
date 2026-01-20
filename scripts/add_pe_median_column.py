#!/usr/bin/env python
"""
添加 pe_median 列到 industry_daily 表
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database import engine
from sqlalchemy import text


def main():
    print("=" * 60)
    print("  添加 pe_median 列到 industry_daily 表")
    print("=" * 60)

    with engine.connect() as conn:
        # 检查列是否已存在
        result = conn.execute(
            text("PRAGMA table_info(industry_daily);")
        ).fetchall()

        columns = [row[1] for row in result]

        if 'pe_median' in columns:
            print("\n⚠️  pe_median 列已存在")
        else:
            # 添加列
            conn.execute(
                text("ALTER TABLE industry_daily ADD COLUMN pe_median REAL;")
            )
            conn.commit()
            print("\n✅ pe_median 列添加成功!")

    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
