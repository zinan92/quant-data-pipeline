"""Tests for Perception Layer Phase 1 — Core Interface Definitions.

Covers:
- RawMarketEvent model (validation, serialization, helpers)
- SourceHealth model (validation, constraints)
- HealthMonitor (record / snapshot lifecycle)
- DataSource ABC (interface contract, health delegation)
- Detector ABC (interface contract, can_handle routing)
- SourceRegistry (register, get, all, health_report, unregister)
- PerceptionConfig (defaults, overrides, helpers)
- UnifiedSignal (local copy sanity check)
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List

import pytest
from pydantic import ValidationError

from src.perception.config import (
    CircuitBreakerConfig,
    DetectorConfig,
    PerceptionConfig,
    SourcePollConfig,
)
from src.perception.detectors.base import Detector
from src.perception.events import EventSource, EventType, MarketScope, RawMarketEvent
from src.perception.health import HealthMonitor, HealthStatus, SourceHealth
from src.perception.signals import (
    AShareSignal,
    CryptoSignal,
    Direction,
    Market,
    SignalType,
    UnifiedSignal,
)
from src.perception.sources.base import DataSource, SourceType
from src.perception.sources.registry import SourceRegistry


# =====================================================================
#  Helpers — concrete implementations of ABCs for testing
# =====================================================================


class FakeDataSource(DataSource):
    """Minimal concrete DataSource for testing."""

    def __init__(
        self,
        name: str = "fake",
        source_type: SourceType = SourceType.REALTIME,
    ) -> None:
        super().__init__(name, source_type)
        self.connected = False
        self._events: List[RawMarketEvent] = []

    async def connect(self) -> None:
        self.connected = True

    async def poll(self) -> List[RawMarketEvent]:
        return list(self._events)

    async def disconnect(self) -> None:
        self.connected = False


class FakeDetector(Detector):
    """Minimal concrete Detector for testing."""

    def __init__(
        self,
        name: str = "fake_detector",
        accepts: List[str] | None = None,
    ) -> None:
        super().__init__(name, accepts or ["kline", "price_update"])
        self._signals: List[UnifiedSignal] = []

    async def detect(self, event: RawMarketEvent) -> List[UnifiedSignal]:
        if not self.can_handle(event):
            return []
        return list(self._signals)


def _make_event(**overrides) -> RawMarketEvent:
    """Factory for a valid RawMarketEvent with sensible defaults."""
    defaults = dict(
        source="tushare",
        event_type="kline",
        market="a_share",
        symbol="000001.SZ",
        data={"open": 10.5, "close": 11.0},
        timestamp=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    defaults.update(overrides)
    return RawMarketEvent(**defaults)


def _make_signal(**overrides) -> UnifiedSignal:
    """Factory for a valid UnifiedSignal with sensible defaults."""
    defaults = dict(
        market=Market.A_SHARE,
        asset="000001.SZ",
        direction=Direction.LONG,
        strength=0.8,
        confidence=0.7,
        signal_type=SignalType.TECHNICAL,
        source="test_detector",
    )
    defaults.update(overrides)
    return UnifiedSignal(**defaults)


# =====================================================================
#  RawMarketEvent
# =====================================================================


class TestRawMarketEvent:
    """RawMarketEvent model tests."""

    def test_create_minimal(self):
        """Event can be created with only required fields."""
        evt = _make_event()
        assert evt.event_id  # auto-generated
        assert evt.source == "tushare"
        assert evt.event_type == "kline"
        assert evt.market == "a_share"
        assert evt.symbol == "000001.SZ"
        assert evt.received_at is not None

    def test_auto_uuid(self):
        """Each event gets a unique event_id by default."""
        e1 = _make_event()
        e2 = _make_event()
        assert e1.event_id != e2.event_id

    def test_explicit_event_id(self):
        """Custom event_id is preserved."""
        eid = uuid.uuid4().hex
        evt = _make_event(event_id=eid)
        assert evt.event_id == eid

    def test_symbol_none_for_macro(self):
        """symbol=None is valid for macro events."""
        evt = _make_event(symbol=None, event_type="news")
        assert evt.symbol is None

    def test_received_at_auto(self):
        """received_at is auto-filled close to now."""
        before = datetime.now(timezone.utc)
        evt = _make_event()
        after = datetime.now(timezone.utc)
        assert before <= evt.received_at <= after

    def test_received_at_adjusted_if_before_timestamp(self):
        """received_at is nudged to timestamp if it precedes it."""
        ts = datetime.now(timezone.utc) + timedelta(hours=1)
        evt = RawMarketEvent(
            source="sina",
            event_type="price_update",
            market="a_share",
            symbol="600000.SH",
            data={},
            timestamp=ts,
            received_at=ts - timedelta(seconds=10),
        )
        assert evt.received_at >= evt.timestamp

    def test_serialization_roundtrip(self):
        """Event survives JSON roundtrip."""
        evt = _make_event()
        raw = evt.model_dump_json()
        restored = RawMarketEvent.model_validate_json(raw)
        assert restored.event_id == evt.event_id
        assert restored.source == evt.source
        assert restored.data == evt.data

    def test_dict_roundtrip(self):
        """Event survives dict roundtrip."""
        evt = _make_event()
        d = evt.model_dump()
        restored = RawMarketEvent.model_validate(d)
        assert restored == evt

    def test_matches_type(self):
        """matches_type helper filters correctly."""
        evt = _make_event(event_type="kline")
        assert evt.matches_type("kline", "news") is True
        assert evt.matches_type("news", "social") is False

    def test_age_seconds(self):
        """age_seconds returns a positive number."""
        evt = _make_event(
            timestamp=datetime.now(timezone.utc) - timedelta(seconds=5)
        )
        assert evt.age_seconds >= 0

    def test_source_enum_values(self):
        """EventSource enum contains expected members."""
        assert EventSource.TUSHARE == "tushare"
        assert EventSource.SINA == "sina"
        assert EventSource.AKSHARE == "akshare"

    def test_event_type_enum_values(self):
        """EventType enum contains expected members."""
        assert EventType.KLINE == "kline"
        assert EventType.NEWS == "news"
        assert EventType.BOARD == "board"

    def test_market_scope_enum_values(self):
        """MarketScope enum contains expected members."""
        assert MarketScope.A_SHARE == "a_share"
        assert MarketScope.US_STOCK == "us_stock"
        assert MarketScope.GLOBAL == "global"

    def test_validation_source_empty_rejected(self):
        """Empty source string is rejected."""
        with pytest.raises(ValidationError):
            _make_event(source="")

    def test_validation_event_type_empty_rejected(self):
        """Empty event_type string is rejected."""
        with pytest.raises(ValidationError):
            _make_event(event_type="")


# =====================================================================
#  SourceHealth
# =====================================================================


class TestSourceHealth:
    """SourceHealth model tests."""

    def test_create_defaults(self):
        """Defaults are sane."""
        h = SourceHealth(source_name="test")
        assert h.status == "healthy"
        assert h.latency_ms == 0.0
        assert h.error_rate == 0.0
        assert h.requests_total == 0
        assert h.requests_failed == 0

    def test_valid_statuses(self):
        """All HealthStatus values are accepted."""
        for status in HealthStatus:
            h = SourceHealth(source_name="x", status=status.value)
            assert h.status == status.value

    def test_invalid_status_rejected(self):
        """Unknown status string is rejected."""
        with pytest.raises(ValidationError):
            SourceHealth(source_name="x", status="exploded")

    def test_error_rate_bounds(self):
        """error_rate must be 0.0–1.0."""
        with pytest.raises(ValidationError):
            SourceHealth(source_name="x", error_rate=1.5)
        with pytest.raises(ValidationError):
            SourceHealth(source_name="x", error_rate=-0.1)

    def test_failed_gt_total_rejected(self):
        """requests_failed > requests_total is rejected."""
        with pytest.raises(ValidationError):
            SourceHealth(
                source_name="x", requests_total=5, requests_failed=10
            )

    def test_failed_eq_total_ok(self):
        """requests_failed == requests_total is fine (100% failure)."""
        h = SourceHealth(
            source_name="x",
            status="down",
            requests_total=3,
            requests_failed=3,
            error_rate=1.0,
        )
        assert h.requests_failed == h.requests_total

    def test_is_healthy_property(self):
        """is_healthy reflects status."""
        assert SourceHealth(source_name="a", status="healthy").is_healthy
        assert not SourceHealth(source_name="b", status="degraded").is_healthy

    def test_computed_error_rate(self):
        """computed_error_rate derives from counters."""
        h = SourceHealth(
            source_name="x",
            requests_total=100,
            requests_failed=25,
            error_rate=0.0,  # stored value ignored
        )
        assert h.computed_error_rate == pytest.approx(0.25)

    def test_computed_error_rate_zero_total(self):
        """computed_error_rate is 0 when no requests."""
        h = SourceHealth(source_name="x")
        assert h.computed_error_rate == 0.0

    def test_serialization_roundtrip(self):
        """SourceHealth survives JSON roundtrip."""
        h = SourceHealth(
            source_name="tushare",
            status="degraded",
            latency_ms=42.5,
            error_rate=0.15,
            last_success=datetime.now(timezone.utc),
            requests_total=100,
            requests_failed=15,
        )
        restored = SourceHealth.model_validate_json(h.model_dump_json())
        assert restored.source_name == h.source_name
        assert restored.latency_ms == h.latency_ms


# =====================================================================
#  HealthMonitor
# =====================================================================


class TestHealthMonitor:
    """HealthMonitor lifecycle tests."""

    def test_initial_snapshot_healthy(self):
        """Fresh monitor is healthy with zero counters."""
        m = HealthMonitor("src")
        snap = m.snapshot()
        assert snap.status == "healthy"
        assert snap.requests_total == 0

    def test_record_success(self):
        """Success increments total and sets latency."""
        m = HealthMonitor("src")
        m.record_success(latency_ms=12.3)
        snap = m.snapshot()
        assert snap.requests_total == 1
        assert snap.requests_failed == 0
        assert snap.latency_ms == 12.3
        assert snap.last_success is not None

    def test_record_failure(self):
        """Failure increments both total and failed."""
        m = HealthMonitor("src")
        m.record_failure("timeout", latency_ms=999)
        snap = m.snapshot()
        assert snap.requests_total == 1
        assert snap.requests_failed == 1
        assert snap.last_error == "timeout"

    def test_degraded_threshold(self):
        """10–50% error rate → degraded."""
        m = HealthMonitor("src")
        for _ in range(8):
            m.record_success()
        for _ in range(2):
            m.record_failure("err")
        snap = m.snapshot()
        assert snap.status == "degraded"

    def test_down_threshold(self):
        """≥50% error rate → down."""
        m = HealthMonitor("src")
        for _ in range(5):
            m.record_success()
        for _ in range(5):
            m.record_failure("err")
        snap = m.snapshot()
        assert snap.status == "down"

    def test_reset(self):
        """reset() clears all counters."""
        m = HealthMonitor("src")
        m.record_success()
        m.record_failure("x")
        m.reset()
        snap = m.snapshot()
        assert snap.requests_total == 0
        assert snap.requests_failed == 0
        assert snap.last_success is None
        assert snap.last_error is None


# =====================================================================
#  DataSource (ABC contract)
# =====================================================================


class TestDataSource:
    """DataSource interface contract tests."""

    def test_instantiation(self):
        """Concrete subclass can be instantiated."""
        src = FakeDataSource("test_src", SourceType.HISTORICAL)
        assert src.name == "test_src"
        assert src.source_type == SourceType.HISTORICAL

    def test_connect_disconnect(self):
        """connect/disconnect lifecycle works."""
        src = FakeDataSource()

        async def _run():
            await src.connect()
            assert src.connected
            await src.disconnect()
            assert not src.connected

        asyncio.run(_run())

    def test_poll_returns_list(self):
        """poll() returns a list."""
        src = FakeDataSource()

        async def _run():
            return await src.poll()

        result = asyncio.run(_run())
        assert isinstance(result, list)

    def test_health_delegation(self):
        """health() delegates to internal HealthMonitor."""
        src = FakeDataSource()
        src.health_monitor.record_success(latency_ms=5.0)
        h = src.health()
        assert h.source_name == "fake"
        assert h.requests_total == 1
        assert h.latency_ms == 5.0

    def test_source_type_enum(self):
        """SourceType enum has expected members."""
        assert SourceType.REALTIME == "realtime"
        assert SourceType.HISTORICAL == "historical"
        assert SourceType.NEWS == "news"
        assert SourceType.SOCIAL == "social"

    def test_repr(self):
        """repr is informative."""
        src = FakeDataSource("my_src", SourceType.NEWS)
        r = repr(src)
        assert "my_src" in r
        assert "news" in r


# =====================================================================
#  Detector (ABC contract)
# =====================================================================


class TestDetector:
    """Detector interface contract tests."""

    def test_instantiation(self):
        """Concrete subclass can be instantiated."""
        det = FakeDetector("vol_det", ["kline"])
        assert det.name == "vol_det"
        assert det.accepts == ["kline"]

    def test_can_handle_true(self):
        """can_handle returns True for accepted types."""
        det = FakeDetector(accepts=["kline", "news"])
        evt = _make_event(event_type="kline")
        assert det.can_handle(evt) is True

    def test_can_handle_false(self):
        """can_handle returns False for non-accepted types."""
        det = FakeDetector(accepts=["news"])
        evt = _make_event(event_type="kline")
        assert det.can_handle(evt) is False

    def test_detect_returns_list(self):
        """detect() returns a list of UnifiedSignal."""
        det = FakeDetector(accepts=["kline"])
        det._signals = [_make_signal()]
        evt = _make_event(event_type="kline")
        result = asyncio.run(det.detect(evt))
        assert len(result) == 1
        assert isinstance(result[0], UnifiedSignal)

    def test_detect_empty_on_unhandled(self):
        """detect() returns empty for non-accepted event types."""
        det = FakeDetector(accepts=["news"])
        det._signals = [_make_signal()]
        evt = _make_event(event_type="kline")
        result = asyncio.run(det.detect(evt))
        assert result == []

    def test_repr(self):
        """repr includes name and accepts."""
        det = FakeDetector("my_det", ["kline"])
        r = repr(det)
        assert "my_det" in r
        assert "kline" in r


# =====================================================================
#  SourceRegistry
# =====================================================================


class TestSourceRegistry:
    """SourceRegistry tests."""

    def test_register_and_get(self):
        """register + get lifecycle."""
        reg = SourceRegistry()
        src = FakeDataSource("alpha")
        reg.register(src)
        assert reg.get("alpha") is src

    def test_register_duplicate_raises(self):
        """Duplicate name raises ValueError."""
        reg = SourceRegistry()
        reg.register(FakeDataSource("alpha"))
        with pytest.raises(ValueError, match="already registered"):
            reg.register(FakeDataSource("alpha"))

    def test_get_missing_raises(self):
        """Missing name raises KeyError."""
        reg = SourceRegistry()
        with pytest.raises(KeyError, match="not registered"):
            reg.get("nope")

    def test_all(self):
        """all() returns all sources in insertion order."""
        reg = SourceRegistry()
        s1 = FakeDataSource("a")
        s2 = FakeDataSource("b")
        reg.register(s1)
        reg.register(s2)
        assert reg.all() == [s1, s2]

    def test_health_report(self):
        """health_report() returns a dict of SourceHealth."""
        reg = SourceRegistry()
        src = FakeDataSource("alpha")
        src.health_monitor.record_success(latency_ms=10)
        reg.register(src)
        report = reg.health_report()
        assert "alpha" in report
        assert isinstance(report["alpha"], SourceHealth)
        assert report["alpha"].requests_total == 1

    def test_unregister(self):
        """unregister removes source."""
        reg = SourceRegistry()
        reg.register(FakeDataSource("alpha"))
        reg.unregister("alpha")
        assert "alpha" not in reg

    def test_unregister_missing_raises(self):
        """Unregistering unknown name raises KeyError."""
        reg = SourceRegistry()
        with pytest.raises(KeyError, match="not registered"):
            reg.unregister("nope")

    def test_len_and_contains(self):
        """__len__ and __contains__ work."""
        reg = SourceRegistry()
        assert len(reg) == 0
        reg.register(FakeDataSource("x"))
        assert len(reg) == 1
        assert "x" in reg
        assert "y" not in reg

    def test_names(self):
        """names property lists registered names."""
        reg = SourceRegistry()
        reg.register(FakeDataSource("a"))
        reg.register(FakeDataSource("b"))
        assert reg.names == ["a", "b"]


# =====================================================================
#  PerceptionConfig
# =====================================================================


class TestPerceptionConfig:
    """PerceptionConfig tests."""

    def test_defaults(self):
        """Default config is valid."""
        cfg = PerceptionConfig()
        assert cfg.global_poll_interval_seconds == 60.0
        assert cfg.sources == {}
        assert cfg.detectors == {}
        assert cfg.circuit_breaker.failure_threshold == 5

    def test_source_config_explicit(self):
        """source_config returns explicit config when available."""
        cfg = PerceptionConfig(
            sources={"tushare": SourcePollConfig(interval_seconds=10)}
        )
        sc = cfg.source_config("tushare")
        assert sc.interval_seconds == 10

    def test_source_config_fallback(self):
        """source_config falls back to global interval."""
        cfg = PerceptionConfig(global_poll_interval_seconds=30)
        sc = cfg.source_config("unknown")
        assert sc.interval_seconds == 30
        assert sc.enabled is True

    def test_detector_enabled_default(self):
        """Unconfigured detector is enabled by default."""
        cfg = PerceptionConfig()
        assert cfg.detector_enabled("something") is True

    def test_detector_disabled(self):
        """Explicitly disabled detector returns False."""
        cfg = PerceptionConfig(
            detectors={"volume_spike": DetectorConfig(enabled=False)}
        )
        assert cfg.detector_enabled("volume_spike") is False

    def test_circuit_breaker_custom(self):
        """Custom circuit breaker values are preserved."""
        cfg = PerceptionConfig(
            circuit_breaker=CircuitBreakerConfig(
                failure_threshold=10,
                recovery_timeout_seconds=120,
                half_open_max_requests=3,
            )
        )
        assert cfg.circuit_breaker.failure_threshold == 10
        assert cfg.circuit_breaker.recovery_timeout_seconds == 120

    def test_serialization_roundtrip(self):
        """Config survives JSON roundtrip."""
        cfg = PerceptionConfig(
            sources={"sina": SourcePollConfig(interval_seconds=5)},
            detectors={"vol": DetectorConfig(enabled=True, params={"k": 1})},
        )
        restored = PerceptionConfig.model_validate_json(cfg.model_dump_json())
        assert restored.sources["sina"].interval_seconds == 5
        assert restored.detectors["vol"].params["k"] == 1

    def test_source_poll_config_validation(self):
        """Invalid poll config values are rejected."""
        with pytest.raises(ValidationError):
            SourcePollConfig(interval_seconds=-1)
        with pytest.raises(ValidationError):
            SourcePollConfig(timeout_seconds=0)

    def test_circuit_breaker_validation(self):
        """Invalid circuit breaker values are rejected."""
        with pytest.raises(ValidationError):
            CircuitBreakerConfig(failure_threshold=0)
        with pytest.raises(ValidationError):
            CircuitBreakerConfig(recovery_timeout_seconds=-5)


# =====================================================================
#  UnifiedSignal (local copy sanity)
# =====================================================================


class TestUnifiedSignal:
    """Sanity tests for the local UnifiedSignal copy."""

    def test_create(self):
        """Signal can be created with required fields."""
        sig = _make_signal()
        assert sig.signal_id
        assert sig.market == "a_share"
        assert sig.asset == "000001.SZ"
        assert 0 <= sig.strength <= 1

    def test_strength_bounds(self):
        """Strength outside 0-1 is rejected."""
        with pytest.raises(ValidationError):
            _make_signal(strength=1.5)
        with pytest.raises(ValidationError):
            _make_signal(strength=-0.1)

    def test_confidence_bounds(self):
        """Confidence outside 0-1 is rejected."""
        with pytest.raises(ValidationError):
            _make_signal(confidence=2.0)

    def test_json_roundtrip(self):
        """Signal survives JSON roundtrip."""
        sig = _make_signal()
        restored = UnifiedSignal.from_json(sig.to_json())
        assert restored.asset == sig.asset
        assert restored.direction == sig.direction

    def test_dict_roundtrip(self):
        """Signal survives dict roundtrip."""
        sig = _make_signal()
        restored = UnifiedSignal.from_dict(sig.to_dict())
        assert restored.signal_type == sig.signal_type

    def test_market_specific_subclass(self):
        """AShareSignal extends UnifiedSignal."""
        sig = AShareSignal(
            asset="000001.SZ",
            direction=Direction.LONG,
            strength=0.9,
            confidence=0.8,
            signal_type=SignalType.TECHNICAL,
            source="test",
            limit_up_count=3,
            concept_codes=["BK001"],
        )
        assert sig.market == "a_share"
        assert sig.limit_up_count == 3
        assert isinstance(sig, UnifiedSignal)

    def test_is_expired(self):
        """is_expired works correctly."""
        past = datetime.now(timezone.utc) - timedelta(hours=2)
        sig = _make_signal(
            timestamp=past,
            expires_at=past + timedelta(seconds=1),  # already passed
        )
        assert sig.is_expired is True

        sig2 = _make_signal(
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
        )
        assert sig2.is_expired is False

        sig3 = _make_signal()
        assert sig3.is_expired is False


# =====================================================================
#  Integration: top-level imports
# =====================================================================


class TestTopLevelImports:
    """Verify the perception package re-exports work."""

    def test_all_imports(self):
        """All key symbols are importable from src.perception."""
        from src.perception import (
            DataSource,
            Detector,
            HealthMonitor,
            PerceptionConfig,
            RawMarketEvent,
            SourceHealth,
            SourceRegistry,
            SourceType,
            UnifiedSignal,
        )

        # Just verify they're the right types
        assert issubclass(DataSource, ABC)
        assert issubclass(Detector, ABC)

    def test_sources_subpackage_imports(self):
        """Sources subpackage re-exports work."""
        from src.perception.sources import DataSource, SourceRegistry, SourceType

        assert SourceType.REALTIME == "realtime"


from abc import ABC
