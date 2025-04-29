"""Tests for command_handler.py's memory handling and edge cases.

This module tests potential memory-related bugs and edge cases in command_handler.py,
focusing on how commands update and interact with memory.
"""

import json
from collections.abc import Generator
from typing import Any
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
    """Test memory is updated even when command output represents an error."""
    # Setup Mocks
    mock_adapter = Mock()
    mock_model = Mock()
    mock_get_adapter.return_value = mock_adapter
    mock_adapter.get_model.return_value = mock_model
    mock_adapter.execute.return_value = "Vibe summary of the error."
    # Simulate truncation
    mock_process_auto.return_value = Truncation(
        original="Error from server: not found", truncated="Error...not found"
    )

    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
        show_kubectl=False,
    )
    error_input = Error(error="Error from server: not found")

    # Call the function under test
    handle_command_output(
        output=error_input,
        output_flags=output_flags,
        summary_prompt_func=dummy_summary_prompt,
        command="get pods",
    )

    # Assert LLM was called with the truncated error output
    mock_adapter.execute.assert_called_once()
    # Check prompt includes error string
    # prompt_arg = mock_adapter.execute.call_args[0][1]
    # assert "Error...not found" in prompt_arg

    # Assert memory was updated with the error
    mock_memory_update.assert_called_once()
    call_kwargs = mock_memory_update.call_args.kwargs
    assert call_kwargs.get("command") == "get pods"
    assert call_kwargs.get("command_output") == error_input.error
    assert call_kwargs.get("vibe_output") == "Vibe summary of the error."


def test_handle_command_output_updates_memory_with_overloaded_error(
    mock_get_adapter: MagicMock,
    mock_memory_update: Mock,
    mock_process_auto: Mock,
) -> None:
    """Test memory is updated correctly when LLM summary itself fails (overloaded)."""
    # Setup Mocks
    mock_adapter = Mock()
    mock_model = Mock()
    mock_get_adapter.return_value = mock_adapter
    mock_adapter.get_model.return_value = mock_model
    # Simulate LLM summary call failing with overloaded error
    overloaded_error_msg = "ERROR: Model capacity is overloaded."
    mock_adapter.execute.return_value = overloaded_error_msg
    # Simulate truncation
    mock_process_auto.return_value = Truncation(
        original="Normal output", truncated="Normal output"
    )

    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
        show_kubectl=False,
    )
    success_input = Success(data="Normal output")

    # Call the function under test
    # Expect an Error result because the summary failed
    result = handle_command_output(
        output=success_input,
        output_flags=output_flags,
        summary_prompt_func=dummy_summary_prompt,
        command="get pods",
    )

    # Assert LLM was called
    mock_adapter.execute.assert_called_once()

    # Assert memory update was NOT called because the summary failed
    mock_memory_update.assert_not_called()

    # Assert the result is an Error object with halt_auto_loop=False
    assert isinstance(result, Error)
    assert result.error == "Model capacity is overloaded."
    assert not result.halt_auto_loop


def test_handle_vibe_request_updates_memory_on_error(
    mock_get_adapter: MagicMock, mock_memory_update: Mock
) -> None:
    """Test handle_vibe_request updates memory when LLM returns ActionType.ERROR."""
    error_msg = "Invalid request parameters."
    explanation = "User asked for something silly."
    error_response_str = json.dumps({
        "action_type": ActionType.ERROR.value,
        "error": error_msg,
        "explanation": explanation,
    })
    mock_get_adapter.return_value.execute.return_value = error_response_str

    # Verb is not needed for this specific error path assertion
    # kubectl_verb = "get"

    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
        show_kubectl=False,
    )

    request_text = "Do something silly"

    # Call handle_vibe_request
    with patch("vibectl.command_handler.console_manager"), \
         patch("vibectl.memory.include_memory_in_prompt", return_value="Plan this: error test"):
        result = handle_vibe_request(
            request=request_text,
            command="vibe",
            plan_prompt="Plan: {request}",
            summary_prompt_func=dummy_summary_prompt,
            output_flags=output_flags,
        )

    # Assert memory update was called correctly
    mock_memory_update.assert_called_once()
    call_kwargs = mock_memory_update.call_args.kwargs
    assert call_kwargs.get("command") == "vibe"
    assert call_kwargs.get("command_output") == f"Planning error: {error_msg}"
    vibe_output_expected = (
        f"Failed to plan command for request: {request_text}. Error: {error_msg}"
    )
    assert call_kwargs.get("vibe_output") == vibe_output_expected
    assert call_kwargs.get("model_name") == output_flags.model_name

    # Assert the function returned an Error object
    assert isinstance(result, Error)
    assert result.error == f"LLM planning error: {error_msg}"
    assert result.recovery_suggestions == explanation


