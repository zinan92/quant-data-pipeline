#!/usr/bin/env python3
"""更新自选股的分类标签"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import session_scope
from src.models import Watchlist


def update_category(tickers, category):
    """
    更新指定股票的分类

    Args:
        tickers: 股票代码列表，例如: ["688111", "002230"]
        category: 分类标签，例如: "AI应用"

    Returns:
        tuple: (updated, not_found) - 更新成功和未找到的股票列表
    """
    updated = []
    not_found = []

    with session_scope() as session:
        for ticker in tickers:
            watchlist_item = session.query(Watchlist).filter(
                Watchlist.ticker == ticker
            ).first()

            if watchlist_item:
                watchlist_item.category = category
                updated.append(ticker)
            else:
                not_found.append(ticker)

    return updated, not_found


# AI应用概念股列表（20只）
AI_APPLICATION_TICKERS = [
    "688111",  # 金山办公
    "002602",  # 世纪华通
    "002230",  # 科大讯飞
    "002558",  # 巨人网络
    "601360",  # 三六零
    "300418",  # 昆仑万维
    "300058",  # 蓝色光标
    "301638",  # 南网数字
    "002195",  # 二三四五
    "300454",  # 深信服
    "002555",  # 三七互娱
    "002131",  # 利欧股份
    "600588",  # 用友网络
    "002517",  # 恺英网络
    "301236",  # 软通动力
    "600637",  # 东方明珠
    "600699",  # 均胜电子
    "300496",  # 中科创达
    "002624",  # 完美世界
    "301171",  # 易点天下
]


if __name__ == "__main__":
    print("开始更新AI应用概念股的分类...")
    updated, not_found = update_category(AI_APPLICATION_TICKERS, "AI应用")

    print("\n" + "=" * 60)
    print("更新结果")
    print("=" * 60)

    if updated:
        print(f"\n✅ 成功更新 {len(updated)} 只股票:")
        for ticker in updated:
            print(f"   {ticker} → AI应用")

    if not_found:
        print(f"\n⚠️  未找到 {len(not_found)} 只股票（不在自选列表中）:")
        for ticker in not_found:
            print(f"   {ticker}")

    print("\n" + "=" * 60)
    print(f"总计: 更新 {len(updated)}, 未找到 {len(not_found)}")
    print("=" * 60 + "\n")
