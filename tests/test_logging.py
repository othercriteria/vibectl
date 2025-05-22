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
            if key == "log_level":
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


def test_console_manager_handler_warn_and_error(monkeypatch: MonkeyPatch) -> None:
    # Patch console_manager methods
    with (
        patch("vibectl.console.console_manager.print_warning") as mock_warn,
        patch("vibectl.console.console_manager.print_error") as mock_err,
    ):
        vclogmod.init_logging()
        logger = vclogmod.logger
        logger.warning("Test warning")
        logger.error("Test error")
        mock_warn.assert_called_with("Test warning")
        mock_err.assert_called_with("Test error")


def test_console_manager_handler_info_and_debug(monkeypatch: MonkeyPatch) -> None:
    # Patch console_manager methods
    with (
        patch("vibectl.console.console_manager.print_warning") as mock_warn,
        patch("vibectl.console.console_manager.print_error") as mock_err,
    ):
        vclogmod.init_logging()
        logger = vclogmod.logger
        logger.info("Test info")
        mock_warn.assert_not_called()
        mock_err.assert_not_called()


def test_handler_not_duplicated() -> None:
    vclogmod.init_logging()
    logger = vclogmod.logger
    handler_count = sum(
        isinstance(h, vclogmod.ConsoleManagerHandler) for h in logger.handlers
    )
    assert handler_count == 1
    # Call again, should not add another
    vclogmod.init_logging()
    handler_count2 = sum(
        isinstance(h, vclogmod.ConsoleManagerHandler) for h in logger.handlers
    )
    assert handler_count2 == 1
