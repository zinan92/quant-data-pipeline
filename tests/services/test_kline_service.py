"""
Unit tests for KlineService

Tests business logic layer using mocked repositories.
"""

import pytest
from unittest.mock import Mock, MagicMock
from datetime import datetime

from src.models import Kline, KlineTimeframe, SymbolType
from src.repositories.kline_repository import KlineRepository
from src.repositories.symbol_repository import SymbolRepository
from src.services.kline_service import KlineService
from src.utils.indicators import calculate_macd


class TestCalculateMacd:
    """Test MACD calculation function"""

    def test_calculate_macd_basic(self):
        """Test basic MACD calculation"""
        # Generate simple price data
        prices = [10.0 + i * 0.1 for i in range(30)]  # Upward trend

        result = calculate_macd(prices)

        assert "dif" in result
        assert "dea" in result
        assert "macd" in result
        assert len(result["dif"]) == 30
        assert len(result["dea"]) == 30
        assert len(result["macd"]) == 30

    def test_calculate_macd_insufficient_data(self):
        """Test MACD with insufficient data"""
        prices = [10.0, 10.1, 10.2]  # Only 3 data points

        result = calculate_macd(prices, slow_period=26)

        # Should return None values
        assert all(v is None for v in result["dif"])
        assert all(v is None for v in result["dea"])
        assert all(v is None for v in result["macd"])

    def test_calculate_macd_custom_periods(self):
        """Test MACD with custom periods"""
        prices = [10.0 + i * 0.1 for i in range(50)]

        result = calculate_macd(
            prices,
            fast_period=5,
            slow_period=10,
            signal_period=5,
        )

        assert len(result["dif"]) == 50
        # Values should not all be None with sufficient data
        assert not all(v is None for v in result["dif"])


class TestKlineServiceGetKlines:
    """Test get_klines method"""

    def test_get_klines_basic(self):
        """Test basic K-line retrieval"""
        # Mock repository
        mock_repo = Mock(spec=KlineRepository)
        mock_klines = [
            Kline(
                symbol_code="000001.SH",
                symbol_type=SymbolType.INDEX,
                timeframe=KlineTimeframe.DAY,
                trade_time="2024-01-01",
                open=3000.0,
                high=3100.0,
                low=2950.0,
                close=3050.0,
                volume=1000000.0,
                amount=5000000.0,
            ),
            Kline(
                symbol_code="000001.SH",
                symbol_type=SymbolType.INDEX,
                timeframe=KlineTimeframe.DAY,
                trade_time="2024-01-02",
                open=3050.0,
                high=3150.0,
                low=3000.0,
                close=3100.0,
                volume=1200000.0,
                amount=6000000.0,
            ),
        ]
        mock_repo.find_by_symbol.return_value = mock_klines

        service = KlineService(kline_repo=mock_repo)

        result = service.get_klines(
            symbol_type=SymbolType.INDEX,
            symbol_code="000001.SH",
            timeframe=KlineTimeframe.DAY,
            limit=10,
        )

        # Verify repository was called
        mock_repo.find_by_symbol.assert_called_once()

        # Verify result format
        assert len(result) == 2
        assert result[0]["datetime"] == "2024-01-02"  # Reversed order (oldest first)
        assert result[0]["close"] == 3100.0
        assert result[1]["datetime"] == "2024-01-01"
        assert result[1]["close"] == 3050.0

    def test_get_klines_with_date_range(self):
        """Test K-line retrieval with date range"""
        mock_repo = Mock(spec=KlineRepository)
        mock_klines = [
            Kline(
                symbol_code="000001.SH",
                symbol_type=SymbolType.INDEX,
                timeframe=KlineTimeframe.DAY,
                trade_time="2024-01-01",
                open=3000.0,
                high=3100.0,
                low=2950.0,
                close=3050.0,
                volume=1000000.0,
                amount=5000000.0,
            ),
        ]
        mock_repo.find_by_symbol_and_date_range.return_value = mock_klines

        service = KlineService(kline_repo=mock_repo)

        result = service.get_klines(
            symbol_type=SymbolType.INDEX,
            symbol_code="000001.SH",
            timeframe=KlineTimeframe.DAY,
            limit=10,
            start_date="2024-01-01",
            end_date="2024-01-05",
        )

        # Should call date range method
        mock_repo.find_by_symbol_and_date_range.assert_called_once()
        mock_repo.find_by_symbol.assert_not_called()

        assert len(result) == 1
        assert result[0]["datetime"] == "2024-01-01"


