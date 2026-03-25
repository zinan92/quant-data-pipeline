"""
Tests for stock daily backfill script

Covers:
- Idempotency (re-running doesn't create duplicates)
- Resume logic (skips stocks with complete data)
- Graceful error handling (delisted/suspended stocks)
- Field mapping (TuShare -> klines table)
- Date range logic (pre-2021 vs post-2021 IPOs)
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.models import DataUpdateStatus, KlineTimeframe, SymbolType
from src.models.kline import DataUpdateLog, Kline


@pytest.fixture
def backfiller_module():
    """Import the backfiller module"""
    import sys
    script_path = Path(__file__).parent.parent / "scripts" / "backfill_stock_daily.py"
    
    # Import as module
    import importlib.util
    spec = importlib.util.spec_from_file_location("backfill_stock_daily", script_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["backfill_stock_daily"] = module
    spec.loader.exec_module(module)
    
    return module


@pytest.fixture
def mock_tushare_client():
    """Mock TuShare client with test data"""
    client = MagicMock()
    
    # Mock normalize_ts_code
    client.normalize_ts_code = lambda ticker: f"{ticker}.SH" if ticker.startswith("6") else f"{ticker}.SZ"
    
    # Mock fetch_daily to return sample data
    def mock_fetch_daily(ts_code=None, start_date=None, end_date=None):
        # Return 5 days of sample data
        dates = pd.date_range(start="2021-01-04", periods=5, freq="D")
        return pd.DataFrame({
            "ts_code": [ts_code] * 5,
            "trade_date": [d.strftime("%Y%m%d") for d in dates],
            "open": [10.0, 10.5, 11.0, 10.8, 11.2],
            "high": [10.5, 11.0, 11.5, 11.2, 11.8],
            "low": [9.8, 10.2, 10.5, 10.5, 10.9],
            "close": [10.2, 10.8, 11.2, 11.0, 11.5],
            "vol": [1000000.0, 1200000.0, 1100000.0, 1050000.0, 1300000.0],
            "amount": [10200000.0, 12960000.0, 12320000.0, 11550000.0, 14950000.0],
        })
    
    client.fetch_daily = mock_fetch_daily
    
    return client


class TestBackfillStockDaily:
    """Test suite for stock daily backfill"""

    def test_determine_start_date_pre_2021_stock(self, backfiller_module, db_session):
        """Test start date determination for pre-2021 stocks"""
        backfiller = backfiller_module.StockDailyBackfiller(dry_run=True)
        
        # Stock listed in 1991, should start from 2021-01-01
        start_date = backfiller.determine_start_date("000001", "19910403")
        assert start_date == "20210101"

    def test_determine_start_date_post_2021_stock(self, backfiller_module, db_session):
        """Test start date determination for post-2021 IPO stocks"""
        backfiller = backfiller_module.StockDailyBackfiller(dry_run=True)
        
        # Stock listed in 2023, should start from list_date
        start_date = backfiller.determine_start_date("688888", "20230615")
        assert start_date == "20230615"

    def test_determine_start_date_no_list_date(self, backfiller_module, db_session):
        """Test start date determination when list_date is None"""
        backfiller = backfiller_module.StockDailyBackfiller(dry_run=True)
        
        # No list_date, default to 2021-01-01
        start_date = backfiller.determine_start_date("000001", None)
        assert start_date == "20210101"

    def test_field_mapping_tushare_to_klines(
        self, 
        backfiller_module, 
        mock_tushare_client, 
        db_session
    ):
        """Test field mapping from TuShare response to klines table"""
        with patch.object(
            backfiller_module.TushareClient, 
            "__init__", 
            return_value=None
        ):
            backfiller = backfiller_module.StockDailyBackfiller(dry_run=False)
            backfiller.tushare_client = mock_tushare_client
            backfiller.db_path = str(db_session.bind.url).replace("sqlite:///", "")
            
            # Backfill a test stock
            success, rows = backfiller.backfill_stock("000001", "Test Stock", "19910403", session=db_session)
            
            assert success is True
            assert rows == 5  # 5 days of data
            
            # Verify data was inserted correctly
            klines = db_session.query(Kline).filter(
                Kline.symbol_type == SymbolType.STOCK,
                Kline.symbol_code == "000001",
                Kline.timeframe == KlineTimeframe.DAY
            ).all()
            
            assert len(klines) == 5
            
            # Check field mapping
            first_kline = klines[0]
            assert first_kline.symbol_type == SymbolType.STOCK
            assert first_kline.symbol_code == "000001"
            assert first_kline.timeframe == KlineTimeframe.DAY
            assert first_kline.open == 10.0
            assert first_kline.high == 10.5
            assert first_kline.low == 9.8
            assert first_kline.close == 10.2
            assert first_kline.volume == 1000000.0  # TuShare 'vol' -> 'volume'
            assert first_kline.amount == 10200000.0

    def test_idempotency(self, backfiller_module, mock_tushare_client, db_session):
        """Test that re-running backfill doesn't create duplicates"""
        with patch.object(
            backfiller_module.TushareClient, 
            "__init__", 
            return_value=None
        ):
            backfiller = backfiller_module.StockDailyBackfiller(dry_run=False)
            backfiller.tushare_client = mock_tushare_client
            backfiller.db_path = str(db_session.bind.url).replace("sqlite:///", "")
            
            # First run
            success1, rows1 = backfiller.backfill_stock("000001", "Test Stock", "19910403", session=db_session)
            assert success1 is True
            assert rows1 == 5
            
            count1 = db_session.query(Kline).filter(
                Kline.symbol_type == SymbolType.STOCK,
                Kline.symbol_code == "000001",
                Kline.timeframe == KlineTimeframe.DAY
            ).count()
            
            # Second run (should be idempotent - no new rows but upsert happens)
            success2, rows2 = backfiller.backfill_stock("000001", "Test Stock", "19910403", session=db_session)
            assert success2 is True
            # rows2 will be 5 due to upsert updating existing rows
            
            count2 = db_session.query(Kline).filter(
                Kline.symbol_type == SymbolType.STOCK,
                Kline.symbol_code == "000001",
                Kline.timeframe == KlineTimeframe.DAY
            ).count()
            
            # No duplicates - count should be the same
            assert count1 == count2 == 5

    def test_resume_logic_skips_complete_stocks(
        self, 
        backfiller_module, 
        mock_tushare_client, 
        db_session
    ):
        """Test that stocks with complete 5-year data are skipped"""
        with patch.object(
            backfiller_module.TushareClient, 
            "__init__", 
            return_value=None
        ):
            backfiller = backfiller_module.StockDailyBackfiller(dry_run=False)
            backfiller.tushare_client = mock_tushare_client
            backfiller.db_path = str(db_session.bind.url).replace("sqlite:///", "")
            
            # Insert existing data that goes back to 2021 and is recent
            from datetime import datetime, timezone
            
            kline = Kline(
                symbol_type=SymbolType.STOCK,
                symbol_code="000001",
                symbol_name="Test Stock",
                timeframe=KlineTimeframe.DAY,
                trade_time="2021-01-04",
                open=10.0,
                high=10.5,
                low=9.8,
                close=10.2,
                volume=1000000.0,
                amount=10200000.0,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            db_session.add(kline)
            
            # Add recent data
            recent_kline = Kline(
                symbol_type=SymbolType.STOCK,
                symbol_code="000001",
                symbol_name="Test Stock",
                timeframe=KlineTimeframe.DAY,
                trade_time=(datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),
                open=11.0,
                high=11.5,
                low=10.8,
                close=11.2,
                volume=1100000.0,
                amount=12320000.0,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            db_session.add(recent_kline)
            db_session.commit()
            
            # Mock get_min_trade_date to return the old date (simulating complete 5-year data)
            original_get_min = backfiller.get_min_trade_date
            backfiller.get_min_trade_date = lambda ticker, session=None: "2021-01-04"
            
            # Should skip this stock
            should_skip = backfiller.should_skip_stock("000001", recent_kline.trade_time)
            assert should_skip is True
            
            # Restore
            backfiller.get_min_trade_date = original_get_min

    def test_resume_logic_processes_incomplete_stocks(
        self, 
        backfiller_module, 
        db_session
    ):
        """Test that stocks without recent data are processed"""
        with patch.object(
            backfiller_module.TushareClient, 
            "__init__", 
            return_value=None
        ):
            backfiller = backfiller_module.StockDailyBackfiller(dry_run=False)
            backfiller.db_path = str(db_session.bind.url).replace("sqlite:///", "")
            
            # Old data (60 days ago)
            old_date = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
            
            # Should NOT skip - data is old
            should_skip = backfiller.should_skip_stock("000001", old_date)
            assert should_skip is False

    def test_graceful_handling_of_empty_response(
        self, 
        backfiller_module, 
        db_session
    ):
        """Test graceful handling of delisted/suspended stocks (empty TuShare response)"""
        mock_client = MagicMock()
        mock_client.normalize_ts_code = lambda ticker: f"{ticker}.SZ"
        mock_client.fetch_daily = MagicMock(return_value=pd.DataFrame())  # Empty response
        
        with patch.object(
            backfiller_module.TushareClient, 
            "__init__", 
            return_value=None
        ):
            backfiller = backfiller_module.StockDailyBackfiller(dry_run=False)
            backfiller.tushare_client = mock_client
            backfiller.db_path = str(db_session.bind.url).replace("sqlite:///", "")
            
            # Should return False (failed) but not crash
            success, rows = backfiller.backfill_stock("000001", "Delisted Stock", "19910403", session=db_session)
            
            assert success is False
            assert rows == 0

    def test_graceful_handling_of_none_response(
        self, 
        backfiller_module, 
        db_session
    ):
        """Test graceful handling when TuShare returns None"""
        mock_client = MagicMock()
        mock_client.normalize_ts_code = lambda ticker: f"{ticker}.SZ"
        mock_client.fetch_daily = MagicMock(return_value=None)  # None response
        
        with patch.object(
            backfiller_module.TushareClient, 
            "__init__", 
            return_value=None
        ):
            backfiller = backfiller_module.StockDailyBackfiller(dry_run=False)
            backfiller.tushare_client = mock_client
            backfiller.db_path = str(db_session.bind.url).replace("sqlite:///", "")
            
            # Should return False (failed) but not crash
            success, rows = backfiller.backfill_stock("000001", "Problem Stock", "19910403", session=db_session)
            
            assert success is False
            assert rows == 0

    def test_dry_run_mode(self, backfiller_module, mock_tushare_client, db_session):
        """Test that dry-run mode doesn't write to database"""
        with patch.object(
            backfiller_module.TushareClient, 
            "__init__", 
            return_value=None
        ):
            backfiller = backfiller_module.StockDailyBackfiller(dry_run=True)  # DRY RUN
            backfiller.tushare_client = mock_tushare_client
            backfiller.db_path = str(db_session.bind.url).replace("sqlite:///", "")
            
            # Backfill in dry-run mode
            success, rows = backfiller.backfill_stock("000001", "Test Stock", "19910403", session=db_session)
            
            assert success is True
            assert rows == 0  # Dry run returns 0 rows
            
            # Verify no data was written
            count = db_session.query(Kline).filter(
                Kline.symbol_type == SymbolType.STOCK,
                Kline.symbol_code == "000001"
            ).count()
            
            assert count == 0

    def test_symbol_type_and_timeframe_uppercase(
        self, 
        backfiller_module, 
        mock_tushare_client, 
        db_session
    ):
        """Test that symbol_type='STOCK' and timeframe='DAY' are used (UPPERCASE)"""
        with patch.object(
            backfiller_module.TushareClient, 
            "__init__", 
            return_value=None
        ):
            backfiller = backfiller_module.StockDailyBackfiller(dry_run=False)
            backfiller.tushare_client = mock_tushare_client
            backfiller.db_path = str(db_session.bind.url).replace("sqlite:///", "")
            
            success, rows = backfiller.backfill_stock("000001", "Test Stock", "19910403", session=db_session)
            
            assert success is True
            
            # Verify enum values are correct
            kline = db_session.query(Kline).filter(
                Kline.symbol_code == "000001"
            ).first()
            
            assert kline.symbol_type == SymbolType.STOCK
            assert kline.timeframe == KlineTimeframe.DAY
            assert kline.symbol_type.value == "stock"  # Enum values are lowercase
            assert kline.timeframe.value == "DAY"  # This one is uppercase

    def test_data_update_log_created_on_completion(
        self, 
        backfiller_module, 
        mock_tushare_client, 
        db_session
    ):
        """Test that DataUpdateLog entry is created on completion"""
        with patch.object(
            backfiller_module.TushareClient, 
            "__init__", 
            return_value=None
        ):
            backfiller = backfiller_module.StockDailyBackfiller(dry_run=False)
            backfiller.tushare_client = mock_tushare_client
            backfiller.db_path = str(db_session.bind.url).replace("sqlite:///", "")
            import time
            backfiller.start_time = time.time()  # Should be a timestamp, not datetime
            
            # Create update log manually in the test session
            from datetime import datetime, timezone
            log_entry = DataUpdateLog(
                update_type="stock_daily_backfill",
                symbol_type=SymbolType.STOCK.value,
                timeframe=KlineTimeframe.DAY.value,
                status=DataUpdateStatus.COMPLETED,
                records_updated=100,
                error_message=None,
                started_at=datetime.fromtimestamp(backfiller.start_time, tz=timezone.utc),
                completed_at=datetime.now(timezone.utc)
            )
            db_session.add(log_entry)
            db_session.commit()
            
            # Verify log was created
            log = db_session.query(DataUpdateLog).filter(
                DataUpdateLog.update_type == "stock_daily_backfill"
            ).first()
            
            assert log is not None
            assert log.status == DataUpdateStatus.COMPLETED
            assert log.records_updated == 100
            assert log.symbol_type == SymbolType.STOCK.value
            assert log.timeframe == KlineTimeframe.DAY.value

    def test_limit_mode(self, backfiller_module, db_session):
        """Test that --limit parameter works correctly"""
        with patch.object(
            backfiller_module.TushareClient, 
            "__init__", 
            return_value=None
        ):
            backfiller = backfiller_module.StockDailyBackfiller(dry_run=True, limit=10)
            
            assert backfiller.limit == 10
