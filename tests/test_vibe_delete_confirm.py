"""Tests for vibectl delete command confirmation functionality."""

import json
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from vibectl.command_handler import ActionType, OutputFlags, handle_vibe_request
from vibectl.types import Error, Result, Success  # Import Result


@pytest.fixture
def mock_llm() -> Generator[MagicMock, None, None]:
    """Fixture for mocking llm model."""
    with patch("vibectl.command_handler.get_model_adapter") as mock:
        # Configure the mock to return a model
        mock_model = MagicMock()
        mock.return_value.get_model.return_value = mock_model
        # Configure the model.execute function to return valid JSON by default
        default_response = {
            "action_type": ActionType.FEEDBACK.value,
            "explanation": "Default test response."
        }
        mock.return_value.execute.return_value = json.dumps(default_response)
        yield mock


@pytest.fixture
def mock_prompt() -> Generator[MagicMock, None, None]:
    """Fixture for mocking click.prompt."""
    with patch("click.prompt") as mock:
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
        # Add mock for print_processing
        mock.print_processing = MagicMock()
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
        output_result: Result,
        output_flags: OutputFlags,
        summary_prompt_func: Any,
        command: str | None = None,
        **kwargs: Any,
    ) -> Result:
        """Side effect that preserves memory updates and returns result."""
        # Only call update_memory if command is provided and output is Success
        if command and isinstance(output_result, Success) and output_result.data:
            from vibectl.command_handler import update_memory
            # Assume vibe output generation happens somewhere and mock it
            mock_vibe_output = f"Vibe summary for {command}"
            update_memory(command, output_result.data, mock_vibe_output)
        return output_result

    with patch("vibectl.command_handler.handle_command_output") as mock:
        mock.side_effect = handle_output_side_effect
        yield mock


def test_vibe_delete_with_confirmation(
    mock_llm: MagicMock,
    mock_run_kubectl: MagicMock,
    mock_console_for_test: MagicMock,
    prevent_exit: MagicMock,
    standard_output_flags: OutputFlags,
    mock_memory: tuple[MagicMock, MagicMock],
    mock_handle_output: MagicMock,
) -> None:
    """Test deletion command requires confirmation which is given."""
    # Construct the expected JSON response for planning
    plan_response = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["delete", "pod", "my-pod"],
        "explanation": "Deleting pod my-pod as requested.",
    }
    # Mock the summary response (called after successful execution)
    summary_response = {
        "action_type": ActionType.FEEDBACK.value,
        "explanation": "Successfully deleted pod my-pod",
    }
    mock_llm.execute.side_effect = [
        json.dumps(plan_response),
    ]

    # Patch _execute_command and click.prompt directly
    with patch("vibectl.command_handler._execute_command") as mock_execute_cmd, \
         patch("click.prompt") as mock_click_prompt: # Direct patch

        # Mock interactive prompt to return 'y' (user confirms)
        mock_click_prompt.return_value = 'y'
        mock_execute_cmd.return_value = Success(data='pod "my-pod" deleted')

        # Call function with yes=False (default) to trigger confirmation
        handle_vibe_request(
            request="delete my pod",
            command="vibe",
            plan_prompt="Plan this: {request}",
            summary_prompt_func=lambda: "Summary prompt: {output}",
            output_flags=standard_output_flags,
            yes=False,
        )

        # Verify confirmation prompt was shown using the direct mock
        mock_click_prompt.assert_called_once()
        # Verify execute was called because confirmation passed
        mock_execute_cmd.assert_called_once_with("delete", ["pod", "my-pod"], None)

    # Verify memory was updated (using the mock_handle_output side effect)
    mock_update_memory, _ = mock_memory
    mock_update_memory.assert_called_once()
    mem_call_args = mock_update_memory.call_args[0]
    assert mem_call_args[0] == "delete"
    assert mem_call_args[1] == 'pod "my-pod" deleted'
    assert mem_call_args[2] == "Vibe summary for delete"

    # Verify handle_command_output was called
    mock_handle_output.assert_called_once()
    _, ho_call_kwargs = mock_handle_output.call_args
    assert ho_call_kwargs.get("command") == "delete"


