"""Source Health monitoring for the Perception Layer.

Tracks the operational status of each data source — latency, error
rates, and overall health classification.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Enums ────────────────────────────────────────────────────────────


class HealthStatus(str, Enum):
    """Discrete health states for a data source."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"


# ── Model ────────────────────────────────────────────────────────────


class SourceHealth(BaseModel):
    """Health snapshot for a single data source.

    Attributes:
        source_name: Identifier of the data source.
        status: Current health classification.
        latency_ms: Last observed request latency in milliseconds.
        error_rate: Rolling error rate (0.0–1.0).
        last_success: Timestamp of the last successful request.
        last_error: Human-readable description of the last error.
        requests_total: Lifetime request count.
        requests_failed: Lifetime failed-request count.
    """

    source_name: str = Field(
        ..., min_length=1, description="Data source identifier"
    )
    status: str = Field(
        default=HealthStatus.HEALTHY,
        description="Health status: healthy | degraded | down",
    )
    latency_ms: float = Field(
        default=0.0, ge=0.0, description="Last request latency (ms)"
    )
    error_rate: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Rolling error rate (0.0–1.0)",
    )
    last_success: Optional[datetime] = Field(
        default=None, description="Timestamp of last successful request"
    )
    last_error: Optional[str] = Field(
        default=None, description="Description of last error"
    )
    requests_total: int = Field(
        default=0, ge=0, description="Total requests made"
    )
    requests_failed: int = Field(
        default=0, ge=0, description="Total failed requests"
    )

    model_config = {"use_enum_values": True}

    # ── validators ───────────────────────────────────────────────────

    @field_validator("status")
    @classmethod
    def _validate_status(cls, v: str) -> str:
        """Ensure status is one of the known health states."""
        allowed = {s.value for s in HealthStatus}
        if v not in allowed:
            raise ValueError(f"status must be one of {allowed}, got '{v}'")
        return v

    @model_validator(mode="after")
    def _failed_le_total(self) -> "SourceHealth":
        """requests_failed must not exceed requests_total."""
        if self.requests_failed > self.requests_total:
            raise ValueError(
                "requests_failed cannot exceed requests_total"
            )
        return self

    # ── helpers ──────────────────────────────────────────────────────

    @property
    def is_healthy(self) -> bool:
        """Shorthand check."""
        return self.status == HealthStatus.HEALTHY

    @property
    def computed_error_rate(self) -> float:
        """Compute error rate from counters (ignores the stored field)."""
        if self.requests_total == 0:
            return 0.0
        return self.requests_failed / self.requests_total


# ── Health Monitor ───────────────────────────────────────────────────


class HealthMonitor:
    """Mutable health tracker for a single data source.

    Usage::

        monitor = HealthMonitor("tushare")
        monitor.record_success(latency_ms=42.5)
        monitor.record_failure("timeout")
        snapshot = monitor.snapshot()  # → SourceHealth
    """

    def __init__(self, source_name: str) -> None:
        self.source_name = source_name
        self._requests_total: int = 0
        self._requests_failed: int = 0
        self._last_success: Optional[datetime] = None
        self._last_error: Optional[str] = None
        self._last_latency_ms: float = 0.0

    def record_success(self, latency_ms: float = 0.0) -> None:
        """Record a successful request."""
        self._requests_total += 1
        self._last_latency_ms = latency_ms
        self._last_success = datetime.now(timezone.utc)

    def record_failure(self, error: str, latency_ms: float = 0.0) -> None:
        """Record a failed request."""
        self._requests_total += 1
        self._requests_failed += 1
        self._last_latency_ms = latency_ms
        self._last_error = error

    @property
    def error_rate(self) -> float:
        """Current error rate."""
        if self._requests_total == 0:
            return 0.0
        return self._requests_failed / self._requests_total

    def _classify_status(self) -> str:
        """Derive health status from error rate."""
        rate = self.error_rate
        if rate >= 0.5:
            return HealthStatus.DOWN
        if rate >= 0.1:
            return HealthStatus.DEGRADED
        return HealthStatus.HEALTHY

    def snapshot(self) -> SourceHealth:
        """Return an immutable health snapshot."""
        return SourceHealth(
            source_name=self.source_name,
            status=self._classify_status(),
            latency_ms=self._last_latency_ms,
            error_rate=round(self.error_rate, 4),
            last_success=self._last_success,
            last_error=self._last_error,
            requests_total=self._requests_total,
            requests_failed=self._requests_failed,
        )

    def reset(self) -> None:
        """Reset all counters."""
        self._requests_total = 0
        self._requests_failed = 0
        self._last_success = None
        self._last_error = None
        self._last_latency_ms = 0.0
