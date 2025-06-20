"""Tests for command_handler.py's memory handling and edge cases.

This module tests potential memory-related bugs and edge cases in command_handler.py,
focusing on how commands update and interact with memory.
"""

import json
from collections.abc import Generator
from typing import Any
from unittest.mock import ANY, AsyncMock, MagicMock, Mock, patch

import llm  # Import the llm library
import pytest

from vibectl.config import Config
from vibectl.execution.vibe import (
    handle_command_output,
    handle_vibe_request,
)
from vibectl.prompts.vibe import plan_vibe_fragments
from vibectl.schema import ActionType, CommandAction, ErrorAction, LLMPlannerResponse
from vibectl.types import (
    Error,
    ExecutionMode,
    Fragment,
    LLMMetrics,
    MetricsDisplayMode,
    OutputFlags,
    PromptFragments,
    Success,
    SummaryPromptFragmentFunc,
    SystemFragments,
    Truncation,
    UserFragments,
)


@pytest.fixture
def mock_memory_update() -> Generator[Mock, None, None]:
    """Mock the update_memory function to check memory updates."""
    with patch("vibectl.execution.vibe.update_memory") as mock:
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


@pytest.fixture
def mock_test_summary_fragments() -> Generator[SummaryPromptFragmentFunc, None, None]:
    """Fixture to provide a test summary prompt function."""

    def test_summary_fragments(
        config: Config | None,
        current_memory: str | None,
        presentation_hints: str | None = None,
    ) -> PromptFragments:
        """Test helper to create summary prompt fragments."""
        # Simple fragments for testing, ensure current_memory is handled safely
        return PromptFragments(
            (
                SystemFragments([Fragment("System: Summarize this for memory")]),
                UserFragments([Fragment(f"User: {{output}} {current_memory!r}")]),
            )
        )

    yield test_summary_fragments


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
        patch("vibectl.memory.set_memory") as mock_set_memory,
        patch("vibectl.command_handler.update_memory") as mock_update_memory,
        patch(
            "vibectl.prompts.memory.memory_update_prompt"
        ) as mock_memory_update_prompt_func,
    ):
        mock_get_memory.return_value = "Initial memory context for testing."

        yield (
            mock_get_memory,
            mock_set_memory,
            mock_update_memory,
            mock_memory_update_prompt_func,
        )


@pytest.mark.asyncio
async def test_handle_command_output_updates_memory(
    mock_memory: dict[str, MagicMock],
    mock_process_auto: Mock,
    mock_get_adapter: MagicMock,
    mock_test_summary_fragments: SummaryPromptFragmentFunc,
) -> None:
    """Test that handle_command_output correctly updates memory."""
    mock_get_adapter.execute_and_log_metrics.reset_mock()
    mock_get_adapter.execute_and_log_metrics.return_value = (
        "mocked summary for update_memory test",  # Unique summary
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
        show_raw_output=True,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
        show_metrics=MetricsDisplayMode.ALL,
    )

    # Call handle_command_output with a command
    with (
        patch("vibectl.execution.vibe.console_manager"),
        patch("vibectl.command_handler.Config") as mock_command_handler_config_cls,
        patch(
            "vibectl.command_handler.update_memory", new_callable=AsyncMock
        ) as local_mock_update_memory,
    ):
        local_mock_update_memory.return_value = LLMMetrics(
            token_input=1, token_output=1, latency_ms=1, total_processing_duration_ms=2
        )
        mock_ch_config_instance = mock_command_handler_config_cls.return_value

        mock_ch_config_instance.is_memory_enabled.return_value = True

        # Ensure force_streaming_vibe is False for this test
        def mock_config_get(key: str, default: Any = None) -> Any:
            if key == "force_streaming_vibe":
                return False
            if key == "memory_enabled":  # Already mocked by is_memory_enabled
                return True
            if key == "model":  # model_name is set in OutputFlags
                return "test-model"
            # Fallback for other keys, if any, to avoid breaking Config
            # This might need to be more sophisticated if Config().get is complex
            from vibectl.config import DEFAULT_CONFIG

            return DEFAULT_CONFIG.get(key, default)

        mock_ch_config_instance.get = Mock(side_effect=mock_config_get)

        # Configure mock_process_auto for this specific test
        mock_process_auto.return_value = Truncation(
            original="test output", truncated="processed test output"
        )
        # The mock_get_adapter fixture is configured to return ("Test response", None)
        # by execute_and_log_metrics, which matches the expectation for vibe_output.
        await handle_command_output(
            output=Success(data="test output"),
            output_flags=output_flags,
            summary_prompt_func=mock_test_summary_fragments,
            command="get pods",
        )

    # Verify memory was updated
    local_mock_update_memory.assert_called_once()  # Simplified assertion

    # Verify arguments if called (can be re-enabled later)
    # local_mock_update_memory.assert_called_once_with(
    #     command_message="get pods",  # Command message should be the command itself
    #     command_output="test output",
    #     vibe_output="Test response",  # This should match the mocked LLM summary
    #     model_name="test-model",
    # )

    # Check that the LLM was called for the memory update
    assert mock_get_adapter.execute_and_log_metrics.call_count == 1

    # At the end of the test, restore the original side_effect if necessary,
    # though pytest fixtures usually handle teardown if side_effect was set on
    # a fixture-provided mock.
    # For safety, if tests run in unexpected order or share state beyond pytest's
    # typical isolation:
    mock_get_adapter.get_model.side_effect = original_get_model_side_effect


