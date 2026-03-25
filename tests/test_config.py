"""
Tests for config value verification.

Validates:
- CANDLE_LOOKBACK defaults to 1250 in config.py
- CANDLE_LOOKBACK can be overridden via .env
"""

import os
from pathlib import Path

import pytest

from src.config import Settings, get_settings


class TestConfigValues:
    """Test configuration defaults and overrides."""

    def test_candle_lookback_default_is_1250(self):
        """Config default for candle_lookback should be 1250."""
        # Create settings without env file override
        settings = Settings(
            _env_file=None,  # Don't read .env
            tushare_token="test_token",
        )
        assert settings.candle_lookback == 1250, "Default candle_lookback should be 1250"

    def test_candle_lookback_from_env(self, monkeypatch):
        """CANDLE_LOOKBACK can be overridden via environment variable."""
        # Set env var
        monkeypatch.setenv("CANDLE_LOOKBACK", "2000")

        # Create fresh settings
        settings = Settings(
            _env_file=None,
            tushare_token="test_token",
        )
        assert settings.candle_lookback == 2000, "CANDLE_LOOKBACK should read from env"

    def test_candle_lookback_in_actual_env_file(self):
        """Verify .env file has CANDLE_LOOKBACK=1250."""
        env_path = Path(__file__).parent.parent / ".env"
        if not env_path.exists():
            pytest.skip(".env file not found")

        env_content = env_path.read_text()
        assert (
            "CANDLE_LOOKBACK=1250" in env_content
        ), ".env should contain CANDLE_LOOKBACK=1250"

    def test_get_settings_singleton(self):
        """get_settings() returns the same instance and has correct candle_lookback."""
        # Clear cache to force fresh load
        get_settings.cache_clear()

        settings = get_settings()
        assert settings.candle_lookback == 1250, "get_settings() should return candle_lookback=1250"

        # Verify singleton behavior
        settings2 = get_settings()
        assert settings is settings2, "get_settings() should return the same instance"
