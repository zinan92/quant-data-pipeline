"""Tests for backfill verification script logic"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import text


class TestBackfillVerifierLogic:
    """Test backfill verification logic"""

    def test_stock_count_query_structure(self, db_session):
        """Test that stock count query works with proper table structure"""
        # Check if stock_basic table exists
        check_table = text("SELECT name FROM sqlite_master WHERE type='table' AND name='stock_basic'")
        result = db_session.execute(check_table)
        if not result.fetchone():
            pytest.skip("stock_basic table not in test database")
        
        # Query structure from verify_backfill.py
        query = text("""
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
        """)
        
        # Should execute without errors (even if no results)
        result = db_session.execute(query)
        rows = result.fetchall()
        assert isinstance(rows, list)

    def test_index_count_query_structure(self, db_session):
        """Test that index count query works"""
        query = text("""
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
        """)
        
        result = db_session.execute(query)
        rows = result.fetchall()
        assert isinstance(rows, list)

    def test_null_ohlcv_check_query(self, db_session):
        """Test NULL OHLCV check query"""
        query = text("""
        SELECT COUNT(*) 
        FROM klines
        WHERE (open IS NULL OR high IS NULL OR low IS NULL OR close IS NULL)
        AND timeframe = 'DAY'
        """)
        
        result = db_session.execute(query)
        count = result.scalar()
        assert isinstance(count, int)
        assert count >= 0

    def test_high_low_violation_query(self, db_session):
        """Test high < low violation check query"""
        query = text("""
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
        """)
        
        result = db_session.execute(query)
        rows = result.fetchall()
        assert isinstance(rows, list)

    def test_gap_detection_query_structure(self, db_session):
        """Test gap detection query structure"""
        # Check if trade_calendar table exists
        check_table = text("SELECT name FROM sqlite_master WHERE type='table' AND name='trade_calendar'")
        result = db_session.execute(check_table)
        if not result.fetchone():
            pytest.skip("trade_calendar table not in test database")
        
        # Sample one stock for testing
        stock_result = db_session.execute(text("""
            SELECT DISTINCT symbol_code
            FROM klines
            WHERE symbol_type = 'STOCK' AND timeframe = 'DAY'
            LIMIT 1
        """))
        stocks = stock_result.fetchall()
        
        if not stocks:
            pytest.skip("No stock klines in test database")
        
        symbol_code = stocks[0][0]
        
        gap_query = text("""
        SELECT COUNT(*) as gap_count
        FROM trade_calendar tc
        WHERE tc.is_trading_day = 1
        AND tc.date >= '2021-01-04'
        AND tc.date <= date('now')
        AND tc.date NOT IN (
            SELECT DISTINCT substr(trade_time, 1, 10)
            FROM klines
            WHERE symbol_code = :symbol_code 
            AND symbol_type = 'STOCK' 
            AND timeframe = 'DAY'
        )
        """)
        
        result = db_session.execute(gap_query, {"symbol_code": symbol_code})
        gap_count = result.scalar()
        assert isinstance(gap_count, int)
        assert gap_count >= 0


class TestSchedulerCompatibility:
    """Test that scheduler works with expanded universe"""

    def test_index_list_has_8_indices(self):
        """Test that INDEX_LIST contains all 8 indices"""
        from src.services.index_updater import INDEX_LIST
        
        assert len(INDEX_LIST) == 8
        
        # Check expected indices are present
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
        
        actual_codes = {item[0] for item in INDEX_LIST}
        assert actual_codes == expected_codes

    def test_stock_updater_reads_from_watchlist(self):
        """Test that StockUpdater reads from watchlist table"""
        from src.repositories.kline_repository import KlineRepository
        from src.repositories.symbol_repository import SymbolRepository
        from src.services.stock_updater import StockUpdater
        from src.database import SessionLocal
        
        session = SessionLocal()
        try:
            kline_repo = KlineRepository(session)
            symbol_repo = SymbolRepository(session)
            updater = StockUpdater(kline_repo, symbol_repo)
            
            # This method should query the watchlist table
            tickers = updater._get_watchlist_tickers()
            
            # Should return a list (may be empty in test db)
            assert isinstance(tickers, list)
            
            # Verify it's actually reading from watchlist table
            watchlist_count = session.execute(
                text("SELECT COUNT(*) FROM watchlist")
            ).scalar()
            
            assert len(tickers) == watchlist_count
        finally:
            session.close()

    def test_no_hardcoded_stock_lists_in_scheduler(self):
        """Test that scheduler doesn't have hardcoded stock lists"""
        from src.services.kline_scheduler import KlineScheduler
        import inspect
        
        # Get source code of scheduler
        source = inspect.getsource(KlineScheduler)
        
        # Should NOT contain hardcoded ticker lists like ["000001", "600000", ...]
        # These patterns would indicate hardcoded stock lists
        bad_patterns = [
            '["000001"',
            '["600000"',
            "['000001'",
            "['600000'",
        ]
        
        for pattern in bad_patterns:
            assert pattern not in source, f"Found hardcoded stock list pattern: {pattern}"

    def test_sqlite_wal_mode_enabled(self):
        """Test that SQLite WAL mode is enabled in database.py"""
        from src.database import engine
        
        # Check that WAL mode is set via event listener
        from src import database
        import inspect
        
        source = inspect.getsource(database)
        
        # Should contain PRAGMA journal_mode=WAL
        assert "PRAGMA journal_mode=WAL" in source
        
        # Verify it's actually enabled by querying a connection
        with engine.connect() as conn:
            result = conn.execute(text("PRAGMA journal_mode"))
            mode = result.scalar()
            assert mode.lower() == "wal"


