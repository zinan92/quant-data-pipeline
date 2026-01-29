#!/usr/bin/env python3
"""
初始化自选股购买价格
从最新K线数据获取价格，设置每只股票买入10000元
"""
import sqlite3
from datetime import datetime

DB_PATH = "data/market.db"


def init_watchlist_prices():
    """初始化自选股价格"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # 获取所有没有价格的自选股
    cur.execute("SELECT ticker FROM watchlist WHERE purchase_price IS NULL")
    tickers = [row[0] for row in cur.fetchall()]
    
    if not tickers:
        print("所有自选股已有价格，无需初始化")
        conn.close()
        return
    
    print(f"找到 {len(tickers)} 只待初始化的自选股")
    
    updated = 0
    failed = []
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    for ticker in tickers:
        # 获取最新K线价格 (优先DAY，否则用MINS_30)
        cur.execute("""
            SELECT close FROM klines 
            WHERE symbol_code = ? 
            AND (symbol_type = 'STOCK' OR symbol_type = 'stock')
            ORDER BY trade_time DESC
            LIMIT 1
        """, (ticker,))
        
        row = cur.fetchone()
        if row and row[0]:
            price = float(row[0])
            shares = 10000.0 / price if price > 0 else 0
            
            cur.execute("""
                UPDATE watchlist 
                SET purchase_price = ?, shares = ?, purchase_date = ?
                WHERE ticker = ?
            """, (price, shares, now, ticker))
            updated += 1
            
            if updated % 50 == 0:
                print(f"已处理 {updated} 只...")
        else:
            failed.append(ticker)
    
    conn.commit()
    conn.close()
    
    print(f"\n初始化完成:")
    print(f"  ✅ 成功: {updated} 只")
    print(f"  ❌ 失败: {len(failed)} 只 (无K线数据)")
    
    if failed and len(failed) <= 20:
        print(f"  失败列表: {', '.join(failed)}")


if __name__ == '__main__':
    init_watchlist_prices()
