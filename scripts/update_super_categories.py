#!/usr/bin/env python
"""
更新股票的超级行业组字段

根据 super_category_mapping.csv 中的映射关系，
将每只股票的 industry_lv1 匹配到对应的超级行业组
"""

import sys
import csv
from pathlib import Path
from typing import Dict

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database import SessionLocal
from src.models import SymbolMetadata


def load_industry_to_super_category_mapping() -> Dict[str, str]:
    """
    加载行业到超级行业组的映射

    Returns:
        Dict[industry_name, super_category_name]: 行业名称 -> 超级行业组
    """
    csv_path = project_root / 'data' / 'super_category_mapping.csv'

    mapping = {}
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            industry_name = row['行业名称']
            super_category = row['超级行业组']
            mapping[industry_name] = super_category

    print(f"📊 加载了 {len(mapping)} 个行业的超级分类映射")
    print(f"   共 {len(set(mapping.values()))} 个超级行业组")
    return mapping


def update_stock_super_categories(mapping: Dict[str, str]):
    """
    更新所有股票的super_category字段

    Args:
        mapping: 行业名称 -> 超级行业组的映射
    """
    session = SessionLocal()

    try:
        print(f"\n💾 开始更新股票的超级行业组...")
        print("=" * 80)

        # 获取所有股票
        symbols = session.query(SymbolMetadata).all()
        total = len(symbols)

        updated_count = 0
        no_industry_count = 0
        no_mapping_count = 0

        for symbol in symbols:
            industry = symbol.industry_lv1

            if not industry:
                # 没有行业信息
                symbol.super_category = None
                no_industry_count += 1
            elif industry in mapping:
                # 找到对应的超级行业组
                symbol.super_category = mapping[industry]
                updated_count += 1
            else:
                # 行业不在映射中（可能是同花顺90行业之外的）
                symbol.super_category = None
                no_mapping_count += 1

        # 提交更改
        session.commit()

        print(f"✅ 更新完成!")
        print(f"   - 总股票数: {total}")
        print(f"   - 成功映射: {updated_count} ({updated_count/total*100:.1f}%)")
        print(f"   - 无行业信息: {no_industry_count} ({no_industry_count/total*100:.1f}%)")
        print(f"   - 行业未匹配: {no_mapping_count} ({no_mapping_count/total*100:.1f}%)")
        print("=" * 80)

        # 显示每个超级行业组的股票数
        print(f"\n📊 各超级行业组股票分布:")
        print("=" * 80)

        super_category_counts = {}
        for symbol in symbols:
            if symbol.super_category:
                super_category_counts[symbol.super_category] = \
                    super_category_counts.get(symbol.super_category, 0) + 1

        # 按股票数量降序排列
        sorted_categories = sorted(
            super_category_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )

        for category, count in sorted_categories:
            print(f"  {category:20s}: {count:>4} 只股票")

        print("=" * 80)

    except Exception as e:
        session.rollback()
        print(f"❌ 更新失败: {e}")
        raise
    finally:
        session.close()


def show_sample_results():
    """显示部分结果样例"""
    session = SessionLocal()

    try:
        print(f"\n📖 数据样例（前10只有超级行业组的股票）:")
        print("=" * 80)

        symbols = session.query(SymbolMetadata).filter(
            SymbolMetadata.super_category != None
        ).limit(10).all()

        for symbol in symbols:
            print(f"{symbol.ticker} {symbol.name}")
            print(f"  行业: {symbol.industry_lv1}")
            print(f"  超级行业组: {symbol.super_category}")
            print()

        print("=" * 80)

    finally:
        session.close()


def main():
    print("=" * 80)
    print("  更新股票超级行业组字段")
    print("=" * 80)

    # 1. 加载映射关系
    mapping = load_industry_to_super_category_mapping()

    # 2. 更新数据库
    update_stock_super_categories(mapping)

    # 3. 显示样例
    show_sample_results()

    print("\n✅ 全部完成!\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