class TestQuantDashboardIntegration:
    """Test that quant-dashboard can read backfilled data"""

    def test_market_reader_can_import(self):
        """Test that MarketReader can be imported"""
        try:
            from src.data_layer.market_reader import MarketReader
            assert MarketReader is not None
        except ImportError:
            # Skip if quant-dashboard is not in path
            pytest.skip("quant-dashboard not in path")

    def test_market_reader_reads_stock_klines(self, db_session):
        """Test that MarketReader can read stock klines"""
        try:
            from src.data_layer.market_reader import MarketReader
        except ImportError:
            pytest.skip("quant-dashboard not in path")
        
        # Get a sample stock
        result = db_session.execute(text("""
            SELECT DISTINCT symbol_code
            FROM klines
            WHERE symbol_type = 'STOCK' AND timeframe = 'DAY'
            LIMIT 1
        """))
        stocks = result.fetchall()
        
        if not stocks:
            pytest.skip("No stock klines in test database")
        
        symbol_code = stocks[0][0]
        
        # MarketReader uses absolute path by default, so we need to check
        # if market.db exists at the expected location
        from pathlib import Path
        db_path = Path("/Users/wendy/work/trading-co/ashare/data/market.db")
        
        if not db_path.exists():
            pytest.skip("market.db not found at expected path")
        
        reader = MarketReader(db_path)
        df = reader.get_stock_klines(symbol_code, start_date="2021-01-04")
        
        # Should return a DataFrame
        import pandas as pd
        assert isinstance(df, pd.DataFrame)
        
        # Should have OHLCV columns
        expected_cols = {"date", "open", "high", "low", "close", "volume"}
        assert expected_cols.issubset(set(df.columns))


class TestDataUpdateLogIntegration:
    """Test DataUpdateLog integration"""

    def test_verification_can_log_to_update_log(self, db_session):
        """Test that verification script can write to DataUpdateLog"""
        from src.models.kline import DataUpdateLog
        from src.models.enums import DataUpdateStatus
        
        # Create a log entry
        now = datetime.now(timezone.utc)
        log = DataUpdateLog(
            update_type="backfill_verification",
            symbol_type="ALL",
            timeframe="DAY",
            status=DataUpdateStatus.COMPLETED,
            records_updated=1000,
            error_message=None,
            started_at=now,
            completed_at=now,
            created_at=now
        )
        
        db_session.add(log)
        db_session.commit()
        
        # Verify it was inserted
        result = db_session.query(DataUpdateLog).filter(
            DataUpdateLog.update_type == "backfill_verification"
        ).first()
        
        assert result is not None
        assert result.status == DataUpdateStatus.COMPLETED
        assert result.records_updated == 1000
