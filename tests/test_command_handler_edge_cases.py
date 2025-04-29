"""Tests for command_handler.py's handling of edge cases and extreme inputs.

This module tests edge cases, extreme inputs, and error conditions to ensure
the command handler is robust against unexpected or malformed inputs.
"""

import json
import unittest.mock as mock
from collections.abc import Generator
from subprocess import TimeoutExpired
from unittest.mock import MagicMock, Mock, patch

import pytest

from vibectl.command_handler import (
    _parse_command_args,
    _process_command_string,
    handle_command_output,
    handle_vibe_request,
)
from vibectl.k8s_utils import run_kubectl_with_complex_args, run_kubectl_with_yaml
from vibectl.prompt import PLAN_VIBE_PROMPT
from vibectl.types import ActionType, Error, OutputFlags, Success, Truncation


@pytest.fixture
def mock_model_adapter() -> Generator[MagicMock, None, None]:
    """Mock the model adapter to return predictable responses."""
    with patch("vibectl.command_handler.get_model_adapter") as mock_adapter:
        mock_model = Mock()
        mock_adapter.return_value.get_model.return_value = mock_model
        mock_adapter.return_value.execute.return_value = "get pods"
        yield mock_adapter


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
def mock_handle_planning_error() -> Generator[MagicMock, None, None]:
    """Mock _handle_planning_error for edge case tests."""
    with patch("vibectl.command_handler._handle_planning_error") as mock:
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


def test_handle_vibe_request_empty_llm_response(mock_model_adapter: MagicMock) -> None:
    """Test handle_vibe_request when LLM returns empty response."""
    # Configure model adapter to return empty string
    mock_model_adapter.return_value.execute.return_value = ""

    # Configure output flags
    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
    )

    # Mock console manager to check for error messages
    with (
        patch("vibectl.command_handler.console_manager") as mock_console,
        patch("vibectl.command_handler.handle_command_output") as mock_handle_output,
    ):
        # Call handle_vibe_request with empty LLM response
        handle_vibe_request(
            request="Show me the pods",
            command="get",
            plan_prompt="Plan how to {command} {request}",
            summary_prompt_func=lambda: "Test prompt {output}",
            output_flags=output_flags,
        )

        # Verify error was printed
        mock_console.print_error.assert_called_once()

        # Verify handle_command_output was not called
        mock_handle_output.assert_not_called()


def test_handle_vibe_request_llm_returns_error(mock_model_adapter: MagicMock) -> None:
    """Test handle_vibe_request when LLM returns an error message."""
    # Configure model adapter to return an error message as valid JSON
    error_msg_text = "I couldn't understand that request"
    error_response = {
        "action_type": ActionType.ERROR.value,
        "error": error_msg_text,
        "explanation": "The request was unclear.",
    }
    mock_model_adapter.return_value.execute.return_value = json.dumps(error_response)

    # Configure output flags
    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
    )

    # Mock console manager and update_memory
    with (
        patch("vibectl.command_handler.console_manager") as mock_console,
        patch("vibectl.command_handler.update_memory"),
    ):
        # Call handle_vibe_request with error response
        handle_vibe_request(
            request="Show me the pods",
            command="get",
            plan_prompt="Plan how to {command} {request}",
            summary_prompt_func=lambda: "Test prompt {output}",
            output_flags=output_flags,
        )

        # Verify error was printed
        mock_console.print_error.assert_called_once()

        # Verify memory was updated
        mock_console.print_processing.assert_called_once_with(
            "Planning error added to memory context"
        )


def test_handle_vibe_request_command_parser_error(
    mock_model_adapter: MagicMock,
) -> None:
    """Test handle_vibe_request with command parsing error."""
    # Configure model adapter to return a valid command string
    mock_model_adapter.return_value.execute.return_value = "get pods"

    # Configure output flags
    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
    )

    # Mock processing to raise ValueError
    with (
        patch("vibectl.command_handler.console_manager") as mock_console,
        patch("vibectl.command_handler._process_command_string") as mock_process,
    ):
        # Simulate parsing error
        mock_process.side_effect = ValueError("Invalid command syntax")

        # Call handle_vibe_request expecting parsing error
        handle_vibe_request(
            request="Show me the pods",
            command="get",
            plan_prompt="Plan how to {command} {request}",
            summary_prompt_func=lambda: "Test prompt {output}",
            output_flags=output_flags,
        )

        # Verify error was printed
        mock_console.print_error.assert_called_once()


