"""Tests for the CLI port-forward command.

This module tests the CLI port-forward command of vibectl. All tests in this module
should use appropriate mocking to prevent real calls to kubectl and LLM services.
"""

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest
from click.testing import CliRunner

from vibectl.cli import cli
from vibectl.command_handler import OutputFlags


@pytest.fixture
def mock_asyncio_for_port_forward() -> Generator[MagicMock, None, None]:
    """Mock asyncio functionality for port-forward command tests to avoid
    coroutine warnings."""
    # Create a mock process
    mock_process = MagicMock()
    mock_process.returncode = None
    mock_process.stdout = MagicMock()
    mock_process.stdout.readline.return_value = (
        b"Forwarding from 127.0.0.1:8080 -> 8080"
    )
    mock_process.stderr = MagicMock()
    mock_process.stderr.read.return_value = b""
    mock_process.wait.return_value = None
    mock_process.terminate.return_value = None

    # Create a mock event loop
    mock_loop = MagicMock()
    mock_loop.is_running.return_value = False

    # Create synchronous (non-async) mocks to avoid coroutine warnings
    def mock_sleep(delay: float, *args: Any, **kwargs: Any) -> None:
        """Mock sleep as a regular function to avoid coroutine warnings."""
        return None

    def mock_wait_for(coro: Any, timeout: float, *args: Any, **kwargs: Any) -> Any:
        """Mock wait_for as a regular function to avoid coroutine warnings."""
        return coro

    def mock_create_subprocess_exec(*args: Any, **kwargs: Any) -> Any:
        """Mock create_subprocess_exec as a regular function."""
        return mock_process

    def mock_create_task(coro: Any, *args: Any, **kwargs: Any) -> Any:
        """Mock create_task to return a MagicMock instead of a Task object."""
        return coro

    # Use a patch context manager to replace all asyncio functions we use
    with (
        # Mock asyncio functions
        patch("vibectl.command_handler.asyncio.get_event_loop", return_value=mock_loop),
        patch("vibectl.command_handler.asyncio.new_event_loop", return_value=mock_loop),
        patch("vibectl.command_handler.asyncio.set_event_loop"),
        # Replace all async functions with synchronous versions
        patch("vibectl.command_handler.asyncio.sleep", mock_sleep),
        patch("vibectl.command_handler.asyncio.wait_for", mock_wait_for),
        patch(
            "vibectl.command_handler.asyncio.create_subprocess_exec",
            mock_create_subprocess_exec,
        ),
        patch("vibectl.command_handler.asyncio.create_task", mock_create_task),
        # Replace asyncio exceptions with regular Exception to avoid awaiting issues
        patch("vibectl.command_handler.asyncio.CancelledError", Exception),
        patch("vibectl.command_handler.asyncio.TimeoutError", Exception),
        # Also mock any direct asyncio imports in the test module
        patch("asyncio.create_task", mock_create_task),
        patch("asyncio.Future", MagicMock),
    ):
        yield mock_process


