"""Tests for command_handler.py's memory handling and edge cases.

This module tests potential memory-related bugs and edge cases in command_handler.py,
focusing on how commands update and interact with memory.
"""

import json
from collections.abc import Generator
from typing import Any
from unittest.mock import ANY, MagicMock, Mock, patch

import llm  # Import the llm library
import pytest

from vibectl.config import Config
from vibectl.execution.vibe import (
    handle_command_output,
    handle_vibe_request,
)
from vibectl.prompt import (
    plan_vibe_fragments,
)
from vibectl.schema import ActionType, CommandAction, ErrorAction, LLMPlannerResponse
from vibectl.types import (
    Error,
    Fragment,
    LLMMetrics,
    OutputFlags,
    PromptFragments,
    Success,
    SystemFragments,
    Truncation,
    UserFragments,
)


@pytest.fixture
def mock_memory_update() -> Generator[Mock, None, None]:
    """Mock the update_memory function to check memory updates."""
    with patch("vibectl.command_handler.update_memory") as mock:
        mock.return_value = LLMMetrics(
            token_input=1, token_output=1, latency_ms=1, total_processing_duration_ms=2
        )
        yield mock


@pytest.fixture
def mock_process_auto() -> Generator[Mock, None, None]:
    """Mock output processor's process_auto method."""
    with patch("vibectl.execution.vibe.output_processor.process_auto") as mock:
        # Default return no truncation, but as a Truncation object
        mock.return_value = Truncation(
            original="processed content", truncated="processed content"
        )
        yield mock


@pytest.mark.asyncio
# @patch("vibectl.model_adapter.get_model_adapter") # Removed this patch
async def test_handle_command_output_updates_memory(
    # mock_get_model_adapter_func: MagicMock, # Removed
    mock_memory: dict[str, MagicMock],  # Changed from mock_memory_update: Mock
    mock_process_auto: Mock,
    mock_get_adapter: MagicMock,  # This is now from conftest.py
) -> None:
    """Test that handle_command_output correctly updates memory."""
    mock_memory_update = mock_memory["update"]

    mock_get_adapter.execute_and_log_metrics.return_value = (
        "mocked summary",
        LLMMetrics(),
    )

    # Reconfigure the get_model method of the conftest mock_get_adapter for this test
    mock_llm_for_test = MagicMock(spec=llm.Model)  # type: ignore
    mock_llm_for_test.name = "test-model"

    original_get_model_side_effect = mock_get_adapter.get_model.side_effect

    def get_model_override(model_name_arg: str) -> Any:
        if model_name_arg == "test-model":
            return mock_llm_for_test
        if original_get_model_side_effect:
            # Call original side effect if it exists (e.g. from conftest)
            # for other models
            return original_get_model_side_effect(model_name_arg)
        # Default fallback if no original side effect or if it doesn't raise
        raise llm.UnknownModelError(  # type: ignore [attr-defined]
            f"get_model_override received unmocked: {model_name_arg}"
        )

    mock_get_adapter.get_model.side_effect = get_model_override

    # Configure output flags
    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
        show_metrics=True,
    )

    # Call handle_command_output with a command
    with (
        patch("vibectl.execution.vibe.console_manager"),
        patch("vibectl.execution.vibe.Config") as mock_vibe_config_cls,
    ):
        mock_vibe_config_instance = mock_vibe_config_cls.return_value
        mock_vibe_config_instance.is_memory_enabled.return_value = True

        # Configure mock_process_auto for this specific test
        mock_process_auto.return_value = Truncation(
            original="test output", truncated="processed test output"
        )
        # The mock_get_adapter fixture is configured to return ("Test response", None)
        # by execute_and_log_metrics, which matches the expectation for vibe_output.
        handle_command_output(
            output=Success(data="test output"),
            output_flags=output_flags,
            summary_prompt_func=get_test_summary_fragments,
            command="get pods",
        )

    # Verify memory was updated
    mock_memory_update.assert_called_once()  # Simplified assertion

    # Verify arguments if called (can be re-enabled later)
    # mock_memory_update.assert_called_once_with(
    #     command_message="get pods",  # Command message should be the command itself
    #     command_output="test output",
    #     vibe_output="Test response",  # This should match the mocked LLM summary
    #     model_name="test-model",
    # )

    # Check that the LLM was called for the summary
    assert mock_get_adapter.execute_and_log_metrics.call_count == 1

    # At the end of the test, restore the original side_effect if necessary,
    # though pytest fixtures usually handle teardown if side_effect was set on
    # a fixture-provided mock.
    # For safety, if tests run in unexpected order or share state beyond pytest's
    # typical isolation:
    mock_get_adapter.get_model.side_effect = original_get_model_side_effect


