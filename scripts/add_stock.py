#!/usr/bin/env python3
"""
统一的股票添加入口
使用标准化模版添加股票，并自动验证所有服务
"""

import sys
import argparse
from pathlib import Path
from typing import List, Tuple

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from templates.stock_template import create_stock_template, StockTemplate
from validators.data_validator import DataValidator
from validators.api_validator import APIValidator
from batch_add_to_watchlist import add_stocks_to_watchlist
from update_stock_sectors import update_sectors


def add_stock_with_validation(
    ticker: str,
    name: str,
    sector: str = "未分类",
    simulate_purchase: bool = False,
    skip_validation: bool = False
) -> bool:
    """
    添加股票并进行完整验证

    Args:
        ticker: 股票代码
        name: 股票名称
        sector: 赛道分类
        simulate_purchase: 是否同时添加到模拟组合
        skip_validation: 是否跳过验证（不推荐）

    Returns:
        bool: 是否成功
    """
    print("=" * 70)
    print(f"ADDING STOCK: {name} ({ticker})")
    print("=" * 70)

    # 1. 创建标准化模版
    try:
        stock = create_stock_template(
            ticker=ticker,
            name=name,
            sector=sector,
            add_to_simulated=simulate_purchase
        )
    except ValueError as e:
        print(f"\n❌ Failed to create stock template: {e}")
        return False

    # 检查是否支持
    if not stock.is_supported():
        print(f"\n⚠️  WARNING: {stock.name} is a Beijing Stock Exchange (BSE) stock.")
        print("    Realtime price data will not be available via Sina Finance API.")
        response = input("    Continue anyway? (y/N): ")
        if response.lower() != 'y':
            print("    Aborted.")
            return False

    print(f"\n📋 Stock Template Created:")
    print(f"   Ticker: {stock.get_full_ticker()}")
    print(f"   Name: {stock.name}")
    print(f"   Sector: {stock.sector}")
    print(f"   Exchange: {stock.exchange.value}")
    print(f"   Supported: {'Yes' if stock.is_supported() else 'No (BSE)'}")

    # 2. 添加到数据库
    print(f"\n📝 Step 1: Adding to database...")
    added, skipped, failed = add_stocks_to_watchlist(
        [(stock.ticker, stock.name, stock.sector)],
        simulate_purchase=simulate_purchase,
        category=stock.sector
    )

    if len(failed) > 0:
        print(f"   ❌ Failed to add stock to database")
        return False

    if len(skipped) > 0:
        print(f"   ⚠️  Stock already exists in watchlist")
    else:
        print(f"   ✅ Stock added to watchlist")

    # 3. 更新赛道分类
    print(f"\n🏷️  Step 2: Updating sector classification...")
    updated, inserted, failed_sectors = update_sectors([stock.ticker], stock.sector)

    if len(failed_sectors) > 0:
        print(f"   ❌ Failed to update sector: {failed_sectors}")
        return False

    if len(updated) > 0:
        print(f"   ✅ Sector updated")
    elif len(inserted) > 0:
        print(f"   ✅ Sector inserted")

    # 4. 验证数据完整性
    if not skip_validation:
        print(f"\n🔍 Step 3: Validating data integrity...")
        with DataValidator(stock) as validator:
            data_result = validator.validate_all()

        if not data_result.is_success():
            print(f"\n⚠️  Data validation found issues:")
            data_result.print_report()
            print(f"\n💡 TIP: Run data sync to fetch missing data:")
            print(f"   python scripts/sync_stock_data.py {stock.ticker}")
        else:
            print(f"   ✅ All data checks passed")

        # 5. 验证API服务
        print(f"\n🌐 Step 4: Validating API services...")
        api_validator = APIValidator(stock)
        api_result = api_validator.validate_all()

        if not api_result.is_success():
            print(f"\n⚠️  API validation found issues:")
            api_result.print_report()
        else:
            print(f"   ✅ All API checks passed")

        # 总结
        print("\n" + "=" * 70)
        if data_result.is_success() and api_result.is_success():
            print("✅ SUCCESS: Stock added and all validations passed!")
        else:
            print("⚠️  PARTIAL SUCCESS: Stock added but some validations failed")
            print("   Please review the validation reports above")
        print("=" * 70 + "\n")

        return data_result.is_success() and api_result.is_success()
    else:
        print("\n⚠️  Validation skipped")
        print("=" * 70 + "\n")
        return True


def add_batch_stocks(
    stocks: List[Tuple[str, str, str]],
    simulate_purchase: bool = False,
    skip_validation: bool = False
) -> Tuple[int, int]:
    """
    批量添加股票

    Args:
        stocks: [(ticker, name, sector), ...]
        simulate_purchase: 是否同时添加到模拟组合
        skip_validation: 是否跳过验证

    Returns:
        (success_count, failed_count)
    """
    print(f"\n{'=' * 70}")
    print(f"BATCH ADDING {len(stocks)} STOCKS")
    print(f"{'=' * 70}\n")

    success = 0
    failed = 0

    for ticker, name, sector in stocks:
        try:
            if add_stock_with_validation(ticker, name, sector, simulate_purchase, skip_validation):
                success += 1
            else:
                failed += 1
        except Exception as e:
            print(f"\n❌ Exception while adding {name} ({ticker}): {e}")
            failed += 1

        print()  # 空行分隔

    # 总结
    print("=" * 70)
    print("BATCH ADDITION SUMMARY")
    print("=" * 70)
    print(f"Total: {len(stocks)} stocks")
    print(f"Success: {success} stocks")
    print(f"Failed: {failed} stocks")
    print("=" * 70 + "\n")

    return success, failed


def main():
    parser = argparse.ArgumentParser(
        description="Add stock to watchlist using standardized template",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Add single stock
  python add_stock.py 600519 贵州茅台 --sector 消费

  # Add with simulated purchase
  python add_stock.py 000001 平安银行 --sector 金融 --simulate

  # Skip validation (faster, not recommended)
  python add_stock.py 300750 宁德时代 --sector 新能源 --skip-validation

  # Add multiple stocks from file
  python add_stock.py --batch stocks.txt
        """
    )

    parser.add_argument('ticker', nargs='?', help='Stock ticker (6 digits)')
    parser.add_argument('name', nargs='?', help='Stock name')
    parser.add_argument('--sector', '-s', default='未分类', help='Sector/industry classification')
    parser.add_argument('--simulate', action='store_true', help='Also add to simulated portfolio')
    parser.add_argument('--skip-validation', action='store_true', help='Skip validation checks')
    parser.add_argument('--batch', '-b', type=str, help='Batch add from file (format: ticker,name,sector per line)')

    args = parser.parse_args()

    # 批量添加模式
    if args.batch:
        batch_file = Path(args.batch)
        if not batch_file.exists():
            print(f"❌ Batch file not found: {args.batch}")
            sys.exit(1)

        stocks = []
        with open(batch_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    parts = line.split(',')
                    if len(parts) >= 2:
                        ticker = parts[0].strip()
                        name = parts[1].strip()
                        sector = parts[2].strip() if len(parts) > 2 else '未分类'
                        stocks.append((ticker, name, sector))

        if not stocks:
            print(f"❌ No valid stocks found in {args.batch}")
            sys.exit(1)

        add_batch_stocks(stocks, args.simulate, args.skip_validation)

    # 单个股票添加模式
    elif args.ticker and args.name:
        success = add_stock_with_validation(
            ticker=args.ticker,
            name=args.name,
            sector=args.sector,
            simulate_purchase=args.simulate,
            skip_validation=args.skip_validation
        )
        sys.exit(0 if success else 1)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