class TestKlineServiceWithIndicators:
    """Test get_klines_with_indicators method"""

    def test_get_klines_with_macd(self):
        """Test K-lines with MACD indicators"""
        mock_repo = Mock(spec=KlineRepository)

        # Generate enough data for MACD calculation
        mock_klines = []
        for i in range(30):
            mock_klines.append(
                Kline(
                    symbol_code="000001.SH",
                    symbol_type=SymbolType.INDEX,
                    timeframe=KlineTimeframe.DAY,
                    trade_time=f"2024-01-{i+1:02d}",
                    open=3000.0 + i * 10,
                    high=3100.0 + i * 10,
                    low=2950.0 + i * 10,
                    close=3050.0 + i * 10,
                    volume=1000000.0,
                    amount=5000000.0,
                )
            )

        mock_repo.find_by_symbol.return_value = mock_klines

        service = KlineService(kline_repo=mock_repo)

        result = service.get_klines_with_indicators(
            symbol_type=SymbolType.INDEX,
            symbol_code="000001.SH",
            timeframe=KlineTimeframe.DAY,
            limit=30,
            include_macd=True,
        )

        assert len(result) == 30

        # Check that MACD indicators are included
        assert "dif" in result[0]
        assert "dea" in result[0]
        assert "macd" in result[0]

        # Values should be numbers (not None) for most data points
        non_none_dif = [k["dif"] for k in result if k["dif"] is not None]
        assert len(non_none_dif) > 0

    def test_get_klines_with_indicators_no_macd(self):
        """Test K-lines without MACD indicators"""
        mock_repo = Mock(spec=KlineRepository)
        mock_klines = [
            Kline(
                symbol_code="000001.SH",
                symbol_type=SymbolType.INDEX,
                timeframe=KlineTimeframe.DAY,
                trade_time="2024-01-01",
                open=3000.0,
                high=3100.0,
                low=2950.0,
                close=3050.0,
                volume=1000000.0,
                amount=5000000.0,
            ),
        ]
        mock_repo.find_by_symbol.return_value = mock_klines

        service = KlineService(kline_repo=mock_repo)

        result = service.get_klines_with_indicators(
            symbol_type=SymbolType.INDEX,
            symbol_code="000001.SH",
            timeframe=KlineTimeframe.DAY,
            limit=10,
            include_macd=False,
        )

        assert len(result) == 1
        # Should not have MACD fields
        assert "dif" not in result[0]


class TestKlineServiceMetadata:
    """Test get_klines_with_meta method"""

    def test_get_klines_with_meta(self):
        """Test K-lines with metadata"""
        mock_kline_repo = Mock(spec=KlineRepository)
        mock_symbol_repo = Mock(spec=SymbolRepository)

        # Setup mock K-lines
        mock_klines = [
            Kline(
                symbol_code="000001.SH",
                symbol_name="上证指数",
                symbol_type=SymbolType.INDEX,
                timeframe=KlineTimeframe.DAY,
                trade_time="2024-01-01",
                open=3000.0,
                high=3100.0,
                low=2950.0,
                close=3050.0,
                volume=1000000.0,
                amount=5000000.0,
            ),
        ]
        mock_kline_repo.find_by_symbol.return_value = mock_klines

        service = KlineService(
            kline_repo=mock_kline_repo,
            symbol_repo=mock_symbol_repo,
        )

        result = service.get_klines_with_meta(
            symbol_type=SymbolType.INDEX,
            symbol_code="000001.SH",
            timeframe=KlineTimeframe.DAY,
            limit=10,
            include_indicators=False,
        )

        # Verify metadata structure
        assert result["symbol_type"] == "index"
        assert result["symbol_code"] == "000001.SH"
        assert result["symbol_name"] == "上证指数"
        assert result["timeframe"] == "day"
        assert result["count"] == 1
        assert len(result["klines"]) == 1


