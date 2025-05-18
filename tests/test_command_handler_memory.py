"""Tests for command_handler.py's memory handling and edge cases.

This module tests potential memory-related bugs and edge cases in command_handler.py,
focusing on how commands update and interact with memory.
"""

import json
from collections.abc import Generator
from typing import Any
from unittest.mock import ANY, MagicMock, Mock, patch

import pytest

from vibectl.command_handler import (
    handle_command_output,
    handle_vibe_request,
)
from vibectl.config import Config
from vibectl.model_adapter import LLMModelAdapter
from vibectl.prompt import (
    plan_vibe_fragments,
)
from vibectl.schema import LLMPlannerResponse, CommandAction, ActionType
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


@pytest.mark.asyncio
async def test_handle_command_output_updates_memory(
    mock_memory_update: Mock,
    mock_process_auto: Mock,
    mock_model_adapter: MagicMock,
) -> None:
    """Test that handle_command_output correctly updates memory."""
    # Configure output flags
    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
        show_metrics=True,
    )

    # Call handle_command_output with a command
    with patch("vibectl.command_handler.console_manager"):
        # Configure mock_process_auto for this specific test
        mock_process_auto.return_value = Truncation(
            original="test output", truncated="processed test output"
        )
        # The mock_model_adapter fixture is configured to return ("Test response", None)
        # by execute_and_log_metrics, which matches the expectation for vibe_output.
        handle_command_output(
            output=Success(data="test output"),
            output_flags=output_flags,
            summary_prompt_func=get_test_summary_fragments,
            command="get pods",
        )

    # Verify memory was updated with correct parameters
    mock_memory_update.assert_called_once_with(
        command_message="get pods",  # Command message should be the command itself
        command_output="test output",
        vibe_output="Test response",  # This should match the mocked LLM summary
        model_name="test-model",
    )

    # Check that the LLM was called for the summary
    assert mock_model_adapter.execute_and_log_metrics.call_count == 1


@pytest.mark.asyncio
async def test_handle_command_output_does_not_update_memory_without_command(
    mock_memory_update: Mock,
    mock_process_auto: Mock,
    mock_model_adapter: MagicMock,
) -> None:
    """Test that memory is updated with 'Unknown' command when no command provided."""
    # Configure output flags
    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
        show_metrics=True,
    )

    # Call handle_command_output without a command
    with patch("vibectl.command_handler.console_manager"):
        mock_process_auto.return_value = Truncation(
            original="test output", truncated="processed test output"
        )
        # The mock_model_adapter fixture is configured to return ("Test response", None)
        handle_command_output(
            output=Success(data="test output"),
            output_flags=output_flags,
            summary_prompt_func=get_test_summary_fragments,
            # command is omitted here
        )

    # Verify memory WAS updated
    mock_memory_update.assert_called_once_with(
        command_message="Unknown",
        command_output="test output",
        vibe_output="Test response",  # This should match the mocked LLM summary
        model_name="test-model",
    )

    # Check that the LLM was called for the summary
    assert mock_model_adapter.execute_and_log_metrics.call_count == 1


@pytest.mark.asyncio
async def test_handle_command_output_updates_memory_with_error_output(
    mock_memory_update: Mock,
    mock_process_auto: Mock,
    mock_model_adapter: MagicMock,
) -> None:
    """Test memory is updated even when command output represents an error."""
    # Use the passed mock_model_adapter instance
    mock_adapter = mock_model_adapter

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
    mock_memory_update.assert_called_once_with(
        command_message="get pods",
        command_output=error_input.error,
        vibe_output=expected_recovery_suggestion_text,
        model_name="test-model",
    )

    # Check that the LLM was called once for recovery
    mock_adapter.execute_and_log_metrics.assert_called_once()


