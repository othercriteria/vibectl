"""Tests for port-forward command handler.

This module tests the handle_port_forward_with_live_display function in
command_handler.py
"""

import asyncio
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest

from vibectl.command_handler import handle_port_forward_with_live_display
from vibectl.types import OutputFlags


class AsyncMockClass(MagicMock):
    """Mock class that supports async magic methods."""

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return super().__call__(*args, **kwargs)

    async def __aexit__(self, *args: Any, **kwargs: Any) -> Any:
        return super().__aexit__(*args, **kwargs)

    async def __aenter__(self, *args: Any, **kwargs: Any) -> Any:
        return super().__aenter__(*args, **kwargs)


@pytest.fixture
def standard_output_flags() -> OutputFlags:
    """Create a standard OutputFlags instance for testing."""
    return OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=True,
        model_name="claude-3.7-sonnet",
    )


@pytest.fixture
def mock_asyncio_components() -> Generator[dict, None, None]:
    """Mock asyncio components for testing port-forward handler."""
    # Create mock process
    mock_process = Mock()
    mock_process.stdout = Mock()
    mock_process.stdout.readline = AsyncMockClass(
        return_value=b"Forwarding from 127.0.0.1:8080 -> 8080"
    )
    mock_process.stderr = Mock()
    mock_process.stderr.read = AsyncMockClass(return_value=b"")
    mock_process.returncode = None
    mock_process.wait = AsyncMockClass()
    mock_process.terminate = Mock()

    # Create mock event loop
    mock_loop = Mock()
    mock_loop.run_until_complete = Mock()
    mock_loop.is_running = Mock(return_value=False)
    mock_loop.close = Mock()

    # Create mock progress components
    mock_progress = Mock()
    mock_task_id = Mock()
    mock_progress.add_task = Mock(return_value=mock_task_id)
    mock_progress.__enter__ = Mock(return_value=mock_progress)
    mock_progress.__exit__ = Mock(return_value=None)

    with (
        patch(
            "vibectl.command_handler.asyncio.create_subprocess_exec",
            new_callable=AsyncMockClass,
            return_value=mock_process,
        ),
        patch("vibectl.command_handler.asyncio.sleep", new_callable=AsyncMockClass),
        patch("vibectl.command_handler.asyncio.wait_for", new_callable=AsyncMockClass),
        patch("vibectl.command_handler.asyncio.create_task", Mock()),
        patch(
            "vibectl.command_handler.asyncio.get_event_loop",
            Mock(return_value=mock_loop),
        ),
        patch(
            "vibectl.command_handler.asyncio.new_event_loop",
            Mock(return_value=mock_loop),
        ),
        patch("vibectl.command_handler.asyncio.set_event_loop", Mock()),
        patch("vibectl.command_handler.asyncio.CancelledError", Exception),
        patch("vibectl.command_handler.asyncio.TimeoutError", Exception),
        patch("vibectl.command_handler.Progress", return_value=mock_progress),
    ):
        yield {
            "process": mock_process,
            "loop": mock_loop,
            "progress": mock_progress,
            "task_id": mock_task_id,
        }


@patch("vibectl.command_handler.time")
@patch("vibectl.command_handler.Config")
@patch("vibectl.command_handler.update_memory")
@patch("vibectl.command_handler.console_manager")
def test_handle_port_forward_basic(
    mock_console: Mock,
    mock_update_memory: Mock,
    mock_config: Mock,
    mock_time: Mock,
    mock_asyncio_components: dict,
    standard_output_flags: OutputFlags,
) -> None:
    """Test basic functionality of handle_port_forward_with_live_display."""
    # Configure mocks
    mock_config.return_value = Mock()
    mock_time.time.return_value = 100

    # Call the function
    handle_port_forward_with_live_display(
        resource="pod/nginx",
        args=("8080:8080",),
        output_flags=standard_output_flags,
    )

    # Verify interactions
    mock_console.print_note.assert_called()
    mock_update_memory.assert_called_once()

    # Verify process was correctly started with kubernetes command
    mock_loop = mock_asyncio_components["loop"]

    mock_loop.run_until_complete.assert_called_once()

    # Verify progress display was created
    mock_progress = mock_asyncio_components["progress"]
    mock_progress.add_task.assert_called_once()

    # Verify memory update if vibe output is enabled
    if standard_output_flags.show_vibe:
        mock_update_memory.assert_called_once()


@patch("vibectl.command_handler.time")
@patch("vibectl.command_handler.Config")
@patch("vibectl.command_handler.update_memory")
@patch("vibectl.command_handler.console_manager")
def test_handle_port_forward_with_error(
    mock_console: Mock,
    mock_update_memory: Mock,
    mock_config: Mock,
    mock_time: Mock,
    mock_asyncio_components: dict,
    standard_output_flags: OutputFlags,
) -> None:
    """Test handle_port_forward_with_live_display when error occurs."""
    # Configure mocks for error scenario
    mock_config.return_value = Mock()
    mock_time.time.return_value = 100

    # Set up process to return error
    mock_process = mock_asyncio_components["process"]
    mock_process.returncode = 1
    mock_process.stderr.read = AsyncMockClass(
        return_value=b"Error: unable to forward port"
    )

    # Call the function
    handle_port_forward_with_live_display(
        resource="pod/nonexistent",
        args=("8080:8080",),
        output_flags=standard_output_flags,
    )

    # Verify error handling - note that print_note will be called for
    # session end message
    mock_console.print_note.assert_called()
    mock_update_memory.assert_called_once()

    # Verify process handling
    mock_loop = mock_asyncio_components["loop"]
    mock_loop.run_until_complete.assert_called_once()


