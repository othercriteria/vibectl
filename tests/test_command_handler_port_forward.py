"""Tests for port-forward command handling.

This module tests how the command handling logic processes LLM output
for port-forward commands, focusing on clean output that doesn't include
prefixes like 'kubectl' or 'vibe'.
"""

import json
from collections.abc import Generator
from unittest.mock import Mock, patch, MagicMock

import pytest

from vibectl.command_handler import (
    OutputFlags,
    handle_vibe_request,
)
from vibectl.types import ActionType, Success


@pytest.fixture
def mock_model_adapter() -> Generator[MagicMock, None, None]:
    """Mock the model adapter to return predictable responses."""
    with patch("vibectl.command_handler.get_model_adapter") as mock_get_adapter:
        mock_adapter_instance = MagicMock()
        mock_model_instance = Mock()
        mock_adapter_instance.get_model.return_value = mock_model_instance
        # Default JSON response can be set here or overridden in tests
        mock_adapter_instance.execute.return_value = json.dumps({
            "action_type": ActionType.COMMAND.value,
            "commands": ["default-arg"],
            "explanation": "Default explanation."
        })
        mock_get_adapter.return_value = mock_adapter_instance
        yield mock_adapter_instance


@pytest.fixture
def mock_run_kubectl() -> Generator[Mock, None, None]:
    """Mock run_kubectl function (still potentially used by _execute_command)."""
    with patch("vibectl.command_handler.run_kubectl") as mock:
        mock.return_value = Success(data="Forwarding from 127.0.0.1:8080 -> 80")
        yield mock


@pytest.fixture
def mock_handle_output() -> Generator[Mock, None, None]:
    """Mock handle_command_output function."""
    with patch("vibectl.command_handler.handle_command_output") as mock:
        # Add a default return value to prevent the real function from running
        # and potentially calling the LLM for summarization.
        mock.return_value = Success(message="Mocked handle_command_output result")
        yield mock


@pytest.fixture
def mock_console() -> Generator[Mock, None, None]:
    """Mock console_manager to prevent output during tests."""
    with patch("vibectl.command_handler.console_manager") as mock:
        yield mock


def test_handle_vibe_request_port_forward_clean(
    mock_model_adapter: MagicMock,
    mock_run_kubectl: Mock,
    mock_handle_output: Mock,
    mock_console: Mock,
) -> None:
    """Test handle_vibe_request with a clean port-forward JSON command."""
    # Configure model adapter
    expected_verb = "port-forward"
    expected_args = ["pod/nginx", "8080:80"]
    expected_response = {
        "action_type": ActionType.COMMAND.value,
        "commands": expected_args,
        "explanation": "Port forwarding nginx.",
    }
    mock_model_adapter.execute.return_value = json.dumps(expected_response)

    # Patch _execute_command which should be called by handle_vibe_request
    with patch("vibectl.command_handler._execute_command") as mock_execute_command:
        mock_execute_command.return_value = Success(data="Forwarding...Output")

        # Create output flags
        # Patch handle_port_forward to ensure it's NOT called when live_display=False
        with patch("vibectl.command_handler.handle_port_forward_with_live_display") as mock_live_handler:
            mock_live_handler.side_effect = AssertionError("Live handler called unexpectedly!")

            # Call handle_vibe_request
            handle_vibe_request(
                request="port forward the nginx pod",
                command="port-forward",
                plan_prompt="Plan how to {command} {request}",
                summary_prompt_func=lambda: "Summarize {output}",
                output_flags=OutputFlags(
                    show_raw=True,
                    show_vibe=True,
                    warn_no_output=False,
                    model_name="test-model",
                    show_kubectl=True,
                ),
                live_display=False, # Explicitly disable live display for this test
            )

    # Assert _execute_command was called with the verb and args from JSON
    mock_execute_command.assert_called_once_with(expected_verb, expected_args, None)

    # Assert handle_command_output was called with the result of _execute_command
    mock_handle_output.assert_called_once()
    call_args, call_kwargs = mock_handle_output.call_args
    # Verify the input to the mock, not the output (which is now mocked)
    assert isinstance(call_args[0], Success) # Check it received a Success object
    assert call_args[0].data == "Forwarding...Output" # Check the data passed to it
    assert call_kwargs.get("command") == expected_verb


