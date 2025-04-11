"""Tests for standard command handling functionality."""

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock, Mock, call, patch

import pytest

from vibectl.command_handler import (
    OutputFlags,
    handle_standard_command,
)

# The test_config and mock_subprocess fixtures are now provided by conftest.py


def test_handle_standard_command_basic(
    mock_subprocess: MagicMock,
    mock_llm: MagicMock,
    mock_console: Mock,
    prevent_exit: MagicMock,
    test_config: Any,
    standard_output_flags: OutputFlags,
) -> None:
    """Test basic command handling."""
    # Set test kubeconfig
    test_config.set("kubeconfig", "/test/kubeconfig")

    # Configure mock to return success
    mock_subprocess.return_value.stdout = "test output"

    # Set up model adapter response for summary
    mock_llm.execute.return_value = "Summarized output"

    # Run command
    handle_standard_command(
        command="get",
        resource="pods",
        args=(),
        output_flags=standard_output_flags,
        summary_prompt_func=lambda: "Test prompt: {output}",
    )

    # Verify command construction - use any_call instead of assert_called_once
    # because subprocess might be called multiple times by other code
    assert mock_subprocess.call_args_list[0] == call(
        ["kubectl", "--kubeconfig", "/test/kubeconfig", "get", "pods"],
        capture_output=True,
        text=True,
        check=True,
    )

    # Verify model adapter was called
    mock_llm.execute.assert_called_once()

    # Verify sys.exit was not called
    prevent_exit.assert_not_called()


@pytest.fixture
def mock_summary_prompt() -> Callable[[], str]:
    """Mock summary prompt function."""
    return lambda: "Test Prompt: {output}"


def test_handle_standard_command(
    mock_subprocess: MagicMock,
    mock_llm: MagicMock,
    mock_console: Mock,
    prevent_exit: MagicMock,
    mock_summary_prompt: Callable[[], str],
    test_config: Any,
    standard_output_flags: OutputFlags,
) -> None:
    """Test standard command handling."""
    # Ensure no kubeconfig is set
    test_config.set("kubeconfig", None)

    # Set up model adapter response for summary
    mock_llm.execute.return_value = "Summarized output"

    # Run command
    handle_standard_command(
        command="get",
        resource="pods",
        args=(),
        output_flags=standard_output_flags,
        summary_prompt_func=mock_summary_prompt,
    )

    # Verify kubectl was called
    mock_subprocess.assert_called_once()
    cmd = mock_subprocess.call_args[0][0]
    assert cmd == ["kubectl", "get", "pods"]

    # Verify model adapter was called
    mock_llm.execute.assert_called_once()

    # Verify sys.exit was not called
    prevent_exit.assert_not_called()


@patch("vibectl.command_handler.handle_exception")
def test_handle_standard_command_error(
    mock_handle_exception: MagicMock,
    mock_subprocess: MagicMock,
    mock_llm: MagicMock,
    mock_console: Mock,
    prevent_exit: MagicMock,
    mock_summary_prompt: Callable[[], str],
    standard_output_flags: OutputFlags,
) -> None:
    """Test error handling in standard command."""
    # Set up error
    mock_subprocess.side_effect = Exception("test error")

    # Run command
    handle_standard_command(
        command="get",
        resource="pods",
        args=(),
        output_flags=standard_output_flags,
        summary_prompt_func=mock_summary_prompt,
    )

    # Verify kubectl was called and exception was handled
    mock_subprocess.assert_called_once()
    mock_handle_exception.assert_called_once()

    # Verify model adapter was NOT called since command failed
    mock_llm.execute.assert_not_called()

    # Verify sys.exit was not called
    prevent_exit.assert_not_called()


@patch("vibectl.command_handler.handle_exception")
def test_handle_standard_command_no_output(
    mock_handle_exception: MagicMock,
    mock_subprocess: MagicMock,
    mock_llm: MagicMock,
    mock_console: Mock,
    prevent_exit: MagicMock,
    mock_summary_prompt: Callable[[], str],
    standard_output_flags: OutputFlags,
) -> None:
    """Test standard command handling with no output."""
    # Set up mock to return no output
    mock_subprocess.return_value = Mock(stdout="", stderr="")

    # Set up model adapter response for summary
    mock_llm.execute.return_value = "No resources found"

    # Run command
    handle_standard_command(
        command="get",
        resource="pods",
        args=(),
        output_flags=standard_output_flags,
        summary_prompt_func=mock_summary_prompt,
    )

    # Verify no exception was handled
    mock_handle_exception.assert_not_called()

    # Verify model adapter was not called since there was no output
    mock_llm.execute.assert_not_called()

    # Verify sys.exit was not called
    prevent_exit.assert_not_called()


@patch("vibectl.command_handler.handle_exception")
def test_handle_standard_command_output_error(
    mock_handle_exception: MagicMock,
    mock_subprocess: MagicMock,
    mock_llm: MagicMock,
    mock_console: Mock,
    prevent_exit: MagicMock,
    mock_summary_prompt: Callable[[], str],
    standard_output_flags: OutputFlags,
) -> None:
    """Test error handling in standard command output processing."""
    # Set up successful command but failed output handling
    mock_subprocess.return_value = Mock(stdout="test output", stderr="")

    with patch("vibectl.command_handler.handle_command_output") as mock_handle_output:
        mock_handle_output.side_effect = Exception("Output handling failed")

        # Run command
        handle_standard_command(
            command="get",
            resource="pods",
            args=(),
            output_flags=standard_output_flags,
            summary_prompt_func=mock_summary_prompt,
        )

        # Verify exception was handled
        mock_handle_exception.assert_called_once_with(mock_handle_output.side_effect)

        # Verify sys.exit was not called
        prevent_exit.assert_not_called()