def test_vibe_delete_with_confirmation_cancelled(
    mock_llm: MagicMock,
    mock_run_kubectl: MagicMock,
    mock_console_for_test: MagicMock,
    prevent_exit: MagicMock,
    standard_output_flags: OutputFlags,
    mock_memory: tuple[MagicMock, MagicMock],
    mock_handle_output: MagicMock,
) -> None:
    """Test deletion command with confirmation that gets cancelled."""
    # Construct the expected JSON response for planning
    plan_response = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["delete", "pod", "nginx"],
        "explanation": "Deleting pod nginx as requested.",
    }
    mock_llm.execute.return_value = json.dumps(plan_response)

    # Patch _execute_command (it should NOT be called)
    with patch("vibectl.command_handler._execute_command") as mock_execute_cmd:
        # Call function with yes=False (default) to trigger confirmation
        result = handle_vibe_request(
            request="delete nginx pod",
            command="vibe",
            plan_prompt="Plan this: {request}",
            summary_prompt_func=lambda: "Summary prompt: {output}",
            output_flags=standard_output_flags,
            yes=False,
        )

    # Verify confirmation prompt was shown
    mock_console_for_test.print_cancelled.assert_called_once()

    # Verify _execute_command was NOT called
    mock_execute_cmd.assert_not_called()

    # Verify the result indicates cancellation
    assert isinstance(result, Success)
    assert result.message == "Command execution cancelled by user"

    # Verify memory was NOT updated
    mock_update_memory, _ = mock_memory
    mock_update_memory.assert_not_called()

    # Verify handle_command_output was NOT called
    mock_handle_output.assert_not_called()


def test_vibe_delete_yes_flag_bypasses_confirmation(
    mock_llm: MagicMock,
    mock_run_kubectl: MagicMock,
    mock_console_for_test: MagicMock,
    mock_prompt: MagicMock,
    prevent_exit: MagicMock,
    standard_output_flags: OutputFlags,
    mock_memory: tuple[MagicMock, MagicMock],
    mock_handle_output: MagicMock,
) -> None:
    """Test that the --yes flag bypasses the delete confirmation."""
    plan_response = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["delete", "configmap", "my-cm"],
        "explanation": "Deleting configmap.",
    }
    mock_llm.execute.return_value = json.dumps(plan_response)

    # Patch _execute_command
    with patch("vibectl.command_handler._execute_command") as mock_execute_cmd:
        mock_execute_cmd.return_value = Success(data="configmap 'my-cm' deleted")

        # Call function with yes=True
        handle_vibe_request(
            request="delete my configmap",
            command="vibe",
            plan_prompt="Plan this: {request}",
            summary_prompt_func=lambda: "Summary prompt: {output}",
            output_flags=standard_output_flags,
            yes=True,
        )

    # Verify confirmation prompt was NOT shown
    mock_prompt.assert_not_called()

    # Verify _execute_command was called correctly
    mock_execute_cmd.assert_called_once_with("delete", ["configmap", "my-cm"], None)

    # Verify memory was updated
    mock_update_memory, _ = mock_memory
    mock_update_memory.assert_called_once()

    # Verify handle_command_output was called
    mock_handle_output.assert_called_once()
    _, ho_call_kwargs = mock_handle_output.call_args
    assert ho_call_kwargs.get("command") == "delete"


def test_vibe_non_delete_commands_skip_confirmation(
    mock_llm: MagicMock,
    mock_run_kubectl: MagicMock,
    mock_console_for_test: MagicMock,
    mock_prompt: MagicMock,
    prevent_exit: MagicMock,
    standard_output_flags: OutputFlags,
    mock_memory: tuple[MagicMock, MagicMock],
    mock_handle_output: MagicMock,
) -> None:
    """Test that non-delete commands skip the confirmation prompt."""
    # Construct the expected JSON response for planning (a 'get' command)
    plan_response = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["get", "pods"],
        "explanation": "Getting pods.",
    }
    # Mock the summary response
    summary_response = {
        "action_type": ActionType.FEEDBACK.value,
        "explanation": "Here are the pods.",
    }
    mock_llm.execute.side_effect = [
        json.dumps(plan_response),
        json.dumps(summary_response),
    ]

    # Patch _execute_command to check it's called and returns success
    with patch("vibectl.command_handler._execute_command") as mock_execute_cmd:
        mock_execute_cmd.return_value = Success(data="pod-a\\npod-b")

        # Call function with a non-delete command and yes=False
        handle_vibe_request(
            request="show pods",
            command="vibe",
            plan_prompt="Plan this: {request}",
            summary_prompt_func=lambda: "Summary prompt: {output}",
            output_flags=standard_output_flags,
            yes=False,
        )

    # Verify confirmation prompt was NOT shown
    mock_prompt.assert_not_called()

    # Verify _execute_command was called correctly
    mock_execute_cmd.assert_called_once_with("get", ["pods"], None)
    call_args, _ = mock_execute_cmd.call_args
    assert call_args[0] == "get"
    assert call_args[1] == ["pods"]
    assert call_args[2] is None

    # Verify memory was updated
    mock_update_memory, _ = mock_memory
    mock_update_memory.assert_called_once()

    # Verify handle_command_output was called
    mock_handle_output.assert_called_once()
    _, ho_call_kwargs = mock_handle_output.call_args
    assert ho_call_kwargs.get("command") == "get"