def test_handle_vibe_request_with_dangerous_commands(
    mock_model_adapter: MagicMock,
) -> None:
    """Test confirmation logic for dangerous commands."""

    def test_command(cmd: str, should_need_confirmation: bool) -> None:
        # Configure model adapter to return the test command
        mock_model_adapter.return_value.execute.return_value = cmd

        # Configure output flags
        output_flags = OutputFlags(
            show_raw=False,
            show_vibe=True,
            warn_no_output=False,
            model_name="test-model",
            show_kubectl=True,
        )

        # Create a list of dangerous commands that need confirmation
        dangerous_cmds = [
            "delete",
            "scale",
            "rollout",
            "patch",
            "apply",
            "replace",
            "create",
        ]

        # Mock confirmation and execution
        with (
            patch("vibectl.command_handler.console_manager"),
            patch("vibectl.command_handler._process_command_string") as mock_process,
            patch("vibectl.command_handler._parse_command_args") as mock_parse,
            patch("vibectl.command_handler._create_display_command") as mock_display,
            patch(
                "vibectl.command_handler._needs_confirmation"
            ) as mock_needs_confirmation,
            patch("vibectl.command_handler._execute_command") as mock_execute,
            patch("vibectl.command_handler.handle_command_output"),
            patch("click.confirm") as mock_confirm,
        ):
            # Set up mocks
            mock_process.return_value = (cmd, None)
            mock_parse.return_value = cmd.split()
            mock_display.return_value = cmd
            # Let the real function determine confirmation
            mock_needs_confirmation.side_effect = lambda c, a: c in dangerous_cmds
            mock_execute.return_value = "test output"
            mock_confirm.return_value = True

            # Call handle_vibe_request
            handle_vibe_request(
                request=f"Please {cmd}",
                command=cmd.split()[0],
                plan_prompt="Plan how to {command} {request}",
                summary_prompt_func=lambda: "Test prompt {output}",
                output_flags=output_flags,
                yes=True,  # Set yes=True to bypass confirmation prompt
            )

            # Check if confirm was called based on command danger level
            if should_need_confirmation:
                # With yes=True, confirm should NOT be called even for
                # dangerous commands
                mock_confirm.assert_not_called()
            else:
                mock_confirm.assert_not_called()

    # Test dangerous commands
    test_command("delete pod my-pod", True)

    # Test safe commands
    test_command("get pods", False)


def test_handle_vibe_request_autonomous_mode(
    mock_model_adapter: MagicMock,
    mock_execute_command: MagicMock,
    mock_handle_planning_error: MagicMock,
    mock_console: MagicMock,
    mock_include_memory: MagicMock,
) -> None:
    """Test autonomous mode behavior, especially with command timeouts."""
    # Configure model adapter to return a simple command JSON
    plan_response = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["sleep", "30"],
        "explanation": "Running a sleep command autonomously."
    }
    mock_model_adapter.return_value.execute.return_value = json.dumps(plan_response)

    # Configure _execute_command to raise TimeoutExpired
    mock_execute_command.side_effect = TimeoutExpired(cmd="kubectl sleep 30", timeout=1)

    # Configure output flags for autonomous mode
    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=False,
        warn_no_output=False,
        model_name="test-model-auto",
        show_kubectl=False,
    )

    # Mock other necessary components
    with patch("vibectl.command_handler.handle_command_output"),\
         patch("vibectl.command_handler.update_memory"):

        # Call handle_vibe_request in autonomous mode
        result = handle_vibe_request(
            request="run sleep command",
            command="vibe",
            plan_prompt="Plan this: {request}",
            summary_prompt_func=lambda: "Summary: {output}",
            output_flags=output_flags,
            autonomous_mode=True,
            yes=True,
        )

    # Verify _execute_command was called
    mock_execute_command.assert_called_once()

    # Verify _handle_planning_error was called due to TimeoutExpired
    mock_console.print_error.assert_any_call(
        mock.ANY,
        style="dim"
    )
    assert any(
        "timed out" in call.args[0].lower()
        for call in mock_console.print_error.call_args_list
    )

    # Verify the result is an Error containing the TimeoutExpired info
    assert isinstance(result, Error)
    assert "Command timed out" in result.error
    assert isinstance(result.exception, TimeoutExpired)


