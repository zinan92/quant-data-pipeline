from __future__ import annotations

import pytest

import src.tasks.scheduler as scheduler_module
from src.tasks.scheduler import SchedulerManager
from src.tasks.task_runner import TaskResult


def _task_result(script_name: str, exit_code: int) -> TaskResult:
    return TaskResult(
        task_name=script_name,
        exit_code=exit_code,
        duration_seconds=1.0,
        stdout="",
        stderr="boom" if exit_code != 0 else "",
        started_at=0.0,
        finished_at=1.0,
    )


def test_update_industry_data_raises_on_script_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = SchedulerManager()

    monkeypatch.setattr(
        scheduler_module,
        "run_script",
        lambda *args, **kwargs: _task_result("update_industry_daily.py", 1),
    )

    with pytest.raises(RuntimeError):
        manager._update_industry_data()


def test_update_etf_data_raises_when_required_step_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = SchedulerManager()

    def _fake_run_script(script_name: str, **kwargs) -> TaskResult:
        if script_name == "update_etf_daily_summary.py":
            return _task_result(script_name, 1)
        return _task_result(script_name, 0)

    monkeypatch.setattr(scheduler_module, "run_script", _fake_run_script)

    with pytest.raises(RuntimeError):
        manager._update_etf_data()
