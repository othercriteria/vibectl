"""Tests for standard command handling functionality."""

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest

from vibectl.command_handler import (
    OutputFlags,
    handle_standard_command,
)

# The test_config and mock_subprocess fixtures are now provided by conftest.py


@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler.OutputProcessor")
@patch("vibectl.command_handler.update_memory")
def test_handle_standard_command_basic(
    mock_update_memory: MagicMock,
    mock_output_processor: MagicMock,
    mock_get_adapter: MagicMock,
    mock_subprocess: MagicMock,
    mock_llm: MagicMock,
    mock_console: Mock,
    prevent_exit: MagicMock,
    test_config: Any,
    standard_output_flags: OutputFlags,
) -> None:
    """Test basic command handling.

    This test ensures that all LLM calls are properly mocked to prevent
    actual API calls which would cause slow tests.
    """
    # Set test kubeconfig
    test_config.set("kubeconfig", "/test/kubeconfig")

    # Configure mock to return success
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = "test output"
    mock_subprocess.return_value = mock_result

    # Setup output processor
    processor_instance = Mock()
    processor_instance.process_auto.return_value = ("processed output", False)
    mock_output_processor.return_value = processor_instance

    # Ensure the get_model_adapter returns our mock_llm
    mock_get_adapter.return_value = mock_llm

    # Set up model adapter response for summary
    mock_model = Mock()
    mock_llm.get_model.return_value = mock_model
    mock_llm.execute.return_value = "Summarized output"

    # Run command
    handle_standard_command(
        command="get",
        resource="pods",
        args=(),
        output_flags=standard_output_flags,
        summary_prompt_func=lambda: "Test prompt: {output}",
    )

    # Verify command construction
    mock_subprocess.assert_called_once()
    cmd_args = mock_subprocess.call_args[0][0]

    # Don't check exact order, just make sure all parts are there
    assert "kubectl" in cmd_args
    assert "get" in cmd_args
    assert "pods" in cmd_args
    assert any(
        arg.startswith("--kubeconfig") or arg == "--kubeconfig" for arg in cmd_args
    )

    # Verify kwargs
    kwargs = mock_subprocess.call_args[1]
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True

    # Verify model adapter was called
    mock_llm.execute.assert_called_once()

    # Verify sys.exit was not called
    prevent_exit.assert_not_called()


@pytest.fixture
def mock_summary_prompt() -> Callable[[], str]:
    """Mock summary prompt function."""
    return lambda: "Test Prompt: {output}"


@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.memory.include_memory_in_prompt")
@patch("vibectl.command_handler.update_memory")
@patch("vibectl.command_handler.OutputProcessor")
def test_handle_standard_command(
    mock_output_processor: MagicMock,
    mock_update_memory: MagicMock,
    mock_include_memory: MagicMock,
    mock_get_adapter: MagicMock,
    mock_subprocess: MagicMock,
    mock_llm: MagicMock,
    mock_console: Mock,
    prevent_exit: MagicMock,
    mock_summary_prompt: Callable[[], str],
    test_config: Any,
    standard_output_flags: OutputFlags,
) -> None:
    """Test standard command handling.

    This test ensures that all LLM calls are properly mocked to prevent
    actual API calls which would cause slow tests.
    """
    # Setup output processor
    processor_instance = Mock()
    processor_instance.process_auto.return_value = ("processed output", False)
    mock_output_processor.return_value = processor_instance

    # Ensure the get_model_adapter returns our mock_llm
    mock_get_adapter.return_value = mock_llm

    # Setup model
    mock_model = Mock()
    mock_llm.get_model.return_value = mock_model

    # Ensure memory functions are properly mocked
    mock_include_memory.side_effect = lambda x: x()

    # Ensure no kubeconfig is set
    test_config.set("kubeconfig", None)

    # Set up model adapter response for summary
    mock_llm.execute.return_value = "Summarized output"

    # Run command
    handle_standard_command(
        command="get",
        resource="pods",
        args=(),
        output_flags=standard_output_flags,
        summary_prompt_func=mock_summary_prompt,
    )

    # Verify kubectl was called
    mock_subprocess.assert_called_once()
    cmd = mock_subprocess.call_args[0][0]
    assert cmd == ["kubectl", "get", "pods"]

    # Verify model adapter was called
    mock_llm.execute.assert_called_once()

    # Verify sys.exit was not called
    prevent_exit.assert_not_called()


@patch("vibectl.command_handler.handle_exception")
def test_handle_standard_command_error(
    mock_handle_exception: MagicMock,
    mock_subprocess: MagicMock,
    mock_llm: MagicMock,
    mock_console: Mock,
    prevent_exit: MagicMock,
    mock_summary_prompt: Callable[[], str],
    standard_output_flags: OutputFlags,
) -> None:
    """Test error handling in standard command."""
    # Set up error
    mock_subprocess.side_effect = Exception("test error")

    # Run command
    handle_standard_command(
        command="get",
        resource="pods",
        args=(),
        output_flags=standard_output_flags,
        summary_prompt_func=mock_summary_prompt,
    )

    # Verify kubectl was called and exception was handled
    mock_subprocess.assert_called_once()
    mock_handle_exception.assert_called_once()

    # Verify model adapter was NOT called since command failed
    mock_llm.execute.assert_not_called()

    # Verify sys.exit was not called
    prevent_exit.assert_not_called()


@patch("vibectl.command_handler.handle_exception")
def test_handle_standard_command_no_output(
    mock_handle_exception: MagicMock,
    mock_subprocess: MagicMock,
    mock_llm: MagicMock,
    mock_console: Mock,
    prevent_exit: MagicMock,
    mock_summary_prompt: Callable[[], str],
    standard_output_flags: OutputFlags,
) -> None:
    """Test standard command handling with no output."""
    # Set up mock to return no output but success return code
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""
    mock_subprocess.return_value = mock_result

    # Run command
    handle_standard_command(
        command="get",
        resource="pods",
        args=(),
        output_flags=standard_output_flags,
        summary_prompt_func=mock_summary_prompt,
    )

    # Verify no exception was handled - the command should exit early with no output
    mock_handle_exception.assert_not_called()

    # Verify model adapter was not called since there was no output
    mock_llm.execute.assert_not_called()

    # Verify sys.exit was not called
    prevent_exit.assert_not_called()


@patch("vibectl.command_handler.handle_exception")
def test_handle_standard_command_output_error(
    mock_handle_exception: MagicMock,
    mock_subprocess: MagicMock,
    mock_llm: MagicMock,
    mock_console: Mock,
    prevent_exit: MagicMock,
    mock_summary_prompt: Callable[[], str],
    standard_output_flags: OutputFlags,
) -> None:
    """Test error handling in standard command output processing."""
    # Set up successful command
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = "test output"
    mock_result.stderr = ""
    mock_subprocess.return_value = mock_result

    # Setup the handle_command_output to fail
    mock_handle_command_output_error = Exception("Output handling failed")

    with patch("vibectl.command_handler.handle_command_output") as mock_handle_output:
        mock_handle_output.side_effect = mock_handle_command_output_error

        # Run command
        handle_standard_command(
            command="get",
            resource="pods",
            args=(),
            output_flags=standard_output_flags,
            summary_prompt_func=mock_summary_prompt,
        )

        # Verify exception was handled
        mock_handle_exception.assert_called_once()
        args, kwargs = mock_handle_exception.call_args
        assert isinstance(args[0], Exception)
        assert str(args[0]) == "Output handling failed"
