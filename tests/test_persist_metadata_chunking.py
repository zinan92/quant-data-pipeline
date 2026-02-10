"""Regression test for _persist_metadata with >999 tickers (SQLite limit)."""

from datetime import datetime, timezone

import pandas as pd
import pytest


def test_persist_metadata_handles_large_ticker_list(db_session):
    """
    Regression test: bulk_upsert_from_dataframe should handle >999 tickers.

    Without chunking, SQLite raises: sqlite3.OperationalError: too many SQL variables
    """
    from src.models import SymbolMetadata
    from src.repositories.symbol_repository import SymbolRepository

    symbol_repo = SymbolRepository(db_session)

    # Create 1500 test metadata records to exceed SQLite's 999-parameter limit
    now = datetime.now(timezone.utc)
    records = []
    for i in range(1500):
        ticker = f"{800000 + i:06d}"
        records.append({
            'ticker': ticker,
            'name': f"测试股票{i}",
            'total_mv': 1000.0 + i,
            'circ_mv': 800.0 + i,
            'pe_ttm': 10.0 + (i % 50),
            'pb': 1.5 + (i % 10) * 0.1,
            'list_date': "20000101",
            'industry_lv1': "测试大批量元数据",
            'industry_lv2': None,
            'industry_lv3': None,
            'concepts': [],
            'last_sync': now
        })

    metadata_df = pd.DataFrame(records)

    # This should NOT raise sqlite3.OperationalError
    symbol_repo.bulk_upsert_from_dataframe(metadata_df, {})
    db_session.commit()

    # Verify all records were inserted
    count = db_session.query(SymbolMetadata).filter(
        SymbolMetadata.industry_lv1 == "测试大批量元数据"
    ).count()

    assert count == 1500, f"Expected 1500 records, got {count}"


def test_persist_metadata_updates_existing_records(db_session):
    """Test that bulk_upsert_from_dataframe correctly updates existing records in chunks."""
    from src.models import SymbolMetadata
    from src.repositories.symbol_repository import SymbolRepository

    symbol_repo = SymbolRepository(db_session)

    # Create initial records
    now = datetime.now(timezone.utc)
    initial_records = [
        SymbolMetadata(
            ticker="999001",
            name="初始名称1",
            total_mv=1000.0,
            circ_mv=800.0,
            pe_ttm=10.0,
            pb=1.5,
            list_date="20000101",
            industry_lv1="初始行业",
            industry_lv2=None,
            industry_lv3=None,
            concepts=[],
            last_sync=now
        ),
        SymbolMetadata(
            ticker="999002",
            name="初始名称2",
            total_mv=2000.0,
            circ_mv=1600.0,
            pe_ttm=20.0,
            pb=2.5,
            list_date="20000101",
            industry_lv1="初始行业",
            industry_lv2=None,
            industry_lv3=None,
            concepts=[],
            last_sync=now
        )
    ]
    db_session.add_all(initial_records)
    db_session.commit()

    # Update with new data
    updated_data = pd.DataFrame([
        {
            'ticker': '999001',
            'name': '更新名称1',
            'total_mv': 1500.0,
            'circ_mv': 1200.0,
            'pe_ttm': 15.0,
            'pb': 2.0,
            'list_date': '20000101',
            'industry_lv1': '更新行业',
            'industry_lv2': None,
            'industry_lv3': None,
            'concepts': [],
            'last_sync': now
        },
        {
            'ticker': '999002',
            'name': '更新名称2',
            'total_mv': 2500.0,
            'circ_mv': 2000.0,
            'pe_ttm': 25.0,
            'pb': 3.0,
            'list_date': '20000101',
            'industry_lv1': '更新行业',
            'industry_lv2': None,
            'industry_lv3': None,
            'concepts': [],
            'last_sync': now
        }
    ])

    symbol_repo.bulk_upsert_from_dataframe(updated_data, {})
    db_session.commit()

    # Refresh session to get updated data
    db_session.expire_all()

    # Verify updates
    record1 = db_session.get(SymbolMetadata, "999001")
    record2 = db_session.get(SymbolMetadata, "999002")

    assert record1.name == "更新名称1"
    assert record1.total_mv == 1500.0

    assert record2.name == "更新名称2"
    assert record2.total_mv == 2500.0
