"""Tests for momentum signal detection logic."""

import json
from pathlib import Path

import pytest


def test_momentum_signals_file_loads():
    """Test that momentum_signals.json can be loaded when it exists."""
    signals_file = Path(__file__).parent.parent / "data" / "monitor" / "momentum_signals.json"
    if not signals_file.exists():
        pytest.skip("momentum_signals.json not present (data not generated yet)")

    data = json.loads(signals_file.read_text(encoding="utf-8"))
    assert isinstance(data, (list, dict)), "momentum_signals.json should contain a list or dict"


def test_concept_monitor_route_exists():
    """Verify the concept-monitor router includes a momentum-signals endpoint."""
    from src.api.routes_concept_monitor_v2 import router

    paths = [route.path for route in router.routes]
    assert "/momentum-signals" in paths, (
        f"Expected /momentum-signals in concept-monitor routes, got {paths}"
    )
