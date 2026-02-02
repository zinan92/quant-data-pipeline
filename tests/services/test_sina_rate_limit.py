"""
Tests for SinaKlineProvider rate-limit handling and StockUpdater circuit breaker.
"""

import asyncio
import time
from unittest.mock import MagicMock, patch, PropertyMock

import pandas as pd
import pytest
import requests

from src.services.sina_kline_provider import SinaKlineProvider, RATE_LIMIT_CODES


# ---------------------------------------------------------------------------
# SinaKlineProvider — unit tests
# ---------------------------------------------------------------------------

class TestSinaRateLimit:
    """Test rate-limit detection & exponential backoff in SinaKlineProvider."""

    def _make_provider(self, **kw):
        """Create a provider with 0 delay for fast tests."""
        defaults = dict(delay=0, max_consecutive_failures=5,
                        backoff_base=0.01, backoff_max=0.05)
        defaults.update(kw)
        return SinaKlineProvider(**defaults)

    # -- fetch_kline rate-limit detection --

    @patch("src.services.sina_kline_provider.time.sleep")
    def test_456_increments_failures(self, mock_sleep):
        """HTTP 456 should increment consecutive_failures and return None."""
        provider = self._make_provider()
        resp = MagicMock()
        resp.status_code = 456
        provider.session.get = MagicMock(return_value=resp)

        result = provider.fetch_kline("000001")
        assert result is None
        assert provider.consecutive_failures == 1
        assert provider.rate_limited is True

    @patch("src.services.sina_kline_provider.time.sleep")
    def test_429_increments_failures(self, mock_sleep):
        """HTTP 429 should also be treated as rate-limit."""
        provider = self._make_provider()
        resp = MagicMock()
        resp.status_code = 429
        provider.session.get = MagicMock(return_value=resp)

        result = provider.fetch_kline("000001")
        assert result is None
        assert provider.consecutive_failures == 1
        assert provider.rate_limited is True

    @patch("src.services.sina_kline_provider.time.sleep")
    def test_success_resets_failures(self, mock_sleep):
        """A successful response should reset the failure counter."""
        provider = self._make_provider()
        provider._consecutive_failures = 3

        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = [
            {"day": "2026-01-01 10:00:00", "open": "10", "high": "11",
             "low": "9", "close": "10.5", "volume": "1000"}
        ]
        provider.session.get = MagicMock(return_value=resp)

        result = provider.fetch_kline("000001")
        assert result is not None
        assert provider.consecutive_failures == 0
        assert provider.rate_limited is False

    @patch("src.services.sina_kline_provider.time.sleep")
    def test_request_exception_increments_failures(self, mock_sleep):
        """Network errors should also increment consecutive failures."""
        provider = self._make_provider()
        provider.session.get = MagicMock(
            side_effect=requests.exceptions.ConnectionError("conn refused")
        )

        result = provider.fetch_kline("000001")
        assert result is None
        assert provider.consecutive_failures == 1

    # -- backoff --

    def test_backoff_sleep_is_called(self):
        """Backoff should sleep on rate-limit responses."""
        provider = self._make_provider(backoff_base=0.01, backoff_max=0.1)
        resp = MagicMock()
        resp.status_code = 456
        provider.session.get = MagicMock(return_value=resp)

        with patch("src.services.sina_kline_provider.time.sleep") as mock_sleep:
            provider.fetch_kline("000001")
            # _wait_for_rate_limit + _backoff_sleep → at least 1 call for backoff
            assert mock_sleep.call_count >= 1

    # -- fetch_batch circuit breaker --

    @patch("src.services.sina_kline_provider.time.sleep")
    def test_fetch_batch_aborts_on_consecutive_failures(self, mock_sleep):
        """fetch_batch should abort after max_consecutive_failures."""
        provider = self._make_provider(max_consecutive_failures=3)

        # Every request returns 456
        resp = MagicMock()
        resp.status_code = 456
        provider.session.get = MagicMock(return_value=resp)

        tickers = [f"{i:06d}" for i in range(20)]
        result = provider.fetch_batch(tickers, period="30m")

        assert result.empty
        # Should have stopped after 3 failures, not tried all 20
        assert provider.session.get.call_count == 3

    @patch("src.services.sina_kline_provider.time.sleep")
    def test_fetch_batch_resets_on_start(self, mock_sleep):
        """fetch_batch should reset state at the start of each batch."""
        provider = self._make_provider()
        provider._consecutive_failures = 99
        provider._rate_limited = True

        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = [
            {"day": "2026-01-01 10:00:00", "open": "10", "high": "11",
             "low": "9", "close": "10.5", "volume": "1000"}
        ]
        provider.session.get = MagicMock(return_value=resp)

        result = provider.fetch_batch(["000001"], period="30m")
        assert not result.empty
        assert provider.consecutive_failures == 0

    # -- reset --

    def test_reset_clears_state(self):
        provider = self._make_provider()
        provider._consecutive_failures = 10
        provider._rate_limited = True
        provider.reset()
        assert provider.consecutive_failures == 0
        assert provider.rate_limited is False


