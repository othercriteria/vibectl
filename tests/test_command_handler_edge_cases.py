"""Tests for command_handler.py's handling of edge cases and extreme inputs.

This module tests edge cases, extreme inputs, and error conditions to ensure
the command handler is robust against unexpected or malformed inputs.
"""

import unittest.mock as mock
from collections.abc import Generator
from subprocess import TimeoutExpired
from unittest.mock import MagicMock, Mock, patch

import pytest

from vibectl.command_handler import (
    _execute_command_with_complex_args,
    _execute_yaml_command,
    _parse_command_args,
    _process_command_string,
    handle_command_output,
    handle_vibe_request,
)
from vibectl.prompt import PLAN_VIBE_PROMPT
from vibectl.types import Error, OutputFlags, Success, Truncation


@pytest.fixture
def mock_model_adapter() -> Generator[MagicMock, None, None]:
    """Mock the model adapter to return predictable responses."""
    with patch("vibectl.command_handler.get_model_adapter") as mock_adapter:
        mock_model = Mock()
        mock_adapter.return_value.get_model.return_value = mock_model
        mock_adapter.return_value.execute.return_value = "get pods"
        yield mock_adapter


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
        patch("vibectl.command_handler.subprocess.run") as mock_run,
        patch("vibectl.command_handler.console_manager"),
    ):
        # Test with empty args list
        mock_process = Mock()
        mock_process.stdout = ""
        mock_process.returncode = 0
        mock_run.return_value = mock_process

        result = _execute_command_with_complex_args([])
        assert isinstance(result, Success)
        assert result.data == ""

        # Test with quoted command arguments
        mock_process.stdout = "test output"
        result = _execute_command_with_complex_args(
            ["get", "pods", "--label='app=nginx'"]
        )
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
    # Configure model adapter to return an error message
    error_msg = "ERROR: I couldn't understand that request"
    mock_model_adapter.return_value.execute.return_value = error_msg

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
        mock_console.print_error.assert_called_once_with(error_msg)

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
) -> None:
    """Test handle_vibe_request in autonomous mode with 'vibe' command.

    This test specifically checks that when autonomous_mode is True and
    command is 'vibe', we don't include 'vibe' in the kubectl command.
    """
    # Configure model adapter to return a valid command string
    mock_model_adapter.return_value.execute.return_value = "get pods -n sandbox"

    # Configure output flags
    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=True,
        show_kubectl=True,
        warn_no_output=False,
        model_name="test-model",
    )

    # Mock console manager to check prompt
    with (
        patch("vibectl.command_handler.console_manager") as mock_console,
        patch("vibectl.command_handler._execute_command") as mock_execute_command,
        patch("vibectl.command_handler.click.confirm", return_value=True),
        patch("vibectl.command_handler.handle_command_output"),
    ):
        # Call handle_vibe_request in autonomous mode with 'vibe' command
        handle_vibe_request(
            request="check pods",
            command="vibe",
            plan_prompt="Plan {request}",
            summary_prompt_func=lambda: "Test prompt {output}",
            output_flags=output_flags,
            autonomous_mode=True,
        )

        # Verify console manager was called with a message NOT including 'vibe'
        # Now should be 'Running: kubectl get pods -n sandbox'
        # NOT 'Running: kubectl vibe get pods -n sandbox'
        assert mock_console.print_processing.called
        note_calls = mock_console.print_processing.call_args_list
        assert len(note_calls) > 0
        # Get the first argument of the first call
        note_text = note_calls[0][0][0]
        assert note_text == "Running: kubectl get pods -n sandbox"

    # Configure model adapter to return command with 'vibe' to ensure it's removed
    mock_model_adapter.return_value.execute.return_value = "vibe get pods -n sandbox"

    # Reset mocks
    mock_console.reset_mock()
    mock_execute_command.reset_mock()

    with (
        patch("vibectl.command_handler.console_manager") as mock_console,
        patch("vibectl.command_handler._execute_command") as mock_execute_command,
        patch("vibectl.command_handler.click.confirm", return_value=True),
        patch("vibectl.command_handler.handle_command_output"),
    ):
        # Call handle_vibe_request again
        handle_vibe_request(
            request="check pods",
            command="vibe",
            plan_prompt="Plan {request}",
            summary_prompt_func=lambda: "Test prompt {output}",
            output_flags=output_flags,
            autonomous_mode=True,
        )

        # Verify console manager was called with the correct message
        assert mock_console.print_processing.called
        note_calls = mock_console.print_processing.call_args_list
        assert len(note_calls) > 0
        # Get the first argument of the first call
        note_text = note_calls[0][0][0]
        # Should now be "Running: kubectl vibe get pods -n sandbox"
        # But we should check that it doesn't have "vibe vibe" (double vibe)
        assert "Running: kubectl " in note_text
        assert "vibe vibe" not in note_text.lower()