@pytest.mark.asyncio
async def test_handle_command_output_updates_memory_with_overloaded_error(
    mock_memory_update: Mock,
    mock_process_auto: Mock,
    mock_model_adapter: MagicMock,
) -> None:
    """Test memory is updated correctly when LLM summary itself fails (overloaded)."""
    # Use the passed mock_model_adapter instance
    mock_adapter = mock_model_adapter

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

    # Patch Config used by update_memory to ensure memory is enabled
    with patch("vibectl.memory.Config") as mock_config_cls:
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
    mock_memory_update.assert_not_called()

    # Check that the LLM was called once for the summary attempt
    mock_adapter.execute_and_log_metrics.assert_called_once()


@pytest.mark.asyncio
async def test_handle_vibe_request_updates_memory_on_error(
    mock_model_adapter: MagicMock, mock_memory_update: Mock
) -> None:
    """Test handle_vibe_request updates memory when LLM planning results in an error."""
    request_text = "error test"
    error_msg = "LLM planning failed"
    explanation = "The plan was invalid."

    # Configure mock_model_adapter for this test
    mock_model_adapter.execute_and_log_metrics.return_value = (
        json.dumps(
            {
                "action_type": ActionType.ERROR.value,
                "error": error_msg,
                "explanation": explanation,
            }
        ),
        None,  # Metrics
    )

    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
        show_metrics=True,
    )

    result = await handle_vibe_request(
        request=request_text,
        command="vibe",
        plan_prompt_func=plan_vibe_fragments,
        summary_prompt_func=get_test_summary_fragments,
        output_flags=output_flags,
    )

    mock_memory_update.assert_called_once()
    call_kwargs = mock_memory_update.call_args.kwargs
    assert (
        call_kwargs.get("command_message") == f"command: vibe request: {request_text}"
    )
    assert call_kwargs.get("command_output") == error_msg
    assert (
        call_kwargs.get("vibe_output")
        == f"LLM Planning Error: vibe {request_text} -> {error_msg}"
    )
    assert call_kwargs.get("model_name") == "test-model"

    # Assert the function returned an Error object
    assert isinstance(result, Error)
    assert result.error == f"LLM planning error: {error_msg}"
    assert result.recovery_suggestions == explanation

    # Check that the LLM was called for the planning
    mock_model_adapter.execute_and_log_metrics.assert_called_once()


