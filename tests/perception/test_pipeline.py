"""Integration tests for the Perception Pipeline.

Tests the full flow:  sources → events → detectors → aggregator → report.
All external HTTP calls and DB access are mocked.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.perception.aggregator import AggregationReport, SignalAggregator
from src.perception.detectors.anomaly_detector import AnomalyDetector
from src.perception.detectors.flow_detector import FlowDetector
from src.perception.detectors.keyword_detector import KeywordDetector
from src.perception.detectors.price_detector import PriceDetector
from src.perception.detectors.technical_detector import TechnicalDetector
from src.perception.detectors.volume_detector import VolumeDetector
from src.perception.events import EventSource, EventType, MarketScope, RawMarketEvent
from src.perception.health import HealthStatus
from src.perception.pipeline import (
    PerceptionPipeline,
    PipelineConfig,
    ScanResult,
)
from src.perception.signals import Direction, Market, SignalType, UnifiedSignal
from src.perception.sources.alert_source import AlertSource, _parse_alert_items
from src.perception.sources.ashare_source import AShareSource, _parse_alert_item, _parse_timestamp
from src.perception.sources.base import SourceType
from src.perception.sources.market_data_source import MarketDataSource
from src.perception.sources.news_source import NewsSource


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def sample_news_response() -> List[Dict[str, Any]]:
    """Simulated /api/news/latest response."""
    return [
        {
            "title": "DeepSeek发布新一代大模型 AI领域迎来重大突破",
            "content": "DeepSeek今日发布了新一代人工智能大模型",
            "datetime": "2026-02-01 10:30:00",
            "source": "财联社",
            "url": "https://example.com/news/1",
        },
        {
            "title": "半导体行业景气度持续提升 芯片板块走强",
            "content": "受全球半导体需求回暖影响，A股芯片板块今日大涨",
            "datetime": "2026-02-01 10:00:00",
            "source": "财联社",
        },
        {
            "title": "央行宣布降准50个基点 释放流动性",
            "content": "中国人民银行决定下调金融机构存款准备金率0.5个百分点",
            "datetime": "2026-02-01 09:30:00",
            "source": "新华社",
        },
        {
            "title": "某公司发布2025年报 业绩符合预期",
            "content": "年度营收同比增长10%，利润率稳定",
            "datetime": "2026-02-01 09:00:00",
            "source": "巨潮资讯",
        },
    ]


@pytest.fixture
def sample_alert_response() -> List[Dict[str, Any]]:
    """Simulated /api/news/market-alerts response."""
    return [
        {
            "title": "封涨停板",
            "content": "某科技股封涨停板",
            "symbol": "000001",
            "datetime": "2026-02-01 10:15:00",
            "type": "涨停",
            "count": 15,
        },
        {
            "title": "大笔买入",
            "content": "主力大笔买入",
            "symbol": "600519",
            "datetime": "2026-02-01 10:20:00",
            "amount": 10_000_000,
        },
        {
            "title": "大笔卖出",
            "content": "大笔卖出信号",
            "symbol": "000858",
            "datetime": "2026-02-01 10:25:00",
            "amount": 8_000_000,
        },
        {
            "title": "封跌停板",
            "content": "某地产股封跌停板",
            "symbol": "001979",
            "datetime": "2026-02-01 10:30:00",
            "type": "跌停",
            "count": 5,
        },
    ]


@pytest.fixture
def sample_index_response() -> Dict[str, Any]:
    """Simulated /api/index/realtime/000001.SH response."""
    return {
        "price": 3250.50,
        "close": 3250.50,
        "open": 3240.00,
        "high": 3260.00,
        "low": 3235.00,
        "change_pct": 0.85,
        "volume": 325000000000,
        "amount": 4500000000000,
        "datetime": "2026-02-01 15:00:00",
    }


@pytest.fixture
def temp_db() -> str:
    """Create a temporary SQLite DB with watchlist and klines data."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    conn = sqlite3.connect(db_path)

    # Create watchlist table
    conn.execute("""
        CREATE TABLE watchlist (
            id INTEGER PRIMARY KEY,
            ticker VARCHAR(16) NOT NULL UNIQUE,
            added_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            purchase_price FLOAT,
            purchase_date DATETIME,
            shares FLOAT,
            category VARCHAR(64),
            is_focus INTEGER NOT NULL DEFAULT 0
        )
    """)

    # Insert some tickers
    conn.execute(
        "INSERT INTO watchlist (ticker, category, is_focus) VALUES (?, ?, ?)",
        ("600519", "白酒", 1),
    )
    conn.execute(
        "INSERT INTO watchlist (ticker, category, is_focus) VALUES (?, ?, ?)",
        ("000661", "创新药", 0),
    )

    # Create klines table
    conn.execute("""
        CREATE TABLE klines (
            id INTEGER PRIMARY KEY,
            symbol_type VARCHAR(7) NOT NULL DEFAULT 'stock',
            symbol_code VARCHAR(16) NOT NULL,
            symbol_name VARCHAR(64),
            timeframe VARCHAR(7) NOT NULL DEFAULT 'daily',
            trade_time VARCHAR(32) NOT NULL,
            open FLOAT NOT NULL,
            high FLOAT NOT NULL,
            low FLOAT NOT NULL,
            close FLOAT NOT NULL,
            volume FLOAT NOT NULL,
            amount FLOAT NOT NULL,
            dif FLOAT,
            dea FLOAT,
            macd FLOAT,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (symbol_type, symbol_code, timeframe, trade_time)
        )
    """)

    # Insert kline data for 600519 — 30 bars
    base_price = 1800.0
    for i in range(30):
        day = f"2026-01-{i+1:02d}"
        o = base_price + i * 2
        h = o + 10
        lo = o - 5
        c = o + 5
        vol = 10000 + i * 500
        amt = c * vol
        conn.execute(
            """INSERT INTO klines
               (symbol_type, symbol_code, timeframe, trade_time,
                open, high, low, close, volume, amount)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("stock", "600519", "daily", day, o, h, lo, c, vol, amt),
        )

    conn.commit()
    conn.close()
    return db_path


def _mock_httpx_response(data: Any, status_code: int = 200) -> httpx.Response:
    """Create a mock httpx.Response."""
    resp = httpx.Response(
        status_code=status_code,
        json=data,
        request=httpx.Request("GET", "http://test"),
    )
    return resp


# ── AShareSource Tests ───────────────────────────────────────────────


class TestAShareSource:
    """Tests for the low-level AShareSource."""

    @pytest.mark.asyncio
    async def test_connect_disconnect(self):
        src = AShareSource()
        await src.connect()
        assert src._connected
        await src.disconnect()
        assert not src._connected

    @pytest.mark.asyncio
    async def test_health_unknown_before_poll(self):
        src = AShareSource()
        h = src.health()
        assert h.status == HealthStatus.UNKNOWN

    @pytest.mark.asyncio
    async def test_health_healthy_after_success(self, sample_news_response, sample_alert_response, sample_index_response):
        src = AShareSource()
        await src.connect()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock()

        def side_effect(url, **kwargs):
            if "news/latest" in url:
                return _mock_httpx_response(sample_news_response)
            elif "market-alerts" in url:
                return _mock_httpx_response(sample_alert_response)
            elif "index/realtime" in url:
                return _mock_httpx_response(sample_index_response)
            return _mock_httpx_response([])

        mock_client.get.side_effect = side_effect
        src._client = mock_client

        events = await src.poll()
        assert len(events) > 0

        h = src.health()
        assert h.status == HealthStatus.HEALTHY
        assert h.total_events > 0

        await src.disconnect()

    def test_parse_timestamp_valid(self):
        dt = _parse_timestamp("2026-02-01 10:30:00")
        assert dt.year == 2026
        assert dt.month == 2
        assert dt.hour == 10

    def test_parse_timestamp_fallback(self):
        dt = _parse_timestamp(None)
        assert isinstance(dt, datetime)

    def test_parse_alert_item_limit_up(self):
        item = {"title": "封涨停板", "content": "某股票涨停", "count": 10}
        etype, data = _parse_alert_item(item)
        assert etype == EventType.LIMIT_EVENT
        assert data["limit_type"] == "limit_up"

    def test_parse_alert_item_large_buy(self):
        item = {"title": "大笔买入", "content": "主力大单买入", "amount": 5000000}
        etype, data = _parse_alert_item(item)
        assert etype == EventType.ANOMALY
        assert data["order_side"] == "buy"

    def test_parse_alert_item_large_sell(self):
        item = {"title": "大笔卖出", "content": "大单卖出", "amount": 3000000}
        etype, data = _parse_alert_item(item)
        assert etype == EventType.ANOMALY
        assert data["order_side"] == "sell"

    def test_parse_alert_item_limit_down(self):
        item = {"title": "封跌停板", "content": "跌停", "count": 8}
        etype, data = _parse_alert_item(item)
        assert etype == EventType.LIMIT_EVENT
        assert data["limit_type"] == "limit_down"


# ── NewsSource Tests ─────────────────────────────────────────────────


class TestNewsSource:
    """Tests for NewsSource — fetch + keyword detection."""

    @pytest.mark.asyncio
    async def test_poll_returns_events(self, sample_news_response):
        src = NewsSource()
        await src.connect()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            return_value=_mock_httpx_response(sample_news_response)
        )
        src._client = mock_client

        events = await src.poll()
        assert len(events) == 4
        assert all(e.event_type == EventType.NEWS for e in events)

        await src.disconnect()

    @pytest.mark.asyncio
    async def test_detect_signals_finds_keywords(self, sample_news_response):
        src = NewsSource()
        await src.connect()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            return_value=_mock_httpx_response(sample_news_response)
        )
        src._client = mock_client

        signals = await src.detect_signals()
        # Should find: DeepSeek/大模型/人工智能, 半导体/芯片, 央行/降准
        assert len(signals) >= 3

        # Verify signal types
        for sig in signals:
            assert sig.signal_type == SignalType.SENTIMENT
            assert sig.strength > 0
            assert sig.confidence > 0

        await src.disconnect()

    @pytest.mark.asyncio
    async def test_health_after_poll(self, sample_news_response):
        src = NewsSource()
        await src.connect()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            return_value=_mock_httpx_response(sample_news_response)
        )
        src._client = mock_client

        await src.poll()
        h = src.health()
        assert h.status == HealthStatus.HEALTHY
        assert h.total_polls == 1
        assert h.total_events == 4

        await src.disconnect()

    @pytest.mark.asyncio
    async def test_error_handling(self):
        src = NewsSource()
        await src.connect()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        src._client = mock_client

        with pytest.raises(httpx.ConnectError):
            await src.poll()

        h = src.health()
        assert h.consecutive_failures == 1

        await src.disconnect()

    def test_name_and_type(self):
        src = NewsSource()
        assert src.name == "news"
        assert src.source_type == SourceType.POLLING


# ── AlertSource Tests ────────────────────────────────────────────────


class TestAlertSource:
    """Tests for AlertSource — fetch + anomaly/flow detection."""

    @pytest.mark.asyncio
    async def test_poll_returns_events(self, sample_alert_response):
        src = AlertSource()
        await src.connect()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            return_value=_mock_httpx_response(sample_alert_response)
        )
        src._client = mock_client

        events = await src.poll()
        assert len(events) == 4

        # Check event types are classified correctly
        etypes = [e.event_type for e in events]
        # 涨停 → LIMIT_EVENT, 大笔买入 → ANOMALY, 大笔卖出 → ANOMALY, 跌停 → LIMIT_EVENT
        assert etypes.count(EventType.LIMIT_EVENT) == 2
        assert etypes.count(EventType.ANOMALY) == 2

        await src.disconnect()

    @pytest.mark.asyncio
    async def test_detect_signals(self, sample_alert_response):
        # Configure anomaly detector with low thresholds so our test data triggers
        anomaly = AnomalyDetector(config={
            "large_order_amount_threshold": 1_000_000,
            "limit_up_count_threshold": 5,
            "limit_down_count_threshold": 3,
        })
        src = AlertSource(anomaly_detector=anomaly)
        await src.connect()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            return_value=_mock_httpx_response(sample_alert_response)
        )
        src._client = mock_client

        signals = await src.detect_signals()
        # Should detect limit_up wave (count=15 > threshold=5)
        # and large orders (amount > 1M)
        assert len(signals) >= 1

        await src.disconnect()

    def test_parse_alert_items_classification(self):
        items = [
            {"title": "封涨停板", "content": "涨停", "count": 10},
            {"title": "大笔买入", "content": "大单", "amount": 5000000},
            {"title": "封跌停板", "content": "跌停", "count": 5},
        ]
        events = _parse_alert_items(items)
        assert len(events) == 3
        assert events[0].event_type == EventType.LIMIT_EVENT
        assert events[0].data["limit_type"] == "limit_up"
        assert events[1].event_type == EventType.ANOMALY
        assert events[1].data["order_side"] == "buy"
        assert events[2].event_type == EventType.LIMIT_EVENT
        assert events[2].data["limit_type"] == "limit_down"

    def test_name_and_type(self):
        src = AlertSource()
        assert src.name == "alerts"
        assert src.source_type == SourceType.POLLING


# ── MarketDataSource Tests ───────────────────────────────────────────


class TestMarketDataSource:
    """Tests for MarketDataSource — index API + DB access."""

    @pytest.fixture
    def _patch_session(self, temp_db):
        """Patch SessionLocal so MarketDataSource reads from the temp DB."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        engine = create_engine(
            f"sqlite:///{temp_db}",
            connect_args={"check_same_thread": False},
        )
        TestSession = sessionmaker(bind=engine)
        with patch("src.database.SessionLocal", TestSession):
            yield

    @pytest.mark.asyncio
    async def test_poll_with_db(self, temp_db, _patch_session, sample_index_response):
        src = MarketDataSource(db_path=temp_db)
        await src.connect()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            return_value=_mock_httpx_response(sample_index_response)
        )
        src._client = mock_client

        events = await src.poll()
        # 4 indexes + 2 watchlist tickers (600519 has klines, 000661 has none)
        # 600519 has 30 kline bars → 1 KLINE event
        assert len(events) >= 4  # at least the indexes

        # Check that we have a KLINE event for 600519
        kline_events = [e for e in events if e.event_type == EventType.KLINE]
        assert len(kline_events) >= 1
        kline_600519 = [e for e in kline_events if e.symbol == "600519"]
        assert len(kline_600519) == 1
        assert len(kline_600519[0].data["bars"]) == 30

        await src.disconnect()

    def test_get_watchlist(self, temp_db, _patch_session):
        src = MarketDataSource(db_path=temp_db)
        wl = src.get_watchlist()
        assert len(wl) == 2
        tickers = [w["ticker"] for w in wl]
        assert "600519" in tickers
        assert "000661" in tickers

    def test_get_klines(self, temp_db, _patch_session):
        src = MarketDataSource(db_path=temp_db)
        bars = src.get_klines("600519")
        assert len(bars) == 30
        assert "open" in bars[0]
        assert "close" in bars[0]
        assert "volume" in bars[0]

    def test_get_klines_missing_symbol(self, temp_db, _patch_session):
        src = MarketDataSource(db_path=temp_db)
        bars = src.get_klines("999999")
        assert bars == []

    def test_get_watchlist_missing_db(self):
        """When SessionLocal fails, get_watchlist raises OperationalError."""
        from sqlalchemy import create_engine
        from sqlalchemy.exc import OperationalError
        from sqlalchemy.orm import sessionmaker

        engine = create_engine("sqlite:///nonexistent_dir/missing.db")
        FailSession = sessionmaker(bind=engine)
        with patch("src.database.SessionLocal", FailSession):
            src = MarketDataSource(db_path="/nonexistent/path.db")
            with pytest.raises(OperationalError):
                src.get_watchlist()

    def test_name_and_type(self):
        src = MarketDataSource()
        assert src.name == "market_data"
        assert src.source_type == SourceType.POLLING