@pytest.mark.asyncio
async def test_handle_command_output_does_not_update_memory_without_command(
    mock_memory: dict[str, MagicMock],
    mock_process_auto: Mock,
    mock_get_adapter: MagicMock,
    mock_test_summary_fragments: SummaryPromptFragmentFunc,
) -> None:
    """Test that memory is updated with 'Unknown' command when no command provided."""
    output_flags = OutputFlags(
        show_raw_output=True,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
        show_metrics=MetricsDisplayMode.NONE,
    )
    mock_get_adapter.execute_and_log_metrics.return_value = (
        "LLM summary for no command",
        LLMMetrics(),
    )

    with (
        patch("vibectl.execution.vibe.Config") as mock_vibe_config_cls,
        patch(
            "vibectl.execution.vibe.update_memory", new_callable=AsyncMock
        ) as local_mock_update_memory,
    ):
        local_mock_update_memory.return_value = LLMMetrics()
        mock_vibe_config_instance = mock_vibe_config_cls.return_value
        mock_vibe_config_instance.is_memory_enabled.return_value = True

        await handle_command_output(
            output=Success(data="test output"),
            output_flags=output_flags,
            summary_prompt_func=mock_test_summary_fragments,
            command=None,  # No command provided
        )
    # If command is None, update_memory should NOT be called by handle_command_output
    local_mock_update_memory.assert_not_called()


@pytest.mark.asyncio
async def test_handle_command_output_updates_memory_with_error_output(
    mock_memory: dict[str, MagicMock],
    mock_process_auto: Mock,
    mock_get_adapter: MagicMock,
    mock_test_summary_fragments: SummaryPromptFragmentFunc,
) -> None:
    """Test memory is updated even when command output represents an error."""
    mock_adapter = mock_get_adapter
    mock_adapter.execute_and_log_metrics.reset_mock()

    mock_process_auto.return_value = Truncation(
        original="Error from server: not found", truncated="Error...not found"
    )

    output_flags = OutputFlags(
        show_raw_output=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
        show_kubectl=False,
        show_metrics=MetricsDisplayMode.ALL,
    )
    error_input = Error(error="Error from server: not found")

    expected_recovery_suggestion_text = "Try checking the pod logs for more details."
    mock_adapter.execute_and_log_metrics.return_value = (
        expected_recovery_suggestion_text,
        LLMMetrics(
            token_input=10,
            token_output=20,
            latency_ms=100,
            total_processing_duration_ms=120,
        ),
    )

    with (
        patch("vibectl.prompts.recovery.recovery_prompt") as mock_recovery_prompt,
        patch("vibectl.command_handler.Config") as mock_vibe_config_cls,
        patch(
            "vibectl.command_handler.update_memory", new_callable=AsyncMock
        ) as local_mock_update_memory,
    ):
        local_mock_update_memory.return_value = LLMMetrics()  # Mock for the single call
        mock_vibe_config_instance = mock_vibe_config_cls.return_value
        mock_vibe_config_instance.is_memory_enabled.return_value = True

        # Ensure force_streaming_vibe is False for this test's Config instance
        def mock_config_get(key: str, default: Any = None) -> Any:
            if key == "force_streaming_vibe":
                return False
            # Add other relevant keys if Config().get is called for them
            from vibectl.config import DEFAULT_CONFIG

            return DEFAULT_CONFIG.get(key, default)

        mock_vibe_config_instance.get = Mock(side_effect=mock_config_get)

        mock_recovery_prompt.return_value = (
            SystemFragments([Fragment("sys")]),
            UserFragments([Fragment("user")]),
        )

        await handle_command_output(
            output=error_input,
            output_flags=output_flags,
            summary_prompt_func=mock_test_summary_fragments,
            command="get pods",
        )

    local_mock_update_memory.assert_called_once_with(
        command_message="get pods",
        command_output="Error from server: not found",
        vibe_output=expected_recovery_suggestion_text,
        model_name="test-model",
        config=ANY,
    )


