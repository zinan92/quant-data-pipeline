"""
Tests for CalendarUpdater cleanup retention logic and trade calendar coverage.

Validates:
- Daily klines survive 400-day-old records (within 1825-day retention)
- 30-minute klines survive 100-day-old records (within 365-day retention)
- Trade calendar coverage spans 2021-2026 with reasonable trading day count
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from sqlalchemy.orm import Session

from src.models import Kline, KlineTimeframe, SymbolType, TradeCalendar
from src.repositories.kline_repository import KlineRepository
from src.services.calendar_updater import CalendarUpdater


def _create_test_kline(
    session: Session,
    days_ago: int,
    timeframe: KlineTimeframe,
    symbol_type: SymbolType = SymbolType.STOCK,
    symbol_code: str = "000001.SZ",
) -> Kline:
    """Helper to create a kline dated N days ago."""
    trade_time = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
    kline = Kline(
        symbol_type=symbol_type,
        symbol_code=symbol_code,
        timeframe=timeframe,
        trade_time=trade_time,
        open=10.0,
        high=11.0,
        low=9.0,
        close=10.5,
        volume=1000000,
    )
    session.add(kline)
    session.commit()
    return kline


class TestCleanupRetentionLogic:
    """Test cleanup_old_klines retention windows."""

    def test_daily_kline_survives_400_days_old(self, db_session: Session):
        """Daily kline 400 days old should survive cleanup (within 1825-day window)."""
        kline_repo = KlineRepository(db_session)
        updater = CalendarUpdater(kline_repo)

        # Create a daily kline dated 400 days ago
        kline = _create_test_kline(db_session, days_ago=400, timeframe=KlineTimeframe.DAY)

        # Run cleanup with default retention (1825 days for daily, 365 for 30-min)
        deleted_count = updater.cleanup_old_klines()

        # Verify the 400-day-old daily kline was NOT deleted
        surviving = (
            db_session.query(Kline)
            .filter(
                Kline.id == kline.id,
                Kline.timeframe == KlineTimeframe.DAY,
            )
            .first()
        )
        assert surviving is not None, "400-day-old daily kline should survive cleanup"
        assert deleted_count == 0, "No daily klines should be deleted within 1825-day window"

    def test_daily_kline_deleted_beyond_1825_days(self, db_session: Session):
        """Daily kline older than 1825 days should be deleted."""
        kline_repo = KlineRepository(db_session)
        updater = CalendarUpdater(kline_repo)

        # Create a daily kline dated 2000 days ago (beyond 1825-day retention)
        kline = _create_test_kline(db_session, days_ago=2000, timeframe=KlineTimeframe.DAY)
        kline_id = kline.id  # Store ID before deletion

        # Run cleanup
        deleted_count = updater.cleanup_old_klines()

        # Verify the 2000-day-old daily kline WAS deleted
        surviving = (
            db_session.query(Kline)
            .filter(
                Kline.id == kline_id,
                Kline.timeframe == KlineTimeframe.DAY,
            )
            .first()
        )
        assert surviving is None, "2000-day-old daily kline should be deleted"
        assert deleted_count == 1, "One daily kline should be deleted"

    def test_30min_kline_survives_100_days_old(self, db_session: Session):
        """30-minute kline 100 days old should survive cleanup (within 365-day window)."""
        kline_repo = KlineRepository(db_session)
        updater = CalendarUpdater(kline_repo)

        # Create a 30-min kline dated 100 days ago
        kline = _create_test_kline(db_session, days_ago=100, timeframe=KlineTimeframe.MINS_30)

        # Run cleanup
        deleted_count = updater.cleanup_old_klines()

        # Verify the 100-day-old 30-min kline was NOT deleted
        surviving = (
            db_session.query(Kline)
            .filter(
                Kline.id == kline.id,
                Kline.timeframe == KlineTimeframe.MINS_30,
            )
            .first()
        )
        assert surviving is not None, "100-day-old 30-min kline should survive cleanup"
        assert deleted_count == 0, "No 30-min klines should be deleted within 365-day window"

    def test_30min_kline_deleted_beyond_365_days(self, db_session: Session):
        """30-minute kline older than 365 days should be deleted."""
        kline_repo = KlineRepository(db_session)
        updater = CalendarUpdater(kline_repo)

        # Create a 30-min kline dated 400 days ago (beyond 365-day retention)
        kline = _create_test_kline(db_session, days_ago=400, timeframe=KlineTimeframe.MINS_30)
        kline_id = kline.id  # Store ID before deletion

        # Run cleanup
        deleted_count = updater.cleanup_old_klines()

        # Verify the 400-day-old 30-min kline WAS deleted
        surviving = (
            db_session.query(Kline)
            .filter(
                Kline.id == kline_id,
                Kline.timeframe == KlineTimeframe.MINS_30,
            )
            .first()
        )
        assert surviving is None, "400-day-old 30-min kline should be deleted"
        assert deleted_count == 1, "One 30-min kline should be deleted"

    def test_cleanup_preserves_recent_data(self, db_session: Session):
        """Recent klines (within retention windows) are preserved."""
        kline_repo = KlineRepository(db_session)
        updater = CalendarUpdater(kline_repo)

        # Create recent klines: 1 day old daily, 1 day old 30-min
        daily_recent = _create_test_kline(db_session, days_ago=1, timeframe=KlineTimeframe.DAY)
        mins_recent = _create_test_kline(
            db_session, days_ago=1, timeframe=KlineTimeframe.MINS_30, symbol_code="000002.SZ"
        )

        # Run cleanup
        deleted_count = updater.cleanup_old_klines()

        # Verify both recent klines survive
        assert (
            db_session.query(Kline).filter(Kline.id == daily_recent.id).first() is not None
        ), "Recent daily kline should survive"
        assert (
            db_session.query(Kline).filter(Kline.id == mins_recent.id).first() is not None
        ), "Recent 30-min kline should survive"
        assert deleted_count == 0, "No recent klines should be deleted"

    def test_custom_retention_parameters(self, db_session: Session):
        """Cleanup accepts custom retention parameters."""
        kline_repo = KlineRepository(db_session)
        updater = CalendarUpdater(kline_repo)

        # Create klines at various ages
        daily_50 = _create_test_kline(db_session, days_ago=50, timeframe=KlineTimeframe.DAY)
        daily_50_id = daily_50.id
        mins_40 = _create_test_kline(
            db_session, days_ago=40, timeframe=KlineTimeframe.MINS_30, symbol_code="000002.SZ"
        )
        mins_40_id = mins_40.id

        # Run cleanup with custom short retention (30 days for both)
        deleted_count = updater.cleanup_old_klines(days=30, mins_days=30)

        # Both should be deleted
        assert (
            db_session.query(Kline).filter(Kline.id == daily_50_id).first() is None
        ), "50-day-old daily should be deleted with 30-day retention"
        assert (
            db_session.query(Kline).filter(Kline.id == mins_40_id).first() is None
        ), "40-day-old 30-min should be deleted with 30-day retention"
        assert deleted_count == 2, "Both old klines should be deleted"


class TestTradeCalendarCoverage:
    """Test trade calendar coverage for 2021-2026."""

    @patch("src.services.calendar_updater.TushareClient")
    def test_trade_calendar_covers_2021_through_2026(
        self, mock_tushare_client, db_session: Session
    ):
        """Trade calendar should span from 2021-01-01 to at least 2026-12-31."""
        kline_repo = KlineRepository(db_session)
        updater = CalendarUpdater(kline_repo)

        # Mock TushareClient to return test data spanning 2021-2026
        mock_client_instance = MagicMock()
        mock_tushare_client.return_value = mock_client_instance

        # Generate mock calendar data: 2021-01-01 to 2026-12-31
        dates = pd.date_range(start="2021-01-01", end="2026-12-31", freq="D")
        mock_df = pd.DataFrame(
            {
                "cal_date": [d.strftime("%Y%m%d") for d in dates],
                # Simulate ~240 trading days per year (weekdays only, roughly)
                "is_open": [1 if d.weekday() < 5 else 0 for d in dates],
            }
        )
        mock_client_instance.fetch_trade_calendar.return_value = mock_df

        # Manually inject the mocked client
        updater._tushare_client = mock_client_instance

        # Run update
        count = updater.update_trade_calendar()

        # Verify date range
        min_date = (
            db_session.query(TradeCalendar.date)
            .order_by(TradeCalendar.date)
            .first()
        )
        max_date = (
            db_session.query(TradeCalendar.date)
            .order_by(TradeCalendar.date.desc())
            .first()
        )

        assert count > 0, "Should have inserted calendar records"
        assert min_date[0] <= "2021-01-04", f"Min date {min_date[0]} should be <= 2021-01-04"
        assert max_date[0] >= "2026-12-31", f"Max date {max_date[0]} should be >= 2026-12-31"

    @patch("src.services.calendar_updater.TushareClient")
    def test_trade_calendar_has_reasonable_trading_day_count(
        self, mock_tushare_client, db_session: Session
    ):
        """Trading day count should be between 1,300 and 1,700 for 6-year span."""
        kline_repo = KlineRepository(db_session)
        updater = CalendarUpdater(kline_repo)

        # Mock TushareClient
        mock_client_instance = MagicMock()
        mock_tushare_client.return_value = mock_client_instance

        # Generate ~1,440 trading days (240/year × 6 years)
        dates = pd.date_range(start="2021-01-01", end="2026-12-31", freq="D")
        mock_df = pd.DataFrame(
            {
                "cal_date": [d.strftime("%Y%m%d") for d in dates],
                "is_open": [1 if d.weekday() < 5 else 0 for d in dates],
            }
        )
        mock_client_instance.fetch_trade_calendar.return_value = mock_df

        updater._tushare_client = mock_client_instance

        # Run update
        updater.update_trade_calendar()

        # Count trading days
        trading_days = (
            db_session.query(TradeCalendar)
            .filter(TradeCalendar.is_trading_day == 1)
            .count()
        )

        assert (
            1300 <= trading_days <= 1700
        ), f"Trading days {trading_days} should be between 1,300 and 1,700"

    @patch("src.services.calendar_updater.TushareClient")
    def test_update_trade_calendar_is_idempotent(
        self, mock_tushare_client, db_session: Session
    ):
        """Running update_trade_calendar twice should not create duplicates."""
        kline_repo = KlineRepository(db_session)
        updater = CalendarUpdater(kline_repo)

        # Mock TushareClient
        mock_client_instance = MagicMock()
        mock_tushare_client.return_value = mock_client_instance

        # Mock data: 10 days
        mock_df = pd.DataFrame(
            {
                "cal_date": ["20210101", "20210104", "20210105", "20210106", "20210107"],
                "is_open": [0, 1, 1, 1, 1],
            }
        )
        mock_client_instance.fetch_trade_calendar.return_value = mock_df

        updater._tushare_client = mock_client_instance

        # First run
        count1 = updater.update_trade_calendar()
        total1 = db_session.query(TradeCalendar).count()

        # Second run (should update existing records, not insert new ones)
        count2 = updater.update_trade_calendar()
        total2 = db_session.query(TradeCalendar).count()

        assert count1 == 5, "First run should process 5 records"
        assert count2 == 5, "Second run should process 5 records"
        assert total1 == total2, "Total count should remain the same (no duplicates)"
        assert total1 == 5, "Should have exactly 5 unique date records"

    @patch("src.services.calendar_updater.TushareClient")
    def test_update_trade_calendar_uses_correct_date_range(
        self, mock_tushare_client, db_session: Session
    ):
        """update_trade_calendar should request data from 2021 to next year."""
        kline_repo = KlineRepository(db_session)
        updater = CalendarUpdater(kline_repo)

        # Mock TushareClient
        mock_client_instance = MagicMock()
        mock_tushare_client.return_value = mock_client_instance

        # Mock empty response
        mock_df = pd.DataFrame(columns=["cal_date", "is_open"])
        mock_client_instance.fetch_trade_calendar.return_value = mock_df

        updater._tushare_client = mock_client_instance

        # Run update
        updater.update_trade_calendar()

        # Verify fetch_trade_calendar was called with correct parameters
        current_year = datetime.now().year
        expected_start = "20210101"
        expected_end = f"{current_year + 1}1231"

        mock_client_instance.fetch_trade_calendar.assert_called_once_with(
            start_date=expected_start, end_date=expected_end
        )
