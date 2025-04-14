"""Tests for the CLI wait command.

This module tests the CLI wait command of vibectl. All tests in this module
should use appropriate mocking to prevent real calls to kubectl and LLM services.
"""

from collections.abc import Generator
from unittest.mock import MagicMock, Mock, patch

import pytest
from click.testing import CliRunner

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


def test_wait_basic(
    cli_runner: CliRunner,
    mock_run_kubectl_for_cli: MagicMock,
    mock_handle_output_for_cli: MagicMock,
    mock_memory: Mock,
) -> None:
    """Test basic wait command functionality."""
    # Set up mock kubectl output for a successful wait
    mock_run_kubectl_for_cli.return_value = "pod/nginx condition met"

    # Invoke CLI with wait command
    result = cli_runner.invoke(cli, ["wait", "pod/nginx", "--for=condition=Ready"])

    # Check results
    assert result.exit_code == 0
    mock_run_kubectl_for_cli.assert_called_once_with(
        ["wait", "pod/nginx", "--for=condition=Ready"], capture=True
    )
    mock_handle_output_for_cli.assert_called_once()


def test_wait_with_args(
    cli_runner: CliRunner,
    mock_run_kubectl_for_cli: MagicMock,
    mock_handle_output_for_cli: MagicMock,
    mock_memory: Mock,
) -> None:
    """Test wait command with additional arguments."""
    # Set up mock kubectl output
    mock_run_kubectl_for_cli.return_value = "pod/nginx condition met"

    # Invoke CLI with wait command and additional args
    result = cli_runner.invoke(
        cli,
        [
            "wait",
            "pod/nginx",
            "--for=condition=Ready",
            "--timeout=30s",
            "-n",
            "default",
        ],
    )

    # Check results
    assert result.exit_code == 0
    mock_run_kubectl_for_cli.assert_called_once_with(
        [
            "wait",
            "pod/nginx",
            "--for=condition=Ready",
            "--timeout=30s",
            "-n",
            "default",
        ],
        capture=True,
    )
    mock_handle_output_for_cli.assert_called_once()


@patch("vibectl.cli.configure_output_flags")
def test_wait_with_flags(
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
    mock_run_kubectl_for_cli: MagicMock,
    mock_handle_output_for_cli: MagicMock,
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

    # Invoke CLI with vibectl-specific flags
    result = cli_runner.invoke(
        cli,
        [
            "wait",
            "pod/nginx",
            "--for=condition=Ready",
            "--show-raw-output",
            "--model",
            "claude-3.7-haiku",
        ],
    )

    # Check results
    assert result.exit_code == 0
    mock_run_kubectl_for_cli.assert_called_once_with(
        ["wait", "pod/nginx", "--for=condition=Ready"], capture=True
    )
    # Check that we used the configured output flags
    mock_configure_flags.assert_called_once()
    mock_handle_output_for_cli.assert_called_once()


def test_wait_error_handling(
    cli_runner: CliRunner,
    mock_run_kubectl_for_cli: MagicMock,
    mock_handle_output_for_cli: MagicMock,
    mock_memory: Mock,
) -> None:
    """Test wait command error handling."""
    # Set up mock kubectl output for a timeout or error
    mock_run_kubectl_for_cli.set_error_response("timed out waiting for the condition")

    # Invoke CLI with wait command
    result = cli_runner.invoke(
        cli, ["wait", "pod/nginx", "--for=condition=Ready", "--timeout=1s"]
    )

    # Check results
    assert result.exit_code == 0  # CLI should handle the error gracefully
    mock_run_kubectl_for_cli.assert_called_once_with(
        ["wait", "pod/nginx", "--for=condition=Ready", "--timeout=1s"], capture=True
    )
    # Ensure handle_output was called with the error message
    mock_handle_output_for_cli.assert_called_once()


@patch("vibectl.cli.handle_vibe_request")
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


def test_wait_vibe_no_request(
    cli_runner: CliRunner, mock_console: Mock, mock_memory: Mock
) -> None:
    """Test wait command with vibe but no request."""
    # Invoke CLI with vibe but no request
    result = cli_runner.invoke(cli, ["wait", "vibe"])

    # Check results
    assert result.exit_code == 1  # Missing request should exit with error
    mock_console.print_error.assert_called_once_with("Missing request after 'vibe'")
