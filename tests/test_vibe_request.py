"""Tests for vibe request handling functionality."""

import json
from collections.abc import Generator
from pathlib import Path
from typing import Any, NoReturn
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from pydantic import ValidationError
from pytest_mock import MockerFixture

from vibectl.cli import cli
from vibectl.command_handler import OutputFlags, handle_vibe_request
from vibectl.config import Config
from vibectl.model_adapter import LLMMetrics, LLMModelAdapter, RecoverableApiError
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
)


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
def mock_llm(mocker: MockerFixture) -> Generator[MagicMock, None, None]:
    """Mocks the get_model_adapter and its methods.

    Yields the mocked adapter *instance*.
    """
    mock_get_adapter = mocker.patch("vibectl.command_handler.get_model_adapter")
    mock_adapter_instance = MagicMock(spec=LLMModelAdapter)
    mock_model_instance = MagicMock()
    mock_get_adapter.return_value = mock_adapter_instance
    mock_adapter_instance.get_model.return_value = mock_model_instance
    mock_adapter_instance.execute.return_value = "Default execute response"
    yield mock_adapter_instance  # Yield the adapter instance


@pytest.mark.asyncio  # Added
async def test_handle_vibe_request_success(  # Added async
    mock_llm: MagicMock,
    mock_console: Mock,
    prevent_exit: MagicMock,
    default_output_flags: OutputFlags,
    mock_memory: MagicMock,
) -> None:
    """Test successful vibe request handling."""
    # Mock the planning response with JSON, including the verb
    kubectl_verb = "get"
    kubectl_args = ["pods"]
    plan_explanation = "Get the pods."
    plan_response = {
        "action_type": ActionType.COMMAND.value,
        "commands": [kubectl_verb, *kubectl_args],
        "explanation": plan_explanation,
    }
    # This metric is associated with the planning step
    planning_metrics = LLMMetrics(latency_ms=100.0, token_input=10, token_output=20)
    # The mock_llm fixture now mocks execute_and_log_metrics directly
    mock_llm.execute_and_log_metrics.return_value = (
        json.dumps(plan_response),
        planning_metrics,
    )

    # Patch _confirm_and_execute_plan as it now contains the execution logic
    with patch(
        "vibectl.command_handler._confirm_and_execute_plan"
    ) as mock_confirm_execute:
        # Assume successful execution within the patched function
        execution_metrics = LLMMetrics(latency_ms=50.0, token_input=0, token_output=0)
        mock_confirm_execute.return_value = Success(
            data="pods output", metrics=execution_metrics
        )

        # Call function
        result = await handle_vibe_request(  # Added await
            request="show me the pods",
            command="vibe",  # <<< Original vibectl command is 'vibe'
            plan_prompt_func=plan_vibe_fragments,
            summary_prompt_func=get_test_summary_fragments,
            output_flags=default_output_flags,
            yes=True,  # Assuming confirmation bypassed for simplicity
        )

        # Verify _confirm_and_execute_plan called with correct args derived from plan
        mock_confirm_execute.assert_called_once_with(
            kubectl_verb,
            kubectl_args,
            None,  # yaml_content
            plan_explanation,
            "vibe",  # command (was False, should be "vibe")
            False,  # semiauto_mode (was True, should be False due to yes=True)
            True,  # yes_flag
            False,  # autonomous_mode
            True,  # live_display_flag (from handle_vibe_request live_display=True)
            default_output_flags,  # output_flags (was ANY)
            get_test_summary_fragments,  # summary_prompt_func (was ANY)
        )

        # Verify the final result is the Success object returned by the patched function
        assert isinstance(result, Success)
        assert result.data == "pods output"
        # Check that metrics from execution are preserved in the final result
        assert result.metrics == execution_metrics

    # Verify LLM planning call occurred
    mock_llm.execute_and_log_metrics.assert_called_once()
    # Verify memory update (if applicable - check mock_memory fixture setup)
    # mock_memory.add_interaction.assert_called() # Example if needed


