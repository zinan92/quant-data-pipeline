"""
Tests for CalendarUpdater cleanup retention logic.

Validates:
- Daily klines survive 400-day-old records (within 1825-day retention)
- 30-minute klines survive 100-day-old records (within 365-day retention)
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from src.models import Kline, KlineTimeframe, SymbolType
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