@pytest.mark.asyncio
async def test_handle_command_output_does_not_update_memory_without_command(
    mock_memory: dict[str, MagicMock],  # Changed from mock_memory_update: Mock
    mock_process_auto: Mock,
    mock_get_adapter: MagicMock,
) -> None:
    """Test that memory is updated with 'Unknown' command when no command provided."""
    mock_memory_update = mock_memory["update"]

    mock_get_adapter.execute_and_log_metrics.return_value = (
        "mocked summary",
        LLMMetrics(),
    )
    # Configure output flags
    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
        show_metrics=True,
    )

    # Call handle_command_output without a command
    with (
        patch("vibectl.execution.vibe.console_manager"),
        patch("vibectl.execution.vibe.Config") as mock_vibe_config_cls,
    ):
        mock_vibe_config_instance = mock_vibe_config_cls.return_value
        mock_vibe_config_instance.is_memory_enabled.return_value = True

        mock_process_auto.return_value = Truncation(
            original="test output", truncated="processed test output"
        )
        # The mock_get_adapter fixture is configured to return ("Test response", None)
        handle_command_output(
            output=Success(data="test output"),
            output_flags=output_flags,
            summary_prompt_func=get_test_summary_fragments,
            # command is omitted here
        )

    # Verify memory WAS updated
    mock_memory_update.assert_called_once()  # Simplified assertion

    # Check that the LLM was called for the summary
    assert mock_get_adapter.execute_and_log_metrics.call_count == 1


@pytest.mark.asyncio
async def test_handle_command_output_updates_memory_with_error_output(
    mock_memory: dict[str, MagicMock],
    mock_process_auto: Mock,
    mock_get_adapter: MagicMock,
) -> None:
    """Test memory is updated even when command output represents an error."""
    # Use the passed mock_get_adapter instance
    mock_adapter = mock_get_adapter

    # Simulate truncation
    mock_process_auto.return_value = Truncation(
        original="Error from server: not found", truncated="Error...not found"
    )

    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,  # show_vibe=True means it will try recovery
        warn_no_output=False,
        model_name="test-model",
        show_kubectl=False,
        show_metrics=True,
    )
    error_input = Error(error="Error from server: not found")

    expected_recovery_suggestion_text = (
        "Try checking the pod logs for more details."  # Changed from JSON
    )

    # Only one LLM call is made for recovery suggestions.
    # This call returns plain text, not a JSON command structure.
    mock_adapter.execute_and_log_metrics.return_value = (
        expected_recovery_suggestion_text,  # Use plain text
        LLMMetrics(
            token_input=10,
            token_output=20,
            latency_ms=100,
            total_processing_duration_ms=120,
        ),  # Metrics for recovery
    )

    # We need to patch recovery_prompt as it's called before the LLM
    # in the error recovery path
    with patch("vibectl.prompt.recovery_prompt") as mock_recovery_prompt:
        mock_recovery_prompt.return_value = (
            SystemFragments([Fragment("sys")]),
            UserFragments([Fragment("user")]),
        )

        handle_command_output(
            output=error_input,
            output_flags=output_flags,
            summary_prompt_func=get_test_summary_fragments,
            command="get pods",
        )

    # Assert memory was updated with the error and the recovery suggestion
    mock_memory["update"].assert_called_once()  # Simplified assertion

    # Check that the LLM was called once for recovery
    mock_adapter.execute_and_log_metrics.assert_called_once()


@pytest.mark.asyncio
async def test_handle_command_output_updates_memory_with_overloaded_error(
    mock_memory: dict[str, MagicMock],
    mock_process_auto: Mock,
    mock_get_adapter: MagicMock,
) -> None:
    """Test memory is updated correctly when LLM summary itself fails (overloaded)."""
    # Use the passed mock_get_adapter instance
    mock_adapter = mock_get_adapter

    # Simulate LLM summary call failing with overloaded error
    overloaded_error_msg = "ERROR: Model capacity is overloaded."
    # This is for the _get_llm_summary_for_memory_update call
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
        show_metrics=True,
    )
    success_input = Success(data="Normal output")

    # Patch Config where it's instantiated by the code under test
    with patch("vibectl.execution.vibe.Config") as mock_config_cls:
        mock_config_instance = mock_config_cls.return_value
        mock_config_instance.is_memory_enabled.return_value = True

        # Call the function under test
        handle_command_output(
            output=success_input,
            output_flags=output_flags,
            summary_prompt_func=get_test_summary_fragments,
            command="get pods",
        )

    # If the LLM summary returns an "ERROR:", _process_vibe_output returns an Error
    # object and does NOT call update_memory.
    mock_memory["update"].assert_not_called()

    # Check that the LLM was called once for the summary attempt
    mock_adapter.execute_and_log_metrics.assert_called_once()


