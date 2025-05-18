"""Tests for vibectl delete command confirmation functionality."""

import json
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from vibectl.command_handler import ActionType, OutputFlags, handle_vibe_request
from vibectl.config import Config
from vibectl.model_adapter import LLMMetrics
from vibectl.prompt import (
    plan_vibe_fragments,
)
from vibectl.schema import LLMPlannerResponse, CommandAction, FeedbackAction
from vibectl.types import (
    Fragment,
    PromptFragments,
    Result,
    Success,
    SystemFragments,
    UserFragments,
)


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
        mock.return_value.execute_and_log_metrics.return_value = json.dumps(
            default_response
        )
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
        show_metrics=True,
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
    ):
        # Set default return values
        mock_get_memory.return_value = "Test memory context"

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


# Dummy summary prompt function that returns fragments
def get_test_summary_fragments(
    config: Config | None = None,
) -> PromptFragments:
    """Dummy summary prompt function for testing that returns fragments."""
    return PromptFragments(
        (
            SystemFragments([Fragment("System fragment with {output}")]),
            UserFragments([Fragment("User fragment with {output}")]),
        )
    )


@pytest.mark.asyncio
@patch("vibectl.command_handler._get_llm_plan")
async def test_vibe_delete_with_confirmation(
    mock_get_llm_plan: MagicMock,
    mock_llm: MagicMock,
    mock_run_kubectl: MagicMock,
    mock_console_for_test: MagicMock,
    prevent_exit: MagicMock,
    standard_output_flags: OutputFlags,
    mock_memory: tuple[MagicMock, MagicMock],
    mock_handle_output: MagicMock,
) -> None:
    """Test deletion command requires confirmation which is given."""
    command_action = CommandAction(
        action_type=ActionType.COMMAND,
        commands=["pod", "my-pod"],
    )
    plan_response_data = LLMPlannerResponse(action=command_action)
    mock_get_llm_plan.return_value = Success(
        data=plan_response_data, metrics=LLMMetrics(latency_ms=100)
    )

    # Keep patches for downstream functions
    with (
        patch("vibectl.command_handler._execute_command") as mock_execute_cmd,
        patch("vibectl.command_handler.click.prompt") as mock_click_prompt,
    ):
        mock_click_prompt.return_value = "y"
        mock_execute_cmd.return_value = Success(data='pod "my-pod" deleted')

        await handle_vibe_request(
            request="delete my pod",
            command="delete",
            plan_prompt_func=plan_vibe_fragments,
            summary_prompt_func=get_test_summary_fragments,
            output_flags=standard_output_flags,
            yes=False,
        )

        # Assert _get_llm_plan was called
        mock_get_llm_plan.assert_called_once()

        # Assert downstream mocks were called
        mock_click_prompt.assert_called_once()
        # Expect the original command verb "delete", and args from LLM plan
        mock_execute_cmd.assert_called_once_with(
            "delete", ["pod", "my-pod"], None, allowed_exit_codes=(0,)
        )

    # Verify memory was updated (using the mock_handle_output side effect)
    mock_update_memory, _ = mock_memory
    # Expect 2 calls: 1 after exec, 1 from handle_output mock side effect
    assert mock_update_memory.call_count == 2
    # Check the second call args (from handle_output mock)
    # This call originates from handle_command_output(..., command=kubectl_verb)
    # where kubectl_verb is from the LLM plan (e.g., "pod")
    mem_call_args_tuple = mock_update_memory.call_args_list[1]
    mem_call_args = mem_call_args_tuple.args  # If called with args

    # Determine if called with args or kwargs for the command
    # The side_effect in the mock_memory fixture calls it as:
    #  mock_update_mem(kwargs["command"], ...)
    # So it should be in args[0] of the actual mock_update_memory
    actual_command_for_memory = mem_call_args[0]
    assert (
        actual_command_for_memory == "delete"
    )  # Corrected: Should be the original command verb

    # Verify handle_command_output was called
    mock_handle_output.assert_called_once()


