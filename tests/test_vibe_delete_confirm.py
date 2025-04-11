"""Tests focused on the delete confirmation behavior in vibe delete commands."""

from collections.abc import Generator
from unittest.mock import MagicMock, Mock, patch

import pytest

from vibectl.command_handler import OutputFlags, handle_vibe_request


@pytest.fixture
def mock_confirm() -> Generator[MagicMock, None, None]:
    """Mock click.confirm function."""
    with patch("click.confirm") as mock:
        yield mock


@pytest.fixture
def mock_console() -> Generator[MagicMock, None, None]:
    """Mock console manager to properly test output messages."""
    with (
        patch("vibectl.command_handler.console_manager") as mock_console,
        patch(
            "vibectl.cli.console_manager", mock_console
        ),  # Use same mock for both modules
    ):
        yield mock_console


@pytest.fixture
def mock_memory() -> Generator[MagicMock, None, None]:
    """Mock memory functions to avoid slow file operations."""
    with (
        patch("vibectl.command_handler.update_memory") as mock_update_memory,
        patch("vibectl.memory.update_memory") as mock_memory_update,
        patch("vibectl.memory.get_memory") as mock_get_memory,
    ):
        # Set default return values
        mock_get_memory.return_value = "Test memory context"

        yield mock_update_memory


def test_vibe_delete_with_confirmation(
    mock_llm: MagicMock,
    mock_run_kubectl: Mock,
    mock_console: Mock,
    mock_confirm: MagicMock,
    prevent_exit: MagicMock,
    standard_output_flags: OutputFlags,
    mock_memory: MagicMock,
) -> None:
    """Test delete command with confirmation dialog."""
    # Set the return value on the already mocked model adapter
    mock_llm.execute.return_value = "kubectl delete pod test-pod"

    # Set confirmation to True (accept)
    mock_confirm.return_value = True

    # Call function
    handle_vibe_request(
        request="delete the test pod",
        command="delete",  # The actual command, not "delete vibe"
        plan_prompt="Test plan prompt",
        summary_prompt_func=lambda: "Test summary prompt",
        output_flags=standard_output_flags,
        yes=False,  # Confirm before executing
    )

    # Verify confirmation was shown
    mock_confirm.assert_called_once()

    # Verify kubectl was called with delete command
    mock_run_kubectl.assert_called_once()

    # Verify sys.exit was not called
    prevent_exit.assert_not_called()


def test_vibe_delete_with_confirmation_cancelled(
    mock_llm: MagicMock,
    mock_run_kubectl: Mock,
    mock_console: Mock,
    mock_confirm: MagicMock,
    prevent_exit: MagicMock,
    standard_output_flags: OutputFlags,
    mock_memory: MagicMock,
) -> None:
    """Test delete command with confirmation dialog cancelled."""
    # Set the return value on the already mocked model adapter
    mock_llm.execute.return_value = "kubectl delete pod test-pod"

    # Set confirmation to False (cancel)
    mock_confirm.return_value = False

    # Call function
    handle_vibe_request(
        request="delete the test pod",
        command="delete",  # The actual command, not "delete vibe"
        plan_prompt="Test plan prompt",
        summary_prompt_func=lambda: "Test summary prompt",
        output_flags=standard_output_flags,
        yes=False,  # Confirm before executing
    )

    # Verify confirmation was shown
    mock_confirm.assert_called_once()

    # Verify cancelled message was shown
    mock_console.print_cancelled.assert_called_once()

    # Verify kubectl was NOT called
    mock_run_kubectl.assert_not_called()

    # Verify sys.exit was not called
    prevent_exit.assert_not_called()


def test_vibe_delete_yes_flag_bypasses_confirmation(
    mock_llm: MagicMock,
    mock_run_kubectl: Mock,
    mock_console: Mock,
    mock_confirm: MagicMock,
    prevent_exit: MagicMock,
    standard_output_flags: OutputFlags,
    mock_memory: MagicMock,
) -> None:
    """Test delete command with --yes flag that bypasses confirmation."""
    # Set the return value on the already mocked model adapter
    mock_llm.execute.return_value = "kubectl delete pod test-pod"

    # Call function with yes=True
    handle_vibe_request(
        request="delete the test pod",
        command="delete",  # The actual command, not "delete vibe"
        plan_prompt="Test plan prompt",
        summary_prompt_func=lambda: "Test summary prompt",
        output_flags=standard_output_flags,
        yes=True,  # Skip confirmation
    )

    # Verify confirmation was NOT shown
    mock_confirm.assert_not_called()

    # Verify kubectl was called
    mock_run_kubectl.assert_called_once()

    # Verify sys.exit was not called
    prevent_exit.assert_not_called()


def test_vibe_non_delete_commands_skip_confirmation(
    mock_llm: MagicMock,
    mock_run_kubectl: Mock,
    mock_console: Mock,
    mock_confirm: MagicMock,
    prevent_exit: MagicMock,
    standard_output_flags: OutputFlags,
    mock_memory: MagicMock,
) -> None:
    """Test non-delete commands don't require confirmation."""
    # Set the return value on the already mocked model adapter
    mock_llm.execute.return_value = "kubectl get pods"

    # Call function with a non-delete command
    handle_vibe_request(
        request="get all pods",
        command="get",  # The actual command, not "get vibe"
        plan_prompt="Test plan prompt",
        summary_prompt_func=lambda: "Test summary prompt",
        output_flags=standard_output_flags,
        yes=False,  # Even with yes=False, non-delete commands don't need confirmation
    )

    # Verify confirmation was NOT shown for get command
    mock_confirm.assert_not_called()

    # Verify kubectl was called
    mock_run_kubectl.assert_called_once()

    # Verify sys.exit was not called
    prevent_exit.assert_not_called()
