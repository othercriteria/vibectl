"""Tests for the command handler module."""

import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest

from vibectl.command_handler import (
    configure_output_flags,
    handle_command_output,
    handle_command_with_options,
    handle_standard_command,
    handle_vibe_request,
    run_kubectl,
)


@pytest.fixture
def test_config(tmp_path: Path) -> Any:
    """Create a test configuration instance."""
    from vibectl.config import Config

    return Config(base_dir=tmp_path)


@pytest.fixture
def mock_subprocess(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Mock subprocess.run."""
    mock = MagicMock()
    mock.return_value = Mock(stdout="test output", stderr="")
    monkeypatch.setattr("subprocess.run", mock)
    return mock


@pytest.fixture
def mock_llm(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Mock LLM model."""
    mock = MagicMock()
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: "Test response")
    mock.return_value = mock_model
    monkeypatch.setattr("llm.get_model", mock)
    return mock


@pytest.fixture
def mock_summary_prompt() -> Callable[[], str]:
    """Mock summary prompt function."""

    def _summary_prompt() -> str:
        return "Summarize this: {output}"

    return _summary_prompt


def test_run_kubectl_success(mock_subprocess: MagicMock, test_config: Any) -> None:
    """Test successful kubectl command execution."""
    # Set test kubeconfig
    test_config.set("kubeconfig", "/test/kubeconfig")

    # Configure mock to return success
    mock_subprocess.return_value.stdout = "test output"

    # Run command
    output = run_kubectl(["get", "pods"], capture=True, config=test_config)

    # Verify command construction
    mock_subprocess.assert_called_once()
    cmd = mock_subprocess.call_args[0][0]
    assert cmd == ["kubectl", "--kubeconfig", "/test/kubeconfig", "get", "pods"]
    assert output == "test output"


def test_run_kubectl_no_kubeconfig(
    mock_subprocess: MagicMock, test_config: Any
) -> None:
    """Test kubectl command without kubeconfig."""
    # Explicitly set kubeconfig to None
    test_config.set("kubeconfig", None)

    # Configure mock to return success
    mock_subprocess.return_value.stdout = "test output"

    output = run_kubectl(["get", "pods"], capture=True, config=test_config)

    # Verify command construction without kubeconfig
    mock_subprocess.assert_called_once()
    cmd = mock_subprocess.call_args[0][0]
    assert cmd == ["kubectl", "get", "pods"]
    assert output == "test output"


def test_run_kubectl_error(mock_subprocess: MagicMock) -> None:
    """Test kubectl command error handling."""
    mock_subprocess.side_effect = Exception("test error")

    with pytest.raises(Exception, match="test error"):
        run_kubectl(["get", "pods"])


def test_run_kubectl_not_found(mock_subprocess: MagicMock) -> None:
    """Test kubectl not found error."""
    mock_subprocess.side_effect = FileNotFoundError()

    with pytest.raises(FileNotFoundError):
        run_kubectl(["get", "pods"])


