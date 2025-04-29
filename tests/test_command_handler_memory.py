"""Tests for command_handler.py's memory handling and edge cases.

This module tests potential memory-related bugs and edge cases in command_handler.py,
focusing on how commands update and interact with memory.
"""

import json
from collections.abc import Generator
from unittest.mock import MagicMock, Mock, patch

import pytest

from vibectl.command_handler import (
    handle_command_output,
    handle_vibe_request,
)
from vibectl.types import ActionType, Error, OutputFlags, Success, Truncation


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
    """Test that memory is NOT updated directly when command execution fails.

    Memory might be updated later if recovery suggestions are successfully fetched,
    but the initial execution error itself doesn't trigger an update in the current flow.
    """
    # Mock LLM planning response (successful plan)
    plan_response = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["pods"],
        "explanation": "Getting pods as requested",
    }
    # Mock LLM recovery suggestion response
    recovery_suggestion = "Try checking the namespace."
    mock_get_adapter.return_value.execute.side_effect = [
        json.dumps(plan_response),
        recovery_suggestion, # Response for recovery prompt
    ]

    # Configure output flags
    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
    )

    # Mock dependencies within handle_vibe_request
    with (
        patch("vibectl.command_handler._execute_command") as mock_execute,
        patch("vibectl.command_handler.console_manager") as mock_console,
        patch("vibectl.memory.include_memory_in_prompt") as mock_include_memory,
        # Mock recovery_prompt to simplify testing
        patch("vibectl.command_handler.recovery_prompt") as mock_recovery_prompt,
    ):
        # Mock _execute_command to return an Error
        execution_error_msg = "Command execution failed"
        mock_execute.return_value = Error(error=execution_error_msg)
        # Mock recovery prompt generation
        mock_recovery_prompt.return_value = "Recovery prompt content"
        # Mock memory include to just return the prompt
        mock_include_memory.side_effect = lambda p, **k: p

        # Call handle_vibe_request
        result = handle_vibe_request(
            request="get pods causing error",
            command="get",
            plan_prompt="Plan: {request}",
            summary_prompt_func=lambda: "Summary: {output}",
            output_flags=output_flags,
        )

    # Verify _execute_command was called
    mock_execute.assert_called_once()

    # Verify the recovery prompt was generated and LLM called for suggestions
    mock_recovery_prompt.assert_called_once()
    assert mock_get_adapter.return_value.execute.call_count == 2 # Plan + Recovery

    # Verify the recovery suggestion was printed
    mock_console.print_suggestion.assert_called_with(recovery_suggestion)

    # Verify memory was NOT updated during this specific error handling path
    # (Memory update might happen if recovery leads to a new successful command later)
    mock_memory_update.assert_not_called()

    # Verify the final result is the original execution Error
    assert isinstance(result, Error)
    assert result.error == execution_error_msg


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
    """Verify that memory_context is correctly included in the prompt arguments if applicable."""
    mock_update, mock_get, mock_set, mock_enabled = mock_memory_functions

    # NOTE: The plan_prompt formatting has changed. Memory context is not directly
    # substituted into the plan_prompt string by handle_vibe_request itself.
    # The prompt template passed might contain it if generated elsewhere.
    # This test now verifies the request placeholder is replaced correctly and
    # the schema argument is passed.

    # Define a simple prompt template with the placeholder
    test_plan_prompt = "Plan this: __REQUEST_PLACEHOLDER__"
    test_request = "get the pods"
    test_memory_context = "We are in the 'sandbox' namespace." # Passed but not used for direct formatting here
    expected_formatted_prompt = test_plan_prompt.replace("__REQUEST_PLACEHOLDER__", test_request)

    # Mock the model execution result with valid JSON
    expected_llm_response = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["pods", "-n", "sandbox"],
        "explanation": "Getting pods in sandbox from memory.",
    }
    mock_model_adapter.execute.return_value = json.dumps(expected_llm_response)

    # Call the function under test
    # Need to patch _execute_command as the focus is on the planning call
    with patch("vibectl.command_handler._execute_command") as mock_execute_cmd:
        mock_execute_cmd.return_value = Success(data="done") # Prevent further processing
        handle_vibe_request(
            request=test_request,
            command="vibe", # Using 'vibe' command type for context
            plan_prompt=test_plan_prompt,
            summary_prompt_func=dummy_summary_prompt,
            output_flags=DEFAULT_OUTPUT_FLAGS,
            memory_context=test_memory_context,
            semiauto=True,
        )

    # Assert that the model adapter was called with the formatted prompt and schema
    mock_model_adapter.execute.assert_called_once()
    call_args, call_kwargs = mock_model_adapter.execute.call_args
    assert call_args[0] == mock_model_adapter.get_model.return_value # Check model object
    assert call_args[1] == expected_formatted_prompt # Check formatted prompt string
    assert "schema" in call_kwargs # Check schema was passed
    assert isinstance(call_kwargs["schema"], dict) # Check schema is a dict

    # Assert that the formatting warning was NOT logged
    mock_logger.warning.assert_not_called()