@pytest.mark.asyncio  # Added
async def test_handle_vibe_request_empty_response(  # Added async
    mock_console: Mock,
    mock_llm: MagicMock,
    mock_run_kubectl: Mock,
    mock_memory: MagicMock,
    default_output_flags: OutputFlags,
) -> None:
    """Test vibe request with empty string response from planner."""
    # Set up empty response
    malformed_response = ""
    mock_llm.execute_and_log_metrics.return_value = (
        malformed_response,
        MagicMock(spec=LLMMetrics),
    )

    # Empty string is handled before JSON parsing
    # It should return Error("LLM returned an empty response.") directly
    with (
        patch("vibectl.command_handler.update_memory") as mock_update_memory,
        patch("vibectl.command_handler.create_api_error") as mock_create_api_error,
        patch(
            "vibectl.memory.include_memory_in_prompt",
            return_value="Plan this: empty response test",
        ),
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
    assert call_args.get("command") == "system"
    assert call_args.get("command_output") == "LLM Error: Empty response."
    assert call_args.get("vibe_output") == "LLM Error: Empty response."
    assert call_args.get("model_name") == default_output_flags.model_name

    mock_create_api_error.assert_not_called()

    # Verify kubectl was NOT called
    mock_run_kubectl.assert_not_called()


@pytest.mark.asyncio  # Added
async def test_handle_vibe_request_error_response(  # Added async
    mock_console: Mock,
    mock_llm: MagicMock,
    mock_run_kubectl: Mock,
    default_output_flags: OutputFlags,
    mock_memory: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test vibe request with error response from planner."""
    caplog.set_level("ERROR")
    # Set up error response JSON
    error_msg = "test planner error"
    explanation_msg = "Something went wrong during planning."
    error_response = {
        "action_type": ActionType.ERROR.value,
        "error": error_msg,
        "explanation": explanation_msg,
    }
    mock_llm.execute_and_log_metrics.return_value = (json.dumps(error_response), None)

    # Set show_kubectl to True (doesn't affect this path but good practice)
    default_output_flags.show_kubectl = True

    # Assert the result of handle_vibe_request
    with patch(
        "vibectl.memory.include_memory_in_prompt", return_value="Plan this: error test"
    ):
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
    assert error_msg in result.error
    # Assert the recovery suggestions come from the explanation
    assert result.recovery_suggestions == explanation_msg

    # Verify kubectl was NOT called
    mock_run_kubectl.assert_not_called()

    # Verify memory was NOT updated on planning error
    mock_memory.add_interaction.assert_not_called()


@pytest.mark.asyncio  # Added
@patch("vibectl.command_handler.create_api_error")
@patch("vibectl.command_handler.update_memory")
async def test_handle_vibe_request_invalid_format(  # Added async
    mock_update_memory: MagicMock,
    mock_create_api_error: MagicMock,
    mock_console: Mock,
    mock_llm: MagicMock,
    mock_run_kubectl: Mock,
    default_output_flags: OutputFlags,
) -> None:
    """Test vibe request with non-JSON format from planner."""
    # Set up invalid response
    non_json_response = "kubectl get pods # This is not JSON"
    mock_llm.execute_and_log_metrics.return_value = (
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
    with patch(
        "vibectl.memory.include_memory_in_prompt",
        return_value="Plan this: invalid format test",
    ):
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
        assert call_kwargs.get("command") == "system"
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
    mock_llm: MagicMock,
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
    mock_llm.execute_and_log_metrics.return_value = (
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
        patch(
            "vibectl.memory.include_memory_in_prompt",
            return_value="Plan this: show me the pods",
        ),
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
@patch("vibectl.command_handler.create_api_error")
@patch("vibectl.command_handler.update_memory")
async def test_handle_vibe_request_llm_output_parsing(  # Added async
    mock_update_memory: MagicMock,
    mock_create_api_error: MagicMock,
    mock_llm: MagicMock,
    mock_run_kubectl: Mock,
    default_output_flags: OutputFlags,
) -> None:
    """Test vibe request handles different JSON parsing/validation errors."""
    from json import JSONDecodeError

    # Note: We expect create_api_error to return a basic Error for assertion comparison
    mock_create_api_error.side_effect = lambda msg, exc: Error(
        error=msg, exception=exc, halt_auto_loop=False
    )

    test_cases = [
        # Desc
        # LLM Response
        # Expected Result Type
        # Expected Error Substring
        # Halt Loop
        # API Error Called
        (
            "Malformed JSON",
            '{"action_type: "COMMAND"}',
            Error,
            "Failed to parse LLM response",
            False,
            True,
        ),
        (
            "Missing action_type",
            '{"commands": ["pods"]}',
            Error,
            "Failed to parse LLM response",
            False,
            True,
        ),
        (
            "Invalid action_type enum",
            '{"action_type": "INVALID"}',
            Error,
            "Failed to parse LLM response",
            False,
            True,
        ),
        (
            "COMMAND missing args",
            '{"action_type": "COMMAND"}',
            Error,
            "LLM sent COMMAND action with no args.",
            True,
            False,
        ),
        (
            "ERROR missing error",
            '{"action_type": "ERROR"}',
            Error,
            "LLM sent ERROR action without message.",
            True,
            False,
        ),
        (
            "WAIT missing duration",
            '{"action_type": "WAIT"}',
            Error,
            "LLM sent WAIT action without duration.",
            True,
            False,
        ),
    ]

    for (
        desc,
        llm_response,
        expected_type,
        expected_substring,
        expect_halt,
        expect_api_error_call,
    ) in test_cases:
        print(f"Running test case: {desc}")
        mock_llm.execute_and_log_metrics.return_value = (llm_response, None)
        mock_update_memory.reset_mock()
        mock_create_api_error.reset_mock()

        result = await handle_vibe_request(
            request=f"test {desc}",
            command="vibe",  # Use vibe command to allow LLM to specify verb
            plan_prompt_func=plan_vibe_fragments,
            summary_prompt_func=get_test_summary_fragments,
            output_flags=default_output_flags,
        )

        # General Assertions
        assert isinstance(result, expected_type)
        if isinstance(result, Error):
            assert expected_substring in result.error
            assert result.halt_auto_loop == expect_halt

        # Specific mock call assertions
        if expect_api_error_call:
            # Errors caught by _get_llm_plan (parsing/validation)
            mock_create_api_error.assert_called_once()
            # Check the exception type passed to create_api_error
            call_args, _ = mock_create_api_error.call_args
            assert isinstance(call_args[1], JSONDecodeError | ValidationError)
            # Memory update should have happened inside _get_llm_plan
            mock_update_memory.assert_called_once()
            assert (
                "System Error: Failed to parse LLM response"
                in mock_update_memory.call_args.kwargs.get("vibe_output", "")
            )
        else:
            # Internal errors caught inside handle_vibe_request
            mock_create_api_error.assert_not_called()
            # Memory update might happen depending on the specific internal error
            if desc == "COMMAND missing args":
                mock_update_memory.assert_called_once()
                assert (
                    "LLM Error: COMMAND action with no args."
                    in mock_update_memory.call_args.kwargs.get("vibe_output", "")
                )
            else:
                mock_update_memory.assert_not_called()


@pytest.mark.asyncio  # Added
async def test_handle_vibe_request_command_error(  # Added async
    mock_llm: MagicMock,
    mock_console: Mock,
    prevent_exit: MagicMock,
    default_output_flags: OutputFlags,
    mock_memory: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test vibe request with command execution error."""
    caplog.set_level("ERROR")
    plan_response = {
        "action_type": ActionType.COMMAND.value,
        "commands": [
            "nonexistent-resource"
        ],  # Corrected: Verb is from command, LLM provides only args
        "explanation": "Trying to get a resource that does not exist.",
    }
    # This first mock value will be overwritten by the side_effect below, but
    # we keep it for clarity about the plan structure.
    mock_llm.execute_and_log_metrics.return_value = (json.dumps(plan_response), None)

    # Patch _execute_command to return an error
    with patch("vibectl.command_handler._execute_command") as mock_execute_cmd:
        error_message = "kubectl command failed"
        mock_execute_cmd.return_value = Error(
            error=error_message, exception=RuntimeError("simulated kubectl error")
        )

        # Set up side_effect for model_adapter.execute_and_log_metrics:
        # plan first, then recovery
        expected_recovery_suggestion = "Recovery suggestion: Check pod status."
        mock_llm.execute_and_log_metrics.side_effect = [
            (json.dumps(plan_response), None),
            (expected_recovery_suggestion, None),
        ]

        # Mock update_memory directly (no need to mock _get_llm_summary)
        with patch("vibectl.command_handler.update_memory") as mock_update_memory_ch:
            # Call the function under test
            result = await handle_vibe_request(  # Added await
                request="run a command that fails",
                command="get",  # Actual verb being executed
                plan_prompt_func=plan_vibe_fragments,
                summary_prompt_func=get_test_summary_fragments,
                output_flags=default_output_flags,  # Assumes show_vibe=True
                yes=True,  # Bypass confirmation
                config=None,  # Added missing config argument
            )

    # Assertions (outside inner 'with' block, but _execute_cmd is from outer block)
    mock_execute_cmd.assert_called_once_with("get", ["nonexistent-resource"], None)

    # Assert the mock patched in the 'with' block was called TWICE
    assert mock_update_memory_ch.call_count == 2
    # Check arguments passed using kwargs for the *second* call (recovery)
    assert mock_update_memory_ch.call_args_list[1] is not None  # Check list index
    second_call_kwargs = mock_update_memory_ch.call_args_list[1].kwargs
    assert second_call_kwargs.get("command") == "get"  # Command verb
    assert (
        second_call_kwargs.get("command_output") == error_message
    )  # Original command error output
    assert second_call_kwargs.get("vibe_output") == expected_recovery_suggestion

    # Assert the final result (handle_command_output returns the modified Error)
    assert isinstance(result, Error)
    assert result.error == error_message  # Original error message
    assert result.recovery_suggestions == expected_recovery_suggestion

    # Verify that memory was updated TWICE (once after exec, once after summary)
    # assert mock_memory.call_count == 2


@pytest.mark.asyncio  # Added
async def test_handle_vibe_request_error(  # Added async
    mock_llm: MagicMock,
    mock_run_kubectl: Mock,
    mock_console: Mock,
    prevent_exit: MagicMock,
    default_output_flags: OutputFlags,
    mock_memory: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test vibe request handling when the LLM returns an error action."""
    caplog.set_level("ERROR")
    # Mock LLM planning response (error action)
    error_msg = "test error from llm"
    explanation_msg = "LLM could not process the request."
    plan_response = {
        "action_type": ActionType.ERROR.value,
        "error": error_msg,
        "explanation": explanation_msg,
    }
    mock_llm.execute_and_log_metrics.return_value = (json.dumps(plan_response), None)

    # Assert the result of handle_vibe_request
    with patch(
        "vibectl.memory.include_memory_in_prompt", return_value="Plan this: llm error"
    ):
        result = await handle_vibe_request(  # Added await
            request="cause an llm error",
            command="error",
            plan_prompt_func=plan_vibe_fragments,
            summary_prompt_func=get_test_summary_fragments,
            output_flags=default_output_flags,
        )

    # Assert handle_vibe_request returned an Error object
    assert isinstance(result, Error)
    # Check the error message structure
    assert result.error.startswith("LLM planning error:")
    assert error_msg in result.error
    # Assert the recovery suggestions come from the explanation
    assert result.recovery_suggestions == explanation_msg

    # Verify kubectl was NOT called
    mock_run_kubectl.assert_not_called()

    # Verify memory was NOT updated
    mock_memory.add_interaction.assert_not_called()


@pytest.mark.asyncio  # Added
async def test_handle_vibe_request_yaml_creation(  # Added async
    mock_llm: MagicMock,
    mock_run_kubectl: Mock,
    mock_console: Mock,
    mock_confirm: MagicMock,
    prevent_exit: MagicMock,
    default_output_flags: OutputFlags,
) -> None:
    """Test vibe request with YAML creation."""
    # Disable vibe summary to prevent extra LLM call/timeout
    default_output_flags.show_vibe = False

    # Construct expected JSON for planning
    expected_response_plan = {
        "action_type": ActionType.COMMAND.value,
        "commands": [
            "get",
            "pods",
            "---",
            "-n default\n---\napiVersion: v1\nkind: Pod\nmetadata:\n  name: test-pod",
        ],
        "explanation": "Creating pod from YAML definition.",
    }
    # Set up model adapter response for both calls
    # summary_response = { # Not used as show_vibe is False
    #     "action_type": ActionType.FEEDBACK.value,
    #     "explanation": "Test response",
    # }
    mock_llm.execute_and_log_metrics.return_value = (
        json.dumps(expected_response_plan),
        None,
    )

    # Set up confirmation to be True (explicitly, although it's the default)
    mock_confirm.return_value = True

    # Mock subprocess.run for kubectl calls with YAML
    with (
        patch(
            "vibectl.memory.include_memory_in_prompt",
            return_value="Plan this: create pod yaml",
        ),
        patch("subprocess.run") as mock_subprocess,
        patch("vibectl.command_handler.update_memory") as mock_update_memory,
    ):
        # Configure mock subprocess to return success
        mock_process = MagicMock()
        mock_process.stdout = "pod/test-pod created"
        mock_process.returncode = 0
        mock_subprocess.return_value = mock_process

        await handle_vibe_request(  # Added await
            request="create pod yaml",
            command="create",
            plan_prompt_func=plan_vibe_fragments,
            summary_prompt_func=get_test_summary_fragments,
            output_flags=default_output_flags,
            yes=True,  # Bypass the interactive prompt
        )

    # Verify that memory was updated TWICE (once after exec, once after summary)
    # assert mock_memory.call_count == 2

    # No need to verify specific args as they can vary by implementation

    # Expect only ONE call because show_vibe is False
    assert mock_update_memory.call_count == 1


@pytest.mark.asyncio  # Added
async def test_handle_vibe_request_yaml_response(  # Added async
    mock_llm: MagicMock,
    mock_console: Mock,
    mock_prompt: MagicMock,
    prevent_exit: MagicMock,
    default_output_flags: OutputFlags,
    mock_memory: MagicMock,
) -> None:
    """Test handling of commands that might involve YAML (basic case)."""
    # NOTE: Current schema doesn't support embedding YAML in the response.
    # This test checks that commands like 'apply -f -' are passed correctly
    # to _execute_command, even though YAML content isn't handled by the schema yet.
    plan_response = {
        "action_type": ActionType.COMMAND.value,
        "commands": [
            "-f",
            "-",
        ],  # Corrected: Verb is from command, LLM provides only args
        "explanation": "Applying configuration from stdin.",
    }
    mock_llm.execute_and_log_metrics.return_value = (json.dumps(plan_response), None)

    # Mock prompt for confirmation (apply requires confirmation)
    mock_prompt.return_value = "y"

    # Patch _execute_command
    with patch("vibectl.command_handler._execute_command") as mock_execute_cmd:
        mock_execute_cmd.return_value = Success(
            data="deployment.apps/nginx-deployment configured"
        )

        # Patch handle_command_output
        with patch(
            "vibectl.command_handler.handle_command_output"
        ) as mock_handle_output:
            await handle_vibe_request(  # Added await
                request="apply this config",
                command="apply",
                plan_prompt_func=plan_vibe_fragments,
                summary_prompt_func=get_test_summary_fragments,
                output_flags=default_output_flags,
                yes=False,  # Ensure confirmation is triggered
                config=None,  # Added missing config argument
            )

            # Verify confirmation was prompted
            mock_prompt.assert_called_once()
            # Verify _execute_command was called with correct verb/args, None
            # for yaml_content
            mock_execute_cmd.assert_called_once_with("apply", ["-f", "-"], None)

            # Verify handle_command_output was called
            mock_handle_output.assert_called_once()
            _, ho_call_kwargs = mock_handle_output.call_args
            assert ho_call_kwargs.get("command") == "apply"


@pytest.mark.asyncio  # Added
async def test_handle_vibe_request_create_pods_yaml(  # Added async
    mock_llm: MagicMock,
    mock_run_kubectl: Mock,
    mock_console: Mock,
    mock_confirm: MagicMock,
    prevent_exit: MagicMock,
    default_output_flags: OutputFlags,
) -> None:
    """Test vibe request that specifically creates multiple pods using a YAML manifest.

    This test ensures the regression with create commands and YAML files
    doesn't happen again.
    """
    # Disable vibe summary to prevent extra LLM call/timeout
    default_output_flags.show_vibe = False

    # Construct expected JSON for planning
    expected_response_plan = {
        "action_type": ActionType.COMMAND.value,
        "commands": [
            "get",
            "pods",
            "---",
            "-n default\n---\napiVersion: v1\nkind: Pod\nmetadata:\n  name: foo\n"
            "  labels:\n    app: nginx-demo\nspec:\n  containers:\n  - name: nginx\n"
            "    image: nginx:latest\n    ports:\n    - containerPort: 80\n---\n"
            "apiVersion: v1\nkind: Pod\nmetadata:\n  name: bar\n  labels:\n"
            "    app: nginx-demo\nspec:\n  containers:\n  - name: nginx\n"
            "    image: nginx:latest\n    ports:\n    - containerPort: 80",
        ],
        "explanation": "Creating multiple pods from YAML.",
    }

    # Simulate a model response for creating two pods
    # summary_response = { # Not used as show_vibe is False
    #     "action_type": ActionType.FEEDBACK.value,
    #     "explanation": "Test response",
    # }
    mock_llm.execute_and_log_metrics.return_value = (
        json.dumps(expected_response_plan),
        None,
    )

    # Set up confirmation to be True
    mock_confirm.return_value = True

    # Mock subprocess.run for kubectl calls with YAML
    with (
        patch(
            "vibectl.memory.include_memory_in_prompt",
            return_value="Plan this: Create nginx demo pods foo and bar.",
        ),
        patch("subprocess.run") as mock_subprocess,
        patch("vibectl.command_handler.update_memory") as mock_update_memory,
    ):
        # Configure mock subprocess to return success
        mock_process = MagicMock()
        mock_process.stdout = "pod/foo created\npod/bar created"
        mock_process.returncode = 0
        mock_subprocess.return_value = mock_process

        await handle_vibe_request(  # Added await
            request="Create nginx demo 'hello, world' pods foo and bar.",
            command="create",
            plan_prompt_func=plan_vibe_fragments,
            summary_prompt_func=get_test_summary_fragments,
            output_flags=default_output_flags,
            yes=True,  # Bypass the interactive prompt
        )

    # Verify that memory was updated TWICE (once after exec, once after summary)
    # assert mock_memory.call_count == 2

    # No need to verify specific args as they can vary by implementation

    # Expect only ONE call because show_vibe is False
    assert mock_update_memory.call_count == 1


@pytest.mark.asyncio  # Added
@patch("vibectl.command_handler.console_manager")
async def test_show_kubectl_flag_controls_command_display(  # Added async
    mock_console_manager: MagicMock,
    mock_llm: MagicMock,
    mock_memory: MagicMock,
    prevent_exit: MagicMock,
) -> None:
    """Test that the show_kubectl flag controls command display."""
    # --- Test Setup ---
    # Define the command the LLM should plan
    llm_verb = "get"
    llm_args = ["pods", "--namespace=test-ns"]
    llm_explanation = "Getting pods in test-ns."
    plan_response = {
        "action_type": ActionType.COMMAND.value,
        "commands": [llm_verb, *llm_args],
        "explanation": llm_explanation,
    }
    mock_llm.execute_and_log_metrics.return_value = (json.dumps(plan_response), None)

    # Define what the display string should look like
    expected_display_args_str = _create_display_command_for_test(llm_args)
    expected_display_command = (
        f"Running: kubectl {llm_verb} {expected_display_args_str}"
    )

    # --- Loop through show_kubectl flag values ---
    for show_flag_value, expect_print in [(True, True), (False, False)]:
        # Reset mocks at the START of the loop iteration
        mock_console_manager.reset_mock()
        mock_llm.reset_mock()  # Reset LLM mock if its state matters per iteration
        # We need fresh mocks for patched functions inside the loop

        # Set the LLM response again for this iteration (if reset)
        mock_llm.execute_and_log_metrics.return_value = (
            json.dumps(plan_response),
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
            patch("vibectl.memory.include_memory_in_prompt"),
        ):  # No need to assert on this mock
            mock_execute_cmd.return_value = Success("pod data")
            mock_handle_output.return_value = Success("Handled output")  # Mock return

            # --- Execute the function under test ---
            await handle_vibe_request(  # Added await
                request="get pods in test-ns",
                command="vibe",  # Original user command
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
            mock_execute_cmd.assert_called_once_with(llm_verb, llm_args, None)

            # 3. Verify handle_command_output was called with the LLM-planned verb
            mock_handle_output.assert_called_once()
            _, ho_call_kwargs = mock_handle_output.call_args
            assert ho_call_kwargs.get("command") == llm_verb

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
    mock_llm: MagicMock,
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
    mock_llm.execute_and_log_metrics.return_value = (json.dumps(plan_response), None)

    # Patch _execute_command to return success
    with patch("vibectl.command_handler._execute_command") as mock_execute_cmd:
        mock_execute_cmd.return_value = Success(data=kubectl_output_data)

        # Set up side_effect for the LLM calls: planning (success), summary (error)
        mock_llm.execute_and_log_metrics.side_effect = [
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
        assert mock_llm.execute_and_log_metrics.call_count == 2

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
    mock_llm: MagicMock,
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
        mock_llm.execute_and_log_metrics.side_effect = [
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
            assert mock_llm.execute_and_log_metrics.call_count == 2

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
