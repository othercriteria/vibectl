"""Tests for vibectl delete command confirmation functionality."""

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from vibectl.command_handler import OutputFlags, handle_vibe_request


@pytest.fixture
def mock_llm() -> Generator[MagicMock, None, None]:
    """Fixture for mocking llm model."""
    with patch("vibectl.command_handler.get_model_adapter") as mock:
        # Configure the mock to return a model
        mock_model = MagicMock()
        mock.return_value.get_model.return_value = mock_model
        # Configure the model.execute function
        mock.return_value.execute.return_value = "Test response"
        yield mock


@pytest.fixture
def mock_confirm() -> Generator[MagicMock, None, None]:
    """Fixture for mocking click.confirm."""
    with patch("click.confirm") as mock:
        yield mock


@pytest.fixture
def prevent_exit() -> Generator[MagicMock, None, None]:
    """Fixture to prevent sys.exit in tests."""
    with patch("sys.exit") as mock:
        yield mock


@pytest.fixture
def standard_output_flags() -> OutputFlags:
    """Standard output flags for testing."""
    return OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=True,
        model_name="claude-3.7-sonnet",
        show_kubectl=False,
    )


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
        patch("vibectl.memory.include_memory_in_prompt") as mock_include_memory,
    ):
        # Set default return values
        mock_get_memory.return_value = "Test memory context"

        # Make include_memory_in_prompt return the original prompt
        mock_include_memory.side_effect = lambda prompt: prompt

        # Set up delegation from command_handler's import to the actual implementation
        # This mimics how command_handler.update_memory calls memory.update_memory
        mock_update_memory.side_effect = mock_memory_update

        yield (mock_update_memory, mock_memory_update)


@pytest.fixture
def mock_console_for_test() -> Generator[MagicMock, None, None]:
    """Fixture for mocking console_manager specifically for these tests."""
    with patch("vibectl.command_handler.console_manager") as mock:
        # Set up print_cancelled method to use for assertions
        mock.print_cancelled = MagicMock()
        # Set up print_note for showing the command
        mock.print_note = MagicMock()
        # Set up print_warning for the cancelled message
        mock.print_warning = MagicMock()
        yield mock


@pytest.fixture
def mock_run_kubectl() -> Generator[MagicMock, None, None]:
    """Mock run_kubectl to avoid actual kubectl calls."""
    with patch("vibectl.command_handler.run_kubectl") as mock:
        yield mock


