from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config import get_settings
from src.tasks.task_runner import run_script
from src.utils.alerting import get_alert_manager
from src.utils.logging import LOGGER
from src.utils.retry import RetryConfig, with_retry

# Import script main functions
import sys
from pathlib import Path

# Add scripts directory to path for imports
scripts_dir = Path(__file__).parent.parent.parent / "scripts"
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

_SCHEDULER_RETRY = RetryConfig(
    max_retries=3,
    base_delay=10.0,
    backoff_factor=2.0,
)


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
            coalesce=True,
            max_instances=1,
            misfire_grace_time=7200,
        )

        # Second evening window for resilience: if first post-close run was missed
        # due restart/provider lag, run once more later the same night.
        self.scheduler.add_job(
            self._refresh_watchlist_job,
            trigger=CronTrigger(
                hour=20,
                minute=30,
                day_of_week="mon-fri",
                timezone=self.settings.scheduler.timezone,
            ),
            id="daily-refresh-retry",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=7200,
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
            try:
                result = loop.run_until_complete(pipeline.scan())
                LOGGER.info(
                    "Perception scan: %d events, %d signals, %.0fms",
                    result.events_fetched,
                    result.signals_detected,
                    result.duration_ms,
                )
            finally:
                loop.run_until_complete(pipeline.stop())
        except Exception as e:
            LOGGER.error("Perception scan failed: %s", e)
            get_alert_manager().emit("warning", "scheduler.perception", str(e))
        finally:
            loop.close()

    def _refresh_watchlist_job(self) -> None:
        LOGGER.info("Scheduled refresh kicked off")

        alerts = get_alert_manager()

        # Update industry and super category data
        LOGGER.info("Updating industry daily data...")
        try:
            with_retry(
                self._update_industry_data,
                config=_SCHEDULER_RETRY,
                label="industry_daily",
            )
        except Exception as e:
            LOGGER.error("Failed to update industry data after retries: %s", e)
            alerts.emit("error", "scheduler.industry", str(e))

        LOGGER.info("Updating concept daily data...")
        try:
            with_retry(
                self._update_concept_data,
                config=_SCHEDULER_RETRY,
                label="concept_daily",
            )
        except Exception as e:
            LOGGER.error("Failed to update concept data after retries: %s", e)
            alerts.emit("error", "scheduler.concept", str(e))

        LOGGER.info("Updating ETF kline and flow data...")
        try:
            with_retry(
                self._update_etf_data,
                config=_SCHEDULER_RETRY,
                label="etf_daily",
            )
        except Exception as e:
            LOGGER.error("Failed to update ETF data after retries: %s", e)
            alerts.emit("error", "scheduler.etf", str(e))

    def _run_script_checked(self, script_name: str, *, timeout: int) -> None:
        """Run script and convert non-zero exit into exceptions for retry pipeline."""
        result = run_script(script_name, timeout=timeout)
        if not result.success:
            stderr = result.stderr[:400] if result.stderr else "no stderr"
            raise RuntimeError(
                f"{script_name} failed (exit={result.exit_code}, {result.duration_seconds:.1f}s): {stderr}"
            )

    def _update_industry_data(self) -> None:
        """Update industry daily data."""
        self._run_script_checked("update_industry_daily.py", timeout=1800)
        LOGGER.info("Industry update completed successfully")

    def _update_concept_data(self) -> None:
        """Update concept daily data (AKShare - runs with timeout monitoring)."""
        self._run_script_checked("update_concept_daily.py", timeout=900)
        LOGGER.info("Concept daily update completed successfully")

    def _update_etf_data(self) -> None:
        """Update ETF kline and flow data."""
        LOGGER.info("Updating ETF daily summary...")
        self._run_script_checked("update_etf_daily_summary.py", timeout=2400)
        LOGGER.info("ETF daily summary update completed successfully")

        LOGGER.info("Building curated ETF filtered snapshot...")
        self._run_script_checked("build_etf_filtered.py", timeout=300)
        LOGGER.info("ETF filtered snapshot build completed successfully")

        LOGGER.info("Updating ETF daily fund flow...")
        self._run_script_checked("update_etf_daily_flow.py", timeout=1800)
        LOGGER.info("ETF daily flow update completed successfully")

        LOGGER.info("Downloading ETF klines...")
        self._run_script_checked("download_etf_klines.py", timeout=1800)
        LOGGER.info("ETF kline download completed successfully")

        LOGGER.info("Calculating ETF fund flow history...")
        self._run_script_checked("calc_etf_flow_history.py", timeout=1800)
        LOGGER.info("ETF flow calculation completed successfully")