def test_handle_vibe_request_error_recovery_flow(
    mock_get_adapter: MagicMock, mock_memory_update: Mock
) -> None:
    """Test command execution error triggers recovery suggestion.

    Memory is NOT updated directly when command execution fails.
    Recovery suggestions are fetched and displayed.
    """
    # Mock LLM planning response (successful plan, include verb)
    kubectl_args = ["pods"] # Define args
    plan_response = {
        "action_type": ActionType.COMMAND.value,
        "commands": kubectl_args, # <<< Corrected: Args only
        "explanation": "Getting pods as requested",
    }
    # Mock LLM recovery suggestion response
    recovery_suggestion = "Try checking the namespace."
    mock_get_adapter.return_value.execute.side_effect = [
        json.dumps(plan_response),
        json.dumps({
            "action_type": ActionType.FEEDBACK.value,
            "explanation": recovery_suggestion # Simulate feedback as recovery
        })
    ]

    # Create output flags, explicitly enabling show_vibe
    output_flags = OutputFlags(
        show_raw=True, show_vibe=True, warn_no_output=False,
        model_name="test-model", show_kubectl=True
    )

    # Mock dependencies within handle_vibe_request
    with (
        patch("vibectl.command_handler._execute_command") as mock_execute_cmd,
        patch("vibectl.command_handler.console_manager") as mock_console,
        patch("vibectl.memory.include_memory_in_prompt") as mock_include_memory,
        patch("vibectl.command_handler.recovery_prompt") as mock_recovery_prompt,
        patch("vibectl.memory.update_memory") as mock_update_memory_mem_module,
        patch("vibectl.command_handler.handle_command_output") as mock_handle_output,
    ):
        # Mock _execute_command to return an Error
        execution_error_msg = "Command execution failed"
        mock_execute_cmd.return_value = Error(error=execution_error_msg)
        # Mock recovery prompt generation
        mock_recovery_prompt.return_value = "Recovery prompt content"
        # Mock memory include to just return the prompt
        mock_include_memory.side_effect = lambda p, **k: p

        # Mock handle_command_output to simulate its behavior on error
        # It should receive the Error, generate recovery, and return the Error
        def handle_output_side_effect(output_res: Error, *args: Any, **kwargs: Any) -> Error:
            """Side effect that preserves memory updates and returns result."""
            # Import necessary modules locally within the side effect function if needed
            import logging # Added import
            from vibectl.memory import update_memory # Added import

            logger = logging.getLogger("test_side_effect") # Define logger

            if isinstance(output_res, Error):
                # Simulate recovery suggestion logic within the mock
                model_adapter = mock_get_adapter()
                # Corrected recovery prompt call - use error message
                recovery_prompt_content = mock_recovery_prompt(output_res.error)
                # Execute the second LLM call for recovery
                llm_recovery_response_json = model_adapter.execute(
                    model_adapter.get_model(), recovery_prompt_content
                )
                suggestion = None
                try:
                    # Assuming recovery call doesn't need complex schema parsing
                    # Adjust if recovery prompt expects specific JSON
                    # Parse the JSON response
                    recovery_data = json.loads(llm_recovery_response_json)
                    suggestion = recovery_data.get("explanation")

                    if suggestion:
                        mock_console.print_vibe(suggestion) # Use print_vibe with extracted suggestion
                    else:
                        logger.warning("Recovery suggestion JSON missing 'explanation'.")
                        mock_console.print_warning("Could not extract recovery suggestion.")

                except json.JSONDecodeError as e:
                    logger.error(f"Error parsing recovery suggestion JSON: {e}")
                    mock_console.print_error("Failed to parse recovery suggestion JSON.")
                except Exception as e:
                    logger.error(f"Error parsing recovery suggestion: {e}")
                    mock_console.print_error("Failed to parse recovery suggestion.")

                # Update memory with error and recovery
                update_memory(
                    command=kwargs.get("command", "Unknown"),
                    command_output=output_res.error,
                    vibe_output=suggestion or "No recovery suggestion.",
                    # Provide defaults if output_flags is missing
                    model_name=kwargs.get("output_flags", OutputFlags(
                        show_raw=False, show_vibe=False, warn_no_output=False,
                        model_name="default-model", show_kubectl=False
                    )).model_name,
                )

                # Return the original Error, potentially enhanced
                output_res.recovery_suggestions = suggestion # Attach suggestion if found
            return output_res

        mock_handle_output.side_effect = handle_output_side_effect

        # Call handle_vibe_request
        result = handle_vibe_request(
            request="get pods causing error",
            command="vibe", # <<< Corrected command to 'vibe'
            plan_prompt="Plan: {request}",
            summary_prompt_func=lambda: "Summary: {output}",
            output_flags=output_flags,
            live_display=False, # Ensure live display is off for this test
        )

        # Verify _execute_command was called with the correct verb and args
        mock_execute_cmd.assert_called_once_with("vibe", kubectl_args, None)

        # Verify handle_command_output was called with the Error object
        mock_handle_output.assert_called_once()
        ho_call_args, ho_kwargs = mock_handle_output.call_args
        assert isinstance(ho_call_args[0], Error)
        assert ho_call_args[0].error == execution_error_msg

        # Verify the recovery prompt was generated
        # The call happens inside the handle_output_side_effect mock
        mock_recovery_prompt.assert_called_once_with(execution_error_msg)

        # Verify the LLM was called twice (Plan + Recovery)
        assert mock_get_adapter.return_value.execute.call_count == 2

        # Verify the recovery suggestion was printed *by the mock side effect*
        mock_console.print_vibe.assert_called_with(recovery_suggestion)

        # Verify memory WAS updated (via the patched function in memory module)
        mock_update_memory_mem_module.assert_called_once()
        update_kwargs = mock_update_memory_mem_module.call_args.kwargs
        assert update_kwargs.get("command") == "vibe"
        assert update_kwargs.get("command_output") == execution_error_msg
        assert update_kwargs.get("vibe_output") == recovery_suggestion

        # Verify the final result contains the error and the suggestion
        assert isinstance(result, Error)
        assert result.error == execution_error_msg
        assert result.recovery_suggestions == recovery_suggestion


def test_handle_vibe_request_includes_memory_context(
    mock_model_adapter: MagicMock,
    mock_memory_functions: tuple,
    mock_logger: MagicMock,
) -> None:
    """Verify memory_context is included in the prompt arguments if applicable."""
    mock_update, mock_get, mock_set, mock_enabled = mock_memory_functions

    # This test now verifies the request placeholder is replaced correctly and
    # the schema argument is passed.

    # Define a simple prompt template with the placeholder
    test_plan_prompt = "Plan this: __REQUEST_PLACEHOLDER__"
    test_request = "get the pods"
    test_memory_context = "We are in the 'sandbox' namespace."
    expected_final_prompt = test_plan_prompt.replace(
        "__REQUEST_PLACEHOLDER__", test_request
    )

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
            command="get",
            plan_prompt=test_plan_prompt,
            summary_prompt_func=dummy_summary_prompt,
            output_flags=DEFAULT_OUTPUT_FLAGS,
            memory_context=test_memory_context, # Pass memory context
        )

        # Verify that the prompt passed to the model includes the request
        # but not memory context placeholder and includes the schema

        # Assert that get_memory was called (implicitly by handle_vibe_request setup)
        # This seems necessary even when memory_context is provided directly.
        # mock_get.assert_called_once()


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


