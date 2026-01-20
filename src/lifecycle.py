from fastapi import FastAPI

from src.config import get_settings
from src.database import init_db
from src.tasks.scheduler import SchedulerManager
from src.services.kline_scheduler import get_scheduler, stop_scheduler
from src.utils.logging import LOGGER

_scheduler_manager: SchedulerManager | None = None


def register_startup_shutdown(app: FastAPI) -> None:
    @app.on_event("startup")
    async def _startup() -> None:
        LOGGER.info("Application startup - using Tushare Pro")

        # Tushare does not require patches like AkShare did

        init_db()
        settings = get_settings()
        if settings.scheduler:
            global _scheduler_manager
            _scheduler_manager = SchedulerManager()
            _scheduler_manager.start()

            # 启动K线数据调度器
            LOGGER.info("Starting K-line data scheduler...")
            kline_scheduler = get_scheduler()
            kline_scheduler.start()

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        LOGGER.info("Application shutdown")
        if _scheduler_manager:
            _scheduler_manager.shutdown()

        # 停止K线数据调度器
        stop_scheduler()
