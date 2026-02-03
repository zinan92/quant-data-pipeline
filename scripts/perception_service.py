#!/usr/bin/env python3
"""Perception Service — standalone scheduler for the perception pipeline.

Runs the perception pipeline on a configurable schedule and publishes
trading-ready signals to ``data/perception_signals.json`` for the
trading-agents project to consume.

Features:
- Configurable scan interval (default 5 min during market hours, 30 min off)
- Auto-detect A-share trading hours (9:30–15:00 CST)
- Crypto mode (24/7) via ``--crypto`` flag
- Output signals to JSON + JSONL for trading-agents
- Health monitoring and auto-restart on failure
- Graceful shutdown on SIGINT / SIGTERM

Usage::

    # Default A-share mode
    python scripts/perception_service.py

    # Custom intervals
    python scripts/perception_service.py --market-interval 300 --off-interval 1800

    # Crypto 24/7
    python scripts/perception_service.py --crypto

    # Single scan (for cron)
    python scripts/perception_service.py --once
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

# Add project root to path
_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from src.perception.pipeline import PerceptionPipeline, PipelineConfig, ScanResult
from src.perception.integration.trading_bridge import TradingBridge, BridgeConfig
from src.perception.integration.signal_publisher import SignalPublisher, PublisherConfig
from src.perception.integration.market_context import MarketContextBuilder, ContextConfig

logger = logging.getLogger("perception_service")

# ── Constants ────────────────────────────────────────────────────────

# Shanghai timezone offset (UTC+8)
CST_OFFSET = timedelta(hours=8)

# A-share trading windows (in CST)
ASHARE_MORNING_OPEN = (9, 30)
ASHARE_MORNING_CLOSE = (11, 30)
ASHARE_AFTERNOON_OPEN = (13, 0)
ASHARE_AFTERNOON_CLOSE = (15, 0)

DEFAULT_MARKET_INTERVAL = 300    # 5 minutes during market hours
DEFAULT_OFF_INTERVAL = 1800      # 30 minutes off-hours
DEFAULT_SIGNALS_JSON = "data/perception_signals.json"
DEFAULT_SIGNALS_JSONL = "data/perception_signals.jsonl"
DEFAULT_CONTEXT_JSON = "data/market_context.json"


# ── Helpers ──────────────────────────────────────────────────────────


def is_ashare_trading_hours() -> bool:
    """Check if current time is within A-share trading hours (CST)."""
    now_utc = datetime.now(timezone.utc)
    now_cst = now_utc + CST_OFFSET

    # Weekends: no trading
    if now_cst.weekday() >= 5:
        return False

    hour, minute = now_cst.hour, now_cst.minute
    time_val = hour * 60 + minute

    morning_open = ASHARE_MORNING_OPEN[0] * 60 + ASHARE_MORNING_OPEN[1]
    morning_close = ASHARE_MORNING_CLOSE[0] * 60 + ASHARE_MORNING_CLOSE[1]
    afternoon_open = ASHARE_AFTERNOON_OPEN[0] * 60 + ASHARE_AFTERNOON_OPEN[1]
    afternoon_close = ASHARE_AFTERNOON_CLOSE[0] * 60 + ASHARE_AFTERNOON_CLOSE[1]

    return (morning_open <= time_val < morning_close) or (
        afternoon_open <= time_val < afternoon_close
    )


def get_scan_interval(
    market_interval: float,
    off_interval: float,
    crypto: bool,
) -> float:
    """Return the appropriate scan interval based on current time."""
    if crypto:
        return market_interval  # 24/7 for crypto
    if is_ashare_trading_hours():
        return market_interval
    return off_interval


# ── Service ──────────────────────────────────────────────────────────


class PerceptionService:
    """Scheduled runner for the perception pipeline."""

    def __init__(
        self,
        pipeline: Optional[PerceptionPipeline] = None,
        bridge: Optional[TradingBridge] = None,
        publisher: Optional[SignalPublisher] = None,
        context_builder: Optional[MarketContextBuilder] = None,
        market_interval: float = DEFAULT_MARKET_INTERVAL,
        off_interval: float = DEFAULT_OFF_INTERVAL,
        crypto: bool = False,
        signals_json_path: str = DEFAULT_SIGNALS_JSON,
        context_json_path: str = DEFAULT_CONTEXT_JSON,
        max_consecutive_failures: int = 5,
    ):
        self.pipeline = pipeline or PerceptionPipeline()
        self.bridge = bridge or TradingBridge()
        self.publisher = publisher or SignalPublisher()
        self.context_builder = context_builder or MarketContextBuilder()

        self.market_interval = market_interval
        self.off_interval = off_interval
        self.crypto = crypto
        self.signals_json_path = signals_json_path
        self.context_json_path = context_json_path
        self.max_consecutive_failures = max_consecutive_failures

        self._running = False
        self._scan_count = 0
        self._failure_count = 0
        self._last_scan_time: Optional[float] = None

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def scan_count(self) -> int:
        return self._scan_count

    @property
    def failure_count(self) -> int:
        return self._failure_count

    async def start(self) -> None:
        """Start the pipeline."""
        if not self.pipeline.is_running:
            await self.pipeline.start()
        self._running = True
        logger.info(
            "Perception service started | market_interval=%ds off_interval=%ds crypto=%s",
            self.market_interval,
            self.off_interval,
            self.crypto,
        )

    async def stop(self) -> None:
        """Stop the pipeline."""
        self._running = False
        await self.pipeline.stop()
        logger.info("Perception service stopped after %d scans", self._scan_count)

    async def run_once(self) -> Optional[ScanResult]:
        """Run a single scan cycle: scan → bridge → publish → context."""
        try:
            # 1. Scan
            result = await self.pipeline.scan()
            self._scan_count += 1
            self._last_scan_time = time.time()

            # 2. Bridge → trading signals
            trading_signals = self.bridge.get_trading_signals(result)

            # 3. Publish
            self.publisher.publish(trading_signals)
            self.publisher.snapshot_to_json(self.signals_json_path)

            # 4. Market context
            ctx = self.context_builder.build(result)
            self._write_context(ctx)

            # Reset failure count on success
            self._failure_count = 0

            actionable = sum(1 for s in trading_signals if s.is_actionable)
            logger.info(
                "Scan #%d complete: %d events → %d signals → %d trading (%d actionable) "
                "| duration=%.0fms",
                self._scan_count,
                result.events_fetched,
                result.signals_detected,
                len(trading_signals),
                actionable,
                result.duration_ms,
            )
            return result

        except Exception as exc:
            self._failure_count += 1
            logger.error(
                "Scan failed (attempt %d/%d): %s",
                self._failure_count,
                self.max_consecutive_failures,
                exc,
            )
            if self._failure_count >= self.max_consecutive_failures:
                logger.critical(
                    "Too many consecutive failures (%d) — will attempt restart",
                    self._failure_count,
                )
                await self._restart()
            return None

    async def run_loop(self) -> None:
        """Run scan cycles in a loop with adaptive interval."""
        await self.start()

        try:
            while self._running:
                await self.run_once()

                interval = get_scan_interval(
                    self.market_interval,
                    self.off_interval,
                    self.crypto,
                )
                logger.debug("Next scan in %.0f seconds", interval)
                await asyncio.sleep(interval)
        finally:
            await self.stop()

    async def _restart(self) -> None:
        """Attempt to restart the pipeline after failures."""
        logger.info("Attempting pipeline restart...")
        try:
            await self.pipeline.stop()
            await asyncio.sleep(2)
            await self.pipeline.start()
            self._failure_count = 0
            logger.info("Pipeline restarted successfully")
        except Exception as exc:
            logger.error("Restart failed: %s", exc)

    def _write_context(self, ctx) -> None:
        """Write market context to JSON file."""
        path = Path(self.context_json_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(ctx.to_dict(), f, ensure_ascii=False, indent=2)
        except OSError as exc:
            logger.warning("Failed to write context: %s", exc)

    def get_status(self) -> dict:
        """Return service health status."""
        return {
            "running": self._running,
            "scan_count": self._scan_count,
            "failure_count": self._failure_count,
            "last_scan_time": self._last_scan_time,
            "market_interval": self.market_interval,
            "off_interval": self.off_interval,
            "crypto": self.crypto,
            "is_market_hours": is_ashare_trading_hours() if not self.crypto else True,
        }


# ── CLI ──────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Perception Service — scheduled signal pipeline"
    )
    parser.add_argument(
        "--market-interval",
        type=float,
        default=DEFAULT_MARKET_INTERVAL,
        help=f"Scan interval during market hours (seconds, default {DEFAULT_MARKET_INTERVAL})",
    )
    parser.add_argument(
        "--off-interval",
        type=float,
        default=DEFAULT_OFF_INTERVAL,
        help=f"Scan interval off-hours (seconds, default {DEFAULT_OFF_INTERVAL})",
    )
    parser.add_argument(
        "--crypto",
        action="store_true",
        help="Crypto mode: scan 24/7 at market-interval",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single scan and exit",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_SIGNALS_JSON,
        help=f"Output JSON path (default {DEFAULT_SIGNALS_JSON})",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level (default INFO)",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    service = PerceptionService(
        market_interval=args.market_interval,
        off_interval=args.off_interval,
        crypto=args.crypto,
        signals_json_path=args.output,
    )

    # Signal handling
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(service.stop()))

    if args.once:
        await service.start()
        await service.run_once()
        await service.stop()
    else:
        await service.run_loop()


if __name__ == "__main__":
    asyncio.run(main())
