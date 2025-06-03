import logging
from collections.abc import Generator
from unittest.mock import patch

import pytest
from pytest import MonkeyPatch

import vibectl.logutil as vclogmod


@pytest.fixture(autouse=True)
def reset_logger_handlers() -> Generator[None, None, None]:
    # Remove all handlers before each test
    logger = vclogmod.logger
    for h in logger.handlers[:]:
        logger.removeHandler(h)
    yield
    for h in logger.handlers[:]:
        logger.removeHandler(h)


def test_logger_respects_config_log_level(monkeypatch: MonkeyPatch) -> None:
    class DummyConfig:
        def get(self, key: str, default: object = None) -> object:
            if key == "system.log_level":
                return "ERROR"
            return default

    monkeypatch.setattr(vclogmod, "Config", lambda: DummyConfig())
    vclogmod.init_logging()
    assert vclogmod.logger.level == logging.ERROR


def test_logger_respects_env_var(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("VIBECTL_LOG_LEVEL", "DEBUG")
    vclogmod.init_logging()
    assert vclogmod.logger.level == logging.DEBUG
    monkeypatch.delenv("VIBECTL_LOG_LEVEL")


def test_error_filtered_out_but_warning_allowed_in_streamhandler(
    monkeypatch: MonkeyPatch,
) -> None:
    """Test StreamHandler filters ERROR messages but allows WARNING messages."""
    vclogmod.init_logging()
    logger = vclogmod.logger

    # Find the StreamHandler
    stream_handlers = [
        h for h in logger.handlers if isinstance(h, logging.StreamHandler)
    ]
    assert len(stream_handlers) == 1
    stream_handler = stream_handlers[0]

    # Test that the filter allows WARNING but blocks ERROR
    warning_record = logging.LogRecord(
        name="test",
        level=logging.WARNING,
        pathname="",
        lineno=0,
        msg="Test warning",
        args=(),
        exc_info=None,
    )
    error_record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname="",
        lineno=0,
        msg="Test error",
        args=(),
        exc_info=None,
    )

    # WARNING should pass through (return True), ERROR should be filtered
    # out (return False)
    assert stream_handler.filter(warning_record)
    assert not stream_handler.filter(error_record)


def test_info_debug_and_warning_allowed_in_streamhandler(
    monkeypatch: MonkeyPatch,
) -> None:
    """Test that INFO, DEBUG, and WARNING messages are allowed through StreamHandler."""
    vclogmod.init_logging()
    logger = vclogmod.logger

    # Find the StreamHandler
    stream_handlers = [
        h for h in logger.handlers if isinstance(h, logging.StreamHandler)
    ]
    assert len(stream_handlers) == 1
    stream_handler = stream_handlers[0]

    # Test that INFO, DEBUG, and WARNING pass through
    info_record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Test info",
        args=(),
        exc_info=None,
    )
    debug_record = logging.LogRecord(
        name="test",
        level=logging.DEBUG,
        pathname="",
        lineno=0,
        msg="Test debug",
        args=(),
        exc_info=None,
    )
    warning_record = logging.LogRecord(
        name="test",
        level=logging.WARNING,
        pathname="",
        lineno=0,
        msg="Test warning",
        args=(),
        exc_info=None,
    )

    # INFO, DEBUG, and WARNING should all pass through (return True)
    assert stream_handler.filter(info_record)
    assert stream_handler.filter(debug_record)
    assert stream_handler.filter(warning_record)


def test_handler_not_duplicated() -> None:
    """Test that init_logging() doesn't create duplicate handlers."""
    vclogmod.init_logging()
    logger = vclogmod.logger
    initial_handler_count = len(logger.handlers)

    # Call again, should not add more handlers
    vclogmod.init_logging()
    final_handler_count = len(logger.handlers)

    assert initial_handler_count == final_handler_count
    # Should have exactly one StreamHandler
    stream_handlers = [
        h for h in logger.handlers if isinstance(h, logging.StreamHandler)
    ]
    assert len(stream_handlers) == 1


def test_streamhandler_info_not_routed_to_console_manager(
    monkeypatch: MonkeyPatch,
) -> None:
    """Test that INFO messages go to StreamHandler only, not console_manager."""
    # Patch console_manager methods to ensure they're not called
    with (
        patch("vibectl.console.console_manager.print_warning") as mock_warn,
        patch("vibectl.console.console_manager.print_error") as mock_err,
    ):
        vclogmod.init_logging()
        logger = vclogmod.logger
        logger.info("Test info")
        # INFO should not trigger console_manager calls
        mock_warn.assert_not_called()
        mock_err.assert_not_called()
