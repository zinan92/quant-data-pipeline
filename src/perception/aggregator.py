"""SignalAggregator — collect, deduplicate, weight, and summarize signals.

The aggregator sits downstream of all detectors and is responsible for:
1. Collecting signals from multiple detectors into a unified stream
2. De-duplicating overlapping signals (same asset + similar source)
3. Weighting signals by confidence and source reliability
4. Producing per-asset composite scores
5. Providing ranked signal summaries for downstream consumers

Usage::

    aggregator = SignalAggregator()

    # Feed signals from detectors
    for detector in detectors:
        signals = detector.detect(event)
        aggregator.ingest(signals)

    # Get aggregated results
    summary = aggregator.summarize()
    top_longs = aggregator.top_signals(Direction.LONG, limit=10)
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.perception.signals import (
    Direction,
    Market,
    SignalType,
    UnifiedSignal,
)

logger = logging.getLogger(__name__)


# ── Configuration ────────────────────────────────────────────────────


@dataclass
class AggregatorConfig:
    """Tuneable parameters for signal aggregation."""

    # De-duplication: signals for the same asset from the same source
    # within this window are merged.
    dedup_window_seconds: float = 60.0

    # Source reliability weights (0-1).  Higher = more trusted.
    source_weights: Dict[str, float] = field(default_factory=lambda: {
        "technical/ma_cross": 0.7,
        "technical/rsi": 0.6,
        "technical/macd": 0.75,
        "technical/volume_breakout": 0.6,
        "price/breakout_52w_high": 0.85,
        "price/breakout_52w_low": 0.85,
        "price/breakout_20d_high": 0.7,
        "price/breakout_20d_low": 0.7,
        "price/gap_up": 0.65,
        "price/gap_down": 0.65,
        "price/large_gap_up": 0.75,
        "price/large_gap_down": 0.75,
        "price/consecutive_up": 0.65,
        "price/consecutive_down": 0.65,
        "price/acceleration": 0.6,
        "volume/surge": 0.65,
        "volume/extreme_surge": 0.75,
        "volume/bearish_divergence": 0.7,
        "volume/selling_exhaustion": 0.65,
        "volume/panic_selling": 0.75,
        "volume/bearish_climax": 0.7,
        "volume/bullish_climax": 0.7,
        "flow/sector_anomaly": 0.7,
        "flow/northbound": 0.8,
        "flow/sector_rotation": 0.65,
        "anomaly": 0.6,
        "keyword": 0.5,
    })

    # Default weight for unknown sources
    default_source_weight: float = 0.5

    # Signal type weights for composite scoring
    signal_type_weights: Dict[str, float] = field(default_factory=lambda: {
        SignalType.TECHNICAL.value: 0.8,
        SignalType.FLOW.value: 0.9,
        SignalType.FUNDAMENTAL.value: 1.0,
        SignalType.SENTIMENT.value: 0.6,
        SignalType.COMPOSITE.value: 1.0,
    })

    # Minimum composite score to include in summary
    min_composite_score: float = 0.1

    # Max age of signals to keep in the buffer
    max_signal_age_seconds: float = 3600.0  # 1 hour

    # Conflicting signal penalty: reduce score when LONG and SHORT signals coexist
    conflict_penalty: float = 0.3


# ── Data structures ──────────────────────────────────────────────────


@dataclass
class AssetSignalSummary:
    """Aggregated signal summary for a single asset."""

    asset: str
    market: Market
    direction: Direction
    composite_score: float      # weighted aggregate score [-1, 1], normalized to [0, 1]
    net_score: float            # raw LONG - SHORT score
    signal_count: int
    long_signals: int
    short_signals: int
    dominant_type: SignalType    # most frequent signal type
    sources: List[str]          # list of source names that contributed
    top_signal: Optional[UnifiedSignal]  # strongest individual signal
    all_signals: List[UnifiedSignal]
    last_updated: datetime

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset": self.asset,
            "market": self.market.value if isinstance(self.market, Market) else self.market,
            "direction": self.direction.value if isinstance(self.direction, Direction) else self.direction,
            "composite_score": round(self.composite_score, 4),
            "net_score": round(self.net_score, 4),
            "signal_count": self.signal_count,
            "long_signals": self.long_signals,
            "short_signals": self.short_signals,
            "dominant_type": self.dominant_type.value if isinstance(self.dominant_type, SignalType) else self.dominant_type,
            "sources": self.sources,
            "last_updated": self.last_updated.isoformat(),
        }


@dataclass
class AggregationReport:
    """Full aggregation report across all assets."""

    timestamp: datetime
    total_signals: int
    total_assets: int
    top_longs: List[AssetSignalSummary]
    top_shorts: List[AssetSignalSummary]
    market_bias: Direction       # overall market lean
    market_bias_score: float     # how strong the lean is
    by_market: Dict[str, Dict[str, Any]]  # per-market stats

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "total_signals": self.total_signals,
            "total_assets": self.total_assets,
            "market_bias": self.market_bias.value,
            "market_bias_score": round(self.market_bias_score, 4),
            "top_longs": [s.to_dict() for s in self.top_longs],
            "top_shorts": [s.to_dict() for s in self.top_shorts],
            "by_market": self.by_market,
        }


# ── Aggregator ───────────────────────────────────────────────────────


class SignalAggregator:
    """Collect, deduplicate, weight, and summarize UnifiedSignals.

    Thread-safe for single-threaded async usage.  For true
    multi-threaded use, add a lock around ``ingest`` / ``summarize``.
    """

    def __init__(self, config: Optional[AggregatorConfig] = None) -> None:
        self._config = config or AggregatorConfig()
        # asset → list of signals
        self._buffer: Dict[str, List[UnifiedSignal]] = defaultdict(list)
        self._total_ingested: int = 0

    # ── Ingestion ────────────────────────────────────────────────────

    def ingest(self, signals: List[UnifiedSignal]) -> int:
        """Add signals to the aggregation buffer.

        Returns the number of signals actually added (after dedup).
        """
        added = 0
        for signal in signals:
            if signal.is_expired:
                continue
            if self._is_duplicate(signal):
                continue
            self._buffer[signal.asset].append(signal)
            added += 1
        self._total_ingested += added
        return added

    def ingest_one(self, signal: UnifiedSignal) -> bool:
        """Add a single signal.  Returns True if it was added."""
        return self.ingest([signal]) > 0

    # ── Querying ─────────────────────────────────────────────────────

    def summarize(self, limit: int = 20) -> AggregationReport:
        """Produce a full aggregation report.

        Args:
            limit: Max number of top signals per direction.

        Returns:
            AggregationReport with ranked signals and market stats.
        """
        self._evict_stale()

        all_summaries: List[AssetSignalSummary] = []
        for asset, signals in self._buffer.items():
            if not signals:
                continue
            summary = self._build_asset_summary(asset, signals)
            if abs(summary.composite_score) >= self._config.min_composite_score:
                all_summaries.append(summary)

        # Sort by composite score
        longs = sorted(
            [s for s in all_summaries if s.direction == Direction.LONG],
            key=lambda s: s.composite_score,
            reverse=True,
        )[:limit]

        shorts = sorted(
            [s for s in all_summaries if s.direction == Direction.SHORT],
            key=lambda s: s.composite_score,
            reverse=True,
        )[:limit]

        # Market bias
        total_long_score = sum(s.composite_score for s in all_summaries if s.direction == Direction.LONG)
        total_short_score = sum(s.composite_score for s in all_summaries if s.direction == Direction.SHORT)
        net = total_long_score - total_short_score
        bias = Direction.LONG if net >= 0 else Direction.SHORT
        bias_score = abs(net) / max(total_long_score + total_short_score, 0.01)

        # Per-market stats
        by_market: Dict[str, Dict[str, Any]] = {}
        for summary in all_summaries:
            mkt = summary.market.value if isinstance(summary.market, Market) else summary.market
            if mkt not in by_market:
                by_market[mkt] = {"long_count": 0, "short_count": 0, "total_score": 0.0}
            if summary.direction == Direction.LONG:
                by_market[mkt]["long_count"] += 1
            else:
                by_market[mkt]["short_count"] += 1
            by_market[mkt]["total_score"] += summary.composite_score

        total_signals = sum(len(sigs) for sigs in self._buffer.values())

        return AggregationReport(
            timestamp=datetime.now(timezone.utc),
            total_signals=total_signals,
            total_assets=len(all_summaries),
            top_longs=longs,
            top_shorts=shorts,
            market_bias=bias,
            market_bias_score=round(bias_score, 4),
            by_market=by_market,
        )

    def top_signals(
        self,
        direction: Optional[Direction] = None,
        market: Optional[Market] = None,
        limit: int = 10,
    ) -> List[AssetSignalSummary]:
        """Get top-ranked asset summaries, optionally filtered."""
        self._evict_stale()

        summaries = []
        for asset, signals in self._buffer.items():
            if not signals:
                continue
            if market:
                signals = [s for s in signals if s.market == market]
            if not signals:
                continue
            summary = self._build_asset_summary(asset, signals)
            if direction and summary.direction != direction:
                continue
            if abs(summary.composite_score) >= self._config.min_composite_score:
                summaries.append(summary)

        summaries.sort(key=lambda s: s.composite_score, reverse=True)
        return summaries[:limit]

    def get_asset_signals(self, asset: str) -> Optional[AssetSignalSummary]:
        """Get the aggregated summary for a specific asset."""
        signals = self._buffer.get(asset, [])
        if not signals:
            return None
        return self._build_asset_summary(asset, signals)

    def signal_count(self) -> int:
        """Total signals currently in buffer."""
        return sum(len(sigs) for sigs in self._buffer.values())

    def asset_count(self) -> int:
        """Number of unique assets with signals."""
        return len([k for k, v in self._buffer.items() if v])

    def clear(self) -> None:
        """Clear all signals from the buffer."""
        self._buffer.clear()
        self._total_ingested = 0

    @property
    def total_ingested(self) -> int:
        """Total signals ingested since creation / last clear."""
        return self._total_ingested

    # ── Internal ─────────────────────────────────────────────────────

    def _is_duplicate(self, signal: UnifiedSignal) -> bool:
        """Check if a near-identical signal already exists in the buffer."""
        existing = self._buffer.get(signal.asset, [])
        window = timedelta(seconds=self._config.dedup_window_seconds)

        for existing_sig in existing:
            # Same source + same direction + within time window
            if (
                existing_sig.source == signal.source
                and existing_sig.direction == signal.direction
                and abs((existing_sig.timestamp - signal.timestamp).total_seconds())
                < window.total_seconds()
            ):
                return True
        return False

    def _evict_stale(self) -> None:
        """Remove signals older than max_signal_age_seconds."""
        cutoff = datetime.now(timezone.utc) - timedelta(
            seconds=self._config.max_signal_age_seconds
        )
        for asset in list(self._buffer.keys()):
            self._buffer[asset] = [
                s for s in self._buffer[asset] if s.timestamp >= cutoff
            ]
            if not self._buffer[asset]:
                del self._buffer[asset]

    def _build_asset_summary(
        self, asset: str, signals: List[UnifiedSignal]
    ) -> AssetSignalSummary:
        """Build a weighted summary for one asset's signals."""
        cfg = self._config

        long_score = 0.0
        short_score = 0.0
        long_count = 0
        short_count = 0
        type_counts: Dict[str, int] = defaultdict(int)
        sources: List[str] = []
        strongest: Optional[UnifiedSignal] = None
        strongest_weight = 0.0

        for sig in signals:
            # Source reliability weight
            source_w = cfg.source_weights.get(sig.source, cfg.default_source_weight)

            # Signal type weight
            st_val = sig.signal_type.value if isinstance(sig.signal_type, SignalType) else sig.signal_type
            type_w = cfg.signal_type_weights.get(st_val, 0.5)

            # Combined weight
            weight = sig.strength * sig.confidence * source_w * type_w

            if sig.direction == Direction.LONG:
                long_score += weight
                long_count += 1
            else:
                short_score += weight
                short_count += 1

            type_counts[st_val] = type_counts.get(st_val, 0) + 1
            sources.append(sig.source)

            if weight > strongest_weight:
                strongest_weight = weight
                strongest = sig

        # Conflict penalty: when both LONG and SHORT signals exist
        if long_count > 0 and short_count > 0:
            minority = min(long_score, short_score)
            long_score -= minority * cfg.conflict_penalty
            short_score -= minority * cfg.conflict_penalty

        net_score = long_score - short_score
        direction = Direction.LONG if net_score >= 0 else Direction.SHORT
        composite = max(long_score, short_score)

        # Dominant signal type
        dominant_type_str = max(type_counts, key=type_counts.get) if type_counts else SignalType.TECHNICAL.value
        try:
            dominant_type = SignalType(dominant_type_str)
        except ValueError:
            dominant_type = SignalType.TECHNICAL

        # Market from strongest signal
        market = strongest.market if strongest else Market.A_SHARE
        if isinstance(market, str):
            try:
                market = Market(market)
            except ValueError:
                market = Market.A_SHARE

        unique_sources = sorted(set(sources))

        return AssetSignalSummary(
            asset=asset,
            market=market,
            direction=direction,
            composite_score=round(composite, 4),
            net_score=round(net_score, 4),
            signal_count=len(signals),
            long_signals=long_count,
            short_signals=short_count,
            dominant_type=dominant_type,
            sources=unique_sources,
            top_signal=strongest,
            all_signals=signals,
            last_updated=max(s.timestamp for s in signals),
        )
