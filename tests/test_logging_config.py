"""Tests for logging_config module."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import pytest

from git_ssh_sync.logging_config import logger, setup_logging, _get_default_log_path


def test_get_default_log_path() -> None:
    """Test that default log path is created correctly."""
    log_path = _get_default_log_path()
    assert log_path.parent.name == "logs"
    assert log_path.parent.parent.name == "git-ssh-sync"
    assert log_path.name == "git-ssh-sync.log"


def test_setup_logging_default() -> None:
    """Test setup_logging with default parameters."""
    setup_logging()

    # Check that root logger has handlers
    root_logger = logging.getLogger()
    assert len(root_logger.handlers) >= 2  # Console and file handlers

    # Check that git_ssh_sync logger is available
    assert logger.name == "git_ssh_sync"


def test_setup_logging_with_levels() -> None:
    """Test setup_logging with different log levels."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = Path(tmpdir) / "test.log"

        for level in ["DEBUG", "INFO", "WARNING", "ERROR"]:
            setup_logging(level=level, log_file=log_file)

            # Check that console handler is set to the correct level
            root_logger = logging.getLogger()
            console_handler = None
            file_handler = None

            for handler in root_logger.handlers:
                if isinstance(handler, logging.FileHandler):
                    file_handler = handler
                elif hasattr(handler, "rich_tracebacks"):  # RichHandler
                    console_handler = handler

            assert console_handler is not None
            assert file_handler is not None

            # Console handler should be set to the specified level
            expected_level = getattr(logging, level)
            assert console_handler.level == expected_level

            # File handler should always be DEBUG
            assert file_handler.level == logging.DEBUG


def test_logger_output(capsys: pytest.CaptureFixture[str]) -> None:
    """Test that logger outputs correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = Path(tmpdir) / "test.log"
        setup_logging(level="DEBUG", log_file=log_file)

        # Log messages at different levels
        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")
        logger.error("Error message")

        # Check that messages are written to file
        log_content = log_file.read_text()
        assert "Debug message" in log_content
        assert "Info message" in log_content
        assert "Warning message" in log_content
        assert "Error message" in log_content


def test_logger_level_filtering() -> None:
    """Test that log level filtering works correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = Path(tmpdir) / "test.log"

        # Test with WARNING level (should not show INFO or DEBUG)
        setup_logging(level="WARNING", log_file=log_file)

        # Log messages at different levels
        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")

        # Check that all messages are in file
        log_content = log_file.read_text()
        assert "Debug message" in log_content
        assert "Info message" in log_content
        assert "Warning message" in log_content


def test_log_file_creation() -> None:
    """Test that log file is created correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = Path(tmpdir) / "test.log"
        setup_logging(level="INFO", log_file=log_file)

        assert log_file.exists()

        # Log a message
        logger.info("Test message")

        # Check file content
        content = log_file.read_text()
        assert "Test message" in content
        assert "git_ssh_sync" in content


def test_log_file_directory_creation() -> None:
    """Test that log file parent directories are created."""
    with tempfile.TemporaryDirectory() as tmpdir:
        nested_path = Path(tmpdir) / "nested" / "dir" / "test.log"
        setup_logging(level="INFO", log_file=nested_path)

        assert nested_path.exists()
        assert nested_path.parent.is_dir()
