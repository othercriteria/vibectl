"""Tests for port-forward command handling.

This module tests how the command handling logic processes LLM output
for port-forward commands, focusing on clean output that doesn't include
prefixes like 'kubectl' or 'vibe'.
"""

import json
from collections.abc import Generator, Callable
from typing import Any
from unittest.mock import MagicMock, Mock, patch, AsyncMock
import subprocess
import asyncio

import pytest

from vibectl.live_display import _execute_port_forward_with_live_display
from vibectl.command_handler import (
    OutputFlags,
    handle_vibe_request,
)
from vibectl.types import ActionType, Success, Error

# Filter the specific UserWarning from rich.live
pytestmark = pytest.mark.filterwarnings("ignore:install \\\"ipywidgets\\\" for Jupyter support:UserWarning:rich.live")


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
    """Mock handle_command_output function (placeholder, might not be needed)."""
    # This might be removed if tests don't need to mock handle_command_output directly
    with patch("vibectl.command_handler.handle_command_output") as mock:
        yield mock


@pytest.fixture
def mock_console_manager() -> Generator[Mock, None, None]:
    """Mock console_manager for port forward tests."""
    with patch("vibectl.live_display.console_manager") as mock:
        # Configure necessary attributes/methods if needed by the test
        mock.status = MagicMock()
        mock.status.return_value.__enter__ = MagicMock()
        mock.status.return_value.__exit__ = MagicMock()
        mock.console = MagicMock() # Add console attribute if needed
        mock.error_console = MagicMock() # Add error_console if needed
        yield mock


@pytest.fixture
def mock_process() -> Generator[MagicMock, None, None]:
    """Fixture for mocking subprocess.Popen process object."""
    process_mock = MagicMock(spec=subprocess.Popen)
    process_mock.poll.return_value = None # Simulate running
    process_mock.pid = 12345
    # Configure communicate to return default empty byte strings
    process_mock.communicate.return_value = (b"", b"")
    process_mock.returncode = 0
    # Mock context manager methods
    process_mock.__enter__.return_value = process_mock
    process_mock.__exit__.return_value = None
    yield process_mock


@pytest.fixture
def mock_popen_factory(
    mock_process: MagicMock,
) -> Callable[..., MagicMock]:
    """Factory fixture to create a mock subprocess.Popen."""

    def _factory(**kwargs: Any) -> MagicMock:
        popen_mock = MagicMock(spec=subprocess.Popen)
        popen_mock.return_value = mock_process
        # Update mock_process attributes if provided
        for key, value in kwargs.items():
            if hasattr(mock_process, key):
                setattr(mock_process, key, value)
            else:
                # Handle potential nested attributes like returncode
                parts = key.split(".")
                obj = mock_process
                try:
                    for part in parts[:-1]:
                        obj = getattr(obj, part)
                    setattr(obj, parts[-1], value)
                except AttributeError:
                    print(f"Warning: Could not set attribute {key} on mock_process")
        return popen_mock

    return _factory