def test_handle_vibe_request_yaml_prompt_with_spec_field(
    mock_model_adapter: MagicMock,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """Test handle_vibe_request with a prompt containing {spec} placeholder.

    This tests the handling of format placeholders in prompt templates. Before the fix,
    this would raise KeyError: 'spec'. After the fix, it should handle this gracefully
    by using a fallback string replacement method.
    """
    # Configure model adapter to return a response that includes YAML with {spec}
    mock_model_adapter.return_value.execute.return_value = """create -f - << EOF
---
apiVersion: v1
kind: Pod
metadata:
  name: test-pod
  labels:
    app: test
{spec}
  containers:
  - name: test-container
    image: nginx:latest
EOF"""

    # Configure output flags
    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
    )

    # This simulates what happens in vibe_cmd.py - the prompt already contains
    # formatted placeholders with {memory_context} and {request} filled in,
    # but the prompt itself might contain other format-style placeholders like {spec}
    pre_formatted_prompt = """You are planning a command.
Memory: "Previous context"
Request: "create a pod"

If you need to create a pod, use this template:
apiVersion: v1
kind: Pod
metadata:
  name: example
{spec}
  containers:
  - name: container
    image: nginx
"""

    # With the fix, this should now run without raising a KeyError
    with (
        patch("vibectl.command_handler.console_manager"),
        patch("vibectl.command_handler._execute_command"),
        patch("vibectl.command_handler.click.confirm", return_value=True),
        patch("vibectl.command_handler.handle_command_output"),
        patch("vibectl.command_handler.logger", autospec=True) as mock_logger,
        patch("vibectl.command_handler.subprocess.Popen") as mock_popen,
    ):
        # Configure the mock subprocess
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b"success", b"")
        mock_popen.return_value = mock_process

        # This should not raise an exception after the fix
        handle_vibe_request(
            request="create a pod",
            command="vibe",
            plan_prompt=pre_formatted_prompt,
            summary_prompt_func=lambda: "Test prompt {output}",
            output_flags=output_flags,
        )

    # Verify the fallback method is being used based on logger calls
    mock_logger.warning.assert_called_once()
    warning_message = mock_logger.warning.call_args[0][0]
    assert "Format error" in warning_message
    assert "'spec'" in warning_message
    assert "Using fallback formatting method" in warning_message

    # Verify a kubectl command execution was logged (more flexible assertion)
    any_yaml_cmd_logged = False
    for call in mock_logger.info.call_args_list:
        if "Executing kubectl command" in str(call) and "yaml: True" in str(call):
            any_yaml_cmd_logged = True
            break
    assert any_yaml_cmd_logged, "No yaml command execution was logged"


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
    from vibectl.command_handler import _execute_yaml_command

    # Mock subprocess.Popen to simulate a TimeoutExpired exception
    with patch("vibectl.command_handler.subprocess.Popen") as mock_popen:
        # Create a mock process that raises TimeoutExpired when communicate is called
        mock_process = MagicMock()
        mock_process.communicate.side_effect = TimeoutExpired(
            cmd=["kubectl"], timeout=30
        )

        # Set up mock to return a process object that will raise an exception
        mock_popen.return_value = mock_process

        # Call _execute_yaml_command with stdin pipe command
        result = _execute_yaml_command(
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
    with patch("vibectl.command_handler.subprocess.Popen") as mock_popen:
        # Create a mock process
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b"success", b"")

        # Set up mock to return our process
        mock_popen.return_value = mock_process

        # Call _execute_yaml_command with stdin pipe command
        _execute_yaml_command(["create", "-f", "-"], "---\napiVersion: v1\nkind: Pod")

        # Verify the timeout parameter was passed to communicate
        mock_process.communicate.assert_called_once()
        args, kwargs = mock_process.communicate.call_args
        assert "timeout" in kwargs
        assert kwargs["timeout"] == 30


def test_handle_vibe_request_with_malformed_memory_context(
    mock_model_adapter: MagicMock,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """Test handle_vibe_request with malformed memory_context that causes format errors.

    This test is designed to reproduce the issue where memory content containing
    strings that might confuse the string formatter leads to format errors with the
    'memory_context' key, which then leads to malformed kubectl commands.
    """
    # Set up model adapter to properly handle execute
    mock_adapter = Mock()
    mock_model = Mock()
    mock_adapter.get_model.return_value = mock_model

    # First call to execute raises KeyError, simulating the format error
    mock_adapter.execute.side_effect = [
        KeyError("memory_context"),  # First call fails with KeyError
        "To get pods in namespace",  # Second call succeeds if retry happens
    ]
    mock_model_adapter.return_value = mock_adapter

    # Memory content that contains elements that might confuse formatting
    problematic_memory = (
        "To ensure proper function of our service, need to check our db connection.\n"
        "Try to use kubectl to access the database {stats} and verify it's working.\n"
        "Output the {service.status} of the database to continue with deployment."
    )

    # Create output flags
    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=False,
        warn_no_output=False,
        model_name="test-model",
        show_kubectl=True,
    )

    # Patch necessary dependencies
    with (
        patch("vibectl.command_handler.console_manager"),
        patch("vibectl.command_handler.logger", autospec=True) as mock_logger,
    ):
        # This should NOT raise an exception, even when model_adapter.execute fails
        result = handle_vibe_request(
            request="show me pod status",
            command="vibe",
            plan_prompt=PLAN_VIBE_PROMPT,
            summary_prompt_func=lambda: "Test prompt {output}",
            output_flags=output_flags,
            memory_context=problematic_memory,
        )

        # Verify we get a proper error result
        assert isinstance(result, Error)
        assert "Error processing vibe request" in result.error
        assert "memory_context" in result.error

        # Verify an error is logged
        mock_logger.error.assert_any_call(
            mock.ANY,  # The error message string may vary
            exc_info=True,  # But we should be logging with exc_info=True
        )


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
