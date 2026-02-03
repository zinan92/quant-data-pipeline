"""Tests for MarketContextBuilder — market context from perception data."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from src.perception.aggregator import (
    AggregationReport,
    AssetSignalSummary,
)
from src.perception.integration.market_context import (
    ContextConfig,
    MarketContext,
    MarketContextBuilder,
    MarketSentiment,
    RiskFactor,
    RiskLevel,
    SectorSignal,
)
from src.perception.pipeline import ScanResult
from src.perception.signals import (
    Direction,
    Market,
    SignalType,
    UnifiedSignal,
)


# ── Fixtures ─────────────────────────────────────────────────────────


def _make_signal(
    asset: str = "BTC",
    direction: Direction = Direction.LONG,
    strength: float = 0.8,
    confidence: float = 0.7,
    source: str = "technical/rsi",
    metadata: dict | None = None,
) -> UnifiedSignal:
    return UnifiedSignal(
        market=Market.CRYPTO,
        asset=asset,
        direction=direction,
        strength=strength,
        confidence=confidence,
        signal_type=SignalType.TECHNICAL,
        source=source,
        metadata=metadata or {},
    )


def _make_summary(
    asset: str = "BTC",
    direction: Direction = Direction.LONG,
    composite_score: float = 0.6,
    net_score: float = 0.5,
    long_signals: int = 3,
    short_signals: int = 0,
    signals: list | None = None,
) -> AssetSignalSummary:
    sig = _make_signal(asset=asset, direction=direction)
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
        sources=["technical/rsi"],
        top_signal=sig,
        all_signals=signals or [sig],
        last_updated=datetime.now(timezone.utc),
    )


def _make_report(
    top_longs: list | None = None,
    top_shorts: list | None = None,
    market_bias: Direction = Direction.LONG,
    market_bias_score: float = 0.5,
    by_market: dict | None = None,
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
        market_bias_score=market_bias_score,
        by_market=by_market or {},
    )


def _make_scan_result(report: AggregationReport) -> ScanResult:
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


class TestMarketContextBasic:
    def test_build_from_scan_result(self):
        builder = MarketContextBuilder()
        report = _make_report(
            top_longs=[_make_summary("BTC")],
            market_bias=Direction.LONG,
            market_bias_score=0.5,
        )
        scan = _make_scan_result(report)
        ctx = builder.build(scan)
        assert isinstance(ctx, MarketContext)
        assert ctx.long_count == 1
        assert ctx.short_count == 0

    def test_from_report(self):
        builder = MarketContextBuilder()
        report = _make_report(
            top_longs=[_make_summary("BTC")],
            market_bias=Direction.LONG,
            market_bias_score=0.5,
        )
        ctx = builder.from_report(report)
        assert ctx.total_signals == report.total_signals

    def test_to_dict(self):
        builder = MarketContextBuilder()
        report = _make_report(top_longs=[_make_summary("BTC")])
        ctx = builder.from_report(report)
        d = ctx.to_dict()
        assert "sentiment" in d
        assert "risk_level" in d
        assert "timestamp" in d
        assert "sector_signals" in d


class TestSentimentClassification:
    def test_strongly_bullish(self):
        builder = MarketContextBuilder()
        report = _make_report(
            top_longs=[_make_summary("A"), _make_summary("B")],
            market_bias=Direction.LONG,
            market_bias_score=0.7,
        )
        ctx = builder.from_report(report)
        assert ctx.sentiment == MarketSentiment.STRONGLY_BULLISH
        assert ctx.sentiment_score > 0.6

    def test_bullish(self):
        builder = MarketContextBuilder()
        report = _make_report(
            top_longs=[_make_summary("A")],
            market_bias=Direction.LONG,
            market_bias_score=0.3,
        )
        ctx = builder.from_report(report)
        assert ctx.sentiment == MarketSentiment.BULLISH

    def test_neutral(self):
        builder = MarketContextBuilder()
        report = _make_report(
            market_bias=Direction.LONG,
            market_bias_score=0.1,
        )
        ctx = builder.from_report(report)
        assert ctx.sentiment == MarketSentiment.NEUTRAL

    def test_bearish(self):
        builder = MarketContextBuilder()
        report = _make_report(
            top_shorts=[_make_summary("X", Direction.SHORT)],
            market_bias=Direction.SHORT,
            market_bias_score=0.3,
        )
        ctx = builder.from_report(report)
        assert ctx.sentiment == MarketSentiment.BEARISH

    def test_strongly_bearish(self):
        builder = MarketContextBuilder()
        report = _make_report(
            top_shorts=[_make_summary("X", Direction.SHORT)],
            market_bias=Direction.SHORT,
            market_bias_score=0.7,
        )
        ctx = builder.from_report(report)
        assert ctx.sentiment == MarketSentiment.STRONGLY_BEARISH

    def test_custom_thresholds(self):
        cfg = ContextConfig(
            strongly_bullish_threshold=0.9,
            bullish_threshold=0.5,
        )
        builder = MarketContextBuilder(config=cfg)
        report = _make_report(
            market_bias=Direction.LONG,
            market_bias_score=0.6,
        )
        ctx = builder.from_report(report)
        # 0.6 is above 0.5 but below 0.9 → BULLISH, not STRONGLY
        assert ctx.sentiment == MarketSentiment.BULLISH


class TestRiskFactors:
    def test_no_risk_factors_when_clean(self):
        builder = MarketContextBuilder()
        report = _make_report(top_longs=[_make_summary("A")])
        ctx = builder.from_report(report)
        assert ctx.risk_level == RiskLevel.LOW

    def test_high_risk_many_shorts(self):
        builder = MarketContextBuilder(ContextConfig(high_risk_short_count=3))
        shorts = [_make_summary(f"S{i}", Direction.SHORT) for i in range(4)]
        report = _make_report(top_shorts=shorts)
        ctx = builder.from_report(report)
        factors = [f for f in ctx.risk_factors if f.name == "elevated_bearish_signals"]
        assert len(factors) == 1
        assert ctx.risk_level in (RiskLevel.HIGH, RiskLevel.EXTREME)

    def test_extreme_risk_mass_shorts(self):
        builder = MarketContextBuilder(ContextConfig(extreme_risk_short_count=5))
        shorts = [_make_summary(f"S{i}", Direction.SHORT) for i in range(6)]
        report = _make_report(top_shorts=shorts)
        ctx = builder.from_report(report)
        factors = [f for f in ctx.risk_factors if f.name == "mass_bearish_signals"]
        assert len(factors) == 1

    def test_low_long_ratio_risk(self):
        builder = MarketContextBuilder()
        longs = [_make_summary("L1")]
        shorts = [_make_summary(f"S{i}", Direction.SHORT) for i in range(4)]
        report = _make_report(top_longs=longs, top_shorts=shorts)
        ctx = builder.from_report(report)
        low_ratio = [f for f in ctx.risk_factors if f.name == "low_long_ratio"]
        assert len(low_ratio) == 1

    def test_signal_divergence(self):
        builder = MarketContextBuilder()
        longs = [_make_summary(f"L{i}") for i in range(3)]
        shorts = [_make_summary(f"S{i}", Direction.SHORT) for i in range(3)]
        report = _make_report(top_longs=longs, top_shorts=shorts)
        ctx = builder.from_report(report)
        div_factors = [f for f in ctx.risk_factors if f.name == "signal_divergence"]
        assert len(div_factors) == 1

    def test_no_bullish_in_market(self):
        builder = MarketContextBuilder()
        report = _make_report(
            top_shorts=[_make_summary("X", Direction.SHORT)],
            by_market={"crypto": {"short_count": 3, "long_count": 0, "total_score": 1.0}},
        )
        ctx = builder.from_report(report)
        mkt_factors = [f for f in ctx.risk_factors if "no_bullish" in f.name]
        assert len(mkt_factors) == 1


class TestSectorSignals:
    def test_sector_extraction(self):
        builder = MarketContextBuilder(ContextConfig(min_sector_signals=1))
        sig = _make_signal("BTC", metadata={"sector": "DeFi"})
        summary = _make_summary("BTC", signals=[sig])
        report = _make_report(top_longs=[summary])
        ctx = builder.from_report(report)
        assert len(ctx.sector_signals) >= 1
        assert ctx.sector_signals[0].sector == "DeFi"

    def test_sector_min_signals_filter(self):
        builder = MarketContextBuilder(ContextConfig(min_sector_signals=5))
        sig = _make_signal("BTC", metadata={"sector": "DeFi"})
        summary = _make_summary("BTC", signals=[sig])
        report = _make_report(top_longs=[summary])
        ctx = builder.from_report(report)
        # Only 1 signal → below min threshold of 5
        assert len(ctx.sector_signals) == 0

    def test_sector_signal_to_dict(self):
        ss = SectorSignal(
            sector="DeFi",
            direction="inflow",
            strength=0.7,
            signal_count=3,
            top_assets=["BTC", "ETH"],
        )
        d = ss.to_dict()
        assert d["sector"] == "DeFi"
        assert d["strength"] == 0.7


class TestRiskFactorModel:
    def test_to_dict_with_value(self):
        rf = RiskFactor(
            name="test_risk",
            severity="high",
            description="something risky",
            value=42.0,
        )
        d = rf.to_dict()
        assert d["name"] == "test_risk"
        assert d["value"] == 42.0

    def test_to_dict_without_value(self):
        rf = RiskFactor(
            name="test_risk",
            severity="moderate",
            description="something risky",
        )
        d = rf.to_dict()
        assert "value" not in d


class TestEmptyContext:
    def test_empty_report(self):
        builder = MarketContextBuilder()
        report = _make_report(market_bias_score=0.0)
        ctx = builder.from_report(report)
        assert ctx.active_assets == 0
        assert ctx.risk_level == RiskLevel.LOW
        assert ctx.sentiment == MarketSentiment.NEUTRAL
