"""Tests for vibectl delete command confirmation functionality."""

import json
from collections.abc import Generator
from typing import Any
from unittest.mock import ANY, MagicMock, patch

import pytest

from vibectl.command_handler import ActionType, OutputFlags, handle_vibe_request
from vibectl.types import Error, Result, Success  # Import Result and Error


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
            "explanation": "Default test response.",
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


@pytest.mark.asyncio
async def test_vibe_delete_with_confirmation(
    mock_llm: MagicMock,
    mock_run_kubectl: MagicMock,
    mock_console_for_test: MagicMock,
    prevent_exit: MagicMock,
    standard_output_flags: OutputFlags,
    mock_memory: tuple[MagicMock, MagicMock],
    mock_handle_output: MagicMock,
) -> None:
    """Test deletion command requires confirmation which is given."""
    # Mock LLM response for delete command (args only)
    plan_response = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["pod", "my-pod"],  # Args only
        "explanation": "Deleting pod my-pod as requested.",
    }
    mock_llm.return_value.execute.return_value = json.dumps(plan_response)

    # Patch _execute_command and click.prompt directly
    with (
        patch("vibectl.command_handler._execute_command") as mock_execute_cmd,
        patch("click.prompt") as mock_click_prompt,
    ):
        mock_click_prompt.return_value = "y"
        mock_execute_cmd.return_value = Success(data='pod "my-pod" deleted')

        await handle_vibe_request(
            request="delete my pod",
            command="delete",
            plan_prompt="Plan this: {request}",
            summary_prompt_func=lambda: "Summary prompt: {output}",
            output_flags=standard_output_flags,
            yes=False,
        )

        mock_click_prompt.assert_called_once()
        mock_execute_cmd.assert_called_once_with("delete", ["pod", "my-pod"], None)

    # Verify memory was updated (using the mock_handle_output side effect)
    mock_update_memory, _ = mock_memory
    # Expect 2 calls: 1 after exec, 1 from handle_output mock side effect
    assert mock_update_memory.call_count == 2
    # Check the second call args (from handle_output mock)
    mem_call_args = mock_update_memory.call_args_list[1][0]
    assert mem_call_args[0] == "delete"

    # Verify handle_command_output was called
    mock_handle_output.assert_called_once()
    _, ho_call_kwargs = mock_handle_output.call_args
    assert ho_call_kwargs.get("command") == "delete"


@pytest.mark.asyncio
async def test_vibe_delete_with_confirmation_cancelled(
    mock_llm: MagicMock,
    mock_run_kubectl: MagicMock,
    mock_console_for_test: MagicMock,
    prevent_exit: MagicMock,
    standard_output_flags: OutputFlags,
    mock_memory: tuple[MagicMock, MagicMock],
    mock_handle_output: MagicMock,
) -> None:
    """Test deletion command with confirmation that gets cancelled."""
    # Mock LLM response for delete command (args only)
    plan_response = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["pod", "nginx"],  # Args only
        "explanation": "Deleting pod nginx as requested.",
    }
    mock_llm.return_value.execute.return_value = json.dumps(plan_response)
    mock_llm.return_value.execute.side_effect = None

    # Patch _execute_command (it should NOT be called)
    with (
        patch("vibectl.command_handler._execute_command") as mock_execute_cmd,
        patch("click.prompt") as mock_click_prompt,
    ):
        mock_click_prompt.return_value = "n"  # User cancels

        result = await handle_vibe_request(
            request="delete nginx pod",
            command="delete",
            plan_prompt="Plan this: {request}",
            summary_prompt_func=lambda: "Summary prompt: {output}",
            output_flags=standard_output_flags,
            yes=False,
        )

        mock_click_prompt.assert_called_once()

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


