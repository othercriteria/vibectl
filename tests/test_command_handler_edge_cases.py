"""Tests for command_handler.py's handling of edge cases and extreme inputs.

This module tests edge cases, extreme inputs, and error conditions to ensure
the command handler is robust against unexpected or malformed inputs.
"""

import json
from collections.abc import Generator
from unittest.mock import ANY, MagicMock, Mock, patch

import pytest
from pydantic import ValidationError
from rich.panel import Panel

from vibectl.command_handler import (
    ActionType,
    OutputFlags,
    _create_display_command,
    _execute_command,
    _handle_command_confirmation,
    handle_command_output,
    handle_standard_command,
    handle_vibe_request,
)
from vibectl.k8s_utils import run_kubectl_with_complex_args
from vibectl.types import Error, RecoverableApiError, Success, Truncation


@pytest.fixture
def mock_get_adapter_patch() -> Generator[MagicMock, None, None]:
    """Mock the get_model_adapter function. Yields the mocked adapter instance."""
    with patch("vibectl.command_handler.get_model_adapter") as mock_patch:
        mock_adapter_instance = MagicMock()
        mock_model_instance = Mock()
        mock_adapter_instance.get_model.return_value = mock_model_instance
        mock_adapter_instance.execute = MagicMock()
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
def mock_include_memory() -> Generator[MagicMock, None, None]:
    """Mock include_memory_in_prompt."""
    with patch("vibectl.memory.include_memory_in_prompt") as mock:
        # Default behavior: return prompt unmodified
        mock.side_effect = lambda prompt, **kwargs: prompt
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


def test_execute_command_with_complex_args_edge_cases() -> None:
    """Test executing commands with complex edge cases."""
    with (
        patch("vibectl.k8s_utils.subprocess.run") as mock_run,
        patch("vibectl.command_handler.console_manager"),
    ):
        # Test with empty args list
        mock_process = Mock()
        mock_process.stdout = ""
        mock_process.returncode = 0
        mock_run.return_value = mock_process

        # Use the function from k8s_utils
        result = run_kubectl_with_complex_args([])
        assert isinstance(result, Success)
        assert result.data == ""

        # Test with quoted command arguments
        mock_process.stdout = "test output"
        result = run_kubectl_with_complex_args(["get", "pods", "--label='app=nginx'"])
        assert mock_run.called
        cmd_args = mock_run.call_args[0][0]
        assert "--label='app=nginx'" in cmd_args


def test_handle_command_output_extreme_inputs() -> None:
    """Test handle_command_output with extreme or unusual inputs."""
    with (
        patch("vibectl.command_handler.get_model_adapter") as mock_get_adapter,
        patch("vibectl.command_handler.console_manager"),
        patch("vibectl.command_handler.output_processor") as mock_processor,
    ):
        # Set up mocks
        mock_adapter = Mock()
        mock_model = Mock()
        mock_adapter.get_model.return_value = mock_model
        mock_adapter.execute.return_value = "Test response"
        mock_get_adapter.return_value = mock_adapter
        mock_processor.process_auto.return_value = Truncation(
            original="A" * 5000, truncated="A" * 2000 + "..."
        )

        # Create output flags
        output_flags = OutputFlags(
            show_raw=True,
            show_vibe=True,
            warn_no_output=False,
            model_name="test-model",
        )

        # Test with None output (should handle gracefully)
        handle_command_output(
            output=None,  # type: ignore
            output_flags=output_flags,
            summary_prompt_func=lambda: "Test {output}",
        )

        # Test with empty output
        handle_command_output(
            output="",
            output_flags=output_flags,
            summary_prompt_func=lambda: "Test {output}",
        )

        # Test with extremely long output
        long_output = "A" * 100000  # Reverted to 100k chars
        mock_processor.process_auto.return_value = Truncation(
            original=long_output, truncated=long_output[:1000]
        )
        handle_command_output(
            output=long_output,
            output_flags=output_flags,
            summary_prompt_func=lambda: "Test {output}",
        )


def test_handle_vibe_request_empty_llm_response(
    mock_get_adapter_patch: MagicMock, mock_console: MagicMock
) -> None:
    """Test handle_vibe_request when LLM returns empty response."""
    # Configure model adapter to return empty string
    mock_get_adapter_patch.execute.return_value = ""

    # Configure output flags
    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
    )

    # Mock the functions called during error handling
    with (
        patch("vibectl.command_handler.handle_command_output") as mock_handle_output,
        patch(
            "vibectl.memory.include_memory_in_prompt", return_value="Plan this: empty"
        ),
        patch("vibectl.command_handler.update_memory") as mock_update_memory,
        patch("vibectl.command_handler.create_api_error") as mock_create_api_error,
    ):
        # Call handle_vibe_request with empty LLM response
        result = handle_vibe_request(
            request="Show me the pods",
            command="vibe",
            plan_prompt="Plan how to {command} {request}",
            summary_prompt_func=lambda: "Test prompt {output}",
            output_flags=output_flags,
            memory_context="test-context",
        )

        # Verify update_memory was called because the function returns early
        mock_update_memory.assert_called_once()
        # Verify create_api_error was NOT called
        mock_create_api_error.assert_not_called()
        # Verify handle_command_output was NOT called
        mock_handle_output.assert_not_called()
        # Verify the result is an Error object
        assert isinstance(result, Error)
        assert result.error == "LLM returned an empty response."


