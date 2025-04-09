"""
Fixtures for pytest.

This file contains fixtures that can be used across all tests.
"""

import os
from collections.abc import Generator
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner
from rich.console import Console

from vibectl.config import Config
from vibectl.console import ConsoleManager


@pytest.fixture
def mock_run_kubectl() -> Generator[Mock, None, None]:
    """Fixture providing patched run_kubectl function for all tests."""
    # We need to patch BOTH the CLI import AND the command_handler module
    # The CLI imports from command_handler, and most tests call the CLI module directly
    with (
        patch("vibectl.cli.run_kubectl") as cli_mock,
        patch("vibectl.command_handler.run_kubectl") as handler_mock,
    ):
        # Set up default mock behavior for successful cases
        handler_mock.return_value = "test output"
        cli_mock.return_value = "test output"

        # Create a special side_effect that intelligently handles different cases
        def mock_side_effect(
            cmd: list[str], capture: bool = False, config: object = None
        ) -> str | None:
            # Default success case
            return "test output"

        # Make the CLI mock delegate to the handler mock to ensure consistent behavior
        handler_mock.side_effect = mock_side_effect
        cli_mock.side_effect = handler_mock

        # Return the handler mock since that's the one that gets used by the CLI code
        yield handler_mock


@pytest.fixture
def mock_handle_command_output() -> Generator[Mock, None, None]:
    """Fixture providing patched handle_command_output function for all tests."""
    # Again patch both paths for consistency
    with (
        patch("vibectl.cli.handle_command_output") as cli_mock,
        patch("vibectl.command_handler.handle_command_output") as handler_mock,
    ):
        # Keep calls in sync - this fixture returns the handler_mock since that's
        # the implementation that actually gets used
        cli_mock.side_effect = handler_mock
        yield handler_mock


@pytest.fixture
def test_console() -> ConsoleManager:
    """Fixture providing a ConsoleManager instance for testing.

    This instance has the console and error_console properties set to record
    output for verification in tests.
    """
    console_manager = ConsoleManager()
    # Get theme and create new Console instances that record output
    theme = console_manager.themes["default"]
    console_manager.console = Console(record=True, theme=theme)
    console_manager.error_console = Console(stderr=True, record=True, theme=theme)
    return console_manager


@pytest.fixture(autouse=True, scope="session")
def ensure_test_config_env(
    tmp_path_factory: pytest.TempPathFactory,
) -> Generator[None, None, None]:
    """Ensure all tests use a separate config directory.

    This prevents tests from interfering with the user's actual configuration.
    """
    # Create a dedicated test config directory
    config_dir = tmp_path_factory.mktemp("vibectl-test-config")

    # Save the original environment
    old_config_dir = os.environ.get("VIBECTL_CONFIG_DIR")

    # Set the test config directory
    os.environ["VIBECTL_CONFIG_DIR"] = str(config_dir)

    try:
        yield
    finally:
        # Restore the original environment
        if old_config_dir:
            os.environ["VIBECTL_CONFIG_DIR"] = old_config_dir
        else:
            if "VIBECTL_CONFIG_DIR" in os.environ:
                del os.environ["VIBECTL_CONFIG_DIR"]


@pytest.fixture
def test_config(tmp_path: Path) -> Config:
    """Fixture providing a Config instance for testing.

    This creates a temporary config file that doesn't affect the real user config.
    """
    # Use a unique temporary directory for each test
    config = Config(base_dir=tmp_path / "vibectl-test-config")
    return config


@pytest.fixture
def cli_runner(tmp_path: Path) -> CliRunner:
    """Fixture providing a Click CLI test runner with isolation.

    This ensures CLI tests don't modify the user's actual configuration.

    Args:
        tmp_path: Pytest fixture providing a temporary directory path

    Returns:
        CliRunner: A Click test runner with an isolated environment
    """
    # No need to set VIBECTL_CONFIG_DIR as it's already set by ensure_test_config_env
    return CliRunner()
