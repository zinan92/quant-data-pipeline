"""Perception Layer configuration.

Centralises all tunable knobs: poll intervals, detector toggles, and
circuit-breaker thresholds.  The config is a Pydantic model so it
can be loaded from YAML / JSON / env-vars with validation.
"""

from __future__ import annotations

from typing import Dict, Optional

from pydantic import BaseModel, Field, field_validator


# ── Sub-models ───────────────────────────────────────────────────────


class SourcePollConfig(BaseModel):
    """Per-source polling configuration.

    Attributes:
        interval_seconds: Seconds between consecutive polls.
        enabled: Whether the source is active.
        timeout_seconds: Max time to wait for a single poll response.
        max_retries: How many times to retry before tripping the breaker.
    """

    interval_seconds: float = Field(
        default=60.0, gt=0, description="Poll interval in seconds"
    )
    enabled: bool = Field(default=True, description="Source enabled?")
    timeout_seconds: float = Field(
        default=30.0, gt=0, description="Request timeout in seconds"
    )
    max_retries: int = Field(
        default=3, ge=0, description="Max retries before circuit break"
    )


class DetectorConfig(BaseModel):
    """Per-detector toggle + optional params.

    Attributes:
        enabled: Whether this detector runs.
        params: Arbitrary detector-specific parameters.
    """

    enabled: bool = Field(default=True, description="Detector enabled?")
    params: Dict[str, object] = Field(
        default_factory=dict,
        description="Detector-specific parameters",
    )


class CircuitBreakerConfig(BaseModel):
    """Circuit-breaker thresholds shared across sources.

    Attributes:
        failure_threshold: Number of consecutive failures to trip the
            breaker.
        recovery_timeout_seconds: Seconds to wait before allowing a
            retry after the breaker trips.
        half_open_max_requests: Requests to allow through in half-open
            state before deciding to close or re-open.
    """

    failure_threshold: int = Field(
        default=5, ge=1, description="Failures to trip breaker"
    )
    recovery_timeout_seconds: float = Field(
        default=60.0, gt=0, description="Seconds before retry after trip"
    )
    half_open_max_requests: int = Field(
        default=1,
        ge=1,
        description="Requests in half-open before deciding",
    )


# ── Top-level config ────────────────────────────────────────────────


class PerceptionConfig(BaseModel):
    """Root configuration for the Perception Layer.

    Example (YAML)::

        sources:
          tushare:
            interval_seconds: 30
            enabled: true
          sina:
            interval_seconds: 10
        detectors:
          volume_spike:
            enabled: true
            params:
              threshold: 3.0
        circuit_breaker:
          failure_threshold: 5
          recovery_timeout_seconds: 60

    Attributes:
        sources: Per-source polling configs keyed by source name.
        detectors: Per-detector configs keyed by detector name.
        circuit_breaker: Global circuit-breaker settings.
        global_poll_interval_seconds: Default poll interval when a
            source doesn't have an explicit config.
    """

    sources: Dict[str, SourcePollConfig] = Field(
        default_factory=dict,
        description="Per-source polling configuration",
    )
    detectors: Dict[str, DetectorConfig] = Field(
        default_factory=dict,
        description="Per-detector configuration",
    )
    circuit_breaker: CircuitBreakerConfig = Field(
        default_factory=CircuitBreakerConfig,
        description="Circuit-breaker thresholds",
    )
    global_poll_interval_seconds: float = Field(
        default=60.0,
        gt=0,
        description="Default poll interval if source has no explicit config",
    )

    # ── helpers ──────────────────────────────────────────────────────

    def source_config(self, name: str) -> SourcePollConfig:
        """Return config for a source, falling back to defaults.

        Args:
            name: Source name.

        Returns:
            The explicit config or a default ``SourcePollConfig`` with
            the global poll interval.
        """
        if name in self.sources:
            return self.sources[name]
        return SourcePollConfig(
            interval_seconds=self.global_poll_interval_seconds
        )

    def detector_enabled(self, name: str) -> bool:
        """Check whether a detector is enabled (default: True).

        Args:
            name: Detector name.

        Returns:
            ``True`` if enabled or not explicitly configured.
        """
        cfg = self.detectors.get(name)
        return cfg.enabled if cfg is not None else True
