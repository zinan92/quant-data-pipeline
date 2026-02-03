"""Market Context — build a high-level market context from perception data.

Provides a ``MarketContext`` object that can be injected into the
trading-agents analysis pipeline to give it situational awareness:

- Overall market sentiment (bullish / bearish / neutral)
- Sector rotation signals
- Key risk factors (limit-down count, divergence alerts, etc.)

Usage::

    builder = MarketContextBuilder()
    ctx = builder.build(scan_result)
    print(ctx.sentiment, ctx.risk_level)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from src.perception.aggregator import AggregationReport, AssetSignalSummary
from src.perception.pipeline import ScanResult
from src.perception.signals import Direction, Market, SignalType, UnifiedSignal

logger = logging.getLogger(__name__)


# ── Enums & Models ───────────────────────────────────────────────────


class MarketSentiment(str, Enum):
    STRONGLY_BULLISH = "strongly_bullish"
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"
    STRONGLY_BEARISH = "strongly_bearish"


class RiskLevel(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    EXTREME = "extreme"


@dataclass
class SectorSignal:
    """Rotation signal for a single sector / concept."""

    sector: str
    direction: str        # "inflow" / "outflow"
    strength: float       # 0–1
    signal_count: int
    top_assets: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sector": self.sector,
            "direction": self.direction,
            "strength": round(self.strength, 4),
            "signal_count": self.signal_count,
            "top_assets": self.top_assets,
        }


@dataclass
class RiskFactor:
    """A single identified risk factor."""

    name: str
    severity: str  # "low", "moderate", "high", "extreme"
    description: str
    value: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "name": self.name,
            "severity": self.severity,
            "description": self.description,
        }
        if self.value is not None:
            d["value"] = self.value
        return d


@dataclass
class MarketContext:
    """Snapshot of overall market conditions from perception data."""

    timestamp: datetime
    sentiment: MarketSentiment
    sentiment_score: float          # -1 (max bearish) to +1 (max bullish)
    risk_level: RiskLevel
    risk_factors: List[RiskFactor]
    sector_signals: List[SectorSignal]
    active_assets: int
    total_signals: int
    long_count: int
    short_count: int
    market_stats: Dict[str, Dict[str, Any]]  # per-market breakdown

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "sentiment": self.sentiment.value,
            "sentiment_score": round(self.sentiment_score, 4),
            "risk_level": self.risk_level.value,
            "risk_factors": [rf.to_dict() for rf in self.risk_factors],
            "sector_signals": [ss.to_dict() for ss in self.sector_signals],
            "active_assets": self.active_assets,
            "total_signals": self.total_signals,
            "long_count": self.long_count,
            "short_count": self.short_count,
            "market_stats": self.market_stats,
        }


# ── Configuration ────────────────────────────────────────────────────


@dataclass
class ContextConfig:
    """Tuneable knobs for context building."""

    # Sentiment thresholds (applied to bias_score * sign)
    strongly_bullish_threshold: float = 0.6
    bullish_threshold: float = 0.2
    bearish_threshold: float = -0.2
    strongly_bearish_threshold: float = -0.6

    # Risk: number of short signals that bump risk level
    high_risk_short_count: int = 5
    extreme_risk_short_count: int = 10

    # Sector analysis: minimum signals to consider a sector rotation
    min_sector_signals: int = 2


# ── Builder ──────────────────────────────────────────────────────────


class MarketContextBuilder:
    """Build a MarketContext from a ScanResult or AggregationReport.

    Usage::

        builder = MarketContextBuilder()
        ctx = builder.build(scan_result)
    """

    def __init__(self, config: Optional[ContextConfig] = None) -> None:
        self._config = config or ContextConfig()

    @property
    def config(self) -> ContextConfig:
        return self._config

    # ── Public API ───────────────────────────────────────────────────

    def build(self, scan_result: ScanResult) -> MarketContext:
        """Build context from a full ScanResult."""
        return self.from_report(scan_result.report)

    def from_report(self, report: AggregationReport) -> MarketContext:
        """Build context from an AggregationReport."""
        cfg = self._config
        now = datetime.now(timezone.utc)

        # ── Sentiment ────────────────────────────────────────────
        sentiment_score = self._compute_sentiment_score(report)
        sentiment = self._classify_sentiment(sentiment_score)

        # ── Counts ───────────────────────────────────────────────
        long_count = len(report.top_longs)
        short_count = len(report.top_shorts)

        # ── Risk factors ─────────────────────────────────────────
        risk_factors = self._identify_risk_factors(report, long_count, short_count)
        risk_level = self._classify_risk(risk_factors)

        # ── Sector rotation ──────────────────────────────────────
        sector_signals = self._extract_sector_signals(report)

        # ── Per-market stats ─────────────────────────────────────
        market_stats = dict(report.by_market)

        return MarketContext(
            timestamp=now,
            sentiment=sentiment,
            sentiment_score=sentiment_score,
            risk_level=risk_level,
            risk_factors=risk_factors,
            sector_signals=sector_signals,
            active_assets=report.total_assets,
            total_signals=report.total_signals,
            long_count=long_count,
            short_count=short_count,
            market_stats=market_stats,
        )

    # ── Internal ─────────────────────────────────────────────────────

    def _compute_sentiment_score(self, report: AggregationReport) -> float:
        """Derive a -1..+1 sentiment score from the aggregation report."""
        # Use market_bias_score with sign from market_bias direction
        sign = 1.0 if report.market_bias == Direction.LONG else -1.0
        raw = sign * report.market_bias_score

        # Clamp
        return max(-1.0, min(1.0, raw))

    def _classify_sentiment(self, score: float) -> MarketSentiment:
        cfg = self._config
        if score >= cfg.strongly_bullish_threshold:
            return MarketSentiment.STRONGLY_BULLISH
        elif score >= cfg.bullish_threshold:
            return MarketSentiment.BULLISH
        elif score <= cfg.strongly_bearish_threshold:
            return MarketSentiment.STRONGLY_BEARISH
        elif score <= cfg.bearish_threshold:
            return MarketSentiment.BEARISH
        return MarketSentiment.NEUTRAL

    def _identify_risk_factors(
        self,
        report: AggregationReport,
        long_count: int,
        short_count: int,
    ) -> List[RiskFactor]:
        """Scan the report for risk factors."""
        cfg = self._config
        factors: List[RiskFactor] = []

        # 1. Many short signals → bearish pressure
        if short_count >= cfg.extreme_risk_short_count:
            factors.append(RiskFactor(
                name="mass_bearish_signals",
                severity="extreme",
                description=f"{short_count} short signals detected — extreme bearish pressure",
                value=float(short_count),
            ))
        elif short_count >= cfg.high_risk_short_count:
            factors.append(RiskFactor(
                name="elevated_bearish_signals",
                severity="high",
                description=f"{short_count} short signals detected — significant bearish pressure",
                value=float(short_count),
            ))

        # 2. Low long-to-short ratio
        total = long_count + short_count
        if total > 0:
            long_ratio = long_count / total
            if long_ratio < 0.3:
                factors.append(RiskFactor(
                    name="low_long_ratio",
                    severity="high",
                    description=f"Only {long_ratio:.0%} of signals are bullish — market breadth is weak",
                    value=long_ratio,
                ))

        # 3. Check for concentrated short signals in specific markets
        for mkt, stats in report.by_market.items():
            sc = stats.get("short_count", 0)
            lc = stats.get("long_count", 0)
            if sc > 0 and lc == 0:
                factors.append(RiskFactor(
                    name=f"no_bullish_in_{mkt}",
                    severity="moderate",
                    description=f"No bullish signals in {mkt} market ({sc} bearish only)",
                    value=float(sc),
                ))

        # 4. Strong one-sided bias can itself be risky (overheating)
        if report.market_bias_score > 0.8 and long_count > 8:
            factors.append(RiskFactor(
                name="overheated_bullish",
                severity="moderate",
                description="Very strong bullish consensus — potential overheating",
                value=report.market_bias_score,
            ))

        # 5. Divergence: lots of signals but no clear direction
        if total >= 6 and abs(long_count - short_count) <= 1:
            factors.append(RiskFactor(
                name="signal_divergence",
                severity="moderate",
                description=f"Even split ({long_count}L/{short_count}S) — high uncertainty",
            ))

        return factors

    def _classify_risk(self, factors: List[RiskFactor]) -> RiskLevel:
        """Determine overall risk level from individual factors."""
        if not factors:
            return RiskLevel.LOW

        severities = [f.severity for f in factors]
        if "extreme" in severities:
            return RiskLevel.EXTREME
        if severities.count("high") >= 2:
            return RiskLevel.EXTREME
        if "high" in severities:
            return RiskLevel.HIGH
        if "moderate" in severities:
            return RiskLevel.MODERATE
        return RiskLevel.LOW

    def _extract_sector_signals(
        self, report: AggregationReport
    ) -> List[SectorSignal]:
        """Extract sector rotation signals from the report.

        Looks at signal metadata for sector/concept information
        and groups them to detect rotational patterns.
        """
        cfg = self._config
        sector_data: Dict[str, Dict[str, Any]] = {}

        all_summaries = list(report.top_longs) + list(report.top_shorts)
        for summary in all_summaries:
            # Try to extract sector info from signal sources
            for sig in summary.all_signals:
                sector = sig.metadata.get("sector") or sig.metadata.get("concept")
                if not sector:
                    continue

                if sector not in sector_data:
                    sector_data[sector] = {
                        "long_strength": 0.0,
                        "short_strength": 0.0,
                        "count": 0,
                        "assets": set(),
                    }
                sd = sector_data[sector]
                sd["count"] += 1
                sd["assets"].add(summary.asset)
                if sig.direction == Direction.LONG or sig.direction == "long":
                    sd["long_strength"] += sig.strength * sig.confidence
                else:
                    sd["short_strength"] += sig.strength * sig.confidence

        # Build sector signals
        result: List[SectorSignal] = []
        for sector, sd in sector_data.items():
            if sd["count"] < cfg.min_sector_signals:
                continue

            net = sd["long_strength"] - sd["short_strength"]
            direction = "inflow" if net >= 0 else "outflow"
            strength = abs(net) / max(sd["long_strength"] + sd["short_strength"], 0.01)

            result.append(SectorSignal(
                sector=sector,
                direction=direction,
                strength=min(strength, 1.0),
                signal_count=sd["count"],
                top_assets=sorted(sd["assets"])[:5],
            ))

        # Sort by strength descending
        result.sort(key=lambda s: s.strength, reverse=True)
        return result
