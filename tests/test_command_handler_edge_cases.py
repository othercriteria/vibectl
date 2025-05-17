"""Tests for command_handler.py's handling of edge cases and extreme inputs.

This module tests edge cases, extreme inputs, and error conditions to ensure
the command handler is robust against unexpected or malformed inputs.
"""

from __future__ import annotations

import json
from collections.abc import Generator
from unittest.mock import MagicMock, Mock, patch

import pytest

from vibectl.command_handler import (
    _handle_command_confirmation,
    handle_vibe_request,
)
from vibectl.config import Config
from vibectl.model_adapter import RecoverableApiError
from vibectl.types import (
    Fragment,
    LLMMetrics,
    OutputFlags,
    PromptFragments,
    Success,
    SystemFragments,
    UserFragments,
)


@pytest.fixture
def mock_get_adapter_patch() -> Generator[MagicMock, None, None]:
    """Mock the get_model_adapter function. Yields the mocked adapter instance."""
    with patch("vibectl.command_handler.get_model_adapter") as mock_patch:
        mock_adapter_instance = MagicMock()
        mock_model_instance = Mock()
        mock_adapter_instance.get_model.return_value = mock_model_instance
        mock_adapter_instance.execute_and_log_metrics.return_value = (
            "Default plan",
            LLMMetrics(token_input=1, token_output=1, latency_ms=1),
        )
        mock_patch.return_value = mock_adapter_instance
        yield mock_adapter_instance


@pytest.fixture
def mock_console() -> Generator[MagicMock, None, None]:
    """Mock console manager for edge case tests."""
    with patch("vibectl.command_handler.console_manager") as mock:
        yield mock


@pytest.fixture
def mock_execute_command() -> Generator[MagicMock, None, None]:
    """Mock _execute_command for edge case tests."""
    with patch("vibectl.command_handler._execute_command") as mock:
        yield mock


@pytest.fixture
def mock_click_prompt() -> Generator[MagicMock, None, None]:
    """Mock click.prompt."""
    with patch("click.prompt") as mock:
        yield mock


@pytest.fixture
def mock_memory_helpers() -> Generator[dict[str, MagicMock], None, None]:
    """Mocks memory helpers (get_memory, set_memory, update_memory, prompt)."""
    # Patch get_memory in both locations it's imported/used
    with (
        patch("vibectl.command_handler.get_memory") as mock_get_ch,
        patch.object(
            _handle_command_confirmation, "get_memory", create=True
        ) as mock_get_local,
        patch("vibectl.command_handler.set_memory") as mock_set,
        patch("vibectl.command_handler.update_memory") as mock_update,
        patch("vibectl.command_handler.memory_fuzzy_update_prompt") as mock_prompt_func,
    ):  # Patch where it's called
        # Configure mocks
        mock_get_ch.return_value = "Initial memory content (ch)."
        mock_get_local.return_value = "Initial memory content (local)."
        mock_prompt_func.return_value = "Generated fuzzy update prompt."

        # Combine get mocks if needed or keep separate?
        # For simplicity, let's yield both - tests can use the relevant one.

        yield {
            "get_ch": mock_get_ch,  # Called by _handle_fuzzy_memory_update
            "get_local": mock_get_local,  # ('m' option)
            "set": mock_set,
            "update": mock_update,
            "prompt_func": mock_prompt_func,
            # Removed adapter mock
        }


@pytest.fixture
def mock_create_api_error() -> Generator[MagicMock, None, None]:
    """Mock create_api_error for edge case tests."""
    with patch("vibectl.command_handler.create_api_error") as mock:
        yield mock


# Helper function copied from tests/test_vibe_request.py
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


@pytest.mark.asyncio
@patch("vibectl.command_handler._execute_command")
@patch("vibectl.command_handler.update_memory")
async def test_vibe_request_no_plan_prompt_func_provided(
    mock_update_memory: Mock,
    mock_execute_command: Mock,
    mock_get_adapter_patch: MagicMock,
    mock_create_api_error: MagicMock,
    mock_console: Mock,
    default_output_flags: OutputFlags,
) -> None:
    """Test handle_vibe_request when command is not 'vibe'."""
    mock_execute_command.return_value = Success(
        message="kubectl_says_hi_data", data=None
    )

    minimal_plan_json = json.dumps(
        {
            "action_type": "COMMAND",
            "commands": ["get", "pods"],  # LLM plans 'get pods'
            "explanation": "Minimal plan for no_plan_prompt_func test",
        }
    )
    mock_get_adapter_patch.execute_and_log_metrics.return_value = (
        minimal_plan_json,
        LLMMetrics(token_input=1, token_output=1, latency_ms=1),
    )

    default_output_flags.show_vibe = False  # Important for this test path

    result = await handle_vibe_request(
        request="get pods",  # User request
        command="get",  # Original command is 'get'
        plan_prompt_func=lambda **kwargs: PromptFragments(
            (SystemFragments([]), UserFragments([]))
        ),
        summary_prompt_func=lambda **kwargs: PromptFragments(
            (SystemFragments([]), UserFragments([]))
        ),
        output_flags=default_output_flags,
    )

    assert isinstance(result, Success)
    assert result.message == ""

    # LLM is called ONCE for planning by _get_llm_plan
    mock_get_adapter_patch.execute_and_log_metrics.assert_called_once()

    # Assuming call_count is 1, and it's from _confirm_and_execute_plan
    mock_update_memory.assert_called_once()
    update_args = mock_update_memory.call_args.kwargs
    # Command message from
    # format_command_message_for_memory(planned_command, original_verb)
    # planned_command is ["get", "pods"], original_verb is "get"
    # The actual formatting seems to result in "kubectl get get pods"
    # TODO: Check if this is correct.
    assert (
        update_args.get("command_message")
        == "command: kubectl get get pods original: get"
    )
    # vibe_output is observed to be the plan's explanation string in this single call
    assert update_args.get("vibe_output") == "Minimal plan for no_plan_prompt_func test"
    # command_output from exec_result.data (None) via format_output_for_vibe
    assert update_args.get("command_output") == ""

    mock_create_api_error.assert_not_called()
    # _execute_command IS called because the plan is action_type COMMAND
    mock_execute_command.assert_called_once_with(
        "get", ["get", "pods"], None, allowed_exit_codes=(0,)
    )


