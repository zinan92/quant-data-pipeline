#!/usr/bin/env python3
"""
Expand Stock Universe: Add CSI 300/500/1000 constituents

This script:
1. Fetches CSI 300, CSI 500, and CSI 1000 constituent stocks from TuShare
2. Merges with existing watchlist (preserves all existing entries)
3. Updates watchlist table
4. Updates symbol_metadata table for new stocks
5. Updates stock_sectors table for new stocks
6. Fetches stock_basic info for new stocks if not already present

The script is idempotent and can be run multiple times safely.

Usage:
    python scripts/expand_stock_universe.py
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
from datetime import datetime
from typing import Set, List, Dict
import logging

from src.config import get_settings
from src.services.tushare_client import TushareClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)

# Index configuration
INDICES = [
    ('000300.SH', 'CSI 300'),
    ('000905.SH', 'CSI 500'),
    ('000852.SH', 'CSI 1000'),
]


class StockUniverseExpander:
    """Stock universe expansion manager"""

    def __init__(self):
        self.settings = get_settings()
        self.db_path = self.settings.database_url.replace("sqlite:///", "")
        self.tushare_client = TushareClient(
            token=self.settings.tushare_token,
            points=self.settings.tushare_points
        )

    def get_existing_watchlist(self) -> Set[str]:
        """Get all existing tickers from watchlist"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT DISTINCT ticker FROM watchlist")
        existing = {row[0] for row in cursor.fetchall()}

        conn.close()
        logger.info(f"Found {len(existing)} existing watchlist entries")
        return existing

    def fetch_index_constituents(self, index_code: str, index_name: str) -> Set[str]:
        """
        Fetch constituent stocks for a given index

        Args:
            index_code: Index code (e.g., '000300.SH')
            index_name: Index name for logging

        Returns:
            Set of stock tickers (6-digit codes without exchange suffix)
        """
        logger.info(f"Fetching constituents for {index_name} ({index_code})...")

        # Fetch recent index weights (latest composition)
        df = self.tushare_client.pro.index_weight(
            index_code=index_code,
            start_date='20260101',
            end_date='20260325'
        )

        if df.empty:
            logger.warning(f"No data returned for {index_name}")
            return set()

        # Extract unique stock codes and convert to 6-digit format
        constituents = set()
        for ts_code in df['con_code'].unique():
            ticker = self.tushare_client.denormalize_ts_code(ts_code)
            constituents.add(ticker)

        logger.info(f"  {index_name}: {len(constituents)} unique stocks")
        return constituents

    def fetch_all_constituents(self) -> Set[str]:
        """Fetch constituents from all configured indices"""
        all_constituents = set()

        for index_code, index_name in INDICES:
            constituents = self.fetch_index_constituents(index_code, index_name)
            all_constituents.update(constituents)

        logger.info(f"\nTotal unique constituents across all indices: {len(all_constituents)}")
        return all_constituents

    def merge_with_watchlist(
        self,
        existing: Set[str],
        constituents: Set[str]
    ) -> Set[str]:
        """
        Merge new constituents with existing watchlist

        Args:
            existing: Existing watchlist tickers
            constituents: New constituent tickers

        Returns:
            Set of new tickers to add
        """
        new_tickers = constituents - existing
        preserved_count = len(existing)
        new_count = len(new_tickers)
        total_count = preserved_count + new_count

        logger.info(f"\nMerge summary:")
        logger.info(f"  Existing watchlist entries: {preserved_count}")
        logger.info(f"  New stocks to add: {new_count}")
        logger.info(f"  Total after merge: {total_count}")

        return new_tickers

    def insert_into_watchlist(self, new_tickers: Set[str]) -> int:
        """
        Insert new tickers into watchlist table

        Args:
            new_tickers: Set of new tickers to add

        Returns:
            Number of successfully inserted tickers
        """
        if not new_tickers:
            logger.info("No new tickers to insert into watchlist")
            return 0

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        now = datetime.now().isoformat()

        inserted = 0
        failed = []

        for ticker in sorted(new_tickers):
            try:
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO watchlist (ticker, added_at, is_focus, category)
                    VALUES (?, ?, 0, '指数成份股')
                    """,
                    (ticker, now)
                )
                if cursor.rowcount > 0:
                    inserted += 1
            except Exception as e:
                failed.append((ticker, str(e)))
                logger.error(f"Failed to insert {ticker}: {e}")

        conn.commit()
        conn.close()

        logger.info(f"\nWatchlist update:")
        logger.info(f"  Successfully inserted: {inserted}")
        if failed:
            logger.warning(f"  Failed: {len(failed)}")
            for ticker, error in failed[:5]:  # Show first 5 failures
                logger.warning(f"    {ticker}: {error}")

        return inserted

    def fetch_and_update_stock_basic(self, tickers: Set[str]) -> int:
        """
        Fetch stock basic info and update stock_basic table

        Args:
            tickers: Set of tickers to fetch info for

        Returns:
            Number of successfully updated stocks
        """
        if not tickers:
            logger.info("No tickers to fetch stock_basic info for")
            return 0

        logger.info(f"\nFetching stock_basic info for {len(tickers)} stocks...")

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Check which tickers are already in stock_basic
        cursor.execute("SELECT symbol FROM stock_basic")
        existing_in_basic = {row[0] for row in cursor.fetchall()}
        tickers_to_fetch = tickers - existing_in_basic

        logger.info(f"  Already in stock_basic: {len(tickers & existing_in_basic)}")
        logger.info(f"  Need to fetch: {len(tickers_to_fetch)}")

        if not tickers_to_fetch:
            conn.close()
            return 0

        # Fetch all stock list and filter
        df_all = self.tushare_client.fetch_stock_list()

        inserted = 0
        for ticker in tickers_to_fetch:
            ts_code = self.tushare_client.normalize_ts_code(ticker)
            row = df_all[df_all['ts_code'] == ts_code]

            if row.empty:
                logger.warning(f"  No stock_basic data for {ticker}")
                continue

            try:
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO stock_basic (ts_code, symbol, name, area, industry, market, list_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ts_code,
                        ticker,
                        row.iloc[0]['name'],
                        row.iloc[0].get('area', ''),
                        row.iloc[0].get('industry', ''),
                        row.iloc[0].get('market', ''),
                        row.iloc[0].get('list_date', '')
                    )
                )
                if cursor.rowcount > 0:
                    inserted += 1
            except Exception as e:
                logger.error(f"  Failed to insert stock_basic for {ticker}: {e}")

        conn.commit()
        conn.close()

        logger.info(f"  Successfully inserted into stock_basic: {inserted}")
        return inserted

    def update_symbol_metadata(self, tickers: Set[str]) -> int:
        """
        Update symbol_metadata table for new stocks

        Args:
            tickers: Set of tickers to update

        Returns:
            Number of successfully updated stocks
        """
        if not tickers:
            logger.info("No tickers to update in symbol_metadata")
            return 0

        logger.info(f"\nUpdating symbol_metadata for {len(tickers)} stocks...")

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Check which tickers are already in symbol_metadata
        cursor.execute("SELECT ticker FROM symbol_metadata")
        existing_in_metadata = {row[0] for row in cursor.fetchall()}
        tickers_to_add = tickers - existing_in_metadata

        logger.info(f"  Already in symbol_metadata: {len(tickers & existing_in_metadata)}")
        logger.info(f"  Need to add: {len(tickers_to_add)}")

        if not tickers_to_add:
            conn.close()
            return 0

        # Fetch stock basic info for names and list dates
        df_all = self.tushare_client.fetch_stock_list()

        inserted = 0
        now = datetime.now().isoformat()

        for ticker in tickers_to_add:
            ts_code = self.tushare_client.normalize_ts_code(ticker)
            row = df_all[df_all['ts_code'] == ts_code]

            if row.empty:
                logger.warning(f"  No data for {ticker}")
                continue

            try:
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO symbol_metadata (ticker, name, list_date, last_sync)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        ticker,
                        row.iloc[0]['name'],
                        row.iloc[0].get('list_date', ''),
                        now
                    )
                )
                if cursor.rowcount > 0:
                    inserted += 1
            except Exception as e:
                logger.error(f"  Failed to insert symbol_metadata for {ticker}: {e}")

        conn.commit()
        conn.close()

        logger.info(f"  Successfully inserted into symbol_metadata: {inserted}")
        return inserted

    def update_stock_sectors(self, tickers: Set[str]) -> int:
        """
        Update stock_sectors table for new stocks

        Args:
            tickers: Set of tickers to update

        Returns:
            Number of successfully updated stocks
        """
        if not tickers:
            logger.info("No tickers to update in stock_sectors")
            return 0

        logger.info(f"\nUpdating stock_sectors for {len(tickers)} stocks...")

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Check which tickers are already in stock_sectors
        cursor.execute("SELECT DISTINCT ticker FROM stock_sectors")
        existing_in_sectors = {row[0] for row in cursor.fetchall()}
        tickers_to_add = tickers - existing_in_sectors

        logger.info(f"  Already in stock_sectors: {len(tickers & existing_in_sectors)}")
        logger.info(f"  Need to add: {len(tickers_to_add)}")

        if not tickers_to_add:
            conn.close()
            return 0

        inserted = 0
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        for ticker in tickers_to_add:
            try:
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO stock_sectors (ticker, sector, created_at, updated_at)
                    VALUES (?, '指数成份股', ?, ?)
                    """,
                    (ticker, now, now)
                )
                if cursor.rowcount > 0:
                    inserted += 1
            except Exception as e:
                logger.error(f"  Failed to insert stock_sectors for {ticker}: {e}")

        conn.commit()
        conn.close()

        logger.info(f"  Successfully inserted into stock_sectors: {inserted}")
        return inserted

    def verify_expansion(self) -> Dict[str, int]:
        """
        Verify the expansion results

        Returns:
            Dictionary with counts for each table
        """
        logger.info("\n" + "=" * 60)
        logger.info("Verification")
        logger.info("=" * 60)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        results = {}

        # Check watchlist
        cursor.execute("SELECT COUNT(DISTINCT ticker) FROM watchlist")
        results['watchlist'] = cursor.fetchone()[0]

        # Check symbol_metadata
        cursor.execute("SELECT COUNT(DISTINCT ticker) FROM symbol_metadata")
        results['symbol_metadata'] = cursor.fetchone()[0]

        # Check stock_sectors
        cursor.execute("SELECT COUNT(DISTINCT ticker) FROM stock_sectors")
        results['stock_sectors'] = cursor.fetchone()[0]

        # Check stock_basic
        cursor.execute("SELECT COUNT(DISTINCT symbol) FROM stock_basic")
        results['stock_basic'] = cursor.fetchone()[0]

        conn.close()

        logger.info(f"  watchlist: {results['watchlist']} distinct tickers")
        logger.info(f"  symbol_metadata: {results['symbol_metadata']} distinct tickers")
        logger.info(f"  stock_sectors: {results['stock_sectors']} distinct tickers")
        logger.info(f"  stock_basic: {results['stock_basic']} distinct symbols")

        # Verify success criteria
        success = True
        if results['watchlist'] < 800:
            logger.error(f"  ❌ watchlist has {results['watchlist']} tickers, expected >= 800")
            success = False
        else:
            logger.info(f"  ✅ watchlist has >= 800 tickers")

        if results['stock_sectors'] < 800:
            logger.error(f"  ❌ stock_sectors has {results['stock_sectors']} tickers, expected >= 800")
            success = False
        else:
            logger.info(f"  ✅ stock_sectors has >= 800 tickers")

        logger.info("=" * 60)

        if success:
            logger.info("✅ Stock universe expansion completed successfully!")
        else:
            logger.error("❌ Stock universe expansion did not meet success criteria")

        return results

    def run(self):
        """Main execution flow"""
        logger.info("=" * 60)
        logger.info("Stock Universe Expansion - CSI 300/500/1000")
        logger.info("=" * 60)

        try:
            # Step 1: Get existing watchlist
            existing = self.get_existing_watchlist()

            # Step 2: Fetch all constituents
            all_constituents = self.fetch_all_constituents()

            # Step 3: Merge with watchlist
            new_tickers = self.merge_with_watchlist(existing, all_constituents)

            # Step 4: Update tables
            self.insert_into_watchlist(new_tickers)

            # Step 5: Update stock_basic (for new tickers only)
            self.fetch_and_update_stock_basic(new_tickers)

            # Step 6: Update symbol_metadata (for new tickers only)
            self.update_symbol_metadata(new_tickers)

            # Step 7: Update stock_sectors (for new tickers only)
            self.update_stock_sectors(new_tickers)

            # Step 8: Verify
            results = self.verify_expansion()

            return results

        except Exception as e:
            logger.error(f"Expansion failed: {e}")
            raise


def main():
    """Entry point"""
    expander = StockUniverseExpander()
    expander.run()


if __name__ == '__main__':
    main()
