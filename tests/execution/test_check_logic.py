"""
Tests for the 'vibectl check' execution logic.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vibectl.execution.check import run_check_command
from vibectl.schema import (
    CommandAction,
    DoneAction,
    ErrorAction,
    FeedbackAction,
    LLMPlannerResponse,
    ThoughtAction,
    WaitAction,
)
from vibectl.types import Error, OutputFlags, PredicateCheckExitCode, Result, Success


@pytest.mark.asyncio
async def test_run_check_command_done_action_immediate_success() -> None:
    """
    Tests run_check_command when the LLM returns a DoneAction immediately,
    indicating the predicate is true.
    """
    mock_output_flags = OutputFlags(
        show_vibe=False,
        show_kubectl=False,
        show_raw=False,
        model_name="test-model",
        warn_no_output=False,
        show_metrics=False,
    )
    mock_config = MagicMock()
    mock_config.get_typed.return_value = 10  # check_max_iterations

    mock_done_action = DoneAction(
        action_type="DONE",
        exit_code=PredicateCheckExitCode.TRUE.value,
        explanation="Predicate is true.",
    )
    mock_llm_response = LLMPlannerResponse(action=mock_done_action)

    with (
        patch("vibectl.execution.check.Config", return_value=mock_config),
        patch("vibectl.execution.check.get_memory", return_value="Initial memory"),
        patch("vibectl.execution.check.update_memory") as mock_update_memory,
        patch(
            "vibectl.execution.check._get_check_llm_plan",
            return_value=Success(data=mock_llm_response, metrics=None),
        ),
    ):
        result: Result = await run_check_command(
            predicate="Is the sky blue?",
            output_flags=mock_output_flags,
        )

    assert isinstance(result, Success)
    assert result.original_exit_code == PredicateCheckExitCode.TRUE.value
    assert result.message == "Predicate is true."
    assert result.continue_execution is False
    mock_update_memory.assert_called_once()


@pytest.mark.asyncio
async def test_run_check_command_done_action_immediate_false() -> None:
    """
    Tests run_check_command when the LLM returns a DoneAction immediately,
    indicating the predicate is false.
    """
    mock_output_flags = OutputFlags(
        show_vibe=False,
        show_kubectl=False,
        show_raw=False,
        model_name="test-model",
        warn_no_output=False,
        show_metrics=False,
    )
    mock_config = MagicMock()
    mock_config.get_typed.return_value = 10  # check_max_iterations

    mock_done_action = DoneAction(
        action_type="DONE",
        exit_code=PredicateCheckExitCode.FALSE.value,
        explanation="Predicate is false.",
    )
    mock_llm_response = LLMPlannerResponse(action=mock_done_action)

    with (
        patch("vibectl.execution.check.Config", return_value=mock_config),
        patch("vibectl.execution.check.get_memory", return_value="Initial memory"),
        patch("vibectl.execution.check.update_memory") as mock_update_memory,
        patch(
            "vibectl.execution.check._get_check_llm_plan",
            return_value=Success(data=mock_llm_response, metrics=None),
        ),
    ):
        result: Result = await run_check_command(
            predicate="Are there any running pods?",
            output_flags=mock_output_flags,
        )

    assert isinstance(result, Success)
    assert result.original_exit_code == PredicateCheckExitCode.FALSE.value
    assert result.message == "Predicate is false."
    assert result.continue_execution is False
    mock_update_memory.assert_called_once()


@pytest.mark.asyncio
async def test_run_check_command_done_action_cannot_determine() -> None:
    """
    Tests run_check_command when the LLM returns a DoneAction immediately,
    indicating the predicate cannot be determined.
    """
    mock_output_flags = OutputFlags(
        show_vibe=False,
        show_kubectl=False,
        show_raw=False,
        model_name="test-model",
        warn_no_output=False,
        show_metrics=False,
    )
    mock_config = MagicMock()
    mock_config.get_typed.return_value = 10  # check_max_iterations

    mock_done_action = DoneAction(
        action_type="DONE",
        exit_code=PredicateCheckExitCode.CANNOT_DETERMINE.value,
        explanation="Cannot determine predicate truthiness.",
    )
    mock_llm_response = LLMPlannerResponse(action=mock_done_action)

    with (
        patch("vibectl.execution.check.Config", return_value=mock_config),
        patch("vibectl.execution.check.get_memory", return_value="Initial memory"),
        patch("vibectl.execution.check.update_memory") as mock_update_memory,
        patch(
            "vibectl.execution.check._get_check_llm_plan",
            return_value=Success(data=mock_llm_response, metrics=None),
        ),
    ):
        result: Result = await run_check_command(
            predicate="Is this a trick question?",
            output_flags=mock_output_flags,
        )

    assert isinstance(result, Success)
    assert result.original_exit_code == PredicateCheckExitCode.CANNOT_DETERMINE.value
    assert result.message == "Cannot determine predicate truthiness."
    assert result.continue_execution is False
    mock_update_memory.assert_called_once()


@pytest.mark.asyncio
async def test_run_check_command_thought_then_done() -> None:
    """
    Tests run_check_command when LLM returns a ThoughtAction followed by a DoneAction.
    """
    mock_output_flags = OutputFlags(
        show_vibe=False,
        show_kubectl=False,
        show_raw=False,
        model_name="test-model",
        warn_no_output=False,
        show_metrics=False,
    )
    mock_config = MagicMock()
    mock_config.get_typed.return_value = 10  # check_max_iterations

    mock_thought_action = ThoughtAction(
        action_type="THOUGHT", text="Let me think about this."
    )
    mock_done_action = DoneAction(
        action_type="DONE",
        exit_code=PredicateCheckExitCode.TRUE.value,
        explanation="Okay, I've thought, and it's true.",
    )
    mock_llm_response_thought = LLMPlannerResponse(action=mock_thought_action)
    mock_llm_response_done = LLMPlannerResponse(action=mock_done_action)

    # _get_check_llm_plan will be called twice
    mock_get_plan = MagicMock(
        side_effect=[
            Success(data=mock_llm_response_thought, metrics=None),
            Success(data=mock_llm_response_done, metrics=None),
        ]
    )

    with (
        patch("vibectl.execution.check.Config", return_value=mock_config),
        patch(
            "vibectl.execution.check.get_memory", return_value="Initial memory"
        ) as mock_get_memory,
        patch("vibectl.execution.check.update_memory") as mock_update_memory,
        patch("vibectl.execution.check._get_check_llm_plan", new=mock_get_plan),
    ):
        result: Result = await run_check_command(
            predicate="Is thinking required?",
            output_flags=mock_output_flags,
        )

    assert isinstance(result, Success)
    assert result.original_exit_code == PredicateCheckExitCode.TRUE.value
    assert result.message == "Okay, I've thought, and it's true."
    assert result.continue_execution is False
    assert mock_get_memory.call_count == 2
    assert mock_update_memory.call_count == 2
    assert mock_get_plan.call_count == 2


@pytest.mark.asyncio
async def test_run_check_command_command_then_done() -> None:
    """
    Tests run_check_command with a CommandAction followed by a DoneAction.
    Ensures read-only command execution and memory updates.
    """
    mock_output_flags = OutputFlags(
        show_vibe=False,
        show_kubectl=False,
        show_raw=False,
        model_name="test-model",
        warn_no_output=False,
        show_metrics=False,
    )
    mock_config = MagicMock()
    mock_config.get_typed.return_value = 10  # check_max_iterations

    mock_command_action = CommandAction(
        action_type="COMMAND",
        commands=["kubectl", "get", "pods"],
        explanation="Checking pods...",
        allowed_exit_codes=[0],
    )
    mock_done_action = DoneAction(
        action_type="DONE",
        exit_code=PredicateCheckExitCode.TRUE.value,
        explanation="Pods are present.",
    )
    mock_llm_response_command = LLMPlannerResponse(action=mock_command_action)
    mock_llm_response_done = LLMPlannerResponse(action=mock_done_action)

    mock_get_plan = MagicMock(
        side_effect=[
            Success(data=mock_llm_response_command, metrics=None),
            Success(data=mock_llm_response_done, metrics=None),
        ]
    )

    mock_kubectl_result = Success(data="pod-a active\npod-b active", metrics=None)

    with (
        patch("vibectl.execution.check.Config", return_value=mock_config),
        patch(
            "vibectl.execution.check.get_memory", return_value="Memory content"
        ) as mock_get_memory,
        patch("vibectl.execution.check.update_memory") as mock_update_memory,
        patch("vibectl.execution.check._get_check_llm_plan", new=mock_get_plan),
        patch(
            "vibectl.execution.check.is_kubectl_command_read_only", return_value=True
        ) as mock_is_read_only,
        patch(
            "vibectl.execution.check.run_kubectl", return_value=mock_kubectl_result
        ) as mock_run_kubectl,
    ):
        result: Result = await run_check_command(
            predicate="Are pods running?",
            output_flags=mock_output_flags,
        )

    assert isinstance(result, Success)
    assert result.original_exit_code == PredicateCheckExitCode.TRUE.value
    assert result.message == "Pods are present."
    assert mock_get_memory.call_count == 2
    assert mock_update_memory.call_count == 2
    mock_is_read_only.assert_called_once_with(["kubectl", "get", "pods"])
    mock_run_kubectl.assert_called_once_with(
        ["kubectl", "get", "pods"], allowed_exit_codes=(0,), config=mock_config
    )
    assert mock_get_plan.call_count == 2


@pytest.mark.asyncio
async def test_run_check_command_non_read_only_command_error() -> None:
    """
    Tests that an error is returned if the LLM plans a non-read-only command.
    """
    mock_output_flags = OutputFlags(
        show_vibe=False,
        show_kubectl=False,
        show_raw=False,
        model_name="test-model",
        warn_no_output=False,
        show_metrics=False,
    )
    mock_config = MagicMock()
    mock_config.get_typed.return_value = 10  # check_max_iterations

    mock_command_action = CommandAction(
        action_type="COMMAND",
        commands=["kubectl", "delete", "pod", "my-pod"],
        explanation="Attempting to delete a pod.",
        allowed_exit_codes=[0],
    )
    mock_llm_response_command = LLMPlannerResponse(action=mock_command_action)

    mock_get_plan = MagicMock(
        return_value=Success(data=mock_llm_response_command, metrics=None)
    )

    with (
        patch("vibectl.execution.check.Config", return_value=mock_config),
        patch("vibectl.execution.check.get_memory", return_value="Memory content"),
        patch("vibectl.execution.check.update_memory") as mock_update_memory,
        patch("vibectl.execution.check._get_check_llm_plan", new=mock_get_plan),
        patch(
            "vibectl.execution.check.is_kubectl_command_read_only", return_value=False
        ) as mock_is_read_only,
        patch("vibectl.execution.check.run_kubectl") as mock_run_kubectl,
    ):
        result: Result = await run_check_command(
            predicate="Is the cluster empty?",
            output_flags=mock_output_flags,
        )

    assert isinstance(result, Error)
    assert "LLM planned a non-read-only command" in result.error
    assert result.original_exit_code == PredicateCheckExitCode.CANNOT_DETERMINE.value
    mock_is_read_only.assert_called_once_with(["kubectl", "delete", "pod", "my-pod"])
    mock_run_kubectl.assert_not_called()
    mock_update_memory.assert_called_once()  # Memory updated with the error
    assert mock_get_plan.call_count == 1


@pytest.mark.asyncio
async def test_run_check_command_wait_then_done() -> None:
    """
    Tests run_check_command with a WaitAction followed by a DoneAction.
    """
    mock_output_flags = OutputFlags(
        show_vibe=False,
        show_kubectl=False,
        show_raw=False,
        model_name="test-model",
        warn_no_output=False,
        show_metrics=False,
    )
    mock_config = MagicMock()
    mock_config.get_typed.return_value = 10  # check_max_iterations

    mock_wait_action = WaitAction(
        action_type="WAIT", duration_seconds=0
    )  # Use a very short wait for testing
    mock_done_action = DoneAction(
        action_type="DONE",
        exit_code=PredicateCheckExitCode.TRUE.value,
        explanation="Waited and now it's true.",
    )
    mock_llm_response_wait = LLMPlannerResponse(action=mock_wait_action)
    mock_llm_response_done = LLMPlannerResponse(action=mock_done_action)

    mock_get_plan = MagicMock(
        side_effect=[
            Success(data=mock_llm_response_wait, metrics=None),
            Success(data=mock_llm_response_done, metrics=None),
        ]
    )

    with (
        patch("vibectl.execution.check.Config", return_value=mock_config),
        patch(
            "vibectl.execution.check.get_memory", return_value="Memory content"
        ) as mock_get_memory,
        patch("vibectl.execution.check.update_memory") as mock_update_memory,
        patch("vibectl.execution.check._get_check_llm_plan", new=mock_get_plan),
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_async_sleep,
    ):
        result: Result = await run_check_command(
            predicate="Do I need to wait?",
            output_flags=mock_output_flags,
        )

    assert isinstance(result, Success)
    assert result.original_exit_code == PredicateCheckExitCode.TRUE.value
    assert result.message == "Waited and now it's true."
    assert mock_get_memory.call_count == 2
    assert mock_update_memory.call_count == 2
    mock_async_sleep.assert_called_once_with(0)
    assert mock_get_plan.call_count == 2


@pytest.mark.asyncio
async def test_run_check_command_error_action_then_done() -> None:
    """
    Tests run_check_command with an ErrorAction from the LLM, followed by a DoneAction.
    """
    mock_output_flags = OutputFlags(
        show_vibe=False,
        show_kubectl=False,
        show_raw=False,
        model_name="test-model",
        warn_no_output=False,
        show_metrics=False,
    )
    mock_config = MagicMock()
    mock_config.get_typed.return_value = 10  # check_max_iterations

    mock_error_action = ErrorAction(action_type="ERROR", message="Something seems off.")
    mock_done_action = DoneAction(
        action_type="DONE",
        exit_code=PredicateCheckExitCode.TRUE.value,
        explanation="Figured it out, it's true.",
    )
    mock_llm_response_error = LLMPlannerResponse(action=mock_error_action)
    mock_llm_response_done = LLMPlannerResponse(action=mock_done_action)

    mock_get_plan = MagicMock(
        side_effect=[
            Success(data=mock_llm_response_error, metrics=None),
            Success(data=mock_llm_response_done, metrics=None),
        ]
    )

    with (
        patch("vibectl.execution.check.Config", return_value=mock_config),
        patch(
            "vibectl.execution.check.get_memory", return_value="Memory content"
        ) as mock_get_memory,
        patch("vibectl.execution.check.update_memory") as mock_update_memory,
        patch("vibectl.execution.check._get_check_llm_plan", new=mock_get_plan),
    ):
        result: Result = await run_check_command(
            predicate="Is something wrong?",
            output_flags=mock_output_flags,
        )

    assert isinstance(result, Success)
    assert result.original_exit_code == PredicateCheckExitCode.TRUE.value
    assert result.message == "Figured it out, it's true."
    assert mock_get_memory.call_count == 2
    assert mock_update_memory.call_count == 2
    assert mock_get_plan.call_count == 2


@pytest.mark.asyncio
async def test_run_check_command_feedback_action_then_done() -> None:
    """
    Tests run_check_command with FeedbackAction from the LLM, followed by DoneAction.
    """
    mock_output_flags = OutputFlags(
        show_vibe=False,
        show_kubectl=False,
        show_raw=False,
        model_name="test-model",
        warn_no_output=False,
        show_metrics=False,
    )
    mock_config = MagicMock()
    mock_config.get_typed.return_value = 10  # check_max_iterations

    mock_feedback_action = FeedbackAction(
        action_type="FEEDBACK", message="Here is some feedback."
    )
    mock_done_action = DoneAction(
        action_type="DONE",
        exit_code=PredicateCheckExitCode.TRUE.value,
        explanation="Considered feedback, it's true.",
    )
    mock_llm_response_feedback = LLMPlannerResponse(action=mock_feedback_action)
    mock_llm_response_done = LLMPlannerResponse(action=mock_done_action)

    mock_get_plan = MagicMock(
        side_effect=[
            Success(data=mock_llm_response_feedback, metrics=None),
            Success(data=mock_llm_response_done, metrics=None),
        ]
    )

    with (
        patch("vibectl.execution.check.Config", return_value=mock_config),
        patch(
            "vibectl.execution.check.get_memory", return_value="Memory content"
        ) as mock_get_memory,
        patch("vibectl.execution.check.update_memory") as mock_update_memory,
        patch("vibectl.execution.check._get_check_llm_plan", new=mock_get_plan),
    ):
        result: Result = await run_check_command(
            predicate="Need feedback?",
            output_flags=mock_output_flags,
        )

    assert isinstance(result, Success)
    assert result.original_exit_code == PredicateCheckExitCode.TRUE.value
    assert result.message == "Considered feedback, it's true."
    assert mock_get_memory.call_count == 2
    assert mock_update_memory.call_count == 2
    assert mock_get_plan.call_count == 2


@pytest.mark.asyncio
async def test_run_check_command_max_iterations_reached() -> None:
    """
    Tests that run_check_command terminates with an error if max_iterations is reached.
    """
    max_iterations = 3
    mock_output_flags = OutputFlags(
        show_vibe=False,
        show_kubectl=False,
        show_raw=False,
        model_name="test-model",
        warn_no_output=False,
        show_metrics=False,
    )
    mock_config = MagicMock()
    mock_config.get_typed.return_value = max_iterations

    mock_thought_action = ThoughtAction(action_type="THOUGHT", text="Still thinking...")
    mock_llm_response_thought = LLMPlannerResponse(action=mock_thought_action)

    # _get_check_llm_plan will be called max_iterations times
    mock_get_plan = MagicMock(
        return_value=Success(data=mock_llm_response_thought, metrics=None)
    )

    with (
        patch("vibectl.execution.check.Config", return_value=mock_config),
        patch(
            "vibectl.execution.check.get_memory", return_value="Initial memory"
        ) as mock_get_memory,
        patch("vibectl.execution.check.update_memory") as mock_update_memory,
        patch("vibectl.execution.check._get_check_llm_plan", new=mock_get_plan),
    ):
        result: Result = await run_check_command(
            predicate="Will this ever end?",
            output_flags=mock_output_flags,
        )

    assert isinstance(result, Error)
    assert (
        f"Cannot determine predicate within {max_iterations} iterations."
        in result.error
    )
    assert result.original_exit_code == PredicateCheckExitCode.CANNOT_DETERMINE.value
    assert mock_get_memory.call_count == max_iterations
    assert (
        mock_update_memory.call_count == max_iterations + 1
    )  # +1 for the final update after loop
    assert mock_get_plan.call_count == max_iterations


@pytest.mark.asyncio
async def test_run_check_command_llm_plan_error() -> None:
    """
    Tests run_check_command when _get_check_llm_plan returns an Error.
    """
    mock_output_flags = OutputFlags(
        show_vibe=False,
        show_kubectl=False,
        show_raw=False,
        model_name="test-model",
        warn_no_output=False,
        show_metrics=False,
    )
    mock_config = MagicMock()
    mock_config.get_typed.return_value = 10  # check_max_iterations

    llm_error = Error(
        "LLM connection failed",
        original_exit_code=PredicateCheckExitCode.CANNOT_DETERMINE.value,
    )

    with (
        patch("vibectl.execution.check.Config", return_value=mock_config),
        patch(
            "vibectl.execution.check.get_memory", return_value="Initial memory"
        ) as mock_get_memory,
        patch("vibectl.execution.check.update_memory") as mock_update_memory,
        patch(
            "vibectl.execution.check._get_check_llm_plan", return_value=llm_error
        ) as mock_get_plan,
    ):
        result: Result = await run_check_command(
            predicate="Will the LLM fail?",
            output_flags=mock_output_flags,
        )

    assert isinstance(result, Error)
    assert result.error == "LLM connection failed"
    assert result.original_exit_code == PredicateCheckExitCode.CANNOT_DETERMINE.value
    mock_get_memory.assert_called_once()
    mock_update_memory.assert_not_called()  # No updates if plan fails immediately
    mock_get_plan.assert_called_once()


@pytest.mark.asyncio
async def test_run_check_command_kubectl_error_then_done() -> None:
    """
    Tests run_check_command where a CommandAction leads to a kubectl error,
    followed by a successful DoneAction in the next iteration.
    """
    mock_output_flags = OutputFlags(
        show_vibe=False,
        show_kubectl=False,
        show_raw=False,
        model_name="test-model",
        warn_no_output=False,
        show_metrics=False,
    )
    mock_config = MagicMock()
    mock_config.get_typed.return_value = 10  # check_max_iterations

    mock_command_action = CommandAction(
        action_type="COMMAND",
        commands=["kubectl", "get", "nonexistent"],
        explanation="Trying to get a nonexistent resource.",
        allowed_exit_codes=[0],
    )
    mock_done_action = DoneAction(
        action_type="DONE",
        exit_code=PredicateCheckExitCode.FALSE.value,
        explanation="Could not find resource, so predicate is false.",
    )
    mock_llm_response_command = LLMPlannerResponse(action=mock_command_action)
    mock_llm_response_done = LLMPlannerResponse(action=mock_done_action)

    mock_get_plan = MagicMock(
        side_effect=[
            Success(data=mock_llm_response_command, metrics=None),
            Success(data=mock_llm_response_done, metrics=None),
        ]
    )

    mock_kubectl_error = Error(
        error="kubectl command failed", original_exit_code=1, metrics=None
    )

    with (
        patch("vibectl.execution.check.Config", return_value=mock_config),
        patch(
            "vibectl.execution.check.get_memory", return_value="Memory content"
        ) as mock_get_memory,
        patch("vibectl.execution.check.update_memory") as mock_update_memory,
        patch("vibectl.execution.check._get_check_llm_plan", new=mock_get_plan),
        patch(
            "vibectl.execution.check.is_kubectl_command_read_only", return_value=True
        ) as mock_is_read_only,
        patch(
            "vibectl.execution.check.run_kubectl", return_value=mock_kubectl_error
        ) as mock_run_kubectl,
    ):
        result: Result = await run_check_command(
            predicate="Does a nonexistent resource exist?",
            output_flags=mock_output_flags,
        )

    assert isinstance(
        result, Success
    )  # Overall success because it eventually got a DoneAction
    assert result.original_exit_code == PredicateCheckExitCode.FALSE.value
    assert result.message == "Could not find resource, so predicate is false."
    assert mock_get_memory.call_count == 2
    assert mock_update_memory.call_count == 2  # One for command error, one for done
    mock_is_read_only.assert_called_once_with(["kubectl", "get", "nonexistent"])
    mock_run_kubectl.assert_called_once_with(
        ["kubectl", "get", "nonexistent"], allowed_exit_codes=(0,), config=mock_config
    )
    assert mock_get_plan.call_count == 2
