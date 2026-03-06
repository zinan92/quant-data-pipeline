"""Simple JSONL-based alerting system.

Alerts are appended to a daily JSONL file. Downstream services (e.g. tradinghouse)
can poll the recent alerts via the API or read the file directly.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.utils.logging import LOGGER

_ALERTS_DIR = Path(__file__).parent.parent.parent / "logs" / "alerts"


@dataclass(frozen=True)
class Alert:
    """Immutable alert record."""

    level: str  # "warning" | "error" | "critical"
    source: str
    message: str
    timestamp: str
    details: dict[str, Any]


class AlertManager:
    """Append-only JSONL alert log. One file per day."""

    def __init__(self, alerts_dir: Path | None = None) -> None:
        self._dir = alerts_dir or _ALERTS_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

    def _today_file(self) -> Path:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self._dir / f"alerts-{date_str}.jsonl"

    def emit(self, level: str, source: str, message: str, **details: Any) -> Alert:
        """Create and persist an alert. Returns the frozen Alert."""
        alert = Alert(
            level=level,
            source=source,
            message=message,
            timestamp=datetime.now(timezone.utc).isoformat(),
            details=details,
        )
        try:
            with open(self._today_file(), "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(alert), ensure_ascii=False) + "\n")
        except OSError as e:
            LOGGER.error("Failed to write alert: %s", e)

        if level == "critical":
            LOGGER.critical("[ALERT] %s: %s", source, message)
        elif level == "error":
            LOGGER.error("[ALERT] %s: %s", source, message)
        else:
            LOGGER.warning("[ALERT] %s: %s", source, message)

        return alert

    def recent(self, limit: int = 20) -> list[Alert]:
        """Read recent alerts from today's file."""
        path = self._today_file()
        if not path.exists():
            return []

        alerts: list[Alert] = []
        try:
            lines = path.read_text(encoding="utf-8").strip().splitlines()
            for line in lines[-limit:]:
                data = json.loads(line)
                alerts.append(Alert(**data))
        except (OSError, json.JSONDecodeError, TypeError) as e:
            LOGGER.warning("Failed to read alerts: %s", e)

        return alerts


# Module-level singleton
_manager: AlertManager | None = None


def get_alert_manager() -> AlertManager:
    """Get or create the global AlertManager singleton."""
    global _manager
    if _manager is None:
        _manager = AlertManager()
    return _manager
