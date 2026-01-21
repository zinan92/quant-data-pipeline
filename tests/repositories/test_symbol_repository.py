"""
Unit tests for SymbolRepository

Tests symbol metadata access methods.
"""

import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database import Base
from src.models import SymbolMetadata
from src.repositories.symbol_repository import SymbolRepository


@pytest.fixture(scope="function")
def db_session():
    """Create a fresh in-memory database for each test"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    yield session

    session.close()


@pytest.fixture
def sample_symbols():
    """Generate sample symbol metadata for testing"""
    now = datetime.now()
    return [
        SymbolMetadata(
            ticker="000001",
            name="平安银行",
            total_mv=500000.0,
            circ_mv=450000.0,
            pe_ttm=5.5,
            pb=0.8,
            list_date="19910403",
            industry_lv1="金融",
            industry_lv2="银行",
            industry_lv3="股份制银行",
            super_category="金融服务",
            concepts=["智慧金融", "数字货币"],
            last_sync=now,
        ),
        SymbolMetadata(
            ticker="600519",
            name="贵州茅台",
            total_mv=2500000.0,
            circ_mv=2500000.0,
            pe_ttm=35.0,
            pb=12.5,
            list_date="20010827",
            industry_lv1="消费",
            industry_lv2="食品饮料",
            industry_lv3="白酒",
            super_category="消费品",
            concepts=["白酒", "高端消费"],
            last_sync=now,
        ),
        SymbolMetadata(
            ticker="000858",
            name="五粮液",
            total_mv=800000.0,
            circ_mv=750000.0,
            pe_ttm=25.0,
            pb=8.0,
            list_date="19980527",
            industry_lv1="消费",
            industry_lv2="食品饮料",
            industry_lv3="白酒",
            super_category="消费品",
            concepts=["白酒", "国企改革"],
            last_sync=now,
        ),
    ]


class TestSymbolRepositoryBasicOperations:
    """Test basic CRUD operations"""

    def test_save_single_symbol(self, db_session):
        """Test saving a single symbol"""
        repo = SymbolRepository(db_session)
        now = datetime.now()

        symbol = SymbolMetadata(
            ticker="000001",
            name="平安银行",
            total_mv=500000.0,
            circ_mv=450000.0,
            pe_ttm=5.5,
            pb=0.8,
            last_sync=now,
        )

        saved = repo.save(symbol)
        repo.commit()

        assert saved.ticker == "000001"
        assert saved.name == "平安银行"

    def test_find_by_ticker(self, db_session, sample_symbols):
        """Test finding symbol by ticker"""
        repo = SymbolRepository(db_session)

        for symbol in sample_symbols:
            repo.save(symbol)
        repo.commit()

        found = repo.find_by_ticker("600519")

        assert found is not None
        assert found.name == "贵州茅台"
        assert found.total_mv == 2500000.0

    def test_count(self, db_session, sample_symbols):
        """Test counting all symbols"""
        repo = SymbolRepository(db_session)

        for symbol in sample_symbols:
            repo.save(symbol)
        repo.commit()

        count = repo.count()
        assert count == 3


class TestSymbolRepositoryQueries:
    """Test query methods"""

    def test_find_by_tickers_batch(self, db_session, sample_symbols):
        """Test batch querying by tickers"""
        repo = SymbolRepository(db_session)

        for symbol in sample_symbols:
            repo.save(symbol)
        repo.commit()

        symbols = repo.find_by_tickers(["000001", "600519"])

        assert len(symbols) == 2
        tickers = {s.ticker for s in symbols}
        assert tickers == {"000001", "600519"}

    def test_find_by_name(self, db_session, sample_symbols):
        """Test finding symbol by exact name"""
        repo = SymbolRepository(db_session)

        for symbol in sample_symbols:
            repo.save(symbol)
        repo.commit()

        found = repo.find_by_name("贵州茅台")

        assert found is not None
        assert found.ticker == "600519"

    def test_search_by_name(self, db_session, sample_symbols):
        """Test fuzzy search by name"""
        repo = SymbolRepository(db_session)

        for symbol in sample_symbols:
            repo.save(symbol)
        repo.commit()

        # Search for "茅台" should find "贵州茅台"
        results = repo.search_by_name("茅台")

        assert len(results) == 1
        assert results[0].name == "贵州茅台"

    def test_find_by_industry(self, db_session, sample_symbols):
        """Test finding symbols by industry"""
        repo = SymbolRepository(db_session)

        for symbol in sample_symbols:
            repo.save(symbol)
        repo.commit()

        # Find all 白酒 stocks
        symbols = repo.find_by_industry(
            industry_lv1="消费",
            industry_lv2="食品饮料",
        )

        assert len(symbols) == 2  # 茅台 and 五粮液
        names = {s.name for s in symbols}
        assert names == {"贵州茅台", "五粮液"}

    @pytest.mark.skip(reason="JSON array contains() not supported in SQLite - needs custom implementation")
    def test_find_by_concept(self, db_session, sample_symbols):
        """Test finding symbols by concept"""
        repo = SymbolRepository(db_session)

        for symbol in sample_symbols:
            repo.save(symbol)
        repo.commit()

        # Find stocks with "白酒" concept
        symbols = repo.find_by_concept("白酒")

        assert len(symbols) == 2
        names = {s.name for s in symbols}
        assert names == {"贵州茅台", "五粮液"}

    def test_find_by_market_value_range(self, db_session, sample_symbols):
        """Test finding symbols by market value range"""
        repo = SymbolRepository(db_session)

        for symbol in sample_symbols:
            repo.save(symbol)
        repo.commit()

        # Find stocks with market value > 1,000,000 (1 trillion)
        symbols = repo.find_by_market_value_range(min_mv=1000000.0)

        assert len(symbols) == 1
        assert symbols[0].name == "贵州茅台"

    def test_get_all_tickers(self, db_session, sample_symbols):
        """Test getting all ticker codes"""
        repo = SymbolRepository(db_session)

        for symbol in sample_symbols:
            repo.save(symbol)
        repo.commit()

        tickers = repo.get_all_tickers()

        assert len(tickers) == 3
        assert set(tickers) == {"000001", "600519", "000858"}


class TestSymbolRepositoryUpsert:
    """Test upsert operations"""

    def test_upsert_new_symbol(self, db_session):
        """Test upserting a new symbol"""
        repo = SymbolRepository(db_session)
        now = datetime.now()

        symbol = SymbolMetadata(
            ticker="000001",
            name="平安银行",
            total_mv=500000.0,
            circ_mv=450000.0,
            last_sync=now,
        )

        result = repo.upsert(symbol)
        repo.commit()

        assert result.ticker == "000001"
        assert result.name == "平安银行"

    def test_upsert_existing_symbol(self, db_session):
        """Test upserting an existing symbol (update)"""
        repo = SymbolRepository(db_session)
        now = datetime.now()

        # Insert initial data
        symbol = SymbolMetadata(
            ticker="000001",
            name="平安银行",
            total_mv=500000.0,
            circ_mv=450000.0,
            last_sync=now,
        )
        repo.upsert(symbol)
        repo.commit()

        # Update with new market value
        symbol.total_mv = 550000.0
        result = repo.upsert(symbol)
        repo.commit()

        # Should still have only 1 record
        count = repo.count()
        assert count == 1

        # Market value should be updated
        found = repo.find_by_ticker("000001")
        assert found.total_mv == 550000.0

    def test_upsert_batch(self, db_session, sample_symbols):
        """Test batch upsert"""
        repo = SymbolRepository(db_session)

        count = repo.upsert_batch(sample_symbols)
        repo.commit()

        assert count == 3

        # Verify all symbols were inserted
        all_symbols = repo.find_all()
        assert len(all_symbols) == 3


class TestSymbolRepositoryStatistics:
    """Test statistics methods"""

    def test_get_statistics(self, db_session, sample_symbols):
        """Test getting symbol statistics"""
        repo = SymbolRepository(db_session)

        for symbol in sample_symbols:
            repo.save(symbol)
        repo.commit()

        stats = repo.get_statistics()

        assert stats["total"] == 3


class TestSymbolRepositoryEdgeCases:
    """Test edge cases"""

    def test_find_by_ticker_not_found(self, db_session):
        """Test finding non-existent ticker"""
        repo = SymbolRepository(db_session)

        found = repo.find_by_ticker("NONEXISTENT")

        assert found is None

    def test_find_by_name_not_found(self, db_session):
        """Test finding non-existent name"""
        repo = SymbolRepository(db_session)

        found = repo.find_by_name("不存在的股票")

        assert found is None

    def test_search_by_name_no_results(self, db_session):
        """Test search with no results"""
        repo = SymbolRepository(db_session)

        results = repo.search_by_name("不存在")

        assert results == []

    def test_find_by_industry_no_results(self, db_session):
        """Test finding by industry with no results"""
        repo = SymbolRepository(db_session)

        symbols = repo.find_by_industry(
            industry_lv1="不存在的行业"
        )

        assert symbols == []

    def test_upsert_batch_empty_list(self, db_session):
        """Test upserting empty list"""
        repo = SymbolRepository(db_session)

        count = repo.upsert_batch([])

        assert count == 0
