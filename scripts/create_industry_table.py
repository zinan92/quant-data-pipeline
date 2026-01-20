#!/usr/bin/env python
"""
创建 industry_daily 表
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database import engine, Base
from src.models import IndustryDaily

def main():
    print("=" * 60)
    print("  创建 industry_daily 表")
    print("=" * 60)

    # 创建表
    print("\n创建表...")
    IndustryDaily.__table__.create(engine, checkfirst=True)
    print("✓ 表创建成功！")

    return 0


if __name__ == "__main__":
    sys.exit(main())