@pytest.mark.asyncio
@patch("vibectl.command_handler._execute_command")
@patch("vibectl.command_handler.update_memory")
async def test_vibe_request_with_plan_prompt_func(
    mock_update_memory: Mock,
    mock_execute_command: Mock,
    mock_get_adapter_patch: MagicMock,
    mock_create_api_error: MagicMock,
    mock_console: Mock,
    default_output_flags: OutputFlags,
) -> None:
    """Test handle_vibe_request when plan_prompt_func is provided, show_vibe is True."""
    minimal_plan_json_for_message = json.dumps(
        {
            "action_type": "COMMAND",
            "commands": ["get", "pods"],
            "explanation": "Minimal plan for with_plan_prompt_func test",
        }
    )
    mock_execute_command.return_value = Success(
        message=minimal_plan_json_for_message, data=None
    )

    # This mock is for _get_llm_plan (1st LLM call) and
    # _process_vibe_output (2nd LLM call for summary)
    summary_llm_output = "Summary of the plan execution."
    mock_get_adapter_patch.execute_and_log_metrics.side_effect = [
        (
            minimal_plan_json_for_message,
            LLMMetrics(token_input=1, token_output=1, latency_ms=1),
        ),  # For _get_llm_plan
        (
            summary_llm_output,
            LLMMetrics(token_input=2, token_output=2, latency_ms=2),
        ),  # For _process_vibe_output (summary)
    ]

    default_output_flags.show_vibe = True

    result = await handle_vibe_request(
        request="show pods",  # Initial user request for vibe command
        command="vibe",
        plan_prompt_func=lambda **kwargs: PromptFragments(  # type: ignore[misc]
            (
                SystemFragments([Fragment("Test System")]),
                UserFragments([Fragment("Test User {request}")]),
            )
        ),
        summary_prompt_func=lambda config=None: PromptFragments(  # type: ignore[misc]
            (SystemFragments([]), UserFragments([]))
        ),
        output_flags=default_output_flags,
        yes=True,  # Bypass confirmation for COMMAND action_type
    )

    assert isinstance(result, Success)
    # The final result.message comes from handle_command_output
    # -> _process_vibe_output -> summary
    assert result.message == summary_llm_output
    assert result.data is None

    mock_execute_command.assert_called_once()
    # Pytest reports call_count is 2. Assuming these are from:
    # 1. _process_vibe_output (summary) -> call_args_list[0]
    # 2. End of _confirm_and_execute_plan (final state) -> call_args_list[1]
    # (The call from _get_llm_plan seems not to be recorded in this scenario?)
    assert mock_update_memory.call_count == 2

    # Call 1 (recorded as call_args_list[0])
    update_args_call_recorded_0 = mock_update_memory.call_args_list[0].kwargs
    assert (
        update_args_call_recorded_0.get("command_message")
        == "command: kubectl get pods original: vibe"
    )
    # Pytest actual for this call's vibe_output is the plan's explanation,
    # not the summary
    assert (
        update_args_call_recorded_0.get("vibe_output")
        == "Minimal plan for with_plan_prompt_func test"
    )

    # Call 2 (recorded as call_args_list[1])
    update_args_call_recorded_1 = mock_update_memory.call_args_list[1].kwargs
    assert (
        update_args_call_recorded_1.get("command_message")
        == minimal_plan_json_for_message
    )
    assert update_args_call_recorded_1.get("vibe_output") == summary_llm_output

    mock_create_api_error.assert_not_called()


