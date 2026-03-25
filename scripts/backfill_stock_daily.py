#!/usr/bin/env python3
"""
Backfill 5 years of daily kline data for all stocks in the expanded universe.

This script:
1. Reads stock list from watchlist table (post-expansion, >= 800 stocks)
2. For each stock, checks existing data: SELECT MAX(trade_time) FROM klines
3. Determines start_date: MAX of (stock's list_date from stock_basic, '20210101')
4. Calls TushareClient.fetch_daily() for missing range
5. Inserts into klines table using UPSERT (INSERT OR REPLACE) to avoid duplicates
6. Uses existing RateLimiter (180 calls/min)
7. Logs progress every 50 stocks
8. Tracks progress in DataUpdateLog
9. Handles delisted/suspended stocks gracefully (empty response = skip with warning)
10. Supports resume: if interrupted, re-running skips stocks that already have data

Field mapping: TuShare (ts_code, trade_date, open, high, low, close, vol, amount)
              -> klines (symbol_code, trade_time, open, high, low, close, volume, amount)

Usage:
    python scripts/backfill_stock_daily.py [--dry-run] [--limit N]

Options:
    --dry-run: Print what would be done without actually backfilling
    --limit N: Only process first N stocks (for testing)
"""

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3

from src.config import get_settings
from src.models import DataUpdateStatus, KlineTimeframe, SymbolType
from src.models.kline import DataUpdateLog
from src.services.kline_service import KlineService
from src.services.tushare_client import TushareClient
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Constants
TARGET_START_DATE = "20210101"  # 2021-01-01
PROGRESS_LOG_INTERVAL = 50  # Log progress every N stocks


