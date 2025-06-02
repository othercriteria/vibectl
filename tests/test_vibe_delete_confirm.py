"""Tests for vibectl delete command confirmation functionality."""

from collections.abc import Generator
from typing import Any
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from vibectl.config import Config
from vibectl.execution.vibe import ActionType, OutputFlags, handle_vibe_request
from vibectl.model_adapter import LLMMetrics
from vibectl.prompts.vibe import plan_vibe_fragments
from vibectl.schema import CommandAction, FeedbackAction, LLMPlannerResponse
from vibectl.types import (
    Error,
    Fragment,
    MetricsDisplayMode,
    PromptFragments,
    Result,
    Success,
    SystemFragments,
    UserFragments,
)


@pytest.fixture
def mock_llm() -> Generator[MagicMock, None, None]:
    """Fixture for mocking llm model."""
    with patch("vibectl.execution.vibe.get_model_adapter") as mock:
        # Configure the mock to return a model
        mock_model_adapter = MagicMock()
        mock_model_adapter.get_model.return_value = MagicMock()

        # Configure execute_and_log_metrics as an AsyncMock
        mock_model_adapter.execute_and_log_metrics = AsyncMock()

        # Default side effect for execute_and_log_metrics
        default_response_action = {
            "action_type": ActionType.FEEDBACK.value,
            "message": "Default feedback message",
            "explanation": "Default test response.",
        }
        default_llm_response_obj = LLMPlannerResponse(
            action=FeedbackAction(**default_response_action)
        )
        default_response_tuple = (
            default_llm_response_obj.model_dump_json(),
            LLMMetrics(latency_ms=10),
        )

        async def default_side_effect(
            *args: Any, **kwargs: Any
        ) -> tuple[str, LLMMetrics]:
            return default_response_tuple

        mock_model_adapter.execute_and_log_metrics.side_effect = default_side_effect
        mock.return_value = mock_model_adapter
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
        show_raw_output=True,
        show_vibe=True,
        warn_no_output=True,
        model_name="claude-3.7-sonnet",
        show_kubectl=False,
        show_metrics=MetricsDisplayMode.ALL,
    )


@pytest.fixture
def mock_memory() -> Generator[tuple[MagicMock, MagicMock], None, None]:
    """Mock memory functions to avoid actual LLM API calls.

    Returns two mocks:
    1. mock_update_memory: The patch for vibectl.execution.vibe.update_memory
    2. mock_memory_update: The patch for vibectl.memory.update_memory

    This prevents actual API calls to LLMs during tests, which would:
    - Add cost for each test run
    - Make tests flaky due to API dependencies
    - Significantly slow down test execution

    This simulates the actual call chain where command_handler.py imports and calls
    the function implemented in memory.py. Tests can verify calls at either level.
    """
    with (
        patch("vibectl.execution.vibe.update_memory") as mock_update_memory,
        patch("vibectl.memory.update_memory") as mock_memory_update,
        patch("vibectl.execution.vibe.get_memory") as mock_get_memory,
    ):
        # Set default return values
        mock_get_memory.return_value = "Test memory context"

        # Configure both mocks to return proper LLMMetrics objects
        def update_memory_side_effect(*args: Any, **kwargs: Any) -> LLMMetrics:
            from vibectl.types import LLMMetrics

            return LLMMetrics(
                token_input=0,
                token_output=0,
                latency_ms=0.0,  # Ensure this is a float, not a mock
                total_processing_duration_ms=0.0,
            )

        # Make sure the mocks are set up as AsyncMock since update_memory is async
        mock_update_memory.return_value = LLMMetrics(
            token_input=0,
            token_output=0,
            latency_ms=0.0,
            total_processing_duration_ms=0.0,
        )
        mock_memory_update.return_value = LLMMetrics(
            token_input=0,
            token_output=0,
            latency_ms=0.0,
            total_processing_duration_ms=0.0,
        )

        yield (mock_update_memory, mock_memory_update)


