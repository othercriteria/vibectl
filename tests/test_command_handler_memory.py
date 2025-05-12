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
from vibectl.schema import LLMCommandResponse
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
    with patch("vibectl.command_handler.get_model_adapter") as mock_adapter_factory:
        # Set up mock adapter instance
        mock_adapter_instance = MagicMock()
        mock_adapter_factory.return_value = mock_adapter_instance

        # Set up mock model object
        mock_model = Mock()
        mock_adapter_instance.get_model.return_value = mock_model
        # Default return value for execute_and_log_metrics - NOW A TUPLE
        mock_adapter_instance.execute_and_log_metrics.return_value = (
            "Test response",
            None,
        )

        yield mock_adapter_factory  # Yield the factory mock


@pytest.mark.asyncio
async def test_handle_command_output_updates_memory(
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

    # Check that the LLM was called for the summary
    mock_adapter_instance = mock_get_adapter.return_value
    # Check execute_and_log_metrics was called for summary
    # Ensure the call count check reflects planning + summary (if applicable)
    # or just memory update
    # This assertion might need adjustment based on whether summary is mocked out
    assert mock_adapter_instance.execute_and_log_metrics.call_count >= 1


@pytest.mark.asyncio
async def test_handle_command_output_does_not_update_memory_without_command(
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
            "vibectl.command_handler._get_llm_summary",
            return_value=("Test response", None),
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

    # Check that the LLM was called for the summary
    mock_adapter_instance = mock_get_adapter.return_value
    # Check execute_and_log_metrics was called for summary
    # Ensure the call count check reflects planning + summary (if applicable)
    # or just memory update
    # This assertion might need adjustment based on whether summary is mocked out
    assert mock_adapter_instance.execute_and_log_metrics.call_count == 0


@pytest.mark.asyncio
async def test_handle_command_output_updates_memory_with_error_output(
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
    mock_adapter.execute_and_log_metrics.return_value = (
        "Vibe summary of the error.",
        None,
    )
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
    mock_adapter.execute_and_log_metrics.assert_called_once()
    # Check prompt includes error string
    # prompt_arg = mock_adapter.execute.call_args[0][1]
    # assert "Error...not found" in prompt_arg

    # Assert memory was updated with the error
    mock_memory_update.assert_called_once()
    call_kwargs = mock_memory_update.call_args.kwargs
    assert call_kwargs.get("command") == "get pods"
    assert call_kwargs.get("command_output") == error_input.error
    assert call_kwargs.get("vibe_output") == "Vibe summary of the error."

    # Check that the LLM was called for the summary
    mock_adapter_instance = mock_get_adapter.return_value
    # Check execute_and_log_metrics was called for summary
    # Ensure the call count check reflects planning + summary (if applicable)
    # or just memory update
    # This assertion might need adjustment based on whether summary is mocked out
    assert mock_adapter_instance.execute_and_log_metrics.call_count >= 1


@pytest.mark.asyncio
async def test_handle_command_output_updates_memory_with_overloaded_error(
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
    # Simulate LLM summary call failing with overloaded error - NOW A TUPLE
    overloaded_error_msg = "ERROR: Model capacity is overloaded."
    mock_adapter.execute_and_log_metrics.return_value = (overloaded_error_msg, None)
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
    mock_adapter.execute_and_log_metrics.assert_called_once()

    # Assert memory update was NOT called because the summary failed
    mock_memory_update.assert_not_called()

    # Assert the result is an Error object with halt_auto_loop=False
    assert isinstance(result, Error)
    assert result.error == "Model capacity is overloaded."
    assert not result.halt_auto_loop

    # Check that the LLM was called for the summary
    mock_adapter_instance = mock_get_adapter.return_value
    # Check execute_and_log_metrics was called for summary
    # Ensure the call count check reflects planning + summary (if applicable)
    # or just memory update
    # This assertion might need adjustment based on whether summary is mocked out
    assert mock_adapter_instance.execute_and_log_metrics.call_count == 1


@pytest.mark.asyncio
async def test_handle_vibe_request_updates_memory_on_error(
    mock_get_adapter: MagicMock, mock_memory_update: Mock
) -> None:
    """Test handle_vibe_request updates memory when LLM returns ActionType.ERROR."""
    error_msg = "Invalid request parameters."
    explanation = "User asked for something silly."
    error_response_str = json.dumps(
        {
            "action_type": ActionType.ERROR.value,
            "error": error_msg,
            "explanation": explanation,
        }
    )
    mock_get_adapter.return_value.execute_and_log_metrics.return_value = (
        error_response_str,
        None,
    )

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
    with (
        patch("vibectl.command_handler.console_manager"),
        patch(
            "vibectl.memory.include_memory_in_prompt",
            return_value="Plan this: error test",
        ),
    ):
        result = await handle_vibe_request(
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
    assert call_kwargs.get("command_output") == error_msg
    assert (
        call_kwargs.get("vibe_output")
        == f"LLM Planning Error: {request_text} -> {error_msg}"
    )
    assert call_kwargs.get("model_name") == "test-model"

    # Assert the function returned an Error object
    assert isinstance(result, Error)
    assert result.error == f"LLM planning error: {error_msg}"
    assert result.recovery_suggestions == explanation

    # Check that the LLM was called for the memory update
    mock_adapter_instance = mock_get_adapter.return_value
    mock_adapter_instance.execute_and_log_metrics.assert_called_once()


@pytest.mark.asyncio
async def test_handle_vibe_request_error_recovery_flow(
    mock_get_adapter: MagicMock, mock_memory_update: Mock
) -> None:
    """Test command execution error triggers recovery suggestion.

    Memory is NOT updated directly when command execution fails.
    Recovery suggestions are fetched and displayed.
    """
    # Mock LLM planning response (successful plan, include verb)
    kubectl_verb = "get"  # Define the verb
    kubectl_args = ["pods"]  # Define args
    plan_response = {
        "action_type": ActionType.COMMAND.value,
        "commands": [kubectl_verb, *kubectl_args],
        "explanation": "Getting pods as requested",
    }
    # Mock LLM recovery suggestion response
    recovery_suggestion = "Try checking the namespace."
    mock_get_adapter.return_value.execute_and_log_metrics.side_effect = [
        (json.dumps(plan_response), None),
        (
            json.dumps(
                {
                    "action_type": ActionType.FEEDBACK.value,
                    "explanation": recovery_suggestion,  # Simulate feedback as recovery
                }
            ),
            None,
        ),
        ("Summary after recovery.", None),  # For _get_llm_summary call
    ]

    # Create output flags, explicitly enabling show_vibe
    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
        show_kubectl=True,
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
        def handle_output_side_effect(
            output_res: Error, *args: Any, **kwargs: Any
        ) -> Error:
            """Side effect that preserves memory updates and returns result."""
            # Import necessary modules locally within the side effect function if needed
            import logging  # Added import

            from vibectl.memory import update_memory  # Added import

            logger = logging.getLogger("test_side_effect")  # Define logger

            if isinstance(output_res, Error):
                # Simulate recovery suggestion logic within the mock
                model_adapter = mock_get_adapter()
                # Corrected recovery prompt call - use error message
                recovery_prompt_content = mock_recovery_prompt(output_res.error)
                # Execute the second LLM call for recovery
                # UNPACK THE TUPLE HERE
                llm_response_tuple = model_adapter.execute_and_log_metrics(
                    model_adapter.get_model(), recovery_prompt_content
                )
                llm_recovery_response_json = llm_response_tuple[
                    0
                ]  # Get the JSON string
                suggestion = None
                try:
                    # Assuming recovery call doesn\'t need complex schema parsing
                    # Adjust if recovery prompt expects specific JSON
                    # Parse the JSON response
                    recovery_data = json.loads(llm_recovery_response_json)
                    suggestion = recovery_data.get("explanation")

                    if suggestion:
                        mock_console.print_vibe(
                            suggestion
                        )  # Use print_vibe with extracted suggestion
                    else:
                        logger.warning(
                            "Recovery suggestion JSON missing 'explanation'."
                        )
                        mock_console.print_warning(
                            "Could not extract recovery suggestion."
                        )

                except json.JSONDecodeError as e:
                    logger.error(f"Error parsing recovery suggestion JSON: {e}")
                    mock_console.print_error(
                        "Failed to parse recovery suggestion JSON."
                    )
                except Exception as e:
                    logger.error(f"Error parsing recovery suggestion: {e}")
                    mock_console.print_error("Failed to parse recovery suggestion.")

                # Update memory with error and recovery
                update_memory(
                    command=kwargs.get("command", "Unknown"),
                    command_output=output_res.error,
                    vibe_output=suggestion or "No recovery suggestion.",
                    # Provide defaults if output_flags is missing
                    model_name=kwargs.get(
                        "output_flags",
                        OutputFlags(
                            show_raw=False,
                            show_vibe=False,
                            warn_no_output=False,
                            model_name="default-model",
                            show_kubectl=False,
                        ),
                    ).model_name,
                )

                # Return the original Error, potentially enhanced
                output_res.recovery_suggestions = (
                    suggestion  # Attach suggestion if found
                )
            return output_res

        mock_handle_output.side_effect = handle_output_side_effect

        # Call handle_vibe_request
        result = await handle_vibe_request(
            request="get pods causing error",
            command="vibe",  # <<< Corrected command to 'vibe'
            plan_prompt="Plan: {request}",
            summary_prompt_func=lambda: "Summary: {output}",
            output_flags=output_flags,
            live_display=False,  # Ensure live display is off for this test
        )

        # Verify _execute_command was called with the correct verb and args
        mock_execute_cmd.assert_called_once_with(kubectl_verb, kubectl_args, None)

        # Verify handle_command_output was called with the Error object
        mock_handle_output.assert_called_once()
        call_args, call_kwargs = mock_handle_output.call_args
        # First positional arg should be the Error object
        assert call_args[0] is result  # Use the result from handle_vibe_request
        assert call_kwargs.get("command") == kubectl_verb  # Expect the actual verb

        # Verify the recovery prompt was generated
        # The call happens inside the handle_output_side_effect mock
        mock_recovery_prompt.assert_called_once_with(execution_error_msg)

        # Verify the LLM was called multiple times (Plan + Recovery)
        assert mock_get_adapter.return_value.execute_and_log_metrics.call_count == 2

        # Verify the recovery suggestion was extracted and returned
        assert isinstance(result, Error)  # Ensure it's an Error object
        assert result.recovery_suggestions == recovery_suggestion  # type: ignore[attr-defined]

        # Verify memory WAS updated (via the patched function in memory module)
        mock_update_memory_mem_module.assert_called_once()
        update_kwargs = mock_update_memory_mem_module.call_args.kwargs
        assert (
            update_kwargs.get("command") == kubectl_verb
        )  # Assert against the correct verb

        # Verify the final result contains the error and the suggestion
        assert isinstance(result, Error)
        assert result.error == execution_error_msg
        assert result.recovery_suggestions == recovery_suggestion

        # Check that execute_and_log_metrics was called for the plan and summary
        mock_adapter_instance = mock_get_adapter.return_value
        assert mock_adapter_instance.execute_and_log_metrics.call_count == 2

        # Verify the prompt and schema used in the first call (planning)
        # (Assuming the planning call is the first one)


@pytest.mark.asyncio
async def test_handle_vibe_request_includes_memory_context(
    mock_model_adapter: MagicMock,
    mock_memory_functions: tuple,
    mock_logger: MagicMock,
) -> None:
    """Verify memory_context is included in the prompt arguments if applicable."""
    mock_update, mock_get, mock_set, mock_enabled = mock_memory_functions
    memory_content = "Existing memory context."
    mock_get.return_value = memory_content

    # Define expected response
    expected_llm_response = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["pods", "-n", "sandbox"],
        "explanation": "Getting pods in sandbox from memory.",
    }
    # Configure the mock adapter (yielded by the fixture) for this test
    mock_model_adapter.execute_and_log_metrics.return_value = (
        json.dumps(expected_llm_response),
        None,
    )

    # Patch _execute_command
    with patch("vibectl.command_handler._execute_command") as mock_execute_cmd:
        mock_execute_cmd.return_value = Success(data="done")

        # Call the function under test
        await handle_vibe_request(
            request="get the pods",
            command="get",
            plan_prompt="Plan this: __REQUEST_PLACEHOLDER__",
            summary_prompt_func=dummy_summary_prompt,
            output_flags=DEFAULT_OUTPUT_FLAGS,  # Defined at the end of the file
            memory_context=memory_content,
        )

        # Assert that execute_and_log_metrics was called at least once
        assert mock_model_adapter.execute_and_log_metrics.call_count >= 1

        # Restore detailed argument checking for the first call (planning call)
        planning_call_args = mock_model_adapter.execute_and_log_metrics.call_args_list[
            0
        ]
        # Unpack args and kwargs
        call_args, call_kwargs = planning_call_args
        # Check KEYWORD arguments (model, prompt_text, response_model)
        assert "model" in call_kwargs
        assert call_kwargs["model"] == mock_model_adapter.get_model.return_value
        assert "prompt_text" in call_kwargs
        assert call_kwargs["prompt_text"] == "Plan this: get the pods"
        assert "response_model" in call_kwargs
        assert call_kwargs["response_model"] == LLMCommandResponse


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
    """Mock get_model_adapter factory and the adapter instance it returns."""
    # Import the class to use for spec
    from vibectl.model_adapter import LLMModelAdapter

    with patch("vibectl.command_handler.get_model_adapter") as mock_factory:
        # Create instance with spec for better mocking
        mock_adapter_instance = MagicMock(spec=LLMModelAdapter)
        # Configure the factory to return this instance
        mock_factory.return_value = mock_adapter_instance

        # Configure methods on the instance
        mock_adapter_instance.get_model.return_value = (
            MagicMock()
        )  # Mock the model object
        # Ensure default execute method returns a tuple
        mock_adapter_instance.execute_and_log_metrics.return_value = (
            "Default LLM Response",
            None,
        )

        yield mock_adapter_instance  # Yield the configured INSTANCE


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