def test_handle_vibe_request_port_forward_with_flags(
    mock_model_adapter: MagicMock,
    mock_run_kubectl: Mock,
    mock_handle_output: Mock,
    mock_console: Mock,
) -> None:
    """Test handle_vibe_request with port-forward JSON containing flags."""
    # Configure model adapter to return a command with flags as JSON
    expected_verb = "port-forward"
    expected_args = ["pod/nginx", "8080:80", "--namespace", "default"]
    expected_response = {
        "action_type": ActionType.COMMAND.value,
        "commands": expected_args,
        "explanation": "Port forwarding nginx in default namespace.",
    }
    mock_model_adapter.execute.return_value = json.dumps(expected_response)

    # Patch _execute_command
    with patch("vibectl.command_handler._execute_command") as mock_execute_command:
        mock_execute_command.return_value = Success(data="Forwarding...Output with Flags")

        # Create output flags
        # Patch handle_port_forward to ensure it's NOT called when live_display=False
        with patch("vibectl.command_handler.handle_port_forward_with_live_display") as mock_live_handler:
            mock_live_handler.side_effect = AssertionError("Live handler called unexpectedly!")

            # Call handle_vibe_request
            handle_vibe_request(
                request=(
                    "port forward the nginx pod to my local port 8080"
                    " in the default namespace"
                ),
                command="port-forward",
                plan_prompt="Plan how to {command} {request}",
                summary_prompt_func=lambda: "Test prompt {output}",
                output_flags=OutputFlags(
                    show_raw=True,
                    show_vibe=True,
                    warn_no_output=False,
                    model_name="test-model",
                    show_kubectl=True,
                ),
                autonomous_mode=False,
                live_display=False, # Explicitly disable live display for this test
            )

        # Verify _execute_command was called correctly
        mock_execute_command.assert_called_once_with(expected_verb, expected_args, None)

        # Verify handle_command_output was called correctly
        mock_handle_output.assert_called_once()
        call_args, call_kwargs = mock_handle_output.call_args
        # Verify the input to the mock
        assert isinstance(call_args[0], Success)
        assert call_args[0].data == "Forwarding...Output with Flags"
        assert call_kwargs.get("command") == expected_verb


def test_handle_vibe_request_port_forward_multiple_ports(
    mock_model_adapter: MagicMock,
    mock_run_kubectl: Mock,
    mock_handle_output: Mock,
    mock_console: Mock,
) -> None:
    """Test handle_vibe_request with port-forward JSON containing multiple ports."""
    # Configure model adapter to return a command with multiple port mappings as JSON
    expected_verb = "port-forward"
    expected_args = ["pod/nginx", "8080:80", "9090:9000"]
    expected_response = {
        "action_type": ActionType.COMMAND.value,
        "commands": expected_args,
        "explanation": "Port forwarding nginx with multiple ports.",
    }
    mock_model_adapter.execute.return_value = json.dumps(expected_response)

    # Patch _execute_command
    with patch("vibectl.command_handler._execute_command") as mock_execute_command:
        mock_execute_command.return_value = Success(data="Forwarding...Multiple Ports")

        # Create output flags
        # Patch handle_port_forward to ensure it's NOT called when live_display=False
        with patch("vibectl.command_handler.handle_port_forward_with_live_display") as mock_live_handler:
            mock_live_handler.side_effect = AssertionError("Live handler called unexpectedly!")

            # Call handle_vibe_request
            handle_vibe_request(
                request=(
                    "port forward the nginx pod with ports 80 and 9000 "
                    "to my local ports 8080 and 9090"
                ),
                command="port-forward",
                plan_prompt="Plan how to {command} {request}",
                summary_prompt_func=lambda: "Test prompt {output}",
                output_flags=OutputFlags(
                    show_raw=True,
                    show_vibe=True,
                    warn_no_output=False,
                    model_name="test-model",
                    show_kubectl=True,
                ),
                live_display=False, # Explicitly disable live display for this test
            )

        # Verify _execute_command was called correctly
        mock_execute_command.assert_called_once_with(expected_verb, expected_args, None)

        # Verify handle_command_output was called correctly
        mock_handle_output.assert_called_once()
        call_args, call_kwargs = mock_handle_output.call_args
        # Verify the input to the mock
        assert isinstance(call_args[0], Success)
        assert call_args[0].data == "Forwarding...Multiple Ports"
        assert call_kwargs.get("command") == expected_verb
