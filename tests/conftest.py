"""
Fixtures for pytest.

This file contains fixtures that can be used across all tests.
"""

from collections.abc import Generator
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
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
        # Keep both mocks in sync
        handler_mock.return_value = "test output"
        cli_mock.return_value = "test output"

        # Make the CLI mock delegate to the handler mock to ensure consistent behavior
        cli_mock.side_effect = handler_mock.side_effect

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


@pytest.fixture
def test_config() -> Config:
    """Fixture providing a Config instance for testing.

    This creates a temporary config file that doesn't affect the real user config.
    """
    # Use tmp_path_factory but we don't need it as a parameter since we're
    # using default Path for isolation
    config = Config(base_dir=Path("/tmp/vibectl-test-config"))
    return config
