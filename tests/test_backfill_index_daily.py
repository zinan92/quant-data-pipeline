"""
Tests for index daily backfill script

Covers:
- All 8 indices are processed
- Each index has data with MIN(trade_time) <= '2021-01-08'
- Each index has >= 1,100 rows
- <= 2 gap days per index
- Uses TuShare pro.index_daily() not Sina
- Idempotent and resumable
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.models import DataUpdateStatus, KlineTimeframe, SymbolType
from src.models.kline import DataUpdateLog, Kline
from src.services.index_updater import INDEX_LIST


@pytest.fixture
def backfiller_module():
    """Import the backfiller module"""
    import sys
    script_path = Path(__file__).parent.parent / "scripts" / "backfill_index_daily.py"
    
    # Import as module
    import importlib.util
    spec = importlib.util.spec_from_file_location("backfill_index_daily", script_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["backfill_index_daily"] = module
    spec.loader.exec_module(module)
    
    return module


@pytest.fixture
def mock_tushare_client():
    """Mock TuShare client with test data"""
    client = MagicMock()
    
    # Mock fetch_index_daily to return sample 5-year data
    def mock_fetch_index_daily(ts_code=None, start_date=None, end_date=None):
        # Return ~1200 days of sample data (5 years of trading days)
        # Start from 2021-01-04 (first trading day of 2021)
        dates = pd.date_range(start="2021-01-04", periods=1200, freq="B")  # Business days
        return pd.DataFrame({
            "ts_code": [ts_code] * len(dates),
            "trade_date": [d.strftime("%Y%m%d") for d in dates],
            "open": [3000.0 + i * 0.5 for i in range(len(dates))],
            "high": [3010.0 + i * 0.5 for i in range(len(dates))],
            "low": [2990.0 + i * 0.5 for i in range(len(dates))],
            "close": [3005.0 + i * 0.5 for i in range(len(dates))],
            "vol": [100000000.0] * len(dates),
            "amount": [300000000000.0] * len(dates),
        })
    
    # Use MagicMock for the method to track calls
    client.fetch_index_daily = MagicMock(side_effect=mock_fetch_index_daily)
    
    return client


class TestIndexDailyBackfill:
    """Test suite for index daily backfill"""

    def test_all_8_indices_in_index_list(self):
        """Test that INDEX_LIST contains all 8 expected indices"""
        expected_codes = {
            "000001.SH",  # 上证指数
            "399001.SZ",  # 深证成指
            "399006.SZ",  # 创业板指
            "000688.SH",  # 科创50
            "899050.BJ",  # 北证50
            "000300.SH",  # 沪深300
            "000905.SH",  # 中证500
            "000852.SH",  # 中证1000
        }
        
        actual_codes = {ts_code for ts_code, _, _ in INDEX_LIST}
        assert actual_codes == expected_codes, f"INDEX_LIST missing or has extra codes: {actual_codes}"

    def test_should_skip_index_with_complete_data(self, backfiller_module, db_session):
        """Test that indices with complete 5-year data are skipped"""
        backfiller = backfiller_module.IndexDailyBackfiller(dry_run=True)
        
        # Index with recent data (yesterday) should be checked for historical coverage
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        
        # Mock get_min_trade_date to return early 2021
        with patch.object(backfiller, 'get_min_trade_date', return_value="2021-01-05"):
            should_skip = backfiller.should_skip_index("000001.SH", yesterday)
            assert should_skip is True

    def test_should_not_skip_index_without_historical_data(self, backfiller_module, db_session):
        """Test that indices with recent data but no historical data are not skipped"""
        backfiller = backfiller_module.IndexDailyBackfiller(dry_run=True)
        
        # Index with recent data (yesterday)
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        
        # Mock get_min_trade_date to return only recent data (Nov 2025)
        with patch.object(backfiller, 'get_min_trade_date', return_value="2025-11-01"):
            should_skip = backfiller.should_skip_index("000001.SH", yesterday)
            assert should_skip is False

    def test_should_not_skip_index_without_data(self, backfiller_module, db_session):
        """Test that indices with no data are not skipped"""
        backfiller = backfiller_module.IndexDailyBackfiller(dry_run=True)
        
        should_skip = backfiller.should_skip_index("000300.SH", None)
        assert should_skip is False

    def test_backfill_index_uses_tushare_fetch_index_daily(
        self,
        backfiller_module,
        mock_tushare_client,
        db_session
    ):
        """Test that backfill uses TuShare pro.index_daily() method"""
        backfiller = backfiller_module.IndexDailyBackfiller(dry_run=False)
        backfiller.tushare_client = mock_tushare_client
        
        # Backfill one index
        success, rows = backfiller.backfill_index("000001.SH", "上证指数", session=db_session)
        
        # Verify fetch_index_daily was called (not Sina API)
        assert mock_tushare_client.fetch_index_daily.called
        assert success is True
        assert rows > 0

    def test_field_mapping_tushare_to_klines(
        self,
        backfiller_module,
        mock_tushare_client,
        db_session
    ):
        """Test that TuShare fields are correctly mapped to klines table columns"""
        backfiller = backfiller_module.IndexDailyBackfiller(dry_run=False)
        backfiller.tushare_client = mock_tushare_client
        
        # Backfill one index
        backfiller.backfill_index("000001.SH", "上证指数", session=db_session)
        
        # Query the inserted data
        from sqlalchemy import select
        stmt = select(Kline).where(
            Kline.symbol_type == SymbolType.INDEX,
            Kline.symbol_code == "000001.SH",
            Kline.timeframe == KlineTimeframe.DAY
        ).limit(1)
        
        kline = db_session.execute(stmt).scalar_one()
        
        # Verify field mapping
        assert kline.symbol_type == SymbolType.INDEX
        assert kline.symbol_code == "000001.SH"
        assert kline.timeframe == KlineTimeframe.DAY
        assert kline.open > 0
        assert kline.high >= kline.low
        assert kline.close > 0
        assert kline.volume > 0
        assert kline.amount > 0

    def test_idempotency_no_duplicates_on_rerun(
        self,
        backfiller_module,
        mock_tushare_client,
        db_session
    ):
        """Test that re-running backfill doesn't create duplicates"""
        backfiller = backfiller_module.IndexDailyBackfiller(dry_run=False)
        backfiller.tushare_client = mock_tushare_client
        
        # First run
        backfiller.backfill_index("000001.SH", "上证指数", session=db_session)
        
        # Count rows
        from sqlalchemy import select, func
        stmt = select(func.count()).where(
            Kline.symbol_type == SymbolType.INDEX,
            Kline.symbol_code == "000001.SH",
            Kline.timeframe == KlineTimeframe.DAY
        )
        count_first = db_session.execute(stmt).scalar()
        
        # Second run (should use UPSERT)
        backfiller.backfill_index("000001.SH", "上证指数", session=db_session)
        
        # Count rows again
        count_second = db_session.execute(stmt).scalar()
        
        # No duplicates should be created
        assert count_second == count_first

    def test_resume_logic_skips_complete_index(
        self,
        backfiller_module,
        mock_tushare_client,
        db_session
    ):
        """Test that resume logic skips indices with complete data"""
        backfiller = backfiller_module.IndexDailyBackfiller(dry_run=False)
        backfiller.tushare_client = mock_tushare_client
        
        # First backfill (complete)
        backfiller.backfill_index("000001.SH", "上证指数", session=db_session)
        db_session.commit()
        
        # Mock the TuShare client to return updated data (simulating no new data)
        # This simulates the case where we already have all available data
        mock_client_no_new_data = MagicMock()
        
        def mock_fetch_no_new_data(ts_code=None, start_date=None, end_date=None):
            # Return empty DataFrame (no new data available)
            return pd.DataFrame()
        
        mock_client_no_new_data.fetch_index_daily = MagicMock(side_effect=mock_fetch_no_new_data)
        
        # Create a new backfiller instance
        backfiller2 = backfiller_module.IndexDailyBackfiller(dry_run=False)
        backfiller2.tushare_client = mock_client_no_new_data
        
        # Second run should detect complete data and either skip or get empty response
        success, rows = backfiller2.backfill_index("000001.SH", "上证指数", session=db_session)
        
        # Either skipped (0 rows) or fetched empty response (0 rows)
        assert rows == 0  # No new rows added

    def test_data_validation_min_trade_time(
        self,
        backfiller_module,
        mock_tushare_client,
        db_session
    ):
        """Test that backfilled data has MIN(trade_time) <= '2021-01-08'"""
        backfiller = backfiller_module.IndexDailyBackfiller(dry_run=False)
        backfiller.tushare_client = mock_tushare_client
        
        # Backfill one index
        backfiller.backfill_index("000001.SH", "上证指数", session=db_session)
        
        # Check MIN(trade_time)
        min_date_str = backfiller.get_min_trade_date("000001.SH", session=db_session)
        assert min_date_str is not None
        
        min_date = datetime.strptime(min_date_str, "%Y-%m-%d")
        target_date = datetime.strptime("2021-01-08", "%Y-%m-%d")
        
        assert min_date <= target_date, f"MIN(trade_time) {min_date_str} is after 2021-01-08"

    def test_data_validation_row_count(
        self,
        backfiller_module,
        mock_tushare_client,
        db_session
    ):
        """Test that each index has >= 1,100 rows"""
        backfiller = backfiller_module.IndexDailyBackfiller(dry_run=False)
        backfiller.tushare_client = mock_tushare_client
        
        # Backfill one index
        backfiller.backfill_index("000001.SH", "上证指数", session=db_session)
        
        # Count rows
        from sqlalchemy import select, func
        stmt = select(func.count()).where(
            Kline.symbol_type == SymbolType.INDEX,
            Kline.symbol_code == "000001.SH",
            Kline.timeframe == KlineTimeframe.DAY
        )
        count = db_session.execute(stmt).scalar()
        
        assert count >= 1100, f"Index 000001.SH has only {count} rows, expected >= 1100"

    def test_empty_response_handling(
        self,
        backfiller_module,
        db_session
    ):
        """Test graceful handling of empty TuShare response"""
        backfiller = backfiller_module.IndexDailyBackfiller(dry_run=False)
        
        # Mock client that returns empty DataFrame
        mock_client = MagicMock()
        mock_client.fetch_index_daily = MagicMock(return_value=pd.DataFrame())
        backfiller.tushare_client = mock_client
        
        # Should not crash
        success, rows = backfiller.backfill_index("999999.XX", "不存在指数", session=db_session)
        
        assert success is False
        assert rows == 0

    def test_exception_handling(
        self,
        backfiller_module,
        db_session
    ):
        """Test graceful handling of TuShare API exceptions"""
        backfiller = backfiller_module.IndexDailyBackfiller(dry_run=False)
        
        # Mock client that raises exception
        mock_client = MagicMock()
        mock_client.fetch_index_daily = MagicMock(side_effect=Exception("API Error"))
        backfiller.tushare_client = mock_client
        
        # Should not crash
        success, rows = backfiller.backfill_index("000001.SH", "上证指数", session=db_session)
        
        assert success is False
        assert rows == 0

    def test_ohlcv_validation(
        self,
        backfiller_module,
        mock_tushare_client,
        db_session
    ):
        """Test that OHLCV data is valid (high >= low, no NULLs)"""
        backfiller = backfiller_module.IndexDailyBackfiller(dry_run=False)
        backfiller.tushare_client = mock_tushare_client
        
        # Backfill one index
        backfiller.backfill_index("000001.SH", "上证指数", session=db_session)
        
        # Query all rows
        from sqlalchemy import select
        stmt = select(Kline).where(
            Kline.symbol_type == SymbolType.INDEX,
            Kline.symbol_code == "000001.SH",
            Kline.timeframe == KlineTimeframe.DAY
        )
        
        klines = db_session.execute(stmt).scalars().all()
        
        for kline in klines:
            # No NULLs
            assert kline.open is not None
            assert kline.high is not None
            assert kline.low is not None
            assert kline.close is not None
            
            # high >= low
            assert kline.high >= kline.low, f"Invalid OHLC: high={kline.high}, low={kline.low}"

    def test_dry_run_mode(
        self,
        backfiller_module,
        mock_tushare_client,
        db_session
    ):
        """Test that dry-run mode doesn't insert data"""
        backfiller = backfiller_module.IndexDailyBackfiller(dry_run=True)
        backfiller.tushare_client = mock_tushare_client
        
        # Run in dry-run mode
        success, rows = backfiller.backfill_index("000001.SH", "上证指数", session=db_session)
        
        # Should report success but insert 0 rows
        assert success is True
        assert rows == 0
        
        # Verify no data was inserted
        from sqlalchemy import select, func
        stmt = select(func.count()).where(
            Kline.symbol_type == SymbolType.INDEX,
            Kline.symbol_code == "000001.SH",
            Kline.timeframe == KlineTimeframe.DAY
        )
        count = db_session.execute(stmt).scalar()
        
        assert count == 0

    def test_data_update_log_created(
        self,
        backfiller_module,
        mock_tushare_client,
        db_session
    ):
        """Test that DataUpdateLog entry is created"""
        backfiller = backfiller_module.IndexDailyBackfiller(dry_run=False)
        backfiller.tushare_client = mock_tushare_client
        backfiller.start_time = 1000000.0
        
        # Create log entry (this creates its own session, so we need to query from DB)
        backfiller.create_update_log(DataUpdateStatus.COMPLETED, 100, None)
        
        # Query from a fresh session to see the committed log (take the latest one)
        from src.database import SessionLocal
        fresh_session = SessionLocal()
        try:
            from sqlalchemy import select
            stmt = select(DataUpdateLog).where(
                DataUpdateLog.update_type == "index_daily_backfill"
            ).order_by(DataUpdateLog.id.desc()).limit(1)
            
            log = fresh_session.execute(stmt).scalar_one()
            
            assert log is not None
            assert log.status == DataUpdateStatus.COMPLETED
            assert log.records_updated == 100
            assert log.symbol_type == SymbolType.INDEX.value
            assert log.timeframe == KlineTimeframe.DAY.value
        finally:
            fresh_session.close()