# ---------------------------------------------------------------------------
# StockUpdater — circuit breaker tests
# ---------------------------------------------------------------------------

class TestStockUpdaterCircuitBreaker:
    """Test that StockUpdater aborts on consecutive None results."""

    def _make_updater(self):
        """Create a StockUpdater with mocked repos."""
        from src.services.stock_updater import StockUpdater
        kline_repo = MagicMock()
        symbol_repo = MagicMock()
        return StockUpdater(kline_repo, symbol_repo)

    @patch("src.services.stock_updater.CIRCUIT_BREAKER_THRESHOLD", 3)
    def test_sync_update_30m_aborts_on_consecutive_none(self):
        """_sync_update_30m should abort after CIRCUIT_BREAKER_THRESHOLD Nones."""
        updater = self._make_updater()

        mock_provider = MagicMock()
        mock_provider.fetch_kline.return_value = None
        mock_provider.consecutive_failures = 0
        mock_provider.max_consecutive_failures = 999  # don't trigger provider CB

        mock_service = MagicMock()

        tickers = [f"{i:06d}" for i in range(20)]
        result = updater._sync_update_30m(tickers, mock_provider, mock_service)

        assert result == 0
        # Should have stopped after 3 consecutive Nones
        assert mock_provider.fetch_kline.call_count == 3

    @patch("src.services.stock_updater.CIRCUIT_BREAKER_THRESHOLD", 10)
    def test_sync_update_30m_resets_on_success(self):
        """Successful fetch should reset the consecutive-none counter."""
        updater = self._make_updater()

        call_count = 0
        def side_effect(ticker, **kw):
            nonlocal call_count
            call_count += 1
            if call_count % 3 == 0:  # every 3rd call succeeds
                df = pd.DataFrame([{
                    "timestamp": pd.Timestamp("2026-01-01 10:00:00"),
                    "open": 10.0, "high": 11.0, "low": 9.0,
                    "close": 10.5, "volume": 1000, "ticker": ticker,
                }])
                return df
            return None

        mock_provider = MagicMock()
        mock_provider.fetch_kline.side_effect = side_effect
        mock_provider.consecutive_failures = 0
        mock_provider.max_consecutive_failures = 999

        mock_service = MagicMock()
        mock_service.save_klines.return_value = 1

        tickers = [f"{i:06d}" for i in range(12)]
        result = updater._sync_update_30m(tickers, mock_provider, mock_service)

        # All 12 should be attempted because successes reset the counter
        assert mock_provider.fetch_kline.call_count == 12

    def test_sync_update_30m_honours_provider_circuit_breaker(self):
        """Should also stop when provider.consecutive_failures is high."""
        updater = self._make_updater()

        mock_provider = MagicMock()
        mock_provider.fetch_kline.return_value = None
        mock_provider.consecutive_failures = 5
        mock_provider.max_consecutive_failures = 5

        mock_service = MagicMock()
        tickers = ["000001"]
        result = updater._sync_update_30m(tickers, mock_provider, mock_service)

        assert result == 0
        # Provider CB already tripped — should not even try
        assert mock_provider.fetch_kline.call_count == 0


class TestStockUpdaterAsync:
    """Test that async methods properly offload to threads."""

    @pytest.mark.asyncio
    async def test_update_watchlist_30m_calls_to_thread(self):
        """update_watchlist_30m should delegate to asyncio.to_thread."""
        from src.services.stock_updater import StockUpdater

        kline_repo = MagicMock()
        symbol_repo = MagicMock()
        kline_repo.session.query.return_value.all.return_value = [
            ("000001",), ("000002",)
        ]

        updater = StockUpdater(kline_repo, symbol_repo)

        # Patch asyncio.to_thread at the module where it's used
        async def fake_to_thread(fn, *args, **kwargs):
            return 0

        with patch("asyncio.to_thread", side_effect=fake_to_thread) as mock_tt, \
             patch("src.services.sina_kline_provider.SinaKlineProvider.__init__",
                   return_value=None), \
             patch("src.services.kline_service.KlineService.__init__",
                   return_value=None):
            result = await updater.update_watchlist_30m()
            mock_tt.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_single_calls_to_thread_for_sina(self):
        """update_single should use asyncio.to_thread for the Sina fetch."""
        from src.services.stock_updater import StockUpdater

        kline_repo = MagicMock()
        symbol_repo = MagicMock()
        updater = StockUpdater(kline_repo, symbol_repo)

        async def fake_to_thread(fn, *args, **kwargs):
            return None

        with patch("asyncio.to_thread", side_effect=fake_to_thread) as mock_tt, \
             patch("src.services.tushare_data_provider.TushareDataProvider") as MockTs, \
             patch("src.services.kline_service.KlineService.__init__",
                   return_value=None):
            MockTs.return_value.fetch_candles.return_value = None
            result = await updater.update_single("000001")
            mock_tt.assert_called_once()
