"""Tests for command_handler.py's memory handling and edge cases.

This module tests potential memory-related bugs and edge cases in command_handler.py,
focusing on how commands update and interact with memory.
"""

from collections.abc import Generator
from unittest.mock import MagicMock, Mock, patch

import pytest

from vibectl.command_handler import (
    handle_command_output,
    handle_vibe_request,
)
from vibectl.types import Error, OutputFlags, Truncation


@pytest.fixture
def mock_memory_update() -> Generator[Mock, None, None]:
    """Mock the update_memory function to check memory updates."""
    with patch("vibectl.command_handler.update_memory") as mock:
        yield mock


@pytest.fixture
def mock_process_auto() -> Generator[Mock, None, None]:
    """Mock output processor's process_auto method."""
    with patch("vibectl.command_handler.output_processor.process_auto") as mock:
        # Default return no truncation, but as a Truncation object
        mock.return_value = Truncation(
            original="processed content", truncated="processed content"
        )
        yield mock


@pytest.fixture
def mock_get_adapter() -> Generator[MagicMock, None, None]:
    """Mock the model adapter with configurable response."""
    with patch("vibectl.command_handler.get_model_adapter") as mock_adapter:
        # Set up mock model
        mock_model = Mock()
        mock_adapter.return_value.get_model.return_value = mock_model
        mock_adapter.return_value.execute.return_value = "Test response"

        yield mock_adapter


def test_handle_command_output_updates_memory(
    mock_get_adapter: MagicMock,
    mock_memory_update: Mock,
    mock_process_auto: Mock,
) -> None:
    """Test that handle_command_output correctly updates memory."""
    # Configure output flags
    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
    )

    # Call handle_command_output with a command
    with patch("vibectl.command_handler.console_manager"):
        # Configure mock_process_auto for this specific test
        mock_process_auto.return_value = Truncation(
            original="test output", truncated="processed test output"
        )
        # Assume LLM returns "Test response" based on mock_get_adapter fixture
        handle_command_output(
            output="test output",
            output_flags=output_flags,
            summary_prompt_func=lambda: "Test prompt {output}",
            command="get pods",
        )

    # Verify memory was updated with correct parameters
    mock_memory_update.assert_called_once_with(
        "get pods", "test output", "Test response", "test-model"
    )


def test_handle_command_output_does_not_update_memory_without_command(
    mock_get_adapter: MagicMock,
    mock_memory_update: Mock,
    mock_process_auto: Mock,
) -> None:
    """Test that memory is not updated when no command is provided."""
    # Configure output flags
    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
    )

    # Call handle_command_output without a command
    with patch("vibectl.command_handler.console_manager"):
        # Configure mock_process_auto for this specific test
        mock_process_auto.return_value = Truncation(
            original="test output", truncated="processed test output"
        )
        handle_command_output(
            output="test output",
            output_flags=output_flags,
            summary_prompt_func=lambda: "Test prompt {output}",
        )

    # Verify memory was not updated
    mock_memory_update.assert_not_called()


def test_handle_command_output_updates_memory_with_error_output(
    mock_get_adapter: MagicMock,
    mock_memory_update: Mock,
    mock_process_auto: Mock,
) -> None:
    """Test that memory is updated even when output contains error message."""
    # Configure output flags
    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
    )

    # Call handle_command_output with error output
    with patch("vibectl.command_handler.console_manager"):
        # Configure mock_process_auto for this specific test
        mock_process_auto.return_value = Truncation(
            original="Error: Command failed with exit code 1",
            truncated="processed error output",
        )
        # Assume LLM returns "Test response" based on mock_get_adapter fixture
        handle_command_output(
            output="Error: Command failed with exit code 1",
            output_flags=output_flags,
            summary_prompt_func=lambda: "Test prompt {output}",
            command="get pods",
        )

    # Verify memory was updated with error output
    mock_memory_update.assert_called_once_with(
        "get pods",
        "Error: Command failed with exit code 1",
        "Test response",
        "test-model",
    )