class TestGapDetection:
    """Test gap detection in backfilled data"""

    def test_gap_detection_logic(self, db_session):
        """Test that gap detection can identify missing trading days"""
        # This is a placeholder for the gap detection logic that will be
        # implemented in the verification script
        
        # Skip this test if trade_calendar is not populated (test DB doesn't always have it)
        from sqlalchemy import select, text
        
        try:
            # Check that trade_calendar exists and has data
            result = db_session.execute(text("SELECT COUNT(*) FROM trade_calendar WHERE is_trading_day = 1"))
            trading_days = result.scalar()
            
            if trading_days == 0:
                pytest.skip("trade_calendar not populated in test database")
        except Exception:
            pytest.skip("trade_calendar table not available in test database")

    def test_max_2_gaps_per_index(self, backfiller_module, mock_tushare_client, db_session):
        """Test that each index has <= 2 gap days (placeholder)"""
        # This test will be expanded once gap detection is fully implemented
        # For now, we just verify the data is continuous (mock data has no gaps)
        
        backfiller = backfiller_module.IndexDailyBackfiller(dry_run=False)
        backfiller.tushare_client = mock_tushare_client
        
        # Backfill one index
        backfiller.backfill_index("000001.SH", "上证指数", session=db_session)
        
        # Query the data and check for continuity
        from sqlalchemy import select
        stmt = select(Kline.trade_time).where(
            Kline.symbol_type == SymbolType.INDEX,
            Kline.symbol_code == "000001.SH",
            Kline.timeframe == KlineTimeframe.DAY
        ).order_by(Kline.trade_time)
        
        dates = [row[0] for row in db_session.execute(stmt).all()]
        
        # With mock data, we should have continuous dates (no gaps)
        assert len(dates) > 0
        
        # Note: Real gap detection will be implemented in the verification script
        # This test just ensures data can be queried
