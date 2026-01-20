"""Integration tests for /api/symbols/industries endpoint."""

from datetime import datetime, timezone, timedelta

import pytest
from fastapi.testclient import TestClient


def test_industries_endpoint_returns_data():
    """Test that the industries endpoint returns valid data structure."""
    from src.main import app
    from src.database import SessionLocal
    from src.models import SymbolMetadata, Candle, Timeframe

    # Seed test data
    session = SessionLocal()
    try:
        # Clean up any existing test data
        session.query(Candle).filter(Candle.ticker.in_(["000001", "000002"])).delete()
        session.query(SymbolMetadata).filter(SymbolMetadata.ticker.in_(["000001", "000002"])).delete()
        session.commit()

        # Create test stocks in the same industry
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)

        stock1 = SymbolMetadata(
            ticker="000001",
            name="平安银行",
            industry_lv1="银行",
            industry_lv2=None,
            industry_lv3=None,
            total_mv=10000.0,
            circ_mv=8000.0,
            pe_ttm=5.0,
            pb=1.0,
            list_date="20000101",
            concepts=[],
            last_sync=now
        )
        stock2 = SymbolMetadata(
            ticker="000002",
            name="万科A",
            industry_lv1="房地产",
            industry_lv2=None,
            industry_lv3=None,
            total_mv=20000.0,
            circ_mv=15000.0,
            pe_ttm=10.0,
            pb=2.0,
            list_date="20000101",
            concepts=[],
            last_sync=now
        )
        session.add_all([stock1, stock2])

        # Create candles for change calculation
        # Stock 1: went from 10.0 to 11.0 (+10%)
        candles1 = [
            Candle(
                ticker="000001",
                timeframe=Timeframe.DAY,
                timestamp=yesterday,
                open=10.0,
                high=10.5,
                low=9.5,
                close=10.0,
                volume=1000.0,
                ma5=10.0,
                ma10=10.0,
                ma20=10.0,
                ma50=10.0
            ),
            Candle(
                ticker="000001",
                timeframe=Timeframe.DAY,
                timestamp=now,
                open=10.0,
                high=11.5,
                low=10.0,
                close=11.0,
                volume=1500.0,
                ma5=10.5,
                ma10=10.5,
                ma20=10.5,
                ma50=10.5
            )
        ]

        # Stock 2: went from 20.0 to 19.0 (-5%)
        candles2 = [
            Candle(
                ticker="000002",
                timeframe=Timeframe.DAY,
                timestamp=yesterday,
                open=20.0,
                high=20.5,
                low=19.5,
                close=20.0,
                volume=2000.0,
                ma5=20.0,
                ma10=20.0,
                ma20=20.0,
                ma50=20.0
            ),
            Candle(
                ticker="000002",
                timeframe=Timeframe.DAY,
                timestamp=now,
                open=20.0,
                high=20.5,
                low=18.5,
                close=19.0,
                volume=2500.0,
                ma5=19.5,
                ma10=19.5,
                ma20=19.5,
                ma50=19.5
            )
        ]

        session.add_all(candles1 + candles2)
        session.commit()

    finally:
        session.close()

    # Test the endpoint
    client = TestClient(app)
    response = client.get("/api/symbols/industries")

    assert response.status_code == 200
    industries = response.json()

    # Verify structure
    assert isinstance(industries, list)
    assert len(industries) >= 2  # At least our 2 test industries

    # Find our test industries
    bank_industry = next((i for i in industries if i["板块名称"] == "银行"), None)
    realestate_industry = next((i for i in industries if i["板块名称"] == "房地产"), None)

    assert bank_industry is not None
    assert realestate_industry is not None

    # Verify bank industry data (may have more stocks if DB has existing data)
    assert bank_industry["股票数量"] >= 1  # At least our test stock
    assert bank_industry["总市值"] >= 10000.0  # Includes our test stock
    assert "涨跌幅" in bank_industry
    assert "上涨家数" in bank_industry
    assert "下跌家数" in bank_industry
    assert bank_industry["行业PE"] is not None  # Should have a PE value

    # Verify real estate industry data (may have more stocks if DB has existing data)
    assert realestate_industry["股票数量"] >= 1  # At least our test stock
    assert realestate_industry["总市值"] >= 20000.0  # Includes our test stock
    assert "涨跌幅" in realestate_industry
    assert "上涨家数" in realestate_industry
    assert "下跌家数" in realestate_industry
    assert realestate_industry["行业PE"] is not None  # Should have a PE value


def test_industries_endpoint_handles_large_ticker_list():
    """Test that the endpoint handles >999 tickers (SQLite parameter limit)."""
    from src.main import app
    from src.database import SessionLocal
    from src.models import SymbolMetadata

    session = SessionLocal()
    try:
        # Clean up existing test data
        session.query(SymbolMetadata).filter(
            SymbolMetadata.industry_lv1 == "测试行业大量"
        ).delete()
        session.commit()

        # Create 1500 test stocks to exceed SQLite's 999-parameter limit
        # Use ticker range 900000-901499 to avoid conflicts with real data
        now = datetime.now(timezone.utc)
        records = []
        for i in range(1500):
            ticker = f"{900000 + i:06d}"
            records.append({
                'ticker': ticker,
                'name': f"测试股票{i}",
                'industry_lv1': "测试行业大量",
                'industry_lv2': None,
                'industry_lv3': None,
                'total_mv': 1000.0,
                'circ_mv': 800.0,
                'pe_ttm': 10.0,
                'pb': 1.5,
                'list_date': "20000101",
                'concepts': [],
                'last_sync': now
            })

        session.bulk_insert_mappings(SymbolMetadata, records)
        session.commit()

    finally:
        session.close()

    # Test the endpoint - should not crash with sqlite3.OperationalError
    client = TestClient(app)
    response = client.get("/api/symbols/industries")

    assert response.status_code == 200
    industries = response.json()
    assert isinstance(industries, list)

    # Verify our test industry exists
    test_industry = next((i for i in industries if i["板块名称"] == "测试行业大量"), None)
    assert test_industry is not None
    assert test_industry["股票数量"] == 1500

    # Clean up after test
    session = SessionLocal()
    try:
        session.query(SymbolMetadata).filter(
            SymbolMetadata.industry_lv1 == "测试行业大量"
        ).delete()
        session.commit()
    finally:
        session.close()


def test_industries_endpoint_response_structure():
    """Test that all required fields are present in response."""
    from src.main import app

    client = TestClient(app)
    response = client.get("/api/symbols/industries")

    assert response.status_code == 200
    industries = response.json()

    if len(industries) > 0:
        industry = industries[0]

        # Verify all required fields exist
        required_fields = [
            "板块名称",
            "股票数量",
            "总市值",
            "涨跌幅",
            "上涨家数",
            "下跌家数",
            "行业PE"
        ]

        for field in required_fields:
            assert field in industry, f"Missing required field: {field}"