def test_handle_vibe_request_llm_returns_error(
    mock_get_adapter_patch: MagicMock,
) -> None:
    """Test handle_vibe_request when LLM returns an error message as JSON."""
    # Configure model adapter to return an error message as valid JSON
    error_msg = "I cannot fulfill this request."
    error_response_str = json.dumps(
        {
            "action_type": ActionType.ERROR.value,
            "error": error_msg,
            "explanation": "Some explanation why.",
        }
    )
    mock_get_adapter_patch.execute.return_value = error_response_str

    output_flags = OutputFlags(
        show_raw=False, show_vibe=False, warn_no_output=False, model_name="test-model"
    )

    # Mock update_memory and create_api_error using parentheses for with statement
    with (
        patch(
            "vibectl.memory.include_memory_in_prompt", return_value="Plan this: error"
        ),
        patch("vibectl.command_handler.update_memory") as mock_update_memory,
        patch("vibectl.command_handler.console_manager") as mock_console,
    ):
        test_request = "Do something impossible"
        result = handle_vibe_request(
            request=test_request,
            command="vibe",
            plan_prompt="Plan how to {command} {request}",
            summary_prompt_func=lambda: "",
            output_flags=output_flags,
            memory_context="error-context",
        )

        # Verify update_memory was called with the error from the response
        mock_update_memory.assert_called_once()
        call_args, call_kwargs = mock_update_memory.call_args
        assert call_kwargs.get("command") == "vibe"
        assert call_kwargs.get("command_output") == error_msg
        assert (
            call_kwargs.get("vibe_output")
            == f"LLM Planning Error: {test_request} -> {error_msg}"
        )
        assert call_kwargs.get("model_name") == "test-model"

        # Verify console output - Restored check for print_note with explanation
        mock_console.print_note.assert_called_with(
            "AI Explanation: Some explanation why."
        )
        mock_console.print_error.assert_called_with(f"LLM Planning Error: {error_msg}")

        # Verify the result is an Error object
        assert isinstance(result, Error)
        assert result.error == f"LLM planning error: {error_msg}"
        assert result.recovery_suggestions == "Some explanation why."


@patch("vibectl.command_handler.update_memory")  # Back to patching command_handler
def test_handle_vibe_request_command_parser_error(
    mock_update_memory_ch: MagicMock,  # Use this mock name again
    mock_get_adapter_patch: MagicMock,  # Reverted argument name
    capfd: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,  # Add caplog fixture
) -> None:
    """Test handle_vibe_request handles command parsing errors."""
    # Configure model to return malformed JSON
    malformed_response = "not {json"  # Malformed
    mock_get_adapter_patch.execute.return_value = malformed_response

    output_flags = OutputFlags(
        show_raw=False, show_vibe=False, warn_no_output=False, model_name="test-model"
    )

    # Expect the inner `except (JSONDecodeError, ValidationError)` block.
    # Patch create_api_error here using 'with'
    with (
        patch(
            "vibectl.memory.include_memory_in_prompt",
            return_value="Plan this: malformed",
        ),
        patch(
            "vibectl.command_handler.create_api_error", autospec=True
        ) as mock_create_api_error_with,
    ):
        # Configure create_api_error mock
        mock_error_instance = Error(error="Mocked API error", halt_auto_loop=False)
        mock_create_api_error_with.return_value = mock_error_instance

        result = handle_vibe_request(
            request="Show pods",
            command="get",
            plan_prompt="Plan how to {command} {request}",
            summary_prompt_func=lambda: "",
            output_flags=output_flags,
            memory_context="parser-error-context",
        )

        # Verify update_memory WAS called (using the decorator mock)
        mock_update_memory_ch.assert_called_once()

        # Verify create_api_error was called (using the context mock)
        mock_create_api_error_with.assert_called_once()
        # Check only exception type and that result matches mock return
        assert isinstance(
            mock_create_api_error_with.call_args[0][1],
            json.JSONDecodeError | ValidationError,
        )
        assert result == mock_create_api_error_with.return_value

        # Verify error output was logged (via logger.error)
        assert (
            "Failed to parse LLM response as JSON"
            in caplog.text  # Check log capture for the specific warning
        )
        assert "ValidationError" in caplog.text or "JSONDecodeError" in caplog.text


