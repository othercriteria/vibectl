"""Tests for recovery suggestions integration with memory.

This test file verifies that recovery suggestions from failed commands
are properly integrated into memory. This is important for vibectl auto mode,
where recovery suggestions from one command should be available for subsequent commands.

The tests verify:
1. That update_memory is called when recovery suggestions are available
2. That the recovery suggestions are passed to update_memory
3. That this correctly happens when used in auto mode
"""

import json
from collections.abc import Generator
from unittest.mock import MagicMock, Mock, patch

import pytest

from vibectl.command_handler import LLMCommandResponse, handle_vibe_request
from vibectl.types import ActionType, Error, OutputFlags


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


@pytest.fixture
def mock_execute() -> Generator[MagicMock, None, None]:
    """Mock vibectl.command_handler._execute_command."""
    with patch("vibectl.command_handler._execute_command") as mock:
        yield mock


@pytest.fixture
def mock_console() -> Generator[MagicMock, None, None]:
    """Mock vibectl.command_handler.console_manager."""
    with patch("vibectl.command_handler.console_manager") as mock:
        yield mock


@pytest.fixture
def mock_get_adapter() -> Generator[MagicMock, None, None]:
    """Mock vibectl.command_handler.get_model_adapter."""
    with patch("vibectl.command_handler.get_model_adapter") as mock_factory:
        mock_adapter_instance = MagicMock()
        mock_factory.return_value = mock_adapter_instance
        # Add a placeholder for execute, tests will configure it
        mock_adapter_instance.execute = MagicMock()
        yield mock_adapter_instance  # Yield the adapter instance mock


@pytest.fixture
def output_flags() -> OutputFlags:
    """Provide standard OutputFlags for recovery tests."""
    return OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
        show_kubectl=True,  # Ensure kubectl command is shown if generated
    )


@patch("vibectl.command_handler.update_memory")
def test_recovery_suggestions_not_in_memory(
    mock_update_memory: Mock,
    mock_get_adapter: MagicMock,
    mock_execute: MagicMock,
    mock_console: MagicMock,
    output_flags: OutputFlags,
) -> None:
    """Test that recovery suggestions are added to the Error result."""
    # Setup
    # Configure the mock adapter instance returned by the fixture
    mock_adapter_instance = mock_get_adapter.return_value
    # Planning step returns JSON via LLMModelAdapter.execute
    plan_response = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["get", "pods"],  # Corrected: Include verb
        "explanation": "Get pods",
    }
    expected_plan_json = json.dumps(plan_response)
    # LLM execute needs to return the plan first, then recovery suggestions
    recovery_suggestion_text = "Error occurred: Pod not found"
    # The second LLM call should return an ERROR action JSON with suggestions
    recovery_response_json = json.dumps(
        {
            "action_type": ActionType.ERROR.value,
            "error": "Failed to get pods",  # Optional: Can be more specific
            "explanation": recovery_suggestion_text,  # Suggestions go here
        }
    )

    mock_adapter_instance.execute.side_effect = [
        expected_plan_json,
        recovery_response_json,  # Return the JSON error response
    ]
    # _execute_command (kubectl) fails
    mock_execute.return_value = Error(error="Pod not found", exception=None)

    # Mock recovery prompt generation and memory interaction
    with (
        patch("vibectl.command_handler.recovery_prompt") as mock_recovery_prompt,
        patch("vibectl.memory.include_memory_in_prompt") as mock_include_memory,
        patch(
            "vibectl.command_handler.LLMCommandResponse.model_validate_json"
        ) as mock_validate_json,
    ):
        mock_recovery_prompt.return_value = "Recovery prompt content"
        mock_include_memory.side_effect = lambda p, **k: p  # Simple passthrough

        # Configure model_validate_json mock
        # First call (plan_response) should succeed
        # Second call (recovery_response_json) should return the ERROR action
        # This might need adjustment if the flow changes how parsing happens
        mock_validate_json.side_effect = [
            LLMCommandResponse(
                **plan_response
            ),  # Simulate successful validation of first call
            LLMCommandResponse(
                **json.loads(recovery_response_json)
            ),  # Simulate successful validation of second call
        ]

        # Execute command
        # Let the actual handle_command_output run to test recovery logic
        result = handle_vibe_request(
            request="show the pods",
            command="vibe",  # Corrected: Command verb is 'vibe'
            plan_prompt="plan {request}",
            summary_prompt_func=lambda: "summarize {output}",
            output_flags=output_flags,
        )

    # Verify results
    assert isinstance(result, Error)
    # Verify memory was NOT updated directly in this path (only via
    # handle_command_output side effect if mocked)
    # If handle_command_output is NOT mocked, update_memory SHOULD be called within it.
    # Since we are patching update_memory at the top level, we check THAT mock.
    # Expect 2 calls: 1 after error, 1 after recovery
    assert mock_update_memory.call_count == 2
    # Check the details of the memory update call
    kwargs = mock_update_memory.call_args_list[1].kwargs  # Check second call
    assert kwargs.get("command") == "get"  # Should be the extracted verb 'get'
    assert "Pod not found" in kwargs.get("command_output", "")
    assert kwargs.get("model_name") == "test-model"


