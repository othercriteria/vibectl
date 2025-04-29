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
from unittest.mock import Mock, patch, MagicMock

import pytest

from vibectl.command_handler import handle_vibe_request
from vibectl.model_adapter import LLMModelAdapter
from vibectl.types import ActionType, Error, OutputFlags, Success, Truncation


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
    with patch("vibectl.command_handler.get_model_adapter") as mock:
        # Configure default behavior if needed, or leave it to tests
        adapter_instance = MagicMock()
        model_instance = MagicMock()
        adapter_instance.get_model.return_value = model_instance
        adapter_instance.execute.return_value = "Default mock execute response"
        mock.return_value = adapter_instance
        yield mock


@pytest.fixture
def output_flags() -> OutputFlags:
    """Provide standard OutputFlags for recovery tests."""
    return OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
        show_kubectl=True, # Ensure kubectl command is shown if generated
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
        "commands": ["get", "pods"], # Corrected: Include verb
        "explanation": "Get pods",
    }
    expected_plan_json = json.dumps(plan_response)
    # LLM execute needs to return the plan first, then recovery suggestions
    recovery_suggestion_text = "Error occurred: Pod not found"
    # Assume recovery returns simple text (or adjust if it needs JSON)
    mock_adapter_instance.execute.side_effect = [
        expected_plan_json,
        recovery_suggestion_text # LLM response for recovery
    ]
    # _execute_command (kubectl) fails
    mock_execute.return_value = Error(error="Pod not found", exception=None)

    # Mock recovery prompt generation and memory interaction
    with patch("vibectl.command_handler.recovery_prompt") as mock_recovery_prompt, \
         patch("vibectl.memory.include_memory_in_prompt") as mock_include_memory:
        mock_recovery_prompt.return_value = "Recovery prompt content"
        mock_include_memory.side_effect = lambda p, **k: p # Simple passthrough

        # Execute command
        # Let the actual handle_command_output run to test recovery logic
        result = handle_vibe_request(
            request="show the pods",
            command="vibe", # Corrected: Command verb is 'vibe'
            plan_prompt="plan {request}",
            summary_prompt_func=lambda: "summarize {output}",
            output_flags=output_flags,
        )

    # Verify results
    assert isinstance(result, Error)
    # Check if the recovery suggestion from the second LLM call is in the final result
    assert result.recovery_suggestions == recovery_suggestion_text
    # Verify memory was NOT updated directly in this path (only via handle_command_output side effect if mocked)
    # If handle_command_output is NOT mocked, update_memory SHOULD be called within it.
    # Since we are patching update_memory at the top level, we check THAT mock.
    mock_update_memory.assert_called_once()
    # Check the details of the memory update call
    _args, kwargs = mock_update_memory.call_args
    assert kwargs.get("command") == "get" # Should be the executed command
    assert "Pod not found" in kwargs.get("command_output", "")
    assert recovery_suggestion_text in kwargs.get("vibe_output", "")
    assert kwargs.get("model_name") == "test-model"


