#!/usr/bin/env python
"""
计算并更新每个板块的PE中位数
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database import SessionLocal
from src.models import IndustryDaily, BoardMapping, SymbolMetadata
from sqlalchemy import func


def calculate_median(values):
    """计算中位数"""
    if not values:
        return None
    sorted_values = sorted(values)
    n = len(sorted_values)
    if n % 2 == 0:
        return (sorted_values[n//2 - 1] + sorted_values[n//2]) / 2
    else:
        return sorted_values[n//2]


def main():
    print("=" * 60)
    print("  计算并更新板块PE中位数")
    print("=" * 60)

    session = SessionLocal()

    try:
        # 获取最新交易日
        latest_date = session.query(
            func.max(IndustryDaily.trade_date)
        ).scalar()

        print(f"\n最新交易日: {latest_date}")

        # 获取该交易日的所有板块数据
        industries = session.query(IndustryDaily).filter(
            IndustryDaily.trade_date == latest_date
        ).all()

        print(f"找到 {len(industries)} 个板块\n")

        updated_count = 0
        skipped_count = 0

        for industry in industries:
            board_name = industry.industry

            # 获取板块成分股
            board_mapping = session.query(BoardMapping).filter(
                BoardMapping.board_name == board_name,
                BoardMapping.board_type == "industry"
            ).first()

            if not board_mapping or not board_mapping.constituents:
                print(f"⚠️  {board_name}: 无成分股数据")
                skipped_count += 1
                continue

            # 获取成分股的PE数据
            symbols = session.query(SymbolMetadata).filter(
                SymbolMetadata.ticker.in_(board_mapping.constituents)
            ).all()

            # 提取有效的PE值（大于0）
            pe_values = [s.pe_ttm for s in symbols if s.pe_ttm is not None and s.pe_ttm > 0]

            if not pe_values:
                print(f"⚠️  {board_name}: 无有效PE数据")
                skipped_count += 1
                continue

            # 计算中位数
            pe_median = calculate_median(pe_values)

            # 更新到数据库
            industry.pe_median = pe_median
            updated_count += 1

            print(f"✅ {board_name}: PE中位数 = {pe_median:.2f} (基于 {len(pe_values)} 只股票)")

        # 提交更改
        session.commit()

        print("\n" + "=" * 60)
        print(f"✅ 更新完成!")
        print(f"   成功更新: {updated_count} 个板块")
        print(f"   跳过: {skipped_count} 个板块")
        print("=" * 60)

        return 0

    except Exception as e:
        session.rollback()
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
