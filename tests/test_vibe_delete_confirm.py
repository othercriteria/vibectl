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
def mock_memory() -> Generator[tuple[MagicMock, MagicMock], None, None]:
    """Mock memory functions to avoid actual LLM API calls.

    Returns two mocks:
    1. mock_update_memory: The patch for vibectl.command_handler.update_memory
    2. mock_memory_update: The patch for vibectl.memory.update_memory

    This prevents actual API calls to LLMs during tests, which would:
    - Add cost for each test run
    - Make tests flaky due to API dependencies
    - Significantly slow down test execution

    This simulates the actual call chain where command_handler.py imports and calls
    the function implemented in memory.py. Tests can verify calls at either level.
    """
    with (
        patch("vibectl.command_handler.update_memory") as mock_update_memory,
        patch("vibectl.memory.update_memory") as mock_memory_update,
        patch("vibectl.memory.get_memory") as mock_get_memory,
    ):
        # Set default return values
        mock_get_memory.return_value = "Test memory context"

        # Set up delegation from command_handler's import to the actual implementation
        # This mimics how command_handler.update_memory calls memory.update_memory
        mock_update_memory.side_effect = mock_memory_update

        yield (mock_update_memory, mock_memory_update)


def test_vibe_delete_with_confirmation(
    mock_llm: MagicMock,
    mock_run_kubectl: MagicMock,
    mock_console: MagicMock,
    mock_confirm: MagicMock,
    prevent_exit: MagicMock,
    standard_output_flags: OutputFlags,
    mock_memory: tuple[MagicMock, MagicMock],
) -> None:
    """Test deletion command with confirmation and memory updates."""
    # Set up the mock to return a command that includes delete
    # First call is for planning, second is for summarizing the output
    mock_llm.execute.side_effect = ["pod my-pod", "Successfully deleted pod my-pod"]

    # Set up kubectl to return a success message
    mock_run_kubectl.return_value = 'pod "my-pod" deleted'

    # Set up confirmation to return True
    mock_confirm.return_value = True

    # Call function
    handle_vibe_request(
        request="delete my pod",
        command="delete",
        plan_prompt="Plan this: {request}",
        summary_prompt_func=lambda: "Summary prompt: {output}",
        output_flags=standard_output_flags,
    )

    # Verify confirmation was shown
    mock_confirm.assert_called_once()

    # Verify kubectl was called with the correct arguments
    mock_run_kubectl.assert_called_once()

    # Unpack the mocks for easier access
    mock_update_memory, mock_memory_update = mock_memory

    # Verify command_handler.update_memory was called with expected args
    assert mock_update_memory.call_count == 1
    args, kwargs = mock_update_memory.call_args
    assert args[0] == "delete pod my-pod"  # The command with verb prepended
    assert "Successfully deleted pod my-pod" in args  # The LLM summary
    assert standard_output_flags.model_name in args  # The model name

    # Verify memory.update_memory was also called (verifying the delegation works)
    assert mock_memory_update.call_count == 1
    mem_args, mem_kwargs = mock_memory_update.call_args
    # Command should be passed through with verb
    assert mem_args[0] == "delete pod my-pod"  
    # Model name should be passed through
    assert standard_output_flags.model_name in mem_args

    # Verify sys.exit was not called
    prevent_exit.assert_not_called()


def test_vibe_delete_with_confirmation_cancelled(
    mock_llm: MagicMock,
    mock_run_kubectl: Mock,
    mock_console: Mock,
    mock_confirm: MagicMock,
    prevent_exit: MagicMock,
    standard_output_flags: OutputFlags,
    mock_memory: tuple[MagicMock, MagicMock],
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

    # Verify neither memory update function was called
    mock_update_memory, mock_memory_update = mock_memory
    mock_update_memory.assert_not_called()
    mock_memory_update.assert_not_called()

    # Verify sys.exit was not called
    prevent_exit.assert_not_called()


def test_vibe_delete_yes_flag_bypasses_confirmation(
    mock_llm: MagicMock,
    mock_run_kubectl: Mock,
    mock_console: Mock,
    mock_confirm: MagicMock,
    prevent_exit: MagicMock,
    standard_output_flags: OutputFlags,
    mock_memory: tuple[MagicMock, MagicMock],
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
    mock_memory: tuple[MagicMock, MagicMock],
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
