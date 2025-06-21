"""Tests for vibe request handling functionality."""

import json
from collections.abc import Generator
from pathlib import Path
from typing import Any, NoReturn
from unittest.mock import (
    ANY,
    AsyncMock,
    MagicMock,
    Mock,
    patch,
)

import llm
import pytest
from pydantic import ValidationError

from vibectl.cli import cli
from vibectl.config import Config
from vibectl.execution.vibe import OutputFlags, _get_llm_plan, handle_vibe_request
from vibectl.memory import (
    update_memory as real_update_memory_impl,
)
from vibectl.model_adapter import (
    LLMMetrics,
    LLMModelAdapter,
    RecoverableApiError,
)
from vibectl.prompts.vibe import plan_vibe_fragments
from vibectl.schema import (
    CommandAction,
    ErrorAction,
    FeedbackAction,
    LLMPlannerResponse,
    WaitAction,
)
from vibectl.types import (
    ActionType,
    Error,
    ExecutionMode,
    Fragment,
    MetricsDisplayMode,
    PromptFragments,
    Result,
    Success,
    SystemFragments,
    UserFragments,
)


def get_test_summary_fragments(
    config: Config | None = None,
    current_memory: str | None = None,
    presentation_hints: str | None = None,
) -> PromptFragments:
    """Dummy summary prompt function for testing that returns fragments."""
    return PromptFragments(
        (
            SystemFragments([Fragment("System fragment with {output}")]),
            UserFragments([Fragment("User fragment with {output}")]),
        )
    )


@pytest.fixture
def mock_confirm() -> Generator[MagicMock, None, None]:
    """Mock click.confirm function."""
    with patch("click.confirm") as mock:
        mock.return_value = True  # Default to confirming actions
        yield mock


@pytest.fixture
def mock_prompt() -> Generator[MagicMock, None, None]:
    """Mock click.prompt function."""
    with patch("click.prompt") as mock:
        yield mock


@pytest.fixture
def default_output_flags(
    mock_config: MagicMock,
) -> OutputFlags:  # Ensure mock_config is used
    return OutputFlags(
        show_raw_output=False,
        show_vibe=True,  # Changed to True
        warn_no_output=True,
        model_name="test-model",
        show_metrics=MetricsDisplayMode.ALL,
        show_kubectl=True,  # Changed to True for more comprehensive testing
        warn_no_proxy=True,
    )


@pytest.fixture
def mock_get_adapter() -> Generator[MagicMock, None, None]:
    """Mocks get_model_adapter in execution.vibe, command_handler, memory modules."""
    adapter_instance = MagicMock(spec=LLMModelAdapter)
    mock_llm_model_instance = MagicMock(spec=llm.Model)  # type: ignore
    mock_llm_model_instance.name = "test-model"

    def get_model_side_effect(model_name_arg: str) -> MagicMock:
        return mock_llm_model_instance

    adapter_instance.get_model.side_effect = get_model_side_effect

    default_planning_response = LLMPlannerResponse(
        action=CommandAction(action_type=ActionType.COMMAND, commands=["get", "pods"])
    ).model_dump_json()
    adapter_instance.execute_and_log_metrics.return_value = (
        default_planning_response,
        LLMMetrics(1, 1, 1, 1),
    )

    with (
        patch(
            "vibectl.execution.vibe.get_model_adapter", return_value=adapter_instance
        ),
        patch(
            "vibectl.command_handler.get_model_adapter", return_value=adapter_instance
        ),
        patch("vibectl.memory.get_model_adapter", return_value=adapter_instance),
        patch("vibectl.model_adapter.get_model_adapter", return_value=adapter_instance),
    ):
        yield adapter_instance


@pytest.fixture
def mock_console() -> Generator[
    MagicMock, None, None
]:  # Changed from Mock to MagicMock for richer API
    """Mock console_manager to prevent real console output."""
    with (
        patch("vibectl.execution.vibe.console_manager") as mock_vibe_console,
        patch("vibectl.command_handler.console_manager", new=mock_vibe_console),
    ):
        # Ensure both patches use the same mock object for consistent assertion
        yield mock_vibe_console


@pytest.mark.asyncio
async def test_handle_vibe_request_success(
    mock_get_adapter: MagicMock,
    mock_console: Mock,
    prevent_exit: MagicMock,
    default_output_flags: OutputFlags,
    mock_memory: MagicMock,
) -> None:
    """Test basic successful vibe request execution."""
    # Mock the LLM planning response
    command_action = CommandAction(
        action_type=ActionType.COMMAND, commands=["get", "pods"]
    )
    llm_response_str = LLMPlannerResponse(action=command_action).model_dump_json()
    mock_get_adapter.execute_and_log_metrics.return_value = (llm_response_str, None)

    with patch("vibectl.execution.vibe._confirm_and_execute_plan") as mock_confirm_exec:
        mock_confirm_exec.return_value = Success(data="kubectl command output")

        result = await handle_vibe_request(
            request="get pods",
            command="get",
            plan_prompt_func=plan_vibe_fragments,
            summary_prompt_func=get_test_summary_fragments,
            output_flags=default_output_flags,
            execution_mode=ExecutionMode.AUTO,
        )

    assert isinstance(result, Success)
    assert result.data == "kubectl command output"  # Check data from mock_confirm_exec
    mock_confirm_exec.assert_called_once()


