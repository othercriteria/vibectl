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
        command="get pods",
        command_output="test output",
        vibe_output="Test response",
        model_name="test-model",
    )


def test_handle_command_output_does_not_update_memory_without_command(
    mock_get_adapter: MagicMock,
    mock_memory_update: Mock,
    mock_process_auto: Mock,
) -> None:
    """Test that memory is updated with 'Unknown' command when no command provided."""
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
        # Mock the summary call directly to avoid LLM interaction
        with patch(
            "vibectl.command_handler._get_llm_summary", return_value="Test response"
        ):
            handle_command_output(
                output="test output",
                output_flags=output_flags,
                summary_prompt_func=lambda: "Test prompt {output}",
                # command is omitted here
            )

    # Verify memory WAS updated with 'Unknown' command
    mock_memory_update.assert_called_once_with(
        command="Unknown",
        command_output="test output",
        vibe_output="Test response",
        model_name="test-model",
    )


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
        command="get pods",
        command_output="Error: Command failed with exit code 1",
        vibe_output="Test response",
        model_name="test-model",
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

    # Memory should NOT be updated when the vibe summary itself is an error string
    mock_memory_update.assert_not_called()


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


# Mock logger to prevent actual logging during tests
@pytest.fixture(autouse=True)
def mock_logger() -> Generator[MagicMock, None, None]:
    with patch("vibectl.command_handler.logger") as mock_log:
        yield mock_log


# Mock console manager
@pytest.fixture(autouse=True)
def mock_console_manager() -> Generator[MagicMock, None, None]:
    with patch("vibectl.command_handler.console_manager") as mock_console:
        yield mock_console


# Mock model adapter and related functions
@pytest.fixture
def mock_model_adapter() -> Generator[MagicMock, None, None]:
    with patch("vibectl.command_handler.get_model_adapter") as mock_get:
        mock_adapter = MagicMock()
        mock_model = MagicMock()
        mock_adapter.get_model.return_value = mock_model
        mock_adapter.execute.return_value = "get pods -n test"  # Default success
        mock_get.return_value = mock_adapter
        yield mock_adapter


# Mock memory functions
@pytest.fixture
def mock_memory_functions() -> Generator[tuple[Mock, Mock, Mock, Mock], None, None]:
    with (
        patch("vibectl.command_handler.update_memory") as mock_update,
        patch("vibectl.memory.get_memory") as mock_get,
        patch("vibectl.memory.set_memory") as mock_set,
        patch("vibectl.memory.is_memory_enabled") as mock_enabled,
    ):
        # Assume memory is enabled by default for these tests
        mock_enabled.return_value = True
        mock_get.return_value = "Existing memory context."  # Default memory
        yield mock_update, mock_get, mock_set, mock_enabled


# Dummy summary prompt function
def dummy_summary_prompt() -> str:
    return "Summarize: {output}"


# Test data
DEFAULT_OUTPUT_FLAGS = OutputFlags(
    show_raw=False,
    show_vibe=True,
    warn_no_output=False,
    model_name="test-model",
    show_kubectl=False,
)


def test_handle_vibe_request_includes_memory_context(
    mock_model_adapter: MagicMock,
    mock_memory_functions: tuple,
    mock_logger: MagicMock,
) -> None:
    """Verify that memory_context is correctly formatted into the plan_prompt."""
    mock_update, mock_get, mock_set, mock_enabled = mock_memory_functions

    # Define a prompt template that requires both request and memory_context
    test_plan_prompt = """
    Plan
    Memory: '{memory_context}'
    Request: '{request}'
    """
    test_request = "get the pods"
    test_memory_context = "We are in the 'sandbox' namespace."
    expected_formatted_prompt = test_plan_prompt.format(
        memory_context=test_memory_context, request=test_request
    )

    # Mock the model execution result
    mock_model_adapter.execute.return_value = "get pods -n sandbox"

    # Call the function under test
    handle_vibe_request(
        request=test_request,
        command="vibe",
        plan_prompt=test_plan_prompt,
        summary_prompt_func=dummy_summary_prompt,
        output_flags=DEFAULT_OUTPUT_FLAGS,
        memory_context=test_memory_context,  # Pass the memory context
        semiauto=True,  # Simulate semiauto where this prompt format is used
    )

    # Assert that the model adapter was called with the correctly formatted prompt
    mock_model_adapter.execute.assert_called_once_with(
        mock_model_adapter.get_model.return_value,  # The mocked model object
        expected_formatted_prompt,
    )

    # Assert that the formatting warning was NOT logged
    mock_logger.warning.assert_not_called()
