"""Signal Publisher — file-based event bus for inter-process communication.

Publishes perception signals to a local JSON-lines file that trading-agents
(or any other consumer) can poll / tail.  Each signal is wrapped in a
``SignalEnvelope`` that carries metadata (source, confidence, timestamp,
expiry, sequence number) for reliable consumption.

Design choices:
- File-based (no external deps like Redis/Kafka)
- Append-only JSON-lines for easy parsing and tailing
- Built-in rotation / size cap to avoid unbounded growth
- In-memory callback bus for co-located consumers
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from src.perception.integration.trading_bridge import TradingSignal

logger = logging.getLogger(__name__)

# Type alias for subscriber callbacks
SignalCallback = Callable[[List["SignalEnvelope"]], None]


# ── Models ───────────────────────────────────────────────────────────


@dataclass
class SignalEnvelope:
    """Wrapper around a TradingSignal with delivery metadata.

    Fields are chosen for compatibility with trading-agents' consumption:
    - ``seq``: monotonic sequence for ordering / dedup
    - ``published_at``: when the envelope was created (epoch)
    - ``expires_at``: when the signal should be discarded (epoch; 0 = never)
    - ``source_pipeline``: which pipeline produced this ("perception")
    - ``signal``: the actual TradingSignal payload as a dict
    """

    seq: int
    published_at: float
    expires_at: float
    source_pipeline: str
    signal: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "seq": self.seq,
            "published_at": self.published_at,
            "expires_at": self.expires_at,
            "source_pipeline": self.source_pipeline,
            "signal": self.signal,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SignalEnvelope":
        return cls(
            seq=data["seq"],
            published_at=data["published_at"],
            expires_at=data["expires_at"],
            source_pipeline=data["source_pipeline"],
            signal=data["signal"],
        )

    @classmethod
    def from_json(cls, raw: str) -> "SignalEnvelope":
        return cls.from_dict(json.loads(raw))

    @property
    def is_expired(self) -> bool:
        if self.expires_at <= 0:
            return False
        return time.time() >= self.expires_at


# ── Configuration ────────────────────────────────────────────────────


@dataclass
class PublisherConfig:
    """Tuneable parameters for the signal publisher."""

    # Path to the JSON-lines output file
    output_path: str = "data/perception_signals.jsonl"

    # Maximum file size in bytes before rotation (10 MB default)
    max_file_bytes: int = 10 * 1024 * 1024

    # Number of rotated files to keep
    max_rotated_files: int = 5

    # Default signal expiry (seconds from publish time; 0 = no expiry)
    default_expiry_seconds: float = 3600.0

    # Source pipeline tag
    source_pipeline: str = "perception"


# ── Publisher ────────────────────────────────────────────────────────


class SignalPublisher:
    """Publish TradingSignals to file and in-memory subscribers.

    Usage::

        publisher = SignalPublisher()
        publisher.publish(trading_signals)

        # Subscribe for in-process callbacks
        publisher.subscribe(my_callback)

        # Read back published envelopes
        recent = publisher.read_recent(limit=20)
    """

    def __init__(self, config: Optional[PublisherConfig] = None) -> None:
        self._config = config or PublisherConfig()
        self._seq = 0
        self._lock = threading.Lock()
        self._subscribers: List[SignalCallback] = []
        self._recent: List[SignalEnvelope] = []
        self._max_recent = 500  # in-memory buffer cap

    @property
    def config(self) -> PublisherConfig:
        return self._config

    @property
    def sequence(self) -> int:
        return self._seq

    # ── Publish ──────────────────────────────────────────────────────

    def publish(self, signals: List[TradingSignal]) -> List[SignalEnvelope]:
        """Wrap signals in envelopes and write them out.

        Returns the envelopes that were published.
        """
        if not signals:
            return []

        envelopes: List[SignalEnvelope] = []
        now = time.time()
        cfg = self._config

        with self._lock:
            for sig in signals:
                self._seq += 1
                exp = (
                    now + cfg.default_expiry_seconds
                    if cfg.default_expiry_seconds > 0
                    else 0.0
                )
                env = SignalEnvelope(
                    seq=self._seq,
                    published_at=now,
                    expires_at=exp,
                    source_pipeline=cfg.source_pipeline,
                    signal=sig.to_dict(),
                )
                envelopes.append(env)

            # Write to file
            self._write_to_file(envelopes)

            # Buffer in memory
            self._recent.extend(envelopes)
            if len(self._recent) > self._max_recent:
                self._recent = self._recent[-self._max_recent:]

        # Notify subscribers (outside lock)
        self._notify(envelopes)

        logger.info("Published %d signal envelopes (seq %d–%d)",
                     len(envelopes),
                     envelopes[0].seq if envelopes else 0,
                     envelopes[-1].seq if envelopes else 0)
        return envelopes

    # ── Subscribe ────────────────────────────────────────────────────

    def subscribe(self, callback: SignalCallback) -> None:
        """Register an in-process callback for new signals."""
        self._subscribers.append(callback)

    def unsubscribe(self, callback: SignalCallback) -> None:
        """Remove a previously registered callback."""
        self._subscribers = [cb for cb in self._subscribers if cb is not callback]

    # ── Read ─────────────────────────────────────────────────────────

    def read_recent(self, limit: int = 50) -> List[SignalEnvelope]:
        """Return the most recent envelopes from the in-memory buffer."""
        with self._lock:
            active = [e for e in self._recent if not e.is_expired]
            return active[-limit:]

    def read_from_file(
        self,
        since_seq: int = 0,
        limit: int = 100,
    ) -> List[SignalEnvelope]:
        """Read envelopes from the file (for external consumers).

        Parameters
        ----------
        since_seq : int
            Only return envelopes with seq > since_seq.
        limit : int
            Max envelopes to return.
        """
        path = Path(self._config.output_path)
        if not path.exists():
            return []

        envelopes: List[SignalEnvelope] = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        env = SignalEnvelope.from_json(line)
                        if env.seq > since_seq and not env.is_expired:
                            envelopes.append(env)
                            if len(envelopes) >= limit:
                                break
                    except (json.JSONDecodeError, KeyError):
                        continue
        except OSError as exc:
            logger.warning("Failed to read signal file: %s", exc)

        return envelopes

    # ── Snapshot (for API / JSON dump) ───────────────────────────────

    def snapshot_to_json(self, path: str, limit: int = 100) -> int:
        """Write current active signals to a JSON file (not JSONL).

        Used by ``scripts/perception_service.py`` to produce the
        ``data/perception_signals.json`` consumed by trading-agents.

        Returns the number of signals written.
        """
        active = self.read_recent(limit=limit)
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "count": len(active),
            "signals": [e.to_dict() for e in active],
        }

        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        return len(active)

    # ── Internal ─────────────────────────────────────────────────────

    def _write_to_file(self, envelopes: List[SignalEnvelope]) -> None:
        """Append envelopes as JSON-lines to the output file."""
        path = Path(self._config.output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Rotate if file is too large
        if path.exists() and path.stat().st_size >= self._config.max_file_bytes:
            self._rotate(path)

        try:
            with open(path, "a", encoding="utf-8") as f:
                for env in envelopes:
                    f.write(env.to_json() + "\n")
        except OSError as exc:
            logger.error("Failed to write signals to %s: %s", path, exc)

    def _rotate(self, path: Path) -> None:
        """Rotate the output file."""
        for i in range(self._config.max_rotated_files - 1, 0, -1):
            src = path.with_suffix(f".{i}.jsonl")
            dst = path.with_suffix(f".{i + 1}.jsonl")
            if src.exists():
                src.rename(dst)

        # Current → .1
        rotated = path.with_suffix(".1.jsonl")
        try:
            path.rename(rotated)
        except OSError:
            pass  # best effort

    def _notify(self, envelopes: List[SignalEnvelope]) -> None:
        """Notify all in-memory subscribers."""
        for cb in self._subscribers:
            try:
                cb(envelopes)
            except Exception as exc:
                logger.warning("Subscriber callback failed: %s", exc)
