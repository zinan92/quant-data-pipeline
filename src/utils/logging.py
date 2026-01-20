import logging
from pathlib import Path

from src.config import get_settings

LOG_FORMAT = (
    "%(asctime)s | %(levelname)s | %(name)s | %(funcName)s:%(lineno)d | %(message)s"
)


def configure_logging() -> None:
    """Configure root logger with console and file handlers."""
    settings = get_settings()
    log_dir: Path = settings.logs_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format=LOG_FORMAT,
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_dir / "service.log", encoding="utf-8"),
        ],
    )


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for the given name.

    Best practice: Use __name__ as the logger name in each module.
    Example: logger = get_logger(__name__)

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


configure_logging()

# Backward compatibility: Keep LOGGER for existing code
LOGGER = logging.getLogger("a_share_monitor")