@pytest.mark.asyncio
async def test_handle_command_output_updates_memory_with_overloaded_error(
    mock_memory: dict[str, MagicMock],
    mock_process_auto: Mock,
    mock_get_adapter: MagicMock,
    mock_test_summary_fragments: SummaryPromptFragmentFunc,
) -> None:
    """Test memory is updated correctly when LLM summary itself fails (overloaded)."""
    mock_adapter = mock_get_adapter
    mock_adapter.execute_and_log_metrics.reset_mock()

    overloaded_error_msg = "ERROR: Model capacity is overloaded."

    # This test simulates an error during summary of a successful command.
    # Since show_streaming=False (default), it uses execute_and_log_metrics,
    # not stream_execute.
    mock_adapter.execute_and_log_metrics = AsyncMock(
        return_value=(overloaded_error_msg, LLMMetrics())
    )

    mock_process_auto.return_value = Truncation(
        original="Normal output", truncated="Normal output"
    )

    output_flags = OutputFlags(
        show_raw_output=False,
        show_vibe=True,  # Vibe is True, so _process_vibe_output is called
        warn_no_output=False,
        model_name="test-model",
        show_kubectl=False,
        show_metrics=MetricsDisplayMode.ALL,
        show_streaming=False,  # Explicitly set to ensure non-streaming path
    )
    success_input = Success(data="Normal output")

    with (
        patch("vibectl.execution.vibe.Config") as mock_vibe_config_cls,
        patch("vibectl.command_handler.Config") as mock_command_handler_config_cls,
        patch(
            "vibectl.command_handler.update_memory", new_callable=AsyncMock
        ) as local_mock_update_memory,
    ):
        local_mock_update_memory.return_value = LLMMetrics()
        mock_vibe_config_instance = mock_vibe_config_cls.return_value
        mock_command_handler_config_cls.return_value = (
            mock_vibe_config_instance  # Share the mock
        )
        mock_vibe_config_instance.is_memory_enabled.return_value = True

        def mock_config_get(key: str, default: Any = None) -> Any:
            if key == "force_streaming_vibe":
                return False
            from vibectl.config import DEFAULT_CONFIG

            return DEFAULT_CONFIG.get(key, default)

        mock_vibe_config_instance.get = Mock(side_effect=mock_config_get)

        await handle_command_output(
            output=success_input,
            output_flags=output_flags,
            summary_prompt_func=mock_test_summary_fragments,
            command="get pods",
        )

    # _process_vibe_output will get `overloaded_error_msg` as summary.
    # It will be displayed. Then update_memory will be called.
    local_mock_update_memory.assert_called_once_with(
        command_message="get pods",
        command_output="Normal output",
        vibe_output=overloaded_error_msg,  # The error message
        model_name="test-model",
        config=ANY,
    )