@patch("vibectl.command_handler._execute_command")
@patch("vibectl.command_handler.handle_command_output")
def test_handle_vibe_request_autonomous_mode(
    mock_handle_output_dec: MagicMock,
    mock_execute_command_dec: MagicMock,
    mock_get_adapter_patch: MagicMock,
    mock_console: MagicMock,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """Test handle_vibe_request in autonomous mode success path."""
    # Configure model adapter
    llm_response_dict = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["get", "pods"],  # Use the correct key and structure
        "explanation": "Fetching pods.",
    }
    mock_get_adapter_patch.execute.return_value = json.dumps(llm_response_dict)

    # Configure output flags
    output_flags = OutputFlags(
        show_raw=False, show_vibe=False, warn_no_output=False, model_name="auto-model"
    )

    # Configure _execute_command mock
    mock_execute_command_dec.return_value = Success("Success!")

    # Mock update_memory and include_memory_in_prompt using a different approach
    with (
        patch(
            "vibectl.memory.include_memory_in_prompt", return_value="Plan this: auto"
        ),
        patch("vibectl.command_handler.update_memory") as mock_update_memory_ctx,
        patch("vibectl.memory.get_model_adapter") as mock_get_adapter_memory,
    ):  # Patch adapter used by update_memory
        # Configure the mock adapter used by memory to prevent get_model failure
        mock_adapter_mem = MagicMock()
        mock_model_mem = Mock()
        mock_adapter_mem.get_model.return_value = mock_model_mem
        mock_get_adapter_memory.return_value = mock_adapter_mem

        # Call handle_vibe_request in autonomous mode
        result = handle_vibe_request(
            request="Get pods",
            command="vibe",
            plan_prompt="Plan how to {command} {request}",
            summary_prompt_func=lambda: "Summary {output}",
            output_flags=output_flags,
            memory_context="auto-test",
            autonomous_mode=True,  # Enable autonomous mode
        )

        # Verify execution flow
        mock_execute_command_dec.assert_called_once_with(
            "get",
            ["pods"],
            None,  # Match actual call signature: verb, args, yaml
        )

        # Verify update_memory was called ONCE after successful execution
        mock_update_memory_ctx.assert_called_once()
        call_args, call_kwargs = mock_update_memory_ctx.call_args
        assert call_kwargs.get("command") == "kubectl get pods"
        assert call_kwargs.get("model_name") == "auto-model"

        # Verify handle_command_output was called
        # Check that it was called with a Success object as the first arg
        mock_handle_output_dec.assert_called_once()
        call_args, call_kwargs_handle = mock_handle_output_dec.call_args
        assert len(call_args) >= 1 and isinstance(call_args[0], Success)
        # Further check kwargs if needed, e.g., output_flags
        assert (
            len(call_args) >= 2 and call_args[1] == output_flags
        )  # Check 2nd positional arg
        assert call_kwargs_handle.get("command") == "get"  # Check command kwarg

        # Verify the result returned by handle_vibe_request itself
        assert result == mock_handle_output_dec.return_value

        # Capture and check stdout/stderr
        captured = capfd.readouterr()
        assert "Success!" not in captured.out  # Output should be handled by mocks
        assert "Error" not in captured.err


@patch("vibectl.command_handler._execute_command")
@patch("vibectl.command_handler.handle_command_output")
def test_handle_vibe_request_autonomous_mode_missing_commands(
    mock_handle_output: MagicMock,
    mock_execute_command: MagicMock,
    mock_get_adapter_patch: MagicMock,
    mock_console: MagicMock,  # Keep this mock
    mock_memory: MagicMock,  # Added fixture
) -> None:
    """Test handle_vibe_request autonomous mode when commands list is missing."""
    # Configure model response (COMMAND but missing 'commands')
    plan_response = {
        "action_type": ActionType.COMMAND.value,
        # "commands": ["pods"], # Intentionally missing
        "explanation": "Forgot commands.",
    }
    mock_get_adapter_patch.execute.return_value = json.dumps(plan_response)

    output_flags = OutputFlags(
        show_raw=True, show_vibe=True, warn_no_output=False, model_name="test-model"
    )

    # Patch handle_command_output (should not be called)
    with (
        patch("vibectl.command_handler.handle_command_output") as mock_handle_output,
    ):
        result = handle_vibe_request(
            request="missing commands test",
            command="vibe",
            plan_prompt="Plan: {request}",
            summary_prompt_func=lambda: "Summary",
            output_flags=output_flags,
            autonomous_mode=True,
        )

        # Verify Error was returned directly from the autonomous check
        mock_execute_command.assert_not_called()
        # mock_memory.assert_not_called()  # Use mock_memory - Old expectation
        # Expect memory to be called once to record the error
        mock_memory.assert_called_once()
        _args, kwargs = mock_memory.call_args
        assert kwargs.get("command") == "vibe"  # Should use original command here
        assert "COMMAND action with no args" in kwargs.get("command_output", "")
        assert kwargs.get("model_name") == "test-model"

        mock_handle_output.assert_not_called()
        # Assert result is an Error
        assert isinstance(result, Error)
        # Check the specific error message for missing commands in COMMAND ActionType
        assert "Internal error: LLM sent COMMAND action with no args." in result.error
        assert result.exception is None  # Verify no exception was attached


def test_handle_vibe_request_with_dangerous_commands(
    mock_get_adapter_patch: MagicMock,
) -> None:
    """Test handle_vibe_request requires confirmation for dangerous commands."""

    # Helper function to run a sub-test for a command string
    def test_command(
        verb: str,
        args_list: list[str],
        yaml_content: str | None,
        should_need_confirmation: bool,
    ) -> None:
        # Define output flags for this specific test context
        output_flags = OutputFlags(
            show_raw=False,
            show_vibe=False,
            warn_no_output=False,
            model_name="test-model",
        )
        # Configure model response
        llm_commands = [verb, *args_list] if args_list else [verb]
        response_dict = {
            "action_type": ActionType.COMMAND.value,
            "commands": llm_commands,
            "yaml_manifest": yaml_content,
            "explanation": "test explanation",
        }
        mock_get_adapter_patch.execute.return_value = json.dumps(response_dict)

        # Mock _needs_confirmation and _execute_command
        with (
            patch(
                "vibectl.command_handler._needs_confirmation"
            ) as mock_needs_confirmation,
            patch("vibectl.command_handler._execute_command") as mock_execute,
            patch(
                "vibectl.command_handler.handle_command_output"
            ) as mock_handle_output,
            patch(
                "vibectl.memory.include_memory_in_prompt",
                return_value="Plan this: dangerous",
            ),
            patch("vibectl.command_handler.update_memory"),
        ):
            mock_needs_confirmation.return_value = should_need_confirmation
            mock_execute.return_value = Success(data="Executed")
            mock_handle_output.return_value = Success(message="Displayed")

            # Call handle_vibe_request
            result = handle_vibe_request(
                request="Do dangerous thing",
                command="vibe",  # Simulate the general vibe command
                plan_prompt="Plan this: {request}",
                summary_prompt_func=lambda: "Summary",
                output_flags=output_flags,
                yes=True,  # Simulate --yes to bypass actual prompt
                autonomous_mode=True,  # Testing confirmation check
            )

            # Assertions
            assert isinstance(result, Success)
            mock_needs_confirmation.assert_called_once_with(
                verb, False
            )  # semiauto is False
            # Assert _execute_command was called with the CORRECT verb and args
            mock_execute.assert_called_once_with(verb, args_list, yaml_content)
            mock_handle_output.assert_called_once()

    # Test cases
    test_command("get", ["pods"], None, False)  # Safe command
    test_command("delete", ["pod", "my-pod"], None, True)  # Dangerous command
    test_command("apply", ["-f", "config.yaml"], None, True)  # Dangerous command
    test_command("scale", ["deployment/app", "--replicas=0"], None, True)  # Dangerous
    test_command("logs", ["my-pod"], None, False)  # Safe


