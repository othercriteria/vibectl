"""Tests for the CLI wait command.

This module tests the CLI wait command of vibectl. All tests in this module
should use appropriate mocking to prevent real calls to kubectl and LLM services.
"""

from collections.abc import Callable, Generator
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest
from click.testing import CliRunner

import vibectl
from vibectl.cli import cli
from vibectl.command_handler import OutputFlags


@pytest.fixture
def mock_run_kubectl_for_cli() -> Generator[MagicMock, None, None]:
    """Mock run_kubectl to avoid actual kubectl calls.

    This fixture specifically patches both the CLI import path and command_handler path.
    """
    with (
        patch("vibectl.cli.run_kubectl") as cli_mock,
        patch("vibectl.command_handler.run_kubectl") as handler_mock,
    ):
        # Set up default responses
        handler_mock.return_value = "test wait output"
        cli_mock.return_value = "test wait output"

        # Make CLI mock delegate to handler mock for consistent behavior
        cli_mock.side_effect = handler_mock

        # Add error response helper
        def set_error_response(stderr: str = "test error") -> None:
            """Configure mock to return an error response."""
            response = f"Error: {stderr}" if stderr else "Error: Command failed"
            handler_mock.return_value = response
            cli_mock.return_value = response

        handler_mock.set_error_response = set_error_response

        yield handler_mock


@pytest.fixture
def mock_handle_output_for_cli() -> Generator[MagicMock, None, None]:
    """Mock handle_command_output for testing."""
    with (
        patch("vibectl.cli.handle_command_output") as cli_mock,
        patch("vibectl.command_handler.handle_command_output") as handler_mock,
    ):
        # Make CLI mock delegate to handler mock
        cli_mock.side_effect = handler_mock

        yield handler_mock


@pytest.fixture
def mock_asyncio_for_wait() -> Generator[MagicMock, None, None]:
    """Mock asyncio functionality for wait command tests to avoid coroutine warnings."""
    # Create a mock event loop
    mock_loop = MagicMock()
    mock_loop.run_until_complete.side_effect = lambda coro: "pod/nginx condition met"
    mock_loop.is_running.return_value = False

    # Create synchronous (non-async) mocks to avoid coroutine warnings
    def mock_sleep(delay: float, *args: Any, **kwargs: Any) -> None:
        """Mock sleep as a regular function to avoid coroutine warnings."""
        return None

    def mock_wait_for(coro: Any, timeout: float) -> Any:
        """Mock wait_for as a regular function to avoid coroutine warnings."""
        return None

    def mock_to_thread(func: Callable, *args: Any, **kwargs: Any) -> Any:
        """Mock to_thread as a regular function to avoid coroutine warnings."""
        return "pod/nginx condition met"

    def mock_create_task(coro: Any) -> MagicMock:
        """Mock create_task to return a MagicMock instead of a Task object."""
        task = MagicMock()
        task.done.return_value = False
        task.cancel.return_value = None
        return task

    # Use a patch context manager to replace all asyncio functions we use
    with (
        # Mock asyncio functions
        patch("vibectl.command_handler.asyncio.get_event_loop", return_value=mock_loop),
        patch("vibectl.command_handler.asyncio.new_event_loop", return_value=mock_loop),
        patch("vibectl.command_handler.asyncio.set_event_loop"),
        # Replace all async functions with synchronous versions
        patch("vibectl.command_handler.asyncio.sleep", mock_sleep),
        patch("vibectl.command_handler.asyncio.wait_for", mock_wait_for),
        patch("vibectl.command_handler.asyncio.to_thread", mock_to_thread),
        patch("vibectl.command_handler.asyncio.create_task", mock_create_task),
        # Replace asyncio exceptions with regular Exception to avoid awaiting issues
        patch("vibectl.command_handler.asyncio.CancelledError", Exception),
        patch("vibectl.command_handler.asyncio.TimeoutError", Exception),
        # Also mock any direct asyncio imports in the test module
        patch("asyncio.create_task", mock_create_task),
        patch("asyncio.Future", MagicMock),
    ):
        yield mock_loop


