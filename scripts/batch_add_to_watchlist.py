#!/usr/bin/env python3
"""批量添加股票到自选列表 - 通用脚本"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime
from sqlalchemy import desc as sql_desc
from src.database import session_scope
from src.models import SymbolMetadata, Watchlist, Kline, KlineTimeframe, SymbolType


def add_stocks_to_watchlist(stocks_list, simulate_purchase=False, category="未分类"):
    """
    批量添加股票到自选列表

    Args:
        stocks_list: 股票列表，格式为 [(ticker, name, description), ...]
                    例如: [("688111", "金山办公", "AI办公应用"), ...]
        simulate_purchase: 是否模拟买入（默认False，仅添加到自选）
                          如果为True，会设置买入价格、日期和股数
        category: 分类标签（默认"未分类"）
                 例如: "AI应用", "半导体", "新能源"等

    Returns:
        tuple: (added, skipped, failed) - 成功、跳过、失败的股票列表
    """
    added = []
    skipped = []
    failed = []

    with session_scope() as session:
        for stock_info in stocks_list:
            # 处理不同格式的输入
            if len(stock_info) >= 2:
                ticker = stock_info[0]
                name = stock_info[1]
                desc = stock_info[2] if len(stock_info) > 2 else ""
            else:
                failed.append((stock_info[0] if stock_info else "未知", "未知", "数据格式错误"))
                continue

            # 检查股票是否存在
            symbol = session.query(SymbolMetadata).filter(
                SymbolMetadata.ticker == ticker
            ).first()

            if not symbol:
                failed.append((ticker, name, "股票不存在于数据库"))
                continue

            # 检查是否已在自选中
            existing = session.query(Watchlist).filter(
                Watchlist.ticker == ticker
            ).first()

            if existing:
                skipped.append((ticker, name, "已在自选列表中"))
                continue

            # 根据参数决定是否模拟买入
            purchase_price = None
            shares = None
            purchase_date = None

            if simulate_purchase:
                # 获取最新收盘价作为买入价格（从 klines 表查询）
                latest_kline = session.query(Kline).filter(
                    Kline.symbol_code == ticker,
                    Kline.symbol_type == SymbolType.STOCK,
                    Kline.timeframe == KlineTimeframe.DAY
                ).order_by(sql_desc(Kline.trade_time)).first()

                purchase_date = datetime.now()

                if latest_kline and latest_kline.close:
                    purchase_price = float(latest_kline.close)
                    # 每只股票买入10000元
                    shares = 10000.0 / purchase_price if purchase_price > 0 else None

            # 添加到自选
            watchlist_item = Watchlist(
                ticker=ticker,
                purchase_price=purchase_price,
                purchase_date=purchase_date,
                shares=shares,
                category=category
            )
            session.add(watchlist_item)
            added.append((ticker, name, purchase_price, shares))

    return added, skipped, failed


def print_results(title, added, skipped, failed):
    """打印添加结果"""
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)

    if added:
        print(f"\n✅ 成功添加 {len(added)} 只股票:")
        for ticker, name, price, shares in added:
            price_str = f"¥{price:.2f}" if price else "未知"
            shares_str = f"{shares:.2f}股" if shares else "未知"
            print(f"   {ticker} {name} - 买入价: {price_str}, 股数: {shares_str}")

    if skipped:
        print(f"\n⏭️  跳过 {len(skipped)} 只股票 (已在自选中):")
        for ticker, name, reason in skipped:
            print(f"   {ticker} {name}")

    if failed:
        print(f"\n❌ 失败 {len(failed)} 只股票:")
        for ticker, name, reason in failed:
            print(f"   {ticker} {name} - {reason}")

    print("\n" + "=" * 60)
    print(f"总计: 添加 {len(added)}, 跳过 {len(skipped)}, 失败 {len(failed)}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    # 示例：如果直接运行此脚本，提示用户使用方式
    print("这是一个通用的批量添加股票到自选的脚本。")
    print("\n使用方式：")
    print("1. 在Python中导入此模块:")
    print("   from scripts.batch_add_to_watchlist import add_stocks_to_watchlist, print_results")
    print("\n2. 准备股票列表:")
    print("   stocks = [")
    print("       ('688111', '金山办公', 'AI办公应用'),")
    print("       ('002230', '科大讯飞', 'AI语音识别'),")
    print("   ]")
    print("\n3. 调用函数:")
    print("   added, skipped, failed = add_stocks_to_watchlist(stocks)")
    print("   print_results('批量添加结果', added, skipped, failed)")
    print("\n或者创建一个新的脚本，导入并使用此函数。")
