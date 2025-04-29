"""Tests for command_handler.py's handling of edge cases and extreme inputs.

This module tests edge cases, extreme inputs, and error conditions to ensure
the command handler is robust against unexpected or malformed inputs.
"""

import json
from collections.abc import Generator
from unittest.mock import MagicMock, Mock, patch

import pytest
from pydantic import ValidationError

from vibectl.command_handler import (
    ActionType,
    OutputFlags,
    _parse_command_args,
    handle_command_output,
    handle_vibe_request,
)
from vibectl.k8s_utils import run_kubectl_with_complex_args
from vibectl.types import Error, Success, Truncation


@pytest.fixture
def mock_get_adapter_patch() -> Generator[MagicMock, None, None]:
    """Mock the get_model_adapter function. Yields the mocked adapter instance."""
    with patch("vibectl.command_handler.get_model_adapter") as mock_patch:
        # Create the mock adapter instance that the factory will return
        mock_adapter_instance = MagicMock()

        # Configure default behavior for the adapter's methods if needed
        # For instance, mock get_model to avoid errors if called unexpectedly
        mock_model_instance = Mock()
        mock_adapter_instance.get_model.return_value = mock_model_instance
        # execute will typically be configured per-test
        mock_adapter_instance.execute = MagicMock()

        # Configure the factory patch to return our mock instance
        mock_patch.return_value = mock_adapter_instance

        # Yield the mock adapter instance for tests to use and configure
        yield mock_adapter_instance  # Yield the instance (Correct)


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


def test_parse_command_args_invalid_quotes() -> None:
    """Test command argument parsing with invalid quotes."""
    # Unbalanced quotes
    args = _parse_command_args('get pod "test-pod')
    assert len(args) == 3
    assert args == ["get", "pod", '"test-pod']

    # Mixed quotes
    args = _parse_command_args("get pod \"test-pod'")
    assert len(args) == 3
    assert args == ["get", "pod", "\"test-pod'"]


def test_parse_command_args_special_characters() -> None:
    """Test command argument parsing with special characters."""
    # Command with special characters
    args = _parse_command_args(
        'get pods -l app=nginx,env=prod --sort-by="{.status.phase}"'
    )
    assert len(args) == 5
    assert args[-1] == "--sort-by={.status.phase}"

    # Command with glob patterns
    args = _parse_command_args("get pods app-*")
    assert len(args) == 3
    assert args[-1] == "app-*"


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
        long_output = "A" * 100000  # 100k chars
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

        # Verify update_memory was NOT called because the function returns early
        mock_update_memory.assert_not_called()
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

        # Verify console output
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
            "Failed to parse or validate LLM response" in caplog.text
        )  # Check log capture
        assert "LLM Output:" in caplog.text
        assert malformed_response in caplog.text


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

        # Check AI Explanation was printed
        mock_console.print_note.assert_called_with("AI Explanation: Fetching pods.")


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
        patch("vibectl.command_handler.is_api_error") as mock_is_api_error,
    ):
        mock_is_api_error.return_value = False  # Assume not API error

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
        assert "COMMAND action with no commands" in kwargs.get("command_output", "")
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
    def test_command(cmd_str: str, should_need_confirmation: bool) -> None:
        # Configure model response
        plan_response = {
            "action_type": ActionType.COMMAND.value,
            "commands": [cmd_str],  # Pass command as list element
            "explanation": f"Executing: {cmd_str}",
        }
        mock_get_adapter_patch.execute.return_value = json.dumps(plan_response)

        output_flags = OutputFlags(
            show_raw=True, show_vibe=True, warn_no_output=False, model_name="test-model"
        )

        # Mock _needs_confirmation and _handle_command_confirmation
        with (
            patch("vibectl.command_handler._needs_confirmation") as mock_needs,
            patch(
                "vibectl.command_handler._handle_command_confirmation"
            ) as mock_confirm,
            patch("vibectl.command_handler._execute_command") as mock_execute,
            patch("vibectl.memory.include_memory_in_prompt"),
        ):  # Mock memory include
            mock_needs.return_value = should_need_confirmation
            # Simulate user cancelling if confirmation is asked
            mock_confirm.return_value = Success("Command execution cancelled by user")
            mock_execute.return_value = Success("Executed successfully")

            result = handle_vibe_request(
                request=f"Run {cmd_str}",
                command="vibe",  # Assume vibe is the base command
                plan_prompt="Plan",
                summary_prompt_func=lambda: "Summary",
                output_flags=output_flags,
                yes=False,  # Ensure confirmation is potentially triggered
            )

            # Assert _needs_confirmation was called with the original command verb
            mock_needs.assert_called_once_with("vibe", False)

            if should_need_confirmation:
                mock_confirm.assert_called_once()
                assert isinstance(result, Success)
                assert result.message == "Command execution cancelled by user"
                mock_execute.assert_not_called()
            else:
                mock_confirm.assert_not_called()
                mock_execute.assert_called_once()
                # Allow result to be the Success from execute

            # Reset mocks for next sub-test
            mock_needs.reset_mock()
            mock_confirm.reset_mock()
            mock_execute.reset_mock()
            mock_get_adapter_patch.reset_mock()  # Reset the correct mock

    # Test cases
    test_command("get pods", False)  # Safe command
    test_command("delete pod my-pod", True)  # Dangerous command
    test_command("apply -f config.yaml", True)  # Dangerous command
    test_command("scale deployment/app --replicas=0", True)  # Dangerous
    test_command("logs my-pod", False)  # Safe


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
        assert call_kwargs.get("command_output") == expected_error_string
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