def test_handle_command_output_updates_memory_with_overloaded_error(
    mock_get_adapter: MagicMock,
    mock_memory_update: Mock,
    mock_process_auto: Mock,
) -> None:
    """Test memory update when LLM returns overloaded_error (transient failure)."""
    # Simulate the model adapter returning an overloaded_error
    overloaded_error = (
        'ERROR: {"type": "error", "error": {"type": '
        '"overloaded_error", "message": "Overloaded"}}'
    )
    mock_get_adapter.return_value.execute.return_value = overloaded_error

    # Configure output flags
    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
    )

    # Call handle_command_output with a command, simulating an overloaded LLM
    with patch("vibectl.command_handler.console_manager"):
        # Configure mock_process_auto for this specific test
        mock_process_auto.return_value = Truncation(
            original="test output", truncated="processed test output"
        )
        result = handle_command_output(
            output="test output",
            output_flags=output_flags,
            summary_prompt_func=lambda: "Test prompt {output}",
            command="get pods",
        )

    # The function now returns an Error object instead of raising an exception
    assert isinstance(result, Error)
    assert "overloaded_error" in result.error

    # Memory should still be updated with the overloaded error as the vibe_output
    # The vibe_output comes AFTER the LLM call, which returned the error
    mock_memory_update.assert_called_once_with(
        "get pods", "test output", overloaded_error, "test-model"
    )
    # Note: Error is now returned to caller instead of being raised,
    # but memory update should still happen BEFORE the function returns the Error


def test_handle_vibe_request_updates_memory_on_error(
    mock_get_adapter: MagicMock, mock_memory_update: Mock
) -> None:
    """Test that memory is updated even when command execution fails."""
    # Configure model adapter to return a valid command
    mock_get_adapter.return_value.execute.return_value = "get pods"

    # Configure output flags
    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
    )

    # First test: When exception is thrown, it is transformed to Error result
    with (
        patch("vibectl.command_handler._execute_command") as mock_execute,
        patch("vibectl.command_handler.handle_command_output") as mock_handle_output,
        patch("vibectl.command_handler.console_manager"),
        patch("vibectl.command_handler._process_command_string") as mock_process,
        patch("vibectl.command_handler._parse_command_args") as mock_parse,
        patch("vibectl.command_handler._create_display_command") as mock_display,
        patch("vibectl.command_handler.recovery_prompt", "Recovery: {error}"),
    ):
        # Set up mocks
        mock_process.return_value = ("get pods", None)
        mock_parse.return_value = ["get", "pods"]
        mock_display.return_value = "get pods"
        mock_execute.side_effect = Exception("Command execution failed")

        # Call handle_vibe_request
        result = handle_vibe_request(
            request="Show me the pods",
            command="get",
            plan_prompt="Plan how to {command} {request}",
            summary_prompt_func=lambda: "Test prompt {output}",
            output_flags=output_flags,
            yes=True,  # Skip confirmation
        )

        # Verify the result is an Error
        assert isinstance(result, Error)
        # Check that the error contains our exception message
        error_content = str(result.error) if result.error else ""
        exception_content = str(result.exception) if result.exception else ""
        assert (
            "Command execution failed" in error_content
            or "Command execution failed" in exception_content
        )

    # Second test: When Error is returned directly
    mock_handle_output.reset_mock()

    with (
        patch("vibectl.command_handler._execute_command") as mock_execute,
        patch("vibectl.command_handler.handle_command_output") as mock_handle_output,
        patch("vibectl.command_handler.console_manager"),
        patch("vibectl.command_handler._process_command_string") as mock_process,
        patch("vibectl.command_handler._parse_command_args") as mock_parse,
        patch("vibectl.command_handler._create_display_command") as mock_display,
        patch("vibectl.command_handler.recovery_prompt", "Recovery: {error}"),
    ):
        # Set up mocks
        mock_process.return_value = ("get pods", None)
        mock_parse.return_value = ["get", "pods"]
        mock_display.return_value = "get pods"
        # Simulate _execute_command returning an Error object
        mock_execute.return_value = Error(
            error="Execution resulted in Error", exception=None
        )

        # Call handle_vibe_request
        result = handle_vibe_request(
            request="Show me the pods",
            command="get",
            plan_prompt="Plan how to {command} {request}",
            summary_prompt_func=lambda: "Test prompt {output}",
            output_flags=output_flags,
            yes=True,  # Skip confirmation
        )

        # Verify the result is the same Error object
        assert isinstance(result, Error)
        assert "Execution resulted in Error" in result.error

    # Verify handle_command_output was not called in either error scenario
    mock_handle_output.assert_not_called()
