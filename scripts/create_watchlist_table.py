#!/usr/bin/env python
"""
创建 watchlist 表
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database import engine
from src.models import Watchlist


def main():
    print("=" * 60)
    print("  创建 watchlist 表")
    print("=" * 60)

    # 创建表
    Watchlist.__table__.create(engine, checkfirst=True)

    print("\n✅ watchlist 表创建成功!")
    print("\n表结构:")
    print("  - id: 主键")
    print("  - ticker: 股票代码（唯一）")
    print("  - added_at: 添加时间")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