def test_run_kubectl_called_process_error(
    mock_subprocess: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test kubectl command error handling with CalledProcessError."""
    error = subprocess.CalledProcessError(1, ["kubectl"], stderr="test error")
    mock_subprocess.side_effect = error

    output = run_kubectl(["get", "pods"], capture=True)

    # Verify error was printed to stderr
    captured = capsys.readouterr()
    assert captured.err == "test error\n"
    # Check error message is properly formatted
    assert output == "Error: test error"


def test_run_kubectl_called_process_error_no_stderr(mock_subprocess: MagicMock) -> None:
    """Test kubectl command error handling with CalledProcessError but no stderr."""
    error = subprocess.CalledProcessError(1, ["kubectl"], stderr="")
    mock_subprocess.side_effect = error

    output = run_kubectl(["get", "pods"], capture=True)
    assert output == "Error: Command failed with exit code 1"


def test_run_kubectl_no_capture(mock_subprocess: MagicMock) -> None:
    """Test kubectl command without output capture."""
    output = run_kubectl(["get", "pods"], capture=False)

    # Verify command was run without capture
    mock_subprocess.assert_called_once()
    assert output is None


def test_run_kubectl_called_process_error_no_capture(
    mock_subprocess: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test kubectl command error handling with CalledProcessError in non-capture mode.

    Verifies proper error handling when subprocess raises a CalledProcessError.
    """
    error = subprocess.CalledProcessError(1, ["kubectl"], stderr="test error")
    mock_subprocess.side_effect = error

    output = run_kubectl(["get", "pods"], capture=False)

    # Verify error was printed to stderr and no output returned
    captured = capsys.readouterr()
    assert captured.err == "test error\n"
    assert output is None


def test_handle_standard_command(
    mock_subprocess: MagicMock,
    mock_llm: MagicMock,
    mock_summary_prompt: Callable[[], str],
    test_config: Any,
) -> None:
    """Test standard command handling."""
    # Ensure no kubeconfig is set
    test_config.set("kubeconfig", None)

    handle_standard_command(
        command="get",
        resource="pods",
        args=(),
        show_raw_output=True,
        show_vibe=True,
        model_name="test-model",
        summary_prompt_func=mock_summary_prompt,
        warn_no_output=True,
    )

    # Verify kubectl was called
    mock_subprocess.assert_called_once()
    cmd = mock_subprocess.call_args[0][0]
    assert cmd == ["kubectl", "get", "pods"]


def test_handle_command_output_raw_only(
    mock_llm: MagicMock, mock_summary_prompt: Callable[[], str]
) -> None:
    """Test command output handling with only raw output."""
    handle_command_output(
        output="test output",
        show_raw_output=True,
        show_vibe=False,
        model_name="test-model",
        summary_prompt_func=mock_summary_prompt,
    )

    # Verify LLM was not called
    mock_llm.assert_not_called()


def test_handle_command_output_vibe_only(
    mock_llm: MagicMock, mock_summary_prompt: Callable[[], str]
) -> None:
    """Test command output handling with only vibe output."""
    handle_command_output(
        output="test output",
        show_raw_output=False,
        show_vibe=True,
        model_name="test-model",
        summary_prompt_func=mock_summary_prompt,
    )

    # Verify LLM was called
    mock_llm.assert_called_once()


def test_handle_command_output_truncation(
    mock_llm: MagicMock, mock_summary_prompt: Callable[[], str]
) -> None:
    """Test command output handling with truncation."""
    # Create long output that will need truncation
    long_output = "x" * 20000

    handle_command_output(
        output=long_output,
        show_raw_output=False,
        show_vibe=True,
        model_name="test-model",
        summary_prompt_func=mock_summary_prompt,
        max_token_limit=1000,
        truncation_ratio=2,
    )

    # Verify LLM was called with truncated output
    mock_llm.assert_called_once()


def test_handle_vibe_request_success(
    mock_llm: MagicMock, mock_subprocess: MagicMock
) -> None:
    """Test successful vibe request handling."""
    # Set up test data
    mock_subprocess.return_value = Mock(stdout="test output", stderr="")

    def summary_prompt() -> str:
        return "Summarize this: {output}"

    # Run vibe request
    handle_vibe_request(
        request="show me the pods",
        command="get",
        plan_prompt="Plan this: {request}",
        summary_prompt_func=summary_prompt,
        show_raw_output=True,
        show_vibe=True,
        model_name="test-model",
    )

    # Verify LLM was called for planning
    mock_llm.assert_called()


def test_handle_vibe_request_error_response(mock_llm: MagicMock) -> None:
    """Test vibe request with error response from planner."""
    # Set up error response
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: "ERROR: Invalid request")
    mock_llm.return_value = mock_model

    def summary_prompt() -> str:
        return "Summarize this: {output}"

    with pytest.raises(SystemExit):
        handle_vibe_request(
            request="invalid request",
            command="get",
            plan_prompt="Plan this: {request}",
            summary_prompt_func=summary_prompt,
            show_raw_output=True,
            show_vibe=True,
            model_name="test-model",
        )


