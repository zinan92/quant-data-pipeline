#!/usr/bin/env python3
"""添加AI应用概念股到自选列表"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from batch_add_to_watchlist import add_stocks_to_watchlist, print_results


# 20只AI应用概念股（来自截图）
AI_APPLICATION_STOCKS = [
    ("688111", "金山办公", "AI办公"),
    ("002602", "世纪华通", "AI应用"),
    ("002230", "科大讯飞", "AI应用"),
    ("002558", "巨人网络", "AI应用"),
    ("601360", "三六零", "AI应用"),
    ("300418", "昆仑万维", "AI应用"),
    ("300058", "蓝色光标", "AI应用"),
    ("301638", "南网数字", "AI应用"),
    ("002195", "二三四五", "AI应用"),
    ("300454", "深信服", "AI应用"),
    ("002555", "三七互娱", "AI应用"),
    ("002131", "利欧股份", "AI应用"),
    ("600588", "用友网络", "AI应用"),
    ("002517", "恺英网络", "AI应用"),
    ("301236", "软通动力", "AI应用"),
    ("600637", "东方明珠", "AI应用"),
    ("600699", "均胜电子", "AI应用"),
    ("300496", "中科创达", "AI应用"),
    ("002624", "完美世界", "AI应用"),
    ("301171", "易点天下", "AI应用"),
]


if __name__ == "__main__":
    print("开始批量添加AI应用概念股到自选...")
    # simulate_purchase=False 表示只添加到自选，不模拟买入
    # category="AI应用" 设置分类标签
    added, skipped, failed = add_stocks_to_watchlist(
        AI_APPLICATION_STOCKS,
        simulate_purchase=False,
        category="AI应用"
    )
    print_results("AI应用概念股添加结果", added, skipped, failed)
