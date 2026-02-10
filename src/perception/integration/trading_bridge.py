"""Trading Bridge — translates Perception signals into trading-agents format.

Maps Perception's UnifiedSignal / AggregationReport into a flat list of
TradingSignal objects that the trading-agents decision engine can consume
directly.

Key responsibilities:
- Map signal directions to trading actions (LONG / SHORT / WAIT)
- Apply confidence thresholds (drop low-confidence noise)
- Aggregate conflicting signals per asset
- Provide a clean API:  ``get_trading_signals(scan_result) -> List[TradingSignal]``
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from src.perception.aggregator import AggregationReport, AssetSignalSummary
from src.perception.pipeline import ScanResult
from src.perception.signals import Direction, Market, SignalType, UnifiedSignal
from src.utils.logging import get_logger

logger = get_logger(__name__)


# ── Enums & Models ───────────────────────────────────────────────────


class TradingAction(str, Enum):
    """Action the trading-agents pipeline should take."""

    LONG = "long"
    SHORT = "short"
    WAIT = "wait"


@dataclass
class TradingSignal:
    """A trading-ready signal compatible with trading-agents' PipelineSignal.

    Fields are deliberately aligned with
    ``trading-agents/src/pipeline/signal.py::PipelineSignal``.
    """

    signal_type: str           # e.g. "perception/technical", "perception/flow"
    asset: str                 # ticker
    action: TradingAction      # LONG / SHORT / WAIT
    direction: str             # "bullish" / "bearish" / "neutral"
    strength: float            # 0.0 – 1.0
    confidence: float          # 0.0 – 1.0
    reason: str
    timestamp: float = 0.0     # epoch seconds
    metadata: Dict[str, Any] = field(default_factory=dict)

    # ── helpers ──────────────────────────────────────────────────

    @property
    def is_actionable(self) -> bool:
        return self.action != TradingAction.WAIT

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_type": self.signal_type,
            "asset": self.asset,
            "action": self.action.value,
            "direction": self.direction,
            "strength": round(self.strength, 4),
            "confidence": round(self.confidence, 4),
            "reason": self.reason,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


# ── Configuration ────────────────────────────────────────────────────


@dataclass
class BridgeConfig:
    """Tuneable knobs for the trading bridge."""

    # Minimum confidence to emit a LONG/SHORT (below → WAIT)
    min_confidence: float = 0.4

    # Minimum composite score from aggregator
    min_composite_score: float = 0.15

    # When conflicting signals exist for an asset and the net score is
    # below this fraction of the composite, emit WAIT.
    conflict_ratio_threshold: float = 0.3

    # Default expiry window for generated signals (seconds)
    default_expiry_seconds: float = 3600.0

    # Map perception source names to trading signal_type prefixes
    source_prefix: str = "perception"


# ── Bridge ───────────────────────────────────────────────────────────


class TradingBridge:
    """Bridge Perception → Trading-Agents.

    Usage::

        bridge = TradingBridge()
        result = await pipeline.scan()
        signals = bridge.get_trading_signals(result)
        for sig in signals:
            if sig.is_actionable:
                ...  # feed to trading-agents
    """

    def __init__(self, config: Optional[BridgeConfig] = None) -> None:
        self._config = config or BridgeConfig()

    @property
    def config(self) -> BridgeConfig:
        return self._config

    # ── Public API ───────────────────────────────────────────────────

    def get_trading_signals(self, scan_result: ScanResult) -> List[TradingSignal]:
        """Convert a ScanResult into a list of TradingSignals.

        This is the main entry point.  It extracts the aggregation
        report from a completed scan and translates each asset summary
        into a TradingSignal.
        """
        report = scan_result.report
        return self.from_report(report)

    def from_report(self, report: AggregationReport) -> List[TradingSignal]:
        """Convert an AggregationReport into TradingSignals."""
        signals: List[TradingSignal] = []

        # Process top longs
        for summary in report.top_longs:
            sig = self._translate_summary(summary)
            if sig is not None:
                signals.append(sig)

        # Process top shorts
        for summary in report.top_shorts:
            sig = self._translate_summary(summary)
            if sig is not None:
                signals.append(sig)

        logger.info(
            "Bridge produced %d trading signals (%d actionable) from report "
            "with %d assets",
            len(signals),
            sum(1 for s in signals if s.is_actionable),
            report.total_assets,
        )
        return signals

    def from_unified_signals(
        self, signals: List[UnifiedSignal]
    ) -> List[TradingSignal]:
        """Translate raw UnifiedSignals directly (without aggregation)."""
        out: List[TradingSignal] = []
        for sig in signals:
            if sig.is_expired:
                continue
            ts = self._translate_unified(sig)
            if ts is not None:
                out.append(ts)
        return out

    # ── Internal ─────────────────────────────────────────────────────

    def _translate_summary(
        self, summary: AssetSignalSummary
    ) -> Optional[TradingSignal]:
        """Translate one AssetSignalSummary into a TradingSignal."""
        cfg = self._config

        # Check composite score threshold
        if summary.composite_score < cfg.min_composite_score:
            return None

        # Determine action
        action = self._resolve_action(summary)

        # Build direction string for trading-agents compatibility
        direction = self._direction_string(summary.direction)

        # Determine dominant signal type for the signal_type field
        sig_type = f"{cfg.source_prefix}/{summary.dominant_type.value}"

        # Confidence = composite_score clamped to [0, 1]
        confidence = min(summary.composite_score, 1.0)

        # Build reason
        reason_parts = [
            f"{summary.signal_count} perception signal(s)",
            f"net_score={summary.net_score:.3f}",
            f"sources=[{', '.join(summary.sources[:5])}]",
        ]
        if summary.long_signals > 0 and summary.short_signals > 0:
            reason_parts.append(
                f"conflicting: {summary.long_signals}L/{summary.short_signals}S"
            )
        reason = "; ".join(reason_parts)

        ts_epoch = summary.last_updated.timestamp()

        return TradingSignal(
            signal_type=sig_type,
            asset=summary.asset,
            action=action,
            direction=direction,
            strength=min(summary.composite_score, 1.0),
            confidence=confidence,
            reason=reason,
            timestamp=ts_epoch,
            metadata={
                "market": summary.market.value if isinstance(summary.market, Market) else summary.market,
                "long_signals": summary.long_signals,
                "short_signals": summary.short_signals,
                "net_score": summary.net_score,
                "composite_score": summary.composite_score,
                "sources": summary.sources,
            },
        )

    def _translate_unified(self, sig: UnifiedSignal) -> Optional[TradingSignal]:
        """Translate a single UnifiedSignal into a TradingSignal."""
        cfg = self._config

        if sig.confidence < cfg.min_confidence:
            return None

        action = (
            TradingAction.LONG
            if sig.direction == Direction.LONG
            else TradingAction.SHORT
        )
        direction = self._direction_string(sig.direction)

        return TradingSignal(
            signal_type=f"{cfg.source_prefix}/{sig.signal_type}",
            asset=sig.asset,
            action=action,
            direction=direction,
            strength=sig.strength,
            confidence=sig.confidence,
            reason=f"Direct signal from {sig.source}",
            timestamp=sig.timestamp.timestamp(),
            metadata=sig.metadata,
        )

    def _resolve_action(self, summary: AssetSignalSummary) -> TradingAction:
        """Decide LONG/SHORT/WAIT from an asset summary."""
        cfg = self._config

        # If there's a strong conflict, WAIT
        if summary.long_signals > 0 and summary.short_signals > 0:
            total = summary.long_signals + summary.short_signals
            minority_ratio = min(summary.long_signals, summary.short_signals) / total
            if minority_ratio >= cfg.conflict_ratio_threshold:
                return TradingAction.WAIT

        # Check confidence via top_signal
        if summary.top_signal and summary.top_signal.confidence < cfg.min_confidence:
            return TradingAction.WAIT

        # Map direction
        if summary.direction == Direction.LONG:
            return TradingAction.LONG
        else:
            return TradingAction.SHORT

    @staticmethod
    def _direction_string(direction: Direction) -> str:
        """Convert Direction enum to trading-agents 'bullish'/'bearish' string."""
        if isinstance(direction, str):
            return "bullish" if direction == "long" else "bearish"
        return "bullish" if direction == Direction.LONG else "bearish"