def test_port_forward_basic(
    cli_runner: CliRunner,
    mock_run_kubectl_for_cli: MagicMock,
    mock_handle_output_for_cli: MagicMock,
    mock_asyncio_for_port_forward: MagicMock,
    mock_memory: Mock,
) -> None:
    """Test port-forward command with basic arguments."""
    # Set up mock kubectl output
    mock_run_kubectl_for_cli.return_value = "Forwarding from 127.0.0.1:8080 -> 8080"

    with (
        patch("vibectl.command_handler.run_kubectl", mock_run_kubectl_for_cli),
        patch(
            "vibectl.command_handler.handle_command_output", mock_handle_output_for_cli
        ),
    ):
        # Invoke CLI with --no-live-display to use the standard command handler
        result = cli_runner.invoke(
            cli,
            ["port-forward", "pod/nginx", "8080:8080", "--no-live-display"],
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
    # Command output handler should be called
    mock_handle_output_for_cli.assert_called_once()


def test_port_forward_with_args(
    cli_runner: CliRunner,
    mock_run_kubectl_for_cli: MagicMock,
    mock_handle_output_for_cli: MagicMock,
    mock_asyncio_for_port_forward: MagicMock,
    mock_memory: Mock,
) -> None:
    """Test port-forward command with additional arguments."""
    # Set up mock kubectl output
    mock_run_kubectl_for_cli.return_value = "Forwarding from 127.0.0.1:5000 -> 80"

    with (
        patch("vibectl.command_handler.run_kubectl", mock_run_kubectl_for_cli),
        patch(
            "vibectl.command_handler.handle_command_output", mock_handle_output_for_cli
        ),
    ):
        # Invoke CLI with port-forward command and additional args, and no live display
        result = cli_runner.invoke(
            cli,
            [
                "port-forward",
                "service/web",
                "5000:80",
                "--address",
                "0.0.0.0",
                "-n",
                "default",
                "--no-live-display",
            ],
        )

    # Check results
    assert result.exit_code == 0
    # Command output handler should be called
    mock_handle_output_for_cli.assert_called_once()


@patch("vibectl.subcommands.port_forward_cmd.configure_output_flags")
def test_port_forward_with_flags(
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
    mock_run_kubectl_for_cli: MagicMock,
    mock_handle_output_for_cli: MagicMock,
    mock_asyncio_for_port_forward: MagicMock,
    mock_memory: Mock,
) -> None:
    """Test port-forward command with vibectl-specific flags."""
    # Configure output flags
    mock_configure_flags.return_value = OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=True,
        model_name="claude-3.7-haiku",
    )

    # Set up mock kubectl output
    mock_run_kubectl_for_cli.return_value = "Forwarding from 127.0.0.1:8080 -> 8080"

    with (
        patch("vibectl.command_handler.run_kubectl", mock_run_kubectl_for_cli),
        patch(
            "vibectl.command_handler.handle_command_output", mock_handle_output_for_cli
        ),
    ):
        # Invoke CLI with vibectl-specific flags and no live display
        result = cli_runner.invoke(
            cli,
            [
                "port-forward",
                "pod/nginx",
                "8080:8080",
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


def test_port_forward_error_handling(
    cli_runner: CliRunner,
    mock_run_kubectl_for_cli: MagicMock,
    mock_handle_output_for_cli: MagicMock,
    mock_asyncio_for_port_forward: MagicMock,
    mock_memory: Mock,
) -> None:
    """Test port-forward command error handling."""
    # Set up mock kubectl output for an error
    mock_run_kubectl_for_cli.return_value = "Error: unable to forward port"

    with (
        patch("vibectl.command_handler.run_kubectl", mock_run_kubectl_for_cli),
        patch(
            "vibectl.command_handler.handle_command_output", mock_handle_output_for_cli
        ),
    ):
        # Invoke CLI with port-forward command and no live display
        result = cli_runner.invoke(
            cli,
            [
                "port-forward",
                "pod/nonexistent",
                "8080:8080",
                "--no-live-display",
            ],
        )

    # Check results
    assert result.exit_code == 0  # CLI should handle the error gracefully
    # Make sure the output was processed
    mock_handle_output_for_cli.assert_called_once()


@patch("vibectl.subcommands.port_forward_cmd.handle_vibe_request")
def test_port_forward_vibe_request(
    mock_handle_vibe: MagicMock, cli_runner: CliRunner, mock_memory: Mock
) -> None:
    """Test port-forward command with vibe request."""
    # Invoke CLI with vibe request
    result = cli_runner.invoke(
        cli, ["port-forward", "vibe", "forward port 8080 of nginx pod to my local 8080"]
    )

    # Check results
    assert result.exit_code == 0
    mock_handle_vibe.assert_called_once()
    assert (
        mock_handle_vibe.call_args[1]["request"]
        == "forward port 8080 of nginx pod to my local 8080"
    )
    assert mock_handle_vibe.call_args[1]["command"] == "port-forward"
    # Check that live_display is True by default
    assert mock_handle_vibe.call_args[1]["live_display"] is True


@patch("vibectl.subcommands.port_forward_cmd.handle_vibe_request")
def test_port_forward_vibe_with_live_display_flag(
    mock_handle_vibe: MagicMock, cli_runner: CliRunner, mock_memory: Mock
) -> None:
    """Test port-forward vibe command with explicit live display flag."""
    # Test with --live-display flag
    result = cli_runner.invoke(
        cli,
        ["port-forward", "vibe", "forward port 8080 of nginx pod", "--live-display"],
    )
    assert result.exit_code == 0
    mock_handle_vibe.assert_called_once()
    assert mock_handle_vibe.call_args[1]["live_display"] is True
    mock_handle_vibe.reset_mock()

    # Test with --no-live-display flag
    result = cli_runner.invoke(
        cli,
        ["port-forward", "vibe", "forward port 8080 of nginx pod", "--no-live-display"],
    )
    assert result.exit_code == 0
    mock_handle_vibe.assert_called_once()
    assert mock_handle_vibe.call_args[1]["live_display"] is False


def test_port_forward_vibe_no_request(cli_runner: CliRunner, mock_memory: Mock) -> None:
    """Test port-forward vibe command with no request."""
    with patch("vibectl.subcommands.port_forward_cmd.console_manager") as mock_console:
        # Invoke CLI with vibe but no request
        result = cli_runner.invoke(cli, ["port-forward", "vibe"])

        # Check results - should exit with error
        assert result.exit_code == 1
        mock_console.print_error.assert_called_once_with("Missing request after 'vibe'")
