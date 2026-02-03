"""Tests for TradingBridge — Perception → Trading-Agents signal translation."""

from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone

from src.perception.aggregator import (
    AggregationReport,
    AggregatorConfig,
    AssetSignalSummary,
    SignalAggregator,
)
from src.perception.integration.trading_bridge import (
    BridgeConfig,
    TradingAction,
    TradingBridge,
    TradingSignal,
)
from src.perception.pipeline import ScanResult
from src.perception.signals import (
    Direction,
    Market,
    SignalType,
    UnifiedSignal,
)
from src.perception.health import HealthStatus, SourceHealth


# ── Fixtures ─────────────────────────────────────────────────────────


def _make_signal(
    asset: str = "BTC",
    direction: Direction = Direction.LONG,
    strength: float = 0.8,
    confidence: float = 0.7,
    source: str = "technical/rsi",
    signal_type: SignalType = SignalType.TECHNICAL,
    market: Market = Market.CRYPTO,
    **kwargs,
) -> UnifiedSignal:
    return UnifiedSignal(
        market=market,
        asset=asset,
        direction=direction,
        strength=strength,
        confidence=confidence,
        signal_type=signal_type,
        source=source,
        **kwargs,
    )


def _make_summary(
    asset: str = "BTC",
    direction: Direction = Direction.LONG,
    composite_score: float = 0.6,
    net_score: float = 0.5,
    long_signals: int = 3,
    short_signals: int = 0,
    confidence: float = 0.7,
) -> AssetSignalSummary:
    sig = _make_signal(asset=asset, direction=direction, confidence=confidence)
    return AssetSignalSummary(
        asset=asset,
        market=Market.CRYPTO,
        direction=direction,
        composite_score=composite_score,
        net_score=net_score,
        signal_count=long_signals + short_signals,
        long_signals=long_signals,
        short_signals=short_signals,
        dominant_type=SignalType.TECHNICAL,
        sources=["technical/rsi", "technical/macd"],
        top_signal=sig,
        all_signals=[sig],
        last_updated=datetime.now(timezone.utc),
    )


def _make_report(
    top_longs: list | None = None,
    top_shorts: list | None = None,
    market_bias: Direction = Direction.LONG,
) -> AggregationReport:
    longs = top_longs or []
    shorts = top_shorts or []
    return AggregationReport(
        timestamp=datetime.now(timezone.utc),
        total_signals=sum(s.signal_count for s in longs + shorts),
        total_assets=len(longs) + len(shorts),
        top_longs=longs,
        top_shorts=shorts,
        market_bias=market_bias,
        market_bias_score=0.6,
        by_market={},
    )


def _make_scan_result(report: AggregationReport | None = None) -> ScanResult:
    if report is None:
        report = _make_report(top_longs=[_make_summary()])
    return ScanResult(
        timestamp=datetime.now(timezone.utc),
        duration_ms=42.0,
        events_fetched=10,
        signals_detected=5,
        signals_ingested=5,
        report=report,
        source_health={},
    )


# ── Tests ────────────────────────────────────────────────────────────


class TestTradingSignal:
    """TradingSignal model tests."""

    def test_to_dict(self):
        sig = TradingSignal(
            signal_type="perception/technical",
            asset="BTC",
            action=TradingAction.LONG,
            direction="bullish",
            strength=0.8,
            confidence=0.7,
            reason="test",
        )
        d = sig.to_dict()
        assert d["action"] == "long"
        assert d["direction"] == "bullish"
        assert d["strength"] == 0.8

    def test_is_actionable(self):
        sig_long = TradingSignal(
            signal_type="x", asset="A", action=TradingAction.LONG,
            direction="bullish", strength=0.5, confidence=0.5, reason="t",
        )
        sig_wait = TradingSignal(
            signal_type="x", asset="A", action=TradingAction.WAIT,
            direction="neutral", strength=0.5, confidence=0.5, reason="t",
        )
        assert sig_long.is_actionable is True
        assert sig_wait.is_actionable is False


