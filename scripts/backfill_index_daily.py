#!/usr/bin/env python3
"""
Backfill 5 years of daily kline data for all 8 indices.

This script:
1. Iterates over all 8 indices from INDEX_LIST (000001.SH, 399001.SZ, 399006.SZ, 000688.SH, 899050.BJ, 000300.SH, 000905.SH, 000852.SH)
2. Uses TuShare pro.index_daily(ts_code=code, start_date='20210101', end_date=<today>) — NOT Sina (Sina only returns ~60 bars)
3. Maps TuShare fields to klines table columns with symbol_type='INDEX', timeframe='DAY'
4. Uses UPSERT to avoid duplicates
5. Checks existing data and only fetches missing range (resume support)

Usage:
    python scripts/backfill_index_daily.py [--dry-run]

Options:
    --dry-run: Print what would be done without actually backfilling
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
from src.services.index_updater import INDEX_LIST
from src.services.kline_service import KlineService
from src.services.tushare_client import TushareClient
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Constants
TARGET_START_DATE = "20210101"  # 2021-01-01


class IndexDailyBackfiller:
    """Index daily kline data backfiller"""

    def __init__(self, dry_run: bool = False):
        """
        Initialize backfiller

        Args:
            dry_run: If True, only print what would be done
        """
        self.dry_run = dry_run
        self.settings = get_settings()
        self.db_path = self.settings.database_url.replace("sqlite:///", "")
        
        # Initialize TuShare client
        self.tushare_client = TushareClient(
            token=self.settings.tushare_token,
            points=self.settings.tushare_points
        )
        
        # Stats
        self.total_indices = len(INDEX_LIST)
        self.processed_count = 0
        self.success_count = 0
        self.skip_count = 0
        self.fail_count = 0
        self.total_rows_inserted = 0
        self.start_time = None

    def get_existing_data_range(self, ts_code: str, session=None) -> Optional[str]:
        """
        Get the latest trade_time for an index's daily klines

        Args:
            ts_code: Index code (e.g., '000001.SH')
            session: Optional SQLAlchemy session (for testing)

        Returns:
            Latest trade_time as string (YYYY-MM-DD) or None if no data exists
        """
        if session:
            # Use SQLAlchemy session for testing
            from sqlalchemy import select, func
            from src.models.kline import Kline
            stmt = select(func.max(Kline.trade_time)).where(
                Kline.symbol_type == SymbolType.INDEX,
                Kline.symbol_code == ts_code,
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
            
            cursor.execute(query, (SymbolType.INDEX.value, ts_code, KlineTimeframe.DAY.value))
            result = cursor.fetchone()
            conn.close()

            return result[0] if result and result[0] else None

    def get_min_trade_date(self, ts_code: str, session=None) -> Optional[str]:
        """Get the earliest trade_time for an index
        
        Args:
            ts_code: Index code (e.g., '000001.SH')
            session: Optional SQLAlchemy session (for testing)
            
        Returns:
            Earliest trade_time as string (YYYY-MM-DD) or None if no data exists
        """
        if session:
            # Use SQLAlchemy session for testing
            from sqlalchemy import select, func
            from src.models.kline import Kline
            stmt = select(func.min(Kline.trade_time)).where(
                Kline.symbol_type == SymbolType.INDEX,
                Kline.symbol_code == ts_code,
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
            
            cursor.execute(query, (SymbolType.INDEX.value, ts_code, KlineTimeframe.DAY.value))
            result = cursor.fetchone()
            conn.close()

            return result[0] if result and result[0] else None

    def should_skip_index(self, ts_code: str, max_existing_date: Optional[str]) -> bool:
        """
        Determine if an index should be skipped (already has recent and historical data)

        Args:
            ts_code: Index code
            max_existing_date: Latest trade_time in database (YYYY-MM-DD format)

        Returns:
            True if index should be skipped (has complete 5-year data)
        """
        if not max_existing_date:
            return False

        # Parse the max_existing_date
        try:
            max_date = datetime.strptime(max_existing_date, "%Y-%m-%d")
        except ValueError:
            return False

        # Check if data is recent (within last 7 days)
        cutoff_date = datetime.now() - timedelta(days=7)
        
        # If max_date is recent, check if it also has historical data back to 2021
        if max_date >= cutoff_date:
            min_date_str = self.get_min_trade_date(ts_code)
            if min_date_str:
                try:
                    min_date = datetime.strptime(min_date_str, "%Y-%m-%d")
                    target_date = datetime.strptime("2021-01-04", "%Y-%m-%d")
                    if min_date <= target_date + timedelta(days=7):  # Allow 7-day buffer
                        return True
                except ValueError:
                    pass

        return False

    def backfill_index(
        self,
        ts_code: str,
        name: str,
        session=None
    ) -> tuple[bool, int]:
        """
        Backfill daily kline data for a single index

        Args:
            ts_code: Index code (e.g., '000001.SH')
            name: Index name
            session: Optional SQLAlchemy session (for testing)

        Returns:
            Tuple of (success: bool, rows_inserted: int)
        """
        # Check existing data
        max_existing_date = self.get_existing_data_range(ts_code, session)
        
        # Determine if we should skip
        if self.should_skip_index(ts_code, max_existing_date):
            logger.info(f"  {ts_code} ({name}): Already has complete 5-year data, skipping")
            return (True, 0)  # Count as success, 0 rows

        # Start date is 2021-01-01
        start_date = TARGET_START_DATE
        
        # End date is today
        end_date = datetime.now().strftime("%Y%m%d")

        # If we have existing data but it doesn't go back to 2021, we need to backfill
        # We'll fetch the full range and let UPSERT handle duplicates
        if max_existing_date:
            min_date_str = self.get_min_trade_date(ts_code, session)
            if min_date_str:
                try:
                    min_date = datetime.strptime(min_date_str, "%Y-%m-%d")
                    target_date = datetime.strptime("2021-01-04", "%Y-%m-%d")
                    
                    # If we already have data back to 2021, just fill the gap at the end
                    if min_date <= target_date + timedelta(days=7):
                        # Start from day after max_existing_date
                        existing_dt = datetime.strptime(max_existing_date, "%Y-%m-%d")
                        next_day = existing_dt + timedelta(days=1)
                        start_date = next_day.strftime("%Y%m%d")
                        logger.debug(
                            f"  {ts_code} ({name}): Has historical data, filling gap from {start_date}"
                        )
                    else:
                        # Need to backfill to 2021
                        logger.debug(
                            f"  {ts_code} ({name}): Backfilling from 2021 (current min: {min_date_str})"
                        )
                except ValueError:
                    pass

        # Log what we're about to do
        logger.info(
            f"  {ts_code} ({name}): Fetching {start_date} to {end_date} "
            f"(existing: {max_existing_date or 'none'})"
        )

        if self.dry_run:
            logger.info(f"  [DRY RUN] Would fetch daily data for {ts_code} from {start_date} to {end_date}")
            return (True, 0)

        # Fetch data from TuShare using pro.index_daily()
        try:
            df = self.tushare_client.fetch_index_daily(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date
            )

            if df is None or df.empty:
                logger.warning(
                    f"  {ts_code} ({name}): Empty response from TuShare"
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
                logger.warning(f"  {ts_code} ({name}): No kline data to insert")
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
                    symbol_type=SymbolType.INDEX,
                    symbol_code=ts_code,
                    symbol_name=name,
                    timeframe=KlineTimeframe.DAY,
                    klines=klines,
                    calculate_indicators=False  # Skip MACD calculation for speed
                )
                
                session.commit()
                logger.info(
                    f"  {ts_code} ({name}): Inserted {rows_inserted} rows "
                    f"({len(klines)} fetched)"
                )
                return (True, rows_inserted)

            except Exception as e:
                session.rollback()
                logger.error(f"  {ts_code} ({name}): Database error: {e}")
                return (False, 0)
            finally:
                if should_close_session:
                    session.close()

        except Exception as e:
            logger.error(f"  {ts_code} ({name}): Failed to fetch data: {e}")
            return (False, 0)

    def create_update_log(self, status: DataUpdateStatus, records: int, error: Optional[str] = None):
        """Create a DataUpdateLog entry"""
        if self.dry_run:
            return

        from src.database import SessionLocal
        
        session = SessionLocal()
        try:
            now = datetime.now(timezone.utc)
            
            log_entry = DataUpdateLog(
                update_type="index_daily_backfill",
                symbol_type=SymbolType.INDEX.value,
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
        logger.info("Index Daily Kline Backfill")
        logger.info("="*60)
        
        if self.dry_run:
            logger.info("*** DRY RUN MODE - No data will be written ***")

        logger.info(f"\nProcessing {self.total_indices} indices from INDEX_LIST\n")

        # Start timing
        self.start_time = time.time()

        # Process each index
        for ts_code, sina_code, name in INDEX_LIST:
            try:
                success, rows_inserted = self.backfill_index(ts_code, name)
                
                self.processed_count += 1
                
                if success:
                    if rows_inserted > 0:
                        self.success_count += 1
                        self.total_rows_inserted += rows_inserted
                    else:
                        self.skip_count += 1
                else:
                    self.fail_count += 1

            except Exception as e:
                logger.error(f"  {ts_code} ({name}): Unexpected error: {e}")
                self.processed_count += 1
                self.fail_count += 1
                continue

        # Final summary
        elapsed = time.time() - self.start_time
        logger.info("\n" + "="*60)
        logger.info("BACKFILL COMPLETE")
        logger.info("="*60)
        logger.info(
            f"\nProcessed: {self.processed_count}/{self.total_indices}\n"
            f"  Success: {self.success_count} | "
            f"Skipped: {self.skip_count} | "
            f"Failed: {self.fail_count}\n"
            f"  Total rows inserted: {self.total_rows_inserted}\n"
            f"  Elapsed time: {elapsed:.1f} seconds"
        )

        # Create DataUpdateLog entry
        if self.fail_count > 0:
            status = DataUpdateStatus.FAILED
            error = f"{self.fail_count} indices failed"
        else:
            status = DataUpdateStatus.COMPLETED
            error = None

        self.create_update_log(status, self.total_rows_inserted, error)

        logger.info(f"\nDataUpdateLog entry created: {status.value}")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Backfill 5 years of daily kline data for all 8 indices"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without actually backfilling"
    )

    args = parser.parse_args()

    backfiller = IndexDailyBackfiller(dry_run=args.dry_run)
    backfiller.run()


if __name__ == "__main__":
    main()