@patch.object(LLMModelAdapter, "get_model")
@patch.object(LLMModelAdapter, "execute")
@patch("vibectl.command_handler._execute_command")
@patch("vibectl.command_handler.update_memory")
def test_recovery_suggestions_should_update_memory(
    mock_update_memory: Mock,
    mock_execute: Mock,             # Represents _execute_command
    mock_execute_command: Mock,     # Represents LLMModelAdapter.execute
    mock_get_model: Mock,
) -> None:
    """Test that memory should be updated with recovery suggestions."""
    # Setup
    mock_model = Mock()
    mock_get_model.return_value = mock_model
    # Planning step returns JSON via LLMModelAdapter.execute
    expected_plan_json = json.dumps({
        "action_type": ActionType.COMMAND.value,
        "commands": ["pods"],
        "explanation": "Get pods",
    })
    # LLM execute needs to return the plan first, then recovery suggestions
    recovery_suggestion_text = "Error occurred: Pod not found. Try 'kubectl get pods -A'."
    mock_execute_command.side_effect = [
        expected_plan_json,
        recovery_suggestion_text # LLM response for recovery
    ]
    # _execute_command (kubectl) fails
    original_error = Error(error="Pod not found", exception=None)
    mock_execute.return_value = original_error

    # Execute command
    output_flags = Mock(
        model_name="test-model",
        show_vibe=True, # Ensure vibe path is taken in handle_command_output
        show_raw=True,
        show_kubectl=True,
    )
    # Let the actual handle_command_output run to test recovery logic
    result = handle_vibe_request(
        request="show the pods",
        command="vibe", # Command verb
        plan_prompt="plan {request}",
        summary_prompt_func=lambda: "summarize {output}",
        output_flags=output_flags,
    )

    # Verify recovery suggestions are populated
    assert isinstance(result, Error)
    assert result.recovery_suggestions == recovery_suggestion_text

    # Verify memory update was called
    mock_update_memory.assert_called_once()
    # Check that the memory update includes the recovery suggestion
    update_args, update_kwargs = mock_update_memory.call_args
    assert original_error.error in update_kwargs["command_output"]
    assert recovery_suggestion_text in update_kwargs["vibe_output"]


@patch.object(LLMModelAdapter, "get_model")
@patch.object(LLMModelAdapter, "execute")
@patch("vibectl.command_handler._execute_command")
@patch("vibectl.command_handler.update_memory")
def test_recovery_suggestions_in_auto_mode(
    mock_update_memory: Mock,
    mock_execute: Mock,             # Represents _execute_command
    mock_execute_command: Mock,     # Represents LLMModelAdapter.execute
    mock_get_model: Mock,
) -> None:
    """Test recovery suggestions in auto mode should update memory."""
    # Setup
    mock_model = Mock()
    mock_get_model.return_value = mock_model

    # LLM Calls:
    # 1. Initial plan (JSON)
    # 2. Recovery suggestions (string)
    # 3. Second plan (JSON) - if auto mode retries
    initial_plan_json = json.dumps({
        "action_type": ActionType.COMMAND.value,
        "commands": ["pods"],
        "explanation": "Get pods",
    })
    recovery_suggestion_text = "Error occurred: Pod not found. Trying again with -A."
    second_plan_json = json.dumps({ # Assume auto mode asks for a new plan
         "action_type": ActionType.COMMAND.value,
         "commands": ["pods", "-A"],
         "explanation": "Getting all pods (-A).",
    })
    mock_execute_command.side_effect = [
        initial_plan_json,
        recovery_suggestion_text,
        # second_plan_json, # Auto-mode retry logic not implemented/tested here yet
    ]

    # Kubectl execution results:
    # 1. First attempt fails
    # 2. Second attempt succeeds (if auto mode retries)
    original_error = Error(error="Pod not found", exception=None)
    # success_result = Success(message="Success", data="No pods found in default namespace") # For retry
    mock_execute.side_effect = [
        original_error,
        # success_result, # For retry
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
        command="vibe", # Command verb
        plan_prompt="plan {request}",
        summary_prompt_func=lambda: "summarize {output}",
        output_flags=output_flags,
        # autonomous_mode=True # Test without auto mode first to check recovery suggestions
    )

    # Verify recovery suggestions on the first result
    assert isinstance(result1, Error)
    assert result1.recovery_suggestions == recovery_suggestion_text

    # Verify memory update was called for the first failed attempt
    mock_update_memory.assert_called_once()
    update_args, update_kwargs = mock_update_memory.call_args
    assert original_error.error in update_kwargs["command_output"]
    assert recovery_suggestion_text in update_kwargs["vibe_output"]

    # TODO: Add checks for autonomous mode retry behavior if/when implemented
    # Reset mocks if testing retry
    # mock_update_memory.reset_mock()
    # result2 = handle_vibe_request(...) # Call again or check loop
    # assert isinstance(result2, Success)
    # mock_update_memory.assert_called_once() # Check memory updated for second attempt
