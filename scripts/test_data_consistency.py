#!/usr/bin/env python3
"""
测试数据一致性验证系统
可手动运行此脚本来验证修复效果
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.services.data_consistency_validator import DataConsistencyValidator


async def main():
    """运行数据一致性验证"""
    print("=" * 70)
    print("数据一致性验证测试")
    print("=" * 70)
    print()

    validator = DataConsistencyValidator(tolerance=0.01)

    print("开始验证...")
    print()

    results = await validator.validate_all()

    print()
    print("=" * 70)
    print("验证结果")
    print("=" * 70)

    summary = results["summary"]
    print(f"\n总计验证: {summary['total_validated']} 个标的")
    print(f"不一致数: {summary['total_inconsistencies']} 个")
    print(f"一致性率: {summary['consistency_rate']:.2f}%")
    print(f"健康状态: {'✅ 正常' if summary['is_healthy'] else '❌ 异常'}")

    if results["inconsistencies"]:
        print(f"\n发现 {len(results['inconsistencies'])} 个不一致项:")
        print("-" * 70)
        for item in results["inconsistencies"]:
            print(f"\n标的: {item['symbol_name']} ({item['symbol_code']})")
            print(f"类型: {item['symbol_type']}")
            if item.get('daily_close'):
                print(f"  日线收盘价: {item['daily_close']:.2f} ({item.get('daily_date', 'N/A')})")
            if item.get('mins30_close'):
                print(f"  30分钟收盘价: {item['mins30_close']:.2f} ({item.get('mins30_datetime', 'N/A')})")
            if item.get('realtime_price'):
                print(f"  实时价格: {item['realtime_price']:.2f}")
            print(f"  问题: {', '.join(item['inconsistency_details'])}")
    else:
        print("\n✅ 所有数据一致性验证通过！")

    print()
    print("=" * 70)

    return summary['is_healthy']


if __name__ == "__main__":
    is_healthy = asyncio.run(main())
    sys.exit(0 if is_healthy else 1)
