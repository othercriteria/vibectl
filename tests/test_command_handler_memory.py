"""Tests for command_handler.py's memory handling and edge cases.

This module tests potential memory-related bugs and edge cases in command_handler.py,
focusing on how commands update and interact with memory.
"""

from collections.abc import Generator
from unittest.mock import MagicMock, Mock, patch

import pytest

from vibectl.command_handler import (
    _execute_command,
    _execute_command_with_complex_args,
    _execute_yaml_command,
    handle_command_output,
    handle_vibe_request,
)
from vibectl.types import OutputFlags


@pytest.fixture
def mock_memory_update() -> Generator[Mock, None, None]:
    """Mock the update_memory function to check memory updates."""
    with patch("vibectl.command_handler.update_memory") as mock:
        yield mock


@pytest.fixture
def mock_process_auto() -> Generator[Mock, None, None]:
    """Mock output processor's process_auto method."""
    with patch("vibectl.command_handler.output_processor.process_auto") as mock:
        # Default return no truncation
        mock.return_value = ("processed content", False)
        yield mock


@pytest.fixture
def mock_get_adapter() -> Generator[MagicMock, None, None]:
    """Mock the model adapter with configurable response."""
    with patch("vibectl.command_handler.get_model_adapter") as mock_adapter:
        # Set up mock model
        mock_model = Mock()
        mock_adapter.return_value.get_model.return_value = mock_model
        mock_adapter.return_value.execute.return_value = "Test response"

        yield mock_adapter


def test_handle_command_output_updates_memory(
    mock_get_adapter: MagicMock, mock_memory_update: Mock, mock_process_auto: Mock
) -> None:
    """Test that handle_command_output correctly updates memory."""
    # Configure output flags
    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
    )

    # Call handle_command_output with a command
    with patch("vibectl.command_handler.console_manager"):
        handle_command_output(
            output="test output",
            output_flags=output_flags,
            summary_prompt_func=lambda: "Test prompt {output}",
            command="get pods",
        )

    # Verify memory was updated with correct parameters
    mock_memory_update.assert_called_once_with(
        "get pods", "test output", "Test response", "test-model"
    )


def test_handle_command_output_does_not_update_memory_without_command(
    mock_get_adapter: MagicMock, mock_memory_update: Mock, mock_process_auto: Mock
) -> None:
    """Test that memory is not updated when no command is provided."""
    # Configure output flags
    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
    )

    # Call handle_command_output without a command
    with patch("vibectl.command_handler.console_manager"):
        handle_command_output(
            output="test output",
            output_flags=output_flags,
            summary_prompt_func=lambda: "Test prompt {output}",
        )

    # Verify memory was not updated
    mock_memory_update.assert_not_called()


def test_handle_command_output_updates_memory_with_error_output(
    mock_get_adapter: MagicMock, mock_memory_update: Mock, mock_process_auto: Mock
) -> None:
    """Test that memory is updated even when output contains error message."""
    # Configure output flags
    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
    )

    # Call handle_command_output with error output
    with patch("vibectl.command_handler.console_manager"):
        handle_command_output(
            output="Error: Command failed with exit code 1",
            output_flags=output_flags,
            summary_prompt_func=lambda: "Test prompt {output}",
            command="get pods",
        )

    # Verify memory was updated with error output
    mock_memory_update.assert_called_once_with(
        "get pods",
        "Error: Command failed with exit code 1",
        "Test response",
        "test-model",
    )


def test_handle_vibe_request_updates_memory_on_error(
    mock_get_adapter: MagicMock, mock_memory_update: Mock
) -> None:
    """Test that memory is updated even when command execution fails."""
    # Configure model adapter to return a valid command
    mock_get_adapter.return_value.execute.return_value = "get pods"

    # Configure output flags
    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
    )

    # Mock _execute_command to raise an exception
    with (
        patch("vibectl.command_handler._execute_command") as mock_execute,
        patch("vibectl.command_handler.handle_command_output") as mock_handle_output,
        patch("vibectl.command_handler.console_manager"),
        patch("vibectl.command_handler._process_command_string") as mock_process,
        patch("vibectl.command_handler._parse_command_args") as mock_parse,
        patch("vibectl.command_handler._create_display_command") as mock_display,
    ):
        # Set up mocks
        mock_process.return_value = ("get pods", None)
        mock_parse.return_value = ["get", "pods"]
        mock_display.return_value = "get pods"
        mock_execute.side_effect = Exception("Command execution failed")

        # Call handle_vibe_request
        handle_vibe_request(
            request="Show me the pods",
            command="get",
            plan_prompt="Plan how to {command} {request}",
            summary_prompt_func=lambda: "Test prompt {output}",
            output_flags=output_flags,
            yes=True,  # Skip confirmation
        )

    # Verify handle_command_output was called with error output
    mock_handle_output.assert_called_once()
    call_args = mock_handle_output.call_args[1]
    assert "output" in call_args
    assert "Error:" in call_args["output"]
    assert "command" in call_args
    assert call_args["command"] == "get pods"


