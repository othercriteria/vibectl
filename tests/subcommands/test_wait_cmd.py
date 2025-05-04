"""Tests for the CLI wait command.

This module tests the CLI wait command of vibectl. All tests in this module
should use appropriate mocking to prevent real calls to kubectl and LLM services.
"""

from collections.abc import Callable, Generator
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest
from click.testing import CliRunner

from vibectl.cli import cli
from vibectl.command_handler import OutputFlags
from vibectl.subcommands import wait_cmd as wait_cmd_module
from vibectl.types import Error, Success


@pytest.fixture
def mock_run_kubectl_for_cli() -> Generator[MagicMock, None, None]:
    """Mock run_kubectl to avoid actual kubectl calls.

    This fixture specifically patches both the CLI import path and command_handler path.
    """
    with (
        patch("vibectl.command_handler.run_kubectl") as cli_mock,
        patch("vibectl.command_handler.handle_command_output") as handler_mock,
    ):
        # Set up default responses
        handler_mock.return_value = Success(data="test wait output")
        cli_mock.return_value = Success(data="test wait output")

        # Make CLI mock delegate to handler mock for consistent behavior
        cli_mock.side_effect = handler_mock

        # Add error response helper
        def set_error_response(stderr: str = "test error") -> None:
            """Configure mock to return an error response."""
            error_msg = stderr if stderr else "Command failed"
            error_obj = Error(error=error_msg)
            handler_mock.return_value = error_obj
            cli_mock.return_value = error_obj

        handler_mock.set_error_response = set_error_response

        yield handler_mock


@pytest.fixture
def mock_handle_output_for_cli() -> Generator[MagicMock, None, None]:
    """Mock handle_command_output for testing."""
    with (
        patch("vibectl.command_handler.handle_command_output") as cli_mock,
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
        patch("asyncio.get_event_loop", return_value=mock_loop),
        patch("asyncio.new_event_loop", return_value=mock_loop),
        patch("asyncio.set_event_loop"),
        # Replace all async functions with synchronous versions
        patch("asyncio.sleep", mock_sleep),
        patch("asyncio.wait_for", mock_wait_for),
        patch("asyncio.to_thread", mock_to_thread),
        patch("asyncio.create_task", mock_create_task),
        # Replace asyncio exceptions with regular Exception to avoid awaiting issues
        patch("asyncio.CancelledError", Exception),
        patch("asyncio.TimeoutError", Exception),
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
    from vibectl.types import Success

    # Set up mock kubectl output
    mock_run_kubectl_for_cli.return_value = Success(data="pod/nginx condition met")

    # Configure mock_asyncio_for_wait to return our result
    mock_asyncio_for_wait.run_until_complete.return_value = Success(
        data="pod/nginx condition met"
    )

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
    from vibectl.types import Success

    # Set up mock kubectl output
    mock_run_kubectl_for_cli.return_value = Success(data="pod/nginx condition met")

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
    from vibectl.types import Success

    # Configure output flags
    mock_configure_flags.return_value = OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=True,
        model_name="claude-3.7-haiku",
    )

    # Set up mock kubectl output
    mock_run_kubectl_for_cli.return_value = Success(data="pod/nginx condition met")

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

    # Check results - CLI should exit with non-zero status for errors
    assert result.exit_code == 1
    # Make sure the error is being processed
    assert "timed out waiting for the condition" in result.output


@patch("vibectl.subcommands.wait_cmd.handle_vibe_request")
def test_wait_vibe_request(
    mock_handle_vibe: MagicMock,
    cli_runner: CliRunner,
    mock_configure_output_flags: MagicMock,
    mock_configure_memory_flags: MagicMock,
) -> None:
    """Test wait command with vibe request."""
    mock_handle_vibe.return_value = Success(message="Planned and executed")
    result = cli_runner.invoke(
        cli, ["wait", "vibe", "wait until the deployment myapp is ready"]
    )
    assert result.exit_code == 0
    mock_handle_vibe.assert_called_once()
    # Check specific arguments passed to handle_vibe_request
    call_args = mock_handle_vibe.call_args[1]
    assert call_args["request"] == "wait until the deployment myapp is ready"
    assert call_args["command"] == "wait"
    # Add more assertions if needed for other args like output_flags


