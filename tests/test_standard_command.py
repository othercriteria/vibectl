"""Tests for standard command handling functionality."""

from collections.abc import Callable
from unittest.mock import MagicMock, Mock, patch

import pytest

from vibectl.command_handler import (
    handle_standard_command,
)
from vibectl.types import Error, OutputFlags, Success

# The test_config and mock_subprocess fixtures are now provided by conftest.py


@pytest.fixture
def mock_summary_prompt() -> Callable[[], str]:
    """Mock summary prompt function."""
    return lambda: "Test Prompt: {output}"


@patch("vibectl.command_handler.run_kubectl")
@patch("vibectl.k8s_utils.subprocess.run")
@patch("vibectl.command_handler.handle_command_output")
@patch("vibectl.command_handler.console_manager")
def test_handle_standard_command_logs(
    mock_console: Mock,
    mock_handle_output: Mock,
    mock_subprocess_run: Mock,
    mock_run_kubectl: Mock,
) -> None:
    """Test handle_standard_command specifically for the logs command."""
    # Setup mocks: run_kubectl returns Success
    log_output = "Log line 1\nLog line 2"
    mock_run_kubectl.return_value = Success(data=log_output)
    mock_handle_output.return_value = Success(message=log_output)

    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=False,
        warn_no_output=False,
        model_name="test-model",
        show_kubectl=True,
        show_metrics=True,
    )

    # Test handling the logs command
    # Define summary function properly
    def summary_func() -> str:
        return "Summarize logs: {output}"

    result = handle_standard_command(
        "logs", "pod/my-pod", ("-c", "my-container"), output_flags, summary_func
    )

    # Verify run_kubectl was called with correct args
    mock_run_kubectl.assert_called_once_with(
        ["logs", "pod/my-pod", "-c", "my-container"], capture=True
    )

    # Verify handle_command_output was called correctly
    mock_handle_output.assert_called_once()
    # call_args = (positional_args_tuple, keyword_args_dict)
    pos_args, kw_args = mock_handle_output.call_args

    # Verify positional arguments
    assert isinstance(pos_args[0], str)
    assert pos_args[0] == log_output
    assert pos_args[1] == output_flags  # Check 2nd positional arg
    assert pos_args[2] == summary_func  # Check 3rd positional arg

    # Verify keyword arguments
    assert kw_args["command"] == "logs"

    # Verify the result is what handle_command_output returned
    assert result == mock_handle_output.return_value

    # Verify subprocess.run was not called directly
    mock_subprocess_run.assert_not_called()


@patch("vibectl.command_handler.run_kubectl")
@patch("vibectl.command_handler.handle_command_output")
def test_handle_standard_command_error_with_exception(
    mock_handle_output: MagicMock,
    mock_run_kubectl: MagicMock,
    default_output_flags: OutputFlags,
    mock_memory: tuple[MagicMock, MagicMock],
    mock_console: Mock,
    mock_summary_prompt: Callable[[], str],
) -> None:
    """Test handle_standard_command when run_kubectl returns Error with exception."""
    test_exception = ValueError("Test kubectl error")
    mock_run_kubectl.return_value = Error(
        error="kubectl command failed", exception=test_exception
    )

    # Run command
    result = handle_standard_command(
        command="get",
        resource="pods",
        args=("mypod",),
        output_flags=default_output_flags,  # Flags don't matter much here
        summary_prompt_func=mock_summary_prompt,
    )

    # Verify run_kubectl was called
    mock_run_kubectl.assert_called_once_with(["get", "pods", "mypod"], capture=True)

    # Verify handle_command_output was NOT called
    mock_handle_output.assert_not_called()

    # Verify the returned result is an Error object containing the original exception
    assert isinstance(result, Error)
    assert result.error == "Unexpected error: Test kubectl error"
    assert result.exception == test_exception  # original exception is preserved
    # Verify error was printed (via _handle_standard_command_error -> logger -> console)


@patch("vibectl.command_handler.run_kubectl")
@patch("vibectl.command_handler.handle_command_output")
def test_handle_standard_command_empty_output(
    mock_handle_output: MagicMock,
    mock_run_kubectl: MagicMock,
    mock_console: Mock,
    default_output_flags: OutputFlags,
    mock_summary_prompt: Callable[[], str],
) -> None:
    """Test handle_standard_command if run_kubectl returns Success with empty output."""
    mock_run_kubectl.return_value = Success(data="", message="")

    # Run command
    result = handle_standard_command(
        command="get",
        resource="pods",
        args=(),
        output_flags=default_output_flags,
        summary_prompt_func=mock_summary_prompt,
    )

    # Verify run_kubectl was called with args list *without* kubectl prepended
    # as run_kubectl itself handles prepending.
    mock_run_kubectl.assert_called_once_with(["get", "pods"], capture=True)

    # Verify handle_command_output was NOT called
    mock_handle_output.assert_not_called()

    # Verify the returned result is a Success object indicating no output
    assert isinstance(result, Success)
    assert result.message == "Command returned no output"
    assert result.continue_execution is True  # Check if execution should continue