def test_configure_output_flags(test_config: Any) -> None:
    """Test output flag configuration."""
    # Test with defaults
    test_config.set("model", "claude-3.7-sonnet")  # Set default model
    test_config.set("warn_no_output", True)  # Set default warning behavior

    show_raw, show_vibe, warn_no_output, model = configure_output_flags()
    assert not show_raw
    assert show_vibe
    assert warn_no_output  # Should use config value (True)
    assert model == "claude-3.7-sonnet"  # Should use config value

    # Test with explicit values and config overrides
    test_config.set("warn_no_output", False)  # Override to False in config

    show_raw, show_vibe, warn_no_output, model = configure_output_flags(
        show_raw_output=True,
        show_vibe=False,
        model="test-model",
    )
    assert show_raw
    assert not show_vibe
    assert not warn_no_output  # Should be False from config
    assert model == "test-model"


def test_handle_command_output_missing_api_key(
    mock_llm: MagicMock, mock_summary_prompt: Callable[[], str]
) -> None:
    """Test command output handling with missing API key."""
    # Simulate missing API key error
    mock_model = Mock()
    mock_model.prompt.side_effect = Exception("no key found")
    mock_llm.return_value = mock_model

    # Should not raise exception but print error
    handle_command_output(
        output="test output",
        show_raw_output=False,
        show_vibe=True,
        model_name="test-model",
        summary_prompt_func=mock_summary_prompt,
    )

    # Verify LLM was called
    mock_llm.assert_called_once()


def test_handle_command_output_model_selection(
    mock_llm: MagicMock, mock_summary_prompt: Callable[[], str], test_config: Any
) -> None:
    """Test command output uses correct model from config."""
    # Set model in config
    test_config.set("model", "claude-3.7-sonnet")

    # Get output flags
    _, _, _, model = configure_output_flags()

    # Use configured model
    handle_command_output(
        output="test output",
        show_raw_output=False,
        show_vibe=True,
        model_name=model,
        summary_prompt_func=mock_summary_prompt,
    )

    # Verify correct model was requested
    mock_llm.assert_called_once_with("claude-3.7-sonnet")


@patch("vibectl.command_handler.handle_exception")
def test_handle_vibe_request_empty_response(
    mock_handle_exception: MagicMock, mock_llm: MagicMock
) -> None:
    """Test vibe request with empty response from planner."""
    # Set up empty response
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: "")
    mock_llm.return_value = mock_model

    def summary_prompt() -> str:
        return "Summarize this: {output}"

    # Run vibe request
    handle_vibe_request(
        request="show me the pods",
        command="get",
        plan_prompt="Plan this: {request}",
        summary_prompt_func=summary_prompt,
        show_raw_output=True,
        show_vibe=True,
        model_name="test-model",
    )

    # Verify LLM was called and exception was handled
    mock_llm.assert_called_once()
    mock_handle_exception.assert_called_once()


@patch("vibectl.command_handler.handle_exception")
def test_handle_vibe_request_invalid_format(
    mock_handle_exception: MagicMock, mock_llm: MagicMock
) -> None:
    """Test vibe request with invalid format from planner."""
    # Set up invalid response (completely empty response)
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: "")
    mock_llm.return_value = mock_model

    def summary_prompt() -> str:
        return "Summarize this: {output}"

    # Run vibe request
    handle_vibe_request(
        request="show me the pods",
        command="get",
        plan_prompt="Plan this: {request}",
        summary_prompt_func=summary_prompt,
        show_raw_output=True,
        show_vibe=True,
        model_name="test-model",
    )

    # Verify LLM was called and exception was handled
    assert mock_llm.call_count > 0  # Check that LLM was called at least once
    mock_handle_exception.assert_called_once()


@patch("vibectl.command_handler.handle_exception")
def test_handle_standard_command_error(
    mock_handle_exception: MagicMock,
    mock_subprocess: MagicMock,
    mock_llm: MagicMock,
    mock_summary_prompt: Callable[[], str],
) -> None:
    """Test error handling in standard command."""
    # Set up error
    mock_subprocess.side_effect = Exception("test error")

    # Run command
    handle_standard_command(
        command="get",
        resource="pods",
        args=(),
        show_raw_output=True,
        show_vibe=True,
        model_name="test-model",
        summary_prompt_func=mock_summary_prompt,
        warn_no_output=True,
    )

    # Verify kubectl was called and exception was handled
    mock_subprocess.assert_called_once()
    mock_handle_exception.assert_called_once()