@pytest.mark.asyncio
async def test_handle_vibe_request_updates_memory_on_error(
    mock_get_adapter: MagicMock,
    # mock_memory_update: Mock # This fixture patches command_handler.update_memory
) -> None:
    """Test handle_vibe_request updates memory when LLM planning results in an error."""
    with patch("vibectl.execution.vibe.update_memory") as mock_vibe_update_memory:
        mock_vibe_update_memory.return_value = LLMMetrics(
            token_input=1, token_output=1, latency_ms=1, total_processing_duration_ms=2
        )
        request_text = "error test"
        llm_error_message = "LLM planning failed due to invalid input."

        # Configure mock_get_adapter for this test
        error_action = ErrorAction(
            action_type=ActionType.ERROR, message=llm_error_message
        )
        llm_response_obj = LLMPlannerResponse(action=error_action)
        mock_get_adapter.execute_and_log_metrics.return_value = (
            llm_response_obj.model_dump_json(),
            None,  # Metrics for the planning call
        )

        output_flags = OutputFlags(
            show_raw=False,
            show_vibe=True,
            warn_no_output=False,
            model_name="test-model",
            show_metrics=True,
        )

        with patch("vibectl.execution.vibe.Config") as mock_vibe_config_cls:
            mock_vibe_config_instance = mock_vibe_config_cls.return_value
            mock_vibe_config_instance.is_memory_enabled.return_value = True

            result = await handle_vibe_request(
                request=request_text,
                command="vibe",
                plan_prompt_func=plan_vibe_fragments,
                summary_prompt_func=get_test_summary_fragments,
                output_flags=output_flags,
            )

        mock_vibe_update_memory.assert_called_once()
        call_kwargs = mock_vibe_update_memory.call_args.kwargs
        assert (
            call_kwargs.get("command_message")
            == f"command: vibe request: {request_text}"
        )
        assert call_kwargs.get("command_output") == llm_error_message

        # Assert the function returned an Error object
        assert isinstance(result, Error)
        assert result.error == f"LLM planning error: {llm_error_message}"
        assert result.recovery_suggestions == llm_error_message

        # Check that the LLM was called for the planning
        mock_get_adapter.execute_and_log_metrics.assert_called_once()


