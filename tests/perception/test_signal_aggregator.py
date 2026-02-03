"""Tests for SignalAggregator."""

import pytest
from datetime import datetime, timedelta, timezone

from src.perception.aggregator import (
    AggregatorConfig,
    SignalAggregator,
)
from src.perception.signals import (
    Direction,
    Market,
    SignalType,
    UnifiedSignal,
)


def _make_signal(
    asset="TEST.SH",
    direction=Direction.LONG,
    strength=0.7,
    confidence=0.8,
    source="technical/ma_cross",
    signal_type=SignalType.TECHNICAL,
    market=Market.A_SHARE,
    ts=None,
):
    return UnifiedSignal(
        market=market,
        asset=asset,
        direction=direction,
        strength=strength,
        confidence=confidence,
        signal_type=signal_type,
        source=source,
        timestamp=ts or datetime.now(timezone.utc),
    )


class TestAggregatorBasic:
    def test_empty(self):
        agg = SignalAggregator()
        assert agg.signal_count() == 0
        assert agg.asset_count() == 0
        report = agg.summarize()
        assert report.total_signals == 0

    def test_ingest_one(self):
        agg = SignalAggregator()
        sig = _make_signal()
        assert agg.ingest_one(sig) is True
        assert agg.signal_count() == 1
        assert agg.asset_count() == 1

    def test_ingest_multiple(self):
        agg = SignalAggregator()
        signals = [
            _make_signal(asset="A.SH", source="technical/rsi"),
            _make_signal(asset="B.SH", source="technical/macd"),
            _make_signal(asset="A.SH", source="flow/northbound"),
        ]
        added = agg.ingest(signals)
        assert added == 3
        assert agg.asset_count() == 2
        assert agg.signal_count() == 3

    def test_clear(self):
        agg = SignalAggregator()
        agg.ingest([_make_signal(), _make_signal(asset="B.SH")])
        assert agg.signal_count() == 2
        agg.clear()
        assert agg.signal_count() == 0


class TestDeduplication:
    def test_exact_duplicate_rejected(self):
        """Same asset + same source + same direction within window → deduplicated."""
        agg = SignalAggregator(AggregatorConfig(dedup_window_seconds=60))
        ts = datetime.now(timezone.utc)
        sig1 = _make_signal(source="technical/rsi", ts=ts)
        sig2 = _make_signal(source="technical/rsi", ts=ts + timedelta(seconds=10))

        agg.ingest_one(sig1)
        added = agg.ingest_one(sig2)
        assert added is False
        assert agg.signal_count() == 1

    def test_different_source_not_deduped(self):
        """Same asset but different source → both kept."""
        agg = SignalAggregator(AggregatorConfig(dedup_window_seconds=60))
        ts = datetime.now(timezone.utc)
        sig1 = _make_signal(source="technical/rsi", ts=ts)
        sig2 = _make_signal(source="technical/macd", ts=ts)

        agg.ingest_one(sig1)
        added = agg.ingest_one(sig2)
        assert added is True
        assert agg.signal_count() == 2

    def test_different_direction_not_deduped(self):
        """Same source but different direction → both kept."""
        agg = SignalAggregator(AggregatorConfig(dedup_window_seconds=60))
        ts = datetime.now(timezone.utc)
        sig1 = _make_signal(direction=Direction.LONG, ts=ts)
        sig2 = _make_signal(direction=Direction.SHORT, ts=ts)

        agg.ingest_one(sig1)
        added = agg.ingest_one(sig2)
        assert added is True


class TestAssetSummary:
    def test_single_long_signal(self):
        agg = SignalAggregator()
        agg.ingest_one(_make_signal(strength=0.8, confidence=0.9))
        summary = agg.get_asset_signals("TEST.SH")
        assert summary is not None
        assert summary.direction == Direction.LONG
        assert summary.long_signals == 1
        assert summary.short_signals == 0
        assert summary.composite_score > 0

    def test_conflicting_signals(self):
        """Both LONG and SHORT signals → conflict penalty applies."""
        agg = SignalAggregator(AggregatorConfig(conflict_penalty=0.3))
        agg.ingest([
            _make_signal(direction=Direction.LONG, strength=0.8, confidence=0.9, source="technical/rsi"),
            _make_signal(direction=Direction.SHORT, strength=0.3, confidence=0.5, source="technical/macd"),
        ])
        summary = agg.get_asset_signals("TEST.SH")
        assert summary is not None
        # LONG should dominate since it's much stronger
        assert summary.direction == Direction.LONG
        # But score should be penalized
        assert summary.long_signals == 1
        assert summary.short_signals == 1

    def test_multiple_confirmations(self):
        """Multiple LONG signals from different sources → high composite score."""
        agg = SignalAggregator()
        agg.ingest([
            _make_signal(source="technical/rsi", strength=0.7, confidence=0.8),
            _make_signal(source="technical/macd", strength=0.8, confidence=0.7),
            _make_signal(source="flow/northbound", strength=0.6, confidence=0.8,
                        signal_type=SignalType.FLOW),
        ])
        summary = agg.get_asset_signals("TEST.SH")
        assert summary is not None
        assert summary.direction == Direction.LONG
        assert summary.signal_count == 3
        assert summary.composite_score > 0.5