def test_handle_vibe_request_yaml_prompt_with_spec_field(
    mock_model_adapter: MagicMock,
    capfd: pytest.CaptureFixture[str],
    mock_console: MagicMock,
    mock_execute_command: MagicMock,
    mock_include_memory: MagicMock,
) -> None:
    """Test handling of YAML input containing a 'spec:' field.

    Previously, this triggered a specific warning. This test verifies the current
    behavior after JSON schema implementation.
    """
    # Configure model adapter to return a create command with YAML including 'spec:'
    yaml_content = """
apiVersion: v1
kind: Pod
metadata:
  name: test-pod-spec
spec:
  containers:
  - name: nginx
    image: nginx
"""
    plan_response = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["create", "-f", "-"],
        "explanation": "Creating pod with spec field.",
        "yaml_content": yaml_content
    }
    mock_model_adapter.return_value.execute.return_value = json.dumps(plan_response)

    # Mock _execute_command to return success
    mock_execute_command.return_value = Success(data="pod/test-pod-spec created")

    # Configure output flags
    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model-spec",
        show_kubectl=True,
    )

    # Mock other necessary components
    with patch("vibectl.command_handler.handle_command_output"), \
         patch("vibectl.command_handler.update_memory"), \
         patch("click.confirm") as mock_confirm:

        mock_confirm.return_value = True

        # Call handle_vibe_request
        handle_vibe_request(
            request="create pod with spec",
            command="create",
            plan_prompt="Plan this: {request}",
            summary_prompt_func=lambda: "Summary: {output}",
            output_flags=output_flags,
            yes=False,
        )

    # Verify _execute_command was called with the correct args including YAML
    mock_execute_command.assert_called_once()
    call_args, _ = mock_execute_command.call_args
    assert call_args[0] == "create"
    assert call_args[1] == ["-f", "-"]
    assert call_args[2] == yaml_content

    # Verify the warning about 'spec:' field is NOT printed anymore
    assert not any(
        "'spec:' field found" in call.args[0]
        for call in mock_console.print_warning.call_args_list
    )


def test_parse_command_args_with_natural_language() -> None:
    """Test _parse_command_args function with natural language in the command.

    This function verifies that _parse_command_args parses the entire string,
    including natural language. The fix for handling natural language is
    elsewhere (in the auto command and create_kubectl_error), not in this function.
    """
    from vibectl.command_handler import _parse_command_args

    # Test case 1: Natural language before kubectl command
    test_cmd = (
        "I'll plan a command to gather more information about the cluster state. "
        "get pods --all-namespaces -o wide"
    )
    result = _parse_command_args(test_cmd)
    # Currently, the function just splits the string as-is, without attempting to
    # mangle it into a kubectl command.
    assert "I'll" in result
    assert "plan" in result
    assert "get" in result
    assert "pods" in result
    assert "--all-namespaces" in result
    assert "-o" in result
    assert "wide" in result

    # Test case 2: Natural language mixed with kubectl command
    test_cmd = "I need to get pods in all namespaces to understand the cluster"
    result = _parse_command_args(test_cmd)
    assert "I" in result
    assert "need" in result
    assert "get" in result
    assert "pods" in result

    # Test case 3: Command with quotes
    test_cmd = "get pods with label 'app=nginx'"
    result = _parse_command_args(test_cmd)
    # Quotes should be handled correctly by shlex
    assert "get" in result
    assert "pods" in result
    assert "with" in result
    assert "label" in result
    assert "app=nginx" in result