@pytest.fixture
def mock_console(monkeypatch: Any) -> Generator[MagicMock, None, None]:
    """Mock console manager for CLI tests."""
    mock = MagicMock()

    # Add console attribute for direct print calls
    mock.console = MagicMock()

    with (
        patch("vibectl.cli.console_manager", mock),
        patch("vibectl.command_handler.console_manager", mock),
    ):
        yield mock


def test_wait_basic(
    cli_runner: CliRunner,
    mock_run_kubectl_for_cli: MagicMock,
    mock_handle_output_for_cli: MagicMock,
    mock_asyncio_for_wait: MagicMock,
    mock_memory: Mock,
) -> None:
    """Test wait command with basic arguments."""
    # Set up mock kubectl output
    mock_run_kubectl_for_cli.return_value = "pod/nginx condition met"

    # Configure mock_asyncio_for_wait to return our result
    mock_asyncio_for_wait.run_until_complete.return_value = "pod/nginx condition met"

    # Invoke CLI with --no-live-display to use the standard command handler
    result = cli_runner.invoke(
        cli,
        ["wait", "pod/nginx", "--for=condition=Ready", "--no-live-display"],
        catch_exceptions=False,
    )

    # Print result details for debugging
    if result.exit_code != 0:
        print(f"Exit code: {result.exit_code}")
        print(f"Exception: {result.exception}")
        import traceback

        if result.exc_info:
            print(traceback.format_exception(*result.exc_info))
        print(f"Output: {result.output}")

    # Check results
    assert result.exit_code == 0
    # Run kubectl will be called via asyncio.to_thread
    mock_handle_output_for_cli.assert_called_once()


def test_wait_with_args(
    cli_runner: CliRunner,
    mock_run_kubectl_for_cli: MagicMock,
    mock_handle_output_for_cli: MagicMock,
    mock_asyncio_for_wait: MagicMock,
    mock_memory: Mock,
) -> None:
    """Test wait command with additional arguments."""
    # Set up mock kubectl output
    mock_run_kubectl_for_cli.return_value = "pod/nginx condition met"

    # Invoke CLI with wait command and additional args, and no live display
    result = cli_runner.invoke(
        cli,
        [
            "wait",
            "pod/nginx",
            "--for=condition=Ready",
            "--timeout=30s",
            "-n",
            "default",
            "--no-live-display",
        ],
    )

    # Check results
    assert result.exit_code == 0
    # Run kubectl will be called via asyncio.to_thread
    mock_handle_output_for_cli.assert_called_once()


@patch("vibectl.subcommands.wait_cmd.configure_output_flags")
def test_wait_with_flags(
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
    mock_run_kubectl_for_cli: MagicMock,
    mock_handle_output_for_cli: MagicMock,
    mock_asyncio_for_wait: MagicMock,
    mock_memory: Mock,
) -> None:
    """Test wait command with vibectl-specific flags."""
    # Configure output flags
    mock_configure_flags.return_value = OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=True,
        model_name="claude-3.7-haiku",
    )

    # Set up mock kubectl output
    mock_run_kubectl_for_cli.return_value = "pod/nginx condition met"

    # Invoke CLI with vibectl-specific flags and no live display
    result = cli_runner.invoke(
        cli,
        [
            "wait",
            "pod/nginx",
            "--for=condition=Ready",
            "--show-raw-output",
            "--model",
            "claude-3.7-haiku",
            "--no-live-display",
        ],
    )

    # Check results
    assert result.exit_code == 0
    # Check that we used the configured output flags
    mock_configure_flags.assert_called_once()
    mock_handle_output_for_cli.assert_called_once()