@pytest.mark.asyncio
async def test_handle_vibe_request_command_execution(
    mock_get_adapter: MagicMock,
    mock_console: Mock,
    prevent_exit: MagicMock,
    default_output_flags: OutputFlags,
    mock_memory: MagicMock,
) -> None:
    """Test vibe request where a command is executed."""
    command_to_execute = ["version"]
    command_action = CommandAction(
        action_type=ActionType.COMMAND, commands=command_to_execute
    )
    llm_response_str = LLMPlannerResponse(action=command_action).model_dump_json()
    mock_get_adapter.execute_and_log_metrics.return_value = (llm_response_str, None)

    with patch("vibectl.execution.vibe._execute_command") as mock_execute_cmd:
        mock_execute_cmd.return_value = Success(data="clientVersion: v1.2.3")
        # Mock update_memory for this scope if its calls are asserted
        with patch("vibectl.execution.vibe.update_memory"):
            await handle_vibe_request(
                request="show k8s version",
                command="version",  # Corresponds to the command in CommandAction
                plan_prompt_func=plan_vibe_fragments,
                summary_prompt_func=get_test_summary_fragments,
                output_flags=default_output_flags,
                execution_mode=ExecutionMode.AUTO,
            )
            mock_execute_cmd.assert_called_once_with(
                "version", command_to_execute, None, allowed_exit_codes=(0,)
            )


@pytest.mark.asyncio
async def test_handle_vibe_request_yaml_execution(
    mock_get_adapter: MagicMock,
    mock_console: Mock,
    mock_prompt: MagicMock,  # For apply confirmation
    prevent_exit: MagicMock,
    default_output_flags: OutputFlags,
    mock_memory: MagicMock,
) -> None:
    """Test vibe request with a command involving YAML (e.g., apply -f -)."""
    yaml_manifest_content = "apiVersion: v1\nkind: Pod\nmetadata:\n  name: test-pod"
    command_action = CommandAction(
        action_type=ActionType.COMMAND,
        commands=["-f", "-"],
        yaml_manifest=yaml_manifest_content,
    )
    llm_response_str = LLMPlannerResponse(action=command_action).model_dump_json()
    mock_get_adapter.execute_and_log_metrics.return_value = (llm_response_str, None)
    mock_prompt.return_value = "y"  # Confirm apply

    with patch("vibectl.execution.vibe._execute_command") as mock_execute_cmd:
        mock_execute_cmd.return_value = Success(data="pod/test-pod created")
        await handle_vibe_request(
            request="apply this config from yaml",
            command="apply",
            plan_prompt_func=plan_vibe_fragments,
            summary_prompt_func=get_test_summary_fragments,
            output_flags=default_output_flags,
            execution_mode=ExecutionMode.AUTO,
        )
        mock_execute_cmd.assert_called_once_with(
            "apply", ["-f", "-"], yaml_manifest_content, allowed_exit_codes=(0,)
        )
        # In ExecutionMode.AUTO, confirmation prompts are bypassed, so no prompt
        # should be shown.
        mock_prompt.assert_not_called()


@pytest.mark.asyncio
async def test_handle_vibe_request_llm_planning_error(
    mock_get_adapter: MagicMock,
    mock_console: Mock,
    prevent_exit: MagicMock,
    default_output_flags: OutputFlags,
    mock_memory: MagicMock,
) -> None:
    """Test handling of a direct error from the LLM during planning."""
    # Simulate an error during the execute_and_log_metrics call for planning
    llm_api_error_message = "LLM API connection timed out"
    mock_get_adapter.execute_and_log_metrics.side_effect = RuntimeError(
        llm_api_error_message
    )

    result = await handle_vibe_request(
        request="get pods",
        command="get",
        plan_prompt_func=plan_vibe_fragments,
        summary_prompt_func=get_test_summary_fragments,
        output_flags=default_output_flags,
        execution_mode=ExecutionMode.AUTO,
    )
    assert isinstance(result, Error)
    assert llm_api_error_message in result.error
    assert result.exception is not None
    assert isinstance(result.exception, RuntimeError)


@pytest.mark.asyncio
async def test_handle_vibe_request_llm_wait(
    mock_get_adapter: MagicMock,
    mock_console: Mock,
    prevent_exit: MagicMock,
    default_output_flags: OutputFlags,
    mock_memory: MagicMock,
) -> None:
    """Test handling of a WAIT action from the LLM."""
    wait_duration = 5
    wait_action = WaitAction(
        action_type=ActionType.WAIT, duration_seconds=wait_duration
    )
    llm_response_str = LLMPlannerResponse(action=wait_action).model_dump_json()
    mock_get_adapter.execute_and_log_metrics.return_value = (llm_response_str, None)

    with patch("asyncio.sleep") as mock_async_sleep:
        result = await handle_vibe_request(
            request="wait for 5 seconds",
            command="wait",  # Or any command, LLM dictates wait
            plan_prompt_func=plan_vibe_fragments,
            summary_prompt_func=get_test_summary_fragments,
            output_flags=default_output_flags,
            execution_mode=ExecutionMode.AUTO,
        )
        assert isinstance(result, Success)
        assert result.message == f"Waited for {wait_duration} seconds."
        mock_async_sleep.assert_called_once_with(wait_duration)


@pytest.mark.asyncio
async def test_handle_vibe_request_llm_feedback(
    mock_get_adapter: MagicMock,
    mock_console: Mock,
    prevent_exit: MagicMock,
    default_output_flags: OutputFlags,
    mock_memory: MagicMock,
) -> None:
    """Test handling of a FEEDBACK action from the LLM."""
    feedback_message = "This is a feedback message from the LLM."
    feedback_explanation_str = "This is an explanation for the feedback."
    feedback_suggestion_str = "This is a suggestion for the feedback."

    feedback_action = FeedbackAction(
        action_type=ActionType.FEEDBACK,
        message=feedback_message,
        explanation=feedback_explanation_str,
        suggestion=feedback_suggestion_str,
    )
    llm_response_obj = LLMPlannerResponse(action=feedback_action)
    llm_response_str = llm_response_obj.model_dump_json()

    # Setup mock returns for execute_and_log_metrics
    # First call (planning), Second call (memory update summary)
    mock_get_adapter.execute_and_log_metrics.side_effect = [
        (
            llm_response_str,
            LLMMetrics(token_input=10, token_output=10, latency_ms=100.0, call_count=1),
        ),
        (
            "Memory updated with feedback.",
            LLMMetrics(token_input=5, token_output=5, latency_ms=50.0, call_count=1),
        ),
    ]

    result = await handle_vibe_request(
        request="give me feedback",
        command="vibe",
        plan_prompt_func=plan_vibe_fragments,
        summary_prompt_func=get_test_summary_fragments,
        output_flags=default_output_flags,
        execution_mode=ExecutionMode.AUTO,
    )
    assert isinstance(result, Success)
    assert result.message == f"Applied AI feedback: {feedback_suggestion_str}"

    mock_console.print_vibe.assert_called_once_with(feedback_message)
    # When execution_mode=ExecutionMode.AUTO, _handle_command_confirmation returns
    # early, so it doesn't print the note.
    # The proposal is printed directly by the FEEDBACK action block.
    mock_console.print_note.assert_not_called()
    mock_console.print_proposal.assert_called_once_with(
        f"Suggested memory update: {feedback_suggestion_str}"
    )

    # Verify memory update was called with the correct parameters
    mock_memory["update"].assert_called_once_with(
        command_message="command: vibe request: give me feedback",
        command_output=feedback_message,
        vibe_output=feedback_suggestion_str,
        model_name=default_output_flags.model_name,
    )