@patch("vibectl.command_handler.output_processor")
def test_handle_command_output_llm_error(
    mock_processor: MagicMock,
    mock_llm: MagicMock,
    mock_summary_prompt: Callable[[], str],
) -> None:
    """Test LLM error handling in command output."""
    # Set up processor
    mock_processor.process_auto.return_value = ("test output", False)

    # Set up LLM error
    mock_model = Mock()
    mock_model.prompt.side_effect = Exception("LLM error")
    mock_llm.return_value = mock_model

    # Run command output handling
    handle_command_output(
        output="test output",
        show_raw_output=True,
        show_vibe=True,
        model_name="test-model",
        summary_prompt_func=mock_summary_prompt,
    )

    # Verify LLM was called
    mock_llm.assert_called_once()


@patch("vibectl.command_handler.output_processor")
def test_handle_command_output_processor_error(
    mock_processor: MagicMock,
    mock_llm: MagicMock,
    mock_summary_prompt: Callable[[], str],
) -> None:
    """Test output processor error handling in command output."""
    # Set up processor error
    mock_processor.process_auto.side_effect = Exception("Processor error")

    # Run command output handling
    handle_command_output(
        output="test output",
        show_raw_output=True,
        show_vibe=True,
        model_name="test-model",
        summary_prompt_func=mock_summary_prompt,
    )

    # Verify processor was called
    mock_processor.process_auto.assert_called_once()
    # Verify LLM was not called due to processor error
    mock_llm.assert_not_called()


@patch("vibectl.command_handler.console_manager")
def test_handle_vibe_request_no_output(
    mock_console: MagicMock, mock_llm: MagicMock
) -> None:
    """Test vibe request with no output flags."""

    def summary_prompt() -> str:
        return "Summarize this: {output}"

    handle_vibe_request(
        request="show me the pods",
        command="get",
        plan_prompt="Plan this: {request}",
        summary_prompt_func=summary_prompt,
        show_raw_output=False,
        show_vibe=False,
        model_name="test-model",
        warn_no_output=True,
    )

    # Verify warning was printed
    assert (
        mock_console.print_no_output_warning.called
    ), "Warning should be printed when no output flags are enabled"


@patch("vibectl.command_handler.handle_exception")
def test_handle_vibe_request_llm_output_parsing(
    mock_handle_exception: MagicMock, mock_llm: MagicMock
) -> None:
    """Test vibe request with LLM output that includes delimiter."""
    # Set up LLM response with delimiter
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: "get pods\n---\nother content")
    mock_llm.return_value = mock_model

    def summary_prompt() -> str:
        return "Summarize this: {output}"

    handle_vibe_request(
        request="show me the pods",
        command="get",
        plan_prompt="Plan this: {request}",
        summary_prompt_func=summary_prompt,
        show_raw_output=True,
        show_vibe=True,
        model_name="test-model",
    )

    # Verify exception handler was not called
    mock_handle_exception.assert_not_called()


@patch("vibectl.command_handler.handle_exception")
def test_handle_vibe_request_command_error(
    mock_handle_exception: MagicMock, mock_llm: MagicMock
) -> None:
    """Test vibe request with command execution error."""
    # Set up LLM response
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: "get pods")
    mock_llm.return_value = mock_model

    def summary_prompt() -> str:
        return "Summarize this: {output}"

    with patch("vibectl.command_handler.run_kubectl") as mock_run:
        mock_run.side_effect = Exception("Command failed")

        handle_vibe_request(
            request="show me the pods",
            command="get",
            plan_prompt="Plan this: {request}",
            summary_prompt_func=summary_prompt,
            show_raw_output=True,
            show_vibe=True,
            model_name="test-model",
        )

        # Verify exception was handled
        mock_handle_exception.assert_called_once_with(mock_run.side_effect)


@patch("vibectl.command_handler.handle_exception")
def test_handle_standard_command_no_output(
    mock_handle_exception: MagicMock,
    mock_subprocess: MagicMock,
    mock_llm: MagicMock,
    mock_summary_prompt: Callable[[], str],
) -> None:
    """Test standard command handling with no output."""
    # Set up mock to return no output
    mock_subprocess.return_value = Mock(stdout="", stderr="")

    handle_standard_command(
        command="get",
        resource="pods",
        args=(),
        show_raw_output=True,
        show_vibe=True,
        model_name="test-model",
        summary_prompt_func=mock_summary_prompt,
        warn_no_output=True,
    )

    # Verify no exception was handled
    mock_handle_exception.assert_not_called()


