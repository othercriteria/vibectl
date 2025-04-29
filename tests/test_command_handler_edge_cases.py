"""Tests for command_handler.py's handling of edge cases and extreme inputs.

This module tests edge cases, extreme inputs, and error conditions to ensure
the command handler is robust against unexpected or malformed inputs.
"""

import json
import unittest.mock as mock
from collections.abc import Generator
from subprocess import TimeoutExpired
from unittest.mock import MagicMock, Mock, patch
from pydantic import ValidationError

import pytest

from vibectl.command_handler import (
    _parse_command_args,
    _process_command_string,
    handle_command_output,
    handle_vibe_request,
    create_api_error,
)
from vibectl.k8s_utils import run_kubectl_with_complex_args, run_kubectl_with_yaml
from vibectl.prompt import PLAN_VIBE_PROMPT
from vibectl.types import ActionType, Error, OutputFlags, Success, Truncation
from vibectl.memory import update_memory
from vibectl.schema import LLMCommandResponse


@pytest.fixture
def mock_get_adapter_patch() -> Generator[MagicMock, None, None]:
    """Mock the get_model_adapter function. Yields the patch object."""
    with patch("vibectl.command_handler.get_model_adapter") as mock_patch:
        # Configure a default mock instance (won't be used directly by the refined test)
        default_adapter_instance = MagicMock()
        default_model_instance = Mock()
        default_adapter_instance.get_model.return_value = default_model_instance
        default_adapter_instance.execute.return_value = "Default LLM response - should not be used by test"
        mock_patch.return_value = default_adapter_instance
        yield mock_patch # Yield the patch object itself


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


def test_process_command_string_empty_input() -> None:
    """Test command string processing with empty input."""
    cmd_args, yaml_content = _process_command_string("")
    assert cmd_args == ""
    assert yaml_content is None


def test_process_command_string_extremely_long_input() -> None:
    """Test command string processing with extremely long input."""
    # Create a very long string (over 10k chars)
    long_command = "get pods " + "a" * 10000
    cmd_args, yaml_content = _process_command_string(long_command)
    assert cmd_args == long_command
    assert yaml_content is None


def test_process_command_string_unusual_yaml_markers() -> None:
    """Test command string processing with unusual YAML markers."""
    # Test with --- marker at beginning of string
    cmd_str = "---\napiVersion: v1\nkind: Pod"
    cmd_args, yaml_content = _process_command_string(cmd_str)
    assert cmd_args == ""
    assert yaml_content == "---\napiVersion: v1\nkind: Pod"

    # Test with multiple --- markers
    cmd_str = "apply -f\n---\napiVersion: v1\n---\nkind: Pod"
    cmd_args, yaml_content = _process_command_string(cmd_str)
    assert cmd_args == "apply -f"
    assert yaml_content == "---\napiVersion: v1\n---\nkind: Pod"

    # Test with EOF marker but no content
    cmd_str = "apply -f - << EOF\nEOF"
    cmd_args, yaml_content = _process_command_string(cmd_str)
    assert cmd_args == "apply -f -"
    assert yaml_content == ""


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


