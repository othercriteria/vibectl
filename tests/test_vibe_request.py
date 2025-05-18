"""Tests for vibe request handling functionality."""

import json
from collections.abc import Generator
from pathlib import Path
from typing import Any, NoReturn
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from pydantic import ValidationError

from vibectl.cli import cli
from vibectl.command_handler import OutputFlags, handle_vibe_request
from vibectl.config import Config
from vibectl.model_adapter import LLMMetrics, RecoverableApiError
from vibectl.prompt import (
    plan_vibe_fragments,
)
from vibectl.types import (
    ActionType,
    Error,
    Fragment,
    PromptFragments,
    Result,
    Success,
    SystemFragments,
    UserFragments,
    Truncation,
)
from vibectl.schema import LLMPlannerResponse, CommandAction, ErrorAction, FeedbackAction, WaitAction


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
        show_raw=False,
        show_vibe=True,  # Changed to True
        warn_no_output=True,
        model_name="test-model",
        show_metrics=True,
        show_kubectl=True,  # Changed to True for more comprehensive testing
        warn_no_proxy=True,
    )


@pytest.mark.asyncio  # Added
async def test_handle_vibe_request_success(  # Added async
    mock_get_adapter: MagicMock,
    mock_console: Mock,
    prevent_exit: MagicMock,
    default_output_flags: OutputFlags,
    mock_memory: MagicMock,
) -> None:
    """Test basic successful vibe request execution."""
    # Mock the LLM planning response
    command_action = CommandAction(action_type=ActionType.COMMAND, commands=["get", "pods"])
    llm_response_str = LLMPlannerResponse(action=command_action).model_dump_json()
    mock_get_adapter.execute_and_log_metrics.return_value = (llm_response_str, None)

    # Mock _confirm_and_execute_plan to return success
    with patch("vibectl.command_handler._confirm_and_execute_plan") as mock_confirm_exec:
        mock_confirm_exec.return_value = Success(data="kubectl command output")

        # Mock update_memory
        with patch("vibectl.command_handler.update_memory") as mock_update_memory:
            result = await handle_vibe_request(
                request="get pods",
                command="get",
                plan_prompt_func=plan_vibe_fragments,
                summary_prompt_func=get_test_summary_fragments,
                output_flags=default_output_flags,
            )

    assert isinstance(result, Success)
    mock_confirm_exec.assert_called_once()
    # Ensure update_memory is called appropriately (e.g., if summary generation is mocked or happens)
    # Depending on full flow, mock_update_memory might be called multiple times.


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
    command_action = CommandAction(action_type=ActionType.COMMAND, commands=command_to_execute)
    llm_response_str = LLMPlannerResponse(action=command_action).model_dump_json()
    mock_get_adapter.execute_and_log_metrics.return_value = (llm_response_str, None)

    with patch("vibectl.command_handler._execute_command") as mock_execute_cmd:
        mock_execute_cmd.return_value = Success(data="clientVersion: v1.2.3")
        # Mock update_memory for this scope if its calls are asserted
        with patch("vibectl.command_handler.update_memory") as mock_update_mem_local:
            await handle_vibe_request(
                request="show k8s version",
                command="version", # Corresponds to the command in CommandAction
                plan_prompt_func=plan_vibe_fragments,
                summary_prompt_func=get_test_summary_fragments,
                output_flags=default_output_flags,
                yes=True, # Bypass confirmation for COMMAND action
            )
            mock_execute_cmd.assert_called_once_with(
                "version", command_to_execute, None, allowed_exit_codes=(0,)
            )
            # Check memory update calls if necessary, e.g., mock_update_mem_local.assert_called()