@pytest.mark.asyncio
@patch("vibectl.command_handler._get_llm_plan")
async def test_vibe_delete_with_confirmation_cancelled(
    mock_get_llm_plan: MagicMock,
    mock_llm: MagicMock,
    mock_run_kubectl: MagicMock,
    mock_console_for_test: MagicMock,
    prevent_exit: MagicMock,
    standard_output_flags: OutputFlags,
    mock_memory: tuple[MagicMock, MagicMock],
    mock_handle_output: MagicMock,
) -> None:
    """Test deletion command with confirmation that gets cancelled."""
    command_action = CommandAction(
        action_type=ActionType.COMMAND,
        commands=["pod", "nginx"],
    )
    plan_response_data = LLMPlannerResponse(action=command_action)
    mock_get_llm_plan.return_value = Success(
        data=plan_response_data, metrics=LLMMetrics(latency_ms=100)
    )

    # Configure side effect for the mock LLM adapter to handle the fuzzy update call
    fuzzy_update_response_text = "Memory updated by fuzzy logic."
    mock_llm.return_value.execute_and_log_metrics.side_effect = [
        # First call (planning) is handled by mock_get_llm_plan,
        # but side_effect needs an entry
        ("This should not be used", None),
        # Second call (fuzzy update) returns simple text and None metrics
        (fuzzy_update_response_text, None),
    ]

    # Patch _execute_command (it should NOT be called if cancelled)
    with (
        patch("vibectl.command_handler._execute_command") as mock_execute_cmd,
        patch("vibectl.command_handler.click.prompt") as mock_click_prompt,
    ):
        # Mock click.prompt to return 'b' (no but)
        mock_click_prompt.return_value = "b"

        result = await handle_vibe_request(
            request="delete nginx pod",
            command="delete",
            plan_prompt_func=plan_vibe_fragments,
            summary_prompt_func=get_test_summary_fragments,
            output_flags=standard_output_flags,
            yes=False,
        )

        # Verify _get_llm_plan was called
        mock_get_llm_plan.assert_called_once()
        # Verify confirmation prompt was called
        assert mock_click_prompt.call_count == 2

    # Verify confirmation cancelled message was printed
    mock_console_for_test.print_cancelled.assert_called_once()

    # Verify _execute_command was NOT called
    mock_execute_cmd.assert_not_called()

    # Verify the result indicates cancellation
    assert isinstance(result, Success)
    assert result.message == "Command execution cancelled by user"

    # Verify memory was NOT updated
    mock_update_memory, _ = mock_memory
    mock_update_memory.assert_not_called()  # Should not be called if command cancelled

    # Verify handle_command_output was NOT called because user cancelled
    mock_handle_output.assert_not_called()