def test_handle_vibe_request_port_forward_clean(
    mock_model_adapter: MagicMock,
    mock_run_kubectl: Mock,
    mock_handle_output: Mock,
    mock_console_manager: Mock,
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
    mock_console_manager: Mock,
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
    mock_console_manager: Mock,
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


@pytest.mark.asyncio
async def test_execute_port_forward_success(
    mock_config: MagicMock,
    mock_console_manager: MagicMock,
    mock_popen_factory: Callable[..., MagicMock],
    mock_process: MagicMock, # Get the shared process mock
) -> None:
    """Test successful execution of port forward with live display."""
    # Setup
    resource = "pod/my-pod"
    args = ("8080:80",)
    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
        show_kubectl=True,
        warn_no_proxy=False,
    )
    port_mapping = "8080:80"
    local_port = "8080"
    remote_port = "80"
    display_text = f"Forwarding {resource} port {remote_port} to {local_port}"
    summary_prompt_func = lambda: "Summary"

    # Configure the mock process returned by asyncio.create_subprocess_exec
    mock_process.returncode = 0
    # Mock stdout/stderr streams
    mock_process.stdout = AsyncMock()
    # Simulate the "Forwarding from..." line then EOF
    mock_process.stdout.readline = AsyncMock(side_effect=[b"Forwarding from 127.0.0.1:8080 -> 80\\n", b""])
    mock_process.stderr = AsyncMock()
    mock_process.stderr.read = AsyncMock(return_value=b"")
    # Mock the wait method to return immediately
    mock_process.wait = AsyncMock(return_value=0)
    # Mock terminate if needed
    mock_process.terminate = Mock()


    # Patch asyncio.create_subprocess_exec to return our configured mock_process
    with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_create_subprocess, \
         patch("vibectl.live_display.time.sleep"), \
         patch("vibectl.live_display.TcpProxy") as mock_tcp_proxy, \
         patch("vibectl.live_display.update_memory") as mock_update_memory, \
         patch("vibectl.live_display.get_model_adapter") as mock_get_adapter_live: # Mock adapter in live_display

        # Execute (Call the real function again)
        result = _execute_port_forward_with_live_display(
            resource=resource,
            args=args,
            output_flags=output_flags,
            port_mapping=port_mapping,
            local_port=local_port,
            remote_port=remote_port,
            display_text=display_text,
            summary_prompt_func=summary_prompt_func,
        )

        # Assertions
        mock_create_subprocess.assert_called_once()
        # Check the command passed to create_subprocess_exec
        expected_cmd = [
            "kubectl", "port-forward", resource, *args # Add other expected args like --address if needed
        ]
        # Note: create_subprocess_exec takes command parts as *args, not a list
        call_args = mock_create_subprocess.call_args.args
        assert call_args[:len(expected_cmd)] == tuple(expected_cmd)

        # Assert the function returns a Success object
        assert isinstance(result, Success)
        # Optionally check parts of the success message if needed
        # assert "completed successfully" in result.message


def test_execute_port_forward_kubectl_error(
    mock_config: MagicMock,
    mock_console_manager: MagicMock,
    mock_popen_factory: Callable[..., MagicMock],
    mock_process: MagicMock,
) -> None:
    """Test handling of kubectl errors during port forward startup."""
    # Setup
    resource = "pod/my-pod-does-not-exist"
    args = ("8080:80",)
    output_flags = OutputFlags(
        show_raw=False, show_vibe=True, warn_no_output=False,
        model_name="test-model", show_kubectl=True, warn_no_proxy=False
    )
    port_mapping = "8080:80"
    local_port = "8080"
    remote_port = "80"
    display_text = f"Forwarding {resource} port {remote_port} to {local_port}"
    summary_prompt_func = lambda: "Summary"

    # Configure the mock process for kubectl error
    kubectl_error_message = b"error: pod not found"
    mock_process.returncode = 1 # Simulate process ended with error
    # Mock stdout/stderr streams
    mock_process.stdout = AsyncMock()
    mock_process.stdout.readline = AsyncMock(return_value=b"") # No stdout expected on error start
    mock_process.stderr = AsyncMock()
    mock_process.stderr.read = AsyncMock(return_value=kubectl_error_message) # Return error message
    # Mock the wait method to return immediately
    mock_process.wait = AsyncMock(return_value=1) # Return non-zero code
    # Mock terminate if needed
    mock_process.terminate = Mock()


    # Patch asyncio.create_subprocess_exec to return our configured mock_process
    with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_create_subprocess, \
         patch("vibectl.live_display.time.sleep"), \
         patch("vibectl.live_display.TcpProxy") as mock_tcp_proxy, \
         patch("vibectl.live_display.update_memory") as mock_update_memory, \
         patch("vibectl.live_display.get_model_adapter") as mock_get_adapter_live: # Mock adapter in live_display

        # Execute (call real function)
        result = _execute_port_forward_with_live_display(
            resource=resource,
            args=args,
            output_flags=output_flags,
            port_mapping=port_mapping,
            local_port=local_port,
            remote_port=remote_port,
            display_text=display_text,
            summary_prompt_func=summary_prompt_func,
        )

        # Assertions
        mock_create_subprocess.assert_called_once()
        # Check the command passed to create_subprocess_exec
        expected_cmd = [
            "kubectl", "port-forward", resource, *args # Add other expected args if needed
        ]
        call_args = mock_create_subprocess.call_args.args
        assert call_args[:len(expected_cmd)] == tuple(expected_cmd)

        # Check that error was printed to console
        mock_console_manager.print_error.assert_any_call(
            f"Port-forward error: {kubectl_error_message.decode()}"
        )
        assert isinstance(result, Error)
        assert kubectl_error_message.decode() in result.error