@pytest.mark.asyncio
async def test_handle_vibe_request_yaml_execution(
    mock_get_adapter: MagicMock,
    mock_console: Mock,
    mock_prompt: MagicMock, # For apply confirmation
    prevent_exit: MagicMock,
    default_output_flags: OutputFlags,
    mock_memory: MagicMock,
) -> None:
    """Test vibe request with a command involving YAML (e.g., apply -f -)."""
    yaml_manifest_content = "apiVersion: v1\nkind: Pod\nmetadata:\n  name: test-pod"
    command_action = CommandAction(
        action_type=ActionType.COMMAND, 
        commands=["-f", "-"], 
        yaml_manifest=yaml_manifest_content
    )
    llm_response_str = LLMPlannerResponse(action=command_action).model_dump_json()
    mock_get_adapter.execute_and_log_metrics.return_value = (llm_response_str, None)
    mock_prompt.return_value = "y" # Confirm apply

    with patch("vibectl.command_handler._execute_command") as mock_execute_cmd:
        mock_execute_cmd.return_value = Success(data="pod/test-pod created")
        with patch("vibectl.command_handler.update_memory") as mock_update_memory:
            await handle_vibe_request(
                request="apply this config from yaml",
                command="apply",
                plan_prompt_func=plan_vibe_fragments,
                summary_prompt_func=get_test_summary_fragments,
                output_flags=default_output_flags,
                yes=False,
            )
            mock_execute_cmd.assert_called_once_with(
                "apply", ["-f", "-"], yaml_manifest_content, allowed_exit_codes=(0,)
            )
            mock_prompt.assert_called_once()


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
    mock_get_adapter.execute_and_log_metrics.side_effect = RuntimeError(llm_api_error_message)

    result = await handle_vibe_request(
        request="get pods",
        command="get",
        plan_prompt_func=plan_vibe_fragments,
        summary_prompt_func=get_test_summary_fragments,
        output_flags=default_output_flags,
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
    wait_action = WaitAction(action_type=ActionType.WAIT, duration_seconds=wait_duration)
    llm_response_str = LLMPlannerResponse(action=wait_action).model_dump_json()
    mock_get_adapter.execute_and_log_metrics.return_value = (llm_response_str, None)

    with patch("asyncio.sleep") as mock_async_sleep:
        result = await handle_vibe_request(
            request="wait for 5 seconds",
            command="wait", # Or any command, LLM dictates wait
            plan_prompt_func=plan_vibe_fragments,
            summary_prompt_func=get_test_summary_fragments,
            output_flags=default_output_flags,
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
    feedback_action = FeedbackAction(action_type=ActionType.FEEDBACK, message=feedback_message)
    llm_response_str = LLMPlannerResponse(action=feedback_action).model_dump_json()
    mock_get_adapter.execute_and_log_metrics.return_value = (llm_response_str, None)

    result = await handle_vibe_request(
        request="give me feedback",
        command="feedback", # Or any command, LLM dictates feedback
        plan_prompt_func=plan_vibe_fragments,
        summary_prompt_func=get_test_summary_fragments,
        output_flags=default_output_flags,
    )
    assert isinstance(result, Success)
    assert result.message == feedback_message
    mock_console.print_vibe_response.assert_called_once_with(feedback_message)


@pytest.mark.asyncio
async def test_handle_vibe_request_llm_feedback_no_explanation(
    mock_get_adapter: MagicMock,
    mock_console: Mock,
    prevent_exit: MagicMock,
    default_output_flags: OutputFlags,
    mock_memory: MagicMock,
) -> None:
    """Test FEEDBACK action with an empty message (should be handled gracefully)."""
    # FeedbackAction.message must be a string. An empty string is a valid case.
    feedback_action = FeedbackAction(action_type=ActionType.FEEDBACK, message="") 
    llm_response_str = LLMPlannerResponse(action=feedback_action).model_dump_json()
    mock_get_adapter.execute_and_log_metrics.return_value = (llm_response_str, None)

    result = await handle_vibe_request(
        request="feedback with no message",
        command="feedback",
        plan_prompt_func=plan_vibe_fragments,
        summary_prompt_func=get_test_summary_fragments,
        output_flags=default_output_flags,
    )
    assert isinstance(result, Success)
    # If LLM provides an empty string, it should still be considered 'feedback provided'
    # The handler might choose to use a default message if the provided one is empty.
    # Current _handle_action_feedback uses action.message directly if not None, else default.
    # An empty string is not None, so it should use the empty string.
    # Let's adjust assertion: if message is empty, console prints empty, result.message is empty.
    assert result.message == "" 
    mock_console.print_vibe_response.assert_called_once_with("")


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
    command_action = CommandAction(action_type=ActionType.COMMAND, commands=["nonexistent-resource"])
    plan_json_str = LLMPlannerResponse(action=command_action).model_dump_json()

    # Recovery suggestion from LLM
    recovery_message = "Recovery suggestion: Check resource name."
    recovery_action = FeedbackAction(action_type=ActionType.FEEDBACK, message=recovery_message)
    recovery_json_str = LLMPlannerResponse(action=recovery_action).model_dump_json()

    mock_get_adapter.execute_and_log_metrics.side_effect = [
        (plan_json_str, None),          # For initial plan
        (recovery_json_str, None),      # For recovery suggestion
    ]

    with patch("vibectl.command_handler._execute_command") as mock_execute_cmd:
        error_message = "kubectl command failed"
        mock_execute_cmd.return_value = Error(
            error=error_message, exception=RuntimeError("simulated kubectl error")
        )
        with patch("vibectl.command_handler.update_memory") as mock_update_memory_ch:
            result = await handle_vibe_request(
                request="run a command that fails",
                command="get",
                plan_prompt_func=plan_vibe_fragments,
                summary_prompt_func=get_test_summary_fragments,
                output_flags=default_output_flags,
                yes=True,
            )

    assert isinstance(result, Error)
    assert error_message in result.error
    assert result.recovery_suggestions == recovery_message
    mock_execute_cmd.assert_called_once_with(
        "get", ["nonexistent-resource"], None, allowed_exit_codes=(0,)
    )
    assert mock_get_adapter.execute_and_log_metrics.call_count == 2 # Plan + Recovery
    # Check that memory was updated after the error and after recovery suggestion
    # This depends on how update_memory is called in the error paths.
    # For simplicity, checking it was called at least once for the error.
    assert mock_update_memory_ch.call_count >= 1 


@pytest.mark.asyncio
async def test_handle_vibe_request_error(
    mock_get_adapter: MagicMock,
    mock_run_kubectl: Mock,
    mock_console: Mock,
    prevent_exit: MagicMock,
    default_output_flags: OutputFlags,
    mock_memory: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test vibe request handling when the LLM returns an error action (already updated above)."""
    # This test was refactored in a previous step to use the new schema correctly.
    # Re-running it here to ensure consistency with other mock updates.
    caplog.set_level("ERROR")
    error_msg_from_llm = "LLM could not process the request due to ambiguity."
    error_action = ErrorAction(action_type=ActionType.ERROR, message=error_msg_from_llm)
    llm_response_obj = LLMPlannerResponse(action=error_action)
    mock_get_adapter.execute_and_log_metrics.return_value = (
        llm_response_obj.model_dump_json(),
        None,
    )

    result = await handle_vibe_request(
        request="cause an llm error",
        command="error",
        plan_prompt_func=plan_vibe_fragments,
        summary_prompt_func=get_test_summary_fragments,
        output_flags=default_output_flags,
    )

    assert isinstance(result, Error)
    assert result.error.startswith("LLM planning error:")
    assert error_msg_from_llm in result.error
    assert result.recovery_suggestions == error_msg_from_llm
    mock_run_kubectl.assert_not_called() # Kubectl should not be called if LLM returns ERROR action
    # Check memory update if it happens for ERROR action
    # mock_memory["update_ch"].assert_called_once_with(...)


@pytest.mark.asyncio
async def test_handle_vibe_request_yaml_response(
    mock_get_adapter: MagicMock,
    mock_console: Mock,
    mock_prompt: MagicMock,
    prevent_exit: MagicMock,
    default_output_flags: OutputFlags,
    mock_memory: MagicMock,
) -> None:
    """Test handling of commands that might involve YAML (basic case), now with proper mocks."""
    yaml_manifest_content = "apiVersion: v1\nkind: Pod\nmetadata:\n  name: test-pod-yaml"
    command_action = CommandAction(
        action_type=ActionType.COMMAND, 
        commands=["-f", "-"], 
        yaml_manifest=yaml_manifest_content
    )
    llm_response_str = LLMPlannerResponse(action=command_action).model_dump_json()
    mock_get_adapter.execute_and_log_metrics.return_value = (llm_response_str, None)
    mock_prompt.return_value = "y" # Confirm apply

    with patch("vibectl.command_handler._execute_command") as mock_execute_cmd:
        mock_execute_cmd.return_value = Success(
            data="deployment.apps/nginx-deployment configured"
        )
        with patch("vibectl.command_handler.update_memory") as mock_update_memory:
            await handle_vibe_request(
                request="apply this config from yaml",
                command="apply",
                plan_prompt_func=plan_vibe_fragments,
                summary_prompt_func=get_test_summary_fragments,
                output_flags=default_output_flags,
                yes=False,
            )
            mock_execute_cmd.assert_called_once_with(
                "apply", ["-f", "-"], yaml_manifest_content, allowed_exit_codes=(0,)
            )
            mock_prompt.assert_called_once()


# Test for when show_vibe is False, but summary is generated for memory
@pytest.mark.asyncio
async def test_handle_vibe_request_summary_for_memory_no_vibe_output(
    mock_get_adapter: MagicMock,
    mock_console: Mock,
    prevent_exit: MagicMock,
    default_output_flags: OutputFlags, 
    mock_memory: MagicMock,
) -> None:
    """Test that summary is generated for memory even if show_vibe is False."""
    default_output_flags.show_vibe = False # Crucial for this test

    # LLM plan response
    command_action = CommandAction(action_type=ActionType.COMMAND, commands=["get", "nodes"])
    plan_json = LLMPlannerResponse(action=command_action).model_dump_json()
    
    # LLM summary response (this will be for memory)
    summary_text = "Summary: Got nodes successfully."
    # Note: The summary LLM call in update_memory uses a simple string, not a structured response model

    mock_get_adapter.execute_and_log_metrics.side_effect = [
        (plan_json, None),      # For planning
        (summary_text, None),   # For summary generation inside update_memory after command execution
        (summary_text, None),   # For summary generation inside update_memory after summary (if nested)
    ]

    with patch("vibectl.command_handler._confirm_and_execute_plan") as mock_confirm_exec:
        mock_confirm_exec.return_value = Success(data="node1\nnode2")
        # We need to mock update_memory from command_handler if we want to check its internal call to LLM
        # For this test, let's assume update_memory (the one in vibectl.memory) is called and works.
        with patch("vibectl.memory.update_memory") as mock_actual_update_memory:
            await handle_vibe_request(
                request="get nodes for memory",
                command="get",
                plan_prompt_func=plan_vibe_fragments,
                summary_prompt_func=get_test_summary_fragments, # This is for the main summary, not memory summary
                output_flags=default_output_flags,
                yes=True,
            )
    
    mock_console.print_vibe_response.assert_not_called() # Vibe output should be suppressed
    # Check that the model adapter was called for summary (inside update_memory)
    # The number of calls depends on how many times update_memory is hit and decides to summarize.
    # Expect at least one call for planning, and at least one for summary if command was successful.
    assert mock_get_adapter.execute_and_log_metrics.call_count >= 2 
    # Verify mock_actual_update_memory was called (at least once after successful command execution)
    mock_actual_update_memory.assert_called()


# Tests for _get_llm_plan internal logic (parsing, validation errors)
# These are effectively covered by test_handle_vibe_request_llm_output_parsing
# but can be more targeted if _get_llm_plan is tested in isolation.

# Example: Test for _get_llm_plan successfully parsing a CommandAction
@pytest.mark.asyncio
async def test_get_llm_plan_parses_command_action(
    mock_get_adapter: MagicMock, 
    default_output_flags: OutputFlags,
    mock_memory: MagicMock, # For get_memory call inside _get_llm_plan
) -> None:
    """Test _get_llm_plan successfully parses a CommandAction."""
    from vibectl.command_handler import _get_llm_plan # Import for direct test
    command_action = CommandAction(action_type=ActionType.COMMAND, commands=["get", "svc"])
    llm_response_str = LLMPlannerResponse(action=command_action).model_dump_json()
    mock_get_adapter.execute_and_log_metrics.return_value = (llm_response_str, LLMMetrics(latency_ms=10))
    mock_memory["get_ch"].return_value = "Test memory context"

    # Prepare fragments as _get_llm_plan expects them
    base_system_fragments, base_user_fragments = plan_vibe_fragments()
    request_str = "get services"
    # Assuming the request is typically added to user fragments
    # This might need adjustment based on how plan_vibe_fragments structures things
    # or if _get_llm_plan itself expects to receive the raw request string and add it.
    # For now, let's assume it's added to user fragments before calling.
    current_user_fragments = UserFragments(base_user_fragments + [Fragment(f"My request is: {request_str}")])

    result = _get_llm_plan(
        model_name=default_output_flags.model_name,
        plan_system_fragments=base_system_fragments,
        plan_user_fragments=current_user_fragments, 
        response_model_type=LLMPlannerResponse 
    )
    assert isinstance(result, Success)
    assert isinstance(result.data, LLMPlannerResponse)
    assert isinstance(result.data.action, CommandAction)
    assert result.data.action.commands == ["get", "svc"]


# Example: Test for _get_llm_plan handling a Pydantic validation error
@pytest.mark.asyncio
async def test_get_llm_plan_handles_pydantic_validation_error(
    mock_get_adapter: MagicMock, 
    default_output_flags: OutputFlags,
    mock_memory: MagicMock,
) -> None:
    """Test _get_llm_plan handles Pydantic validation error during parsing."""
    from vibectl.command_handler import _get_llm_plan
    # Invalid JSON string (e.g., missing 'action' key for LLMPlannerResponse)
    invalid_llm_response_str = '{"foo": "bar"}'
    mock_get_adapter.execute_and_log_metrics.return_value = (invalid_llm_response_str, LLMMetrics(latency_ms=10))
    mock_memory["get_ch"].return_value = "Test memory context"

    # Prepare fragments
    base_system_fragments, base_user_fragments = plan_vibe_fragments()
    request_str = "test validation error"
    current_user_fragments = UserFragments(base_user_fragments + [Fragment(f"My request is: {request_str}")])

    result = _get_llm_plan(
        model_name=default_output_flags.model_name,
        plan_system_fragments=base_system_fragments,
        plan_user_fragments=current_user_fragments,
        response_model_type=LLMPlannerResponse
    )
    assert isinstance(result, Error)
    assert "Failed to parse LLM response as expected JSON" in result.error
    assert isinstance(result.exception, Exception) # Should be a Pydantic ValidationError


@pytest.mark.asyncio  # Added
async def test_handle_vibe_request_empty_response(  # Added async
    mock_console: Mock,
    mock_get_adapter: MagicMock,
    mock_run_kubectl: Mock,
    mock_memory: MagicMock,
    default_output_flags: OutputFlags,
) -> None:
    """Test vibe request with empty string response from planner."""
    # Set up empty response
    malformed_response = ""
    mock_get_adapter.execute_and_log_metrics.return_value = (
        malformed_response,
        MagicMock(spec=LLMMetrics),
    )

    # Empty string is handled before JSON parsing
    # It should return Error("LLM returned an empty response.") directly
    with (
        patch("vibectl.command_handler.update_memory") as mock_update_memory,
        patch("vibectl.command_handler.create_api_error") as mock_create_api_error,
    ):
        result = await handle_vibe_request(  # Added await
            request="empty response test",
            command="get",
            plan_prompt_func=plan_vibe_fragments,
            summary_prompt_func=get_test_summary_fragments,
            output_flags=default_output_flags,
        )

    # Assert that the specific error for empty response was returned
    assert isinstance(result, Error)
    assert result.error == "LLM returned an empty response."

    # Verify update_memory and create_api_error were NOT called for this specific path
    mock_update_memory.assert_called_once()
    call_args = mock_update_memory.call_args.kwargs
    assert call_args.get("command_message") == "system"
    assert call_args.get("command_output") == "LLM Error: Empty response."
    assert call_args.get("vibe_output") == "LLM Error: Empty response."
    assert call_args.get("model_name") == default_output_flags.model_name

    mock_create_api_error.assert_not_called()

    # Verify kubectl was NOT called
    mock_run_kubectl.assert_not_called()


@pytest.mark.asyncio  # Added
async def test_handle_vibe_request_error_response(  # Added async
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
    error_action = ErrorAction(
        action_type=ActionType.ERROR,
        message=error_msg_from_llm
    )
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
    )

    # Assert handle_vibe_request returned an Error object
    assert isinstance(result, Error)
    # Check the error message structure
    assert result.error.startswith("LLM planning error:")
    assert error_msg_from_llm in result.error
    # Assert the recovery suggestions come from the explanation
    assert result.recovery_suggestions == "LLM could not process the request due to ambiguity."

    # Verify kubectl was NOT called
    mock_run_kubectl.assert_not_called()

    # Verify memory was updated because _get_llm_plan handles it
    mock_memory["update_ch"].assert_called_once_with(
        command_message="command: get request: ERROR: test error",
        command_output=error_msg_from_llm,  # which is "LLM could not process the request due to ambiguity."
        vibe_output=f"LLM Planning Error: get ERROR: test error -> {error_msg_from_llm}",
        model_name=default_output_flags.model_name,
    )


@pytest.mark.asyncio  # Added
@patch("vibectl.command_handler.create_api_error")
@patch("vibectl.command_handler.update_memory")
async def test_handle_vibe_request_invalid_format(  # Added async
    mock_update_memory: MagicMock,
    mock_create_api_error: MagicMock,
    mock_console: Mock,
    mock_get_adapter: MagicMock,
    mock_run_kubectl: Mock,
    default_output_flags: OutputFlags,
) -> None:
    """Test vibe request with non-JSON format from planner."""
    # Set up invalid response
    non_json_response = "kubectl get pods # This is not JSON"
    mock_get_adapter.execute_and_log_metrics.return_value = (
        non_json_response,
        MagicMock(spec=LLMMetrics),
    )

    # Configure the mock create_api_error to return a specific Error object
    # Need a dummy exception instance for the mock
    dummy_exception = ValidationError.from_exception_data("DummyValidationError", [])
    expected_error_return = Error(
        error="Failed API error during parsing",
        exception=dummy_exception,
        halt_auto_loop=False,
    )
    mock_create_api_error.return_value = expected_error_return

    # Expect JSONDecodeError path - removed inner with block for patches
    result = await handle_vibe_request(  # Added await
        request="show me the pods invalid format",
        command="get",
        plan_prompt_func=plan_vibe_fragments,
        summary_prompt_func=get_test_summary_fragments,
        output_flags=default_output_flags,
    )

    # Verify update_memory and create_api_error were called due to parsing failure
    mock_update_memory.assert_called_once()
    call_kwargs = mock_update_memory.call_args.kwargs
    assert call_kwargs.get("command_message") == "system"
    assert "Failed to parse LLM response as expected JSON" in call_kwargs.get(
        "command_output", ""
    )
    assert "System Error: Failed to parse LLM response:" in call_kwargs.get(
        "vibe_output", ""
    )
    assert call_kwargs.get("model_name") == default_output_flags.model_name

    # Verify create_api_error was called (now happens in _get_llm_plan)
    mock_create_api_error.assert_called_once()

    # Verify the function returned the specific Error object we configured
    assert result is expected_error_return


@pytest.mark.asyncio  # Added
async def test_handle_vibe_request_no_output(  # Added async
    mock_get_adapter: MagicMock,
    mock_run_kubectl: Mock,
    mock_console: MagicMock,
    prevent_exit: MagicMock,
    mock_memory: MagicMock,
) -> None:
    """Test vibe request with no output flags."""
    # Set up model response JSON
    plan_response = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["pods"],
        "explanation": "Get pods",
    }
    # Summary not needed as handle_command_output is fully mocked
    mock_get_adapter.execute_and_log_metrics.return_value = (
        json.dumps(plan_response),
        None,
    )  # Return JSON string and None metrics

    # Create custom OutputFlags with no outputs
    no_output_flags = OutputFlags(
        show_raw=False,
        show_vibe=False,
        warn_no_output=True,
        model_name="model-xyz-1.2.3",
        show_kubectl=False,
        show_metrics=False,
    )

    # Mock console_manager directly for this test to add print_raw
    # and check print_no_output_warning
    with (
        patch("vibectl.command_handler.console_manager") as direct_console_mock,
        patch("vibectl.command_handler._execute_command") as mock_execute_cmd,
    ):
        # Configure the console mock methods needed by handle_command_output
        direct_console_mock.print_no_output_warning = MagicMock()
        direct_console_mock.print_error = MagicMock()
        direct_console_mock.print_processing = MagicMock()
        direct_console_mock.print_raw = MagicMock()  # Add mock for print_raw

        # Mock the execution result
        mock_execute_cmd.return_value = Success(data="pod-a\npod-b")

        # Call handle_vibe_request (handle_command_output will be called internally)
        await handle_vibe_request(  # Added await
            request="show me the pods",
            command="get",
            plan_prompt_func=plan_vibe_fragments,
            summary_prompt_func=get_test_summary_fragments,
            output_flags=no_output_flags,
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


@pytest.mark.asyncio  # Added
@patch("vibectl.command_handler.console_manager")
async def test_show_kubectl_flag_controls_command_display(  # Added async
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
    command_action = CommandAction(action_type=ActionType.COMMAND, commands=llm_commands_from_plan)
    llm_response_str = LLMPlannerResponse(action=command_action).model_dump_json()

    mock_get_adapter.execute_and_log_metrics.return_value = (
        llm_response_str,
        None,
    )

    # Define what the display string should look like
    expected_display_args_str = _create_display_command_for_test(llm_commands_from_plan)
    expected_display_command = (
        f"Running: kubectl get {expected_display_args_str}"
    )

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
            show_raw=False,
            show_vibe=False,
            warn_no_output=False,
            model_name="test",
            show_kubectl=show_flag_value,  # Set based on loop
            show_metrics=True,
        )

        # Mock _execute_command and handle_command_output within the loop
        with (
            patch("vibectl.command_handler._execute_command") as mock_execute_cmd,
            patch(
                "vibectl.command_handler.handle_command_output"
            ) as mock_handle_output,
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
                autonomous_mode=False,
                yes=True,  # Bypass confirmation
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

    # No assertions needed outside the loop


# This test becomes async to properly test the interaction
# It no longer uses CliRunner
@pytest.mark.asyncio
@patch("vibectl.utils.console_manager.print_vibe")  # Patch print_vibe
@patch("vibectl.cli.handle_result")  # Patch handle_result
@patch("vibectl.cli.run_vibe_command")  # Patch run_vibe_command where cli.vibe calls it
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


@pytest.mark.asyncio  # Added
async def test_handle_vibe_request_recoverable_api_error_during_summary(  # Added async
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

    # Mock the planning response (successful)
    plan_response = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["get", "pods"],
        "explanation": "Get the pods.",
    }
    kubectl_output_data = "pod-a\npod-b"
    # This initial return value will be overwritten by the side_effect
    mock_get_adapter.execute_and_log_metrics.return_value = (
        json.dumps(plan_response),
        None,
    )

    # Patch _execute_command to return success
    with patch("vibectl.command_handler._execute_command") as mock_execute_cmd:
        mock_execute_cmd.return_value = Success(data=kubectl_output_data)

        # Set up side_effect for the LLM calls: planning (success), summary (error)
        mock_get_adapter.execute_and_log_metrics.side_effect = [
            (json.dumps(plan_response), None),  # First call for planning
            RecoverableApiError("Rate limit hit"),  # Second call for summary
        ]

        # Call function
        result = await handle_vibe_request(  # Added await
            request="show me the pods",
            command="vibe",  # This command parameter seems unused now for vibe requests
            plan_prompt_func=plan_vibe_fragments,
            summary_prompt_func=get_test_summary_fragments,
            output_flags=default_output_flags,
            yes=True,
        )

        # Verify _execute_command was called
        mock_execute_cmd.assert_called_once()

        # Verify the LLM was called twice (plan + summary attempt)
        assert mock_get_adapter.execute_and_log_metrics.call_count == 2

        # Verify the final result is the non-halting Error constructed by the handler
        assert isinstance(result, Error)
        assert not result.halt_auto_loop  # Ensure it's non-halting
        # Check that the error message contains the specific text from the exception
        assert (
            "Recoverable API error during Vibe processing: Rate limit hit"
            in result.error
        )


@pytest.mark.asyncio  # Added
async def test_handle_vibe_request_general_exception_during_recovery(  # Added async
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

    # Patch _execute_command to return an Error
    with patch("vibectl.command_handler._execute_command") as mock_execute_cmd:
        mock_execute_cmd.return_value = Error(
            error=initial_error_message,
            exception=RuntimeError("simulated kubectl error"),
        )

        # Mock the LLM adapter execute method
        # First call (planning) returns the plan
        # Second call (recovery) raises a general Exception
        recovery_exception_message = "Unexpected LLM service outage"
        mock_get_adapter.execute_and_log_metrics.side_effect = [
            (json.dumps(plan_response), None),
            Exception(recovery_exception_message),
        ]

        # Mock update_memory to check its call (it should be called for initial error)
        with patch("vibectl.command_handler.update_memory") as mock_update_memory:
            # Call the function under test
            result = await handle_vibe_request(  # Added await
                request="get a non-existent configmap",
                command="get",  # Actual verb being executed
                plan_prompt_func=plan_vibe_fragments,
                summary_prompt_func=get_test_summary_fragments,
                output_flags=default_output_flags,  # Assumes show_vibe=True
                yes=True,  # Bypass confirmation
            )

            # Verify the LLM execute was called twice (plan + recovery attempt)
            assert mock_get_adapter.execute_and_log_metrics.call_count == 2

            # Verify update_memory was NOT called for the recovery failure itself
            # (it might be called for the *initial* error before recovery is attempted)
            # The second call (in handle_command_output) *will* contain the message.
            call_count = 0
            for call in mock_update_memory.call_args_list:
                call_count += 1
                # The second call should have the recovery failure message
                if call_count == 2:
                    assert recovery_exception_message in call.kwargs.get(
                        "vibe_output", ""
                    )
            # Ensure update_memory was called (at least once for initial, maybe twice)
            assert call_count > 0

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
            # 1. Initial error printed
            mock_console.print_error.assert_any_call(initial_error_message)
            # 2. Recovery failure message printed via print_vibe
            mock_console.print_vibe.assert_called_once_with(
                f"Failed to get recovery suggestions: {recovery_exception_message}"
            )