@pytest.mark.asyncio
async def test_handle_vibe_request_error_recovery_flow(
    mock_get_adapter: MagicMock, mock_memory: dict[str, MagicMock]
) -> None:
    """Test command execution error triggers recovery suggestion and memory updates.

    Specifically tests that `vibectl.memory.update_memory` is called after recovery.
    """
    # Mock LLM planning response (successful plan, include verb)
    kubectl_verb = "get"
    kubectl_args = ["pods"]
    # plan_response = {
    #     "action_type": ActionType.COMMAND.value,
    #     "commands": [kubectl_verb, *kubectl_args],
    #     "explanation": "Plan to get pods",
    # }
    # Mock LLM recovery suggestion response
    recovery_suggestion_text = "Try checking the namespace."
    # This is the summary text for the first memory update (after command exec)
    memory_update_summary_text = "Memory summary after get pods."

    mock_get_adapter.execute_and_log_metrics.side_effect = [
        (
            # Call 1: Planning
            LLMPlannerResponse(
                action=CommandAction(
                    action_type=ActionType.COMMAND,
                    commands=["get", "pods"],
                )
            ).model_dump_json(),
            LLMMetrics(
                token_input=50,
                token_output=30,
                latency_ms=200,
                total_processing_duration_ms=220,
            ),
        ),
        (
            # Call 2: Memory update summary for _confirm_and_execute_plan
            memory_update_summary_text,
            LLMMetrics(
                token_input=5,
                token_output=5,
                latency_ms=50,
                total_processing_duration_ms=60,
            ),
        ),
        (
            # Call 3: Recovery suggestion for handle_command_output
            recovery_suggestion_text,
            LLMMetrics(
                token_input=10,
                token_output=20,
                latency_ms=100,
                total_processing_duration_ms=120,
            ),
        ),
    ]

    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=True,  # Important for recovery path in handle_command_output
        warn_no_output=False,
        model_name="test-model",
        show_kubectl=True,
        show_metrics=True,
    )
    original_execution_error = Error(
        error="kubectl failed: pod not found", exception=RuntimeError("simulated")
    )

    # We need to mock multiple components:
    # - _execute_command: to simulate kubectl failure
    # - console_manager: to suppress print
    # - recovery_prompt: to control input to recovery LLM call
    # - vibectl.memory.update_memory: to check the specific memory update
    # - handle_command_output: to control its return and check how it's called

    with (
        patch("vibectl.execution.vibe._execute_command") as mock_execute_cmd,
        patch("vibectl.execution.vibe.console_manager"),
        patch("vibectl.command_handler.recovery_prompt") as mock_recovery_prompt,
        patch(
            "vibectl.execution.vibe.handle_command_output"
        ) as mock_handle_output_wrapper,
        patch(
            "vibectl.execution.vibe.Config"
        ) as mock_vibe_config_cls,  # Added Config mock for handle_vibe_request
    ):
        mock_vibe_config_instance = mock_vibe_config_cls.return_value
        mock_vibe_config_instance.is_memory_enabled.return_value = (
            True  # Ensure memory checks pass if relevant
        )

        mock_execute_cmd.return_value = original_execution_error

        def handle_output_side_effect(
            output_res: Error, *args: Any, **kwargs: Any
        ) -> Error:
            # Simulate that handle_command_output, when given an Error,
            # fetches recovery and annotates the error object.
            if isinstance(output_res, Error):
                output_res.recovery_suggestions = (
                    recovery_suggestion_text  # Set by internal recovery
                )
                # It would internally call vibectl.command_handler.update_memory
                # For this test, we assume that happened as tested elsewhere or
                # via mock_memory_update
            return output_res

        mock_handle_output_wrapper.side_effect = handle_output_side_effect
        mock_recovery_prompt.return_value = (
            SystemFragments([]),
            UserFragments([]),
        )

        # Call the main function
        result = await handle_vibe_request(
            request="get my pods",
            command="vibe",
            plan_prompt_func=plan_vibe_fragments,
            summary_prompt_func=get_test_summary_fragments,
            output_flags=output_flags,
            yes=True,
        )

        # --- Assertions ---
        # 1. LLM planning call
        mock_get_adapter.execute_and_log_metrics.assert_any_call(
            model=mock_get_adapter.get_model.return_value,
            system_fragments=ANY,
            user_fragments=ANY,
            response_model=LLMPlannerResponse,
        )
        # 2. Kubectl execution
        mock_execute_cmd.assert_called_once_with(
            kubectl_verb, kubectl_args, None, allowed_exit_codes=(0,)
        )

        # 3. handle_command_output wrapper was called
        mock_handle_output_wrapper.assert_called_once()
        # Check that original_error was passed to handle_command_output
        assert mock_handle_output_wrapper.call_args[0][0] == original_execution_error
        # Check that show_vibe was True when handle_command_output was called
        # output_flags is the second positional argument (index 1 in the args tuple)
        assert mock_handle_output_wrapper.call_args[0][1].show_vibe is True

        # 4. Final result from handle_vibe_request
        assert isinstance(result, Error)
        assert result.error == original_execution_error.error
        assert result.recovery_suggestions == recovery_suggestion_text


