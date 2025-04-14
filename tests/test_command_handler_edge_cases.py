"""Tests for command_handler.py's handling of edge cases and extreme inputs.

This module tests edge cases, extreme inputs, and error conditions to ensure
the command handler is robust against unexpected or malformed inputs.
"""

from collections.abc import Generator
from unittest.mock import MagicMock, Mock, patch

import pytest

from vibectl.command_handler import (
    _execute_command_with_complex_args,
    _filter_kubeconfig_flags,
    _parse_command_args,
    _process_command_string,
    handle_command_output,
    handle_vibe_request,
)
from vibectl.types import OutputFlags


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


def test_filter_kubeconfig_flags_special_cases() -> None:
    """Test kubeconfig flag filtering with special cases."""
    # Test with multiple kubeconfig flags
    args = [
        "get",
        "pods",
        "--kubeconfig",
        "/path/to/config",
        "--kubeconfig",
        "/another/path",
    ]
    filtered = _filter_kubeconfig_flags(args)
    assert filtered == ["get", "pods"]

    # Test with kubeconfig flags at beginning
    args = ["--kubeconfig", "/path/to/config", "get", "pods"]
    filtered = _filter_kubeconfig_flags(args)
    assert filtered == ["get", "pods"]

    # Test with kubeconfig flags at end
    args = ["get", "pods", "--kubeconfig", "/path/to/config"]
    filtered = _filter_kubeconfig_flags(args)
    assert filtered == ["get", "pods"]

    # Test with equals sign format
    args = ["get", "pods", "--kubeconfig=/path/to/config"]
    filtered = _filter_kubeconfig_flags(args)
    assert filtered == ["get", "pods"]


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
        assert result == ""

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
        mock_processor.process_auto.return_value = ("processed content", False)

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
        mock_processor.process_auto.return_value = (long_output[:1000], True)
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

    # Mock console manager and note
    with (
        patch("vibectl.command_handler.console_manager") as mock_console,
        patch("vibectl.command_handler.handle_command_output") as mock_handle_output,
    ):
        # Call handle_vibe_request with error response
        handle_vibe_request(
            request="Show me the pods",
            command="get",
            plan_prompt="Plan how to {command} {request}",
            summary_prompt_func=lambda: "Test prompt {output}",
            output_flags=output_flags,
        )

        # Verify note was printed with the error message
        mock_console.print_note.assert_called_once()

        # Verify handle_command_output was not called
        mock_handle_output.assert_not_called()


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
            )

            # Check if confirm was called based on command danger level
            if should_need_confirmation:
                mock_confirm.assert_called_once()
            else:
                mock_confirm.assert_not_called()

    # Test dangerous commands
    test_command("delete pod my-pod", True)
    test_command("scale deployment my-app --replicas=3", True)
    test_command("create deployment my-app", True)

    # Test safe commands
    test_command("get pods", False)
    test_command("describe pod my-pod", False)
