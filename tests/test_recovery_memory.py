"""Tests for recovery suggestions integration with memory.

This test file verifies that recovery suggestions from failed commands
are properly integrated into memory. This is important for vibectl auto mode,
where recovery suggestions from one command should be available for subsequent commands.

The tests verify:
1. That update_memory is called when recovery suggestions are available
2. That the recovery suggestions are passed to update_memory
3. That this correctly happens when used in auto mode
"""

from collections.abc import Generator
from unittest.mock import MagicMock, Mock, patch

import pytest

from vibectl.config import Config
from vibectl.execution.vibe import handle_vibe_request
from vibectl.model_adapter import LLMModelAdapter
from vibectl.prompts.vibe import plan_vibe_fragments
from vibectl.schema import ActionType, CommandAction, LLMPlannerResponse
from vibectl.types import (
    Error,
    Fragment,
    OutputFlags,
    PromptFragments,
    Success,
    SystemFragments,
    UserFragments,
)


@pytest.fixture
def clean_memory() -> Generator[None, None, None]:
    """Fixture to ensure clean memory state for tests."""
    from vibectl.memory import get_memory, set_memory

    # Save current memory
    original_memory = get_memory()

    # Clear memory for tests
    set_memory("")

    yield

    # Restore original memory
    set_memory(original_memory)


@pytest.fixture
def mock_execute() -> Generator[MagicMock, None, None]:
    """Mock vibectl.execution.vibe._execute_command."""
    with patch("vibectl.execution.vibe._execute_command") as mock:
        yield mock


@pytest.fixture
def mock_console() -> Generator[MagicMock, None, None]:
    """Mocks the console manager instance."""
    with patch("vibectl.console.console_manager") as mock_console_mgr:
        yield mock_console_mgr


@pytest.fixture
def mock_get_adapter() -> Generator[MagicMock, None, None]:
    """Mock the get_model_adapter function. Yields the mocked adapter instance."""
    with patch("vibectl.command_handler.get_model_adapter") as mock_patch:
        mock_adapter_instance = MagicMock(spec=LLMModelAdapter)
        # get_model should return a mock model object
        mock_model_obj = MagicMock()
        mock_adapter_instance.get_model.return_value = mock_model_obj
        mock_patch.return_value = mock_adapter_instance
        yield mock_adapter_instance


@pytest.fixture
def output_flags() -> OutputFlags:
    """Provide standard OutputFlags for recovery tests."""
    return OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
        show_kubectl=True,  # Ensure kubectl command is shown if generated
        warn_no_proxy=True,
        show_metrics=True,
    )