@patch("vibectl.subcommands.wait_cmd.handle_vibe_request")
def test_wait_vibe_request_error(
    mock_handle_vibe: MagicMock,
    cli_runner: CliRunner,
    mock_configure_output_flags: MagicMock,
    mock_configure_memory_flags: MagicMock,
) -> None:
    """Test wait command vibe request error handling."""
    # Simulate an error returned by handle_vibe_request
    mock_handle_vibe.return_value = Error(error="LLM planning failed")
    result = cli_runner.invoke(cli, ["wait", "vibe", "some complex wait request"])
    # Expect a non-zero exit code because the command failed
    assert result.exit_code != 0
    # Check that the error message is in the output
    assert "LLM planning failed" in result.output
    mock_handle_vibe.assert_called_once()
    # Check specific arguments passed to handle_vibe_request
    call_args = mock_handle_vibe.call_args[1]
    assert call_args["request"] == "some complex wait request"
    assert call_args["command"] == "wait"


def test_wait_vibe_no_request(
    cli_runner: CliRunner,
    mock_configure_output_flags: MagicMock,
    mock_configure_memory_flags: MagicMock,
    mock_asyncio_for_wait: MagicMock,
) -> None:
    """Test that the wait command properly handles missing vibe request."""
    result = cli_runner.invoke(cli, ["wait", "vibe"], input="\\n")
    assert result.exit_code != 0  # Should fail if no request is provided
    assert "Missing request after 'vibe' command" in result.output


def test_wait_with_live_display_asyncio(
    cli_runner: CliRunner,
    mock_run_kubectl_for_cli: MagicMock,
    mock_handle_output_for_cli: MagicMock,
    mock_asyncio_for_wait: MagicMock,
    mock_memory: Mock,
) -> None:
    """Test wait command with live display using asyncio."""
    from unittest.mock import patch

    from vibectl.types import Success

    result_value = Success(data="pod/nginx condition met")
    mock_run_kubectl_for_cli.return_value = result_value

    with patch.object(
        wait_cmd_module, "handle_wait_with_live_display", return_value=Success()
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

    from vibectl.types import Error

    error_response = Error(error="timed out waiting for the condition")
    mock_run_kubectl_for_cli.return_value = error_response

    with patch.object(
        wait_cmd_module, "handle_wait_with_live_display", return_value=error_response
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


@patch("vibectl.subcommands.wait_cmd.handle_standard_command")
def test_wait_standard_command(
    mock_handle_standard: MagicMock,
    cli_runner: CliRunner,
    mock_configure_output_flags: MagicMock,
    mock_configure_memory_flags: MagicMock,
) -> None:
    """Test wait command execution path without live display."""
    mock_handle_standard.return_value = Success(message="Wait completed standard")
    result = cli_runner.invoke(
        cli,
        [
            "wait",
            "deployment/app",
            "--for=jsonpath='{.status}'=Running",
            "--no-live-display",
        ],
    )
    assert result.exit_code == 0
    mock_handle_standard.assert_called_once()
    call_args = mock_handle_standard.call_args[1]
    assert call_args["command"] == "wait"
    assert call_args["resource"] == "deployment/app"
    assert call_args["args"] == ("--for=jsonpath='{.status}'=Running",)


@patch("vibectl.subcommands.wait_cmd.handle_standard_command")
def test_wait_standard_command_error(
    mock_handle_standard: MagicMock,
    cli_runner: MagicMock,
    mock_configure_output_flags: MagicMock,
    mock_configure_memory_flags: MagicMock,
) -> None:
    """Test error handling in the standard wait command path."""
    # Simulate an error returned by handle_standard_command
    mock_handle_standard.return_value = Error(error="Standard command failed")
    result = cli_runner.invoke(
        cli, ["wait", "job/myjob", "--for=condition=Complete", "--no-live-display"]
    )
    # Expect a non-zero exit code because the command failed
    assert result.exit_code != 0
    # Check that the error message is in the output (might be wrapped by handler)
    # We just check that the mock was called correctly.
    mock_handle_standard.assert_called_once()
    call_args = mock_handle_standard.call_args[1]
    assert call_args["command"] == "wait"
    assert call_args["resource"] == "job/myjob"
    assert call_args["args"] == (
        "--for=condition=Complete",
        # "--no-live-display", # Flag not passed down
    )