@patch("vibectl.command_handler._execute_command")
@patch("vibectl.command_handler.update_memory")
def test_recovery_suggestions_should_update_memory(
    mock_update_memory: Mock,
    mock_execute: Mock,  # Represents _execute_command
    mock_get_adapter: MagicMock,  # Use the fixture for the adapter
) -> None:
    """Test that memory should be updated with recovery suggestions."""
    # Setup
    # Planning step returns JSON via LLMModelAdapter.execute
    expected_plan_json = json.dumps(
        {
            "action_type": ActionType.COMMAND.value,
            "commands": ["pods"],
            "explanation": "Get pods",
        }
    )
    # LLM execute needs to return the plan first, then recovery suggestions
    recovery_suggestion_text = "Oops: Pod not found. Try 'kubectl get pods -A'."
    # Configure the adapter instance's execute method via the fixture
    mock_get_adapter.execute.side_effect = [
        expected_plan_json,
        recovery_suggestion_text,  # LLM response for recovery
    ]
    # _execute_command (kubectl) fails
    original_error = Error(error="Pod not found", exception=None)
    mock_execute.return_value = original_error

    # Execute command
    output_flags = Mock(
        model_name="test-model",
        show_vibe=True,  # Ensure vibe path is taken in handle_command_output
        show_raw=True,
        show_kubectl=True,
    )
    # Let the actual handle_command_output run to test recovery logic
    result = handle_vibe_request(
        request="show the pods",
        command="vibe",  # Command verb
        plan_prompt="plan {request}",
        summary_prompt_func=lambda: "summarize {output}",
        output_flags=output_flags,
    )

    # Verify recovery suggestions are populated
    assert isinstance(result, Error)
    assert result.recovery_suggestions == recovery_suggestion_text

    # Verify memory update was called TWICE
    assert mock_update_memory.call_count == 2
    # Check the second call for recovery details
    update_kwargs = mock_update_memory.call_args_list[1].kwargs
    assert original_error.error in update_kwargs["command_output"]
    assert recovery_suggestion_text in update_kwargs["vibe_output"]


@patch("vibectl.command_handler._execute_command")
@patch("vibectl.command_handler.update_memory")
def test_recovery_suggestions_in_auto_mode(
    mock_update_memory: Mock,
    mock_execute: Mock,  # Represents _execute_command
    mock_get_adapter: MagicMock,  # Use the adapter fixture
) -> None:
    """Test recovery suggestions in auto mode should update memory."""
    # Setup
    # LLM Calls:
    # 1. Initial plan (JSON)
    # 2. Recovery suggestions (string)
    # 3. Second plan (JSON) - if auto mode retries
    initial_plan_json = json.dumps(
        {
            "action_type": ActionType.COMMAND.value,
            "commands": ["get", "pods"],
            "explanation": "Get pods",
        }
    )
    recovery_suggestion_text = "Error occurred: Pod not found. Trying again with -A."
    # Make the second call return a different command (e.g., fix the namespace)
    # second_plan = { # Remove unused variable
    #     "action_type": ActionType.COMMAND.value,
    #     "commands": ["pods", "-n", "correct-namespace"],
    #     "explanation": "Getting pods in the correct namespace.",
    # }
    # second_plan_json = json.dumps(second_plan) # Unused

    # Configure the adapter instance's execute method via the fixture
    mock_get_adapter.execute.side_effect = [
        initial_plan_json,
        recovery_suggestion_text,
        # second_plan_json, # Auto-mode retry logic not implemented/tested here yet
    ]

    # Kubectl execution results:
    # 1. First attempt fails
    # 2. Second attempt succeeds (if auto mode retries)
    original_error = Error(error="Pod not found", exception=None)
    mock_execute.side_effect = [
        original_error,
        # success_result, # For retry
    ]

    # Execute first command (fails)
    # First time without autonomous mode to check recovery suggestions
    output_flags = Mock(
        model_name="test-model",
        show_vibe=True,
        show_raw=True,
        show_kubectl=True,
    )
    result1 = handle_vibe_request(
        request="show the pods",
        command="vibe",  # Command verb
        plan_prompt="plan {request}",
        summary_prompt_func=lambda: "summarize {output}",
        output_flags=output_flags,
    )

    # Verify recovery suggestions on the first result
    assert isinstance(result1, Error)
    assert result1.recovery_suggestions == recovery_suggestion_text

    # Verify memory update was called TWICE for the first failed attempt
    assert mock_update_memory.call_count == 2
    # Check the second call details (recovery)
    update_kwargs = mock_update_memory.call_args_list[1].kwargs
    # The command should be the *failed* one's verb ('get')
    failed_plan = json.loads(initial_plan_json)
    failed_verb = failed_plan["commands"][0]
    assert update_kwargs["command"] == failed_verb
    assert original_error.error in update_kwargs["command_output"]
    assert recovery_suggestion_text in update_kwargs["vibe_output"]

    # Verify memory updated TWICE after first call
    # (1: after _execute returns error; 2: after recovery suggestion)
    assert mock_update_memory.call_count == 2
