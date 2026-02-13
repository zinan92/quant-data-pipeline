"""Persistence layer for perception scan results and signals."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from src.database import session_scope
from src.models.perception_signal import PerceptionScanReport, PerceptionSignal
from src.utils.logging import get_logger

logger = get_logger(__name__)


class PerceptionStore:
    """Read/write perception signals and scan reports to SQLite."""

    def save_scan(self, scan_id: str, result: Any) -> None:
        """Persist a scan report and all its signals.

        Parameters
        ----------
        scan_id : str
            Unique identifier for this scan cycle.
        result : ScanResult
            The scan result from PerceptionPipeline.scan().
        """
        with session_scope() as session:
            # Save the report
            report = result.report
            report_row = PerceptionScanReport(
                scan_id=scan_id,
                timestamp=result.timestamp,
                duration_ms=result.duration_ms,
                events_fetched=result.events_fetched,
                signals_detected=result.signals_detected,
                signals_ingested=result.signals_ingested,
                market_bias=report.market_bias.value
                if hasattr(report.market_bias, "value")
                else str(report.market_bias),
                market_bias_score=report.market_bias_score,
                top_longs_json=json.dumps(
                    [s.to_dict() for s in report.top_longs]
                ),
                top_shorts_json=json.dumps(
                    [s.to_dict() for s in report.top_shorts]
                ),
                source_health_json=json.dumps(
                    {
                        k: {
                            "status": v.status.value
                            if hasattr(v.status, "value")
                            else v.status,
                            "latency_ms": v.latency_ms,
                            "consecutive_failures": v.consecutive_failures,
                        }
                        for k, v in result.source_health.items()
                    }
                ),
                errors_json=json.dumps(result.errors),
            )
            session.add(report_row)

            # Save individual signals from top_longs + top_shorts
            seen_ids: set = set()
            for summary in report.top_longs + report.top_shorts:
                for sig in summary.all_signals:
                    sid = sig.signal_id
                    if sid in seen_ids:
                        continue
                    seen_ids.add(sid)

                    sig_row = PerceptionSignal(
                        signal_id=sid,
                        scan_id=scan_id,
                        asset=sig.asset,
                        market=sig.market.value
                        if hasattr(sig.market, "value")
                        else str(sig.market),
                        direction=sig.direction.value
                        if hasattr(sig.direction, "value")
                        else str(sig.direction),
                        signal_type=sig.signal_type.value
                        if hasattr(sig.signal_type, "value")
                        else str(sig.signal_type),
                        source=sig.source,
                        strength=sig.strength,
                        confidence=sig.confidence,
                        metadata_json=json.dumps(sig.metadata),
                        created_at=sig.timestamp,
                        expires_at=sig.expires_at,
                    )
                    session.add(sig_row)

    def get_signals(
        self,
        asset: Optional[str] = None,
        hours: int = 24,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query historical signals.

        Parameters
        ----------
        asset : str | None
            Filter by asset ticker/name. None = all assets.
        hours : int
            Look back this many hours.
        limit : int
            Max results to return.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        with session_scope() as session:
            query = (
                session.query(PerceptionSignal)
                .filter(PerceptionSignal.created_at >= cutoff)
            )
            if asset:
                query = query.filter(PerceptionSignal.asset == asset)

            rows = (
                query.order_by(PerceptionSignal.created_at.desc())
                .limit(limit)
                .all()
            )

            return [
                {
                    "signal_id": r.signal_id,
                    "scan_id": r.scan_id,
                    "asset": r.asset,
                    "market": r.market,
                    "direction": r.direction,
                    "signal_type": r.signal_type,
                    "source": r.source,
                    "strength": r.strength,
                    "confidence": r.confidence,
                    "metadata": json.loads(r.metadata_json)
                    if r.metadata_json
                    else {},
                    "created_at": r.created_at.isoformat()
                    if r.created_at
                    else None,
                    "expires_at": r.expires_at.isoformat()
                    if r.expires_at
                    else None,
                }
                for r in rows
            ]

    def get_reports(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Query historical scan reports."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        with session_scope() as session:
            rows = (
                session.query(PerceptionScanReport)
                .filter(PerceptionScanReport.timestamp >= cutoff)
                .order_by(PerceptionScanReport.timestamp.desc())
                .all()
            )

            return [
                {
                    "scan_id": r.scan_id,
                    "timestamp": r.timestamp.isoformat()
                    if r.timestamp
                    else None,
                    "duration_ms": r.duration_ms,
                    "events_fetched": r.events_fetched,
                    "signals_detected": r.signals_detected,
                    "signals_ingested": r.signals_ingested,
                    "market_bias": r.market_bias,
                    "market_bias_score": r.market_bias_score,
                    "top_longs": json.loads(r.top_longs_json)
                    if r.top_longs_json
                    else [],
                    "top_shorts": json.loads(r.top_shorts_json)
                    if r.top_shorts_json
                    else [],
                    "source_health": json.loads(r.source_health_json)
                    if r.source_health_json
                    else {},
                    "errors": json.loads(r.errors_json)
                    if r.errors_json
                    else [],
                }
                for r in rows
            ]

    def cleanup(self, days: int = 30) -> int:
        """Remove signals and reports older than *days*.

        Returns the total number of rows deleted.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        deleted = 0

        with session_scope() as session:
            d1 = (
                session.query(PerceptionSignal)
                .filter(PerceptionSignal.created_at < cutoff)
                .delete()
            )
            d2 = (
                session.query(PerceptionScanReport)
                .filter(PerceptionScanReport.timestamp < cutoff)
                .delete()
            )
            deleted = d1 + d2

        logger.info("Cleaned up %d perception rows older than %d days", deleted, days)
        return deleted
