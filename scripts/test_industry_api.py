#!/usr/bin/env python
"""
测试新的行业接口
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database import SessionLocal
from src.models import IndustryDaily
from sqlalchemy import func


def main():
    print("=" * 60)
    print("  测试行业数据接口")
    print("=" * 60)

    session = SessionLocal()

    try:
        # 获取最新交易日
        latest_date = session.query(
            func.max(IndustryDaily.trade_date)
        ).scalar()

        print(f"\n最新交易日: {latest_date}")

        # 查询最新交易日的数据
        industries = session.query(IndustryDaily).filter(
            IndustryDaily.trade_date == latest_date
        ).order_by(IndustryDaily.pct_change.desc()).all()

        print(f"总行业数: {len(industries)}")

        print("\n涨幅前10的行业:")
        print(f"{'行业名称':<15} {'涨跌幅':<10} {'上涨':<8} {'下跌':<8} {'PE':<10} {'总市值(亿)':<12}")
        print("-" * 80)

        for ind in industries[:10]:
            pe_str = f"{ind.industry_pe:.2f}" if ind.industry_pe else "N/A"
            mv_str = f"{ind.total_mv / 10000:.2f}" if ind.total_mv else "0.00"
            print(f"{ind.industry:<15} {ind.pct_change:>8.2f}% {ind.up_count or 0:>6} {ind.down_count or 0:>6} {pe_str:>8} {mv_str:>10}")

        print("\n跌幅前10的行业:")
        for ind in industries[-10:]:
            pe_str = f"{ind.industry_pe:.2f}" if ind.industry_pe else "N/A"
            mv_str = f"{ind.total_mv / 10000:.2f}" if ind.total_mv else "0.00"
            print(f"{ind.industry:<15} {ind.pct_change:>8.2f}% {ind.up_count or 0:>6} {ind.down_count or 0:>6} {pe_str:>8} {mv_str:>10}")

        print("\n" + "=" * 60)
        print("  ✅ 数据查询成功！")
        print("=" * 60)

        return 0

    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
