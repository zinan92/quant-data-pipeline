"""Tests for PriceDetector."""

import pytest
from datetime import datetime, timezone

from src.perception.detectors.price_detector import PriceDetector, PriceDetectorConfig
from src.perception.events import EventType, MarketScope, RawMarketEvent
from src.perception.signals import Direction, Market


def _make_event(bars, symbol="TEST.SH"):
    return RawMarketEvent(
        source="tushare",
        event_type=EventType.KLINE,
        market=MarketScope.CN_STOCK,
        symbol=symbol,
        data={"bars": bars},
        timestamp=datetime.now(timezone.utc),
    )


def _make_bars(closes, opens=None, highs=None, lows=None, volumes=None):
    """Generate bar dicts from price lists."""
    n = len(closes)
    opens = opens or closes
    highs = highs or [max(c, o) + 0.5 for c, o in zip(closes, opens)]
    lows = lows or [min(c, o) - 0.5 for c, o in zip(closes, opens)]
    volumes = volumes or [1_000_000] * n
    return [
        {"open": o, "high": h, "low": l, "close": c, "volume": v}
        for o, h, l, c, v in zip(opens, highs, lows, closes, volumes)
    ]


class TestPriceDetectorBasic:
    def test_empty_bars(self):
        d = PriceDetector()
        event = _make_event([])
        assert d.detect(event) == []

    def test_name_and_accepts(self):
        d = PriceDetector()
        assert d.name == "price"
        assert EventType.KLINE in d.accepts
        assert EventType.PRICE_UPDATE in d.accepts


class TestBreakout:
    def test_new_20d_high(self):
        """Price breaks above 20-day high → LONG signal."""
        closes = [10.0] * 20 + [11.0]  # 20 days at 10, then jump to 11
        highs = [10.5] * 20 + [11.5]
        lows = [9.5] * 20 + [10.5]
        bars = _make_bars(closes, highs=highs, lows=lows)
        event = _make_event(bars)

        d = PriceDetector()
        signals = d.detect(event)

        breakout_signals = [s for s in signals if "breakout" in s.source and "high" in s.source]
        assert len(breakout_signals) > 0
        assert breakout_signals[0].direction == Direction.LONG

    def test_new_20d_low(self):
        """Price breaks below 20-day low → SHORT signal."""
        closes = [10.0] * 20 + [9.0]
        highs = [10.5] * 20 + [9.5]
        lows = [9.5] * 20 + [8.5]
        bars = _make_bars(closes, highs=highs, lows=lows)
        event = _make_event(bars)

        d = PriceDetector()
        signals = d.detect(event)

        breakdown_signals = [s for s in signals if "breakout" in s.source and "low" in s.source]
        assert len(breakdown_signals) > 0
        assert breakdown_signals[0].direction == Direction.SHORT

    def test_near_high(self):
        """Price within 2% of 20d high but not breaking → near-high signal."""
        closes = [10.0] * 20 + [10.0]
        highs = [10.2] * 20 + [10.15]  # high=10.2, current=10.15 (99.5%)
        lows = [9.8] * 20 + [9.9]
        bars = _make_bars(closes, highs=highs, lows=lows)
        event = _make_event(bars)

        d = PriceDetector()
        signals = d.detect(event)

        near_high = [s for s in signals if "near" in s.source and "high" in s.source]
        assert len(near_high) > 0


class TestGap:
    def test_gap_up(self):
        """Open significantly above yesterday's close → gap up."""
        bars = _make_bars(
            closes=[10.0, 10.5],
            opens=[10.0, 10.2],
            highs=[10.1, 10.6],
            lows=[9.9, 10.15],
        )
        event = _make_event(bars)

        d = PriceDetector(PriceDetectorConfig(gap_min_pct=1.0))
        signals = d.detect(event)

        gap_signals = [s for s in signals if "gap" in s.source]
        assert len(gap_signals) > 0
        assert gap_signals[0].direction == Direction.LONG

    def test_gap_down(self):
        """Open significantly below yesterday's close → gap down."""
        bars = _make_bars(
            closes=[10.0, 9.5],
            opens=[10.0, 9.8],
            highs=[10.1, 9.85],
            lows=[9.9, 9.4],
        )
        event = _make_event(bars)

        d = PriceDetector(PriceDetectorConfig(gap_min_pct=1.0))
        signals = d.detect(event)

        gap_signals = [s for s in signals if "gap" in s.source]
        assert len(gap_signals) > 0
        assert gap_signals[0].direction == Direction.SHORT

    def test_no_gap_small_move(self):
        """Small open move → no gap signal."""
        bars = _make_bars(
            closes=[10.0, 10.05],
            opens=[10.0, 10.02],
            highs=[10.1, 10.1],
            lows=[9.9, 10.0],
        )
        event = _make_event(bars)

        d = PriceDetector(PriceDetectorConfig(gap_min_pct=1.0))
        signals = d.detect(event)

        gap_signals = [s for s in signals if "gap" in s.source]
        assert len(gap_signals) == 0


class TestMomentum:
    def test_consecutive_up(self):
        """5 consecutive up days → momentum signal."""
        closes = [10.0, 10.1, 10.2, 10.3, 10.4, 10.5]
        bars = _make_bars(closes)
        event = _make_event(bars)

        d = PriceDetector(PriceDetectorConfig(min_consecutive_days=3))
        signals = d.detect(event)

        streak = [s for s in signals if "consecutive" in s.source]
        assert len(streak) > 0
        assert streak[0].direction == Direction.LONG

    def test_consecutive_down(self):
        """4 consecutive down days → bearish momentum."""
        closes = [10.0, 9.9, 9.8, 9.7, 9.6]
        bars = _make_bars(closes)
        event = _make_event(bars)

        d = PriceDetector(PriceDetectorConfig(min_consecutive_days=3))
        signals = d.detect(event)

        streak = [s for s in signals if "consecutive" in s.source]
        assert len(streak) > 0
        assert streak[0].direction == Direction.SHORT


class TestMASupport:
    def test_price_near_ma20(self):
        """Price very close to MA20 → support/resistance signal."""
        # 20 bars all at 10.0 → MA20 = 10.0, close also ~10.0
        closes = [10.0] * 19 + [10.02]
        bars = _make_bars(closes)
        event = _make_event(bars)

        d = PriceDetector(PriceDetectorConfig(ma_test_tolerance_pct=0.5))
        signals = d.detect(event)

        ma_signals = [s for s in signals if "ma" in s.source.lower() and ("support" in s.source or "resistance" in s.source)]
        assert len(ma_signals) > 0
