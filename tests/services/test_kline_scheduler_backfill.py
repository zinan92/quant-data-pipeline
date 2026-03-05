from __future__ import annotations

from datetime import datetime

from src.services.kline_scheduler import should_run_startup_backfill


def test_should_run_startup_backfill_when_daily_data_is_stale() -> None:
    now = datetime(2026, 3, 4, 18, 30)
    assert should_run_startup_backfill(
        now=now,
        expected_trade_date="2026-03-04",
        latest_index_date="2026-03-03",
        latest_stock_date="2026-03-03",
    )


def test_should_not_run_startup_backfill_before_evening_window() -> None:
    now = datetime(2026, 3, 4, 16, 30)
    assert not should_run_startup_backfill(
        now=now,
        expected_trade_date="2026-03-04",
        latest_index_date="2026-03-03",
        latest_stock_date="2026-03-03",
    )


def test_should_not_run_startup_backfill_when_data_is_current() -> None:
    now = datetime(2026, 3, 4, 19, 0)
    assert not should_run_startup_backfill(
        now=now,
        expected_trade_date="2026-03-04",
        latest_index_date="2026-03-04",
        latest_stock_date="2026-03-04",
    )