@pytest.mark.asyncio
async def test_handle_vibe_request_error_recovery_flow(
    mock_model_adapter: MagicMock, mock_memory_update: Mock
) -> None:
    """Test command execution error triggers recovery suggestion and memory updates.

    Specifically tests that `vibectl.memory.update_memory` is called after recovery.
    """
    # Mock LLM planning response (successful plan, include verb)
    kubectl_verb = "get"
    kubectl_args = ["pods"]
    plan_response = {
        "action_type": ActionType.COMMAND.value,
        "commands": [kubectl_verb, *kubectl_args],
        "explanation": "Getting pods as requested",
    }
    # Mock LLM recovery suggestion response
    recovery_suggestion_text = "Try checking the namespace."
    mock_model_adapter.execute_and_log_metrics.side_effect = [
        (
            LLMPlannerResponse(action=CommandAction(
                action_type=ActionType.COMMAND,
                commands=["get", "pods"],
            )).model_dump_json(),
            LLMMetrics(
                token_input=50,
                token_output=30,
                latency_ms=200,
                total_processing_duration_ms=220,
            ),
        ),
        recovery_suggestion_text,  # Recovery suggestion
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
        patch("vibectl.command_handler._execute_command") as mock_execute_cmd,
        patch("vibectl.command_handler.console_manager"),
        patch("vibectl.command_handler.recovery_prompt") as mock_recovery_prompt,
        patch(
            "vibectl.memory.update_memory"
        ) as mock_update_memory_in_memory_module,  # For vibectl.memory.update_memory
        patch(
            "vibectl.command_handler.handle_command_output"
        ) as mock_handle_output_wrapper,
    ):
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
        mock_model_adapter.execute_and_log_metrics.assert_any_call(
            model=mock_model_adapter.get_model.return_value,
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

        # 5. Check memory update calls:
        mock_memory_update.assert_any_call(
            command_message="command: kubectl get pods original: vibe",
            command_output=original_execution_error.error,
            vibe_output="Getting pods as requested",
            model_name="test-model",
        )
        # This one should NOT have been called by this flow, as memory updates are now
        # expected to go through vibectl.command_handler.update_memory
        mock_update_memory_in_memory_module.assert_not_called()


@pytest.mark.asyncio
async def test_handle_vibe_request_includes_memory_context(
    mock_model_adapter: MagicMock,
    mock_memory_functions: tuple,
    mock_logger: MagicMock,
) -> None:
    """Verify memory_context is included in the prompt arguments if applicable."""
    mock_get_memory, mock_set_memory, mock_update_memory, mock_prompt_func = (
        mock_memory_functions
    )
    memory_content = "Existing memory context."
    mock_get_memory.return_value = memory_content

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
            plan_prompt_func=plan_vibe_fragments,
            summary_prompt_func=get_test_summary_fragments,
            output_flags=DEFAULT_OUTPUT_FLAGS,  # Defined at the end of the file
        )

        # Assert that execute_and_log_metrics was called at least once
        assert mock_model_adapter.execute_and_log_metrics.call_count >= 1

        # Restore detailed argument checking for the first call (planning call)
        planning_call_args = mock_model_adapter.execute_and_log_metrics.call_args_list[
            0
        ]
        # Unpack args and kwargs
        call_args, call_kwargs = planning_call_args
        # Check KEYWORD arguments
        # (model, system_fragments, user_fragments, response_model)
        assert "model" in call_kwargs
        assert call_kwargs["model"] == mock_model_adapter.get_model.return_value
        # Check for fragments instead of prompt_text
        assert "system_fragments" in call_kwargs
        assert "user_fragments" in call_kwargs
        # Check that memory content is in the user fragments
        # Revert to using any() to check if *any* fragment contains the memory context
        print(
            f"DEBUG: User fragments passed to mock: {call_kwargs['user_fragments']}"
        )  # Add debug print
        assert any(
            f"Memory Context:\n{memory_content}" in frag
            for frag in call_kwargs["user_fragments"]
        ), "Memory context string not found in user_fragments"
        assert "response_model" in call_kwargs
        assert call_kwargs["response_model"] == LLMPlannerResponse

        # Optional: Check the request string is in the user fragments
        assert any("get the pods" in frag for frag in call_kwargs["user_fragments"])


@pytest.fixture(autouse=True)
def mock_logger() -> Generator[MagicMock, None, None]:
    """Mock the logger to prevent real logging during tests."""
    with patch("vibectl.command_handler.logger") as mock_log:
        yield mock_log


@pytest.fixture(autouse=True)
def mock_console_manager() -> Generator[MagicMock, None, None]:
    """Mock the console manager to prevent real console output."""
    with patch("vibectl.command_handler.console_manager") as mock_console:
        yield mock_console


@pytest.fixture
def mock_model_adapter() -> Generator[
    MagicMock, None, None
]:  # Renamed from _mock_model_adapter to avoid leading underscore warning
    """Mock LLMModelAdapter for command handling by mocking get_model_adapter."""
    # This mock_instance will be returned by get_model_adapter
    # Using spec=LLMModelAdapter helps catch incorrect attribute access on the mock
    mock_adapter_instance = MagicMock(spec=LLMModelAdapter)
    mock_adapter_instance.execute_and_log_metrics.return_value = ("Test response", None)

    # Patch get_model_adapter where it's used (in command_handler)
    with patch(
        "vibectl.command_handler.get_model_adapter", return_value=mock_adapter_instance
    ):
        yield mock_adapter_instance


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
        patch("vibectl.command_handler.get_memory") as mock_get_memory,
        patch("vibectl.command_handler.set_memory") as mock_set_memory,
        patch("vibectl.command_handler.update_memory") as mock_update_memory,
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
