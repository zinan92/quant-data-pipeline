#!/usr/bin/env python
"""
修复超级行业组的涨跌幅数据
使用成分行业的市值加权平均涨跌幅
"""

import sys
import csv
from pathlib import Path
from typing import Dict, List

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database import SessionLocal
from src.models import SuperCategoryDaily, IndustryDaily


def load_super_category_mapping() -> Dict[str, List[str]]:
    """加载超级行业组到行业的映射"""
    csv_path = project_root / 'data' / 'super_category_mapping.csv'

    mapping = {}
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            super_category = row['超级行业组']
            industry = row['行业名称']

            if super_category not in mapping:
                mapping[super_category] = []
            mapping[super_category].append(industry)

    return mapping


def calculate_weighted_pct_change(
    session,
    industries: List[str],
    trade_date: str
) -> float | None:
    """
    计算超级行业组的市值加权平均涨跌幅

    Args:
        session: 数据库会话
        industries: 成分行业列表
        trade_date: 交易日期

    Returns:
        加权平均涨跌幅（小数形式），如果无法计算则返回None
    """
    # 获取所有成分行业的数据
    industry_data = session.query(IndustryDaily).filter(
        IndustryDaily.trade_date == trade_date,
        IndustryDaily.industry.in_(industries)
    ).all()

    if not industry_data:
        return None

    # 计算市值加权平均
    weighted_sum = 0
    total_mv = 0

    for ind in industry_data:
        if ind.pct_change is not None and ind.total_mv:
            # 涨跌幅是百分比形式，需要转换为小数
            pct_decimal = ind.pct_change / 100
            weighted_sum += pct_decimal * ind.total_mv
            total_mv += ind.total_mv

    if total_mv == 0:
        return None

    return weighted_sum / total_mv


def fix_pct_change_for_date(trade_date: str):
    """修复指定日期的超级行业组涨跌幅"""
    session = SessionLocal()

    try:
        # 加载映射关系
        mapping = load_super_category_mapping()
        print(f"📊 加载了 {len(mapping)} 个超级行业组的映射")

        # 获取所有超级行业组记录
        records = session.query(SuperCategoryDaily).filter(
            SuperCategoryDaily.trade_date == trade_date
        ).all()

        if not records:
            print(f"❌ 未找到日期 {trade_date} 的数据")
            return

        print(f"\n🔄 开始更新 {trade_date} 的涨跌幅...")
        print("=" * 80)

        updated_count = 0

        for record in records:
            super_category = record.super_category_name
            industries = mapping.get(super_category, [])

            if not industries:
                print(f"⚠️  {super_category}: 未找到成分行业")
                continue

            # 计算加权平均涨跌幅
            pct_change = calculate_weighted_pct_change(
                session, industries, trade_date
            )

            if pct_change is not None:
                record.pct_change = pct_change
                updated_count += 1
                print(f"✅ {super_category:20s}: {pct_change*100:>7.2f}%")
            else:
                print(f"⚠️  {super_category:20s}: 无法计算")

        # 提交更改
        session.commit()

        print("=" * 80)
        print(f"✅ 成功更新了 {updated_count}/{len(records)} 个超级行业组的涨跌幅")

    except Exception as e:
        session.rollback()
        print(f"❌ 更新失败: {e}")
        raise
    finally:
        session.close()


def main():
    import sys

    if len(sys.argv) > 1:
        trade_date = sys.argv[1]
    else:
        # 使用最新日期
        session = SessionLocal()
        from sqlalchemy import func
        trade_date = session.query(
            func.max(SuperCategoryDaily.trade_date)
        ).scalar()
        session.close()

        if not trade_date:
            print("❌ 数据库中没有超级行业组数据")
            return 1

    print("=" * 80)
    print("  修复超级行业组涨跌幅数据")
    print("=" * 80)
    print(f"交易日期: {trade_date}\n")

    fix_pct_change_for_date(trade_date)

    print("\n✅ 完成!\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