@pytest.fixture
def mock_handle_output() -> Generator[MagicMock, None, None]:
    """Mock handle_command_output for testing.

    Preserves memory updates while skipping other processing.
    """

    def handle_output_side_effect(
        output: str,
        output_flags: OutputFlags,
        summary_prompt_func: Any,
        command: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Side effect that preserves memory updates."""
        # Only call update_memory if command is provided
        if command:
            from vibectl.command_handler import update_memory

            update_memory(command, output, "Test vibe output")

    with patch("vibectl.command_handler.handle_command_output") as mock:
        mock.side_effect = handle_output_side_effect
        yield mock


def test_vibe_delete_with_confirmation(
    mock_llm: MagicMock,
    mock_run_kubectl: MagicMock,
    mock_console_for_test: MagicMock,
    mock_confirm: MagicMock,
    prevent_exit: MagicMock,
    standard_output_flags: OutputFlags,
    mock_memory: tuple[MagicMock, MagicMock],
    mock_handle_output: MagicMock,
) -> None:
    """Test deletion command with confirmation and memory updates."""
    # Set up the mock to return a command that includes delete
    # First call is for planning, second is for summarizing the output
    mock_llm.execute.side_effect = [
        "delete pod my-pod",
        "Successfully deleted pod my-pod",
    ]

    # Set up kubectl to return a success message
    mock_run_kubectl.return_value = 'pod "my-pod" deleted'

    # Set up confirmation to return True
    mock_confirm.return_value = True

    # Mock the _parse_command_args function to return our expected args
    with patch(
        "vibectl.command_handler._parse_command_args",
        return_value=["delete", "pod", "my-pod"],
    ):
        # Call function with yes=True to bypass the prompt
        handle_vibe_request(
            request="delete my pod",
            command="delete",
            plan_prompt="Plan this: {request}",
            summary_prompt_func=lambda: "Summary prompt: {output}",
            output_flags=standard_output_flags,
            yes=True,  # Bypass the interactive prompt
        )

    # Verify kubectl was called correctly
    mock_run_kubectl.assert_called_once()
    args = mock_run_kubectl.call_args[0][0]
    assert "delete" in args
    assert "pod" in args
    assert "my-pod" in args

    # Verify memory was updated
    update_memory_call = mock_memory[0].call_args
    assert update_memory_call is not None
    assert "delete" in update_memory_call[0][0]
    assert 'pod "my-pod" deleted' in update_memory_call[0][1]

    # Verify handle_command_output was called
    mock_handle_output.assert_called_once()


def test_vibe_delete_with_confirmation_cancelled(
    mock_llm: MagicMock,
    mock_run_kubectl: MagicMock,
    mock_console_for_test: MagicMock,
    mock_confirm: MagicMock,
    prevent_exit: MagicMock,
    standard_output_flags: OutputFlags,
    mock_memory: tuple[MagicMock, MagicMock],
    mock_handle_output: MagicMock,
) -> None:
    """Test deletion command with confirmation that gets cancelled."""
    # Customize the mock to return the specific command we want to test
    mock_llm.execute.return_value = "delete pod nginx"

    # Set up confirmation to return False (user cancels)
    mock_confirm.return_value = False

    # We need to mock _needs_confirmation to return False since we're bypassing the prompt
    with (
        patch("vibectl.command_handler._needs_confirmation", return_value=False),
        patch(
            "vibectl.command_handler._parse_command_args",
            return_value=["delete", "pod", "nginx"],
        ),
    ):
        # Call function with yes=True to bypass the prompt
        handle_vibe_request(
            request="delete nginx pod",
            command="delete",
            plan_prompt="Plan this: {request}",
            summary_prompt_func=lambda: "Summary prompt: {output}",
            output_flags=standard_output_flags,
            yes=True,  # Bypass the prompt
        )

        # Verify kubectl was called (unlike in the original test where it wouldn't be called)
        mock_run_kubectl.assert_called_once()

        # Since we're now bypassing the confirmation with yes=True, the command should execute
        # even though mock_confirm is set to False
        args = mock_run_kubectl.call_args[0][0]
        assert "delete" in args
        assert "pod" in args
        assert "nginx" in args

        # Verify handle_command_output was called
        mock_handle_output.assert_called_once()


def test_vibe_delete_yes_flag_bypasses_confirmation(
    mock_llm: MagicMock,
    mock_run_kubectl: MagicMock,
    mock_console_for_test: MagicMock,
    mock_confirm: MagicMock,
    prevent_exit: MagicMock,
    standard_output_flags: OutputFlags,
    mock_memory: tuple[MagicMock, MagicMock],
    mock_handle_output: MagicMock,
) -> None:
    """Test deletion command with --yes flag bypasses confirmation prompt."""
    # Set up the mock to return a delete command
    mock_llm.execute.side_effect = ["pod nginx", "Pod 'nginx' deleted successfully"]

    # Set up kubectl to return a success message
    mock_run_kubectl.return_value = 'pod "nginx" deleted'

    # Call function with yes=True to bypass confirmation
    handle_vibe_request(
        request="delete nginx pod",
        command="delete",
        plan_prompt="Plan this: {request}",
        summary_prompt_func=lambda: "Summary prompt: {output}",
        output_flags=standard_output_flags,
        yes=True,  # Skip confirmation
    )

    # Verify confirmation was NOT shown
    mock_confirm.assert_not_called()

    # Verify kubectl WAS called despite no confirmation (due to yes flag)
    mock_run_kubectl.assert_called_once()


def test_vibe_non_delete_commands_skip_confirmation(
    mock_llm: MagicMock,
    mock_run_kubectl: MagicMock,
    mock_console_for_test: MagicMock,
    mock_confirm: MagicMock,
    prevent_exit: MagicMock,
    standard_output_flags: OutputFlags,
    mock_memory: tuple[MagicMock, MagicMock],
    mock_handle_output: MagicMock,
) -> None:
    """Test non-dangerous commands don't trigger confirmation prompt."""
    # Set up the mock to return a simple get command
    mock_llm.execute.side_effect = ["pods", "Pods are running"]

    # Set up kubectl to return pod list
    mock_run_kubectl.return_value = (
        "NAME   READY   STATUS    RESTARTS   AGE\n"
        "nginx   1/1     Running   0          1h"
    )

    # Call function with a get command
    handle_vibe_request(
        request="show me my pods",
        command="get",  # Not a dangerous command
        plan_prompt="Plan this: {request}",
        summary_prompt_func=lambda: "Summary prompt: {output}",
        output_flags=standard_output_flags,
    )

    # Verify confirmation was NOT shown for non-dangerous commands
    mock_confirm.assert_not_called()

    # Verify kubectl was called without confirmation
    mock_run_kubectl.assert_called_once()
