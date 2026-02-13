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

        # ── Perception pipeline scans ────────────────────────────────

        # A股盘中 (9:15-15:30 CST, Mon-Fri)
        self.scheduler.add_job(
            self._perception_scan_job,
            trigger=CronTrigger(
                minute="*/5",
                hour="9-15",
                day_of_week="mon-fri",
                timezone="Asia/Shanghai",
            ),
            id="perception-cn",
            replace_existing=True,
        )

        # 美股盘中 evening leg (21:30-23:55 CST, Mon-Fri)
        self.scheduler.add_job(
            self._perception_scan_job,
            trigger=CronTrigger(
                minute="*/5",
                hour="21-23",
                day_of_week="mon-fri",
                timezone="Asia/Shanghai",
            ),
            id="perception-us-evening",
            replace_existing=True,
        )

        # 美股盘中 morning leg (00:00-04:00 CST, Tue-Sat)
        self.scheduler.add_job(
            self._perception_scan_job,
            trigger=CronTrigger(
                minute="*/5",
                hour="0-4",
                day_of_week="tue-sat",
                timezone="Asia/Shanghai",
            ),
            id="perception-us-morning",
            replace_existing=True,
        )

    def _perception_scan_job(self) -> None:
        """Run one perception scan cycle (sync wrapper for async pipeline)."""
        import asyncio

        from src.perception.pipeline import PerceptionPipeline

        loop = asyncio.new_event_loop()
        try:
            pipeline = PerceptionPipeline()
            loop.run_until_complete(pipeline.start())
            result = loop.run_until_complete(pipeline.scan())
            loop.run_until_complete(pipeline.stop())
            LOGGER.info(
                "Perception scan: %d events, %d signals, %.0fms",
                result.events_fetched,
                result.signals_detected,
                result.duration_ms,
            )
        except Exception as e:
            LOGGER.error("Perception scan failed: %s", e)
        finally:
            loop.close()

    def _refresh_watchlist_job(self) -> None:
        LOGGER.info("Scheduled refresh kicked off")

        # Update industry and super category data
        LOGGER.info("Updating industry daily data...")
        try:
            self._update_industry_data()
        except Exception as e:
            LOGGER.error(f"Failed to update industry data: {e}")

        LOGGER.info("Updating concept daily data...")
        try:
            self._update_concept_data()
        except Exception as e:
            LOGGER.error(f"Failed to update concept data: {e}")

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

    def _update_concept_data(self) -> None:
        """Update concept daily data (AKShare - runs in background)"""
        try:
            import subprocess
            import sys
            from pathlib import Path
            script_path = Path(__file__).parent.parent.parent / "scripts" / "update_concept_daily.py"
            log_path = Path(__file__).parent.parent.parent / "logs" / "concept_daily.log"
            log_path.parent.mkdir(exist_ok=True)

            # Run in background since it takes ~6 minutes
            with open(log_path, "w") as log_file:
                subprocess.Popen(
                    [sys.executable, str(script_path)],
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            LOGGER.info("Concept daily update started in background")
        except Exception as e:
            LOGGER.error(f"Concept daily update exception: {e}", exc_info=True)

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