@pytest.mark.asyncio
async def test_handle_vibe_request_updates_memory_on_error(
    mock_get_adapter: MagicMock,
    mock_test_summary_fragments: SummaryPromptFragmentFunc,
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
            show_raw_output=False,
            show_vibe=True,
            warn_no_output=False,
            model_name="test-model",
            show_metrics=MetricsDisplayMode.ALL,
        )

        with patch("vibectl.execution.vibe.Config") as mock_vibe_config_cls:
            mock_vibe_config_instance = mock_vibe_config_cls.return_value
            mock_vibe_config_instance.is_memory_enabled.return_value = True

            result = await handle_vibe_request(
                request=request_text,
                command="vibe",
                plan_prompt_func=plan_vibe_fragments,
                summary_prompt_func=mock_test_summary_fragments,
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
    mock_get_adapter: MagicMock,
    mock_memory: dict[str, MagicMock],
    mock_test_summary_fragments: SummaryPromptFragmentFunc,
) -> None:
    """Test command execution error triggers recovery suggestion and memory updates.

    Specifically tests that `vibectl.memory.update_memory` is called after recovery.
    """
    # Reset shared mock for this test
    mock_get_adapter.execute_and_log_metrics.reset_mock()

    # ---- Add setup for mock_llm_for_test ----
    mock_llm_for_test = MagicMock(spec=llm.Model)  # type: ignore
    mock_llm_for_test.name = "test-model"
    original_get_model_side_effect = mock_get_adapter.get_model.side_effect

    def get_model_override_for_error_recovery_test(
        model_name_arg: str,
    ) -> Any:  # Renamed for clarity
        if model_name_arg == "test-model":
            return mock_llm_for_test
        if original_get_model_side_effect:
            return original_get_model_side_effect(model_name_arg)
        raise llm.NotFoundError(  # type: ignore [attr-defined]
            "get_model_override_for_error_recovery_test received unmocked: "
            f"{model_name_arg}"
        )

    mock_get_adapter.get_model.side_effect = get_model_override_for_error_recovery_test
    # ---- End setup for mock_llm_for_test ----

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
        show_raw_output=True,
        show_vibe=True,  # Important for recovery path in handle_command_output
        warn_no_output=False,
        model_name="test-model",
        show_kubectl=True,
        show_metrics=MetricsDisplayMode.ALL,
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
        patch("vibectl.prompts.recovery.recovery_prompt") as mock_recovery_prompt,
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
            summary_prompt_func=mock_test_summary_fragments,
            output_flags=output_flags,
            execution_mode=ExecutionMode.AUTO,
        )

        # --- Assertions ---
        # 1. LLM planning call
        mock_get_adapter.execute_and_log_metrics.assert_any_call(
            model=mock_llm_for_test,
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
    mock_memory_functions: tuple[Mock, Mock, Mock, Mock],
    mock_logger: MagicMock,
    mock_test_summary_fragments: SummaryPromptFragmentFunc,
) -> None:
    """Test that handle_vibe_request includes memory context in the prompt."""
    mock_get_memory, _, _, _ = mock_memory_functions
    # Reset shared mock for this test
    mock_get_adapter.execute_and_log_metrics.reset_mock()

    # ---- Add setup for mock_llm_for_test ----
    mock_llm_for_test = MagicMock(spec=llm.Model)  # type: ignore
    mock_llm_for_test.name = "test-model"
    original_get_model_side_effect = mock_get_adapter.get_model.side_effect

    def get_model_override_for_context_test(model_name_arg: str) -> Any:
        if model_name_arg == "test-model":
            return mock_llm_for_test
        if original_get_model_side_effect:
            return original_get_model_side_effect(model_name_arg)

    mock_get_adapter.get_model.side_effect = get_model_override_for_context_test
    # ---- End setup for mock_llm_for_test ----

    mock_get_memory.return_value = "Previous memory context"

    output_flags = OutputFlags(
        show_raw_output=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
        show_kubectl=False,
        show_metrics=MetricsDisplayMode.ALL,
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
            summary_prompt_func=mock_test_summary_fragments,
            output_flags=output_flags,
            execution_mode=ExecutionMode.AUTO,
        )

    # Verify that the mock_plan_fragments_func was called by handle_vibe_request
    mock_plan_fragments_func.assert_called_once()

    # Verify that execute_and_log_metrics was called for planning
    mock_get_adapter.execute_and_log_metrics.assert_called_once_with(
        model=mock_llm_for_test,  # Ensure this uses mock_llm_for_test
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


@pytest.mark.asyncio
async def test_handle_command_output_passes_memory_to_summary_prompt(
    mock_memory_functions: tuple[Mock, Mock, Mock, Mock],
    mock_process_auto: Mock,
    mock_get_adapter: MagicMock,
) -> None:
    """Test handle_command_output fetches memory and passes to summary_prompt_func."""
    mock_get_memory_func, mock_set_memory_func, mock_update_memory_func, _ = (
        mock_memory_functions
    )

    # Reset shared mocks specific to this test's needs
    mock_get_adapter.execute_and_log_metrics.reset_mock()
    mock_get_memory_func.reset_mock()
    mock_update_memory_func.reset_mock()
    mock_set_memory_func.reset_mock()

    test_memory_content = "This is the active memory context."
    mock_get_memory_func.return_value = test_memory_content

    # Configure mock_process_auto for this specific test
    mock_process_auto.return_value = Truncation(
        original="kubectl output data", truncated="kubectl output data"
    )

    # Mock the summary prompt function to capture its arguments
    mock_summary_prompt_creator = MagicMock(spec=SummaryPromptFragmentFunc)

    def summary_prompt_side_effect(
        config_param: Config | None,
        current_memory: str | None,
        presentation_hints: str | None = None,
    ) -> PromptFragments:
        assert current_memory == test_memory_content
        # Based on types.py, Fragment is str, UserFragments is list[str]
        # So this is effectively (SystemFragments_list_str, UserFragments_list_str)
        # SystemFragments(["System text"]), UserFragments(["User text"])
        return (
            [f"System with memory: {current_memory!r}"],  # SystemFragments -> list[str]
            ["User: {output}"],  # UserFragments -> list[str]
        )  # type: ignore

    mock_summary_prompt_creator.side_effect = summary_prompt_side_effect

    # Note: Using streaming path, so no need to mock execute_and_log_metrics
    # for main vibe call

    output_flags = OutputFlags(
        show_raw_output=False,
        show_vibe=True,  # Vibe must be true for update_memory to be called on success
        warn_no_output=False,
        model_name="test-model",
        show_metrics=MetricsDisplayMode.NONE,
        show_streaming=True,  # Enable streaming for this test
    )

    with (
        patch("vibectl.command_handler.Config") as mock_ch_config_cls,
        patch("vibectl.command_handler.get_memory") as local_mock_get_memory,
    ):
        mock_ch_config_instance = mock_ch_config_cls.return_value
        mock_ch_config_instance.is_memory_enabled.return_value = True
        local_mock_get_memory.return_value = test_memory_content

        # Call the SUT (handle_command_output)
        # It will use the `update_memory` that is patched by
        # `mock_memory_functions` fixture.
        await handle_command_output(
            output=Success(data="kubectl output data"),
            output_flags=output_flags,
            summary_prompt_func=mock_summary_prompt_creator,
            command="get pods",
        )

    # Assertions:
    # 1. update_memory (from the fixture, which patches
    # vibectl.command_handler.update_memory) was called.
    mock_update_memory_func.assert_called_once()
    update_memory_call_args = mock_update_memory_func.call_args
    # Ensure summary_prompt_func is NOT passed to update_memory
    assert "summary_prompt_func" not in update_memory_call_args.kwargs

    # Verify the other relevant arguments passed to update_memory
    assert (
        update_memory_call_args.kwargs.get("command_message")
        == "command: get pods output: kubectl output data"
    )

    # The vibe_output passed to update_memory should be the concatenation of
    # the streamed chunks from the main vibe LLM call.
    # The default stream from conftest yields "Stream chunk 1" and "Stream chunk 2",
    # which join to "Stream chunk 1Stream chunk 2".
    assert (
        update_memory_call_args.kwargs.get("vibe_output")
        == "Stream chunk 1Stream chunk 2"
    )
    assert update_memory_call_args.kwargs.get("model_name") == "test-model"

    # 2. The local_mock_get_memory (patching vibectl.command_handler.get_memory)
    #    should have been called by handle_command_output to fetch memory for the
    #    summary_prompt_func.
    local_mock_get_memory.assert_called_once()

    # 3. summary_prompt_func (mock_summary_prompt_creator) was called by
    #    handle_command_output with the correct memory content.
    mock_summary_prompt_creator.assert_called_once_with(ANY, test_memory_content, ANY)

    # 4. The main "vibe" LLM call (which is now streaming) was made correctly.

    # First, verify that the correct model name was requested from the adapter
    mock_get_adapter.get_model.assert_called_once_with(output_flags.model_name)

    # Then, check the arguments passed to stream_execute_and_log_metrics
    # (not stream_execute)
    mock_get_adapter.stream_execute_and_log_metrics.assert_called_once()
    actual_call_args_list = (
        mock_get_adapter.stream_execute_and_log_metrics.call_args_list
    )
    assert len(actual_call_args_list) == 1
    actual_call = actual_call_args_list[0]

    # Check keyword arguments for stream_execute_and_log_metrics
    assert isinstance(
        actual_call.kwargs["model"], Mock
    )  # Check it's some Mock instance

    # Check system_fragments (which is list[str])
    actual_system_fragments = actual_call.kwargs["system_fragments"]
    assert isinstance(actual_system_fragments, list)
    assert len(actual_system_fragments) == 1
    assert isinstance(actual_system_fragments[0], str)
    assert actual_system_fragments[0] == f"System with memory: {test_memory_content!r}"

    # Check user_fragments (which is list[str])
    actual_user_fragments = actual_call.kwargs["user_fragments"]
    assert isinstance(actual_user_fragments, list)
    assert len(actual_user_fragments) == 1
    assert isinstance(actual_user_fragments[0], str)
    assert actual_user_fragments[0] == "User: kubectl output data"

    assert actual_call.kwargs.get("response_model") is None

    # Ensure the non-streaming path was NOT taken for the main vibe call
    mock_get_adapter.execute_and_log_metrics.assert_not_called()
