"""PriceDetector -- price-level signal detection for market events.

Detects:
1. Breakout signals    — new 52-week / N-day highs or lows
2. Gap signals         — gap-up / gap-down at open
3. Support/resistance  — price testing key levels (MA, round numbers)
4. Price momentum      — consecutive up/down days, acceleration

Accepts event types: KLINE, PRICE_UPDATE

Like TechnicalDetector, this detector is *stateless*.  Each event must
carry ``event.data["bars"]`` (list of OHLCV dicts, oldest → newest)
and optionally ``event.data["today"]`` for intraday context.
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
class PriceDetectorConfig:
    """Tuneable thresholds for PriceDetector."""

    # Breakout detection
    breakout_lookback_days: int = 250  # ~1 year for 52-week high/low
    short_breakout_days: int = 20     # 20-day breakout (1 month)
    near_high_pct: float = 0.98       # within 2% of high = "near high"

    # Gap detection
    gap_min_pct: float = 1.0          # minimum gap size (%)
    large_gap_pct: float = 3.0        # "large" gap threshold

    # Support/resistance
    round_number_tolerance_pct: float = 0.5  # within 0.5% of round number
    ma_test_tolerance_pct: float = 0.5       # within 0.5% of MA

    # Momentum
    min_consecutive_days: int = 3     # minimum streak to trigger
    acceleration_lookback: int = 5    # bars to measure acceleration

    # General
    base_confidence: float = 0.65


# ── Detector ─────────────────────────────────────────────────────────


class PriceDetector(Detector):
    """Stateless price-level detector.

    Each event must carry ``data["bars"]`` — a list of bar dicts with
    at least ``open``, ``high``, ``low``, ``close``.  Bars are ordered
    oldest → newest.
    """

    _ACCEPTED = [EventType.KLINE, EventType.PRICE_UPDATE]

    def __init__(self, config: Optional[PriceDetectorConfig] = None) -> None:
        self._config = config or PriceDetectorConfig()

    @property
    def name(self) -> str:
        return "price"

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

        signals: List[UnifiedSignal] = []

        try:
            signals.extend(self._detect_breakout(bars, asset, market, ts))
        except Exception:
            logger.exception("Breakout detection error for %s", asset)

        try:
            signals.extend(self._detect_gap(bars, asset, market, ts))
        except Exception:
            logger.exception("Gap detection error for %s", asset)

        try:
            signals.extend(self._detect_ma_support_resistance(bars, asset, market, ts))
        except Exception:
            logger.exception("MA support/resistance detection error for %s", asset)

        try:
            signals.extend(self._detect_momentum(bars, asset, market, ts))
        except Exception:
            logger.exception("Momentum detection error for %s", asset)

        return signals

    # ── Sub-detectors ────────────────────────────────────────────────

    def _detect_breakout(
        self,
        bars: List[Dict[str, Any]],
        asset: str,
        market: Market,
        ts,
    ) -> List[UnifiedSignal]:
        """Detect new N-day highs/lows and near-high conditions."""
        signals: List[UnifiedSignal] = []
        cfg = self._config

        if len(bars) < 2:
            return []

        current = bars[-1]
        cur_close = float(current.get("close", 0))
        cur_high = float(current.get("high", 0))
        cur_low = float(current.get("low", 0))

        if cur_close <= 0:
            return []

        # Check against different lookback windows
        for label, lookback in [
            ("52w", cfg.breakout_lookback_days),
            ("20d", cfg.short_breakout_days),
        ]:
            window = bars[-lookback:] if len(bars) >= lookback else bars
            if len(window) < 5:
                continue

            # Exclude the current bar for comparison
            prev_bars = window[:-1]
            prev_highs = [float(b.get("high", 0)) for b in prev_bars]
            prev_lows = [float(b.get("low", float("inf"))) for b in prev_bars]

            if not prev_highs or not prev_lows:
                continue

            period_high = max(prev_highs)
            period_low = min(prev_lows) if prev_lows else cur_low

            # New high breakout
            if period_high > 0 and cur_high > period_high:
                pct_above = (cur_high - period_high) / period_high * 100
                strength = min(1.0, 0.5 + pct_above / 5.0)
                signals.append(
                    UnifiedSignal(
                        market=market,
                        asset=asset,
                        direction=Direction.LONG,
                        strength=round(max(0.1, strength), 4),
                        confidence=cfg.base_confidence + (0.1 if label == "52w" else 0.0),
                        signal_type=SignalType.TECHNICAL,
                        source=f"price/breakout_{label}_high",
                        timestamp=ts,
                        metadata={
                            "detector": "price",
                            "sub_type": f"breakout_{label}_high",
                            "current_high": cur_high,
                            "period_high": period_high,
                            "pct_above": round(pct_above, 2),
                            "lookback_days": lookback,
                        },
                    )
                )

            # New low breakdown
            if period_low > 0 and cur_low < period_low:
                pct_below = (period_low - cur_low) / period_low * 100
                strength = min(1.0, 0.5 + pct_below / 5.0)
                signals.append(
                    UnifiedSignal(
                        market=market,
                        asset=asset,
                        direction=Direction.SHORT,
                        strength=round(max(0.1, strength), 4),
                        confidence=cfg.base_confidence + (0.1 if label == "52w" else 0.0),
                        signal_type=SignalType.TECHNICAL,
                        source=f"price/breakout_{label}_low",
                        timestamp=ts,
                        metadata={
                            "detector": "price",
                            "sub_type": f"breakout_{label}_low",
                            "current_low": cur_low,
                            "period_low": period_low,
                            "pct_below": round(pct_below, 2),
                            "lookback_days": lookback,
                        },
                    )
                )

            # Near-high (within threshold of high without breaking)
            if (
                period_high > 0
                and cur_high <= period_high
                and cur_high / period_high >= cfg.near_high_pct
            ):
                proximity = cur_high / period_high
                strength = min(1.0, 0.3 + (proximity - cfg.near_high_pct) / (1.0 - cfg.near_high_pct))
                signals.append(
                    UnifiedSignal(
                        market=market,
                        asset=asset,
                        direction=Direction.LONG,
                        strength=round(max(0.1, strength), 4),
                        confidence=cfg.base_confidence - 0.05,
                        signal_type=SignalType.TECHNICAL,
                        source=f"price/near_{label}_high",
                        timestamp=ts,
                        metadata={
                            "detector": "price",
                            "sub_type": f"near_{label}_high",
                            "current_high": cur_high,
                            "period_high": period_high,
                            "proximity_pct": round(proximity * 100, 2),
                        },
                    )
                )

        return signals

    def _detect_gap(
        self,
        bars: List[Dict[str, Any]],
        asset: str,
        market: Market,
        ts,
    ) -> List[UnifiedSignal]:
        """Detect gap-up / gap-down at today's open vs yesterday's close."""
        if len(bars) < 2:
            return []

        cfg = self._config
        today = bars[-1]
        yesterday = bars[-2]

        today_open = float(today.get("open", 0))
        yesterday_close = float(yesterday.get("close", 0))

        if yesterday_close <= 0 or today_open <= 0:
            return []

        gap_pct = (today_open - yesterday_close) / yesterday_close * 100

        if abs(gap_pct) < cfg.gap_min_pct:
            return []

        direction = Direction.LONG if gap_pct > 0 else Direction.SHORT
        is_large = abs(gap_pct) >= cfg.large_gap_pct

        # Larger gap → stronger signal
        strength = min(1.0, 0.4 + abs(gap_pct) / 10.0)
        confidence = cfg.base_confidence + (0.1 if is_large else 0.0)

        # Check if gap was filled (today's low/high crossed yesterday's close)
        today_low = float(today.get("low", 0))
        today_high = float(today.get("high", 0))
        gap_filled = False
        if gap_pct > 0 and today_low <= yesterday_close:
            gap_filled = True
        elif gap_pct < 0 and today_high >= yesterday_close:
            gap_filled = True

        label = "gap_up" if gap_pct > 0 else "gap_down"
        if is_large:
            label = f"large_{label}"

        return [
            UnifiedSignal(
                market=market,
                asset=asset,
                direction=direction,
                strength=round(max(0.1, strength), 4),
                confidence=round(min(1.0, confidence), 4),
                signal_type=SignalType.TECHNICAL,
                source=f"price/{label}",
                timestamp=ts,
                metadata={
                    "detector": "price",
                    "sub_type": label,
                    "gap_pct": round(gap_pct, 2),
                    "today_open": today_open,
                    "yesterday_close": yesterday_close,
                    "gap_filled": gap_filled,
                    "is_large": is_large,
                },
            )
        ]

    def _detect_ma_support_resistance(
        self,
        bars: List[Dict[str, Any]],
        asset: str,
        market: Market,
        ts,
    ) -> List[UnifiedSignal]:
        """Detect price testing key moving average levels."""
        signals: List[UnifiedSignal] = []
        cfg = self._config

        closes = [float(b.get("close", 0)) for b in bars if b.get("close")]
        if len(closes) < 20:
            return []

        cur_close = closes[-1]
        if cur_close <= 0:
            return []

        ma_periods = [5, 10, 20, 60]
        for period in ma_periods:
            if len(closes) < period:
                continue

            ma_val = sum(closes[-period:]) / period
            if ma_val <= 0:
                continue

            dist_pct = abs(cur_close - ma_val) / ma_val * 100

            if dist_pct > cfg.ma_test_tolerance_pct:
                continue

            # Price is testing this MA level
            # Determine if it's support (price above MA) or resistance (price below MA)
            if cur_close >= ma_val:
                direction = Direction.LONG
                level_type = "support"
            else:
                direction = Direction.SHORT
                level_type = "resistance"

            # Longer-period MAs are more significant
            period_weight = {5: 0.3, 10: 0.5, 20: 0.7, 60: 0.9}.get(period, 0.5)
            # Closer to MA → stronger signal
            closeness = 1.0 - (dist_pct / cfg.ma_test_tolerance_pct)
            strength = min(1.0, period_weight * (0.5 + 0.5 * closeness))

            signals.append(
                UnifiedSignal(
                    market=market,
                    asset=asset,
                    direction=direction,
                    strength=round(max(0.1, strength), 4),
                    confidence=round(cfg.base_confidence - 0.05, 4),
                    signal_type=SignalType.TECHNICAL,
                    source=f"price/ma{period}_{level_type}",
                    timestamp=ts,
                    metadata={
                        "detector": "price",
                        "sub_type": f"ma_{level_type}",
                        "ma_period": period,
                        "ma_value": round(ma_val, 4),
                        "close": cur_close,
                        "distance_pct": round(dist_pct, 4),
                        "level_type": level_type,
                    },
                )
            )

        return signals

    def _detect_momentum(
        self,
        bars: List[Dict[str, Any]],
        asset: str,
        market: Market,
        ts,
    ) -> List[UnifiedSignal]:
        """Detect consecutive up/down streaks and price acceleration."""
        signals: List[UnifiedSignal] = []
        cfg = self._config

        if len(bars) < cfg.min_consecutive_days + 1:
            return []

        closes = [float(b.get("close", 0)) for b in bars if b.get("close")]
        if len(closes) < cfg.min_consecutive_days + 1:
            return []

        # --- Consecutive days streak ---
        streak = 0
        for i in range(len(closes) - 1, 0, -1):
            if closes[i] > closes[i - 1]:
                if streak >= 0:
                    streak += 1
                else:
                    break
            elif closes[i] < closes[i - 1]:
                if streak <= 0:
                    streak -= 1
                else:
                    break
            else:
                break

        abs_streak = abs(streak)
        if abs_streak >= cfg.min_consecutive_days:
            direction = Direction.LONG if streak > 0 else Direction.SHORT
            # Cumulative change over streak
            start_idx = len(closes) - abs_streak - 1
            cum_change = (closes[-1] - closes[start_idx]) / closes[start_idx] * 100 if closes[start_idx] > 0 else 0

            strength = min(1.0, 0.3 + abs_streak * 0.1 + abs(cum_change) / 20.0)

            label = "consecutive_up" if streak > 0 else "consecutive_down"
            signals.append(
                UnifiedSignal(
                    market=market,
                    asset=asset,
                    direction=direction,
                    strength=round(max(0.1, strength), 4),
                    confidence=round(cfg.base_confidence, 4),
                    signal_type=SignalType.TECHNICAL,
                    source=f"price/{label}",
                    timestamp=ts,
                    metadata={
                        "detector": "price",
                        "sub_type": label,
                        "streak_days": abs_streak,
                        "cumulative_change_pct": round(cum_change, 2),
                    },
                )
            )

        # --- Price acceleration ---
        lookback = min(cfg.acceleration_lookback, len(closes) - 1)
        if lookback >= 3:
            # Compare last half vs first half of lookback window
            mid = lookback // 2
            recent = closes[-mid:]
            earlier = closes[-(lookback):-mid]

            if len(recent) >= 2 and len(earlier) >= 2:
                recent_change = (recent[-1] - recent[0]) / recent[0] * 100 if recent[0] > 0 else 0
                earlier_change = (earlier[-1] - earlier[0]) / earlier[0] * 100 if earlier[0] > 0 else 0

                # Acceleration = recent rate > earlier rate in same direction
                if abs(recent_change) > abs(earlier_change) * 1.5 and abs(recent_change) > 1.0:
                    if (recent_change > 0 and earlier_change > 0) or (recent_change < 0 and earlier_change < 0):
                        direction = Direction.LONG if recent_change > 0 else Direction.SHORT
                        accel_ratio = abs(recent_change) / max(abs(earlier_change), 0.01)
                        strength = min(1.0, 0.4 + (accel_ratio - 1.5) * 0.2)

                        signals.append(
                            UnifiedSignal(
                                market=market,
                                asset=asset,
                                direction=direction,
                                strength=round(max(0.1, strength), 4),
                                confidence=round(cfg.base_confidence - 0.05, 4),
                                signal_type=SignalType.TECHNICAL,
                                source="price/acceleration",
                                timestamp=ts,
                                metadata={
                                    "detector": "price",
                                    "sub_type": "acceleration",
                                    "recent_change_pct": round(recent_change, 2),
                                    "earlier_change_pct": round(earlier_change, 2),
                                    "acceleration_ratio": round(accel_ratio, 2),
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