@pytest.mark.asyncio
async def test_vibe_delete_yes_flag_bypasses_confirmation(
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
    # Mock LLM response for delete command (args only)
    plan_response = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["pod", "my-pod"],  # Args only
        "explanation": "Deleting pod my-pod as requested.",
    }
    mock_llm.return_value.execute.return_value = json.dumps(plan_response)
    mock_llm.return_value.execute.side_effect = None

    # Patch _execute_command
    with patch("vibectl.command_handler._execute_command") as mock_execute_cmd:
        mock_execute_cmd.return_value = Success(data="pod 'my-pod' deleted")

        await handle_vibe_request(
            request="delete my pod",
            command="delete",
            plan_prompt="Plan this: {request}",
            summary_prompt_func=lambda: "Summary prompt: {output}",
            output_flags=standard_output_flags,
            yes=True,
        )

    # Verify confirmation prompt was NOT shown
    mock_prompt.assert_not_called()

    # Verify _execute_command was called correctly
    mock_execute_cmd.assert_called_once_with("delete", ["pod", "my-pod"], None)

    # Verify memory was updated
    mock_update_memory, _ = mock_memory
    # Expect 2 calls: 1 after exec, 1 from handle_output mock side effect
    assert mock_update_memory.call_count == 2

    # Verify handle_command_output was called
    mock_handle_output.assert_called_once()
    _, ho_call_kwargs = mock_handle_output.call_args
    assert ho_call_kwargs.get("command") == "delete"


@pytest.mark.asyncio
async def test_vibe_non_delete_commands_skip_confirmation(
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
    # Mock LLM response for a safe command (get) (args only)
    plan_response = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["pods"],  # Args only
        "explanation": "Getting pods.",
    }

    # <<< FIX: Set return_value on the mocked adapter instance returned by the patch >>>
    mock_llm.return_value.execute.return_value = json.dumps(plan_response)
    # Ensure side_effect is cleared if set elsewhere
    mock_llm.return_value.execute.side_effect = None

    # Patch _execute_command to check it's called and returns success
    with patch("vibectl.command_handler._execute_command") as mock_execute_cmd:
        mock_execute_cmd.return_value = Success(data="pod-a\\npod-b")

        # Call function with a non-delete command and yes=False
        await handle_vibe_request(
            request="show pods",
            command="get",
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
    # Expect 2 calls
    assert mock_update_memory.call_count == 2

    # Verify handle_command_output was called
    mock_handle_output.assert_called_once()
    _, ho_call_kwargs = mock_handle_output.call_args
    assert ho_call_kwargs.get("command") == "get"


@patch("vibectl.memory.get_memory")
@patch("vibectl.command_handler.console_manager")
@pytest.mark.asyncio
async def test_vibe_delete_confirmation_memory_option(
    mock_console: MagicMock,
    mock_get_memory: MagicMock,
    mock_llm: MagicMock,
    mock_run_kubectl: MagicMock,
    prevent_exit: MagicMock,
    standard_output_flags: OutputFlags,
    mock_memory: tuple[MagicMock, MagicMock],
    mock_handle_output: MagicMock,
) -> None:
    """Test the 'm' (memory) option during command confirmation."""
    # Mock LLM response for delete command
    plan_response = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["pod", "mem-test"],
        "explanation": "Deleting pod mem-test.",
    }
    mock_llm.return_value.execute.return_value = json.dumps(plan_response)

    # Mock get_memory return value
    mock_get_memory.return_value = "Current memory content."

    # Patch _execute_command and click.prompt
    with (
        patch("vibectl.command_handler._execute_command") as mock_execute_cmd,
        patch("click.prompt") as mock_click_prompt,
    ):
        # Simulate user entering 'm' then 'y'
        mock_click_prompt.side_effect = ["m", "y"]
        mock_execute_cmd.return_value = Success(data='pod "mem-test" deleted')

        await handle_vibe_request(
            request="delete mem-test pod",
            command="delete",
            plan_prompt="Plan: {request}",
            summary_prompt_func=lambda: "Summary: {output}",
            output_flags=standard_output_flags,
            yes=False,
        )

        # Verify prompt was called twice (once for 'm', once for 'y')
        assert mock_click_prompt.call_count == 2
        # Verify get_memory was called after 'm' was entered
        mock_get_memory.assert_called_once()
        # Verify memory content was printed (via console_manager.safe_print)
        # Use assert_any_call as other prints might happen
        mock_console.safe_print.assert_any_call(
            mock_console.console, ANY
        )  # ANY checks for Panel object
        # Verify command was executed after 'y' was entered
        mock_execute_cmd.assert_called_once_with("delete", ["pod", "mem-test"], None)

    # Verify memory was updated (expect 2 calls)
    mock_update_memory, _ = mock_memory
    assert mock_update_memory.call_count == 2

    # Verify handle_command_output was called
    mock_handle_output.assert_called_once()


