from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.config import get_settings
from src.database import init_db
from src.tasks.scheduler import SchedulerManager
from src.services.kline_scheduler import get_scheduler, stop_scheduler
from src.services.crypto_ws import start_crypto_ws, stop_crypto_ws
from src.utils.logging import LOGGER


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──
    LOGGER.info("Application startup - using Tushare Pro")
    init_db()

    settings = get_settings()
    scheduler_manager = None
    if settings.scheduler:
        scheduler_manager = SchedulerManager()
        scheduler_manager.start()

        kline_scheduler = get_scheduler()
        kline_scheduler.start()
        LOGGER.info("K-line scheduler STARTED (daily=Tushare, 30m=Sina)")

    try:
        await start_crypto_ws()
        LOGGER.info("Crypto WebSocket STARTED (Binance realtime)")
    except Exception as e:
        LOGGER.warning(f"Crypto WebSocket failed to start: {e} (non-fatal)")

    yield

    # ── Shutdown ──
    LOGGER.info("Application shutdown")
    if scheduler_manager:
        scheduler_manager.shutdown()
    stop_scheduler()
    try:
        await stop_crypto_ws()
    except Exception as e:
        LOGGER.warning(f"Crypto WS shutdown error: {e}")
