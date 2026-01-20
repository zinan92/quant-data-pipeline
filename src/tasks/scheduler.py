from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config import get_settings
from src.utils.logging import LOGGER


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
        import subprocess
        from pathlib import Path

        script_path = Path(__file__).parent.parent.parent / "scripts" / "update_industry_daily.py"
        result = subprocess.run(
            ["python", str(script_path)],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            LOGGER.error(f"Industry update failed: {result.stderr}")
        else:
            LOGGER.info("Industry update completed successfully")

    def _update_super_category_data(self) -> None:
        """Update super category daily data"""
        import subprocess
        from pathlib import Path

        script_path = Path(__file__).parent.parent.parent / "scripts" / "update_super_category_daily.py"
        result = subprocess.run(
            ["python", str(script_path)],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            LOGGER.error(f"Super category update failed: {result.stderr}")
        else:
            LOGGER.info("Super category update completed successfully")

    def _update_etf_data(self) -> None:
        """Update ETF kline and flow data"""
        import subprocess
        from pathlib import Path

        scripts_dir = Path(__file__).parent.parent.parent / "scripts"

        # 0. Refresh the raw ETF daily summary so downstream scripts see latest data
        LOGGER.info("Updating ETF daily summary...")
        summary_script = scripts_dir / "update_etf_daily_summary.py"
        result = subprocess.run(
            ["python", str(summary_script)],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            LOGGER.error(f"ETF daily summary update failed: {result.stderr}")
            return
        LOGGER.info("ETF daily summary update completed successfully")

        # 0.1 Build curated filtered snapshot for the dashboard and downstream scripts
        LOGGER.info("Building curated ETF filtered snapshot...")
        filtered_script = scripts_dir / "build_etf_filtered.py"
        result = subprocess.run(
            ["python", str(filtered_script)],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            LOGGER.error(f"ETF filtered snapshot build failed: {result.stderr}")
            return
        LOGGER.info("ETF filtered snapshot build completed successfully")

        # 0.2 Update ETF daily fund flow from akshare
        LOGGER.info("Updating ETF daily fund flow...")
        flow_update_script = scripts_dir / "update_etf_daily_flow.py"
        result = subprocess.run(
            ["python", str(flow_update_script)],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            LOGGER.error(f"ETF daily flow update failed: {result.stderr}")
        else:
            LOGGER.info("ETF daily flow update completed successfully")

        # 1. Download ETF klines and calculate trend indicators
        LOGGER.info("Downloading ETF klines...")
        kline_script = scripts_dir / "download_etf_klines.py"
        result = subprocess.run(
            ["python", str(kline_script)],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            LOGGER.error(f"ETF kline download failed: {result.stderr}")
        else:
            LOGGER.info("ETF kline download completed successfully")

        # 2. Calculate 7d/30d fund flow history
        LOGGER.info("Calculating ETF fund flow history...")
        flow_script = scripts_dir / "calc_etf_flow_history.py"
        result = subprocess.run(
            ["python", str(flow_script)],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            LOGGER.error(f"ETF flow calculation failed: {result.stderr}")
        else:
            LOGGER.info("ETF flow calculation completed successfully")
