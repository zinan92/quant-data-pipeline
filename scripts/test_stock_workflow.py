#!/usr/bin/env python3
"""
快速测试脚本：验证股票添加工作流程

使用测试股票验证整个流程：
1. 创建标准化模版
2. 添加到数据库
3. 验证数据完整性
4. 验证API服务
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.add_stock import add_stock_with_validation


# 测试股票（使用常见的大盘股）
TEST_STOCKS = [
    ("600519", "贵州茅台", "消费"),
    ("000001", "平安银行", "金融"),
    ("300750", "宁德时代", "新能源"),
]


def run_workflow_test():
    """运行工作流程测试"""
    print("=" * 70)
    print("STOCK ADDITION WORKFLOW TEST")
    print("=" * 70)
    print("\nThis test will:")
    print("1. Add test stocks to watchlist")
    print("2. Validate data integrity")
    print("3. Validate API services")
    print("4. Generate comprehensive reports")
    print("\n" + "=" * 70)

    input("\nPress Enter to start the test...")

    success_count = 0
    failed_count = 0

    for ticker, name, sector in TEST_STOCKS:
        print(f"\n{'=' * 70}")
        print(f"Testing: {name} ({ticker})")
        print(f"{'=' * 70}")

        try:
            result = add_stock_with_validation(
                ticker=ticker,
                name=name,
                sector=sector,
                simulate_purchase=False,
                skip_validation=False
            )

            if result:
                success_count += 1
                print(f"✅ {name} passed all validations")
            else:
                failed_count += 1
                print(f"⚠️  {name} completed with warnings")

        except Exception as e:
            failed_count += 1
            print(f"❌ {name} failed: {e}")

        print()

    # 总结
    print("=" * 70)
    print("WORKFLOW TEST SUMMARY")
    print("=" * 70)
    print(f"Total tests: {len(TEST_STOCKS)}")
    print(f"Success: {success_count}")
    print(f"Failed/Warnings: {failed_count}")
    print("=" * 70)

    if failed_count == 0:
        print("\n✅ All tests passed! Workflow is working correctly.")
        print("\nNext steps:")
        print("1. Run E2E tests: npx playwright test tests/e2e/test_watchlist_card.spec.ts")
        print("2. Check frontend: http://localhost:5173")
        print("3. Verify cards display all information correctly")
    else:
        print(f"\n⚠️  {failed_count} tests had issues. Please review the reports above.")
        print("\nTroubleshooting:")
        print("1. Ensure backend is running: uvicorn src.main:app --reload")
        print("2. Check database exists: ls -lh data/stocks.db")
        print("3. Verify network connectivity")

    print()


if __name__ == "__main__":
    try:
        run_workflow_test()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