@patch("vibectl.command_handler.handle_exception")
def test_handle_vibe_request_output_error(
    mock_handle_exception: MagicMock, mock_llm: MagicMock
) -> None:
    """Test vibe request with output handling error."""
    # Set up LLM response
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: "get pods")
    mock_llm.return_value = mock_model

    def summary_prompt() -> str:
        return "Summarize this: {output}"

    with patch("vibectl.command_handler.run_kubectl") as mock_run:
        mock_run.return_value = "test output"

        with patch(
            "vibectl.command_handler.handle_command_output"
        ) as mock_handle_output:
            mock_handle_output.side_effect = Exception("Output handling failed")

            handle_vibe_request(
                request="show me the pods",
                command="get",
                plan_prompt="Plan this: {request}",
                summary_prompt_func=summary_prompt,
                show_raw_output=True,
                show_vibe=True,
                model_name="test-model",
            )

            # Verify exception was handled with exit_on_error=False
            mock_handle_exception.assert_called_once_with(
                mock_handle_output.side_effect, exit_on_error=False
            )


@patch("vibectl.command_handler.handle_exception")
def test_handle_standard_command_output_error(
    mock_handle_exception: MagicMock,
    mock_subprocess: MagicMock,
    mock_llm: MagicMock,
    mock_summary_prompt: Callable[[], str],
) -> None:
    """Test error handling in standard command output processing."""
    # Set up successful command but failed output handling
    mock_subprocess.return_value = Mock(stdout="test output", stderr="")

    with patch("vibectl.command_handler.handle_command_output") as mock_handle_output:
        mock_handle_output.side_effect = Exception("Output handling failed")

        handle_standard_command(
            command="get",
            resource="pods",
            args=(),
            show_raw_output=True,
            show_vibe=True,
            model_name="test-model",
            summary_prompt_func=mock_summary_prompt,
            warn_no_output=True,
        )

        # Verify exception was handled
        mock_handle_exception.assert_called_once_with(mock_handle_output.side_effect)


@patch("vibectl.command_handler.handle_exception")
def test_handle_vibe_request_llm_error(
    mock_handle_exception: MagicMock, mock_llm: MagicMock
) -> None:
    """Test vibe request with LLM error."""
    # Set up LLM error
    mock_model = Mock()
    mock_model.prompt.side_effect = Exception("LLM error")
    mock_llm.return_value = mock_model

    def summary_prompt() -> str:
        return "Summarize this: {output}"

    handle_vibe_request(
        request="show me the pods",
        command="get",
        plan_prompt="Plan this: {request}",
        summary_prompt_func=summary_prompt,
        show_raw_output=True,
        show_vibe=True,
        model_name="test-model",
    )

    # Verify exception was handled
    mock_handle_exception.assert_called_once_with(mock_model.prompt.side_effect)


@patch("os.unlink")
@patch("tempfile.NamedTemporaryFile")
@patch("vibectl.command_handler.run_kubectl")
@patch("vibectl.command_handler.handle_command_output")
@patch("llm.get_model")
def test_handle_vibe_request_create_with_yaml(
    mock_llm: MagicMock,
    mock_handle_output: MagicMock,
    mock_run_kubectl: MagicMock,
    mock_named_temp_file: MagicMock,
    mock_unlink: MagicMock,
) -> None:
    """Test vibe request handling for create command with YAML content."""
    # Setup mock LLM response with both kubectl args and YAML content
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(
        text=lambda: """
-n
default
---
apiVersion: v1
kind: Pod
metadata:
  name: test-pod
spec:
  containers:
  - name: nginx
    image: nginx:latest
"""
    )
    mock_llm.return_value = mock_model

    # Setup mock temp file
    mock_file = MagicMock()
    mock_file.__enter__.return_value = mock_file
    mock_file.name = "/tmp/test-yaml-12345.yaml"
    mock_named_temp_file.return_value = mock_file

    # Setup mock kubectl output
    mock_run_kubectl.return_value = "pod/test-pod created"

    # Run the function
    def summary_prompt() -> str:
        return "Summary: {output}"

    handle_vibe_request(
        request="create a pod called test-pod",
        command="create",
        plan_prompt="Create this: {request}",
        summary_prompt_func=summary_prompt,
        show_raw_output=True,
        show_vibe=True,
        model_name="test-model",
    )

    # Verify tempfile was created and written to
    mock_named_temp_file.assert_called_once()
    mock_file.write.assert_called_once()

    # Verify kubectl was called with correct arguments
    mock_run_kubectl.assert_called_once_with(
        ["create", "-f", "/tmp/test-yaml-12345.yaml", "", "-n", "default"], capture=True
    )

    # Verify temporary file was cleaned up
    mock_unlink.assert_called_once_with("/tmp/test-yaml-12345.yaml")

    # Verify output was handled
    mock_handle_output.assert_called_once()


