"""NarrativeDetector — converts park-intel SENTIMENT events to UnifiedSignals.

Maps topic_heat momentum (accelerating / decelerating) to per-ticker
signals using TAG_TICKER_MAP from narrative_mapping.
"""

from __future__ import annotations

from typing import List

from src.perception.detectors.base import Detector
from src.perception.events import EventType, RawMarketEvent
from src.perception.signals import Direction, Market, SignalType, UnifiedSignal
from src.utils.logging import get_logger

logger = get_logger(__name__)


# Market mapping for signal generation
_CN_CONCEPT_MARKET = Market.A_SHARE
_US_TICKER_MARKET = Market.US_STOCK


class NarrativeDetector(Detector):
    """Detect narrative momentum signals from park-intel topic_heat.

    Accepts SENTIMENT events produced by QualitativeSource.
    For each accelerating/decelerating tag, generates one UnifiedSignal
    per associated ticker/concept.
    """

    @property
    def name(self) -> str:
        return "narrative"

    @property
    def accepts(self) -> List[EventType]:
        return [EventType.SENTIMENT]

    def detect(self, event: RawMarketEvent) -> List[UnifiedSignal]:
        data = event.data or {}
        momentum_label = data.get("momentum_label", "stable")

        if momentum_label == "stable":
            return []

        tag = data.get("tag", "")
        momentum = data.get("momentum", 0)
        us_tickers = data.get("us_tickers", [])
        cn_concepts = data.get("cn_concepts", [])

        if not us_tickers and not cn_concepts:
            return []

        # Direction from momentum
        if momentum_label == "accelerating":
            direction = Direction.LONG
        elif momentum_label == "decelerating":
            direction = Direction.SHORT
        else:
            return []

        strength = min(abs(momentum) * 0.3, 0.8)
        confidence = 0.55

        base_meta = {
            "tag": tag,
            "momentum": momentum,
            "momentum_label": momentum_label,
            "source": "park-intel",
        }

        signals: List[UnifiedSignal] = []

        # US tickers
        for ticker in us_tickers:
            signals.append(
                UnifiedSignal(
                    market=_US_TICKER_MARKET,
                    asset=ticker,
                    direction=direction,
                    strength=strength,
                    confidence=confidence,
                    signal_type=SignalType.SENTIMENT,
                    source="narrative/topic_heat",
                    timestamp=event.timestamp,
                    metadata={**base_meta, "asset_type": "us_ticker"},
                )
            )

        # CN concepts
        for concept in cn_concepts:
            signals.append(
                UnifiedSignal(
                    market=_CN_CONCEPT_MARKET,
                    asset=concept,
                    direction=direction,
                    strength=strength,
                    confidence=confidence,
                    signal_type=SignalType.SENTIMENT,
                    source="narrative/topic_heat",
                    timestamp=event.timestamp,
                    metadata={**base_meta, "asset_type": "cn_concept"},
                )
            )

        return signals
