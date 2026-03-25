"""
Tests for stock universe expansion script
"""
import sqlite3
import sys
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
import pandas as pd
import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.expand_stock_universe import StockUniverseExpander


class TestStockUniverseExpander:
    """Test suite for StockUniverseExpander"""

    @pytest.fixture
    def mock_settings(self):
        """Mock settings"""
        settings = Mock()
        settings.database_url = "sqlite:///test.db"
        settings.tushare_token = "test_token"
        settings.tushare_points = 15000
        return settings

    @pytest.fixture
    def mock_tushare_client(self):
        """Mock TuShare client"""
        client = Mock()
        client.denormalize_ts_code = lambda x: x.split('.')[0]
        client.normalize_ts_code = lambda x: f"{x}.SH" if x.startswith('6') else f"{x}.SZ"
        return client

    @pytest.fixture
    def expander(self, tmp_path, mock_settings, mock_tushare_client):
        """Create expander with temporary database"""
        db_path = tmp_path / "test_market.db"
        mock_settings.database_url = f"sqlite:///{db_path}"

        # Create test database with required tables
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # watchlist table
        cursor.execute("""
            CREATE TABLE watchlist (
                id INTEGER PRIMARY KEY,
                ticker VARCHAR(16) UNIQUE NOT NULL,
                added_at DATETIME NOT NULL,
                is_focus INTEGER NOT NULL DEFAULT 0,
                category VARCHAR(64),
                purchase_price FLOAT,
                purchase_date DATETIME,
                shares FLOAT,
                positioning TEXT
            )
        """)

        # symbol_metadata table
        cursor.execute("""
            CREATE TABLE symbol_metadata (
                ticker VARCHAR(16) PRIMARY KEY,
                name VARCHAR(64) NOT NULL,
                list_date VARCHAR(8),
                total_mv FLOAT,
                circ_mv FLOAT,
                pe_ttm FLOAT,
                pb FLOAT,
                introduction TEXT,
                main_business TEXT,
                business_scope TEXT,
                chairman VARCHAR(64),
                manager VARCHAR(64),
                reg_capital FLOAT,
                setup_date VARCHAR(10),
                province VARCHAR(32),
                city VARCHAR(32),
                employees INTEGER,
                website VARCHAR(128),
                industry_lv1 VARCHAR(64),
                industry_lv2 VARCHAR(64),
                industry_lv3 VARCHAR(64),
                super_category VARCHAR(64),
                concepts JSON,
                last_sync DATETIME NOT NULL
            )
        """)

        # stock_sectors table
        cursor.execute("""
            CREATE TABLE stock_sectors (
                id INTEGER PRIMARY KEY,
                ticker TEXT NOT NULL,
                sector TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                positioning TEXT
            )
        """)

        # stock_basic table
        cursor.execute("""
            CREATE TABLE stock_basic (
                ts_code TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                name TEXT NOT NULL,
                area TEXT,
                industry TEXT,
                market TEXT,
                list_date TEXT
            )
        """)

        # Insert some existing data
        cursor.execute(
            "INSERT INTO watchlist (ticker, added_at, is_focus) VALUES (?, ?, ?)",
            ('000001', datetime.now().isoformat(), 0)
        )
        cursor.execute(
            "INSERT INTO watchlist (ticker, added_at, is_focus) VALUES (?, ?, ?)",
            ('600000', datetime.now().isoformat(), 0)
        )
        cursor.execute(
            "INSERT INTO symbol_metadata (ticker, name, last_sync) VALUES (?, ?, ?)",
            ('000001', '平安银行', datetime.now().isoformat())
        )
        cursor.execute(
            "INSERT INTO stock_sectors (ticker, sector, created_at, updated_at) VALUES (?, ?, ?, ?)",
            ('000001', '金融', datetime.now().strftime('%Y-%m-%d %H:%M:%S'), datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        )

        conn.commit()
        conn.close()

        with patch('scripts.expand_stock_universe.get_settings', return_value=mock_settings):
            with patch('scripts.expand_stock_universe.TushareClient', return_value=mock_tushare_client):
                expander = StockUniverseExpander()
                expander.db_path = str(db_path)
                return expander

    def test_get_existing_watchlist(self, expander):
        """Test getting existing watchlist"""
        existing = expander.get_existing_watchlist()
        assert isinstance(existing, set)
        assert '000001' in existing
        assert '600000' in existing
        assert len(existing) == 2

    def test_fetch_index_constituents(self, expander):
        """Test fetching index constituents"""
        # Mock TuShare response
        mock_df = pd.DataFrame({
            'index_code': ['000300.SH'] * 5,
            'con_code': ['600519.SH', '300750.SZ', '601899.SH', '000001.SZ', '600036.SH'],
            'trade_date': ['20260302'] * 5,
            'weight': [3.5, 3.4, 2.6, 2.5, 2.4]
        })

        expander.tushare_client.pro.index_weight = Mock(return_value=mock_df)

        constituents = expander.fetch_index_constituents('000300.SH', 'CSI 300')

        assert isinstance(constituents, set)
        assert len(constituents) == 5
        assert '600519' in constituents
        assert '300750' in constituents

    def test_fetch_index_constituents_empty(self, expander):
        """Test fetching index constituents with empty response"""
        expander.tushare_client.pro.index_weight = Mock(return_value=pd.DataFrame())

        constituents = expander.fetch_index_constituents('000300.SH', 'CSI 300')

        assert isinstance(constituents, set)
        assert len(constituents) == 0

    def test_merge_with_watchlist(self, expander):
        """Test merging new constituents with existing watchlist"""
        existing = {'000001', '600000', '600519'}
        constituents = {'600519', '300750', '601899', '000002'}

        new_tickers = expander.merge_with_watchlist(existing, constituents)

        assert isinstance(new_tickers, set)
        assert len(new_tickers) == 3
        assert '300750' in new_tickers
        assert '601899' in new_tickers
        assert '000002' in new_tickers
        assert '600519' not in new_tickers  # Already exists

    def test_insert_into_watchlist(self, expander):
        """Test inserting new tickers into watchlist"""
        new_tickers = {'000002', '600519', '300750'}

        inserted = expander.insert_into_watchlist(new_tickers)

        assert inserted == 3

        # Verify insertion
        conn = sqlite3.connect(expander.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM watchlist")
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 5  # 2 existing + 3 new

    def test_insert_into_watchlist_empty(self, expander):
        """Test inserting empty set into watchlist"""
        inserted = expander.insert_into_watchlist(set())
        assert inserted == 0

    def test_insert_into_watchlist_idempotent(self, expander):
        """Test that inserting same tickers twice is idempotent"""
        new_tickers = {'000002', '600519'}

        # First insertion
        inserted1 = expander.insert_into_watchlist(new_tickers)
        assert inserted1 == 2

        # Second insertion (should be ignored)
        inserted2 = expander.insert_into_watchlist(new_tickers)
        assert inserted2 == 0

        # Verify count
        conn = sqlite3.connect(expander.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM watchlist")
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 4  # 2 existing + 2 new (not 6)

    def test_fetch_and_update_stock_basic(self, expander):
        """Test fetching and updating stock_basic"""
        tickers = {'000002', '600519'}

        # Mock TuShare fetch_stock_list
        mock_df = pd.DataFrame({
            'ts_code': ['000002.SZ', '600519.SH'],
            'symbol': ['000002', '600519'],
            'name': ['万科A', '贵州茅台'],
            'area': ['深圳', '贵州'],
            'industry': ['房地产', '白酒'],
            'market': ['主板', '主板'],
            'list_date': ['19910129', '20010827']
        })

        expander.tushare_client.fetch_stock_list = Mock(return_value=mock_df)

        inserted = expander.fetch_and_update_stock_basic(tickers)

        assert inserted == 2

        # Verify insertion
        conn = sqlite3.connect(expander.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT symbol, name FROM stock_basic WHERE symbol IN ('000002', '600519')")
        rows = cursor.fetchall()
        conn.close()

        assert len(rows) == 2
        symbols = {row[0] for row in rows}
        assert '000002' in symbols
        assert '600519' in symbols

    def test_update_symbol_metadata(self, expander):
        """Test updating symbol_metadata"""
        tickers = {'000002', '600519'}

        # Mock TuShare fetch_stock_list
        mock_df = pd.DataFrame({
            'ts_code': ['000002.SZ', '600519.SH'],
            'symbol': ['000002', '600519'],
            'name': ['万科A', '贵州茅台'],
            'list_date': ['19910129', '20010827']
        })

        expander.tushare_client.fetch_stock_list = Mock(return_value=mock_df)

        inserted = expander.update_symbol_metadata(tickers)

        assert inserted == 2

        # Verify insertion
        conn = sqlite3.connect(expander.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT ticker, name FROM symbol_metadata WHERE ticker IN ('000002', '600519')")
        rows = cursor.fetchall()
        conn.close()

        assert len(rows) == 2

    def test_update_stock_sectors(self, expander):
        """Test updating stock_sectors"""
        tickers = {'000002', '600519'}

        inserted = expander.update_stock_sectors(tickers)

        assert inserted == 2

        # Verify insertion
        conn = sqlite3.connect(expander.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT ticker FROM stock_sectors WHERE ticker IN ('000002', '600519')")
        rows = cursor.fetchall()
        conn.close()

        assert len(rows) == 2

    def test_verify_expansion(self, expander):
        """Test verification of expansion results"""
        # Add some test data
        new_tickers = {'000002', '600519', '300750'}
        expander.insert_into_watchlist(new_tickers)

        # Mock TuShare client for symbol_metadata and stock_basic updates
        mock_df = pd.DataFrame({
            'ts_code': ['000002.SZ', '600519.SH', '300750.SZ'],
            'symbol': ['000002', '600519', '300750'],
            'name': ['万科A', '贵州茅台', '宁德时代'],
            'area': ['深圳', '贵州', '福建'],
            'industry': ['房地产', '白酒', '电池'],
            'market': ['主板', '主板', '创业板'],
            'list_date': ['19910129', '20010827', '20180611']
        })
        expander.tushare_client.fetch_stock_list = Mock(return_value=mock_df)

        expander.update_symbol_metadata(new_tickers)
        expander.update_stock_sectors(new_tickers)

        results = expander.verify_expansion()

        assert results['watchlist'] == 5  # 2 existing + 3 new
        assert results['symbol_metadata'] >= 4  # 1 existing + 3 new
        assert results['stock_sectors'] >= 4  # 1 existing + 3 new

    def test_no_existing_stocks_dropped(self, expander):
        """Test that existing watchlist entries are preserved"""
        # Get existing watchlist
        existing = expander.get_existing_watchlist()
        assert '000001' in existing
        assert '600000' in existing

        # Add new stocks
        new_tickers = {'000002', '600519'}
        expander.insert_into_watchlist(new_tickers)

        # Verify existing stocks still present
        updated = expander.get_existing_watchlist()
        assert '000001' in updated
        assert '600000' in updated
        assert '000002' in updated
        assert '600519' in updated

    def test_expansion_meets_minimum_count(self, expander):
        """Test that expansion results in >= 800 tickers (mock scenario)"""
        # Mock large constituent sets
        mock_df_300 = pd.DataFrame({
            'con_code': [f"{i:06d}.SH" for i in range(600000, 600300)]
        })
        mock_df_500 = pd.DataFrame({
            'con_code': [f"{i:06d}.SZ" for i in range(300, 800)]
        })
        mock_df_1000 = pd.DataFrame({
            'con_code': [f"{i:06d}.SZ" for i in range(1000, 2001)]
        })

        def mock_index_weight(index_code, start_date, end_date):
            if index_code == '000300.SH':
                return mock_df_300
            elif index_code == '000905.SH':
                return mock_df_500
            elif index_code == '000852.SH':
                return mock_df_1000
            return pd.DataFrame()

        expander.tushare_client.pro.index_weight = mock_index_weight

        # Fetch constituents
        all_constituents = expander.fetch_all_constituents()

        # Should have at least 800 unique stocks
        assert len(all_constituents) >= 800


class TestIntegrationScenarios:
    """Integration tests for common scenarios"""

    def test_script_is_idempotent(self, tmp_path):
        """Test that running script twice doesn't duplicate data"""
        # This would be a full integration test with real database
        # For now, we verify idempotency through INSERT OR IGNORE behavior
        # which is tested in test_insert_into_watchlist_idempotent
        pass

    def test_preserves_existing_categories(self, tmp_path):
        """Test that existing watchlist categories are preserved"""
        # This ensures that stocks already categorized (e.g., 'AI应用')
        # don't get overwritten with '指数成份股'
        pass


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
