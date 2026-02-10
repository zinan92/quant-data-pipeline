"""
Unit tests for MarketDataService (src/services/data_pipeline.py)

Tests metadata refresh, symbol listing, and last-refresh-time queries
using an in-memory SQLite database and a mocked TushareDataProvider.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.models import SymbolMetadata
from src.repositories.symbol_repository import SymbolRepository
from src.services.data_pipeline import MarketDataService


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _make_service(db_session) -> tuple[MarketDataService, MagicMock]:
    """Create a MarketDataService with a real repo and mocked provider."""
    symbol_repo = SymbolRepository(db_session)
    mock_provider = MagicMock()
    service = MarketDataService(
        symbol_repo=symbol_repo,
        provider=mock_provider,
    )
    return service, mock_provider


def _insert_symbol(db_session, ticker: str, name: str, total_mv: float,
                   last_sync: datetime | None = None) -> SymbolMetadata:
    """Insert a SymbolMetadata row and return it."""
    sym = SymbolMetadata(
        ticker=ticker,
        name=name,
        total_mv=total_mv,
        last_sync=last_sync or datetime.now(timezone.utc),
    )
    db_session.add(sym)
    db_session.commit()
    return sym


# ------------------------------------------------------------------ #
# Tests: list_symbols
# ------------------------------------------------------------------ #

class TestListSymbols:

    def test_list_symbols_empty(self, db_session):
        """Returns an empty list when the database has no symbols."""
        service, _ = _make_service(db_session)

        result = service.list_symbols()

        assert result == []

    def test_list_symbols_with_data(self, db_session):
        """Returns SymbolMeta objects for every row in the database."""
        db_session.add(
            SymbolMetadata(ticker="600519", name="贵州茅台", total_mv=20000.0, concepts=[])
        )
        db_session.add(
            SymbolMetadata(ticker="000858", name="五粮液", total_mv=10000.0, concepts=[])
        )
        db_session.commit()

        service, _ = _make_service(db_session)
        result = service.list_symbols()

        assert len(result) == 2
        # Ordered by total_mv descending
        assert result[0].ticker == "600519"
        assert result[0].name == "贵州茅台"
        assert result[0].total_mv == 20000.0
        assert result[1].ticker == "000858"
        assert result[1].name == "五粮液"


# ------------------------------------------------------------------ #
# Tests: last_refresh_time
# ------------------------------------------------------------------ #

class TestLastRefreshTime:

    def test_last_refresh_time_none(self, db_session):
        """Returns None when the database is empty."""
        service, _ = _make_service(db_session)

        result = service.last_refresh_time()

        assert result is None

    def test_last_refresh_time_with_data(self, db_session):
        """Returns the most recent last_sync value across all rows."""
        earlier = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        later = datetime(2025, 6, 15, 12, 30, 0, tzinfo=timezone.utc)

        _insert_symbol(db_session, "600519", "贵州茅台", 20000.0, last_sync=earlier)
        _insert_symbol(db_session, "000858", "五粮液", 10000.0, last_sync=later)

        service, _ = _make_service(db_session)
        result = service.last_refresh_time()

        assert result is not None
        # SQLite may not preserve timezone, so compare naive components
        assert result.year == 2025
        assert result.month == 6
        assert result.day == 15
        assert result.hour == 12
        assert result.minute == 30


# ------------------------------------------------------------------ #
# Tests: refresh_metadata
# ------------------------------------------------------------------ #

class TestRefreshMetadata:

    def test_refresh_metadata_with_mock(self, db_session):
        """Provider returns a DataFrame; bulk_upsert_from_dataframe is called."""
        service, mock_provider = _make_service(db_session)

        fake_df = pd.DataFrame([
            {"ticker": "600519", "name": "贵州茅台", "total_mv": 20000.0},
            {"ticker": "000858", "name": "五粮液", "total_mv": 10000.0},
        ])
        mock_provider.fetch_symbol_metadata.return_value = fake_df

        # Spy on the real repo method
        original_bulk_upsert = service.symbol_repo.bulk_upsert_from_dataframe
        service.symbol_repo.bulk_upsert_from_dataframe = MagicMock(
            side_effect=original_bulk_upsert,
        )

        service.refresh_metadata(["600519", "000858"])

        mock_provider.fetch_symbol_metadata.assert_called_once()
        service.symbol_repo.bulk_upsert_from_dataframe.assert_called_once()

        # Verify the DataFrame and super_category_map were passed
        call_args = service.symbol_repo.bulk_upsert_from_dataframe.call_args
        passed_df = call_args[0][0]
        assert len(passed_df) == 2
        assert list(passed_df["ticker"]) == ["600519", "000858"]

    def test_refresh_metadata_empty_tickers(self, db_session):
        """Calling with an empty ticker list does nothing."""
        service, mock_provider = _make_service(db_session)

        service.refresh_metadata([])

        mock_provider.fetch_symbol_metadata.assert_not_called()

    def test_refresh_metadata_fetch_failure(self, db_session):
        """When the provider raises an exception, the service handles it
        gracefully and does not crash."""
        service, mock_provider = _make_service(db_session)

        mock_provider.fetch_symbol_metadata.side_effect = RuntimeError(
            "API rate limit exceeded"
        )

        # Should NOT raise
        service.refresh_metadata(["600519"])

        mock_provider.fetch_symbol_metadata.assert_called_once()

        # Database should remain empty (no data persisted)
        assert service.list_symbols() == []