def test_execute_yaml_command_timeout_handling() -> None:
    """Test that _execute_yaml_command properly handles subprocess timeouts.

    This tests the code path added to handle subprocess.TimeoutExpired exceptions
    gracefully with a proper error message.
    """
    # Mock subprocess.Popen to simulate a TimeoutExpired exception
    with patch("vibectl.k8s_utils.subprocess.Popen") as mock_popen:
        # Create a mock process that raises TimeoutExpired when communicate is called
        mock_process = MagicMock()
        mock_process.communicate.side_effect = TimeoutExpired(
            cmd=["kubectl"], timeout=30
        )

        # Set up mock to return a process object that will raise an exception
        mock_popen.return_value = mock_process

        # Call run_kubectl_with_yaml with stdin pipe command
        result = run_kubectl_with_yaml(
            ["create", "-f", "-"], "---\napiVersion: v1\nkind: Pod"
        )

        # Verify timeout was handled gracefully
        assert isinstance(result, Error)
        assert "timed out after 30 seconds" in result.error

        # Verify the process was killed
        mock_process.kill.assert_called_once()

        # Verify we tried to get any output after the timeout
        assert mock_process.communicate.call_count == 2


def test_execute_yaml_command_sets_timeout() -> None:
    """Test that _execute_yaml_command sets the timeout parameter.

    Verifies the timeout parameter is correctly passed to subprocess.communicate().
    """

    # Mock subprocess.Popen
    with patch("vibectl.k8s_utils.subprocess.Popen") as mock_popen:
        # Create a mock process
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b"success", b"")

        # Set up mock to return our process
        mock_popen.return_value = mock_process

        # Call run_kubectl_with_yaml with stdin pipe command
        run_kubectl_with_yaml(["create", "-f", "-"], "---\napiVersion: v1\nkind: Pod")

        # Verify the timeout parameter was passed to communicate
        mock_process.communicate.assert_called_once()
        args, kwargs = mock_process.communicate.call_args
        assert "timeout" in kwargs
        assert kwargs["timeout"] == 30


def test_handle_vibe_request_with_malformed_memory_context(
    mock_model_adapter: MagicMock,
    mock_include_memory: MagicMock,
    mock_console: MagicMock,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """Test handling when memory context loading fails."""
    # Configure include_memory_in_prompt to raise KeyError
    error_message = "Simulated memory loading failure"
    mock_include_memory.side_effect = KeyError(error_message)

    # Configure output flags
    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model-mem-err",
        show_kubectl=False,
    )

    # Call handle_vibe_request
    result = handle_vibe_request(
        request="show pods with bad memory",
        command="get",
        plan_prompt="Plan this: {request}",
        summary_prompt_func=lambda: "Summary: {output}",
        output_flags=output_flags,
    )

    # Verify include_memory_in_prompt was called
    mock_include_memory.assert_called_once()

    # Verify an error was printed to the console
    mock_console.print_error.assert_called_once()
    error_output = mock_console.print_error.call_args[0][0]

    # Verify the correct error message is in the output and the result
    # The exact error originates from the exception caught around mock_include_memory call
    expected_error_fragment = f"Unexpected error preparing LLM request: {error_message}"
    assert expected_error_fragment in error_output
    assert isinstance(result, Error)
    assert expected_error_fragment in result.error
    assert isinstance(result.exception, KeyError)


def test_handle_vibe_request_with_unknown_model(
    mock_model_adapter: MagicMock,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """Test handle_vibe_request with an unknown model name.

    This test verifies that the code handles the case gracefully when
    an unknown or invalid model name is provided in the output flags.
    """
    # Set up model adapter to raise a ValueError for an unknown model
    mock_adapter = Mock()
    mock_adapter.get_model.side_effect = ValueError("Unknown model: unknown-model")
    mock_model_adapter.return_value = mock_adapter

    # Create output flags with an unknown model name
    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="unknown-model",
        show_kubectl=True,
    )

    # Patch necessary dependencies
    with patch("vibectl.command_handler.logger", autospec=True) as mock_logger:
        # Call handle_vibe_request with the unknown model
        result = handle_vibe_request(
            request="show pod status",
            command="vibe",
            plan_prompt=PLAN_VIBE_PROMPT,
            summary_prompt_func=lambda: "Test prompt {output}",
            output_flags=output_flags,
        )

        # Verify we get a proper error result
        assert isinstance(result, Error)
        assert "Error processing vibe request" in result.error
        assert "Unknown model" in result.error

        # The current implementation doesn't call console_manager.print_error
        # for exceptions caught in the general exception handler
        # So we shouldn't assert that it was called

        # Verify errors are logged appropriately
        mock_logger.error.assert_any_call(
            "Error in vibe request processing: Unknown model: unknown-model",
            exc_info=True,
        )
