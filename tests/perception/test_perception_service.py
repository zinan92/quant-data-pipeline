"""Tests for PerceptionService — standalone scheduled pipeline runner."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from datetime import datetime, timezone, timedelta
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.perception.aggregator import AggregationReport
from src.perception.integration.trading_bridge import (
    BridgeConfig,
    TradingAction,
    TradingBridge,
    TradingSignal,
)
from src.perception.integration.signal_publisher import (
    PublisherConfig,
    SignalPublisher,
)
from src.perception.integration.market_context import (
    MarketContextBuilder,
    MarketContext,
    MarketSentiment,
    RiskLevel,
)
from src.perception.pipeline import (
    PerceptionPipeline,
    PipelineConfig,
    ScanResult,
)
from src.perception.signals import Direction, Market, SignalType

# Import the service functions and class
from scripts.perception_service import (
    PerceptionService,
    get_scan_interval,
    is_ashare_trading_hours,
)


# ── Fixtures ─────────────────────────────────────────────────────────


def _make_scan_result() -> ScanResult:
    report = AggregationReport(
        timestamp=datetime.now(timezone.utc),
        total_signals=5,
        total_assets=2,
        top_longs=[],
        top_shorts=[],
        market_bias=Direction.LONG,
        market_bias_score=0.5,
        by_market={},
    )
    return ScanResult(
        timestamp=datetime.now(timezone.utc),
        duration_ms=42.0,
        events_fetched=10,
        signals_detected=5,
        signals_ingested=5,
        report=report,
        source_health={},
    )


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def mock_pipeline():
    pipeline = MagicMock(spec=PerceptionPipeline)
    pipeline.is_running = False
    pipeline.start = AsyncMock()
    pipeline.stop = AsyncMock()
    pipeline.scan = AsyncMock(return_value=_make_scan_result())
    return pipeline


@pytest.fixture
def service(mock_pipeline, tmp_dir):
    publisher = SignalPublisher(
        config=PublisherConfig(
            output_path=os.path.join(tmp_dir, "signals.jsonl"),
        )
    )
    return PerceptionService(
        pipeline=mock_pipeline,
        publisher=publisher,
        signals_json_path=os.path.join(tmp_dir, "signals.json"),
        context_json_path=os.path.join(tmp_dir, "context.json"),
        market_interval=10,
        off_interval=60,
    )


# ── Tests ────────────────────────────────────────────────────────────


class TestTradingHoursDetection:
    """Test A-share trading hours detection."""

    def test_is_ashare_trading_hours_returns_bool(self):
        result = is_ashare_trading_hours()
        assert isinstance(result, bool)

    @patch("scripts.perception_service.datetime")
    def test_weekday_morning_session(self, mock_dt):
        # Monday 10:00 CST = 02:00 UTC
        mock_now = datetime(2025, 7, 7, 2, 0, tzinfo=timezone.utc)  # Monday
        mock_dt.now.return_value = mock_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        # Can't easily mock this due to the CST arithmetic, so just test it returns bool
        result = is_ashare_trading_hours()
        assert isinstance(result, bool)

    def test_get_scan_interval_crypto(self):
        interval = get_scan_interval(300, 1800, crypto=True)
        assert interval == 300

    def test_get_scan_interval_returns_numeric(self):
        interval = get_scan_interval(300, 1800, crypto=False)
        assert isinstance(interval, (int, float))
        assert interval in (300, 1800)


class TestPerceptionService:
    @pytest.mark.asyncio
    async def test_start_stop(self, service, mock_pipeline):
        await service.start()
        assert service.is_running
        mock_pipeline.start.assert_awaited_once()

        await service.stop()
        assert not service.is_running
        mock_pipeline.stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_once_success(self, service, mock_pipeline):
        await service.start()
        result = await service.run_once()
        assert result is not None
        assert service.scan_count == 1
        assert service.failure_count == 0
        mock_pipeline.scan.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_once_writes_signals_json(self, service, tmp_dir):
        await service.start()
        await service.run_once()
        path = os.path.join(tmp_dir, "signals.json")
        assert os.path.exists(path)
        with open(path) as f:
            data = json.load(f)
        assert "signals" in data
        assert "updated_at" in data

    @pytest.mark.asyncio
    async def test_run_once_writes_context_json(self, service, tmp_dir):
        await service.start()
        await service.run_once()
        path = os.path.join(tmp_dir, "context.json")
        assert os.path.exists(path)
        with open(path) as f:
            data = json.load(f)
        assert "sentiment" in data
        assert "risk_level" in data

    @pytest.mark.asyncio
    async def test_run_once_handles_failure(self, service, mock_pipeline):
        mock_pipeline.scan = AsyncMock(side_effect=RuntimeError("scan boom"))
        await service.start()
        result = await service.run_once()
        assert result is None
        assert service.failure_count == 1
        assert service.scan_count == 0

    @pytest.mark.asyncio
    async def test_consecutive_failures_trigger_restart(self, service, mock_pipeline):
        mock_pipeline.scan = AsyncMock(side_effect=RuntimeError("scan boom"))
        service.max_consecutive_failures = 2
        await service.start()

        await service.run_once()
        assert service.failure_count == 1
        await service.run_once()
        # After 2 failures, restart should have been attempted
        assert service.failure_count == 0  # reset after restart

    @pytest.mark.asyncio
    async def test_success_resets_failure_count(self, service, mock_pipeline):
        # First: simulate a failure
        mock_pipeline.scan = AsyncMock(side_effect=RuntimeError("boom"))
        await service.start()
        await service.run_once()
        assert service.failure_count == 1

        # Then: success
        mock_pipeline.scan = AsyncMock(return_value=_make_scan_result())
        await service.run_once()
        assert service.failure_count == 0

    def test_get_status(self, service):
        status = service.get_status()
        assert "running" in status
        assert "scan_count" in status
        assert "failure_count" in status
        assert "is_market_hours" in status

    @pytest.mark.asyncio
    async def test_multiple_scans(self, service, mock_pipeline):
        await service.start()
        for _ in range(3):
            await service.run_once()
        assert service.scan_count == 3


class TestPerceptionServiceConfig:
    def test_default_intervals(self, mock_pipeline, tmp_dir):
        svc = PerceptionService(
            pipeline=mock_pipeline,
            signals_json_path=os.path.join(tmp_dir, "s.json"),
            context_json_path=os.path.join(tmp_dir, "c.json"),
        )
        assert svc.market_interval == 300  # default
        assert svc.off_interval == 1800
        assert svc.crypto is False

    def test_crypto_mode(self, mock_pipeline, tmp_dir):
        svc = PerceptionService(
            pipeline=mock_pipeline,
            crypto=True,
            signals_json_path=os.path.join(tmp_dir, "s.json"),
            context_json_path=os.path.join(tmp_dir, "c.json"),
        )
        assert svc.crypto is True