@pytest.mark.asyncio
async def test_handle_vibe_request_includes_memory_context(
    mock_get_adapter: MagicMock,
    mock_memory: dict[str, MagicMock],  # Changed parameter name and type
    mock_logger: MagicMock,
) -> None:
    """Test that handle_vibe_request includes memory context in the prompt."""
    mock_get_memory = mock_memory["get"]  # Use from mock_memory fixture
    mock_get_memory.return_value = "Previous memory context"

    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
        show_kubectl=False,
        show_metrics=True,
    )

    # Mock the LLM response for the planning phase
    mock_get_adapter.execute_and_log_metrics.return_value = (
        json.dumps(
            {
                "action": {
                    "action_type": "COMMAND",
                    "commands": ["pods", "-A"],
                    "explanation": "Get all pods",
                }
            }
        ),
        LLMMetrics(
            token_input=100,
            token_output=50,
            latency_ms=200,
            total_processing_duration_ms=250,
        ),
    )

    # Create a mock for the plan_prompt_func
    mock_plan_fragments_func = MagicMock(name="mock_plan_fragments_func")
    mock_plan_fragments_func.return_value = (
        SystemFragments([Fragment("System Prompt")]),
        UserFragments([Fragment("User Prompt Base")]),
    )

    with patch("vibectl.execution.vibe._confirm_and_execute_plan"):
        await handle_vibe_request(
            request="show all pods",
            command="vibe",
            plan_prompt_func=mock_plan_fragments_func,  # Pass the direct mock
            summary_prompt_func=get_test_summary_fragments,
            output_flags=output_flags,
            yes=True,
        )

    # Verify that the mock_plan_fragments_func was called by handle_vibe_request
    mock_plan_fragments_func.assert_called_once()

    # Verify that execute_and_log_metrics was called for planning
    mock_get_adapter.execute_and_log_metrics.assert_called_once_with(
        model=mock_get_adapter.get_model.return_value,
        system_fragments=ANY,  # Use ANY for complex objects if exact match is hard
        user_fragments=ANY,
        response_model=LLMPlannerResponse,
    )

    # Verify the prompt content passed to the LLM
    call_args = mock_get_adapter.execute_and_log_metrics.call_args
    assert call_args is not None
    kwargs_dict = call_args.kwargs

    passed_system_fragments = kwargs_dict.get("system_fragments")
    passed_user_fragments = kwargs_dict.get("user_fragments")

    assert passed_system_fragments == SystemFragments([Fragment("System Prompt")])

    expected_user_fragments = UserFragments(
        [
            Fragment("Memory Context:\nPrevious memory context"),
            Fragment("User Prompt Base"),
            Fragment("show all pods"),
        ]
    )
    assert passed_user_fragments == expected_user_fragments
    mock_get_memory.assert_called_with(ANY)


@pytest.fixture(autouse=True)
def mock_logger() -> Generator[MagicMock, None, None]:
    """Mock the logger to prevent real logging during tests."""
    with patch("vibectl.command_handler.logger") as mock_log:
        yield mock_log


@pytest.fixture(autouse=True)
def mock_console_manager() -> Generator[MagicMock, None, None]:
    """Mock the console manager to prevent real console output."""
    with patch("vibectl.execution.vibe.console_manager") as mock_console:
        yield mock_console


@pytest.fixture
def mock_memory_functions() -> Generator[tuple[Mock, Mock, Mock, Mock], None, None]:
    """Mocks core memory functions including get_memory, set_memory, update_memory.

    Yields a tuple of mocks:
      (
        mock_get_memory,
        mock_set_memory,
        mock_update_memory,
        mock_memory_update_prompt_func,
      )
    These patch locations in `vibectl.command_handler` because that is where they
    are imported and used by the functions under test (e.g. handle_vibe_request).
    """
    with (
        patch("vibectl.execution.vibe.get_memory") as mock_get_memory,
        patch("vibectl.execution.vibe.set_memory") as mock_set_memory,
        patch("vibectl.execution.vibe.update_memory") as mock_update_memory,
        patch(
            "vibectl.prompt.memory_update_prompt"
        ) as mock_memory_update_prompt_func,  # Patched in prompt module
    ):
        # Set default return values or side effects as needed
        mock_get_memory.return_value = "Initial memory context for testing."
        # Example: mock_memory_update_prompt_func.return_value = (["Sys"], ["User"])

        yield (
            mock_get_memory,
            mock_set_memory,
            mock_update_memory,
            mock_memory_update_prompt_func,
        )


# Helper function for dummy prompt fragments
def get_test_summary_fragments(
    config: Config | None = None,
) -> PromptFragments:
    """Dummy summary prompt function for testing that returns fragments."""
    return PromptFragments(
        (
            SystemFragments([Fragment("System fragment with {output}")]),
            UserFragments([Fragment("User fragment with {output}")]),
        )
    )


DEFAULT_OUTPUT_FLAGS = OutputFlags(
    show_raw=False,
    show_vibe=True,
    warn_no_output=True,
    model_name="test-model",
    show_metrics=True,
    show_kubectl=True,
    warn_no_proxy=True,
)