@pytest.mark.asyncio
async def test_handle_vibe_request_llm_feedback_no_explanation(
    mock_get_adapter: MagicMock,
    mock_console: Mock,
    prevent_exit: MagicMock,
    default_output_flags: OutputFlags,
    mock_memory: MagicMock,
) -> None:
    """Test vibe request with FEEDBACK action from planner, no explanation."""
    feedback_message = "feedback message"
    # Correctly structured LLM response for a FeedbackAction
    feedback_action = FeedbackAction(
        action_type=ActionType.FEEDBACK,
        message=feedback_message,
        explanation=None,
        suggestion=None,
    )
    llm_response_obj = LLMPlannerResponse(action=feedback_action)
    llm_response_str = llm_response_obj.model_dump_json()

    # Set up side_effect for LLM calls
    # Call 1: Planning phase
    # Call 2 (optional): Memory update phase (if update_memory calls LLM)
    mock_get_adapter.execute_and_log_metrics.side_effect = [
        (
            llm_response_str,
            LLMMetrics(token_input=1, token_output=1, latency_ms=100.0, call_count=1),
        ),  # For the planning call
        (
            "Updated memory after feedback action via LLM.",
            LLMMetrics(token_input=1, token_output=1, latency_ms=100.0, call_count=1),
        ),  # Potential for memory update summary call
    ]

    result = await handle_vibe_request(
        request="vibe feedback no explanation",
        command="vibe",
        plan_prompt_func=plan_vibe_fragments,
        summary_prompt_func=get_test_summary_fragments,
        output_flags=default_output_flags,
        execution_mode=ExecutionMode.AUTO,
    )

    assert isinstance(result, Success)

    # Verify LLM was called once for planning
    # (update_memory is mocked and won't call LLM).
    assert mock_get_adapter.execute_and_log_metrics.call_count == 1

    # Verify console output
    mock_console.print_vibe.assert_called_once_with(feedback_message)
    # When execution_mode=ExecutionMode.AUTO, _handle_command_confirmation does
    # not print the explanation note.
    mock_console.print_note.assert_not_called()
    # The proposal for memory update is printed directly by the FEEDBACK block.
    mock_console.print_proposal.assert_called_once_with(
        "Suggested memory update: AI unable to provide a specific suggestion."
    )

    # Verify memory update was called.
    mock_memory["update"].assert_called_once_with(
        command_message="command: vibe request: vibe feedback no explanation",
        command_output=feedback_message,
        vibe_output="AI unable to provide a specific suggestion.",
        model_name=default_output_flags.model_name,
    )


