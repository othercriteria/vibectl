"""Tests for standard command handling functionality."""

import asyncio
from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from vibectl.command_handler import (
    handle_standard_command,
)
from vibectl.config import Config
from vibectl.types import (
    Error,
    Fragment,
    MetricsDisplayMode,
    OutputFlags,
    PromptFragments,
    Success,
    SystemFragments,
    UserFragments,
)

# The test_config and mock_subprocess fixtures are now provided by conftest.py


@pytest.fixture
def mock_summary_prompt() -> Callable[[Config | None, str | None], PromptFragments]:
    """Mock summary prompt function that adheres to SummaryPromptFragmentFunc type."""

    def _mock_summary_prompt_func(
        config: Config | None = None, current_memory: str | None = None
    ) -> PromptFragments:
        return PromptFragments(
            (SystemFragments([]), UserFragments([Fragment("Test Prompt: {output}")]))
        )

    return _mock_summary_prompt_func


@patch("vibectl.command_handler.run_kubectl")
@patch("vibectl.k8s_utils.subprocess.run")
@patch("vibectl.command_handler.handle_command_output")
@patch("vibectl.command_handler.console_manager")
def test_handle_standard_command_logs(
    mock_console: Mock,
    mock_handle_output: AsyncMock,
    mock_subprocess_run: Mock,
    mock_run_kubectl: Mock,
) -> None:
    """Test handle_standard_command specifically for the logs command."""
    # Setup mocks: run_kubectl returns Success
    log_output = "Log line 1\nLog line 2"
    mock_run_kubectl.return_value = Success(data=log_output)
    mock_handle_output.return_value = Success(
        message="Processed logs by mock_handle_output"
    )

    output_flags = OutputFlags(
        show_raw_output=True,
        show_vibe=False,
        warn_no_output=False,
        model_name="test-model",
        show_kubectl=True,
        show_metrics=MetricsDisplayMode.ALL,
    )

    # Test handling the logs command
    # Define summary function properly
    def summary_func(
        config: Config | None = None, current_memory: str | None = None
    ) -> PromptFragments:
        return PromptFragments(
            (SystemFragments([]), UserFragments([Fragment("Summarize logs: {output}")]))
        )

    result = asyncio.run(
        handle_standard_command(
            "logs", "pod/my-pod", ("-c", "my-container"), output_flags, summary_func
        )
    )

    # Verify run_kubectl was called with correct args (no capture kwarg)
    mock_run_kubectl.assert_called_once_with(
        ["logs", "pod/my-pod", "-c", "my-container"], allowed_exit_codes=(0,)
    )

    # Verify handle_command_output was called correctly
    mock_handle_output.assert_called_once()
    pos_args, kw_args = mock_handle_output.call_args

    # handle_command_output receives the string data from the Success
    # object returned by run_kubectl --- THIS COMMENT IS NOW OUTDATED.
    # It now receives the full Success object.
    assert isinstance(pos_args[0], Success)
    assert pos_args[0].data == log_output
    assert pos_args[1] == output_flags
    assert pos_args[2] == summary_func
    assert kw_args["command"] == "logs"

    assert result == mock_handle_output.return_value
    mock_subprocess_run.assert_not_called()  # Confirm the unused mock wasn't called


@patch("vibectl.command_handler.run_kubectl")
@patch("vibectl.command_handler.handle_command_output")
@patch("vibectl.command_handler.console_manager")
def test_handle_standard_command_error_with_exception(
    mock_console_mgr: Mock,
    mock_handle_output: AsyncMock,
    mock_run_kubectl: MagicMock,
    default_output_flags: OutputFlags,
    mock_summary_prompt: Callable[[Config | None, str | None], PromptFragments],
) -> None:
    """Test handle_standard_command when run_kubectl returns Error with exception."""
    test_exception = ValueError("Test kubectl error")
    kubectl_error_result = Error(
        error="kubectl command failed internally", exception=test_exception
    )
    mock_run_kubectl.return_value = kubectl_error_result

    # Mock handle_command_output to return an Error with recovery suggestions
    # This simulates the recovery suggestion flow when show_vibe=True
    mock_handle_output.return_value = Error(
        error="kubectl command failed internally",
        exception=test_exception,
        recovery_suggestions="Try checking the command syntax",
    )

    result = asyncio.run(
        handle_standard_command(
            command="get",
            resource="pods",
            args=("mypod",),
            output_flags=default_output_flags,
            summary_prompt_func=mock_summary_prompt,
        )
    )

    mock_run_kubectl.assert_called_once_with(
        ["get", "pods", "mypod"], allowed_exit_codes=(0,)
    )
    # Now expect handle_command_output to be called since show_vibe=True by default
    # and errors go through recovery suggestion flow
    mock_handle_output.assert_called_once()

    assert isinstance(result, Error)
    assert result.error == "kubectl command failed internally"
    assert result.exception == test_exception
    # No longer expect print_error call here since handle_command_output handles display
    # mock_console_mgr.print_error.assert_called_once_with(kubectl_error_result.error)


@patch("vibectl.command_handler.run_kubectl")
@patch("vibectl.command_handler.handle_command_output")
@patch("vibectl.command_handler.console_manager")
def test_handle_standard_command_empty_output(
    mock_console_mgr: Mock,
    mock_handle_output: AsyncMock,
    mock_run_kubectl: MagicMock,
    default_output_flags: OutputFlags,
    mock_summary_prompt: Callable[[Config | None, str | None], PromptFragments],
) -> None:
    """Test handle_standard_command if run_kubectl returns Success with empty output."""
    mock_run_kubectl.return_value = Success(
        data="", message="kubectl success no output"
    )
    # Set a specific return value for mock_handle_output to assert against
    expected_handle_output_result = Success(message="Processed by mock_handle_output")
    mock_handle_output.return_value = expected_handle_output_result

    result = asyncio.run(
        handle_standard_command(
            command="get",
            resource="pods",
            args=(),
            output_flags=default_output_flags,
            summary_prompt_func=mock_summary_prompt,
        )
    )

    mock_run_kubectl.assert_called_once_with(["get", "pods"], allowed_exit_codes=(0,))
    # handle_command_output should now be called
    mock_handle_output.assert_called_once_with(
        mock_run_kubectl.return_value,  # It's called with the Success object
        default_output_flags,
        mock_summary_prompt,
        command="get",
    )

    assert result == expected_handle_output_result
    # This console print is from _handle_empty_output,
    # which is no longer directly called in this path
    mock_console_mgr.print_processing.assert_not_called()