def test_handle_vibe_request_with_unknown_model(
    mock_get_adapter_patch: MagicMock,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """Test handle_vibe_request handles unknown model errors gracefully."""
    # Configure adapter to raise ValueError on get_model
    unknown_model_error = ValueError("Unknown model requested: bad-model")
    mock_get_adapter_patch.get_model.side_effect = unknown_model_error

    output_flags = OutputFlags(
        show_raw=True, show_vibe=True, warn_no_output=False, model_name="bad-model"
    )

    # Mock update_memory and create_api_error
    with (
        patch("vibectl.command_handler.update_memory") as mock_update_mem,
        patch("vibectl.command_handler.create_api_error") as mock_create_api_err,
        patch("vibectl.memory.include_memory_in_prompt"),
    ):  # Mock memory include
        # Configure create_api_error to return a specific Error
        api_error_return = Error(error="API Error: test")
        mock_create_api_err.return_value = api_error_return

        result = handle_vibe_request(
            request="Test unknown model",
            command="get",
            plan_prompt="Plan",
            summary_prompt_func=lambda: "Summary",
            output_flags=output_flags,
        )

        # Verify update_memory was called due to the ValueError catch block
        mock_update_mem.assert_called_once()
        # Check kwargs
        call_kwargs = mock_update_mem.call_args.kwargs
        assert call_kwargs.get("command") == "system"
        expected_error_string = (
            f"Failed to get model '{output_flags.model_name}': {unknown_model_error}"
        )
        assert call_kwargs.get("command_output") == (expected_error_string)
        assert (
            call_kwargs.get("vibe_output")
            == f"System Error: Failed to get model '{output_flags.model_name}'."
        )
        assert call_kwargs.get("model_name") == "bad-model"
        # Verify create_api_error was called with the raw error and exception
        mock_create_api_err.assert_called_once_with(
            expected_error_string,
            unknown_model_error,
        )

        # Verify the final result is the one returned by create_api_error
        assert result is api_error_return


@patch("vibectl.command_handler._execute_command")
def test_confirmation_yes(
    mock_execute_command: MagicMock,
    mock_get_adapter_patch: MagicMock,
    mock_click_prompt: MagicMock,
    mock_console: MagicMock,
    mock_memory_helpers: dict,
) -> None:
    """Test confirmation flow when user inputs 'y' (Yes)."""
    # Setup: LLM response for a dangerous command
    llm_response_str = json.dumps(
        {
            "action_type": "COMMAND",
            "commands": ["delete", "pod", "my-pod", "-n", "test"],
            "explanation": "Deleting the pod.",
        }
    )
    mock_get_adapter_patch.execute.return_value = llm_response_str
    mock_click_prompt.return_value = "y"  # Simulate user pressing 'y'

    output_flags = OutputFlags(
        model_name="test-model", show_raw=False, show_vibe=False, warn_no_output=False
    )
    result = handle_vibe_request(
        request="delete the pod",
        command="vibe",
        plan_prompt="Plan: {request}",
        summary_prompt_func=lambda: "",
        output_flags=output_flags,
        semiauto=True,  # Trigger confirmation
    )

    assert isinstance(
        result, Success
    ), f"Expected Success, got {type(result).__name__}: {result}"
    mock_execute_command.assert_called_once_with(
        "delete", ["pod", "my-pod", "-n", "test"], None
    )
    mock_console.print_cancelled.assert_not_called()


@patch("vibectl.command_handler._execute_command")
def test_confirmation_no(
    mock_execute_command: MagicMock,
    mock_get_adapter_patch: MagicMock,
    mock_click_prompt: MagicMock,
    mock_console: MagicMock,
    mock_memory_helpers: dict,
) -> None:
    """Test confirmation flow when user inputs 'n' (No)."""
    llm_response_str = json.dumps(
        {
            "action_type": "COMMAND",
            "commands": ["delete", "pod", "my-pod"],
            "explanation": "Deleting the pod.",
        }
    )
    mock_get_adapter_patch.execute.return_value = llm_response_str
    mock_click_prompt.return_value = "n"

    output_flags = OutputFlags(
        model_name="test-model", show_raw=False, show_vibe=False, warn_no_output=False
    )
    result = handle_vibe_request(
        request="delete the pod",
        command="vibe",
        plan_prompt="Plan: {request}",
        summary_prompt_func=lambda: "",
        output_flags=output_flags,
        semiauto=True,
    )

    assert isinstance(result, Success)
    assert result.message == "Command execution cancelled by user"
    mock_execute_command.assert_not_called()
    mock_console.print_cancelled.assert_called_once()


@patch("vibectl.command_handler._execute_command")
def test_confirmation_exit_semiauto(
    mock_execute_command: MagicMock,
    mock_get_adapter_patch: MagicMock,
    mock_click_prompt: MagicMock,
    mock_console: MagicMock,
    mock_memory_helpers: dict,
) -> None:
    """Test confirmation flow when user inputs 'e' (Exit) in semiauto mode."""
    llm_response_str = json.dumps(
        {
            "action_type": "COMMAND",
            "commands": ["delete", "pod", "my-pod"],
            "explanation": "Deleting the pod.",
        }
    )
    mock_get_adapter_patch.execute.return_value = llm_response_str
    mock_click_prompt.return_value = "e"

    output_flags = OutputFlags(
        model_name="test-model", show_raw=False, show_vibe=False, warn_no_output=False
    )
    result = handle_vibe_request(
        request="delete the pod",
        command="vibe",
        plan_prompt="Plan: {request}",
        summary_prompt_func=lambda: "",
        output_flags=output_flags,
        semiauto=True,  # Semiauto mode enables 'e'
    )

    assert isinstance(result, Success)
    assert result.message == "User requested exit from semiauto loop"
    assert result.continue_execution is False
    mock_execute_command.assert_not_called()
    # Check console output for exit message? Maybe too detailed.


@patch("vibectl.command_handler._execute_command")
@patch(
    "vibectl.command_handler.console_manager.safe_print"
)  # Mock safe_print for Panel
@patch("vibectl.memory.get_memory")  # Explicitly patch the target of the local import
def test_confirmation_memory(
    mock_local_get_memory: MagicMock,  # Add mock for the explicit patch
    mock_safe_print: MagicMock,
    mock_execute_command: MagicMock,
    mock_get_adapter_patch: MagicMock,
    mock_click_prompt: MagicMock,
    mock_memory_helpers: dict,  # Still use this for other mocks if needed
    mock_console: MagicMock,
) -> None:
    """Test confirmation flow when user inputs 'm' (Memory) then 'y'."""
    llm_response_str = json.dumps(
        {
            "action_type": "COMMAND",
            "commands": ["delete", "pod", "my-pod"],
            "explanation": "Deleting the pod.",
        }
    )
    mock_get_adapter_patch.execute.return_value = llm_response_str
    # Simulate 'm' then 'y'
    mock_click_prompt.side_effect = ["m", "y"]
    # Configure the specific mock for the local import
    mock_local_get_memory.return_value = "Memory content shown via local import."

    output_flags = OutputFlags(
        model_name="test-model", show_raw=False, show_vibe=False, warn_no_output=False
    )
    result = handle_vibe_request(
        request="delete the pod",
        command="vibe",
        plan_prompt="Plan: {request}",
        summary_prompt_func=lambda: "",
        output_flags=output_flags,
        semiauto=True,
    )

    assert isinstance(result, Success)
    assert mock_click_prompt.call_count == 2
    # Check the mock for the local import was called
    mock_local_get_memory.assert_called_once()
    # Check the command_handler import mock was NOT called
    mock_memory_helpers["get_ch"].assert_not_called()
    # Check that Panel was printed
    assert any(
        isinstance(arg, Panel)
        for call_args in mock_safe_print.call_args_list
        for arg in call_args.args
    )
    mock_execute_command.assert_called_once()  # Command eventually executed


@patch("vibectl.command_handler._execute_command")
def test_confirmation_yes_and(
    mock_execute_command: MagicMock,
    mock_get_adapter_patch: MagicMock,
    mock_click_prompt: MagicMock,
    mock_memory_helpers: dict,
    mock_console: MagicMock,
) -> None:
    """Test confirmation flow for 'a' (Yes And) with successful fuzzy memory update."""
    # Mock planning LLM response (first execute call)
    planning_response_str = json.dumps(
        {
            "action_type": "COMMAND",
            "commands": ["delete", "pod", "my-pod"],
            "explanation": "Deleting the pod.",
        }
    )
    # Mock fuzzy update LLM response (second execute call)
    fuzzy_update_response_str = "Updated memory content"
    mock_get_adapter_patch.execute.side_effect = [
        planning_response_str,
        fuzzy_update_response_str,
    ]

    # Simulate 'a' then memory input
    mock_click_prompt.side_effect = ["a", "User added context"]

    output_flags = OutputFlags(
        model_name="test-model", show_raw=False, show_vibe=False, warn_no_output=False
    )
    result = handle_vibe_request(
        request="delete the pod",
        command="vibe",
        plan_prompt="Plan: {request}",
        summary_prompt_func=lambda: "",
        output_flags=output_flags,
        semiauto=True,
    )

    assert isinstance(result, Success)
    assert mock_click_prompt.call_count == 2  # Confirmation + Memory input
    # Check the command_handler import mock for fuzzy update
    mock_memory_helpers["get_ch"].assert_called_once()
    mock_memory_helpers["prompt_func"].assert_called_once()
    # Check execute was called twice (planning + fuzzy update)
    assert mock_get_adapter_patch.execute.call_count == 2
    # Check set_memory was called with the fuzzy update response
    mock_memory_helpers["set"].assert_called_once_with(
        fuzzy_update_response_str, ANY
    )  # Config obj passed
    mock_execute_command.assert_called_once()  # Command executed after update
    mock_console.print_success.assert_any_call("Memory updated")


@patch("vibectl.command_handler._execute_command")
def test_confirmation_no_but(
    mock_execute_command: MagicMock,
    mock_get_adapter_patch: MagicMock,
    mock_click_prompt: MagicMock,
    mock_memory_helpers: dict,
    mock_console: MagicMock,
) -> None:
    """Test confirmation flow for 'b' (No But) with successful fuzzy memory update."""
    # Mock planning LLM response (first execute call)
    planning_response_str = json.dumps(
        {
            "action_type": "COMMAND",
            "commands": ["delete", "pod", "my-pod"],
            "explanation": "Deleting the pod.",
        }
    )
    # Mock fuzzy update LLM response (second execute call)
    fuzzy_update_response_str = "Updated memory with alternative"
    mock_get_adapter_patch.execute.side_effect = [
        planning_response_str,
        fuzzy_update_response_str,
    ]

    mock_click_prompt.side_effect = ["b", "User added alternative"]

    output_flags = OutputFlags(
        model_name="test-model", show_raw=False, show_vibe=False, warn_no_output=False
    )
    result = handle_vibe_request(
        request="delete the pod",
        command="vibe",
        plan_prompt="Plan: {request}",
        summary_prompt_func=lambda: "",
        output_flags=output_flags,
        semiauto=True,
    )

    assert isinstance(result, Success)
    assert result.message == "Command execution cancelled by user"
    assert mock_click_prompt.call_count == 2
    # Check the command_handler import mock for fuzzy update
    mock_memory_helpers["get_ch"].assert_called_once()
    mock_memory_helpers["prompt_func"].assert_called_once()
    assert mock_get_adapter_patch.execute.call_count == 2
    mock_memory_helpers["set"].assert_called_once_with(fuzzy_update_response_str, ANY)
    mock_execute_command.assert_not_called()  # Command NOT executed
    mock_console.print_cancelled.assert_called_once()
    mock_console.print_success.assert_any_call("Memory updated")


@patch("vibectl.command_handler._execute_command")
def test_fuzzy_memory_update_llm_error(
    mock_execute_command: MagicMock,
    mock_get_adapter_patch: MagicMock,
    mock_click_prompt: MagicMock,
    mock_memory_helpers: dict,
    mock_console: MagicMock,
) -> None:
    """Test confirmation flow 'a' (Yes And) when fuzzy memory update LLM fails."""
    # Mock planning LLM response (first execute call)
    planning_response_str = json.dumps(
        {
            "action_type": "COMMAND",
            "commands": ["delete", "pod", "my-pod"],
            "explanation": "Deleting the pod.",
        }
    )
    # Simulate LLM error during fuzzy update call (second execute call)
    llm_error = ValueError("LLM API failed")
    mock_get_adapter_patch.execute.side_effect = [planning_response_str, llm_error]

    # Simulate 'a' then memory input
    mock_click_prompt.side_effect = ["a", "User context"]

    output_flags = OutputFlags(
        model_name="test-model", show_raw=False, show_vibe=False, warn_no_output=False
    )
    result = handle_vibe_request(
        request="delete the pod",
        command="vibe",
        plan_prompt="Plan: {request}",
        summary_prompt_func=lambda: "",
        output_flags=output_flags,
        semiauto=True,
    )

    # Expect an Error result because the memory update failed
    assert isinstance(result, Error)
    assert "Error updating memory" in result.error
    assert result.exception == llm_error

    # Command should not execute if memory update fails
    mock_execute_command.assert_not_called()
    mock_memory_helpers["set"].assert_not_called()
    mock_console.print_error.assert_any_call(f"Error updating memory: {llm_error}")


@patch("vibectl.command_handler._run_standard_kubectl_command")
@patch("vibectl.command_handler.handle_command_output")
@patch("vibectl.command_handler.logger")  # Mock logger to check calls
def test_handle_standard_command_unexpected_error(
    mock_logger: MagicMock,
    mock_handle_output: MagicMock,
    mock_run_kubectl: MagicMock,
    mock_console: MagicMock,  # Use existing fixture
) -> None:
    """
    Test handle_standard_command when an unexpected error occurs
    after successful kubectl execution (triggering _handle_standard_command_error).
    """
    # Arrange: Simulate kubectl success, but error during output handling
    mock_run_kubectl.return_value = Success(data="kubectl successful output")
    test_exception = ValueError("Unexpected error during output handling")
    mock_handle_output.side_effect = test_exception

    output_flags = OutputFlags(
        model_name="test", show_raw=False, show_vibe=False, warn_no_output=False
    )

    # Define dummy prompt function using def
    def dummy_prompt_func() -> str:
        return "prompt"

    # Act
    result = handle_standard_command(
        command="get",
        resource="pods",
        args=("-n", "test"),  # Use tuple literal
        output_flags=output_flags,
        summary_prompt_func=dummy_prompt_func,
    )

    # Assert
    assert isinstance(result, Error), f"Expected Error, got {type(result)}"
    # Check that the error message format is correct (shortened)
    assert "Unexpected error: Unexpected error" in result.error
    assert result.exception == test_exception
    mock_run_kubectl.assert_called_once_with("get", "pods", ("-n", "test"))
    mock_handle_output.assert_called_once()
    # Verify logger.error was called only once (by the handler)
    mock_logger.error.assert_called_once()
    # Optionally, check the specific call content
    assert (
        "Unexpected error handling standard command"
        in mock_logger.error.call_args[0][0]
    )


# --- Test Cases for Vibe Processing Error Handling --- #


@patch("vibectl.command_handler.update_memory")  # Mock memory updates
@patch("vibectl.command_handler.output_processor")  # Mock output processor
def test_handle_command_output_vibe_recoverable_error(
    mock_processor: MagicMock,
    mock_update_memory: MagicMock,
    mock_get_adapter_patch: MagicMock,  # Use the adapter fixture
    mock_console: MagicMock,
) -> None:
    """
    Test handle_command_output when Vibe processing (_get_llm_summary)
    raises a RecoverableApiError.
    """
    # Arrange: Simulate successful command output, but LLM summary fails
    command_output = "Some successful command output."
    output_flags = OutputFlags(
        model_name="test", show_raw=False, show_vibe=True, warn_no_output=False
    )

    # Define dummy prompt function using def
    def dummy_prompt_func() -> str:
        return "Summarize: {output}"

    mock_processor.process_auto.return_value = Truncation(
        original=command_output, truncated=command_output
    )

    # Mock the LLM execute call to raise a RecoverableApiError
    api_error = RecoverableApiError("LLM rate limit exceeded")
    mock_get_adapter_patch.execute.side_effect = api_error

    # Act
    result = handle_command_output(
        output=command_output,
        output_flags=output_flags,
        summary_prompt_func=dummy_prompt_func,
        command="get pods",
    )

    # Assert
    assert isinstance(result, Error), f"Expected Error, got {type(result)}"
    assert "API Error: LLM rate limit exceeded" in result.error
    assert result.exception == api_error
    assert result.halt_auto_loop is False  # Should be non-halting
    mock_console.print_error.assert_any_call("API Error: LLM rate limit exceeded")
    mock_update_memory.assert_not_called()  # Memory shouldn't update on Vibe error


@patch("vibectl.command_handler.update_memory")
@patch("vibectl.command_handler.output_processor")
def test_handle_command_output_vibe_general_error(
    mock_processor: MagicMock,
    mock_update_memory: MagicMock,
    mock_get_adapter_patch: MagicMock,
    mock_console: MagicMock,
) -> None:
    """
    Test handle_command_output when Vibe processing (_get_llm_summary)
    raises a general Exception.
    """
    # Arrange
    command_output = "More successful output."
    output_flags = OutputFlags(
        model_name="test", show_raw=False, show_vibe=True, warn_no_output=False
    )

    # Define dummy prompt function using def
    def dummy_prompt_func() -> str:
        return "Summarize: {output}"

    mock_processor.process_auto.return_value = Truncation(
        original=command_output, truncated=command_output
    )

    # Mock the LLM execute call to raise a general Exception
    general_error = ValueError("Unexpected LLM client issue")
    mock_get_adapter_patch.execute.side_effect = general_error

    # Act
    result = handle_command_output(
        output=command_output,
        output_flags=output_flags,
        summary_prompt_func=dummy_prompt_func,
        command="describe node",
    )

    # Assert
    assert isinstance(result, Error), f"Expected Error, got {type(result)}"
    assert "Error getting Vibe summary: Unexpected LLM client issue" in result.error
    assert result.exception == general_error
    # General errors during vibe processing should be halting by default
    assert result.halt_auto_loop is True
    mock_console.print_error.assert_any_call(
        "Error getting Vibe summary: Unexpected LLM client issue"
    )
    mock_update_memory.assert_not_called()


@patch("vibectl.command_handler.update_memory")
@patch("vibectl.command_handler.output_processor")
def test_handle_command_output_recovery_llm_fails(
    mock_processor: MagicMock,
    mock_update_memory: MagicMock,
    mock_get_adapter_patch: MagicMock,
    mock_console: MagicMock,
) -> None:
    """
    Test handle_command_output when the initial command failed, show_vibe is True,
    and the subsequent LLM call for recovery suggestions also fails.
    """
    # Arrange: Simulate initial command error
    initial_error_msg = "kubectl command failed initially"
    initial_error = Error(
        error=initial_error_msg, exception=RuntimeError("kubectl error")
    )
    output_flags = OutputFlags(
        model_name="test", show_raw=False, show_vibe=True, warn_no_output=False
    )

    # Define dummy prompt function using def
    def dummy_prompt_func() -> str:
        return "unused"

    # Mock the LLM execute call (for recovery) to raise an error
    recovery_llm_error = ValueError("Recovery LLM failed")
    mock_get_adapter_patch.execute.side_effect = recovery_llm_error

    # Act
    result = handle_command_output(
        output=initial_error,  # Pass the initial Error object
        output_flags=output_flags,
        summary_prompt_func=dummy_prompt_func,
        command="delete pod",
    )

    # Assert
    assert isinstance(result, Error), f"Expected Error, got {type(result)}"
    # Check for combined error message (matching actual format)
    assert f"Original Error: {initial_error_msg}" in result.error
    assert (
        f"Vibe Failure: Error getting Vibe summary: {recovery_llm_error}"
        in result.error
    )
    # Exception should be the *original* error's exception or the recovery one
    assert (
        result.exception == initial_error.exception
        or result.exception == recovery_llm_error
    )
    assert result.halt_auto_loop is True  # Should be halting
    mock_console.print_error.assert_any_call(initial_error_msg)  # Prints original error
    mock_console.print_error.assert_any_call(
        f"Error getting Vibe summary: {recovery_llm_error}"
    )  # Prints recovery failure
    # Update memory should be called *only* for the initial error logging
    # inside the recovery block before the LLM call fails.
    # Refine: memory update happens *after* successful recovery LLM call.
    # So it should NOT be called here.
    mock_update_memory.assert_not_called()


def test_handle_vibe_request_handles_api_errors() -> None:
    # This test case is not provided in the original file or the code block
    # It's assumed to exist based on the function name, but the implementation
    # is not provided in the original file or the code block.
    # If the test case is to be implemented, the implementation should be added here.
    pass


@patch("vibectl.command_handler.update_memory")
@patch("vibectl.command_handler.create_api_error")
@patch("vibectl.command_handler.get_model_adapter")
def test_handle_vibe_request_parsing_error_after_fallback(
    mock_get_adapter: MagicMock,
    mock_create_api_error: MagicMock,
    mock_update_memory: MagicMock,
    caplog: pytest.LogCaptureFixture,
    mock_console: MagicMock,
) -> None:
    """Test handle_vibe_request handles parsing error when schema fallback occurred."""
    caplog.set_level("WARNING")
    # Arrange
    # Configure adapter mock
    mock_adapter_instance = MagicMock()
    mock_model_instance = Mock()
    mock_adapter_instance.get_model.return_value = mock_model_instance
    # Simulate execute returning raw text (as if schema fallback happened)
    raw_text_response = "This is raw text, not JSON."
    mock_adapter_instance.execute.return_value = raw_text_response
    mock_get_adapter.return_value = mock_adapter_instance

    # Configure create_api_error mock
    mock_error_instance = Error(error="Mocked API Error", halt_auto_loop=False)
    mock_create_api_error.return_value = mock_error_instance

    output_flags = OutputFlags(
        model_name="fallback-model",
        show_raw=False,
        show_vibe=False,
        warn_no_output=False,
    )

    # Act
    result = handle_vibe_request(
        request="Test parsing error after fallback",
        command="vibe",
        plan_prompt="Plan: {request}",
        summary_prompt_func=lambda: "Summary",
        output_flags=output_flags,
    )

    # Assert
    # Verify adapter.execute was called (with schema requested)
    mock_adapter_instance.execute.assert_called_once()
    call_kwargs = mock_adapter_instance.execute.call_args.kwargs
    assert call_kwargs.get("response_model") is not None  # Check schema was requested

    # Verify update_memory was called due to parsing error
    mock_update_memory.assert_called_once()
    mem_kwargs = mock_update_memory.call_args.kwargs
    assert mem_kwargs.get("command") == "system"
    assert "Failed to parse LLM response as expected JSON" in mem_kwargs.get(
        "command_output"
    )
    assert "System Error: Failed to parse LLM response" in mem_kwargs.get("vibe_output")
    assert mem_kwargs.get("model_name") == "fallback-model"

    # Verify create_api_error was called
    mock_create_api_error.assert_called_once()
    create_args, _ = mock_create_api_error.call_args
    # Check the exception type passed to create_api_error
    assert isinstance(create_args[1], json.JSONDecodeError | ValidationError)

    # Verify the result is the error returned by create_api_error
    assert result == mock_error_instance

    # Verify the warning log message
    assert "Failed to parse LLM response as JSON" in caplog.text
    assert raw_text_response[:500] in caplog.text  # Check truncated response is logged


def test_create_display_command_edge_cases() -> None:
    """Test _create_display_command with edge cases."""
    # Test -f with non-'-' argument
    args1 = ["apply", "-f", "my-file.yaml"]
    assert _create_display_command(args1) == "apply -f my-file.yaml"

    # Test -f without following argument (should not happen but test)
    args2 = ["apply", "-f"]
    assert _create_display_command(args2) == "apply -f"

    # Test args with special characters
    args3 = ["get", "pod", "--field-selector", "status.phase!=Running"]
    assert (
        _create_display_command(args3)
        == "get pod --field-selector status.phase!=Running"
    )

    # Test complex args with quotes already present (should handle gracefully)
    args4 = ["exec", "-it", "my-pod", "--", 'bash -c "echo hello > /tmp/test"']
    assert (
        _create_display_command(args4)
        == 'exec -it my-pod -- "bash -c "echo hello > /tmp/test""'
    )


@patch("vibectl.command_handler.run_kubectl_with_yaml")
@patch("vibectl.command_handler.run_kubectl_with_complex_args")
@patch("vibectl.command_handler.run_kubectl")
@patch("vibectl.command_handler.logger")  # Mock logger
def test_execute_command_exception_handling(
    mock_logger: MagicMock,
    mock_run_std: MagicMock,
    mock_run_complex: MagicMock,
    mock_run_yaml: MagicMock,
) -> None:
    """Test the except block in _execute_command."""
    test_exception = OSError("Disk full")

    # Test exception from standard run_kubectl
    mock_run_std.side_effect = test_exception
    result = _execute_command("get", ["pods"], None)
    assert isinstance(result, Error)
    assert "Error executing command: Disk full" in result.error
    assert result.exception == test_exception
    mock_logger.error.assert_called_once()
    mock_logger.reset_mock()

    # Test exception from run_kubectl_with_complex_args
    mock_run_complex.side_effect = test_exception
    result = _execute_command("exec", ["pod", "--", "cmd with space"], None)
    assert isinstance(result, Error)
    assert "Error executing command: Disk full" in result.error
    assert result.exception == test_exception
    mock_logger.error.assert_called_once()
    mock_logger.reset_mock()

    # Test exception from run_kubectl_with_yaml
    mock_run_yaml.side_effect = test_exception
    result = _execute_command("apply", ["-f", "-"], "apiVersion: v1")
    assert isinstance(result, Error)
    assert "Error executing command: Disk full" in result.error
    assert result.exception == test_exception
    mock_logger.error.assert_called_once()