@pytest.mark.asyncio
async def test_handle_vibe_request_command_error(
    mock_get_adapter: MagicMock,
    mock_console: Mock,
    prevent_exit: MagicMock,
    default_output_flags: OutputFlags,
    mock_memory: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test vibe request with command execution error and recovery."""
    caplog.set_level("ERROR")
    # Initial plan from LLM
    command_action = CommandAction(
        action_type=ActionType.COMMAND, commands=["nonexistent-resource"]
    )
    plan_json_str = LLMPlannerResponse(action=command_action).model_dump_json()

    # Recovery suggestion from LLM (plain text, not JSON)
    recovery_message = "Recovery suggestion: Check resource name."

    # Mock the responses for execute_and_log_metrics
    # 1. Initial plan
    # 2. Recovery suggestion (plain text from recovery prompt)
    plan_metrics = LLMMetrics(latency_ms=10)
    recovery_metrics = LLMMetrics(
        token_input=0,
        token_output=0,
        latency_ms=10,
        total_processing_duration_ms=None,
        fragments_used=None,
        call_count=0,
    )
    mock_get_adapter.execute_and_log_metrics.side_effect = [
        (plan_json_str, plan_metrics),  # For initial plan
        (recovery_message, recovery_metrics),  # For recovery suggestion (plain text)
    ]

    with patch("vibectl.execution.vibe._execute_command") as mock_execute_cmd:
        error_message = "kubectl command failed"
        mock_execute_cmd.return_value = Error(
            error=error_message, exception=RuntimeError("simulated kubectl error")
        )
        # The request text used in handle_vibe_request
        request_text_for_test = "run a command that fails"
        result = await handle_vibe_request(
            request=request_text_for_test,
            command="get",  # This is original_command_verb
            plan_prompt_func=plan_vibe_fragments,
            summary_prompt_func=get_test_summary_fragments,
            output_flags=default_output_flags,
            execution_mode=ExecutionMode.AUTO,
        )

    assert isinstance(result, Error)
    assert error_message in result.error
    # get_llm_recovery_suggestion returns JSON, but handle_command_output parses it.
    assert (
        result.recovery_suggestions == recovery_message
    )  # Changed back from recovery_json_str
    mock_execute_cmd.assert_called_once_with(
        "get", ["nonexistent-resource"], None, allowed_exit_codes=(0,)
    )
    assert mock_get_adapter.execute_and_log_metrics.call_count == 2

    # Check that memory was updated after the error and after recovery suggestion
    assert mock_memory["update"].call_count == 2

    # Define expected calls for mock_memory["update"]
    # Call 1: From handle_command_output during error recovery
    call_1_kwargs = {
        "command_message": "get",
        "command_output": error_message,
        "vibe_output": recovery_message,
        "model_name": default_output_flags.model_name,
        "config": ANY,
    }

    # Call 2: From handle_vibe_request's main error block
    expected_cmd_msg_2 = "command: kubectl get nonexistent-resource original: get"
    call_2_kwargs = {
        "command_message": expected_cmd_msg_2,
        "command_output": result.error,
        "vibe_output": "Executed: kubectl get nonexistent-resource",
        "model_name": default_output_flags.model_name,
    }

    # Check call 1 arguments appeared
    mock_memory["update"].assert_any_call(**call_1_kwargs)

    # Check call 2 arguments appeared
    mock_memory["update"].assert_any_call(**call_2_kwargs)


@pytest.mark.asyncio
async def test_handle_vibe_request_yaml_response(
    mock_get_adapter: MagicMock,
    mock_console: Mock,
    mock_prompt: MagicMock,
    prevent_exit: MagicMock,
    default_output_flags: OutputFlags,
    mock_memory: MagicMock,
) -> None:
    """Test handling of commands that might involve YAML (basic case)."""
    yaml_manifest_content = (
        "apiVersion: v1\nkind: Pod\nmetadata:\n  name: test-pod-yaml"
    )
    command_action = CommandAction(
        action_type=ActionType.COMMAND,
        commands=["-f", "-"],
        yaml_manifest=yaml_manifest_content,
    )
    llm_response_str = LLMPlannerResponse(action=command_action).model_dump_json()
    mock_get_adapter.execute_and_log_metrics.return_value = (llm_response_str, None)
    mock_prompt.return_value = "y"  # Confirm apply

    with patch("vibectl.execution.vibe._execute_command") as mock_execute_cmd:
        mock_execute_cmd.return_value = Success(
            data="deployment.apps/nginx-deployment configured"
        )
        await handle_vibe_request(
            request="apply this config from yaml",
            command="apply",
            plan_prompt_func=plan_vibe_fragments,
            summary_prompt_func=get_test_summary_fragments,
            output_flags=default_output_flags,
            execution_mode=ExecutionMode.AUTO,
        )
        mock_execute_cmd.assert_called_once_with(
            "apply", ["-f", "-"], yaml_manifest_content, allowed_exit_codes=(0,)
        )
        # In ExecutionMode.AUTO, confirmation prompts are bypassed, so no
        # prompt should be shown.
        mock_prompt.assert_not_called()


@pytest.mark.asyncio
async def test_handle_vibe_request_summary_for_memory_no_vibe_output(
    mock_get_adapter: MagicMock,
    mock_console: Mock,
    prevent_exit: MagicMock,
    default_output_flags: OutputFlags,
    mock_memory: MagicMock,
) -> None:
    """Test that summary is generated for memory even if show_vibe is False."""
    default_output_flags.show_vibe = False  # Crucial for this test

    # LLM plan response
    command_action = CommandAction(
        action_type=ActionType.COMMAND, commands=["get", "nodes"]
    )
    plan_json = LLMPlannerResponse(action=command_action).model_dump_json()

    # LLM summary response (this will be for memory)
    summary_text = "Summary: Got nodes successfully and they are all ready."
    # Make kubectl_output_data more substantial
    kubectl_output_data = "node1 Ready version=v1.2.3 os=linux"

    # Expect 2 calls: planning, and then update_memory's internal summary call.
    mock_get_adapter.reset_mock()  # Reset from previous tests if any
    mock_get_adapter.execute_and_log_metrics.side_effect = [
        (
            plan_json,
            LLMMetrics(token_input=1, token_output=1, latency_ms=100.0, call_count=1),
        ),  # For planning
        (
            summary_text,
            LLMMetrics(token_input=1, token_output=1, latency_ms=100.0, call_count=1),
        ),  # For summary generation inside update_memory
    ]

    with patch("vibectl.execution.vibe._execute_command") as mock_execute_cmd:
        mock_execute_cmd.return_value = Success(data=kubectl_output_data)
        # The real vibectl.memory.update_memory should be called, so
        # no patch for it here.
        await handle_vibe_request(
            request="get nodes for memory",
            command="get",
            plan_prompt_func=plan_vibe_fragments,
            summary_prompt_func=get_test_summary_fragments,
            output_flags=default_output_flags,
            execution_mode=ExecutionMode.AUTO,
        )

    mock_console.print_vibe.assert_not_called()  # Vibe output should be suppressed
    # Check that the model adapter was called for planning.
    assert (
        mock_get_adapter.execute_and_log_metrics.call_count >= 1
    )  # At least planning call
    mock_memory["update"].assert_called_once()  # Verify memory update was attempted


@pytest.mark.asyncio
async def test_get_llm_plan_parses_command_action(
    mock_get_adapter: MagicMock,
    default_output_flags: OutputFlags,
    mock_memory: MagicMock,  # For get_memory call inside _get_llm_plan
) -> None:
    """Test _get_llm_plan successfully parses a CommandAction."""

    command_action = CommandAction(
        action_type=ActionType.COMMAND, commands=["get", "svc"]
    )
    llm_response_str = LLMPlannerResponse(action=command_action).model_dump_json()
    mock_get_adapter.execute_and_log_metrics.return_value = (
        llm_response_str,
        LLMMetrics(latency_ms=10),
    )
    mock_memory["get"].return_value = "Test memory context"

    # Prepare fragments as _get_llm_plan expects them
    base_system_fragments, base_user_fragments = plan_vibe_fragments()
    request_str = "get services"
    current_user_fragments = UserFragments(
        [*base_user_fragments, Fragment(f"My request is: {request_str}")]
    )

    result = await _get_llm_plan(
        model_name=default_output_flags.model_name,
        plan_system_fragments=base_system_fragments,
        plan_user_fragments=current_user_fragments,
        response_model_type=LLMPlannerResponse,
        config=Config(),
    )
    assert isinstance(result, Success)
    assert isinstance(result.data, LLMPlannerResponse)
    assert isinstance(result.data.action, CommandAction)
    assert result.data.action.commands == ["get", "svc"]


@pytest.mark.asyncio
async def test_get_llm_plan_handles_pydantic_validation_error(
    mock_get_adapter: MagicMock,
    default_output_flags: OutputFlags,
    mock_memory: MagicMock,
) -> None:
    """Test _get_llm_plan handles Pydantic validation error during parsing."""
    # Invalid JSON string (e.g., missing 'action' key for LLMPlannerResponse)
    invalid_llm_response_str = '{"foo": "bar"}'
    mock_get_adapter.execute_and_log_metrics.return_value = (
        invalid_llm_response_str,
        LLMMetrics(latency_ms=10),
    )
    mock_memory["get"].return_value = "Test memory context"

    base_system_fragments, base_user_fragments = plan_vibe_fragments()
    request_str = "test validation error"
    current_user_fragments = UserFragments(
        [*base_user_fragments, Fragment(f"My request is: {request_str}")]
    )

    result = await _get_llm_plan(
        model_name=default_output_flags.model_name,
        plan_system_fragments=base_system_fragments,
        plan_user_fragments=current_user_fragments,
        response_model_type=LLMPlannerResponse,
        config=Config(),
    )
    assert isinstance(result, Error)
    assert "Failed to parse LLM response as expected JSON" in result.error
    assert isinstance(
        result.exception, Exception
    )  # Should be a Pydantic ValidationError


@pytest.mark.asyncio  # Added
async def test_handle_vibe_request_empty_response(  # Added async
    mock_console: Mock,
    mock_get_adapter: MagicMock,
    mock_run_kubectl: Mock,
    mock_memory: MagicMock,
    default_output_flags: OutputFlags,
) -> None:
    """Test vibe request with empty string response from planner."""
    with patch("vibectl.model_adapter.llm.get_model") as mock_actual_llm_get_model:
        mock_actual_llm_get_model.return_value = MagicMock()  # Mock the deep llm call

        # Ensure get_model on the adapter instance also appears to work if called
        mock_get_adapter.get_model = MagicMock(
            return_value=mock_actual_llm_get_model.return_value
        )

        # Set up empty response for execute_and_log_metrics
        malformed_response = ""
        mock_get_adapter.execute_and_log_metrics.return_value = (
            malformed_response,
            MagicMock(spec=LLMMetrics),
        )

        # Empty string is handled before JSON parsing
        with patch("vibectl.execution.vibe.update_memory") as mock_update_memory:
            result = await handle_vibe_request(
                request="empty response test",
                command="get",
                plan_prompt_func=plan_vibe_fragments,
                summary_prompt_func=get_test_summary_fragments,
                output_flags=default_output_flags,
                execution_mode=ExecutionMode.AUTO,
            )

        # Assert that the specific error for empty response was returned
        assert isinstance(result, Error)
        assert result.error == "LLM returned an empty response."

        # Verify update_memory was called
        mock_update_memory.assert_called_once()
        call_args = mock_update_memory.call_args.kwargs
        assert call_args.get("command_message") == "system"
        assert call_args.get("command_output") == "LLM Error: Empty response."
        assert call_args.get("vibe_output") == "LLM Error: Empty response."
        assert call_args.get("model_name") == default_output_flags.model_name

        # Verify kubectl was NOT called
        mock_run_kubectl.assert_not_called()


@pytest.mark.asyncio
async def test_handle_vibe_request_error_response(
    mock_console: Mock,
    mock_get_adapter: MagicMock,
    mock_run_kubectl: Mock,
    default_output_flags: OutputFlags,
    mock_memory: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test vibe request with error response from planner."""
    caplog.set_level("ERROR")
    # Mock LLM planning response (error action)
    error_msg_from_llm = "LLM could not process the request due to ambiguity."

    # Correctly structured LLM response for an ErrorAction
    error_action = ErrorAction(action_type=ActionType.ERROR, message=error_msg_from_llm)
    llm_response_obj = LLMPlannerResponse(action=error_action)

    mock_get_adapter.execute_and_log_metrics.return_value = (
        llm_response_obj.model_dump_json(),
        None,
    )

    # Set show_kubectl to True (doesn't affect this path but good practice)
    default_output_flags.show_kubectl = True

    # Assert the result of handle_vibe_request
    result = await handle_vibe_request(  # Added await
        request="ERROR: test error",
        command="get",
        plan_prompt_func=plan_vibe_fragments,
        summary_prompt_func=get_test_summary_fragments,
        output_flags=default_output_flags,
        execution_mode=ExecutionMode.AUTO,
    )

    # Assert handle_vibe_request returned an Error object
    assert isinstance(result, Error)
    # Check the error message structure
    assert result.error.startswith("LLM planning error:")
    assert error_msg_from_llm in result.error
    # Assert the recovery suggestions come from the explanation
    assert (
        result.recovery_suggestions
        == "LLM could not process the request due to ambiguity."
    )

    # Verify kubectl was NOT called
    mock_run_kubectl.assert_not_called()

    # Verify memory was updated. In the ErrorAction path of handle_vibe_request,
    # update_memory is called directly.
    mock_memory["update"].assert_called_once_with(
        command_message="command: get request: ERROR: test error",
        command_output=error_msg_from_llm,
        vibe_output="",
        model_name=default_output_flags.model_name,
    )


@pytest.mark.asyncio
@patch("vibectl.execution.vibe.update_memory")
async def test_handle_vibe_request_invalid_format(
    mock_update_memory: MagicMock,
    mock_console: Mock,
    mock_get_adapter: MagicMock,
    mock_run_kubectl: Mock,
    default_output_flags: OutputFlags,
) -> None:
    """Test vibe request when LLM returns invalid JSON/schema."""
    with patch("vibectl.model_adapter.llm.get_model") as mock_actual_llm_get_model:
        mock_model_instance = MagicMock()
        mock_actual_llm_get_model.return_value = (
            mock_model_instance  # Mock the deep llm call
        )

        # Ensure get_model on the adapter instance also appears to work
        mock_get_adapter.get_model = MagicMock(return_value=mock_model_instance)

        invalid_json_response = "this is not valid json"
        mock_get_adapter.execute_and_log_metrics.return_value = (
            invalid_json_response,
            None,
        )

        # Expected error from _get_llm_plan when parsing fails
        result = await handle_vibe_request(
            request="get pods",
            command="get",
            plan_prompt_func=plan_vibe_fragments,
            summary_prompt_func=get_test_summary_fragments,
            output_flags=default_output_flags,
            execution_mode=ExecutionMode.AUTO,
        )

        assert isinstance(result, Error)
        assert "Failed to parse LLM response as expected JSON" in result.error
        assert isinstance(result.exception, ValidationError | json.JSONDecodeError)
        mock_update_memory.assert_called_once()


@pytest.mark.asyncio
async def test_handle_vibe_request_no_output(
    mock_get_adapter: MagicMock,
    mock_run_kubectl: Mock,
    mock_console: MagicMock,
    prevent_exit: MagicMock,
    mock_memory: MagicMock,
) -> None:
    """Test vibe request with no output flags."""
    # Set up model response JSON
    # Correctly structure the LLM response for a CommandAction
    command_action = CommandAction(action_type=ActionType.COMMAND, commands=["pods"])
    llm_planner_response_obj = LLMPlannerResponse(action=command_action)
    plan_json_str = llm_planner_response_obj.model_dump_json()

    mock_get_adapter.execute_and_log_metrics.return_value = (
        plan_json_str,
        None,
    )

    # Create custom OutputFlags with no outputs
    no_output_flags = OutputFlags(
        show_raw_output=False,
        show_vibe=False,
        warn_no_output=True,
        model_name="model-xyz-1.2.3",
        show_kubectl=False,
        show_metrics=MetricsDisplayMode.NONE,
    )

    # Mock console_manager directly for this test to add print_raw and check
    # print_no_output_warning. Target where it's used by handle_command_output.
    with (
        patch("vibectl.command_handler.console_manager") as direct_console_mock,
        patch("vibectl.execution.vibe._execute_command") as mock_execute_cmd,
    ):
        # Configure the console mock methods needed by handle_command_output
        direct_console_mock.print_no_output_warning = MagicMock()
        direct_console_mock.print_error = MagicMock()
        direct_console_mock.print_processing = MagicMock()
        direct_console_mock.print_raw = MagicMock()

        # Mock the execution result
        mock_execute_cmd.return_value = Success(data="pod-a\npod-b")

        # Call handle_vibe_request (handle_command_output will be called internally)
        await handle_vibe_request(
            request="show me the pods",
            command="get",
            plan_prompt_func=plan_vibe_fragments,
            summary_prompt_func=get_test_summary_fragments,
            output_flags=no_output_flags,
            execution_mode=ExecutionMode.AUTO,
        )

        # Verify warning was printed by the real
        # handle_command_output -> _check_output_visibility
        direct_console_mock.print_no_output_warning.assert_called_once()

        # Verify _execute_command was called
        mock_execute_cmd.assert_called_once()

    # Verify run_kubectl was NOT called directly (it's called by _execute_command)
    mock_run_kubectl.assert_not_called()

    # Verify sys.exit was not called
    prevent_exit.assert_not_called()


@pytest.mark.asyncio
@patch("vibectl.execution.vibe.console_manager")
async def test_show_kubectl_flag_controls_command_display(
    mock_console_manager: MagicMock,
    mock_get_adapter: MagicMock,
    mock_memory: MagicMock,
    prevent_exit: MagicMock,
) -> None:
    """Test that the show_kubectl flag controls command display."""
    # --- Test Setup ---
    # Define the command the LLM should plan
    llm_commands_from_plan = ["get", "pods", "--namespace=test-ns"]

    # This is the JSON string the LLM would return
    command_action = CommandAction(
        action_type=ActionType.COMMAND, commands=llm_commands_from_plan
    )
    llm_response_str = LLMPlannerResponse(action=command_action).model_dump_json()

    mock_get_adapter.execute_and_log_metrics.return_value = (
        llm_response_str,
        None,
    )

    # Define what the display string should look like
    expected_display_args_str = _create_display_command_for_test(llm_commands_from_plan)
    expected_display_command = f"Running: kubectl get {expected_display_args_str}"

    # --- Loop through show_kubectl flag values ---
    for show_flag_value, expect_print in [(True, True), (False, False)]:
        # Reset mocks at the START of the loop iteration
        mock_console_manager.reset_mock()
        mock_get_adapter.reset_mock()
        # We need fresh mocks for patched functions inside the loop

        # Set the LLM response again for this iteration (if reset)
        mock_get_adapter.execute_and_log_metrics.return_value = (
            llm_response_str,
            None,
        )

        # Create output flags for this iteration
        output_flags = OutputFlags(
            show_raw_output=False,
            show_vibe=False,
            warn_no_output=False,
            model_name="test",
            show_kubectl=show_flag_value,  # Set based on loop
            show_metrics=MetricsDisplayMode.ALL,
        )

        # Mock _execute_command and handle_command_output within the loop
        with (
            patch("vibectl.execution.vibe._execute_command") as mock_execute_cmd,
            patch("vibectl.execution.vibe.handle_command_output") as mock_handle_output,
        ):  # No need to assert on this mock
            mock_execute_cmd.return_value = Success("pod data")
            mock_handle_output.return_value = Success("Handled output")  # Mock return

            # --- Execute the function under test ---
            await handle_vibe_request(  # Added await
                request="get pods in test-ns",
                command="get",  # Original user command
                plan_prompt_func=plan_vibe_fragments,
                summary_prompt_func=get_test_summary_fragments,
                output_flags=output_flags,
                execution_mode=ExecutionMode.AUTO,
            )

            # --- Assertions ---
            # 1. Check if the command was displayed based on the flag
            if expect_print:
                # Verify print_processing was called with the correct command string
                found_call = any(
                    call.args and call.args[0] == expected_display_command
                    for call in mock_console_manager.print_processing.call_args_list
                )
                assert found_call, (
                    f"{expected_display_command!r} not found in calls: "
                    f"{mock_console_manager.print_processing.call_args_list}"
                )
            else:
                # Verify print_processing was NOT called with the command display string
                for call in mock_console_manager.print_processing.call_args_list:
                    if call.args:
                        assert not call.args[0].startswith("Running: kubectl"), (
                            f"Expected no kubectl command print, but "
                            f"found: {call.args[0]}"
                        )

            # 2. Verify _execute_command was called with the LLM-planned command
            mock_execute_cmd.assert_called_once_with(
                "get", llm_commands_from_plan, None, allowed_exit_codes=(0,)
            )

            # 3. Verify handle_command_output was called with the LLM-planned verb
            mock_handle_output.assert_called_once()
            _, ho_call_kwargs = mock_handle_output.call_args
            assert ho_call_kwargs.get("command") == "get"


@pytest.mark.asyncio
@patch("vibectl.execution.vibe.console_manager.print_vibe")
@patch("vibectl.cli.handle_result")
@patch("vibectl.cli.run_vibe_command")
async def test_vibe_cli_emits_vibe_check(
    mock_run_vibe_command: AsyncMock,
    mock_handle_result: Mock,
    mock_print_vibe: Mock,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """CLI-level test: 'vibectl vibe' invokes logic that should print vibe check."""

    # Configure the patched run_vibe_command to return Success
    # Needs to be awaitable since run_vibe_command is async
    async def async_success(*args: Any, **kwargs: Any) -> Success:
        return Success(message="1 pod running")

    mock_run_vibe_command.side_effect = async_success

    # Configure mock_handle_result side effect
    def side_effect_handle_result(result: Result) -> NoReturn:
        # Simulate the part of handle_result that calls print_vibe
        if isinstance(result, Success):
            mock_print_vibe(f"✨ Vibe check: {result.message}")
        # Important: handle_result in cli.py likely calls sys.exit()
        # We need to prevent that in the test or raise SystemExit
        raise SystemExit(0 if isinstance(result, Success) else 1)

    mock_handle_result.side_effect = side_effect_handle_result

    # Call the main CLI entrypoint for the vibe command
    cmd_obj = cli.commands["vibe"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main([])  # Call main directly

    # Assert exit code is 0
    assert exc_info.value.code == 0

    # Assert our patched print_vibe was called via the handle_result side effect
    mock_print_vibe.assert_called_once_with("✨ Vibe check: 1 pod running")


@pytest.fixture
def mock_adapter_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[MagicMock, None, None]:
    """Mock vibe adapter instance."""
    mock_adapter_instance = MagicMock()
    mock_model_instance = MagicMock()
    mock_adapter_instance.get_model.return_value = mock_model_instance

    # Configure the mock adapter instance's execute method (can be overridden in tests)
    mock_adapter_instance.execute.return_value = "Default execute response"

    # Yield the mock adapter instance, not the function mock
    yield mock_adapter_instance


# Helper function to mimic _create_display_command for test assertions
def _create_display_command_for_test(args: list[str]) -> str:
    display_args = []
    for arg in args:
        if " " in arg or any(c in arg for c in "<>|"):
            display_args.append(f'"{arg}"')
        else:
            display_args.append(arg)
    return " ".join(display_args)


@pytest.mark.asyncio
async def test_handle_vibe_request_recoverable_api_error_during_summary(
    mock_get_adapter: MagicMock,
    mock_console: Mock,
    prevent_exit: MagicMock,
    default_output_flags: OutputFlags,
    mock_memory: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test RecoverableApiError during Vibe summary phase is handled.

    When the LLM call for summary fails with a recoverable error, it should
    be caught, logged, and returned as a non-halting API error.
    """
    caplog.set_level("WARNING")
    default_output_flags.show_vibe = True  # Ensure Vibe processing is enabled

    # Enable streaming to match test expectations
    default_output_flags.show_streaming = True

    command_action = CommandAction(
        action_type=ActionType.COMMAND, commands=["get", "pods"]
    )
    llm_planner_response_obj = LLMPlannerResponse(action=command_action)
    plan_json_str = llm_planner_response_obj.model_dump_json()

    kubectl_output_data = "pod-a\\npod-b"

    # Expected LLM responses
    plan_response = (plan_json_str, LLMMetrics(latency_ms=10))
    memory_update_response_text = "Memory updated post-command"
    memory_update_metrics = LLMMetrics(latency_ms=5)
    memory_update_response = (memory_update_response_text, memory_update_metrics)
    summary_error = RecoverableApiError("Rate limit hit")

    mock_get_adapter.execute_and_log_metrics.side_effect = [
        plan_response,  # For initial plan
        memory_update_response,  # For update_memory call by real_update_memory_impl
        # No third entry needed since streaming is enabled and will use
        # stream_execute_and_log_metrics
    ]

    # Configure the side_effect for the mock LLM adapter's
    # stream_execute_and_log_metrics (streaming)
    # This will be called by stream_vibe_output_and_log_metrics for the summary
    mock_get_adapter.stream_execute_and_log_metrics.side_effect = (
        summary_error  # The exception instance
    )

    # Patch _execute_command where it's called from vibe.py
    with (
        patch("vibectl.execution.vibe._execute_command") as mock_execute_cmd,
        # Patch update_memory for this test to use the real implementation,
        # which will then use the mock_get_adapter.
        patch(
            "vibectl.execution.vibe.update_memory", side_effect=real_update_memory_impl
        ) as mock_actual_update_call,
    ):
        mock_execute_cmd.return_value = Success(data=kubectl_output_data)
        # Call function
        result = await handle_vibe_request(
            request="show me the pods",
            command="vibe",
            plan_prompt_func=plan_vibe_fragments,
            summary_prompt_func=get_test_summary_fragments,
            output_flags=default_output_flags,
            execution_mode=ExecutionMode.AUTO,
        )

        # Verify _execute_command was called
        mock_execute_cmd.assert_called_once()

        # Verify the LLM was called for planning and first memory update (non-streaming)
        assert mock_get_adapter.execute_and_log_metrics.call_count == 2
        # Verify the LLM was called for summary (streaming)
        assert mock_get_adapter.stream_execute_and_log_metrics.call_count == 1

        # Verify the final result is an Error because the summary LLM call failed,
        # but it's a non-halting error.
        assert isinstance(result, Error)
        assert result.halt_auto_loop is False  # Key check for recoverable API errors
        expected_error_message_fragment = (
            "Recoverable API error during Vibe processing: Rate limit hit"
        )
        assert expected_error_message_fragment in result.error

        # Check logs for the warning about the Vibe summary error
        if caplog.records:
            found_log = False
            for record in caplog.records:
                if (
                    record.name == "vibectl"
                    and record.levelname == "WARNING"
                    and expected_error_message_fragment in record.getMessage()
                ):
                    found_log = True
                    break
            error_msg = (
                f"Expected log message not found: {expected_error_message_fragment}"
            )
            assert found_log, error_msg
        else:
            raise AssertionError("Expected log records but none found")

        # Check that update_memory was called
        assert mock_actual_update_call.call_count >= 1  # Check the new patch


@pytest.mark.asyncio
async def test_handle_vibe_request_general_exception_during_recovery(
    mock_get_adapter: MagicMock,
    mock_console: Mock,
    prevent_exit: MagicMock,
    default_output_flags: OutputFlags,
    mock_memory: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test general Exception during recovery suggestion phase is handled.

    When the direct LLM call for recovery suggestions (after an initial command
    error) fails with an unexpected exception, the original error should be
    combined with the recovery failure message.
    """
    caplog.set_level("ERROR")
    default_output_flags.show_vibe = True  # Ensure Vibe recovery is attempted

    # Mock the planning response (successful plan initially)
    plan_response = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["get", "configmaps"],
        "explanation": "Get configmaps",
    }
    initial_error_message = "Error: ConfigMap 'test-cm' not found"

    # Patch _execute_command to return an Error (target
    # vibectl.execution.vibe._execute_command)
    with patch("vibectl.execution.vibe._execute_command") as mock_execute_cmd:
        mock_execute_cmd.return_value = Error(
            error=initial_error_message,
            exception=RuntimeError("simulated kubectl error"),
        )

        # Mock the LLM adapter execute method
        # First call (planning) returns the plan
        # Second call (recovery in handle_command_output) raises a general Exception
        recovery_exception_message = "Unexpected LLM service outage"
        mock_get_adapter.execute_and_log_metrics.side_effect = [
            (json.dumps({"action": plan_response}), None),  # Planning call
            Exception(recovery_exception_message),  # Recovery suggestion call
        ]

        # Patch vibectl.memory.update_memory to prevent it from consuming the
        # side_effect and vibectl.command_handler.update_memory to check its call
        # for recovery failure message.
        with (
            patch(
                "vibectl.execution.vibe.update_memory"
            ) as mock_internal_update_memory,
            patch("vibectl.command_handler.update_memory") as mock_ch_update_memory,
        ):
            mock_internal_update_memory.return_value = (
                None  # Ensure it doesn't call LLM
            )
            # Call the function under test
            result = await handle_vibe_request(
                request="get a non-existent configmap",
                command="get",  # Actual verb being executed
                plan_prompt_func=plan_vibe_fragments,
                summary_prompt_func=get_test_summary_fragments,
                output_flags=default_output_flags,  # Assumes show_vibe=True
                execution_mode=ExecutionMode.AUTO,
            )

            # Verify the LLM execute was called twice (plan + recovery attempt)
            assert mock_get_adapter.execute_and_log_metrics.call_count == 2

            # Verify vibectl.memory.update_memory (called by _confirm_and_execute_plan)
            mock_internal_update_memory.assert_called_once()

            # Verify vibectl.command_handler.update_memory (called by
            # handle_command_output for recovery failure)
            mock_ch_update_memory.assert_called_once()
            ch_call_args = mock_ch_update_memory.call_args.kwargs
            assert recovery_exception_message in ch_call_args.get("vibe_output", "")

            # Verify the final result is the *original* Error object, annotated
            assert isinstance(result, Error)

            # Assert the error message is the ORIGINAL error message
            assert result.error == initial_error_message
            # Assert the recovery suggestions contain the failure message
            assert "Failed to get recovery suggestions" in (
                result.recovery_suggestions or ""
            )
            assert recovery_exception_message in (result.recovery_suggestions or "")
            # Assert the halt loop remains True because recovery failed
            assert result.halt_auto_loop is True

            # Assert the exception in the Error object is original command's exception
            assert isinstance(result.exception, RuntimeError)

            # Verify console output:
            # 1. Initial error IS printed by print_error because halt_auto_loop=True
            # from initial Error
            mock_console.print_error.assert_called_once_with(initial_error_message)
            # 2. Recovery failure message IS printed via print_vibe
            mock_console.print_vibe.assert_called_once_with(
                f"Failed to get recovery suggestions: {recovery_exception_message}"
            )