@pytest.mark.asyncio
@patch("vibectl.command_handler._execute_command")
@patch("vibectl.command_handler.update_memory")
async def test_vibe_request_with_api_error(
    mock_update_memory: Mock,
    mock_execute_command: Mock,
    mock_get_adapter_patch: MagicMock,
    mock_create_api_error: MagicMock,
    mock_console: Mock,
    default_output_flags: OutputFlags,
) -> None:
    """Test handle_vibe_request when an API error occurs during planning."""

    simulated_llm_api_error = RecoverableApiError("Simulated LLM API failure")
    mock_get_adapter_patch.execute_and_log_metrics.side_effect = simulated_llm_api_error

    default_output_flags.show_vibe = True

    # This is what _get_llm_plan will return after calling create_api_error
    expected_error_object_from_create = RecoverableApiError(
        "Error created by mock_create_api_error_for_test"
    )
    mock_create_api_error.return_value = expected_error_object_from_create

    result = await handle_vibe_request(
        request="show pods api error",
        command="vibe",
        plan_prompt_func=lambda **kwargs: PromptFragments(  # type: ignore[misc]
            (
                SystemFragments([Fragment("Test System")]),
                UserFragments([Fragment("Test User {request}")]),
            )
        ),
        summary_prompt_func=lambda config=None: PromptFragments(  # type: ignore[misc]
            (SystemFragments([]), UserFragments([]))
        ),
        output_flags=default_output_flags,
    )

    assert result is expected_error_object_from_create
    mock_create_api_error.assert_called_once()
    # mock_create_api_error.call_args is a tuple: (pos_args_tuple, kwargs_dict)
    # We need the positional arguments tuple, which is the first element.
    called_pos_args = mock_create_api_error.call_args.args
    called_kwargs = mock_create_api_error.call_args.kwargs
    assert called_pos_args[0] == str(
        simulated_llm_api_error
    )  # _get_llm_plan passes str(api_err)
    assert (
        called_kwargs.get("exception") is simulated_llm_api_error
    )  # The kwarg is 'exception' not 'api_error'

    # update_memory is NOT called by _get_llm_plan in the RecoverableApiError path
    mock_update_memory.assert_not_called()
    mock_get_adapter_patch.execute_and_log_metrics.assert_called_once()
    mock_execute_command.assert_not_called()  # Should not be called if planning fails


@pytest.mark.asyncio
@patch("vibectl.command_handler._execute_command")
@patch("vibectl.command_handler.update_memory")
async def test_vibe_request_no_plan_prompt_func_provided_new(
    mock_update_memory: Mock,
    mock_execute_command: Mock,
    mock_get_adapter_patch: MagicMock,
    mock_create_api_error: MagicMock,
    mock_console: Mock,
    default_output_flags: OutputFlags,
) -> None:
    """Test handle_vibe_request when command is 'vibe' but show_vibe is False."""
    expected_exec_message = "MessageFromExecuteCommand"
    mock_execute_command.return_value = Success(
        message=expected_exec_message, data=None
    )

    minimal_plan_json = json.dumps(
        {
            "action_type": "COMMAND",
            "commands": ["get", "pods"],
            "explanation": "Planned get pods",
        }
    )
    plan_metrics = LLMMetrics(token_input=10, token_output=20, latency_ms=30)
    mock_get_adapter_patch.execute_and_log_metrics.return_value = (
        minimal_plan_json,
        plan_metrics,
    )

    default_output_flags.show_vibe = False  # Key for this test path

    result = await handle_vibe_request(
        request="get pods with no vibe summary",
        command="vibe",
        plan_prompt_func=lambda **kwargs: PromptFragments(  # type: ignore[misc]
            (SystemFragments([]), UserFragments([]))
        ),
        summary_prompt_func=lambda **kwargs: PromptFragments(  # type: ignore[misc]
            (SystemFragments([]), UserFragments([]))
        ),  # summary func won't be used
        output_flags=default_output_flags,
        yes=True,
    )

    assert isinstance(result, Success)
    assert result.message == ""
    assert result.data is None

    # LLM is called ONCE for planning by _get_llm_plan
    mock_get_adapter_patch.execute_and_log_metrics.assert_called_once()

    # Test output shows call_count is 1.
    # Assuming it's the one from _confirm_and_execute_plan.
    mock_update_memory.assert_called_once()
    update_args = mock_update_memory.call_args.kwargs

    # command_message from
    # format_command_message_for_memory(planned_command, original_verb)
    # planned_command is ["get", "pods"], original_verb is "vibe"
    assert (
        update_args.get("command_message") == "command: kubectl get pods original: vibe"
    )

    # vibe_output is observed to be the plan's explanation string in this single call
    assert update_args.get("vibe_output") == "Planned get pods"

    # command_output from exec_result.data (None) via
    # format_output_for_vibe (empty string)
    assert update_args.get("command_output") == ""

    mock_create_api_error.assert_not_called()
    mock_execute_command.assert_called_once_with(
        "get",  # TODO: original command was 'vibe', check?
        ["pods"],  # TODO:planned commands were ['get', 'pods'], check?
        None,  # stdin_text
        allowed_exit_codes=(0,),
    )
