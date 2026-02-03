"""Perception Pipeline — orchestrator for the full scan cycle.

Lifecycle per cycle:
    1. All sources poll() in parallel
    2. Events are routed to matching detectors
    3. Signals are ingested into the SignalAggregator
    4. An AggregationReport is produced

The pipeline is async-friendly and can be driven by a timer,
a cron scheduler, or an API endpoint.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.perception.aggregator import (
    AggregationReport,
    AggregatorConfig,
    SignalAggregator,
)
from src.perception.detectors.anomaly_detector import AnomalyDetector
from src.perception.detectors.base import Detector
from src.perception.detectors.flow_detector import FlowDetector
from src.perception.detectors.keyword_detector import KeywordDetector
from src.perception.detectors.price_detector import PriceDetector
from src.perception.detectors.technical_detector import TechnicalDetector
from src.perception.detectors.volume_detector import VolumeDetector
from src.perception.events import RawMarketEvent
from src.perception.health import HealthMonitor, HealthStatus, SourceHealth
from src.perception.signals import UnifiedSignal
from src.perception.sources.alert_source import AlertSource
from src.perception.sources.base import DataSource
from src.perception.sources.market_data_source import MarketDataSource
from src.perception.sources.news_source import NewsSource

logger = logging.getLogger(__name__)


# ── Configuration ────────────────────────────────────────────────────


@dataclass
class PipelineConfig:
    """Pipeline-level configuration."""

    # ashare API base URL
    api_base_url: str = "http://127.0.0.1:8000"

    # SQLite DB path for market data
    db_path: str = "data/market.db"

    # Scan interval (seconds) when running in loop mode
    scan_interval_seconds: float = 60.0

    # HTTP timeout
    http_timeout: float = 10.0

    # News fetch limit
    news_limit: int = 50

    # Aggregator config
    aggregator_config: Optional[AggregatorConfig] = None


# ── Scan result ──────────────────────────────────────────────────────


@dataclass
class ScanResult:
    """Result of a single scan cycle."""

    timestamp: datetime
    duration_ms: float
    events_fetched: int
    signals_detected: int
    signals_ingested: int
    report: AggregationReport
    source_health: Dict[str, SourceHealth]
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "duration_ms": round(self.duration_ms, 2),
            "events_fetched": self.events_fetched,
            "signals_detected": self.signals_detected,
            "signals_ingested": self.signals_ingested,
            "report": self.report.to_dict(),
            "source_health": {
                k: {
                    "status": v.status.value if hasattr(v.status, "value") else v.status,
                    "latency_ms": v.latency_ms,
                    "total_events": v.total_events,
                    "consecutive_failures": v.consecutive_failures,
                }
                for k, v in self.source_health.items()
            },
            "errors": self.errors,
        }


# ── Pipeline ─────────────────────────────────────────────────────────


class PerceptionPipeline:
    """Orchestrate the full perception scan cycle.

    Usage::

        pipeline = PerceptionPipeline()
        await pipeline.start()
        result = await pipeline.scan()
        await pipeline.stop()
    """

    def __init__(
        self,
        config: Optional[PipelineConfig] = None,
        sources: Optional[List[DataSource]] = None,
        detectors: Optional[List[Detector]] = None,
        aggregator: Optional[SignalAggregator] = None,
    ) -> None:
        self._config = config or PipelineConfig()
        self._aggregator = aggregator or SignalAggregator(
            self._config.aggregator_config
        )
        self._health_monitor = HealthMonitor()
        self._running = False
        self._scan_count = 0
        self._last_result: Optional[ScanResult] = None

        # Build default sources if not provided
        if sources is not None:
            self._sources = list(sources)
        else:
            self._sources = self._build_default_sources()

        # Build default detectors if not provided
        if detectors is not None:
            self._detectors = list(detectors)
        else:
            self._detectors = self._build_default_detectors()

        # Build event-type → detector routing map
        self._route_map = self._build_route_map()

    # ── Lifecycle ────────────────────────────────────────────────────

    async def start(self) -> None:
        """Connect all sources."""
        for source in self._sources:
            try:
                await source.connect()
            except Exception as exc:
                logger.warning("Failed to connect source %s: %s", source.name, exc)
        self._running = True

    async def stop(self) -> None:
        """Disconnect all sources."""
        for source in self._sources:
            try:
                await source.disconnect()
            except Exception as exc:
                logger.warning("Failed to disconnect source %s: %s", source.name, exc)
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def scan_count(self) -> int:
        return self._scan_count

    @property
    def last_result(self) -> Optional[ScanResult]:
        return self._last_result

    # ── Scan ─────────────────────────────────────────────────────────

    async def scan(self) -> ScanResult:
        """Run one full scan cycle: fetch → detect → aggregate → report."""
        t0 = time.monotonic()
        errors: List[str] = []
        all_events: List[RawMarketEvent] = []
        all_signals: List[UnifiedSignal] = []

        # 1. Fetch events from all sources (parallel)
        fetch_tasks = [self._safe_poll(src, errors) for src in self._sources]
        results = await asyncio.gather(*fetch_tasks)

        for events in results:
            all_events.extend(events)

        # 2. Route events to detectors
        for event in all_events:
            etype = event.event_type
            etype_val = etype.value if hasattr(etype, "value") else str(etype)

            matched_detectors = self._route_map.get(etype_val, [])
            for detector in matched_detectors:
                try:
                    sigs = detector.detect(event)
                    all_signals.extend(sigs)
                except Exception as exc:
                    err = f"Detector {detector.name} error: {exc}"
                    logger.warning(err)
                    errors.append(err)

        # 3. Ingest signals into aggregator
        ingested = self._aggregator.ingest(all_signals)

        # 4. Produce report
        report = self._aggregator.summarize()

        # 5. Collect health
        source_health: Dict[str, SourceHealth] = {}
        for src in self._sources:
            h = src.health()
            source_health[src.name] = h
            self._health_monitor.update(src.name, h)

        duration_ms = (time.monotonic() - t0) * 1000
        self._scan_count += 1

        result = ScanResult(
            timestamp=datetime.now(timezone.utc),
            duration_ms=duration_ms,
            events_fetched=len(all_events),
            signals_detected=len(all_signals),
            signals_ingested=ingested,
            report=report,
            source_health=source_health,
            errors=errors,
        )
        self._last_result = result
        return result

    async def run_loop(self, max_cycles: Optional[int] = None) -> None:
        """Run scan cycles in a loop with configured interval.

        Parameters
        ----------
        max_cycles : int | None
            Stop after this many cycles; None = run forever.
        """
        cycles = 0
        while True:
            try:
                await self.scan()
            except Exception as exc:
                logger.error("Pipeline scan error: %s", exc)

            cycles += 1
            if max_cycles is not None and cycles >= max_cycles:
                break

            await asyncio.sleep(self._config.scan_interval_seconds)

    # ── Query helpers ────────────────────────────────────────────────

    def get_current_signals(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return current signals from the aggregator as dicts."""
        summaries = self._aggregator.top_signals(limit=limit)
        return [s.to_dict() for s in summaries]

    def get_health(self) -> Dict[str, Any]:
        """Return pipeline and source health."""
        source_health = self._health_monitor.report()
        return {
            "pipeline": {
                "running": self._running,
                "scan_count": self._scan_count,
                "sources": len(self._sources),
                "detectors": len(self._detectors),
                "signal_buffer_size": self._aggregator.signal_count(),
                "asset_count": self._aggregator.asset_count(),
            },
            "sources": {
                name: {
                    "status": h.status.value if hasattr(h.status, "value") else h.status,
                    "latency_ms": h.latency_ms,
                    "total_polls": h.total_polls,
                    "total_events": h.total_events,
                    "consecutive_failures": h.consecutive_failures,
                }
                for name, h in source_health.items()
            },
            "all_healthy": self._health_monitor.all_healthy,
            "unhealthy_sources": self._health_monitor.unhealthy_sources,
        }

    # ── Internal ─────────────────────────────────────────────────────

    async def _safe_poll(
        self, source: DataSource, errors: List[str]
    ) -> List[RawMarketEvent]:
        """Poll a source, catching exceptions."""
        try:
            return await source.poll()
        except Exception as exc:
            err = f"Source {source.name} poll failed: {exc}"
            logger.warning(err)
            errors.append(err)
            return []

    def _build_default_sources(self) -> List[DataSource]:
        """Create the default set of data sources."""
        cfg = self._config
        return [
            NewsSource(
                base_url=cfg.api_base_url,
                news_limit=cfg.news_limit,
                timeout=cfg.http_timeout,
            ),
            MarketDataSource(
                base_url=cfg.api_base_url,
                db_path=cfg.db_path,
                timeout=cfg.http_timeout,
            ),
            AlertSource(
                base_url=cfg.api_base_url,
                timeout=cfg.http_timeout,
            ),
        ]

    def _build_default_detectors(self) -> List[Detector]:
        """Create the default set of detectors."""
        return [
            KeywordDetector(),
            FlowDetector(),
            AnomalyDetector(),
            TechnicalDetector(),
            PriceDetector(),
            VolumeDetector(),
        ]

    def _build_route_map(self) -> Dict[str, List[Detector]]:
        """Map event_type values to lists of detectors that accept them."""
        route: Dict[str, List[Detector]] = {}
        for detector in self._detectors:
            for etype in detector.accepts:
                key = etype.value if hasattr(etype, "value") else str(etype)
                route.setdefault(key, []).append(detector)
        return route
