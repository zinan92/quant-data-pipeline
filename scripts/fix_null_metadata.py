#!/usr/bin/env python3
"""
One-shot fix: refresh symbol_metadata for watchlist stocks with null total_mv.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import sqlite3
from src.services.tushare_client import TushareClient
import pandas as pd
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "market.db")

def main():
    # Find null stocks
    conn = sqlite3.connect(DB_PATH)
    null_tickers = [row[0] for row in conn.execute("""
        SELECT w.ticker FROM watchlist w
        JOIN symbol_metadata sm ON w.ticker = sm.ticker
        WHERE sm.total_mv IS NULL OR sm.total_mv = 0
    """).fetchall()]
    
    print(f"Found {len(null_tickers)} stocks with null total_mv")
    if not null_tickers:
        print("Nothing to fix!")
        return
    
    # Init Tushare
    client = TushareClient(token=os.getenv("TUSHARE_TOKEN"))
    
    # Get latest trade date with data
    latest = client.get_latest_trade_date(with_data=True)
    print(f"Using trade date: {latest}")
    
    # Fetch daily_basic
    daily_df = client.fetch_daily_basic(trade_date=latest)
    if len(daily_df) == 0:
        # Fallback
        from datetime import timedelta
        for i in range(1, 5):
            fallback = (datetime.strptime(latest, '%Y%m%d') - timedelta(days=i)).strftime('%Y%m%d')
            daily_df = client.fetch_daily_basic(trade_date=fallback)
            if len(daily_df) > 0:
                print(f"Using fallback date: {fallback} ({len(daily_df)} rows)")
                break
    
    if len(daily_df) == 0:
        print("ERROR: No daily_basic data available")
        return
    
    daily_dict = daily_df.set_index('ts_code').to_dict('index')
    
    # Update each null ticker
    updated = 0
    for ticker in null_tickers:
        ts_code = client.normalize_ts_code(ticker)
        row = daily_dict.get(ts_code, {})
        total_mv = row.get('total_mv')
        circ_mv = row.get('circ_mv')
        pe_ttm = row.get('pe_ttm')
        pb = row.get('pb')
        
        if total_mv and pd.notna(total_mv):
            pe_val = float(pe_ttm) if pd.notna(pe_ttm) else None
            pb_val = float(pb) if pd.notna(pb) else None
            conn.execute("""
                UPDATE symbol_metadata 
                SET total_mv = ?, circ_mv = ?, pe_ttm = ?, pb = ?, last_sync = ?
                WHERE ticker = ?
            """, (float(total_mv), float(circ_mv) if pd.notna(circ_mv) else None, 
                  pe_val, pb_val, datetime.now().isoformat(), ticker))
            updated += 1
            print(f"  ✅ {ticker}: total_mv={total_mv:.0f}")
        else:
            print(f"  ⚠️ {ticker}: still no data in daily_basic")
    
    conn.commit()
    conn.close()
    print(f"\nDone: updated {updated}/{len(null_tickers)} stocks")


if __name__ == "__main__":
    main()