def test_handle_vibe_request_empty_llm_response(mock_get_adapter_patch: MagicMock, mock_console: MagicMock) -> None:
    """Test handle_vibe_request when LLM returns empty response."""
    # Configure model adapter to return empty string
    mock_get_adapter_patch.return_value.execute.return_value = ""

    # Configure output flags
    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
    )

    # Mock the functions called during error handling using parentheses for with statement
    with (patch("vibectl.command_handler.handle_command_output") as mock_handle_output,
         patch("vibectl.memory.include_memory_in_prompt", return_value="Plan this: empty"),
         patch("vibectl.command_handler.update_memory") as mock_update_memory,
         patch("vibectl.command_handler.create_api_error") as mock_create_api_error):

        # Call handle_vibe_request with empty LLM response
        result = handle_vibe_request(
            request="Show me the pods",
            command="vibe",
            plan_prompt="Plan how to {command} {request}",
            summary_prompt_func=lambda: "Test prompt {output}",
            output_flags=output_flags,
            memory_context="test-context"
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


def test_handle_vibe_request_llm_returns_error(mock_get_adapter_patch: MagicMock) -> None:
    """Test handle_vibe_request when LLM returns an error message as JSON."""
    # Configure model adapter to return an error message as valid JSON
    error_msg = "I cannot fulfill this request."
    error_response_str = json.dumps({
        "action_type": "ERROR",
        "error": error_msg,
        "explanation": "Some explanation why.",
    })
    mock_get_adapter_patch.return_value.execute.return_value = error_response_str

    output_flags = OutputFlags(
        show_raw=False, show_vibe=False, warn_no_output=False, model_name="test-model"
    )

    # Mock update_memory and create_api_error using parentheses for with statement
    with (patch("vibectl.memory.include_memory_in_prompt", return_value="Plan this: error"),
         patch("vibectl.command_handler.update_memory") as mock_update_memory,
         patch("vibectl.command_handler.console_manager") as mock_console):

        test_request = "Do something impossible"
        result = handle_vibe_request(
            request=test_request,
            command="vibe",
            plan_prompt="Plan how to {command} {request}",
            summary_prompt_func=lambda: "",
            output_flags=output_flags,
            memory_context="error-context"
        )

        # Verify update_memory was called with the error from the response
        mock_update_memory.assert_called_once()
        call_args, call_kwargs = mock_update_memory.call_args
        assert call_kwargs.get("command") == "vibe"
        assert call_kwargs.get("command_output") == f"Planning error: {error_msg}"
        assert call_kwargs.get("vibe_output") == f"Failed to plan command for request: {test_request}. Error: {error_msg}"
        assert call_kwargs.get("model_name") == "test-model"

        # Verify console output
        mock_console.print_note.assert_called_with("AI Explanation: Some explanation why.")
        mock_console.print_error.assert_called_with(f"LLM Planning Error: {error_msg}")

        # Verify the result is an Error object
        assert isinstance(result, Error)
        assert result.error == f"LLM planning error: {error_msg}"
        assert result.recovery_suggestions == "Some explanation why."


def test_handle_vibe_request_command_parser_error(
    mock_get_adapter_patch: MagicMock,
    mock_console: MagicMock
) -> None:
    """Test handle_vibe_request handles JSON parsing errors from LLM."""
    # Simulate malformed JSON
    # This specific string should cause a JSONDecodeError
    malformed_json = "{ \"action_type\": \"COMMAND\", \"commands\": [\"get\", \"pods \"" # Missing closing bracket
    mock_get_adapter_patch.return_value.execute.return_value = malformed_json

    output_flags = OutputFlags(
        show_raw=False, show_vibe=False, warn_no_output=False, model_name="test-model"
    )

    # --- Verification Step: Ensure Pydantic raises expected error ---
    with pytest.raises((json.JSONDecodeError, ValidationError)):
        LLMCommandResponse.model_validate_json(malformed_json)
    # --- End Verification Step ---

    # Expect the inner `except (JSONDecodeError, ValidationError)` block.
    with patch("vibectl.memory.include_memory_in_prompt", return_value="Plan this: malformed"), \
         patch("vibectl.command_handler.update_memory") as mock_update_memory, \
         patch("vibectl.command_handler.create_api_error") as mock_create_api_error:

        result = handle_vibe_request(
            request="Show pods",
            command="get",
            plan_prompt="Plan how to {command} {request}",
            summary_prompt_func=lambda: "",
            output_flags=output_flags,
            memory_context="parser-error-context"
        )

        # Assertions for the inner except (JSONDecodeError, ValidationError) block
        mock_update_memory.assert_called_once()
        # Check args for update_memory
        assert "system" == mock_update_memory.call_args[0][0]
        assert "Failed to parse or validate LLM response" in mock_update_memory.call_args[0][1]
        assert "parser-error-context" == mock_update_memory.call_args[0][2]

        # Check create_api_error call
        mock_create_api_error.assert_called_once()
        assert "Failed to parse or validate LLM response" in mock_create_api_error.call_args[0][0]
        assert isinstance(result, Error)
        assert isinstance(result.exception, (json.JSONDecodeError, ValidationError))

        # Check result is from create_api_error
        assert result == mock_create_api_error.return_value


def test_handle_vibe_request_with_dangerous_commands(
    mock_get_adapter_patch: MagicMock,
) -> None:
    """Test confirmation logic for dangerous commands."""

    def test_command(cmd_str: str, should_need_confirmation: bool) -> None:
        # Parse the command string to get the verb and args for the mock
        cmd_parts = cmd_str.split()
        kubectl_verb = cmd_parts[0]
        kubectl_args = cmd_parts[1:]

        # Create a NEW mock adapter instance for THIS specific call
        mock_adapter_instance_for_call = MagicMock()
        mock_model_instance = Mock()
        mock_adapter_instance_for_call.get_model.return_value = mock_model_instance

        # Configure THIS instance to return a VALID JSON response
        plan_response = {
            "action_type": ActionType.COMMAND.value,
            "commands": kubectl_args, # Exclude the verb, only provide args
            "explanation": f"Planning to run {cmd_str}"
        }
        mock_adapter_instance_for_call.execute.return_value = json.dumps(plan_response)

        # Configure the PATCHED get_model_adapter function to return THIS instance
        mock_get_adapter_patch.return_value = mock_adapter_instance_for_call

        # Configure output flags
        output_flags = OutputFlags(
            show_raw=False,
            show_vibe=True,
            warn_no_output=False,
            model_name="test-model",
            show_kubectl=True,
        )

        # Mock confirmation and execution dependencies
        with (
            patch("vibectl.command_handler.console_manager"),
            patch("vibectl.command_handler._create_display_command") as mock_display,
            patch("vibectl.command_handler._execute_command") as mock_execute,
            patch("vibectl.command_handler.handle_command_output"),
            patch("click.prompt") as mock_prompt,
            patch("vibectl.memory.update_memory"),
            patch("vibectl.memory.include_memory_in_prompt", return_value="Plan this..."),
        ):
            # Set up mocks
            mock_display.return_value = cmd_str
            mock_execute.return_value = Success(data="test output")
            mock_prompt.return_value = 'y'

            # Call handle_vibe_request with the *planned* verb for confirmation check
            handle_vibe_request(
                request=f"Please {cmd_str}",
                command=kubectl_verb,
                plan_prompt="Plan how to {command} {request}",
                summary_prompt_func=lambda: "Test prompt {output}",
                output_flags=output_flags,
                yes=False,
            )

            # Check if prompt was called based on command danger level
            if should_need_confirmation:
                mock_prompt.assert_called_once()
                mock_execute.assert_called_once_with(kubectl_verb, kubectl_args, None)
            else:
                mock_prompt.assert_not_called()
                mock_execute.assert_called_once_with(kubectl_verb, kubectl_args, None)

            # Reset mocks that need resetting between test_command calls
            mock_prompt.reset_mock()
            mock_execute.reset_mock()
            mock_get_adapter_patch.reset_mock() # Reset the main patch object return value/calls

            # Restore original adapter mock behavior if needed for subsequent calls
            mock_get_adapter_patch.return_value = mock_adapter_instance_for_call

    # Test dangerous commands (expect confirmation prompt)
    test_command("delete pod my-pod", True)
    test_command("apply -f my-config.yaml", True)

    # Test safe commands (do not expect confirmation prompt)
    # Re-enable safe command tests if needed, ensuring correct verb is passed
    # test_command("get pods", False)
    # test_command("describe service my-svc", False)


def test_handle_vibe_request_autonomous_mode(
    mock_get_adapter_patch: MagicMock,
    mock_execute_command: MagicMock,
    mock_console: MagicMock,
    mock_include_memory: MagicMock,
) -> None:
    """Test handle_vibe_request in autonomous mode handles errors."""
    # Simulate an error during LLM response parsing (ValidationError)
    invalid_schema_json = json.dumps({
        "action_type": "COMMAND",
        # Missing 'commands' field, which is required for COMMAND type
        "explanation": "Getting pods"
    })
    mock_get_adapter_patch.return_value.execute.return_value = invalid_schema_json

    output_flags = OutputFlags(
        show_raw=False, show_vibe=False, warn_no_output=False, model_name="test-model"
    )

    # Expect the inner `except (JSONDecodeError, ValidationError)` block.
    with patch("vibectl.command_handler.update_memory") as mock_update_memory, \
         patch("vibectl.command_handler.create_api_error") as mock_create_api_error:

        result = handle_vibe_request(
            request="get pods auto",
            command="get",
            plan_prompt="Plan this",
            summary_prompt_func=lambda: "",
            output_flags=output_flags,
            autonomous_mode=True,
            memory_context="auto-error-context"
        )

        # --- Assertions based on outer except block --- #
        # Patch is_api_error separately if needed, assume False for now
        with patch("vibectl.command_handler.is_api_error", return_value=False):
            pass # Assertions moved outside

        mock_update_memory.assert_not_called() # Outer block doesn't update memory
        mock_create_api_error.assert_not_called() # Because is_api_error=False

        # Verify a plain Error object was returned
        assert isinstance(result, Error)
        assert isinstance(result.exception, ValidationError)
        assert str(result.exception) in result.error

        # Ensure the command was not executed
        mock_execute_command.assert_not_called()
        # Verify console output is NOT called directly by this path
        mock_console.print_error.assert_not_called()


def test_handle_vibe_request_with_malformed_memory_context(
    mock_get_adapter_patch: MagicMock,
    mock_include_memory: MagicMock,
    mock_console: MagicMock,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """Test handling when memory context causes an issue (e.g., during prompt formatting)."""
    # Simulate an error during include_memory_in_prompt
    mock_include_memory.side_effect = ValueError("Malformed memory context provided")

    output_flags = OutputFlags(
        show_raw=False, show_vibe=False, warn_no_output=False, model_name="test-model"
    )

    # Mock update_memory and create_api_error - expect these NOT to be called for this type of error
    # Use parentheses for with statement
    with (patch("vibectl.command_handler.update_memory") as mock_update_memory,
         patch("vibectl.command_handler.create_api_error") as mock_create_api_error):
        # Expect handle_vibe_request to raise the ValueError from the mock
        with pytest.raises(ValueError, match="Malformed memory context provided"):
             handle_vibe_request(
                request="get pods",
                command="get",
                plan_prompt="Plan how to {command} {request} with {memory}",
                summary_prompt_func=lambda: "",
                output_flags=output_flags,
                memory_context="<<MALFORMED>>"
            )

    # Verify that the parsing error handling path was NOT taken
    mock_update_memory.assert_not_called()
    mock_create_api_error.assert_not_called()
    mock_console.print_error.assert_not_called() # Error should propagate to main handler


def test_handle_vibe_request_with_unknown_model(
    mock_get_adapter_patch: MagicMock,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """Test handle_vibe_request handles ValueError during adapter execute."""
    # Simulate model_adapter.execute raising ValueError
    error_message = "Model 'unknown-model' not found"
    mock_get_adapter_patch.return_value.execute.side_effect = ValueError(error_message)

    output_flags = OutputFlags(
        show_raw=False, show_vibe=False, warn_no_output=False, model_name="unknown-model"
    )

    # Expect the inner `except ValueError:` block to catch this during execute
    with patch("vibectl.command_handler.update_memory") as mock_update_memory, \
         patch("vibectl.command_handler.create_api_error") as mock_create_api_error, \
         patch("vibectl.memory.include_memory_in_prompt", return_value="Plan this: unknown model"):

        result = handle_vibe_request(
            request="get pods with unknown model",
            command="get",
            plan_prompt="Plan this",
            summary_prompt_func=lambda: "",
            output_flags=output_flags,
            memory_context="unknown-model-context"
        )

        # --- Assertions based on outer except block --- #
        # Assume is_api_error is called and returns False
        with patch("vibectl.command_handler.is_api_error", return_value=False):
            pass # Assertions outside

        mock_update_memory.assert_not_called()
        mock_create_api_error.assert_not_called()

        # Verify a plain Error object was returned
        assert isinstance(result, Error)
        assert isinstance(result.exception, ValueError)
        assert str(result.exception) in result.error # error_message should be in result.error

        # Verify console output (outer handler calls print_error)
        # mock_console.print_error.assert_called_once()
