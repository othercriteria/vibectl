"""Tests for recovery suggestions integration with memory.

This test file verifies that recovery suggestions from failed commands
are properly integrated into memory. This is important for vibectl auto mode,
where recovery suggestions from one command should be available for subsequent commands.

The tests verify:
1. That update_memory is called when recovery suggestions are available
2. That the recovery suggestions are passed to update_memory
3. That this correctly happens when used in auto mode
"""

from collections.abc import Generator
from unittest.mock import Mock, patch
import json

import pytest

from vibectl.command_handler import handle_vibe_request
from vibectl.model_adapter import LLMModelAdapter
from vibectl.types import Error, Success, ActionType


@pytest.fixture
def clean_memory() -> Generator[None, None, None]:
    """Fixture to ensure clean memory state for tests."""
    from vibectl.memory import get_memory, set_memory

    # Save current memory
    original_memory = get_memory()

    # Clear memory for tests
    set_memory("")

    yield

    # Restore original memory
    set_memory(original_memory)


@patch.object(LLMModelAdapter, "get_model")
@patch.object(LLMModelAdapter, "execute")
@patch("vibectl.command_handler._process_and_execute_kubectl_command")
@patch("vibectl.command_handler.update_memory")
def test_recovery_suggestions_not_in_memory(
    mock_update_memory: Mock,
    mock_execute: Mock,
    mock_llm_execute: Mock,
    mock_get_model: Mock,
) -> None:
    """Test that recovery suggestions should be added to memory."""
    # Setup
    mock_model = Mock()
    mock_get_model.return_value = mock_model
    # Update planning step to return JSON
    expected_plan = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["pods"],
        "explanation": "Get pods",
    }
    mock_llm_execute.side_effect = [
        json.dumps(expected_plan),
        "Error occurred: Pod not found",  # Recovery suggestions
    ]
    mock_execute.return_value = Error(error="Pod not found", exception=None)

    # Execute command
    output_flags = Mock(
        model_name="test-model",
        show_vibe=True,
        show_raw=True,
        show_kubectl=True,
    )
    result = handle_vibe_request(
        request="show the pods",
        command="vibe",
        plan_prompt="plan {request}",
        summary_prompt_func=lambda: "summarize {output}",
        output_flags=output_flags,
    )

    # Verify results and memory update
    assert isinstance(result, Error)
    assert result.recovery_suggestions == "Error occurred: Pod not found"
    mock_update_memory.assert_called()  # Verifying update_memory was called


@patch.object(LLMModelAdapter, "get_model")
@patch.object(LLMModelAdapter, "execute")
@patch("vibectl.command_handler._process_and_execute_kubectl_command")
@patch("vibectl.command_handler.update_memory")
def test_recovery_suggestions_should_update_memory(
    mock_update_memory: Mock,
    mock_execute: Mock,
    mock_llm_execute: Mock,
    mock_get_model: Mock,
) -> None:
    """Test that memory should be updated with recovery suggestions."""
    # Setup
    mock_model = Mock()
    mock_get_model.return_value = mock_model
    # Update planning step to return JSON
    expected_plan = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["pods"],
        "explanation": "Get pods",
    }
    mock_llm_execute.side_effect = [
        json.dumps(expected_plan),
        "Error occurred: Pod not found",  # Recovery suggestions
    ]
    mock_execute.return_value = Error(error="Pod not found", exception=None)

    # Execute command
    output_flags = Mock(
        model_name="test-model",
        show_vibe=True,
        show_raw=True,
        show_kubectl=True,
    )
    result = handle_vibe_request(
        request="show the pods",
        command="vibe",
        plan_prompt="plan {request}",
        summary_prompt_func=lambda: "summarize {output}",
        output_flags=output_flags,
    )

    # Verify recovery suggestions and memory updates
    assert isinstance(result, Error)
    assert result.recovery_suggestions == "Error occurred: Pod not found"
    assert mock_update_memory.call_count >= 1  # Verify update_memory was called

    # Verify recovery suggestions content in memory
    recovery_in_memory = False
    for call in mock_update_memory.call_args_list:
        args, kwargs = call
        if (
            "vibe_output" in kwargs
            and "Error occurred: Pod not found" in kwargs["vibe_output"]
        ):
            recovery_in_memory = True
            break
    assert recovery_in_memory  # Verify recovery suggestions are in memory update


@patch.object(LLMModelAdapter, "get_model")
@patch.object(LLMModelAdapter, "execute")
@patch("vibectl.command_handler._process_and_execute_kubectl_command")
@patch("vibectl.command_handler.update_memory")
def test_recovery_suggestions_in_auto_mode(
    mock_update_memory: Mock,
    mock_execute: Mock,
    mock_llm_execute: Mock,
    mock_get_model: Mock,
) -> None:
    """Test recovery suggestions in auto mode should update memory."""
    # Setup
    mock_model = Mock()
    mock_get_model.return_value = mock_model
    # Update planning step to return JSON
    expected_plan = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["pods"],
        "explanation": "Get pods",
    }
    mock_llm_execute.side_effect = [
        json.dumps(expected_plan),  # First command planning
        "Error occurred: Pod not found",  # Recovery suggestions
        "get pods --namespace default",  # Second command planning (remains string)
    ]
    mock_execute.side_effect = [
        Error(error="Pod not found", exception=None),
        Success(message="Success", data="No pods found in default namespace"),
    ]

    # Execute first command (fails)
    output_flags = Mock(
        model_name="test-model",
        show_vibe=True,
        show_raw=True,
        show_kubectl=True,
    )
    result1 = handle_vibe_request(
        request="show the pods",
        command="vibe",
        plan_prompt="plan {request}",
        summary_prompt_func=lambda: "summarize {output}",
        output_flags=output_flags,
    )

    # Verify recovery suggestions
    assert isinstance(result1, Error)
    assert result1.recovery_suggestions == "Error occurred: Pod not found"

    # Verify memory updated with recovery suggestions
    assert mock_update_memory.call_count >= 1  # Verify update_memory was called

    # Check recovery suggestions content in memory updates
    recovery_in_memory = False
    for call in mock_update_memory.call_args_list:
        args, kwargs = call
        if (
            "vibe_output" in kwargs
            and "Error occurred: Pod not found" in kwargs["vibe_output"]
        ):
            recovery_in_memory = True
            break
    assert recovery_in_memory  # Verify recovery suggestions are in memory