class TestReport:
    def test_basic_report(self):
        agg = SignalAggregator()
        agg.ingest([
            _make_signal(asset="BULL.SH", direction=Direction.LONG, strength=0.9,
                        source="technical/rsi"),
            _make_signal(asset="BEAR.SH", direction=Direction.SHORT, strength=0.8,
                        source="technical/macd"),
        ])
        report = agg.summarize()
        assert report.total_signals == 2
        assert report.total_assets == 2
        assert len(report.top_longs) >= 1
        assert len(report.top_shorts) >= 1

    def test_market_bias(self):
        """More/stronger LONG signals → LONG bias."""
        agg = SignalAggregator()
        agg.ingest([
            _make_signal(asset="A.SH", direction=Direction.LONG, strength=0.9, source="a"),
            _make_signal(asset="B.SH", direction=Direction.LONG, strength=0.8, source="b"),
            _make_signal(asset="C.SH", direction=Direction.SHORT, strength=0.3, source="c"),
        ])
        report = agg.summarize()
        assert report.market_bias == Direction.LONG

    def test_report_to_dict(self):
        agg = SignalAggregator()
        agg.ingest_one(_make_signal())
        report = agg.summarize()
        d = report.to_dict()
        assert "total_signals" in d
        assert "market_bias" in d
        assert "top_longs" in d


class TestTopSignals:
    def test_top_longs(self):
        agg = SignalAggregator()
        agg.ingest([
            _make_signal(asset="A.SH", strength=0.9, source="a"),
            _make_signal(asset="B.SH", strength=0.5, source="b"),
            _make_signal(asset="C.SH", strength=0.7, source="c"),
        ])
        top = agg.top_signals(direction=Direction.LONG, limit=2)
        assert len(top) == 2
        # Should be sorted by composite score descending
        assert top[0].composite_score >= top[1].composite_score

    def test_filter_by_market(self):
        agg = SignalAggregator()
        agg.ingest([
            _make_signal(asset="A.SH", market=Market.A_SHARE, source="a"),
            _make_signal(asset="BTC", market=Market.CRYPTO, source="b"),
        ])
        top = agg.top_signals(market=Market.A_SHARE)
        assert len(top) == 1
        assert top[0].asset == "A.SH"


class TestStaleEviction:
    def test_old_signals_evicted(self):
        agg = SignalAggregator(AggregatorConfig(max_signal_age_seconds=60))
        old_ts = datetime.now(timezone.utc) - timedelta(seconds=120)
        agg.ingest_one(_make_signal(ts=old_ts))
        assert agg.signal_count() == 1
        # Summarize triggers eviction
        report = agg.summarize()
        assert report.total_signals == 0

    def test_fresh_signals_kept(self):
        agg = SignalAggregator(AggregatorConfig(max_signal_age_seconds=3600))
        agg.ingest_one(_make_signal())
        report = agg.summarize()
        assert report.total_signals == 1


class TestExpiredSignal:
    def test_expired_signal_rejected(self):
        """Signal with expires_at in the past is not ingested."""
        agg = SignalAggregator()
        ts = datetime.now(timezone.utc) - timedelta(minutes=10)
        sig = UnifiedSignal(
            market=Market.A_SHARE,
            asset="TEST.SH",
            direction=Direction.LONG,
            strength=0.7,
            confidence=0.8,
            signal_type=SignalType.TECHNICAL,
            source="test",
            timestamp=ts,
            expires_at=ts + timedelta(seconds=1),  # expired
        )
        added = agg.ingest_one(sig)
        assert added is False