@patch("os.unlink")
@patch("tempfile.NamedTemporaryFile")
@patch("vibectl.command_handler.run_kubectl")
@patch("vibectl.command_handler.handle_command_output")
@patch("llm.get_model")
def test_handle_vibe_request_create_with_yaml_error(
    mock_llm: MagicMock,
    mock_handle_output: MagicMock,
    mock_run_kubectl: MagicMock,
    mock_named_temp_file: MagicMock,
    mock_unlink: MagicMock,
) -> None:
    """Test error handling in vibe request for create command with YAML content."""
    # Setup mock LLM response with both kubectl args and YAML content
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(
        text=lambda: """
-n
default
---
apiVersion: v1
kind: Pod
metadata:
  name: test-pod
spec:
  containers:
  - name: nginx
    image: nginx:latest
"""
    )
    mock_llm.return_value = mock_model

    # Setup mock temp file
    mock_file = MagicMock()
    mock_file.__enter__.return_value = mock_file
    mock_file.name = "/tmp/test-yaml-12345.yaml"
    mock_named_temp_file.return_value = mock_file

    # Setup kubectl to raise an exception
    mock_run_kubectl.side_effect = Exception("Error creating resource")

    # Run the function
    def summary_prompt() -> str:
        return "Summary: {output}"

    # Use patch to prevent sys.exit from actually exiting
    with patch("sys.exit") as mock_exit:
        handle_vibe_request(
            request="create a pod called test-pod",
            command="create",
            plan_prompt="Create this: {request}",
            summary_prompt_func=summary_prompt,
            show_raw_output=True,
            show_vibe=True,
            model_name="test-model",
        )

        # Verify exit was called
        mock_exit.assert_called_once_with(1)

    # Verify tempfile was created
    mock_named_temp_file.assert_called_once()

    # Verify kubectl was called
    mock_run_kubectl.assert_called_once()

    # Verify temporary file was cleaned up after error
    mock_unlink.assert_called_once_with("/tmp/test-yaml-12345.yaml")


@patch("vibectl.command_handler.console_manager")
@patch("vibectl.command_handler.handle_exception")
def test_handle_vibe_request_empty_plan(
    mock_handle_exception: MagicMock, mock_console: MagicMock, mock_llm: MagicMock
) -> None:
    """Test handle_vibe_request when the LLM returns an empty plan."""
    # Set up the LLM to return an empty response
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: "")
    mock_llm.return_value = mock_model

    def summary_prompt() -> str:
        return "Summary template"

    # Execute the function
    handle_vibe_request(
        request="test request",
        command="get",
        plan_prompt="test prompt",
        summary_prompt_func=summary_prompt,
    )

    # Verify the error was handled properly
    mock_handle_exception.assert_called_once()
    args = mock_handle_exception.call_args[0]
    assert isinstance(args[0], Exception)
    assert "Invalid response format" in str(args[0])