@pytest.mark.asyncio
@patch("vibectl.command_handler._get_llm_plan")
async def test_vibe_delete_yes_flag_bypasses_confirmation(
    mock_get_llm_plan: MagicMock,
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
    command_action = CommandAction(
        action_type=ActionType.COMMAND,
        commands=["pod", "bypass-pod"],
    )
    plan_response_data = LLMPlannerResponse(action=command_action)
    mock_get_llm_plan.return_value = Success(
        data=plan_response_data, metrics=LLMMetrics(latency_ms=100)
    )

    # Patch _execute_command (it SHOULD be called)
    with patch("vibectl.command_handler._execute_command") as mock_execute_cmd:
        mock_execute_cmd.return_value = Success(data='pod "bypass-pod" deleted')

        result = await handle_vibe_request(
            request="delete bypass-pod pod",
            command="delete",
            plan_prompt_func=plan_vibe_fragments,
            summary_prompt_func=get_test_summary_fragments,
            output_flags=standard_output_flags,
            yes=True,  # <<<< Bypass confirmation
        )

        # Verify _get_llm_plan was called
        mock_get_llm_plan.assert_called_once()

        # Verify click.prompt was NOT called (using the original mock_prompt fixture)
        mock_prompt.assert_not_called()

        # Verify _execute_command WAS called
        # Expect the original command verb "delete", and args from LLM plan
        mock_execute_cmd.assert_called_once_with(
            "delete", ["pod", "bypass-pod"], None, allowed_exit_codes=(0,)
        )
        # Assert handle_command_output was called with the success result
        mock_handle_output.assert_called_once_with(
            mock_execute_cmd.return_value,
            standard_output_flags,
            get_test_summary_fragments,
            command="delete",  # Expect the original command verb here
        )

    # Verify result
    assert isinstance(result, Success)
    assert 'pod "bypass-pod" deleted' in result.data if result.data else False

    # Verify memory update and handle_output calls
    mock_update_memory, _ = mock_memory
    assert mock_update_memory.call_count == 2
    mock_handle_output.assert_called_once()


@pytest.mark.asyncio
@patch("vibectl.command_handler._get_llm_plan")
async def test_vibe_non_delete_commands_skip_confirmation(
    mock_get_llm_plan: MagicMock,
    mock_llm: MagicMock,
    mock_run_kubectl: MagicMock,
    mock_console_for_test: MagicMock,
    mock_prompt: MagicMock,
    prevent_exit: MagicMock,
    standard_output_flags: OutputFlags,
    mock_memory: tuple[MagicMock, MagicMock],
    mock_handle_output: MagicMock,
) -> None:
    """Test non-delete commands skip confirmation even if yes=False."""
    command_action = CommandAction(
        action_type=ActionType.COMMAND,
        commands=["pods", "-A"],  # Args for 'get'
    )
    plan_response_data = LLMPlannerResponse(action=command_action)
    mock_get_llm_plan.return_value = Success(
        data=plan_response_data, metrics=LLMMetrics(latency_ms=100)
    )

    # Patch _execute_command (it SHOULD be called)
    with patch("vibectl.command_handler._execute_command") as mock_execute_cmd:
        mock_execute_cmd.return_value = Success(data="pod data...")

        result = await handle_vibe_request(
            request="get all pods",
            command="get",  # <<<< Non-delete command
            plan_prompt_func=plan_vibe_fragments,
            summary_prompt_func=get_test_summary_fragments,
            output_flags=standard_output_flags,
            yes=False,  # <<<< Confirmation not bypassed by flag
        )

        # Verify _get_llm_plan was called
        mock_get_llm_plan.assert_called_once()

        # Verify click.prompt was NOT called (using the original mock_prompt fixture)
        mock_prompt.assert_not_called()

        # Verify _execute_command WAS called
        # Expect the original command verb "get", and args from LLM plan
        mock_execute_cmd.assert_called_once_with(
            "get", ["pods", "-A"], None, allowed_exit_codes=(0,)
        )
        # Assert handle_command_output was called
        mock_handle_output.assert_called_once_with(
            mock_execute_cmd.return_value,
            standard_output_flags,
            get_test_summary_fragments,
            command="get",  # Expect the original command verb here
        )

    # Verify result
    assert isinstance(result, Success)
    assert "pod data..." in result.data if result.data else False

    # Verify memory update and handle_output calls
    mock_update_memory, _ = mock_memory
    assert mock_update_memory.call_count == 2
    mock_handle_output.assert_called_once()


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
    # Mock LLM to return a delete command plan
    command_action = CommandAction(
        action_type=ActionType.COMMAND,
        commands=["pod", "nginx-mem"],
    )
    plan_response_data = LLMPlannerResponse(action=command_action)
    mock_llm.return_value.execute_and_log_metrics.return_value = (
        json.dumps(plan_response_data),
        LLMMetrics(latency_ms=100),
    )
    mock_llm.return_value.execute_and_log_metrics.side_effect = (
        None  # Ensure no side effect
    )

    # Mock get_memory (handled by mock_memory fixture, returns "Test memory context")
    _, mock_memory_update = mock_memory
    mock_get_memory.return_value = "Memory content for test"

    # Patch _execute_command and click.prompt
    with (
        patch("vibectl.command_handler._execute_command") as mock_execute_cmd,
        patch("vibectl.command_handler.click.prompt") as mock_click_prompt,
    ):
        # Simulate user entering 'm' then 'y'
        mock_click_prompt.side_effect = ["m", "y"]
        mock_execute_cmd.return_value = Success(data='pod "nginx-mem" deleted')

        result = await handle_vibe_request(
            request="delete nginx-mem pod",
            command="delete",
            plan_prompt_func=plan_vibe_fragments,
            summary_prompt_func=get_test_summary_fragments,
            output_flags=standard_output_flags,
            yes=False,
        )

        # Verify prompt was called twice (once for 'm', once for 'y')
        assert mock_click_prompt.call_count == 2
        # Verify get_memory was called when user chose 'm'
        mock_get_memory.assert_called_once()
        # Verify memory content was printed (check console mock)
        mock_console.safe_print.assert_called_once()
        # Verify the command *was* executed after 'y'
        # Expect the original command verb "delete", and args from LLM plan
        mock_execute_cmd.assert_called_once_with(
            "delete", ["pod", "nginx-mem"], None, allowed_exit_codes=(0,)
        )

        # Verify result is Success
        assert isinstance(result, Success)
        assert result.data is not None
        assert 'pod "nginx-mem" deleted' in result.data

        # Verify memory was updated (once by _confirm_and_execute, once
        # by handle_output mock)
        assert mock_memory_update.call_count == 2
        # Verify handle_command_output was called
        mock_handle_output.assert_called_once()


@pytest.mark.asyncio
@patch("vibectl.command_handler.set_memory")  # Mock set_memory
@patch("vibectl.command_handler.get_memory")
@patch("vibectl.command_handler.console_manager")
async def test_vibe_delete_confirmation_no_but_fuzzy_update_error(
    mock_console: MagicMock,
    mock_get_memory: MagicMock,
    mock_set_memory: MagicMock,  # Added mock
    mock_llm: MagicMock,  # Original planning mock fixture - USE THIS
    mock_run_kubectl: MagicMock,
    prevent_exit: MagicMock,
    standard_output_flags: OutputFlags,
    mock_memory: tuple[MagicMock, MagicMock],
    mock_handle_output: MagicMock,
) -> None:
    """Test 'no but' confirmation where the fuzzy memory update LLM call fails."""
    # Mock LLM response for original delete command planning
    command_action = CommandAction(
        action_type=ActionType.COMMAND,
        commands=["pod", "nginx"],
    )
    plan_response_data = LLMPlannerResponse(action=command_action)

    # Mock response for the fuzzy update LLM call - should be FeedbackAction
    feedback_action = FeedbackAction(
        action_type=ActionType.FEEDBACK,
        message="Memory context noted.", # Changed from explanation to message
    )
    fuzzy_update_llm_response = LLMPlannerResponse(action=feedback_action)

    # Simulate _get_llm_plan for the initial delete, then fuzzy update failure
    mock_llm.return_value.execute_and_log_metrics.side_effect = [
        (
            plan_response_data.model_dump_json(),
            LLMMetrics(latency_ms=100),
        ),  # First call (planning the delete)
        # Second call (fuzzy memory update) - this one will raise an error in the test
        Exception("LLM API error during fuzzy update"),
    ]

    # Patch _execute_command (it should NOT be called if cancelled)
    with (
        patch("vibectl.command_handler._execute_command") as mock_execute_cmd,
        patch("vibectl.command_handler.click.prompt") as mock_click_prompt,
    ):
        # Mock click.prompt to return 'b' (no but)
        mock_click_prompt.return_value = "b"

        result = await handle_vibe_request(
            request="delete nginx pod",
            command="delete",
            plan_prompt_func=plan_vibe_fragments,
            summary_prompt_func=get_test_summary_fragments,
            output_flags=standard_output_flags,
            yes=False,
        )

        # Verify confirmation prompt was called
        # (once for Y/N/A/B/M, once for fuzzy update)
        assert mock_click_prompt.call_count == 2
        # Verify _execute_command was NOT called
        mock_execute_cmd.assert_not_called()

        # Verify the result indicates cancellation (still Success, but cancelled)
        assert isinstance(result, Success)
        assert result.message == "Command execution cancelled by user"

        # Verify fuzzy update LLM call happened
        # (execute_and_log_metrics called twice)
        # Use the mock_llm fixture's return_value (the adapter instance)
        assert mock_llm.return_value.execute_and_log_metrics.call_count == 2

        # Verify memory was updated by the fuzzy logic
        # (mocked by mock_memory fixture?)
        mock_set_memory.assert_called_once()

    # Verify handle_command_output was NOT called because user cancelled
    mock_handle_output.assert_not_called()