class TestTradingBridge:
    """TradingBridge core logic."""

    def test_default_config(self):
        bridge = TradingBridge()
        assert bridge.config.min_confidence == 0.4
        assert bridge.config.source_prefix == "perception"

    def test_custom_config(self):
        cfg = BridgeConfig(min_confidence=0.6)
        bridge = TradingBridge(config=cfg)
        assert bridge.config.min_confidence == 0.6

    def test_get_trading_signals_from_scan_result(self):
        bridge = TradingBridge()
        scan = _make_scan_result()
        signals = bridge.get_trading_signals(scan)
        assert len(signals) >= 1
        assert all(isinstance(s, TradingSignal) for s in signals)

    def test_from_report_longs_only(self):
        bridge = TradingBridge()
        report = _make_report(top_longs=[
            _make_summary("BTC", Direction.LONG, 0.8),
            _make_summary("ETH", Direction.LONG, 0.5),
        ])
        signals = bridge.from_report(report)
        assert len(signals) == 2
        assert all(s.action == TradingAction.LONG for s in signals)

    def test_from_report_shorts(self):
        bridge = TradingBridge()
        report = _make_report(top_shorts=[
            _make_summary("DOGE", Direction.SHORT, 0.6, -0.5, 0, 3),
        ])
        signals = bridge.from_report(report)
        assert len(signals) == 1
        assert signals[0].action == TradingAction.SHORT
        assert signals[0].direction == "bearish"

    def test_from_report_mixed(self):
        bridge = TradingBridge()
        report = _make_report(
            top_longs=[_make_summary("BTC", Direction.LONG, 0.7)],
            top_shorts=[_make_summary("DOGE", Direction.SHORT, 0.5, -0.4, 0, 2)],
        )
        signals = bridge.from_report(report)
        assert len(signals) == 2

    def test_below_composite_threshold_filtered(self):
        bridge = TradingBridge(BridgeConfig(min_composite_score=0.5))
        report = _make_report(top_longs=[
            _make_summary("TINY", Direction.LONG, 0.1),
        ])
        signals = bridge.from_report(report)
        assert len(signals) == 0

    def test_conflicting_signals_produce_wait(self):
        """When minority ratio >= threshold → WAIT."""
        bridge = TradingBridge(BridgeConfig(conflict_ratio_threshold=0.3))
        # 2 long + 2 short = 50% minority → definitely > 0.3
        summary = _make_summary("MIXED", Direction.LONG, 0.6, 0.1, 2, 2)
        report = _make_report(top_longs=[summary])
        signals = bridge.from_report(report)
        assert len(signals) == 1
        assert signals[0].action == TradingAction.WAIT

    def test_low_confidence_top_signal_produces_wait(self):
        bridge = TradingBridge(BridgeConfig(min_confidence=0.5))
        summary = _make_summary("WEAK", Direction.LONG, 0.6, 0.5, 3, 0, confidence=0.2)
        report = _make_report(top_longs=[summary])
        signals = bridge.from_report(report)
        assert len(signals) == 1
        assert signals[0].action == TradingAction.WAIT


class TestBridgeFromUnifiedSignals:
    """Test direct UnifiedSignal → TradingSignal conversion."""

    def test_direct_conversion(self):
        bridge = TradingBridge()
        sig = _make_signal("ETH", Direction.LONG, 0.9, 0.8)
        result = bridge.from_unified_signals([sig])
        assert len(result) == 1
        assert result[0].asset == "ETH"
        assert result[0].action == TradingAction.LONG

    def test_low_confidence_filtered(self):
        bridge = TradingBridge(BridgeConfig(min_confidence=0.5))
        sig = _make_signal("ETH", Direction.LONG, 0.9, 0.3)
        result = bridge.from_unified_signals([sig])
        assert len(result) == 0

    def test_expired_signal_skipped(self):
        bridge = TradingBridge()
        sig = _make_signal("OLD")
        sig.expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        # Need to bypass validator by setting after construction
        result = bridge.from_unified_signals([sig])
        # It should be marked expired
        assert sig.is_expired
        assert len(result) == 0

    def test_short_direction(self):
        bridge = TradingBridge()
        sig = _make_signal("DOGE", Direction.SHORT, 0.7, 0.6)
        result = bridge.from_unified_signals([sig])
        assert len(result) == 1
        assert result[0].action == TradingAction.SHORT
        assert result[0].direction == "bearish"

    def test_signal_metadata_preserved(self):
        bridge = TradingBridge()
        sig = _make_signal("BTC", metadata={"custom": "data"})
        result = bridge.from_unified_signals([sig])
        assert result[0].metadata == {"custom": "data"}


class TestDirectionMapping:
    """Test direction string mapping."""

    def test_long_to_bullish(self):
        assert TradingBridge._direction_string(Direction.LONG) == "bullish"

    def test_short_to_bearish(self):
        assert TradingBridge._direction_string(Direction.SHORT) == "bearish"

    def test_string_long(self):
        assert TradingBridge._direction_string("long") == "bullish"

    def test_string_short(self):
        assert TradingBridge._direction_string("short") == "bearish"


class TestEmptyReport:
    """Edge cases with empty data."""

    def test_empty_report(self):
        bridge = TradingBridge()
        report = _make_report()
        signals = bridge.from_report(report)
        assert signals == []

    def test_empty_scan_result(self):
        bridge = TradingBridge()
        report = _make_report()
        scan = _make_scan_result(report)
        signals = bridge.get_trading_signals(scan)
        assert signals == []