@pytest.fixture
def mock_console_for_test() -> Generator[MagicMock, None, None]:
    """Fixture for mocking console_manager specifically for these tests."""
    with patch("vibectl.execution.vibe.console_manager") as mock:
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

    async def handle_output_side_effect(
        output_result: Result,
        output_flags: OutputFlags,
        summary_prompt_func: Any,
        command: str | None = None,
        **kwargs: Any,
    ) -> Result:
        """Side effect that preserves memory updates and returns result."""
        # Only call update_memory if command is provided and output is Success
        if command and isinstance(output_result, Success) and output_result.data:
            from vibectl.execution.vibe import update_memory

            # Assume vibe output generation happens somewhere and mock it
            mock_vibe_output = f"Vibe summary for {command}"
            await update_memory(command, output_result.data, mock_vibe_output)
        return output_result

    with patch("vibectl.execution.vibe.handle_command_output") as mock:
        mock.side_effect = handle_output_side_effect
        yield mock


# Dummy summary prompt function that returns fragments
def get_test_summary_fragments(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Dummy summary prompt function for testing that returns fragments."""
    return PromptFragments(
        (
            SystemFragments([Fragment("System fragment with {output}")]),
            UserFragments([Fragment("User fragment with {output}")]),
        )
    )


@pytest.mark.asyncio
@patch("vibectl.execution.vibe._get_llm_plan")
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
        patch("vibectl.execution.vibe._execute_command") as mock_execute_cmd,
        patch("vibectl.execution.vibe.click.prompt") as mock_click_prompt,
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
@patch("vibectl.execution.vibe._get_llm_plan")
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
        patch("vibectl.execution.vibe._execute_command") as mock_execute_cmd,
        patch("vibectl.execution.vibe.click.prompt") as mock_click_prompt,
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
@patch("vibectl.execution.vibe._get_llm_plan")
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
    with patch("vibectl.execution.vibe._execute_command") as mock_execute_cmd:
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
            llm_metrics_accumulator=ANY,  # Accept any LLMMetricsAccumulator instance
        )

    # Verify result
    assert isinstance(result, Success)
    assert 'pod "bypass-pod" deleted' in result.data if result.data else False

    # Verify memory update and handle_output calls
    mock_update_memory, _ = mock_memory
    assert mock_update_memory.call_count == 2
    mock_handle_output.assert_called_once()


@pytest.mark.asyncio
@patch("vibectl.execution.vibe._get_llm_plan")
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
    with patch("vibectl.execution.vibe._execute_command") as mock_execute_cmd:
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
            llm_metrics_accumulator=ANY,  # Accept any LLMMetricsAccumulator instance
        )

    # Verify result
    assert isinstance(result, Success)
    assert "pod data..." in result.data if result.data else False

    # Verify memory update and handle_output calls
    mock_update_memory, _ = mock_memory
    assert mock_update_memory.call_count == 2
    mock_handle_output.assert_called_once()


@patch("vibectl.execution.vibe.set_memory")
@patch("vibectl.execution.vibe.get_memory")
@patch("vibectl.execution.vibe.console_manager")
@pytest.mark.asyncio
async def test_vibe_delete_confirmation_memory_option(
    mock_console: MagicMock,
    mock_vibe_get_memory: MagicMock,
    mock_vibe_set_memory: MagicMock,
    mock_llm: MagicMock,
    mock_run_kubectl: MagicMock,
    prevent_exit: MagicMock,
    standard_output_flags: OutputFlags,
    mock_memory: tuple[MagicMock, MagicMock],
    mock_handle_output: MagicMock,
) -> None:
    """Test the 'm' (memory) option during command confirmation."""
    command_action = CommandAction(
        action_type=ActionType.COMMAND,
        commands=["pod", "nginx-mem"],
    )
    plan_response_data = LLMPlannerResponse(action=command_action)

    # Configure the side_effect for the mock LLM adapter's execute_and_log_metrics
    # This is the adapter instance returned by the mock_llm fixture
    llm_adapter_mock = mock_llm.return_value

    async def specific_plan_side_effect(
        *args: Any, **kwargs: Any
    ) -> tuple[str, LLMMetrics]:
        return (
            plan_response_data.model_dump_json(),
            LLMMetrics(latency_ms=100),
        )

    llm_adapter_mock.execute_and_log_metrics.side_effect = specific_plan_side_effect

    mock_vibe_get_memory.return_value = "Memory content for test"

    with (
        patch("vibectl.execution.vibe._execute_command") as mock_execute_cmd,
        patch("vibectl.execution.vibe.click.prompt") as mock_click_prompt,
    ):
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

        assert mock_click_prompt.call_count == 2
        assert mock_vibe_get_memory.call_count == 2
        mock_execute_cmd.assert_called_once()

        # Verify memory content was printed (check console mock)
        mock_console.safe_print.assert_called_once()
        # Verify the command *was* executed after 'y'
        mock_execute_cmd.assert_called_once_with(
            "delete", ["pod", "nginx-mem"], None, allowed_exit_codes=(0,)
        )

        assert isinstance(result, Success)
        assert result.data is not None
        assert 'pod "nginx-mem" deleted' in result.data

        mock_update_memory_vibe, _ = mock_memory
        assert mock_update_memory_vibe.call_count == 2
        mock_handle_output.assert_called_once()


@patch("vibectl.execution.vibe.console_manager")
@patch("vibectl.execution.vibe.get_memory")
@patch("vibectl.execution.vibe.set_memory")
@pytest.mark.asyncio
async def test_vibe_delete_confirmation_no_but_fuzzy_update_error(
    mock_set_memory: MagicMock,
    mock_get_memory: MagicMock,
    mock_console: MagicMock,
    mock_llm: MagicMock,
    mock_run_kubectl: MagicMock,
    prevent_exit: MagicMock,
    standard_output_flags: OutputFlags,
    mock_memory: tuple[MagicMock, MagicMock],
    mock_handle_output: MagicMock,
) -> None:
    """Test 'no but' confirmation where the fuzzy memory update LLM call fails."""
    command_action = CommandAction(
        action_type=ActionType.COMMAND,
        commands=["pod", "nginx"],
    )
    plan_response_data = LLMPlannerResponse(action=command_action)

    # mock_llm.return_value is the mocked adapter instance
    mock_llm.return_value.execute_and_log_metrics.side_effect = [
        (  # First call: LLM planning for the delete command
            plan_response_data.model_dump_json(),
            LLMMetrics(latency_ms=100),  # Dummy metrics
        ),
        # Second call: Fuzzy memory update attempt, which fails in this test
        Exception("LLM API error during fuzzy update"),
    ]

    with (
        patch("vibectl.execution.vibe._execute_command") as mock_execute_cmd,
        patch("vibectl.execution.vibe.click.prompt") as mock_click_prompt,
    ):
        # Simulate user choosing 'b' (no but)
        mock_click_prompt.return_value = "b"

        result = await handle_vibe_request(
            request="delete nginx pod",
            command="delete",
            plan_prompt_func=plan_vibe_fragments,
            summary_prompt_func=get_test_summary_fragments,
            output_flags=standard_output_flags,
            yes=False,
        )

    # click.prompt is called for main confirmation and then for fuzzy input.
    assert mock_click_prompt.call_count == 2
    mock_execute_cmd.assert_not_called()

    assert isinstance(result, Error)
    assert "Error updating memory: LLM API error during fuzzy update" in str(
        result.error
    )
    mock_handle_output.assert_not_called()


@patch("vibectl.execution.vibe.console_manager")
@patch("vibectl.execution.vibe.get_memory")
@patch("vibectl.execution.vibe.set_memory")
@pytest.mark.asyncio
async def test_vibe_delete_confirmation_yes_and_fuzzy_update_success(
    mock_set_memory: MagicMock,
    mock_get_memory: MagicMock,
    mock_console: MagicMock,
    mock_llm: MagicMock,
    mock_run_kubectl: MagicMock,
    prevent_exit: MagicMock,
    standard_output_flags: OutputFlags,
    mock_memory: tuple[MagicMock, MagicMock],
    mock_handle_output: MagicMock,
) -> None:
    """Test 'yes and' confirmation where the fuzzy memory update LLM call succeeds."""
    command_action = CommandAction(
        action_type=ActionType.COMMAND,
        commands=["pod", "nginx"],
    )
    plan_response_data = LLMPlannerResponse(action=command_action)

    feedback_action_for_fuzzy_update = FeedbackAction(
        action_type=ActionType.FEEDBACK,
        message="Memory context noted via fuzzy update.",
    )
    fuzzy_update_llm_response_json = LLMPlannerResponse(
        action=feedback_action_for_fuzzy_update
    ).model_dump_json()

    mock_llm.return_value.execute_and_log_metrics.side_effect = [
        (  # First call: LLM planning for the delete command
            plan_response_data.model_dump_json(),
            LLMMetrics(latency_ms=100),
        ),
        (  # Second call: Successful fuzzy memory update
            fuzzy_update_llm_response_json,
            LLMMetrics(latency_ms=50),
        ),
    ]

    with (
        patch("vibectl.execution.vibe._execute_command") as mock_execute_cmd,
        patch("vibectl.execution.vibe.click.prompt") as mock_click_prompt,
    ):
        # Simulate user choosing 'a' (yes and) and providing fuzzy input
        mock_click_prompt.side_effect = ["a", "my fuzzy memory input"]
        mock_execute_cmd.return_value = Success(data='pod "nginx" deleted')

        result = await handle_vibe_request(
            request="delete nginx pod",
            command="delete",
            plan_prompt_func=plan_vibe_fragments,
            summary_prompt_func=get_test_summary_fragments,
            output_flags=standard_output_flags,
            yes=False,
        )

    assert mock_click_prompt.call_count == 2
    mock_execute_cmd.assert_called_once_with(
        "delete", ["pod", "nginx"], None, allowed_exit_codes=(0,)
    )

    assert isinstance(result, Success)
    assert result.data == 'pod "nginx" deleted'

    # handle_command_output is called by _confirm_and_execute_plan
    # after successful execution
    mock_handle_output.assert_called_once_with(
        mock_execute_cmd.return_value,
        standard_output_flags,
        get_test_summary_fragments,
        command="delete",
        llm_metrics_accumulator=ANY,  # Accept any LLMMetricsAccumulator instance
    )


@patch("vibectl.execution.vibe.console_manager")
@patch("vibectl.execution.vibe.get_memory")
@patch("vibectl.execution.vibe.set_memory")
@pytest.mark.asyncio
async def test_vibe_delete_confirmation_yes_and_fuzzy_update_error(
    mock_set_memory: MagicMock,
    mock_get_memory: MagicMock,
    mock_console: MagicMock,
    mock_llm: MagicMock,
    mock_run_kubectl: MagicMock,
    prevent_exit: MagicMock,
    standard_output_flags: OutputFlags,
    mock_memory: tuple[MagicMock, MagicMock],
    mock_handle_output: MagicMock,
) -> None:
    """Test 'yes and' confirmation where the fuzzy memory update LLM call fails."""
    command_action = CommandAction(
        action_type=ActionType.COMMAND,
        commands=["pod", "nginx"],
    )
    plan_response_data = LLMPlannerResponse(action=command_action)

    mock_llm.return_value.execute_and_log_metrics.side_effect = [
        (  # First call: LLM planning for the delete command
            plan_response_data.model_dump_json(),
            LLMMetrics(latency_ms=100),
        ),
        # Second call: Fuzzy memory update attempt, which fails
        Exception("LLM API error during fuzzy update for yes and"),
    ]

    with (
        patch("vibectl.execution.vibe._execute_command") as mock_execute_cmd,
        patch("vibectl.execution.vibe.click.prompt") as mock_click_prompt,
    ):
        # Simulate user choosing 'a' (yes and) and providing fuzzy input
        mock_click_prompt.side_effect = ["a", "my fuzzy memory input for error case"]

        result = await handle_vibe_request(
            request="delete nginx pod",
            command="delete",
            plan_prompt_func=plan_vibe_fragments,
            summary_prompt_func=get_test_summary_fragments,
            output_flags=standard_output_flags,
            yes=False,
        )

    assert mock_click_prompt.call_count == 2
    # _execute_command should NOT be called because fuzzy update failed before execution
    mock_execute_cmd.assert_not_called()

    assert isinstance(result, Error)
    assert (
        "Error updating memory: LLM API error during fuzzy update for yes and"
        in str(result.error)
    )
    mock_handle_output.assert_not_called()