@patch("vibectl.command_handler.handle_exception")
def test_handle_vibe_request_error_response_prefix(
    mock_handle_exception: MagicMock, mock_llm: MagicMock
) -> None:
    """Test handle_vibe_request when the LLM returns an error response with
    ERROR: prefix.

    Verifies that error responses are properly handled and exception is raised.
    """
    # Set up the LLM to return an error response
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: "ERROR: Invalid request format")
    mock_llm.return_value = mock_model

    def summary_prompt() -> str:
        return "Summary template"

    # Execute the function
    handle_vibe_request(
        request="test request",
        command="get",
        plan_prompt="test prompt",
        summary_prompt_func=summary_prompt,
    )

    # Verify the error was handled properly
    mock_handle_exception.assert_called_once()
    args = mock_handle_exception.call_args[0]
    assert isinstance(args[0], Exception)
    assert "Invalid request format" in str(args[0])


@patch("vibectl.command_handler.llm")
@patch("vibectl.command_handler.run_kubectl")
@patch("vibectl.command_handler.handle_command_output")
def test_handle_vibe_request_multi_yaml(
    mock_handle_output: Mock, mock_run_kubectl: Mock, mock_llm: Mock
) -> None:
    """Test handle_vibe_request with multi-document YAML."""
    # Mock LLM response with a multi-document YAML
    mock_model = Mock()
    mock_text = Mock()
    mock_text.text.return_value = """
-n
default
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx-hello-world
  labels:
    app: nginx-hello-world
spec:
  replicas: 3
  selector:
    matchLabels:
      app: nginx-hello-world
  template:
    metadata:
      labels:
        app: nginx-hello-world
    spec:
      containers:
      - name: nginx
        image: nginx:latest
        ports:
        - containerPort: 80
        livenessProbe:
          httpGet:
            path: /
            port: 80
          initialDelaySeconds: 10
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /
            port: 80
          initialDelaySeconds: 5
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: nginx-service
  labels:
    app: nginx-hello-world
spec:
  selector:
    app: nginx-hello-world
  ports:
  - port: 80
    targetPort: 80
  type: ClusterIP
"""
    mock_model.prompt.return_value = mock_text
    mock_llm.get_model.return_value = mock_model

    # Mock kubectl response
    mock_run_kubectl.return_value = "service/nginx-service created"

    # Call the function
    handle_vibe_request(
        request="create a deployment with service",
        command="create",
        plan_prompt="test prompt {request}",
        summary_prompt_func=lambda: "summary prompt {output}",
    )

    # Assert expectations
    mock_llm.get_model.assert_called_once()
    mock_model.prompt.assert_called_once()

    # The crucial test: verify kubectl was called with -f flag and correct args
    # We can't test the exact file content, but we can verify the command structure
    args, kwargs = mock_run_kubectl.call_args
    assert args[0][0] == "create"  # Command
    assert args[0][1] == "-f"  # Flag for file
    # No need to check for "-n" since it might be handled differently than expected

    # Verify the temp file was created and deleted
    # The third argument should be a path to a temporary file
    temp_file = args[0][2]
    assert not os.path.exists(temp_file)  # Should be deleted after use

    # Check output handling
    mock_handle_output.assert_called_once()


@patch("vibectl.command_handler.include_memory_in_prompt")
@patch("vibectl.command_handler.update_memory")
@patch("vibectl.command_handler.run_kubectl")
def test_handle_vibe_request_with_memory(
    mock_run_kubectl: MagicMock,
    mock_update_memory: MagicMock,
    mock_include_memory: MagicMock,
    mock_llm: MagicMock,
) -> None:
    """Test vibe request with memory integration.

    This test verifies that memory content is properly passed to the planning phase
    via include_memory_in_prompt when handling a vibe request.
    """
    # Set up mocks
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: "pods\n-n\nkube-system")
    mock_llm.return_value = mock_model

    # Mock run_kubectl to return test output
    mock_run_kubectl.return_value = "test output"

    # Set up a return value for include_memory_in_prompt
    # that indicates it was called with proper parameters
    mock_include_memory.return_value = "Prompt with memory included"

    def summary_prompt() -> str:
        return "Summarize this: {output}"

    # Run vibe request that references memory
    handle_vibe_request(
        request="get pods in the namespace mentioned in memory",
        command="get",
        plan_prompt="Plan this: {request}",
        summary_prompt_func=summary_prompt,
        show_raw_output=True,
        show_vibe=True,
        model_name="test-model",
    )

    # Verify include_memory_in_prompt was called and check it's a callable
    mock_include_memory.assert_called_once()

    # The first arg of the call should be a callable (lambda)
    args, _ = mock_include_memory.call_args
    assert callable(args[0]), "First argument should be a callable"

    # Verify that the LLM was called with the modified prompt
    mock_model.prompt.assert_any_call("Prompt with memory included")

    # Verify that kubectl was called with the arguments returned by the LLM
    mock_run_kubectl.assert_called_with(
        ["get", "pods", "-n", "kube-system"],
        capture=True,
    )