# Dummy summary prompt function that returns fragments
def get_test_summary_fragments(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Dummy summary prompt function for testing that returns fragments."""
    return PromptFragments(
        (
            SystemFragments([Fragment("System fragment with {output}")]),
            UserFragments([Fragment("User fragment with {output}")]),
        )
    )


@pytest.mark.asyncio
@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler.update_memory")
@patch("vibectl.execution.vibe._execute_command")
@patch("vibectl.execution.vibe._get_llm_plan")
async def test_recovery_suggestions_should_update_memory(
    mock_get_llm_plan: MagicMock,
    mock_execute: Mock,
    mock_ch_update_memory: Mock,
    mock_ch_get_model_adapter: MagicMock,  # For recovery path in handle_command_output
) -> None:
    """Test that memory should be updated with recovery suggestions."""
    # Setup: Define the plan object that _get_llm_plan (mock_get_llm_plan) should return
    command_action_plan = CommandAction(
        action_type=ActionType.COMMAND, commands=["get", "pods"]
    )
    llm_plan_obj = LLMPlannerResponse(action=command_action_plan)
    # _get_llm_plan now returns a Success object containing the plan
    mock_get_llm_plan.return_value = Success(data=llm_plan_obj)

    # _execute_command (kubectl) fails
    original_error = Error(error="Pod not found", exception=None)
    mock_execute.return_value = original_error

    # Mocking for recovery call via handle_command_output, which uses
    # command_handler.get_model_adapter
    recovery_suggestion_text = "Oops: Pod not found. Try 'kubectl get pods -A'."
    adapter_for_recovery = MagicMock(spec=LLMModelAdapter)
    adapter_for_recovery.get_model.return_value = MagicMock()
    adapter_for_recovery.execute_and_log_metrics.return_value = (
        recovery_suggestion_text,
        None,
    )
    mock_ch_get_model_adapter.return_value = adapter_for_recovery

    output_flags_mock = Mock(spec=OutputFlags)
    output_flags_mock.model_name = "test-model"
    output_flags_mock.show_vibe = True
    output_flags_mock.show_raw = True
    output_flags_mock.show_kubectl = True

    result = await handle_vibe_request(
        request="show the pods",
        command="vibe",
        plan_prompt_func=plan_vibe_fragments,
        summary_prompt_func=get_test_summary_fragments,
        output_flags=output_flags_mock,
    )

    assert isinstance(result, Error)
    assert result.recovery_suggestions == recovery_suggestion_text
    mock_ch_update_memory.assert_called()


@pytest.mark.asyncio
@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler.update_memory")
@patch("vibectl.execution.vibe._execute_command")
@patch("vibectl.execution.vibe._get_llm_plan")
async def test_recovery_suggestions_in_auto_mode(
    mock_get_llm_plan: MagicMock,
    mock_execute: Mock,
    mock_ch_update_memory: Mock,
    mock_ch_get_model_adapter: MagicMock,
) -> None:
    """Test recovery suggestions in auto mode should update memory."""
    # Setup: Define the plan object that _get_llm_plan (mock_get_llm_plan) should return
    initial_command_action = CommandAction(
        action_type=ActionType.COMMAND, commands=["get", "pods"]
    )
    initial_llm_plan_obj = LLMPlannerResponse(action=initial_command_action)
    # _get_llm_plan now returns a Success object containing the plan
    mock_get_llm_plan.return_value = Success(data=initial_llm_plan_obj)

    # _execute_command (kubectl) fails
    original_error = Error(error="Pod not found", exception=None)
    mock_execute.return_value = (
        original_error  # Using return_value as it's called once for the initial plan
    )

    # Mocking for recovery call via handle_command_output
    recovery_suggestion_text = "Error occurred: Pod not found. Trying again with -A."
    adapter_for_recovery = MagicMock(spec=LLMModelAdapter)
    adapter_for_recovery.get_model.return_value = MagicMock()
    adapter_for_recovery.execute_and_log_metrics.return_value = (
        recovery_suggestion_text,
        None,
    )
    mock_ch_get_model_adapter.return_value = adapter_for_recovery

    output_flags_mock = Mock(spec=OutputFlags)
    output_flags_mock.model_name = "test-model"
    output_flags_mock.show_vibe = True
    output_flags_mock.show_raw = True
    output_flags_mock.show_kubectl = True

    result1 = await handle_vibe_request(
        request="show the pods",
        command="vibe",
        plan_prompt_func=plan_vibe_fragments,
        summary_prompt_func=get_test_summary_fragments,
        output_flags=output_flags_mock,
        autonomous_mode=True,
    )

    assert isinstance(result1, Error)
    assert result1.recovery_suggestions == recovery_suggestion_text
    mock_ch_update_memory.assert_called()


@pytest.mark.asyncio
@patch("vibectl.execution.vibe.get_model_adapter")
@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler.update_memory")
@patch("vibectl.execution.vibe._execute_command")
@patch(
    "vibectl.execution.vibe.update_memory",
    return_value=None,
)
async def test_recovery_after_failed_command_with_llm_suggestion_accepted(
    mock_vibe_update_memory: Mock,
    mock_execute: MagicMock,
    mock_ch_update_memory: Mock,
    mock_get_adapter: MagicMock,
    mock_exec_vibe_get_model_adapter: MagicMock,
    mock_console: MagicMock,
    output_flags: OutputFlags,
) -> None:
    """Test recovery returns an annotated Error when LLM suggests a new command plan."""
    # Setup initial plan to be executed by handle_vibe_request
    initial_plan_action = CommandAction(
        action_type=ActionType.COMMAND, commands=["get", "pods"]
    )
    initial_llm_response_obj = LLMPlannerResponse(action=initial_plan_action)
    initial_plan_json = initial_llm_response_obj.model_dump_json()

    adapter_instance_for_initial_plan = MagicMock(spec=LLMModelAdapter)
    adapter_instance_for_initial_plan.get_model.return_value = MagicMock()
    adapter_instance_for_initial_plan.execute_and_log_metrics.return_value = (
        initial_plan_json,
        None,  # Metrics for initial plan
    )
    mock_exec_vibe_get_model_adapter.return_value = adapter_instance_for_initial_plan

    # Mock failed command execution for the initial plan
    original_error_message = "Pod 'test-pod-initial' not found"
    mock_execute.return_value = Error(error=original_error_message)

    # Mock LLM recovery suggestion (this is a new command plan)
    recovered_commands = ["kubectl", "get", "pods", "--all-namespaces"]
    recovered_action = CommandAction(
        action_type=ActionType.COMMAND, commands=recovered_commands
    )
    recovery_plan_obj = LLMPlannerResponse(action=recovered_action)
    recovery_plan_json_str = recovery_plan_obj.model_dump_json()

    adapter_instance_for_recovery = MagicMock(spec=LLMModelAdapter)
    adapter_instance_for_recovery.get_model.return_value = MagicMock()
    adapter_instance_for_recovery.execute_and_log_metrics.return_value = (
        recovery_plan_json_str,  # LLM returns a new plan as a string
        None,  # Metrics for recovery plan
    )
    mock_get_adapter.return_value = adapter_instance_for_recovery

    # User's choice for recovery prompt (if one was shown, which it isn't
    # for CommandAction recovery)
    # This mock is present but won't be called in this specific scenario.
    mock_console.get_selection.return_value = "y"

    # Call the function under test
    result = await handle_vibe_request(
        request="get a pod",
        command="vibe",  # original_command_verb is "vibe"; initial confirmation skipped
        plan_prompt_func=plan_vibe_fragments,
        summary_prompt_func=get_test_summary_fragments,
        output_flags=output_flags,
        yes=False,  # yes=False, but initial confirmation skipped for "vibe" command
    )

    # Assertions to verify the current behavior
    assert isinstance(result, Error), "Expected result to be an Error object"
    assert result.error == original_error_message, "Error message mismatch"
    assert result.recovery_suggestions == recovery_plan_json_str, (
        "Recovery suggestions mismatch"
    )
    assert result.halt_auto_loop is False, (
        "Expected halt_auto_loop to be False for successful recovery suggestion"
    )

    # Verify _execute_command was called once for the initial (failed) command
    mock_execute.assert_called_once_with("get", ["pods"], None, allowed_exit_codes=(0,))

    # Verify the LLM call for recovery suggestion
    # (via mock_get_adapter for command_handler.get_model_adapter)
    adapter_instance_for_recovery.execute_and_log_metrics.assert_called_once()

    # update_memory in command_handler should be called after recovery suggestion
    # is processed
    # This happens inside handle_command_output if recovery is successful.
    mock_ch_update_memory.assert_called_once()

    # update_memory in execution.vibe should be called for the initial command
    # execution record
    mock_vibe_update_memory.assert_called_once()
    vibe_mem_args = mock_vibe_update_memory.call_args.kwargs
    assert (
        vibe_mem_args.get("command_message")
        == "command: kubectl get pods original: vibe"
    )
    assert vibe_mem_args.get("command_output") == original_error_message

    # mock_console.get_selection should NOT have been called:
    # 1. Initial confirmation skipped for "vibe".
    # 2. CommandAction recovery suggestions in handle_command_output don't prompt.
    mock_console.get_selection.assert_not_called()