# ── Pipeline Tests ───────────────────────────────────────────────────


class TestPerceptionPipeline:
    """Integration tests for the full pipeline."""

    @pytest.mark.asyncio
    async def test_start_stop(self):
        """Pipeline starts and stops cleanly."""
        config = PipelineConfig(api_base_url="http://127.0.0.1:9999")
        pipeline = PerceptionPipeline(config=config)

        await pipeline.start()
        assert pipeline.is_running

        await pipeline.stop()
        assert not pipeline.is_running

    @pytest.mark.asyncio
    async def test_scan_with_mock_sources(self):
        """Full scan cycle with mocked sources."""
        now = datetime.now(timezone.utc)

        # Create mock sources
        mock_news = AsyncMock(spec=NewsSource)
        mock_news.name = "news"
        mock_news.source_type = SourceType.POLLING
        mock_news.connect = AsyncMock()
        mock_news.disconnect = AsyncMock()
        mock_news.health.return_value = MagicMock(
            status=HealthStatus.HEALTHY,
            latency_ms=50.0,
            total_events=10,
            consecutive_failures=0,
            total_polls=1,
        )
        mock_news.poll.return_value = [
            RawMarketEvent(
                source=EventSource.CLS,
                event_type=EventType.NEWS,
                market=MarketScope.CN_STOCK,
                data={"title": "DeepSeek发布新模型 人工智能大模型突破"},
                timestamp=now,
            ),
        ]

        mock_market = AsyncMock(spec=MarketDataSource)
        mock_market.name = "market_data"
        mock_market.source_type = SourceType.POLLING
        mock_market.connect = AsyncMock()
        mock_market.disconnect = AsyncMock()
        mock_market.health.return_value = MagicMock(
            status=HealthStatus.HEALTHY,
            latency_ms=100.0,
            total_events=5,
            consecutive_failures=0,
            total_polls=1,
        )
        mock_market.poll.return_value = []

        mock_alerts = AsyncMock(spec=AlertSource)
        mock_alerts.name = "alerts"
        mock_alerts.source_type = SourceType.POLLING
        mock_alerts.connect = AsyncMock()
        mock_alerts.disconnect = AsyncMock()
        mock_alerts.health.return_value = MagicMock(
            status=HealthStatus.HEALTHY,
            latency_ms=30.0,
            total_events=3,
            consecutive_failures=0,
            total_polls=1,
        )
        mock_alerts.poll.return_value = [
            RawMarketEvent(
                source=EventSource.CLS,
                event_type=EventType.LIMIT_EVENT,
                market=MarketScope.CN_STOCK,
                symbol="MARKET",
                data={"limit_up_count": 20, "limit_down_count": 2},
                timestamp=now,
            ),
        ]

        pipeline = PerceptionPipeline(
            sources=[mock_news, mock_market, mock_alerts],
        )
        await pipeline.start()

        result = await pipeline.scan()

        assert isinstance(result, ScanResult)
        assert result.events_fetched == 2  # 1 news + 1 alert
        assert result.signals_detected >= 1  # at least the keyword match
        assert result.report is not None
        assert isinstance(result.report, AggregationReport)
        assert result.duration_ms > 0

        # Health should be reported
        assert "news" in result.source_health
        assert "alerts" in result.source_health

        await pipeline.stop()

    @pytest.mark.asyncio
    async def test_scan_result_serialization(self):
        """ScanResult.to_dict() produces valid JSON."""
        now = datetime.now(timezone.utc)

        health_obj = MagicMock(
            status=HealthStatus.UNKNOWN,
            latency_ms=None,
            total_events=0,
            consecutive_failures=0,
            total_polls=0,
        )

        mock_source = AsyncMock()
        mock_source.name = "test"
        mock_source.source_type = SourceType.POLLING
        mock_source.connect = AsyncMock()
        mock_source.disconnect = AsyncMock()
        mock_source.poll.return_value = []
        mock_source.health = MagicMock(return_value=health_obj)

        pipeline = PerceptionPipeline(sources=[mock_source])
        await pipeline.start()

        result = await pipeline.scan()
        d = result.to_dict()

        # Should be JSON-serializable
        json_str = json.dumps(d)
        assert json_str
        assert "timestamp" in d
        assert "report" in d
        assert "source_health" in d

        await pipeline.stop()

    @pytest.mark.asyncio
    async def test_get_current_signals_empty(self):
        """No signals when nothing scanned yet."""
        pipeline = PerceptionPipeline(sources=[])
        signals = pipeline.get_current_signals()
        assert signals == []

    @pytest.mark.asyncio
    async def test_get_health(self):
        """Health report structure is correct."""
        pipeline = PerceptionPipeline(sources=[])
        health = pipeline.get_health()

        assert "pipeline" in health
        assert "sources" in health
        assert health["pipeline"]["running"] is False
        assert health["pipeline"]["scan_count"] == 0

    @pytest.mark.asyncio
    async def test_scan_count_increments(self):
        """Scan count goes up with each scan."""
        mock_source = AsyncMock()
        mock_source.name = "test"
        mock_source.source_type = SourceType.POLLING
        mock_source.connect = AsyncMock()
        mock_source.disconnect = AsyncMock()
        mock_source.poll.return_value = []
        mock_source.health.return_value = MagicMock(
            status=HealthStatus.UNKNOWN,
            latency_ms=None,
            total_events=0,
            consecutive_failures=0,
            total_polls=0,
        )

        pipeline = PerceptionPipeline(sources=[mock_source])
        await pipeline.start()

        assert pipeline.scan_count == 0
        await pipeline.scan()
        assert pipeline.scan_count == 1
        await pipeline.scan()
        assert pipeline.scan_count == 2

        await pipeline.stop()

    @pytest.mark.asyncio
    async def test_source_error_doesnt_crash_pipeline(self):
        """A failing source doesn't prevent other sources from being polled."""
        now = datetime.now(timezone.utc)

        good_source = AsyncMock()
        good_source.name = "good"
        good_source.source_type = SourceType.POLLING
        good_source.connect = AsyncMock()
        good_source.disconnect = AsyncMock()
        good_source.poll.return_value = [
            RawMarketEvent(
                source=EventSource.CLS,
                event_type=EventType.NEWS,
                market=MarketScope.CN_STOCK,
                data={"title": "正常新闻"},
                timestamp=now,
            ),
        ]
        good_source.health.return_value = MagicMock(
            status=HealthStatus.HEALTHY,
            latency_ms=50.0,
            total_events=1,
            consecutive_failures=0,
            total_polls=1,
        )

        bad_source = AsyncMock()
        bad_source.name = "bad"
        bad_source.source_type = SourceType.POLLING
        bad_source.connect = AsyncMock()
        bad_source.disconnect = AsyncMock()
        bad_source.poll.side_effect = Exception("Connection refused")
        bad_source.health.return_value = MagicMock(
            status=HealthStatus.UNHEALTHY,
            latency_ms=None,
            total_events=0,
            consecutive_failures=5,
            total_polls=1,
        )

        pipeline = PerceptionPipeline(sources=[good_source, bad_source])
        await pipeline.start()

        result = await pipeline.scan()

        # Should still get events from the good source
        assert result.events_fetched == 1
        assert len(result.errors) == 1
        assert "bad" in result.errors[0]

        await pipeline.stop()

    @pytest.mark.asyncio
    async def test_custom_detectors(self):
        """Pipeline works with custom detector list."""
        pipeline = PerceptionPipeline(
            sources=[],
            detectors=[KeywordDetector()],
        )
        assert len(pipeline._detectors) == 1

    @pytest.mark.asyncio
    async def test_custom_aggregator(self):
        """Pipeline works with custom aggregator."""
        agg = SignalAggregator()
        pipeline = PerceptionPipeline(
            sources=[],
            aggregator=agg,
        )
        assert pipeline._aggregator is agg

    @pytest.mark.asyncio
    async def test_route_map_built_correctly(self):
        """Detector routing map covers expected event types."""
        pipeline = PerceptionPipeline(sources=[])
        rm = pipeline._route_map

        # KeywordDetector accepts NEWS
        assert any(
            d.name == "keyword"
            for d in rm.get("news", [])
        )

        # AnomalyDetector accepts ANOMALY, PRICE_UPDATE, LIMIT_EVENT
        assert any(
            d.name == "anomaly"
            for d in rm.get("anomaly", [])
        )

        # PriceDetector accepts KLINE, PRICE_UPDATE
        assert any(
            d.name == "price"
            for d in rm.get("kline", [])
        )

    @pytest.mark.asyncio
    async def test_full_pipeline_with_news_keyword_detection(self):
        """End-to-end: news event → keyword detector → aggregator → report."""
        now = datetime.now(timezone.utc)

        mock_source = AsyncMock()
        mock_source.name = "news"
        mock_source.source_type = SourceType.POLLING
        mock_source.connect = AsyncMock()
        mock_source.disconnect = AsyncMock()
        mock_source.health.return_value = MagicMock(
            status=HealthStatus.HEALTHY,
            latency_ms=10.0,
            total_events=1,
            consecutive_failures=0,
            total_polls=1,
        )
        mock_source.poll.return_value = [
            RawMarketEvent(
                source=EventSource.CLS,
                event_type=EventType.NEWS,
                market=MarketScope.CN_STOCK,
                data={
                    "title": "OpenAI发布GPT-5 人工智能进入新纪元",
                    "content": "AI大模型再次突破",
                },
                timestamp=now,
            ),
        ]

        pipeline = PerceptionPipeline(
            sources=[mock_source],
            detectors=[KeywordDetector()],
        )
        await pipeline.start()

        result = await pipeline.scan()

        assert result.events_fetched == 1
        assert result.signals_detected >= 1  # OpenAI + 人工智能 + 大模型

        # Check the report has signals
        report = result.report
        assert report.total_signals >= 1

        await pipeline.stop()

    @pytest.mark.asyncio
    async def test_last_result_stored(self):
        """Pipeline stores last scan result."""
        mock_source = AsyncMock()
        mock_source.name = "test"
        mock_source.source_type = SourceType.POLLING
        mock_source.connect = AsyncMock()
        mock_source.disconnect = AsyncMock()
        mock_source.poll.return_value = []
        mock_source.health.return_value = MagicMock(
            status=HealthStatus.UNKNOWN,
            latency_ms=None,
            total_events=0,
            consecutive_failures=0,
            total_polls=0,
        )

        pipeline = PerceptionPipeline(sources=[mock_source])
        assert pipeline.last_result is None

        await pipeline.start()
        await pipeline.scan()
        assert pipeline.last_result is not None

        await pipeline.stop()


