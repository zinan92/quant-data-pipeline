"""Exponential backoff retry utility."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar

from src.utils.logging import LOGGER

T = TypeVar("T")


@dataclass(frozen=True)
class RetryConfig:
    """Immutable retry configuration."""

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    backoff_factor: float = 2.0
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,)


DEFAULT_RETRY = RetryConfig()


def with_retry(
    func: Callable[..., T],
    *args: Any,
    config: RetryConfig = DEFAULT_RETRY,
    label: str = "",
    **kwargs: Any,
) -> T:
    """Execute func with exponential backoff retry.

    Args:
        func: The callable to execute.
        *args: Positional arguments for func.
        config: Retry configuration.
        label: Human-readable label for logging.
        **kwargs: Keyword arguments for func.

    Returns:
        The return value of func on success.

    Raises:
        The last exception if all retries are exhausted.
    """
    task_label = label or getattr(func, "__name__", str(func))
    last_exception: Exception | None = None

    for attempt in range(1, config.max_retries + 1):
        try:
            return func(*args, **kwargs)
        except config.retryable_exceptions as e:
            last_exception = e
            if attempt == config.max_retries:
                LOGGER.error(
                    "[retry] %s failed after %d attempts: %s",
                    task_label, config.max_retries, e,
                )
                raise

            delay = min(
                config.base_delay * (config.backoff_factor ** (attempt - 1)),
                config.max_delay,
            )
            LOGGER.warning(
                "[retry] %s attempt %d/%d failed: %s — retrying in %.1fs",
                task_label, attempt, config.max_retries, e, delay,
            )
            time.sleep(delay)

    # Should not reach here, but satisfy type checker
    raise last_exception  # type: ignore[misc]
