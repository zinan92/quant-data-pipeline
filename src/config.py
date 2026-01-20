from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SchedulerConfig(BaseModel):
    daily_refresh_cron: str = "30 15 * * 1-5"  # 15:30 each trading day (Asia/Shanghai)
    timezone: str = "Asia/Shanghai"


class TushareConfig(BaseModel):
    """Tushare Pro API configuration"""
    token: str
    points: int = 15000
    delay: float = 0.3  # seconds between requests
    max_retries: int = 3


class ProxyConfig(BaseModel):
    """DEPRECATED: Proxy configuration (no longer needed with Tushare)"""
    enabled: bool = False
    tunnel: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
        extra="ignore",
    )

    database_url: str = Field(default="sqlite:///data/market.db", alias="DATABASE_URL")
    data_dir: Path = Field(default=Path("data"), alias="DATA_DIR")
    logs_dir: Path = Field(default=Path("logs"), alias="LOGS_DIR")

    default_symbols_str: str = Field(default="", alias="DEFAULT_SYMBOLS")
    candle_lookback: int = Field(default=120, alias="CANDLE_LOOKBACK")

    cors_allow_origins_str: str = Field(default="http://localhost:5173", alias="ALLOW_ORIGINS")

    # Tushare configuration
    tushare_token: str = Field(default="", alias="TUSHARE_TOKEN")
    tushare_points: int = Field(default=15000, alias="TUSHARE_POINTS")
    tushare_delay: float = Field(default=0.3, alias="TUSHARE_DELAY")
    tushare_max_retries: int = Field(default=3, alias="TUSHARE_MAX_RETRIES")

    # Feature flags
    enable_concept_boards: bool = Field(default=True, alias="ENABLE_CONCEPT_BOARDS")
    enable_industry_levels: bool = Field(default=True, alias="ENABLE_INDUSTRY_LEVELS")

    scheduler: SchedulerConfig = SchedulerConfig()
    scheduler_cron_override: Optional[str] = Field(
        default=None, alias="DAILY_REFRESH_CRON"
    )
    scheduler_timezone_override: Optional[str] = Field(
        default=None, alias="SCHEDULER_TIMEZONE"
    )

    # DEPRECATED: Proxy config (keeping for backward compatibility)
    proxy: ProxyConfig = ProxyConfig()
    proxy_enabled_override: Optional[bool] = Field(
        default=None, alias="PROXY_ENABLED"
    )
    proxy_tunnel_override: Optional[str] = Field(
        default=None, alias="PROXY_TUNNEL"
    )
    proxy_username_override: Optional[str] = Field(
        default=None, alias="PROXY_USERNAME"
    )
    proxy_password_override: Optional[str] = Field(
        default=None, alias="PROXY_PASSWORD"
    )

    api_prefix: str = "/api"

    @model_validator(mode="after")
    def _apply_scheduler_overrides(self) -> "Settings":
        # Apply scheduler overrides
        if self.scheduler_cron_override:
            self.scheduler.daily_refresh_cron = self.scheduler_cron_override
        if self.scheduler_timezone_override:
            self.scheduler.timezone = self.scheduler_timezone_override

        # Apply proxy overrides
        if self.proxy_enabled_override is not None:
            self.proxy.enabled = self.proxy_enabled_override
        if self.proxy_tunnel_override:
            self.proxy.tunnel = self.proxy_tunnel_override
        if self.proxy_username_override:
            self.proxy.username = self.proxy_username_override
        if self.proxy_password_override:
            self.proxy.password = self.proxy_password_override

        return self

    @property
    def default_symbols(self) -> List[str]:
        """Get default symbols as a list, normalized to 6-digit format."""
        from src.utils.ticker_utils import TickerNormalizer

        if not self.default_symbols_str:
            return []

        raw_tickers = [
            item.strip() for item in self.default_symbols_str.split(",") if item.strip()
        ]

        # Normalize all tickers to ensure they are in correct format
        return TickerNormalizer.normalize_batch(raw_tickers)

    @property
    def cors_allow_origins(self) -> List[str]:
        """Get CORS allowed origins as a list."""
        return [
            item.strip() for item in self.cors_allow_origins_str.split(",") if item.strip()
        ] if self.cors_allow_origins_str else ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    return settings