# ── API Route Tests ──────────────────────────────────────────────────


class TestPerceptionRoutes:
    """Tests for the FastAPI perception endpoints."""

    @pytest.mark.asyncio
    async def test_routes_importable(self):
        """Routes module imports cleanly."""
        from src.api.routes_perception import router, set_pipeline, trigger_scan, get_signals, get_health
        assert router is not None

    @pytest.mark.asyncio
    async def test_set_pipeline(self):
        """Can inject a custom pipeline."""
        from src.api import routes_perception

        pipeline = PerceptionPipeline(sources=[])
        routes_perception.set_pipeline(pipeline)
        assert routes_perception._pipeline is pipeline

        # Clean up
        routes_perception._pipeline = None


# ── Edge Cases ───────────────────────────────────────────────────────


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_empty_news_response(self):
        """NewsSource handles empty response."""
        src = NewsSource()
        await src.connect()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_httpx_response([]))
        src._client = mock_client

        events = await src.poll()
        assert events == []

        await src.disconnect()

    @pytest.mark.asyncio
    async def test_malformed_news_item(self):
        """NewsSource handles items with missing fields."""
        src = NewsSource()
        await src.connect()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            return_value=_mock_httpx_response([{"title": "Test"}])
        )
        src._client = mock_client

        events = await src.poll()
        assert len(events) == 1
        assert events[0].data["title"] == "Test"

        await src.disconnect()

    @pytest.mark.asyncio
    async def test_nested_response_format(self):
        """NewsSource handles {"data": [...]} response format."""
        src = NewsSource()
        await src.connect()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            return_value=_mock_httpx_response(
                {"data": [{"title": "Nested news about AI"}]}
            )
        )
        src._client = mock_client

        events = await src.poll()
        assert len(events) == 1

        await src.disconnect()

    @pytest.mark.asyncio
    async def test_alert_source_nested_response(self):
        """AlertSource handles {"alerts": [...]} format."""
        src = AlertSource()
        await src.connect()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            return_value=_mock_httpx_response(
                {"alerts": [{"title": "大笔买入", "content": "大单", "amount": 5000000}]}
            )
        )
        src._client = mock_client

        events = await src.poll()
        assert len(events) == 1

        await src.disconnect()

    def test_pipeline_config_defaults(self):
        """PipelineConfig has sensible defaults."""
        cfg = PipelineConfig()
        assert cfg.api_base_url == "http://127.0.0.1:8000"
        assert cfg.scan_interval_seconds == 60.0
        assert cfg.news_limit == 50

    @pytest.mark.asyncio
    async def test_pipeline_default_sources_and_detectors(self):
        """Default pipeline creates 3 sources and 6 detectors."""
        pipeline = PerceptionPipeline()
        assert len(pipeline._sources) == 3
        assert len(pipeline._detectors) == 6

        # Clean up
        await pipeline.stop()