class TestKlineServiceLatest:
    """Test get_latest_kline method"""

    def test_get_latest_kline(self):
        """Test getting latest K-line"""
        mock_repo = Mock(spec=KlineRepository)
        mock_kline = Kline(
            symbol_code="000001.SH",
            symbol_type=SymbolType.INDEX,
            timeframe=KlineTimeframe.DAY,
            trade_time="2024-01-05",
            open=3200.0,
            high=3250.0,
            low=3150.0,
            close=3230.0,
            volume=1500000.0,
            amount=7500000.0,
        )
        mock_repo.find_latest_by_symbol.return_value = mock_kline

        service = KlineService(kline_repo=mock_repo)

        result = service.get_latest_kline(
            symbol_type=SymbolType.INDEX,
            symbol_code="000001.SH",
            timeframe=KlineTimeframe.DAY,
        )

        assert result is not None
        assert result["datetime"] == "2024-01-05"
        assert result["close"] == 3230.0

    def test_get_latest_kline_none(self):
        """Test getting latest when no data exists"""
        mock_repo = Mock(spec=KlineRepository)
        mock_repo.find_latest_by_symbol.return_value = None

        service = KlineService(kline_repo=mock_repo)

        result = service.get_latest_kline(
            symbol_type=SymbolType.INDEX,
            symbol_code="NONEXISTENT",
            timeframe=KlineTimeframe.DAY,
        )

        assert result is None


class TestKlineServiceTradeTime:
    """Test get_latest_trade_time method"""

    def test_get_latest_trade_time(self):
        """Test getting latest trade time"""
        mock_repo = Mock(spec=KlineRepository)
        mock_kline = Kline(
            symbol_code="000001.SH",
            symbol_type=SymbolType.INDEX,
            timeframe=KlineTimeframe.DAY,
            trade_time="2024-01-05",
            open=3200.0,
            high=3250.0,
            low=3150.0,
            close=3230.0,
            volume=1500000.0,
            amount=7500000.0,
        )
        mock_repo.find_latest_by_symbol.return_value = mock_kline

        service = KlineService(kline_repo=mock_repo)

        result = service.get_latest_trade_time(
            symbol_type=SymbolType.INDEX,
            symbol_code="000001.SH",
            timeframe=KlineTimeframe.DAY,
        )

        assert result == "2024-01-05"

    def test_get_latest_trade_time_none(self):
        """Test getting latest trade time when no data"""
        mock_repo = Mock(spec=KlineRepository)
        mock_repo.find_latest_by_symbol.return_value = None

        service = KlineService(kline_repo=mock_repo)

        result = service.get_latest_trade_time(
            symbol_type=SymbolType.INDEX,
            symbol_code="NONEXISTENT",
            timeframe=KlineTimeframe.DAY,
        )

        assert result is None


class TestKlineServiceCount:
    """Test get_klines_count method"""

    def test_get_klines_count(self):
        """Test counting K-lines"""
        mock_repo = Mock(spec=KlineRepository)
        mock_repo.count_by_symbol.return_value = 243

        service = KlineService(kline_repo=mock_repo)

        count = service.get_klines_count(
            symbol_type=SymbolType.INDEX,
            symbol_code="000001.SH",
            timeframe=KlineTimeframe.DAY,
        )

        assert count == 243
        mock_repo.count_by_symbol.assert_called_once()


class TestKlineServiceSymbolList:
    """Test get_symbols_with_kline_data method"""

    def test_get_symbols_with_kline_data(self):
        """Test getting symbols that have K-line data"""
        mock_repo = Mock(spec=KlineRepository)
        mock_repo.find_symbols_with_data.return_value = [
            "000001.SH",
            "000300.SH",
            "399001.SZ",
        ]

        service = KlineService(kline_repo=mock_repo)

        symbols = service.get_symbols_with_kline_data(
            symbol_type=SymbolType.INDEX,
            timeframe=KlineTimeframe.DAY,
        )

        assert len(symbols) == 3
        assert "000001.SH" in symbols
        mock_repo.find_symbols_with_data.assert_called_once()
