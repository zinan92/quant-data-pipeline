"""Run external scripts with timeout, output capture, and exit code tracking.

Replaces fire-and-forget subprocess.Popen patterns with monitored execution.
"""
from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from src.utils.logging import LOGGER


@dataclass(frozen=True)
class TaskResult:
    """Immutable result of a script execution."""

    task_name: str
    exit_code: int
    duration_seconds: float
    stdout: str
    stderr: str
    started_at: float
    finished_at: float

    @property
    def success(self) -> bool:
        return self.exit_code == 0


_SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"
_LOGS_DIR = Path(__file__).parent.parent.parent / "logs"


def run_script(
    script_name: str,
    *,
    timeout: int = 600,
    log_to_file: bool = True,
) -> TaskResult:
    """Run a Python script synchronously with timeout and full output capture.

    Args:
        script_name: Name of the script file in scripts/ directory.
        timeout: Max seconds before killing the process. Default 600 (10 min).
        log_to_file: Whether to also write stdout to logs/{script_stem}.log.

    Returns:
        Immutable TaskResult with exit code, output, and timing info.
    """
    script_path = _SCRIPTS_DIR / script_name
    if not script_path.exists():
        LOGGER.error("Script not found: %s", script_path)
        return TaskResult(
            task_name=script_name,
            exit_code=-1,
            duration_seconds=0.0,
            stdout="",
            stderr=f"Script not found: {script_path}",
            started_at=time.time(),
            finished_at=time.time(),
        )

    started_at = time.time()
    LOGGER.info("Running script: %s (timeout=%ds)", script_name, timeout)

    try:
        completed = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(script_path.parent.parent),
        )
        finished_at = time.time()
        duration = finished_at - started_at

        result = TaskResult(
            task_name=script_name,
            exit_code=completed.returncode,
            duration_seconds=round(duration, 1),
            stdout=completed.stdout[-5000:] if len(completed.stdout) > 5000 else completed.stdout,
            stderr=completed.stderr[-2000:] if len(completed.stderr) > 2000 else completed.stderr,
            started_at=started_at,
            finished_at=finished_at,
        )

    except subprocess.TimeoutExpired:
        finished_at = time.time()
        LOGGER.error("Script timed out after %ds: %s", timeout, script_name)
        result = TaskResult(
            task_name=script_name,
            exit_code=-2,
            duration_seconds=round(finished_at - started_at, 1),
            stdout="",
            stderr=f"Timed out after {timeout}s",
            started_at=started_at,
            finished_at=finished_at,
        )

    except Exception as e:
        finished_at = time.time()
        LOGGER.error("Script execution error: %s — %s", script_name, e)
        result = TaskResult(
            task_name=script_name,
            exit_code=-3,
            duration_seconds=round(finished_at - started_at, 1),
            stdout="",
            stderr=str(e),
            started_at=started_at,
            finished_at=finished_at,
        )

    # Log outcome
    if result.success:
        LOGGER.info(
            "Script completed: %s (%.1fs, exit=%d)",
            script_name, result.duration_seconds, result.exit_code,
        )
    else:
        LOGGER.error(
            "Script failed: %s (%.1fs, exit=%d) — %s",
            script_name, result.duration_seconds, result.exit_code,
            result.stderr[:200] if result.stderr else "no stderr",
        )

    # Optionally persist output to log file
    if log_to_file:
        log_path = _LOGS_DIR / f"{Path(script_name).stem}.log"
        log_path.parent.mkdir(exist_ok=True)
        try:
            log_path.write_text(result.stdout, encoding="utf-8")
        except OSError as e:
            LOGGER.warning("Failed to write log file %s: %s", log_path, e)

    return result