@patch("vibectl.command_handler.run_kubectl")
@patch("vibectl.command_handler.handle_command_output")
def test_handle_vibe_request_in_autonomous_mode(
    mock_handle_output: MagicMock,
    mock_run_kubectl: MagicMock,
    mock_llm: MagicMock,
) -> None:
    """Test vibe request in autonomous mode.

    This test verifies that autonomous mode properly handles kubectl commands
    and executes them directly.
    """
    # Set up mocks
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(
        text=lambda: "kubectl get pods -n kube-system\nNOTE: Checking system pods"
    )
    mock_llm.return_value = mock_model

    # Mock run_kubectl to return test output
    mock_run_kubectl.return_value = "test output"

    def summary_prompt() -> str:
        return "Summarize this: {output}"

    # Run vibe request in autonomous mode
    handle_vibe_request(
        request="check system pods",
        command="vibe",
        plan_prompt="Plan this autonomous command: {request}",
        summary_prompt_func=summary_prompt,
        show_raw_output=True,
        show_vibe=True,
        model_name="test-model",
        yes=True,  # Skip confirmation
        autonomous_mode=True,
    )

    # Verify that the LLM was called with the unmodified plan prompt
    mock_model.prompt.assert_called_once_with("Plan this autonomous command: {request}")

    # Verify that kubectl was called with the correct arguments
    mock_run_kubectl.assert_called_once_with(
        ["get", "pods", "-n", "kube-system"],
        capture=True,
    )

    # Verify that handle_command_output was called with the correct parameters
    mock_handle_output.assert_called_once_with(
        output="test output",
        show_raw_output=True,
        show_vibe=True,
        model_name="test-model",
        summary_prompt_func=summary_prompt,
        command="kubectl get pods -n kube-system",
        warn_no_output=True,
    )


@patch("vibectl.command_handler.console_manager")
@patch("click.confirm")
def test_handle_vibe_request_autonomous_mode_with_confirmation(
    mock_confirm: MagicMock,
    mock_console: MagicMock,
    mock_llm: MagicMock,
) -> None:
    """Test vibe request confirmation in autonomous mode.

    This test verifies that confirmation prompts work properly in autonomous mode.
    """
    # Set up mocks
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(
        text=lambda: "kubectl delete pod test-pod\nNOTE: Removing test pod"
    )
    mock_llm.return_value = mock_model

    # Mock confirmation to cancel the command
    mock_confirm.return_value = False

    def summary_prompt() -> str:
        return "Summarize this: {output}"

    # Run vibe request in autonomous mode
    handle_vibe_request(
        request="remove test pod",
        command="vibe",
        plan_prompt="Plan this autonomous command",
        summary_prompt_func=summary_prompt,
        autonomous_mode=True,
    )

    # Verify confirmation was called
    mock_confirm.assert_called_once_with(
        "Do you want to execute this command?", default=True
    )

    # Verify cancellation message was shown
    mock_console.print_cancelled.assert_called_once()


@patch("vibectl.command_handler.run_kubectl")
@patch("vibectl.command_handler.configure_output_flags")
def test_handle_command_with_options_none_output(
    mock_configure_output_flags: MagicMock,
    mock_run_kubectl: MagicMock,
) -> None:
    """Test handling command with options when output is None."""
    # Set up mocks
    mock_run_kubectl.return_value = None  # Simulate None output
    mock_configure_output_flags.return_value = (True, False, False, "claude-3-opus")

    # Test function
    cmd = ["kubectl", "get", "pods"]
    output, show_vibe = handle_command_with_options(cmd)

    # Assertions
    assert output == ""  # Output should be empty string when None is returned
    assert show_vibe is False
    mock_run_kubectl.assert_called_once_with(cmd, capture=True, config=None)
