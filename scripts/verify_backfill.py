#!/usr/bin/env python3
"""
Verify backfilled data integrity and ensure live scheduler works with expanded universe.

This script:
1. Checks stock kline count per symbol, flags any pre-2021 stock with < 1,000 rows
2. Checks index kline count, flags any index with < 1,100 rows
3. Cross-references klines against trade_calendar to find gaps
4. Validates OHLCV: no NULLs, high >= low
5. Reports summary to console and DataUpdateLog

Usage:
    python scripts/verify_backfill.py [--skip-gap-check] [--verbose]

Options:
    --skip-gap-check: Skip gap detection (saves time)
    --verbose: Print detailed findings
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3

from src.config import get_settings
from src.models import DataUpdateStatus
from src.utils.logging import get_logger

logger = get_logger(__name__)


class BackfillVerifier:
    """Backfill data integrity verifier"""

    def __init__(self, skip_gap_check: bool = False, verbose: bool = False):
        """
        Initialize verifier

        Args:
            skip_gap_check: If True, skip gap detection
            verbose: If True, print detailed findings
        """
        self.skip_gap_check = skip_gap_check
        self.verbose = verbose
        self.settings = get_settings()
        self.db_path = self.settings.database_url.replace("sqlite:///", "")
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()

        # Issue tracking
        self.issues = []
        self.warnings = []

    def log_issue(self, message: str, severity: str = "ERROR"):
        """Log an issue"""
        if severity == "ERROR":
            self.issues.append(message)
            logger.error(f"❌ {message}")
        else:
            self.warnings.append(message)
            logger.warning(f"⚠️  {message}")

    def check_stock_kline_counts(self) -> dict:
        """
        Check stock kline count per symbol, flag any pre-2021 stock with < 1,000 rows

        Returns:
            Dict with summary stats
        """
        logger.info("=" * 60)
        logger.info("Checking stock kline counts...")
        logger.info("=" * 60)

        # Get stocks that were listed before 2021
        query = """
        SELECT 
            sb.ts_code,
            sb.name,
            sb.list_date,
            COUNT(k.id) as kline_count,
            MIN(k.trade_time) as earliest_date,
            MAX(k.trade_time) as latest_date
        FROM stock_basic sb
        LEFT JOIN klines k ON 
            k.symbol_code = sb.ts_code 
            AND k.symbol_type = 'STOCK' 
            AND k.timeframe = 'DAY'
        WHERE sb.list_date < '20210101'
        GROUP BY sb.ts_code, sb.name, sb.list_date
        HAVING kline_count < 1000
        ORDER BY kline_count ASC
        """

        self.cursor.execute(query)
        results = self.cursor.fetchall()

        if results:
            self.log_issue(
                f"Found {len(results)} pre-2021 stocks with < 1,000 daily kline rows",
                severity="ERROR"
            )
            if self.verbose:
                for row in results[:20]:  # Show first 20
                    ts_code, name, list_date, count, earliest, latest = row
                    logger.info(
                        f"  {ts_code} ({name}): {count} rows, "
                        f"listed {list_date}, range {earliest} to {latest}"
                    )
                if len(results) > 20:
                    logger.info(f"  ... and {len(results) - 20} more")
        else:
            logger.info("✅ All pre-2021 stocks have >= 1,000 daily kline rows")

        # Get total stats for all stocks
        self.cursor.execute("""
            SELECT 
                COUNT(DISTINCT k.symbol_code) as stock_count,
                AVG(cnt) as avg_rows,
                MIN(cnt) as min_rows,
                MAX(cnt) as max_rows
            FROM (
                SELECT symbol_code, COUNT(*) as cnt
                FROM klines
                WHERE symbol_type = 'STOCK' AND timeframe = 'DAY'
                GROUP BY symbol_code
            ) as subq
        """)
        total_stats = self.cursor.fetchone()
        stock_count, avg_rows, min_rows, max_rows = total_stats

        logger.info(f"Stock daily kline stats:")
        logger.info(f"  Total stocks: {stock_count}")
        logger.info(f"  Average rows per stock: {avg_rows:.1f}")
        logger.info(f"  Min rows: {min_rows}")
        logger.info(f"  Max rows: {max_rows}")

        return {
            "pre_2021_with_insufficient_data": len(results),
            "total_stocks": stock_count,
            "avg_rows": avg_rows,
            "min_rows": min_rows,
            "max_rows": max_rows
        }

    def check_index_kline_counts(self) -> dict:
        """
        Check index kline count, flag any index with < 1,100 rows

        Returns:
            Dict with summary stats
        """
        logger.info("=" * 60)
        logger.info("Checking index kline counts...")
        logger.info("=" * 60)

        # Expected 8 indices
        expected_indices = [
            "000001.SH",  # 上证指数
            "399001.SZ",  # 深证成指
            "399006.SZ",  # 创业板指
            "000688.SH",  # 科创50
            "899050.BJ",  # 北证50
            "000300.SH",  # 沪深300
            "000905.SH",  # 中证500
            "000852.SH",  # 中证1000
        ]

        query = """
        SELECT 
            symbol_code,
            symbol_name,
            COUNT(*) as kline_count,
            MIN(trade_time) as earliest_date,
            MAX(trade_time) as latest_date
        FROM klines
        WHERE symbol_type = 'INDEX' AND timeframe = 'DAY'
        GROUP BY symbol_code, symbol_name
        ORDER BY symbol_code
        """

        self.cursor.execute(query)
        results = self.cursor.fetchall()

        # Check each expected index
        found_indices = {row[0] for row in results}
        for expected in expected_indices:
            if expected not in found_indices:
                self.log_issue(
                    f"Missing index: {expected}",
                    severity="ERROR"
                )

        # Check counts
        issues_found = []
        for row in results:
            symbol_code, symbol_name, count, earliest, latest = row
            logger.info(
                f"  {symbol_code} ({symbol_name}): {count} rows, "
                f"range {earliest} to {latest}"
            )

            if count < 1100:
                issues_found.append(symbol_code)
                self.log_issue(
                    f"Index {symbol_code} has only {count} rows (expected >= 1,100)",
                    severity="ERROR"
                )

        if not issues_found:
            logger.info("✅ All indices have >= 1,100 daily kline rows")

        return {
            "total_indices": len(results),
            "expected_indices": len(expected_indices),
            "indices_with_insufficient_data": len(issues_found),
        }

    def check_ohlcv_validity(self) -> dict:
        """
        Validate OHLCV: no NULLs, high >= low

        Returns:
            Dict with summary stats
        """
        logger.info("=" * 60)
        logger.info("Checking OHLCV validity...")
        logger.info("=" * 60)

        # Check for NULL values in OHLCV fields
        null_check_query = """
        SELECT COUNT(*) 
        FROM klines
        WHERE (open IS NULL OR high IS NULL OR low IS NULL OR close IS NULL)
        AND timeframe = 'DAY'
        """

        self.cursor.execute(null_check_query)
        null_count = self.cursor.fetchone()[0]

        if null_count > 0:
            self.log_issue(
                f"Found {null_count} daily kline rows with NULL OHLCV fields",
                severity="ERROR"
            )
        else:
            logger.info("✅ No NULL values in OHLCV fields for daily klines")

        # Check for high < low violations
        high_low_query = """
        SELECT 
            symbol_type,
            symbol_code,
            symbol_name,
            trade_time,
            open,
            high,
            low,
            close
        FROM klines
        WHERE high < low AND timeframe = 'DAY'
        LIMIT 100
        """

        self.cursor.execute(high_low_query)
        violations = self.cursor.fetchall()

        if violations:
            self.log_issue(
                f"Found {len(violations)} daily kline rows with high < low",
                severity="ERROR"
            )
            if self.verbose:
                for row in violations[:10]:
                    logger.info(
                        f"  {row[0]} {row[1]} ({row[2]}) on {row[3]}: "
                        f"OHLC={row[4]}/{row[5]}/{row[6]}/{row[7]}"
                    )
        else:
            logger.info("✅ No high < low violations found")

        return {
            "null_ohlcv_count": null_count,
            "high_low_violations": len(violations)
        }

    def check_gaps(self, sample_size: int = 50) -> dict:
        """
        Cross-reference klines against trade_calendar to find gaps

        Args:
            sample_size: Number of stocks to sample for gap detection

        Returns:
            Dict with summary stats
        """
        if self.skip_gap_check:
            logger.info("Skipping gap check (--skip-gap-check flag)")
            return {"skipped": True}

        logger.info("=" * 60)
        logger.info(f"Checking gaps (sampling {sample_size} stocks)...")
        logger.info("=" * 60)

        # Sample stocks for gap detection
        self.cursor.execute("""
            SELECT DISTINCT symbol_code
            FROM klines
            WHERE symbol_type = 'STOCK' AND timeframe = 'DAY'
            ORDER BY RANDOM()
            LIMIT ?
        """, (sample_size,))
        sampled_stocks = [row[0] for row in self.cursor.fetchall()]

        stocks_with_large_gaps = []

        for symbol_code in sampled_stocks:
            # Find missing trading days
            gap_query = """
            SELECT COUNT(*) as gap_count
            FROM trade_calendar tc
            WHERE tc.is_trading_day = 1
            AND tc.date >= '2021-01-04'
            AND tc.date <= date('now')
            AND tc.date NOT IN (
                SELECT DISTINCT substr(trade_time, 1, 10)
                FROM klines
                WHERE symbol_code = ? 
                AND symbol_type = 'STOCK' 
                AND timeframe = 'DAY'
            )
            """

            self.cursor.execute(gap_query, (symbol_code,))
            gap_count = self.cursor.fetchone()[0]

            if gap_count > 30:  # Allow up to 30 missing days (suspensions)
                stocks_with_large_gaps.append((symbol_code, gap_count))
                if self.verbose:
                    logger.info(f"  {symbol_code}: {gap_count} missing trading days")

        if stocks_with_large_gaps:
            self.log_issue(
                f"Found {len(stocks_with_large_gaps)} stocks with > 30 missing trading days (out of {sample_size} sampled)",
                severity="WARNING"
            )
        else:
            logger.info(f"✅ All sampled stocks have <= 30 missing trading days")

        # Check indices (all 8)
        index_gaps = []
        for index_code in ["000001.SH", "399001.SZ", "399006.SZ", "000688.SH", 
                          "899050.BJ", "000300.SH", "000905.SH", "000852.SH"]:
            gap_query = """
            SELECT COUNT(*) as gap_count
            FROM trade_calendar tc
            WHERE tc.is_trading_day = 1
            AND tc.date >= '2021-01-04'
            AND tc.date <= date('now')
            AND tc.date NOT IN (
                SELECT DISTINCT substr(trade_time, 1, 10)
                FROM klines
                WHERE symbol_code = ? 
                AND symbol_type = 'INDEX' 
                AND timeframe = 'DAY'
            )
            """

            self.cursor.execute(gap_query, (index_code,))
            gap_count = self.cursor.fetchone()[0]

            if gap_count > 2:
                index_gaps.append((index_code, gap_count))
                if self.verbose:
                    logger.info(f"  Index {index_code}: {gap_count} missing trading days")

        if index_gaps:
            self.log_issue(
                f"Found {len(index_gaps)} indices with > 2 missing trading days",
                severity="WARNING"
            )
        else:
            logger.info("✅ All indices have <= 2 missing trading days")

        return {
            "sampled_stocks": sample_size,
            "stocks_with_large_gaps": len(stocks_with_large_gaps),
            "indices_with_gaps": len(index_gaps)
        }

    def log_to_database(self, stats: dict, success: bool):
        """
        Log verification results to DataUpdateLog

        Args:
            stats: Dictionary with all stats
            success: Whether verification passed
        """
        logger.info("=" * 60)
        logger.info("Logging verification results to DataUpdateLog...")
        logger.info("=" * 60)

        status = "COMPLETED" if success else "FAILED"
        error_message = None if success else "\n".join(self.issues[:10])  # First 10 issues

        insert_query = """
        INSERT INTO data_update_log (
            update_type, symbol_type, timeframe, status, 
            records_updated, error_message, 
            started_at, completed_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        now = datetime.now(timezone.utc)
        self.cursor.execute(insert_query, (
            "backfill_verification",
            "ALL",
            "DAY",
            status,
            stats.get("total_stocks", 0),
            error_message,
            now,
            now,
            now
        ))
        self.conn.commit()

        logger.info("✅ Verification results logged to database")

    def run(self) -> bool:
        """
        Run all verification checks

        Returns:
            True if all checks passed, False otherwise
        """
        logger.info("=" * 60)
        logger.info("BACKFILL VERIFICATION STARTED")
        logger.info("=" * 60)

        all_stats = {}

        # 1. Check stock kline counts
        all_stats["stock_counts"] = self.check_stock_kline_counts()

        # 2. Check index kline counts
        all_stats["index_counts"] = self.check_index_kline_counts()

        # 3. Check OHLCV validity
        all_stats["ohlcv_validity"] = self.check_ohlcv_validity()

        # 4. Check gaps
        all_stats["gaps"] = self.check_gaps()

        # Summary
        logger.info("=" * 60)
        logger.info("VERIFICATION SUMMARY")
        logger.info("=" * 60)

        success = len(self.issues) == 0

        if success:
            logger.info("✅ ALL CHECKS PASSED")
        else:
            logger.error(f"❌ VERIFICATION FAILED: {len(self.issues)} issues found")
            logger.error("Issues:")
            for issue in self.issues:
                logger.error(f"  - {issue}")

        if self.warnings:
            logger.warning(f"⚠️  {len(self.warnings)} warnings:")
            for warning in self.warnings:
                logger.warning(f"  - {warning}")

        # Log to database
        self.log_to_database(all_stats, success)

        self.conn.close()
        return success


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Verify backfilled data integrity"
    )
    parser.add_argument(
        "--skip-gap-check",
        action="store_true",
        help="Skip gap detection (saves time)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed findings"
    )

    args = parser.parse_args()

    verifier = BackfillVerifier(
        skip_gap_check=args.skip_gap_check,
        verbose=args.verbose
    )
    success = verifier.run()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
