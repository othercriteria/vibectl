"""Tests for port-forward command handling.

This module tests how the command handling logic processes LLM output
for port-forward commands, focusing on clean output that doesn't include
prefixes like 'kubectl' or 'vibe'.
"""

from collections.abc import Generator
from unittest.mock import Mock, patch

import pytest

from vibectl.command_handler import (
    OutputFlags,
    _process_command_string,
    handle_vibe_request,
)


@pytest.fixture
def mock_model_adapter() -> Generator[Mock, None, None]:
    """Mock the model adapter to return predictable responses."""
    with patch("vibectl.command_handler.get_model_adapter") as mock_adapter:
        mock_model = Mock()
        mock_adapter.return_value.get_model.return_value = mock_model
        # Clean response without prefixes
        mock_adapter.return_value.execute.return_value = "pod/nginx 8080:80"
        yield mock_adapter


@pytest.fixture
def mock_handle_port_forward() -> Generator[Mock, None, None]:
    """Mock handle_port_forward_with_live_display function."""
    with patch("vibectl.command_handler.handle_port_forward_with_live_display") as mock:
        yield mock


@pytest.fixture
def mock_run_kubectl() -> Generator[Mock, None, None]:
    """Mock run_kubectl function."""
    with patch("vibectl.command_handler.run_kubectl") as mock:
        mock.return_value = "Forwarding from 127.0.0.1:8080 -> 80"
        yield mock


@pytest.fixture
def mock_handle_output() -> Generator[Mock, None, None]:
    """Mock handle_command_output function."""
    with patch("vibectl.command_handler.handle_command_output") as mock:
        yield mock


@pytest.fixture
def mock_console() -> Generator[Mock, None, None]:
    """Mock console_manager to prevent output during tests."""
    with patch("vibectl.command_handler.console_manager") as mock:
        yield mock


def test_process_command_string_handles_clean_commands() -> None:
    """Test that _process_command_string processes clean commands without prefixes."""
    # Clean command without prefixes
    cmd_args, yaml_content = _process_command_string("pod/nginx 8080:80")
    assert cmd_args == "pod/nginx 8080:80"
    assert yaml_content is None

    # Command with additional flags
    cmd_args, yaml_content = _process_command_string(
        "pod/nginx 8080:80 --namespace default"
    )
    assert cmd_args == "pod/nginx 8080:80 --namespace default"
    assert yaml_content is None


def test_handle_vibe_request_with_clean_command(
    mock_model_adapter: Mock,
    mock_handle_port_forward: Mock,
    mock_run_kubectl: Mock,
    mock_handle_output: Mock,
    mock_console: Mock,
) -> None:
    """Test that handle_vibe_request works with clean commands without prefixes."""
    # Configure model adapter to return a clean command
    mock_model_adapter.return_value.execute.return_value = "pod/nginx 8080:80"

    # Create output flags
    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
    )

    # Call handle_vibe_request
    handle_vibe_request(
        request="port forward the nginx pod to my local port 8080",
        command="port-forward",
        plan_prompt="Plan how to {command} {request}",
        summary_prompt_func=lambda: "Summarize {output}",
        output_flags=output_flags,
        live_display=True,
    )

    # Verify handle_port_forward_with_live_display was called correctly
    mock_handle_port_forward.assert_called_once()
    args = mock_handle_port_forward.call_args[1]
    assert args["resource"] == "pod/nginx"
    assert args["args"] == ("8080:80",)


def test_handle_vibe_request_with_namespace_flag(
    mock_model_adapter: Mock,
    mock_handle_port_forward: Mock,
    mock_run_kubectl: Mock,
    mock_handle_output: Mock,
    mock_console: Mock,
) -> None:
    """Test that handle_vibe_request works with commands containing flags."""
    # Configure model adapter to return a command with flags
    mock_model_adapter.return_value.execute.return_value = (
        "pod/nginx 8080:80 --namespace default"
    )

    # Create output flags
    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
    )

    # Call handle_vibe_request
    handle_vibe_request(
        request=(
            "port forward the nginx pod to my local port 8080 in the default namespace"
        ),
        command="port-forward",
        plan_prompt="Plan how to {command} {request}",
        summary_prompt_func=lambda: "Test prompt {output}",
        output_flags=output_flags,
        autonomous_mode=False,
    )

    # Verify handle_port_forward_with_live_display was called correctly
    mock_handle_port_forward.assert_called_once()
    args = mock_handle_port_forward.call_args[1]
    assert args["resource"] == "pod/nginx"
    assert args["args"] == ("8080:80", "--namespace", "default")


def test_handle_vibe_request_with_multiple_port_mappings(
    mock_model_adapter: Mock,
    mock_handle_port_forward: Mock,
    mock_run_kubectl: Mock,
    mock_handle_output: Mock,
    mock_console: Mock,
) -> None:
    """Test that handle_vibe_request works with multiple port mappings."""
    # Configure model adapter to return a command with multiple port mappings
    mock_model_adapter.return_value.execute.return_value = "pod/nginx 8080:80 9090:9000"

    # Create output flags
    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
    )

    # Call handle_vibe_request
    handle_vibe_request(
        request=(
            "port forward the nginx pod with ports 80 and 9000 "
            "to my local ports 8080 and 9090"
        ),
        command="port-forward",
        plan_prompt="Plan how to {command} {request}",
        summary_prompt_func=lambda: "Test prompt {output}",
        output_flags=output_flags,
    )

    # Verify handle_port_forward_with_live_display was called correctly
    mock_handle_port_forward.assert_called_once()
    args = mock_handle_port_forward.call_args[1]
    assert args["resource"] == "pod/nginx"
    assert args["args"] == ("8080:80", "9090:9000")
