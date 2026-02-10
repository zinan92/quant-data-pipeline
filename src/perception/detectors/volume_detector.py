"""VolumeDetector -- volume anomaly detection for market events.

Detects:
1. Volume surge          — current volume > N× rolling average
2. Volume-price diverge  — price up + volume shrink, or price down + volume surge
3. Volume climax         — extreme volume spike at trend exhaustion
4. Shrinkage pattern     — unusually low volume (potential consolidation)
5. Volume trend          — progressive volume expansion or contraction

Accepts event types: KLINE, PRICE_UPDATE

Stateless detector. Each event must carry ``data["bars"]`` with
``close`` and ``volume`` fields, ordered oldest → newest.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.perception.detectors.base import Detector
from src.perception.events import EventType, RawMarketEvent
from src.perception.signals import (
    Direction,
    Market,
    SignalType,
    UnifiedSignal,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)


# ── Configuration ────────────────────────────────────────────────────


@dataclass
class VolumeDetectorConfig:
    """Tuneable thresholds for VolumeDetector."""

    # Volume surge
    surge_ratio: float = 2.0          # current / avg >= N triggers surge
    extreme_surge_ratio: float = 4.0  # extreme level
    avg_period: int = 20              # rolling average lookback

    # Volume-price divergence
    divergence_price_threshold: float = 1.0  # minimum price change % to consider
    divergence_vol_ratio_low: float = 0.6    # volume < 60% avg → shrinkage
    divergence_vol_ratio_high: float = 1.5   # volume > 150% avg → expansion

    # Shrinkage
    shrinkage_ratio: float = 0.5      # current / avg < 0.5 → shrinkage
    extreme_shrinkage_ratio: float = 0.3

    # Climax
    climax_vol_ratio: float = 3.0     # volume 3x+ avg
    climax_price_reversal_pct: float = 2.0  # close far from high/low

    # Volume trend
    trend_lookback: int = 5           # bars to check for progressive trend
    trend_min_ratio: float = 1.3      # each bar > 130% of prior for expansion

    # General
    base_confidence: float = 0.6


# ── Detector ─────────────────────────────────────────────────────────


class VolumeDetector(Detector):
    """Stateless volume anomaly detector.

    Each event must carry ``data["bars"]`` — list of bar dicts with
    at least ``close`` and ``volume``.  Bars ordered oldest → newest.
    """

    _ACCEPTED = [EventType.KLINE, EventType.PRICE_UPDATE]

    def __init__(self, config: Optional[VolumeDetectorConfig] = None) -> None:
        self._config = config or VolumeDetectorConfig()

    @property
    def name(self) -> str:
        return "volume"

    @property
    def accepts(self) -> List[EventType]:
        return list(self._ACCEPTED)

    # ── public API ───────────────────────────────────────────────────

    def detect(self, event: RawMarketEvent) -> List[UnifiedSignal]:
        bars: List[Dict[str, Any]] = (event.data or {}).get("bars", [])
        if not bars:
            return []

        asset = event.symbol or "UNKNOWN"
        market = self._resolve_market(event)
        ts = event.timestamp

        closes = [float(b["close"]) for b in bars if "close" in b]
        volumes = [float(b["volume"]) for b in bars if "volume" in b]

        if len(closes) < 2 or len(volumes) < 2:
            return []

        signals: List[UnifiedSignal] = []

        try:
            signals.extend(self._detect_surge(volumes, closes, asset, market, ts))
        except Exception:
            logger.exception("Volume surge detection error for %s", asset)

        try:
            signals.extend(self._detect_divergence(volumes, closes, asset, market, ts))
        except Exception:
            logger.exception("Volume-price divergence error for %s", asset)

        try:
            signals.extend(self._detect_climax(bars, volumes, closes, asset, market, ts))
        except Exception:
            logger.exception("Volume climax detection error for %s", asset)

        try:
            signals.extend(self._detect_shrinkage(volumes, closes, asset, market, ts))
        except Exception:
            logger.exception("Volume shrinkage detection error for %s", asset)

        try:
            signals.extend(self._detect_volume_trend(volumes, closes, asset, market, ts))
        except Exception:
            logger.exception("Volume trend detection error for %s", asset)

        return signals

    # ── Sub-detectors ────────────────────────────────────────────────

    def _detect_surge(
        self,
        volumes: List[float],
        closes: List[float],
        asset: str,
        market: Market,
        ts,
    ) -> List[UnifiedSignal]:
        """Detect volume surges relative to rolling average."""
        cfg = self._config

        if len(volumes) < cfg.avg_period + 1:
            return []

        avg = sum(volumes[-(cfg.avg_period + 1):-1]) / cfg.avg_period
        if avg <= 0:
            return []

        ratio = volumes[-1] / avg
        if ratio < cfg.surge_ratio:
            return []

        # Direction from price change
        change_pct = (closes[-1] - closes[-2]) / closes[-2] * 100 if closes[-2] > 0 else 0
        direction = Direction.LONG if change_pct >= 0 else Direction.SHORT

        is_extreme = ratio >= cfg.extreme_surge_ratio
        strength = min(1.0, 0.4 + (ratio - cfg.surge_ratio) / 5.0)
        confidence = cfg.base_confidence + (0.15 if is_extreme else 0.05)

        label = "extreme_surge" if is_extreme else "surge"

        return [
            UnifiedSignal(
                market=market,
                asset=asset,
                direction=direction,
                strength=round(max(0.1, strength), 4),
                confidence=round(min(1.0, confidence), 4),
                signal_type=SignalType.FLOW,
                source=f"volume/{label}",
                timestamp=ts,
                metadata={
                    "detector": "volume",
                    "sub_type": label,
                    "volume_ratio": round(ratio, 2),
                    "current_volume": volumes[-1],
                    "avg_volume": round(avg, 2),
                    "change_pct": round(change_pct, 2),
                    "is_extreme": is_extreme,
                },
            )
        ]

    def _detect_divergence(
        self,
        volumes: List[float],
        closes: List[float],
        asset: str,
        market: Market,
        ts,
    ) -> List[UnifiedSignal]:
        """Detect volume-price divergence patterns.

        Key patterns:
        - Price up + volume shrink → bearish divergence (weak rally)
        - Price down + volume shrink → potential bottom (selling exhaustion)
        - Price up + volume surge → bullish confirmation
        - Price down + volume surge → panic selling / capitulation
        """
        cfg = self._config

        if len(volumes) < cfg.avg_period + 1 or len(closes) < 2:
            return []

        avg_vol = sum(volumes[-(cfg.avg_period + 1):-1]) / cfg.avg_period
        if avg_vol <= 0:
            return []

        vol_ratio = volumes[-1] / avg_vol
        change_pct = (closes[-1] - closes[-2]) / closes[-2] * 100 if closes[-2] > 0 else 0

        if abs(change_pct) < cfg.divergence_price_threshold:
            return []

        signals: List[UnifiedSignal] = []

        # Price up + volume shrink → bearish divergence
        if change_pct > 0 and vol_ratio < cfg.divergence_vol_ratio_low:
            strength = min(1.0, 0.4 + (cfg.divergence_vol_ratio_low - vol_ratio) * 2)
            signals.append(
                UnifiedSignal(
                    market=market,
                    asset=asset,
                    direction=Direction.SHORT,
                    strength=round(max(0.1, strength), 4),
                    confidence=round(cfg.base_confidence + 0.05, 4),
                    signal_type=SignalType.TECHNICAL,
                    source="volume/bearish_divergence",
                    timestamp=ts,
                    metadata={
                        "detector": "volume",
                        "sub_type": "bearish_divergence",
                        "pattern": "price_up_volume_down",
                        "change_pct": round(change_pct, 2),
                        "volume_ratio": round(vol_ratio, 2),
                    },
                )
            )

        # Price down + volume shrink → selling exhaustion (potential bottom)
        elif change_pct < 0 and vol_ratio < cfg.divergence_vol_ratio_low:
            strength = min(1.0, 0.3 + (cfg.divergence_vol_ratio_low - vol_ratio) * 1.5)
            signals.append(
                UnifiedSignal(
                    market=market,
                    asset=asset,
                    direction=Direction.LONG,
                    strength=round(max(0.1, strength), 4),
                    confidence=round(cfg.base_confidence, 4),
                    signal_type=SignalType.TECHNICAL,
                    source="volume/selling_exhaustion",
                    timestamp=ts,
                    metadata={
                        "detector": "volume",
                        "sub_type": "selling_exhaustion",
                        "pattern": "price_down_volume_down",
                        "change_pct": round(change_pct, 2),
                        "volume_ratio": round(vol_ratio, 2),
                    },
                )
            )

        # Price down + volume surge → panic / capitulation
        elif change_pct < 0 and vol_ratio >= cfg.divergence_vol_ratio_high:
            strength = min(1.0, 0.5 + (vol_ratio - cfg.divergence_vol_ratio_high) / 3.0)
            signals.append(
                UnifiedSignal(
                    market=market,
                    asset=asset,
                    direction=Direction.SHORT,
                    strength=round(max(0.1, strength), 4),
                    confidence=round(cfg.base_confidence + 0.1, 4),
                    signal_type=SignalType.FLOW,
                    source="volume/panic_selling",
                    timestamp=ts,
                    metadata={
                        "detector": "volume",
                        "sub_type": "panic_selling",
                        "pattern": "price_down_volume_up",
                        "change_pct": round(change_pct, 2),
                        "volume_ratio": round(vol_ratio, 2),
                    },
                )
            )

        return signals

    def _detect_climax(
        self,
        bars: List[Dict[str, Any]],
        volumes: List[float],
        closes: List[float],
        asset: str,
        market: Market,
        ts,
    ) -> List[UnifiedSignal]:
        """Detect volume climax — extreme volume + price reversal candle.

        A climax occurs when volume is extremely high and the candle
        shows signs of reversal (long wick, close far from extreme).
        """
        cfg = self._config

        if len(volumes) < cfg.avg_period + 1 or len(bars) < 2:
            return []

        avg_vol = sum(volumes[-(cfg.avg_period + 1):-1]) / cfg.avg_period
        if avg_vol <= 0:
            return []

        vol_ratio = volumes[-1] / avg_vol
        if vol_ratio < cfg.climax_vol_ratio:
            return []

        today = bars[-1]
        high = float(today.get("high", 0))
        low = float(today.get("low", 0))
        close = float(today.get("close", 0))
        open_p = float(today.get("open", 0))
        bar_range = high - low

        if bar_range <= 0 or close <= 0:
            return []

        # Check for reversal character
        change_pct = (close - closes[-2]) / closes[-2] * 100 if closes[-2] > 0 else 0

        # Bullish climax: big volume + closing near high after drop = reversal
        # Bearish climax: big volume + closing near low after rise = reversal
        upper_wick = high - max(open_p, close)
        lower_wick = min(open_p, close) - low
        body = abs(close - open_p)

        signals: List[UnifiedSignal] = []

        # Bearish climax: surge volume + long upper wick
        if upper_wick > body and upper_wick > lower_wick and change_pct > 0:
            reversal_score = upper_wick / bar_range
            strength = min(1.0, 0.5 + reversal_score * 0.3 + (vol_ratio - cfg.climax_vol_ratio) / 5.0)
            signals.append(
                UnifiedSignal(
                    market=market,
                    asset=asset,
                    direction=Direction.SHORT,
                    strength=round(max(0.1, strength), 4),
                    confidence=round(cfg.base_confidence + 0.1, 4),
                    signal_type=SignalType.TECHNICAL,
                    source="volume/bearish_climax",
                    timestamp=ts,
                    metadata={
                        "detector": "volume",
                        "sub_type": "bearish_climax",
                        "volume_ratio": round(vol_ratio, 2),
                        "upper_wick_ratio": round(upper_wick / bar_range, 2),
                        "change_pct": round(change_pct, 2),
                    },
                )
            )

        # Bullish climax: surge volume + long lower wick
        elif lower_wick > body and lower_wick > upper_wick and change_pct < 0:
            reversal_score = lower_wick / bar_range
            strength = min(1.0, 0.5 + reversal_score * 0.3 + (vol_ratio - cfg.climax_vol_ratio) / 5.0)
            signals.append(
                UnifiedSignal(
                    market=market,
                    asset=asset,
                    direction=Direction.LONG,
                    strength=round(max(0.1, strength), 4),
                    confidence=round(cfg.base_confidence + 0.1, 4),
                    signal_type=SignalType.TECHNICAL,
                    source="volume/bullish_climax",
                    timestamp=ts,
                    metadata={
                        "detector": "volume",
                        "sub_type": "bullish_climax",
                        "volume_ratio": round(vol_ratio, 2),
                        "lower_wick_ratio": round(lower_wick / bar_range, 2),
                        "change_pct": round(change_pct, 2),
                    },
                )
            )

        return signals

    def _detect_shrinkage(
        self,
        volumes: List[float],
        closes: List[float],
        asset: str,
        market: Market,
        ts,
    ) -> List[UnifiedSignal]:
        """Detect unusually low volume — potential consolidation / breakout setup."""
        cfg = self._config

        if len(volumes) < cfg.avg_period + 1:
            return []

        avg = sum(volumes[-(cfg.avg_period + 1):-1]) / cfg.avg_period
        if avg <= 0:
            return []

        ratio = volumes[-1] / avg
        if ratio >= cfg.shrinkage_ratio:
            return []

        is_extreme = ratio <= cfg.extreme_shrinkage_ratio
        strength = min(1.0, 0.3 + (cfg.shrinkage_ratio - ratio) * 2)
        confidence = cfg.base_confidence - 0.05

        # Shrinkage is market-neutral — it signals consolidation
        # Direction hint from recent price change
        change_pct = (closes[-1] - closes[-2]) / closes[-2] * 100 if closes[-2] > 0 else 0
        direction = Direction.LONG if change_pct >= 0 else Direction.SHORT

        label = "extreme_shrinkage" if is_extreme else "shrinkage"

        return [
            UnifiedSignal(
                market=market,
                asset=asset,
                direction=direction,
                strength=round(max(0.1, strength), 4),
                confidence=round(max(0.0, confidence), 4),
                signal_type=SignalType.FLOW,
                source=f"volume/{label}",
                timestamp=ts,
                metadata={
                    "detector": "volume",
                    "sub_type": label,
                    "volume_ratio": round(ratio, 2),
                    "current_volume": volumes[-1],
                    "avg_volume": round(avg, 2),
                    "is_extreme": is_extreme,
                    "note": "Low volume → consolidation, watch for breakout",
                },
            )
        ]

    def _detect_volume_trend(
        self,
        volumes: List[float],
        closes: List[float],
        asset: str,
        market: Market,
        ts,
    ) -> List[UnifiedSignal]:
        """Detect progressive volume expansion or contraction over N bars."""
        cfg = self._config

        if len(volumes) < cfg.trend_lookback + 1:
            return []

        recent = volumes[-(cfg.trend_lookback + 1):]
        signals: List[UnifiedSignal] = []

        # Check for progressive expansion
        expanding = True
        for i in range(1, len(recent)):
            if recent[i - 1] <= 0 or recent[i] / recent[i - 1] < cfg.trend_min_ratio:
                expanding = False
                break

        if expanding:
            expansion_ratio = recent[-1] / recent[0] if recent[0] > 0 else 0
            change_pct = (closes[-1] - closes[-2]) / closes[-2] * 100 if closes[-2] > 0 else 0
            direction = Direction.LONG if change_pct >= 0 else Direction.SHORT
            strength = min(1.0, 0.4 + expansion_ratio / 10.0)

            signals.append(
                UnifiedSignal(
                    market=market,
                    asset=asset,
                    direction=direction,
                    strength=round(max(0.1, strength), 4),
                    confidence=round(cfg.base_confidence + 0.05, 4),
                    signal_type=SignalType.FLOW,
                    source="volume/progressive_expansion",
                    timestamp=ts,
                    metadata={
                        "detector": "volume",
                        "sub_type": "progressive_expansion",
                        "expansion_ratio": round(expansion_ratio, 2),
                        "trend_bars": cfg.trend_lookback,
                    },
                )
            )

        # Check for progressive contraction
        contracting = True
        for i in range(1, len(recent)):
            if recent[i - 1] <= 0 or recent[i] / recent[i - 1] > 1.0 / cfg.trend_min_ratio:
                contracting = False
                break

        if contracting:
            contraction_ratio = recent[-1] / recent[0] if recent[0] > 0 else 1.0
            strength = min(1.0, 0.3 + (1.0 - contraction_ratio) * 2)
            # Contraction is neutral — signals building energy
            direction = Direction.LONG  # default to LONG (setup for breakout)

            signals.append(
                UnifiedSignal(
                    market=market,
                    asset=asset,
                    direction=direction,
                    strength=round(max(0.1, strength), 4),
                    confidence=round(cfg.base_confidence - 0.05, 4),
                    signal_type=SignalType.FLOW,
                    source="volume/progressive_contraction",
                    timestamp=ts,
                    metadata={
                        "detector": "volume",
                        "sub_type": "progressive_contraction",
                        "contraction_ratio": round(contraction_ratio, 2),
                        "trend_bars": cfg.trend_lookback,
                        "note": "Volume contracting — energy building, watch for breakout",
                    },
                )
            )

        return signals

    # ── helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _resolve_market(event: RawMarketEvent) -> Market:
        scope = str(event.market).lower()
        if "cn" in scope or "a_share" in scope:
            return Market.A_SHARE
        if "us" in scope:
            return Market.US_STOCK
        if "crypto" in scope:
            return Market.CRYPTO
        if "commodity" in scope:
            return Market.COMMODITY
        return Market.A_SHARE
