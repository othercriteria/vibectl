"""Tests for standard command handling functionality."""

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest

from vibectl.command_handler import (
    handle_standard_command,
)
from vibectl.types import OutputFlags, Success, Truncation

# The test_config and mock_subprocess fixtures are now provided by conftest.py


@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler.output_processor")
@patch("vibectl.command_handler.update_memory")
def test_handle_standard_command_basic(
    mock_update_memory: MagicMock,
    mock_processor: MagicMock,
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
    # Patch Config._save_config to prevent file I/O
    with (
        patch("vibectl.config.Config._save_config"),
        patch("vibectl.command_handler.Config") as mock_config_class,
    ):
        # Set up the config mock to return our test_config
        mock_config_class.return_value = test_config

        # Set test kubeconfig
        test_config.set("kubeconfig", "/test/kubeconfig")

        # Configure mock to return success
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "test output"
        mock_subprocess.return_value = mock_result

        # Setup output processor mock to return Truncation
        mock_processor.process_auto.return_value = Truncation(
            original="test output", truncated="processed output"
        )

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

    # Verify kwargs
    kwargs = mock_subprocess.call_args[1]
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True

    # Verify model adapter was called with processed output
    mock_llm.execute.assert_called_once()
    # Check the prompt passed to the LLM
    prompt_arg = mock_llm.execute.call_args[0][1]
    assert "processed output" in prompt_arg

    # Verify sys.exit was not called
    prevent_exit.assert_not_called()


@pytest.fixture
def mock_summary_prompt() -> Callable[[], str]:
    """Mock summary prompt function."""
    return lambda: "Test Prompt: {output}"


@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.memory.include_memory_in_prompt")
@patch("vibectl.command_handler.update_memory")
@patch("vibectl.command_handler.output_processor")
def test_handle_standard_command(
    mock_processor: MagicMock,
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
    # Setup output processor mock to return Truncation
    mock_processor.process_auto.return_value = Truncation(
        original="test output", truncated="processed output"
    )

    # Ensure the get_model_adapter returns our mock_llm
    mock_get_adapter.return_value = mock_llm

    # Setup model
    mock_model = Mock()
    mock_llm.get_model.return_value = mock_model

    # Ensure memory functions are properly mocked
    mock_include_memory.side_effect = lambda x: x()

    # Ensure no kubeconfig is set
    test_config.set("kubeconfig", None)

    # Configure mock subprocess to return success
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = "test output"
    mock_subprocess.return_value = mock_result

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

    # Verify model adapter was called with processed output
    mock_llm.execute.assert_called_once()
    # Check the prompt passed to the LLM
    prompt_arg = mock_llm.execute.call_args[0][1]
    assert "processed output" in prompt_arg

    # Verify sys.exit was not called
    prevent_exit.assert_not_called()


@patch("vibectl.command_handler.run_kubectl")
@patch("vibectl.k8s_utils.subprocess.run")
@patch("vibectl.command_handler.handle_command_output")
@patch("vibectl.command_handler.console_manager")
def test_handle_standard_command_logs(
    mock_console: Mock,
    mock_handle_output: Mock,
    mock_subprocess_run: Mock,
    mock_run_kubectl: Mock,
) -> None:
    """Test handle_standard_command specifically for the logs command."""
    # Setup mocks: run_kubectl returns Success
    log_output = "Log line 1\nLog line 2"
    mock_run_kubectl.return_value = Success(data=log_output)
    mock_handle_output.return_value = Success(message=log_output)

    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=False,
        warn_no_output=False,
        model_name="test-model",
        show_kubectl=True,
    )

    # Test handling the logs command
    # Define summary function properly
    def summary_func() -> str:
        return "Summarize logs: {output}"

    result = handle_standard_command(
        "logs", "pod/my-pod", ("-c", "my-container"), output_flags, summary_func
    )

    # Verify run_kubectl was called with correct args
    mock_run_kubectl.assert_called_once_with(
        ["logs", "pod/my-pod", "-c", "my-container"], capture=True
    )

    # Verify handle_command_output was called correctly
    mock_handle_output.assert_called_once()
    # call_args = (positional_args_tuple, keyword_args_dict)
    pos_args, kw_args = mock_handle_output.call_args

    # Verify positional arguments
    assert isinstance(pos_args[0], str)
    assert pos_args[0] == log_output
    assert pos_args[1] == output_flags  # Check 2nd positional arg
    assert pos_args[2] == summary_func  # Check 3rd positional arg

    # Verify keyword arguments
    assert kw_args["command"] == "logs"

    # Verify the result is what handle_command_output returned
    assert result == mock_handle_output.return_value

    # Verify subprocess.run was not called directly
    mock_subprocess_run.assert_not_called()