class StockDailyBackfiller:
    """Stock daily kline data backfiller"""

    def __init__(self, dry_run: bool = False, limit: Optional[int] = None):
        """
        Initialize backfiller

        Args:
            dry_run: If True, only print what would be done
            limit: If set, only process first N stocks
        """
        self.dry_run = dry_run
        self.limit = limit
        self.settings = get_settings()
        self.db_path = self.settings.database_url.replace("sqlite:///", "")
        
        # Initialize TuShare client
        self.tushare_client = TushareClient(
            token=self.settings.tushare_token,
            points=self.settings.tushare_points
        )
        
        # Stats
        self.total_stocks = 0
        self.processed_count = 0
        self.success_count = 0
        self.skip_count = 0
        self.fail_count = 0
        self.total_rows_inserted = 0
        self.start_time = None

    def get_watchlist_stocks(self) -> list[tuple[str, str, Optional[str]]]:
        """
        Get all stocks from watchlist with their metadata

        Returns:
            List of tuples (ticker, name, list_date)
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Join watchlist with stock_basic to get list_date
        query = """
        SELECT DISTINCT 
            w.ticker,
            COALESCE(sb.name, sm.name, w.ticker) as name,
            sb.list_date
        FROM watchlist w
        LEFT JOIN stock_basic sb ON w.ticker = sb.symbol
        LEFT JOIN symbol_metadata sm ON w.ticker = sm.ticker
        ORDER BY w.ticker
        """
        
        cursor.execute(query)
        stocks = cursor.fetchall()
        conn.close()

        return stocks

    def get_existing_data_range(self, ticker: str, session=None) -> Optional[str]:
        """
        Get the latest trade_time for a stock's daily klines

        Args:
            ticker: Stock ticker (6-digit)
            session: Optional SQLAlchemy session (for testing)

        Returns:
            Latest trade_time as string (YYYY-MM-DD) or None if no data exists
        """
        if session:
            # Use SQLAlchemy session for testing
            from sqlalchemy import select, func
            from src.models.kline import Kline
            stmt = select(func.max(Kline.trade_time)).where(
                Kline.symbol_type == SymbolType.STOCK,
                Kline.symbol_code == ticker,
                Kline.timeframe == KlineTimeframe.DAY
            )
            result = session.execute(stmt).scalar()
            return result
        else:
            # Use raw sqlite3 for production
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            query = """
            SELECT MAX(trade_time) 
            FROM klines 
            WHERE symbol_type = ? 
              AND symbol_code = ? 
              AND timeframe = ?
            """
            
            cursor.execute(query, (SymbolType.STOCK.value, ticker, KlineTimeframe.DAY.value))
            result = cursor.fetchone()
            conn.close()

            return result[0] if result and result[0] else None

    def determine_start_date(self, ticker: str, list_date: Optional[str]) -> str:
        """
        Determine the start date for backfilling

        For post-2021 IPO stocks, start from their list_date.
        For pre-2021 stocks, start from 2021-01-01.

        Args:
            ticker: Stock ticker
            list_date: Stock's list_date from stock_basic (YYYYMMDD format)

        Returns:
            Start date in YYYYMMDD format
        """
        # Default to 2021-01-01
        default_start = TARGET_START_DATE

        if not list_date:
            return default_start

        # Compare list_date with 2021-01-01
        if list_date > TARGET_START_DATE:
            # Post-2021 IPO, start from list_date
            return list_date
        else:
            # Pre-2021 stock, start from 2021-01-01
            return default_start

    def should_skip_stock(self, ticker: str, max_existing_date: Optional[str]) -> bool:
        """
        Determine if a stock should be skipped (already has recent data)

        Args:
            ticker: Stock ticker
            max_existing_date: Latest trade_time in database (YYYY-MM-DD format)

        Returns:
            True if stock should be skipped (has data within last 30 days)
        """
        if not max_existing_date:
            return False

        # Parse the max_existing_date
        try:
            max_date = datetime.strptime(max_existing_date, "%Y-%m-%d")
        except ValueError:
            return False

        # Check if data is recent (within last 30 days)
        cutoff_date = datetime.now() - timedelta(days=30)
        
        # If max_date is recent and >= 2021-01-01, consider it complete
        if max_date >= cutoff_date:
            # Also check if it has data going back to 2021
            min_date_str = self.get_min_trade_date(ticker)
            if min_date_str:
                try:
                    min_date = datetime.strptime(min_date_str, "%Y-%m-%d")
                    target_date = datetime.strptime("2021-01-04", "%Y-%m-%d")
                    if min_date <= target_date + timedelta(days=7):  # Allow 7-day buffer
                        return True
                except ValueError:
                    pass

        return False

    def get_min_trade_date(self, ticker: str, session=None) -> Optional[str]:
        """Get the earliest trade_time for a stock
        
        Args:
            ticker: Stock ticker (6-digit)
            session: Optional SQLAlchemy session (for testing)
            
        Returns:
            Earliest trade_time as string (YYYY-MM-DD) or None if no data exists
        """
        if session:
            # Use SQLAlchemy session for testing
            from sqlalchemy import select, func
            from src.models.kline import Kline
            stmt = select(func.min(Kline.trade_time)).where(
                Kline.symbol_type == SymbolType.STOCK,
                Kline.symbol_code == ticker,
                Kline.timeframe == KlineTimeframe.DAY
            )
            result = session.execute(stmt).scalar()
            return result
        else:
            # Use raw sqlite3 for production
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            query = """
            SELECT MIN(trade_time) 
            FROM klines 
            WHERE symbol_type = ? 
              AND symbol_code = ? 
              AND timeframe = ?
            """
            
            cursor.execute(query, (SymbolType.STOCK.value, ticker, KlineTimeframe.DAY.value))
            result = cursor.fetchone()
            conn.close()

            return result[0] if result and result[0] else None

    def backfill_stock(
        self,
        ticker: str,
        name: str,
        list_date: Optional[str],
        session=None
    ) -> tuple[bool, int]:
        """
        Backfill daily kline data for a single stock

        Args:
            ticker: Stock ticker (6-digit)
            name: Stock name
            list_date: Stock's list_date from stock_basic (YYYYMMDD)
            session: Optional SQLAlchemy session (for testing)

        Returns:
            Tuple of (success: bool, rows_inserted: int)
        """
        # Check existing data
        max_existing_date = self.get_existing_data_range(ticker, session)
        
        # Determine if we should skip
        if self.should_skip_stock(ticker, max_existing_date):
            logger.info(f"  {ticker} ({name}): Already has complete 5-year data, skipping")
            return (True, 0)  # Count as success, 0 rows

        # Determine start date
        start_date = self.determine_start_date(ticker, list_date)
        
        # End date is today
        end_date = datetime.now().strftime("%Y%m%d")

        # If we have existing data, start from the day after max_existing_date
        if max_existing_date:
            try:
                existing_dt = datetime.strptime(max_existing_date, "%Y-%m-%d")
                # Check if existing data is older than our target start
                target_dt = datetime.strptime(TARGET_START_DATE, "%Y%m%d")
                if existing_dt < target_dt:
                    # We have old data but need to fill the 2021+ gap
                    start_date = TARGET_START_DATE
                else:
                    # We have recent data, start from next day
                    next_day = existing_dt + timedelta(days=1)
                    start_date = next_day.strftime("%Y%m%d")
            except ValueError:
                pass

        # Log what we're about to do
        logger.debug(
            f"  {ticker} ({name}): Fetching {start_date} to {end_date} "
            f"(existing: {max_existing_date or 'none'}, list_date: {list_date or 'N/A'})"
        )

        if self.dry_run:
            logger.info(f"  [DRY RUN] Would fetch daily data for {ticker} from {start_date} to {end_date}")
            return (True, 0)

        # Fetch data from TuShare
        try:
            # Convert ticker to ts_code format
            ts_code = self.tushare_client.normalize_ts_code(ticker)
            
            df = self.tushare_client.fetch_daily(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date
            )

            if df is None or df.empty:
                logger.warning(
                    f"  {ticker} ({name}): Empty response from TuShare "
                    f"(may be delisted/suspended)"
                )
                return (False, 0)

            # Map TuShare fields to klines table format
            klines = []
            for _, row in df.iterrows():
                klines.append({
                    "datetime": row["trade_date"],  # YYYYMMDD format
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["vol"]),  # TuShare: vol -> klines: volume
                    "amount": float(row["amount"]),
                })

            if not klines:
                logger.warning(f"  {ticker} ({name}): No kline data to insert")
                return (False, 0)

            # Save to database using KlineService
            if not session:
                from src.database import SessionLocal
                session = SessionLocal()
                should_close_session = True
            else:
                should_close_session = False
            
            try:
                kline_service = KlineService.create_with_session(session)
                
                rows_inserted = kline_service.save_klines(
                    symbol_type=SymbolType.STOCK,
                    symbol_code=ticker,
                    symbol_name=name,
                    timeframe=KlineTimeframe.DAY,
                    klines=klines,
                    calculate_indicators=False  # Skip MACD calculation for speed
                )
                
                session.commit()
                logger.info(
                    f"  {ticker} ({name}): Inserted {rows_inserted} rows "
                    f"({len(klines)} fetched)"
                )
                return (True, rows_inserted)

            except Exception as e:
                session.rollback()
                logger.error(f"  {ticker} ({name}): Database error: {e}")
                return (False, 0)
            finally:
                if should_close_session:
                    session.close()

        except Exception as e:
            logger.error(f"  {ticker} ({name}): Failed to fetch data: {e}")
            return (False, 0)

    def log_progress(self):
        """Log current progress"""
        if self.start_time is None:
            return

        elapsed = time.time() - self.start_time
        rate = self.processed_count / elapsed if elapsed > 0 else 0
        remaining = (self.total_stocks - self.processed_count) / rate if rate > 0 else 0

        logger.info(
            f"\n{'='*60}\n"
            f"Progress: {self.processed_count}/{self.total_stocks} "
            f"({self.processed_count/self.total_stocks*100:.1f}%)\n"
            f"  Success: {self.success_count} | "
            f"Skipped: {self.skip_count} | "
            f"Failed: {self.fail_count}\n"
            f"  Total rows inserted: {self.total_rows_inserted}\n"
            f"  Rate: {rate:.2f} stocks/sec | "
            f"ETA: {remaining/60:.1f} min\n"
            f"{'='*60}"
        )

    def create_update_log(self, status: DataUpdateStatus, records: int, error: Optional[str] = None):
        """Create a DataUpdateLog entry"""
        if self.dry_run:
            return

        from src.database import SessionLocal
        
        session = SessionLocal()
        try:
            now = datetime.now(timezone.utc)
            
            log_entry = DataUpdateLog(
                update_type="stock_daily_backfill",
                symbol_type=SymbolType.STOCK.value,
                timeframe=KlineTimeframe.DAY.value,
                status=status,
                records_updated=records,
                error_message=error,
                started_at=datetime.fromtimestamp(self.start_time, tz=timezone.utc) if self.start_time else now,
                completed_at=now
            )
            
            session.add(log_entry)
            session.commit()
        except Exception as e:
            logger.error(f"Failed to create DataUpdateLog: {e}")
            session.rollback()
        finally:
            session.close()

    def run(self):
        """Run the backfill process"""
        logger.info("\n" + "="*60)
        logger.info("Stock Daily Kline Backfill")
        logger.info("="*60)
        
        if self.dry_run:
            logger.info("*** DRY RUN MODE - No data will be written ***")
        
        if self.limit:
            logger.info(f"*** LIMIT MODE - Only processing first {self.limit} stocks ***")

        # Get watchlist stocks
        logger.info("\nFetching watchlist stocks...")
        stocks = self.get_watchlist_stocks()
        self.total_stocks = len(stocks)
        
        if self.limit:
            stocks = stocks[:self.limit]
            self.total_stocks = len(stocks)

        logger.info(f"Found {self.total_stocks} stocks to process\n")

        if self.total_stocks == 0:
            logger.error("No stocks found in watchlist!")
            return

        # Start timing
        self.start_time = time.time()

        # Process each stock
        for i, (ticker, name, list_date) in enumerate(stocks):
            try:
                success, rows_inserted = self.backfill_stock(ticker, name, list_date)
                
                self.processed_count += 1
                
                if success:
                    if rows_inserted > 0:
                        self.success_count += 1
                        self.total_rows_inserted += rows_inserted
                    else:
                        self.skip_count += 1
                else:
                    self.fail_count += 1

                # Log progress every PROGRESS_LOG_INTERVAL stocks
                if (i + 1) % PROGRESS_LOG_INTERVAL == 0:
                    self.log_progress()

            except Exception as e:
                logger.error(f"  {ticker} ({name}): Unexpected error: {e}")
                self.processed_count += 1
                self.fail_count += 1
                continue

        # Final progress log
        logger.info("\n" + "="*60)
        logger.info("BACKFILL COMPLETE")
        logger.info("="*60)
        self.log_progress()

        # Create DataUpdateLog entry
        if self.fail_count > 0:
            status = DataUpdateStatus.FAILED
            error = f"{self.fail_count} stocks failed"
        else:
            status = DataUpdateStatus.COMPLETED
            error = None

        self.create_update_log(status, self.total_rows_inserted, error)

        logger.info(f"\nDataUpdateLog entry created: {status.value}")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Backfill 5 years of daily kline data for all stocks"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without actually backfilling"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Only process first N stocks (for testing)"
    )

    args = parser.parse_args()

    backfiller = StockDailyBackfiller(dry_run=args.dry_run, limit=args.limit)
    backfiller.run()


if __name__ == "__main__":
    main()
