#!/usr/bin/env python3
"""添加创新药概念股到自选列表"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from batch_add_to_watchlist import add_stocks_to_watchlist, print_results
from update_stock_sectors import update_sectors


# 21只创新药概念股（来自截图）
INNOVATIVE_DRUGS_STOCKS = [
    ("920670", "数字人", "创新药"),
    ("301333", "诺思格", "创新药"),
    ("301257", "普蕊斯", "创新药"),
    ("301230", "泓博医药", "创新药"),
    ("300244", "迪安诊断", "创新药"),
    ("301060", "兰卫医学", "创新药"),
    ("300404", "博济医药", "创新药"),
    ("300676", "华大基因", "创新药"),
    ("688222", "成都先导", "创新药"),
    ("301520", "万邦医药", "创新药"),
    ("002219", "新里程", "创新药"),
    ("002172", "澳洋健康", "创新药"),
    ("000710", "贝瑞基因", "创新药"),
    ("000516", "国际医学", "创新药"),
    ("002044", "美年健康", "创新药"),
    ("300725", "药石科技", "创新药"),
    ("688073", "毕得医药", "创新药"),
    ("688202", "美迪西", "创新药"),
    ("301509", "金凯生科", "创新药"),
    ("300759", "康龙化成", "创新药"),
    ("603259", "药明康德", "创新药"),
]


if __name__ == "__main__":
    print("=" * 60)
    print("开始批量添加创新药概念股")
    print("=" * 60)

    # 1. 添加到自选列表（不模拟买入）
    print("\n步骤1: 添加股票到自选列表...")
    added, skipped, failed = add_stocks_to_watchlist(
        INNOVATIVE_DRUGS_STOCKS,
        simulate_purchase=False,
        category="创新药"  # 虽然watchlist表有category字段，但实际不使用
    )
    print_results("添加到自选列表结果", added, skipped, failed)

    # 2. 更新赛道分类到 stock_sectors 表
    print("\n步骤2: 更新赛道分类到 stock_sectors 表...")
    tickers = [stock[0] for stock in INNOVATIVE_DRUGS_STOCKS]
    updated, inserted, failed_sectors = update_sectors(tickers, "创新药")

    print("\n" + "=" * 60)
    print("✅ 批量添加创新药概念股完成！")
    print("=" * 60)
    print(f"自选列表: 添加 {len(added)}, 跳过 {len(skipped)}, 失败 {len(failed)}")
    print(f"赛道分类: 更新 {len(updated)}, 插入 {len(inserted)}, 失败 {len(failed_sectors)}")
    print("=" * 60 + "\n")