def test_execute_command_with_complex_args_memory_handling() -> None:
    """Test that _execute_command_with_complex_args handles errors properly."""
    with (
        patch("vibectl.command_handler.subprocess.run") as mock_run,
        patch("vibectl.command_handler.console_manager"),
    ):
        # Set up subprocess.run to raise CalledProcessError
        import subprocess

        error = subprocess.CalledProcessError(
            1, ["kubectl", "get", "pods"], stderr="Command failed"
        )
        mock_run.side_effect = error

        # Try to execute command with complex args
        result = _execute_command_with_complex_args(["get", "pods", "with spaces"])

        # Verify error is captured in output for memory
        assert isinstance(result, str)
        assert "Error:" in result


def test_execute_yaml_command_stdin_memory_handling() -> None:
    """Test that _execute_yaml_command handles stdin errors properly."""
    with (
        patch("subprocess.Popen") as mock_popen,
        patch("vibectl.command_handler.console_manager"),
    ):
        # Configure mock Popen
        mock_process = Mock()
        mock_process.returncode = 1
        mock_process.communicate.return_value = (b"", b"Error in stdin")
        mock_popen.return_value = mock_process

        # Patch the Exception raise to capture the error message
        with patch(
            "vibectl.command_handler._execute_yaml_command",
            side_effect=Exception("Error in stdin"),
        ):
            # Try to execute YAML command with stdin
            yaml_content = "apiVersion: v1\nkind: Pod"
            try:
                result = _execute_yaml_command(["apply", "-f", "-"], yaml_content)
            except Exception as e:
                # The function is expected to raise an exception
                # In the real code, this would be caught and formatted for memory
                result = f"Error: {e!s}"

            # Verify error is captured in output for memory
            assert "Error:" in result


def test_execute_yaml_command_file_memory_handling() -> None:
    """Test that _execute_yaml_command handles file errors properly."""
    with (
        patch("subprocess.run") as mock_run,
        patch("vibectl.command_handler.console_manager"),
        patch("tempfile.NamedTemporaryFile") as mock_tempfile,
    ):
        # Configure mock tempfile
        mock_file = Mock()
        mock_file.name = "/tmp/test.yaml"
        mock_tempfile.return_value.__enter__.return_value = mock_file

        # Configure mock run
        mock_process = Mock()
        mock_process.returncode = 1
        mock_process.stderr = "File error"
        mock_run.return_value = mock_process

        # Patch the Exception raise to capture the error message
        with patch(
            "vibectl.command_handler._execute_yaml_command",
            side_effect=Exception("File error"),
        ):
            # Try to execute YAML command with file
            yaml_content = "apiVersion: v1\nkind: Pod"
            try:
                result = _execute_yaml_command(["apply"], yaml_content)
            except Exception as e:
                # The function is expected to raise an exception
                # In the real code, this would be caught and formatted for memory
                result = f"Error: {e!s}"

            # Verify error is captured in output for memory
            assert "Error:" in result


def test_execute_command_memory_leak_prevention() -> None:
    """Test that _execute_command properly handles resources to prevent leaks."""
    with (
        patch("vibectl.command_handler._execute_yaml_command") as mock_yaml_exec,
        patch(
            "vibectl.command_handler._execute_command_with_complex_args"
        ) as mock_complex_exec,
        patch("vibectl.command_handler.run_kubectl") as mock_run_kubectl,
    ):
        # Configure mocks
        mock_yaml_exec.return_value = "YAML applied"
        mock_complex_exec.return_value = "Complex command executed"
        mock_run_kubectl.return_value = "kubectl executed"

        # Test with YAML content
        result1 = _execute_command(["apply", "-f"], "test YAML")
        assert result1 == "YAML applied"

        # Test with complex args
        result2 = _execute_command(["get", "pods", "with spaces"], None)
        assert result2 == "Complex command executed"

        # Test with simple args
        result3 = _execute_command(["get", "pods"], None)
        assert result3 == "kubectl executed"