@pytest.mark.asyncio
@patch("vibectl.command_handler.set_memory")  # Mock set_memory
@patch("vibectl.command_handler.get_memory")
@patch("vibectl.command_handler.get_model_adapter")  # Mock adapter for fuzzy update
@patch("vibectl.command_handler.console_manager")
async def test_vibe_delete_confirmation_no_but_fuzzy_update_error(
    mock_console: MagicMock,
    mock_get_adapter: MagicMock,
    mock_get_memory: MagicMock,
    mock_set_memory: MagicMock,  # Added mock
    mock_llm: MagicMock,  # Original planning mock
    mock_run_kubectl: MagicMock,
    prevent_exit: MagicMock,
    standard_output_flags: OutputFlags,
    mock_memory: tuple[MagicMock, MagicMock],
    mock_handle_output: MagicMock,
) -> None:
    """Test 'no but' confirmation where the fuzzy memory update LLM call fails."""
    # Mock LLM response for original delete command planning
    plan_response = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["pod", "fuzzy-fail"],
        "explanation": "Deleting pod fuzzy-fail.",
    }
    planning_response_str = json.dumps(plan_response)

    # Mock get_memory for the fuzzy update part
    mock_get_memory.return_value = "Existing memory"

    # Mock the *single* adapter instance provided by the mock_get_adapter fixture
    # Make its execute method have a side effect: first success, then failure
    mock_fuzzy_adapter = mock_get_adapter.return_value  # Get the mock adapter instance
    fuzzy_update_exception = ConnectionError("Fuzzy LLM unavailable")
    mock_fuzzy_adapter.execute.side_effect = [
        planning_response_str,  # First call (planning) succeeds
        fuzzy_update_exception,  # Second call (fuzzy update) raises error
    ]

    # Patch _execute_command and click.prompt
    with (
        patch("vibectl.command_handler._execute_command") as mock_execute_cmd,
        patch("click.prompt") as mock_click_prompt,
    ):
        # Simulate user entering 'b' (no but) and then the update text
        mock_click_prompt.side_effect = ["b", "extra context"]

        result = await handle_vibe_request(
            request="delete fuzzy-fail pod",
            command="delete",
            plan_prompt="Plan: {request}",
            summary_prompt_func=lambda: "Summary: {output}",
            output_flags=standard_output_flags,
            yes=False,
        )

        # Verify prompt was called twice (once for 'b', once for update text)
        assert mock_click_prompt.call_count == 2
        # Verify get_memory was called for the update
        mock_get_memory.assert_called_once()
        # Verify the fuzzy update LLM call was attempted (execute called twice total)
        assert mock_fuzzy_adapter.execute.call_count == 2
        # Verify set_memory was NOT called because the update failed
        mock_set_memory.assert_not_called()
        # Verify original command was NOT executed
        mock_execute_cmd.assert_not_called()

    # Verify the result is an Error reflecting the fuzzy update failure
    assert isinstance(result, Error)
    assert result.error == f"Error updating memory: {fuzzy_update_exception}"
    assert result.exception == fuzzy_update_exception

    # Verify cancellation was printed initially
    mock_console.print_cancelled.assert_called_once()
    # Verify fuzzy update error was printed
    mock_console.print_error.assert_called_with(
        f"Error updating memory: {fuzzy_update_exception}"
    )

    # Verify memory was NOT updated via the main update_memory function
    mock_update_main, _ = mock_memory
    mock_update_main.assert_not_called()
    # Verify handle_command_output was NOT called
    mock_handle_output.assert_not_called()