def test_wait_error_handling(
    cli_runner: CliRunner,
    mock_run_kubectl_for_cli: MagicMock,
    mock_handle_output_for_cli: MagicMock,
    mock_asyncio_for_wait: MagicMock,
    mock_memory: Mock,
) -> None:
    """Test wait command error handling."""
    # Set up mock kubectl output for a timeout or error
    mock_run_kubectl_for_cli.set_error_response("timed out waiting for the condition")

    # Invoke CLI with wait command and no live display
    result = cli_runner.invoke(
        cli,
        [
            "wait",
            "pod/nginx",
            "--for=condition=Ready",
            "--timeout=1s",
            "--no-live-display",
        ],
    )

    # Check results
    assert result.exit_code == 0  # CLI should handle the error gracefully
    # Make sure the output was processed
    mock_handle_output_for_cli.assert_called_once()


@patch("vibectl.subcommands.wait_cmd.handle_vibe_request")
def test_wait_vibe_request(
    mock_handle_vibe: MagicMock, cli_runner: CliRunner, mock_memory: Mock
) -> None:
    """Test wait command with vibe request."""
    # Invoke CLI with vibe request
    result = cli_runner.invoke(
        cli, ["wait", "vibe", "wait until the deployment myapp is ready"]
    )

    # Check results
    assert result.exit_code == 0
    mock_handle_vibe.assert_called_once()
    assert (
        mock_handle_vibe.call_args[1]["request"]
        == "wait until the deployment myapp is ready"
    )
    assert mock_handle_vibe.call_args[1]["command"] == "wait"


@patch("vibectl.subcommands.wait_cmd.console_manager")
def test_wait_vibe_no_request(
    mock_console: Mock, cli_runner: CliRunner, mock_memory: Mock
) -> None:
    """Test wait command with vibe but no request."""
    # Invoke CLI with vibe but no request
    result = cli_runner.invoke(cli, ["wait", "vibe"])

    # Check results
    assert result.exit_code == 1  # Missing request should exit with error
    mock_console.print_error.assert_called_once_with("Missing request after 'vibe'")


def test_wait_with_live_display_asyncio(
    cli_runner: CliRunner,
    mock_run_kubectl_for_cli: MagicMock,
    mock_handle_output_for_cli: MagicMock,
    mock_asyncio_for_wait: MagicMock,
    mock_memory: Mock,
) -> None:
    """Test wait command with live display using asyncio."""
    from unittest.mock import patch
    from vibectl.subcommands import wait_cmd as wait_cmd_module

    result_value = "pod/nginx condition met"
    mock_run_kubectl_for_cli.return_value = result_value

    with patch.object(
        wait_cmd_module, "handle_wait_with_live_display", return_value=None
    ) as mock_wait_live_display:
        cli_runner.invoke(
            cli, ["wait", "pod/nginx", "--for=condition=Ready", "--live-display"]
        )
        mock_wait_live_display.assert_called_once()
        assert mock_wait_live_display.call_args[1]["resource"] == "pod/nginx"


def test_wait_with_live_display_error_asyncio(
    cli_runner: CliRunner,
    mock_run_kubectl_for_cli: MagicMock,
    mock_handle_output_for_cli: MagicMock,
    mock_asyncio_for_wait: MagicMock,
    mock_memory: Mock,
) -> None:
    """Test wait command with live display handling errors using asyncio."""
    from unittest.mock import patch
    from vibectl.subcommands import wait_cmd as wait_cmd_module

    error_response = "Error: timed out waiting for the condition"
    mock_run_kubectl_for_cli.return_value = error_response

    with patch.object(
        wait_cmd_module, "handle_wait_with_live_display", return_value=None
    ) as mock_wait_live_display:
        cli_runner.invoke(
            cli,
            [
                "wait",
                "pod/nginx",
                "--for=condition=Ready",
                "--timeout=1s",
                "--live-display",
            ],
        )
        mock_wait_live_display.assert_called_once()
        assert "--timeout=1s" in mock_wait_live_display.call_args[1]["args"]
