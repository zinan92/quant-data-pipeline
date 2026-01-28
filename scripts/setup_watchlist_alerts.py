#!/usr/bin/env python3
"""
设置自选股智能推送规则
根据 watchlist 数据库设置监控规则
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
from src.services.news import get_smart_alert_system


def get_watchlist_by_category():
    """获取按分类的自选股"""
    conn = sqlite3.connect('data/market.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT ticker, category FROM watchlist')
    watchlist = cursor.fetchall()
    
    categories = {}
    for ticker, cat in watchlist:
        cat = cat or '未分类'
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(ticker)
    
    conn.close()
    return categories


def setup_alerts():
    """设置智能推送规则"""
    system = get_smart_alert_system()
    categories = get_watchlist_by_category()
    
    print("设置自选股监控规则...")
    print()
    
    # 为每个分类添加规则
    for category, tickers in categories.items():
        if category == '未分类':
            continue  # 跳过未分类
        
        # 添加股票代码规则
        system.add_stock_rule(
            name=f"自选股-{category}",
            stock_codes=tickers,
            priority='high',
            cooldown_minutes=3
        )
        print(f"✅ 添加规则: 自选股-{category} ({len(tickers)} 只)")
    
    # 添加重点股票规则（未分类中选前20只）
    uncategorized = categories.get('未分类', [])[:20]
    if uncategorized:
        system.add_stock_rule(
            name="自选股-重点关注",
            stock_codes=uncategorized,
            priority='high',
            cooldown_minutes=3
        )
        print(f"✅ 添加规则: 自选股-重点关注 ({len(uncategorized)} 只)")
    
    print()
    print("当前所有规则:")
    for rule in system.get_rules():
        print(f"  • {rule['name']} ({rule['type']}) - {rule['priority']}")


if __name__ == '__main__':
    setup_alerts()
