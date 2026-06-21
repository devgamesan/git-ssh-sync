"""Logging configuration for git-ssh-sync."""

from __future__ import annotations

import logging
from pathlib import Path

from rich.logging import RichHandler


def _get_default_log_path() -> Path:
    """Get the default log file path."""
    cache_dir = Path.home() / ".cache" / "git-ssh-sync" / "logs"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "git-ssh-sync.log"


def setup_logging(
    *,
    level: str = "WARNING",
    log_file: str | Path | None = None,
) -> None:
    """Configure logging for git-ssh-sync.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR).
        log_file: Optional path to log file. If not provided, uses default path.
    """
    # Map level string to logging constants
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
    }
    log_level = level_map.get(level.upper(), logging.WARNING)

    # Remove existing handlers to avoid duplicates
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Console handler with Rich
    console_handler = RichHandler(
        console=None,  # Use default Rich console
        show_time=False,
        show_path=False,
        rich_tracebacks=True,
        tracebacks_show_locals=True,
        markup=True,
    )
    console_handler.setLevel(log_level)
    console_formatter = logging.Formatter("%(message)s")
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # File handler (always logs at DEBUG level)
    if log_file is None:
        log_file = _get_default_log_path()
    else:
        log_file = Path(log_file)

    log_file = Path(log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)  # Always log everything to file
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # Set root logger level to the minimum of all handlers
    root_logger.setLevel(logging.DEBUG)

    # Silence noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


# Global logger instance
logger = logging.getLogger("git_ssh_sync")