@patch("vibectl.command_handler.time")
@patch("vibectl.command_handler.Config")
@patch("vibectl.command_handler.update_memory")
@patch("vibectl.command_handler.console_manager")
def test_handle_port_forward_with_keyboard_interrupt(
    mock_console: Mock,
    mock_update_memory: Mock,
    mock_config: Mock,
    mock_time: Mock,
    mock_asyncio_components: dict,
    standard_output_flags: OutputFlags,
) -> None:
    """Test handle_port_forward_with_live_display with keyboard interrupt."""
    # Configure mocks
    mock_config.return_value = Mock()
    mock_time.time.side_effect = [100, 110]  # Start time, end time

    # Set up loop to raise KeyboardInterrupt
    mock_loop = mock_asyncio_components["loop"]
    mock_loop.run_until_complete.side_effect = KeyboardInterrupt()

    # Call the function
    handle_port_forward_with_live_display(
        resource="pod/nginx",
        args=("8080:8080",),
        output_flags=standard_output_flags,
    )

    # Verify keyboard interrupt handling
    # Get the actual message from the mock calls
    cancel_calls = [
        call_args
        for call_args in mock_console.print_note.call_args_list
        if call_args[0]
        and isinstance(call_args[0][0], str)
        and "cancelled by user" in call_args[0][0]
    ]
    assert (
        len(cancel_calls) > 0
    ), "Expected 'cancelled by user' message not found in console output"

    # Verify cleanup still happens
    assert mock_update_memory.call_count == 1


@patch("vibectl.command_handler.time")
@patch("vibectl.command_handler.Config")
@patch("vibectl.command_handler.update_memory")
@patch("vibectl.command_handler.console_manager")
def test_handle_port_forward_with_cancelation(
    mock_console: Mock,
    mock_update_memory: Mock,
    mock_config: Mock,
    mock_time: Mock,
    mock_asyncio_components: dict,
    standard_output_flags: OutputFlags,
) -> None:
    """Test handle_port_forward_with_live_display with asyncio cancellation."""
    # Configure mocks
    mock_config.return_value = Mock()
    mock_time.time.side_effect = [100, 110]  # Start time, end time

    # Set up loop to raise CancelledError
    mock_loop = mock_asyncio_components["loop"]
    mock_loop.run_until_complete.side_effect = asyncio.CancelledError()

    # Call the function
    handle_port_forward_with_live_display(
        resource="pod/nginx",
        args=("8080:8080",),
        output_flags=standard_output_flags,
    )

    # Verify cancellation handling
    # Get the actual message from the mock calls
    cancel_calls = [
        call_args
        for call_args in mock_console.print_note.call_args_list
        if call_args[0]
        and isinstance(call_args[0][0], str)
        and "Port-forward cancelled" in call_args[0][0]
    ]
    assert (
        len(cancel_calls) > 0
    ), "Expected 'Port-forward cancelled' message not found in console output"

    # Verify cleanup still happens
    assert mock_update_memory.call_count == 1


@patch("vibectl.command_handler.time")
@patch("vibectl.command_handler.Config")
@patch("vibectl.command_handler.update_memory")
@patch("vibectl.command_handler.console_manager")
def test_handle_port_forward_complex_port_mapping(
    mock_console: Mock,
    mock_update_memory: Mock,
    mock_config: Mock,
    mock_time: Mock,
    mock_asyncio_components: dict,
    standard_output_flags: OutputFlags,
) -> None:
    """Test handle_port_forward_with_live_display with complex port mapping."""
    # Configure mocks
    mock_config.return_value = Mock()
    mock_time.time.side_effect = [100, 110]  # Start time, end time

    # Call the function with more complex port mapping
    handle_port_forward_with_live_display(
        resource="service/web",
        args=("5000:80", "--address=0.0.0.0"),
        output_flags=standard_output_flags,
    )

    # Verify correct port extraction and display
    mock_progress = mock_asyncio_components["progress"]
    task_description = mock_progress.add_task.call_args[1]["description"]
    assert "5000" in task_description
    assert "80" in task_description

    # Verify elapsed time message is in print_note calls
    assert mock_console.print_note.call_count >= 1
    assert any(
        "Port-forward session ended after" in str(call)
        for call in mock_console.print_note.call_args_list
    )

    # Verify memory update with correct port info
    mock_update_memory.assert_called_once()
    memory_args = mock_update_memory.call_args[0]
    assert "service/web" in memory_args[0]
    assert "5000:80" in memory_args[0]
    assert "--address=0.0.0.0" in memory_args[0]
