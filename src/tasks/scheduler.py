from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config import get_settings
from src.utils.logging import LOGGER

# Import script main functions
import sys
from pathlib import Path

# Add scripts directory to path for imports
scripts_dir = Path(__file__).parent.parent.parent / "scripts"
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))


class SchedulerManager:
    """Wrapper around APScheduler to manage recurring refresh jobs."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.scheduler = BackgroundScheduler(
            timezone=self.settings.scheduler.timezone
        )

    def start(self) -> None:
        LOGGER.info("Starting scheduler")
        if not self.scheduler.running:
            self._register_jobs()
            self.scheduler.start()

    def shutdown(self) -> None:
        if self.scheduler.running:
            LOGGER.info("Shutting down scheduler")
            self.scheduler.shutdown(wait=False)

    def _register_jobs(self) -> None:
        cron = CronTrigger.from_crontab(self.settings.scheduler.daily_refresh_cron)
        self.scheduler.add_job(
            self._refresh_watchlist_job,
            trigger=cron,
            id="daily-refresh",
            replace_existing=True,
        )

    def _refresh_watchlist_job(self) -> None:
        LOGGER.info("Scheduled refresh kicked off")

        # Update industry and super category data
        LOGGER.info("Updating industry daily data...")
        try:
            self._update_industry_data()
        except Exception as e:
            LOGGER.error(f"Failed to update industry data: {e}")

        LOGGER.info("Updating super category daily data...")
        try:
            self._update_super_category_data()
        except Exception as e:
            LOGGER.error(f"Failed to update super category data: {e}")

        LOGGER.info("Updating ETF kline and flow data...")
        try:
            self._update_etf_data()
        except Exception as e:
            LOGGER.error(f"Failed to update ETF data: {e}")

    def _update_industry_data(self) -> None:
        """Update industry daily data"""
        try:
            from scripts.update_industry_daily import main as update_industry_main
            result = update_industry_main()
            if result != 0:
                LOGGER.error("Industry update failed")
            else:
                LOGGER.info("Industry update completed successfully")
        except Exception as e:
            LOGGER.error(f"Industry update exception: {e}", exc_info=True)

    def _update_super_category_data(self) -> None:
        """Update super category daily data"""
        try:
            from scripts.update_super_category_daily import update_super_category_daily
            update_super_category_daily()
            LOGGER.info("Super category update completed successfully")
        except Exception as e:
            LOGGER.error(f"Super category update exception: {e}", exc_info=True)

    def _update_etf_data(self) -> None:
        """Update ETF kline and flow data"""
        # 0. Refresh the raw ETF daily summary so downstream scripts see latest data
        LOGGER.info("Updating ETF daily summary...")
        try:
            from scripts.update_etf_daily_summary import main as update_etf_summary_main
            result = update_etf_summary_main()
            if result != 0:
                LOGGER.error("ETF daily summary update failed")
                return
            LOGGER.info("ETF daily summary update completed successfully")
        except Exception as e:
            LOGGER.error(f"ETF daily summary update exception: {e}", exc_info=True)
            return

        # 0.1 Build curated filtered snapshot for the dashboard and downstream scripts
        LOGGER.info("Building curated ETF filtered snapshot...")
        try:
            from scripts.build_etf_filtered import main as build_etf_filtered_main
            build_etf_filtered_main()
            LOGGER.info("ETF filtered snapshot build completed successfully")
        except Exception as e:
            LOGGER.error(f"ETF filtered snapshot build exception: {e}", exc_info=True)
            return

        # 0.2 Update ETF daily fund flow from akshare
        LOGGER.info("Updating ETF daily fund flow...")
        try:
            from scripts.update_etf_daily_flow import main as update_etf_flow_main
            result = update_etf_flow_main()
            if result != 0:
                LOGGER.error("ETF daily flow update failed")
            else:
                LOGGER.info("ETF daily flow update completed successfully")
        except Exception as e:
            LOGGER.error(f"ETF daily flow update exception: {e}", exc_info=True)

        # 1. Download ETF klines and calculate trend indicators
        LOGGER.info("Downloading ETF klines...")
        try:
            from scripts.download_etf_klines import main as download_etf_klines_main
            result = download_etf_klines_main()
            if result != 0:
                LOGGER.error("ETF kline download failed")
            else:
                LOGGER.info("ETF kline download completed successfully")
        except Exception as e:
            LOGGER.error(f"ETF kline download exception: {e}", exc_info=True)

        # 2. Calculate 7d/30d fund flow history
        LOGGER.info("Calculating ETF fund flow history...")
        try:
            from scripts.calc_etf_flow_history import main as calc_etf_flow_history_main
            result = calc_etf_flow_history_main()
            if result != 0:
                LOGGER.error("ETF flow calculation failed")
            else:
                LOGGER.info("ETF flow calculation completed successfully")
        except Exception as e:
            LOGGER.error(f"ETF flow calculation exception: {e}", exc_info=True)
