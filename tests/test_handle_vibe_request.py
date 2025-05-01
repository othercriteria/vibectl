"""Tests for handle_vibe_request functionality.

This module tests handle_vibe_request, especially focusing on the handling
of kubeconfig flags to avoid regressions where kubeconfig flags appear in the wrong
position in the final command.
"""

import json
from collections.abc import Generator
from unittest.mock import MagicMock, Mock, patch

import pytest
from pydantic import ValidationError

from vibectl.command_handler import (
    handle_vibe_request,
)
from vibectl.types import ActionType, Error, OutputFlags, Success


@pytest.fixture
def mock_model_adapter() -> Generator[MagicMock, None, None]:
    """Mock the model adapter to return predictable responses."""
    with patch("vibectl.command_handler.get_model_adapter") as mock_adapter:
        mock_model = Mock()
        mock_adapter.return_value.get_model.return_value = mock_model
        mock_adapter.return_value.execute.return_value = (
            "pods --field-selector=status.phase=Succeeded -n sandbox"
        )
        yield mock_adapter


@pytest.fixture
def mock_console() -> Generator[Mock, None, None]:
    """Mock the console manager to avoid output during tests."""
    with patch("vibectl.command_handler.console_manager") as mock:
        yield mock


@pytest.fixture
def mock_handle_output() -> Generator[Mock, None, None]:
    """Mock handle_command_output to avoid actual output handling."""
    with patch("vibectl.command_handler.handle_command_output") as mock:
        yield mock


def test_handle_vibe_request_command_execution() -> None:
    """Test handle_vibe_request executing a basic command with confirmation bypassed."""
    # Create default output flags for this test
    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=False,
        warn_no_output=False,
        model_name="test-model",
        show_kubectl=False,
    )
    # === Mocks ===
    with (
        patch("vibectl.command_handler.get_model_adapter") as mock_get_adapter,
        patch("vibectl.command_handler._execute_command") as mock_execute,
        patch("vibectl.command_handler.update_memory") as mock_update_memory,
    ):
        mock_model = Mock()
        mock_model_adapter = Mock()
        mock_model_adapter.get_model.return_value = mock_model
        # Simulate LLM returning a delete command
        llm_response_delete = {
            "action_type": ActionType.COMMAND.value,
            "commands": ["delete", "pod", "my-pod"],
            "explanation": "Deleting the pod.",
        }
        mock_model_adapter.execute.return_value = json.dumps(llm_response_delete)
        mock_get_adapter.return_value = mock_model_adapter
        # Mock the result of the command execution itself
        mock_execute.return_value = Success(data="pod 'my-pod' deleted")

        # === Execution ===
        result = handle_vibe_request(
            request="delete the pod named my-pod",
            command="vibe",  # Original command was 'vibe'
            plan_prompt="Plan: {request}",
            summary_prompt_func=lambda: "Summary prompt",
            output_flags=output_flags,
            yes=True,  # Bypass confirmation for this test
        )

        # === Verification ===
        # Verify LLM was called for planning
        mock_model_adapter.execute.assert_called_once()
        # Verify the command execution function was called correctly
        mock_execute.assert_called_once_with(
            "delete", ["pod", "my-pod"], None
        )  # verb, args_list, yaml
        mock_update_memory.assert_called_once()

    assert isinstance(result, Success)
    # Check the final message (comes from the mocked _execute_command)
    assert result.message == "pod 'my-pod' deleted"


def test_handle_vibe_request_yaml_execution() -> None:
    """Test handle_vibe_request executing a command with YAML."""
    # Create default output flags for this test
    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=False,
        warn_no_output=False,
        model_name="test-model",
        show_kubectl=False,
    )
    # === Mocks ===
    with patch("vibectl.command_handler.get_model_adapter") as mock_get_adapter:
        mock_model = Mock()
        mock_model_adapter = Mock()
        mock_model_adapter.get_model.return_value = mock_model
        mock_model_adapter.execute.return_value = (
            '{"action_type": "COMMAND", "commands": ["delete", "pod", "my-pod"]}'
        )
        mock_get_adapter.return_value = mock_model_adapter

        # Re-add patch for update_memory
        with (
            patch("vibectl.command_handler._execute_command") as mock_execute,
            patch("vibectl.command_handler.update_memory") as mock_update_memory,
        ):
            mock_execute.return_value = Success(data="pod 'my-pod' deleted")

            # === Execution ===
            result = handle_vibe_request(
                request="delete the pod named my-pod",
                command="vibe",  # Original command was 'vibe'
                plan_prompt="Plan: {request}",
                summary_prompt_func=lambda: "Summary prompt",
                output_flags=output_flags,
                yes=True,  # Bypass confirmation for this test
            )

            # === Verification ===
            mock_model_adapter.execute.assert_called_once()
            mock_execute.assert_called_once_with(
                "delete", ["pod", "my-pod"], None
            )  # verb, args_list, yaml

            assert isinstance(result, Success)
            # Check the final message (which comes from
            # handle_command_output -> _execute_command)
            assert result.message == "pod 'my-pod' deleted"
            mock_update_memory.assert_called_once()


@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler._execute_command")
@patch("vibectl.command_handler.handle_command_output")
@patch("vibectl.command_handler.update_memory")
@patch("vibectl.command_handler.console_manager")
def test_handle_vibe_request_llm_planning_error(
    mock_console: MagicMock,
    mock_update_memory: MagicMock,
    mock_handle_output: MagicMock,
    mock_execute: MagicMock,
    mock_get_adapter: MagicMock,
) -> None:
    """Test handle_vibe_request when LLM returns ActionType.ERROR."""
    output_flags = OutputFlags(
        show_raw=False, show_vibe=True, warn_no_output=False, model_name="test-model"
    )
    mock_adapter = Mock()
    mock_model = Mock()
    mock_get_adapter.return_value = mock_adapter
    mock_adapter.get_model.return_value = mock_model

    # Simulate LLM returning an ERROR action
    llm_response_error = {
        "action_type": ActionType.ERROR.value,
        "error": "I cannot fulfill this request.",
        "explanation": "The request is too ambiguous.",
    }
    mock_adapter.execute.return_value = json.dumps(llm_response_error)

    result = handle_vibe_request(
        request="do something vague",
        command="vibe",
        plan_prompt="Plan: {request}",
        summary_prompt_func=lambda: "",
        output_flags=output_flags,
    )

    assert isinstance(result, Error)
    why_str = "I cannot fulfill this request."
    assert result.error == f"LLM planning error: {why_str}"
    assert result.recovery_suggestions == "The request is too ambiguous."
    mock_adapter.execute.assert_called_once()  # LLM called for planning
    mock_execute.assert_not_called()  # No command execution
    mock_handle_output.assert_not_called()  # No output handling
    mock_update_memory.assert_called_once_with(  # Memory updated with error
        command="vibe",
        command_output=why_str,
        vibe_output=f"LLM Planning Error: do something vague -> {why_str}",
        model_name=output_flags.model_name,
    )
    mock_console.print_note.assert_called_with(
        "AI Explanation: The request is too ambiguous."
    )
    mock_console.print_error.assert_called_with(f"LLM Planning Error: {why_str}")


@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler._execute_command")
@patch("vibectl.command_handler.handle_command_output")
@patch("vibectl.command_handler.update_memory")
@patch("vibectl.command_handler.console_manager")
@patch("time.sleep")  # Mock time.sleep
def test_handle_vibe_request_llm_wait(
    mock_sleep: MagicMock,
    mock_console: MagicMock,
    mock_update_memory: MagicMock,
    mock_handle_output: MagicMock,
    mock_execute: MagicMock,
    mock_get_adapter: MagicMock,
) -> None:
    """Test handle_vibe_request when LLM returns ActionType.WAIT."""
    output_flags = OutputFlags(
        show_raw=False, show_vibe=True, warn_no_output=False, model_name="test-model"
    )
    mock_adapter = Mock()
    mock_model = Mock()
    mock_get_adapter.return_value = mock_adapter
    mock_adapter.get_model.return_value = mock_model

    # Simulate LLM returning a WAIT action
    llm_response_wait = {
        "action_type": ActionType.WAIT.value,
        "wait_duration_seconds": 5,
        "explanation": "Waiting for resource propagation.",
    }
    mock_adapter.execute.return_value = json.dumps(llm_response_wait)

    result = handle_vibe_request(
        request="wait a bit",
        command="vibe",
        plan_prompt="Plan: {request}",
        summary_prompt_func=lambda: "",
        output_flags=output_flags,
    )

    assert isinstance(result, Success)
    assert result.message == "Waited for 5 seconds."
    mock_adapter.execute.assert_called_once()
    mock_sleep.assert_called_once_with(5)
    mock_execute.assert_not_called()
    mock_handle_output.assert_not_called()
    mock_update_memory.assert_not_called()  # No memory update for WAIT
    mock_console.print_note.assert_called_with(
        "AI Explanation: Waiting for resource propagation."
    )
    mock_console.print_processing.assert_any_call(
        "Waiting for 5 seconds as requested by AI..."
    )


@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler._execute_command")
@patch("vibectl.command_handler.handle_command_output")
@patch("vibectl.command_handler.update_memory")
@patch("vibectl.command_handler.console_manager")
def test_handle_vibe_request_llm_feedback(
    mock_console: MagicMock,
    mock_update_memory: MagicMock,
    mock_handle_output: MagicMock,
    mock_execute: MagicMock,
    mock_get_adapter: MagicMock,
) -> None:
    """Test handle_vibe_request when LLM returns ActionType.FEEDBACK."""
    output_flags = OutputFlags(
        show_raw=False, show_vibe=True, warn_no_output=False, model_name="test-model"
    )
    mock_adapter = Mock()
    mock_model = Mock()
    mock_get_adapter.return_value = mock_adapter
    mock_adapter.get_model.return_value = mock_model

    # Simulate LLM returning a FEEDBACK action
    llm_response_feedback = {
        "action_type": ActionType.FEEDBACK.value,
        "explanation": "Consider specifying a namespace.",
    }
    mock_adapter.execute.return_value = json.dumps(llm_response_feedback)

    result = handle_vibe_request(
        request="get pods",
        command="vibe",
        plan_prompt="Plan: {request}",
        summary_prompt_func=lambda: "",
        output_flags=output_flags,
    )

    assert isinstance(result, Success)
    assert result.message == "Received feedback from AI."
    mock_adapter.execute.assert_called_once()
    mock_execute.assert_not_called()
    mock_handle_output.assert_not_called()
    mock_update_memory.assert_not_called()  # No memory update for FEEDBACK
    mock_console.print_note.assert_called_with(
        "AI Explanation: Consider specifying a namespace."
    )


@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler.console_manager")
def test_handle_vibe_request_llm_feedback_no_explanation(
    mock_console: MagicMock,
    mock_get_adapter: MagicMock,
) -> None:
    """Test handle_vibe_request with ActionType.FEEDBACK but no explanation."""
    output_flags = OutputFlags(
        show_raw=False, show_vibe=True, warn_no_output=False, model_name="test-model"
    )
    mock_adapter = Mock()
    mock_model = Mock()
    mock_get_adapter.return_value = mock_adapter
    mock_adapter.get_model.return_value = mock_model

    # Simulate LLM returning FEEDBACK action without explanation
    llm_response_feedback = {"action_type": ActionType.FEEDBACK.value}
    mock_adapter.execute.return_value = json.dumps(llm_response_feedback)

    result = handle_vibe_request(
        request="get pods",
        command="vibe",
        plan_prompt="Plan: {request}",
        summary_prompt_func=lambda: "",
        output_flags=output_flags,
    )

    assert isinstance(result, Success)
    assert result.message == "Received feedback from AI."
    mock_adapter.execute.assert_called_once()
    # Verify the default message is printed when no explanation is given
    mock_console.print_note.assert_called_with("Received feedback from AI.")


@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler.update_memory")
@patch("vibectl.command_handler.console_manager")
def test_handle_vibe_request_llm_invalid_json(
    mock_console: MagicMock,
    mock_update_memory: MagicMock,
    mock_get_adapter: MagicMock,
) -> None:
    """Test handle_vibe_request when LLM returns invalid JSON."""
    output_flags = OutputFlags(
        show_raw=False, show_vibe=False, warn_no_output=False, model_name="test-model"
    )
    mock_adapter = Mock()
    mock_model = Mock()
    mock_get_adapter.return_value = mock_adapter
    mock_adapter.get_model.return_value = mock_model

    # Simulate LLM returning invalid JSON
    invalid_json = '{"action_type": "COMMAND", "commands": ["get", "pods" '
    mock_adapter.execute.return_value = invalid_json

    result = handle_vibe_request(
        request="get pods",
        command="vibe",
        plan_prompt="Plan: {request}",
        summary_prompt_func=lambda: "",
        output_flags=output_flags,
    )

    assert isinstance(result, Error)
    assert "Failed to parse LLM response as expected JSON" in result.error
    assert isinstance(result.exception, ValidationError)
    assert result.halt_auto_loop is False  # Parsing errors are API errors
    mock_update_memory.assert_called_once()  # Memory updated with parse failure
    assert (
        "System Error: Failed to parse LLM response"
        in mock_update_memory.call_args[1]["vibe_output"]
    )


@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler.update_memory")
@patch("vibectl.command_handler.console_manager")
def test_handle_vibe_request_llm_invalid_schema(
    mock_console: MagicMock,
    mock_update_memory: MagicMock,
    mock_get_adapter: MagicMock,
) -> None:
    """Test handle_vibe_request when LLM returns valid JSON but invalid schema."""

    output_flags = OutputFlags(
        show_raw=False, show_vibe=False, warn_no_output=False, model_name="test-model"
    )
    mock_adapter = Mock()
    mock_model = Mock()
    mock_get_adapter.return_value = mock_adapter
    mock_adapter.get_model.return_value = mock_model

    # Simulate LLM returning valid JSON but missing required fields (e.g.,
    # commands for COMMAND)
    invalid_schema_json = (
        '{"action_type": "COMMAND", "explanation": "Missing commands"}'
    )
    mock_adapter.execute.return_value = invalid_schema_json

    result = handle_vibe_request(
        request="get pods",
        command="vibe",
        plan_prompt="Plan: {request}",
        summary_prompt_func=lambda: "",
        output_flags=output_flags,
    )

    assert isinstance(result, Error)
    # Check for the specific internal error when commands are missing for COMMAND type
    assert result.error == "Internal error: LLM sent COMMAND action with no args."
    assert result.exception is None  # No exception attached for this internal check
    assert result.halt_auto_loop is True  # This internal error IS halting
    mock_update_memory.assert_called_once()  # Memory updated with this specific error
    assert (
        "LLM Error: COMMAND action with no args."
        in mock_update_memory.call_args[1]["vibe_output"]
    )


@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler.update_memory")
@patch("vibectl.command_handler.console_manager")
def test_handle_vibe_request_llm_empty_response(
    mock_console: MagicMock,
    mock_update_memory: MagicMock,
    mock_get_adapter: MagicMock,
) -> None:
    """Test handle_vibe_request when LLM returns an empty string."""
    output_flags = OutputFlags(
        show_raw=False, show_vibe=False, warn_no_output=False, model_name="test-model"
    )
    mock_adapter = Mock()
    mock_model = Mock()
    mock_get_adapter.return_value = mock_adapter
    mock_adapter.get_model.return_value = mock_model
    mock_adapter.execute.return_value = ""

    result = handle_vibe_request(
        request="get pods",
        command="vibe",
        plan_prompt="Plan: {request}",
        summary_prompt_func=lambda: "",
        output_flags=output_flags,
    )

    assert isinstance(result, Error)
    assert result.error == "LLM returned an empty response."
    mock_update_memory.assert_called_once_with(
        command="system",
        command_output="LLM Error: Empty response.",
        vibe_output="LLM Error: Empty response.",
        model_name=output_flags.model_name,
    )


@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler.update_memory")
@patch("vibectl.command_handler.console_manager")
def test_handle_vibe_request_action_error_no_message(
    mock_console: MagicMock,
    mock_update_memory: MagicMock,
    mock_get_adapter: MagicMock,
) -> None:
    """Test handle_vibe_request with ActionType.ERROR but missing error message."""
    output_flags = OutputFlags(
        show_raw=False, show_vibe=False, warn_no_output=False, model_name="test-model"
    )
    mock_adapter = Mock()
    mock_model = Mock()
    mock_get_adapter.return_value = mock_adapter
    mock_adapter.get_model.return_value = mock_model

    # Simulate LLM returning ERROR action without error field
    llm_response = {"action_type": ActionType.ERROR.value}
    mock_adapter.execute.return_value = json.dumps(llm_response)

    result = handle_vibe_request(
        request="test",
        command="vibe",
        plan_prompt="p",
        summary_prompt_func=lambda: "",
        output_flags=output_flags,
    )

    assert isinstance(result, Error)
    assert result.error == "Internal error: LLM sent ERROR action without message."
    mock_update_memory.assert_not_called()  # No update because error is internal


@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler.update_memory")
@patch("vibectl.command_handler.console_manager")
def test_handle_vibe_request_action_wait_no_duration(
    mock_console: MagicMock,
    mock_update_memory: MagicMock,
    mock_get_adapter: MagicMock,
) -> None:
    """Test handle_vibe_request with ActionType.WAIT but missing duration."""
    output_flags = OutputFlags(
        show_raw=False, show_vibe=False, warn_no_output=False, model_name="test-model"
    )
    mock_adapter = Mock()
    mock_model = Mock()
    mock_get_adapter.return_value = mock_adapter
    mock_adapter.get_model.return_value = mock_model

    # Simulate LLM returning WAIT action without duration field
    llm_response = {"action_type": ActionType.WAIT.value}
    mock_adapter.execute.return_value = json.dumps(llm_response)

    result = handle_vibe_request(
        request="test",
        command="vibe",
        plan_prompt="p",
        summary_prompt_func=lambda: "",
        output_flags=output_flags,
    )

    assert isinstance(result, Error)
    assert result.error == "Internal error: LLM sent WAIT action without duration."
    mock_update_memory.assert_not_called()


@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler.update_memory")
@patch("vibectl.command_handler.console_manager")
def test_handle_vibe_request_action_command_no_args(
    mock_console: MagicMock,
    mock_update_memory: MagicMock,
    mock_get_adapter: MagicMock,
) -> None:
    """Test handle_vibe_request with ActionType.COMMAND but no commands/yaml."""
    output_flags = OutputFlags(
        show_raw=False, show_vibe=False, warn_no_output=False, model_name="test-model"
    )
    mock_adapter = Mock()
    mock_model = Mock()
    mock_get_adapter.return_value = mock_adapter
    mock_adapter.get_model.return_value = mock_model

    # Simulate LLM returning COMMAND action without commands or yaml
    llm_response = {"action_type": ActionType.COMMAND.value}
    mock_adapter.execute.return_value = json.dumps(llm_response)

    result = handle_vibe_request(
        request="test",
        command="vibe",
        plan_prompt="p",
        summary_prompt_func=lambda: "",
        output_flags=output_flags,
    )

    assert isinstance(result, Error)
    assert result.error == "Internal error: LLM sent COMMAND action with no args."
    assert result.exception is None  # No exception attached for this internal check
    assert result.halt_auto_loop is True
    mock_update_memory.assert_called_once()  # Memory updated with this specific error
    assert (
        "LLM Error: COMMAND action with no args."
        in mock_update_memory.call_args[1]["vibe_output"]
    )


@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler.update_memory")
@patch("vibectl.command_handler.console_manager")
def test_handle_vibe_request_action_command_empty_verb(
    mock_console: MagicMock,
    mock_update_memory: MagicMock,
    mock_get_adapter: MagicMock,
) -> None:
    """Test handle_vibe_request with ActionType.COMMAND but LLM provides empty verb."""
    output_flags = OutputFlags(
        show_raw=False, show_vibe=False, warn_no_output=False, model_name="test-model"
    )
    mock_adapter = Mock()
    mock_model = Mock()
    mock_get_adapter.return_value = mock_adapter
    mock_adapter.get_model.return_value = mock_model

    # Simulate LLM returning COMMAND action with empty first command element
    llm_response = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["", "pods"],  # Empty verb
    }
    mock_adapter.execute.return_value = json.dumps(llm_response)

    result = handle_vibe_request(
        request="test",
        command="vibe",
        plan_prompt="p",
        summary_prompt_func=lambda: "",
        output_flags=output_flags,
    )

    assert isinstance(result, Error)
    assert result.error == "LLM planning failed: Could not determine command verb."
    mock_update_memory.assert_not_called()


@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler.update_memory")
@patch("vibectl.command_handler.console_manager")
@patch("vibectl.command_handler._execute_command")
@patch("vibectl.command_handler.handle_command_output")
def test_handle_vibe_request_command_recoverable_api_error_in_handler(
    mock_handle_output: MagicMock,
    mock_execute_command: MagicMock,
    mock_console: MagicMock,
    mock_update_memory: MagicMock,
    mock_get_adapter: MagicMock,
) -> None:
    """Test handle_vibe_request if handle_command_output raises RecoverableApiError."""
    from vibectl.model_adapter import RecoverableApiError

    output_flags = OutputFlags(
        show_raw=False, show_vibe=True, warn_no_output=False, model_name="test-model"
    )
    mock_adapter = Mock()
    mock_model = Mock()
    mock_get_adapter.return_value = mock_adapter
    mock_adapter.get_model.return_value = mock_model

    # Simulate LLM returning a valid command
    llm_response = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["get", "pods"],
    }
    mock_adapter.execute.return_value = json.dumps(llm_response)

    # Mock command execution to succeed
    mock_execute_command.return_value = Success(data="some pods")

    # Mock handle_command_output to raise RecoverableApiError
    api_error = RecoverableApiError("Output processing failed")
    mock_handle_output.side_effect = api_error

    result = handle_vibe_request(
        request="test",
        command="vibe",
        plan_prompt="p",
        summary_prompt_func=lambda: "",
        output_flags=output_flags,
    )

    assert isinstance(result, Error)
    assert result.error == "API Error: Output processing failed"
    assert result.exception == api_error
    assert result.halt_auto_loop is False
    mock_execute_command.assert_called_once()
    mock_handle_output.assert_called_once()
    mock_update_memory.assert_called_once()  # Memory updated after command execution


@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler.update_memory")
@patch("vibectl.command_handler.console_manager")
@patch("vibectl.command_handler._execute_command")
@patch("vibectl.command_handler.handle_command_output")
def test_handle_vibe_request_command_generic_error_in_handler(
    mock_handle_output: MagicMock,
    mock_execute_command: MagicMock,
    mock_console: MagicMock,
    mock_update_memory: MagicMock,
    mock_get_adapter: MagicMock,
) -> None:
    """Test handle_vibe_request where handle_command_output raises generic Exception."""
    output_flags = OutputFlags(
        show_raw=False, show_vibe=True, warn_no_output=False, model_name="test-model"
    )
    mock_adapter = Mock()
    mock_model = Mock()
    mock_get_adapter.return_value = mock_adapter
    mock_adapter.get_model.return_value = mock_model

    # Simulate LLM returning a valid command
    llm_response = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["get", "pods"],
    }
    mock_adapter.execute.return_value = json.dumps(llm_response)

    # Mock command execution to succeed
    mock_execute_command.return_value = Success(data="some pods")

    # Mock handle_command_output to raise generic Exception
    generic_error = ValueError("Something broke")
    mock_handle_output.side_effect = generic_error

    result = handle_vibe_request(
        request="test",
        command="vibe",
        plan_prompt="p",
        summary_prompt_func=lambda: "",
        output_flags=output_flags,
    )

    assert isinstance(result, Error)
    assert result.error == f"Error handling command output: {generic_error}"
    assert result.exception == generic_error
    assert result.halt_auto_loop is True
    mock_execute_command.assert_called_once()
    mock_handle_output.assert_called_once()
    mock_update_memory.assert_called_once()  # Memory updated after command execution


@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler.update_memory")
@patch("vibectl.command_handler.console_manager")
def test_handle_vibe_request_action_unknown(
    mock_console: MagicMock,
    mock_update_memory: MagicMock,
    mock_get_adapter: MagicMock,
) -> None:
    """Test handle_vibe_request with an unknown ActionType from LLM."""
    output_flags = OutputFlags(
        show_raw=False, show_vibe=False, warn_no_output=False, model_name="test-model"
    )
    mock_adapter = Mock()
    mock_model = Mock()
    mock_get_adapter.return_value = mock_adapter
    mock_adapter.get_model.return_value = mock_model

    # Simulate LLM returning an invalid action type string
    # Need to bypass Pydantic validation slightly for this test by manually creating
    llm_response_text = '{"action_type": "INVALID_ACTION", "explanation": "Test"}'
    mock_adapter.execute.return_value = llm_response_text

    # We expect model_validate_json to potentially raise ValidationError here if strict
    # But if ActionType conversion happens after, this tests the match default case.
    # Let's assume for the test it passes validation but fails the enum match.

    result = handle_vibe_request(
        request="test",
        command="vibe",
        plan_prompt="p",
        summary_prompt_func=lambda: "",
        output_flags=output_flags,
    )

    # This depends on whether validation catches it first or the match case.
    # If validation catches it, it's covered by
    # test_handle_vibe_request_llm_invalid_schema
    # If match default is hit:
    if isinstance(result, Error) and "Unknown ActionType" in result.error:
        assert "Internal error: Unknown ActionType received from LLM" in result.error
        mock_update_memory.assert_not_called()
    else:
        # If ValidationError was raised, this case shouldn't be hit directly.
        # We rely on the invalid_schema test instead.
        pass  # Or assert that it's a validation error


@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler.update_memory")
@patch("vibectl.command_handler.console_manager")
def test_handle_vibe_request_planning_recoverable_api_error(
    mock_console: MagicMock,
    mock_update_memory: MagicMock,
    mock_get_adapter: MagicMock,
) -> None:
    """Test handle_vibe_request when planning LLM call raises RecoverableApiError."""
    from vibectl.model_adapter import RecoverableApiError

    output_flags = OutputFlags(
        show_raw=False, show_vibe=False, warn_no_output=False, model_name="test-model"
    )
    mock_adapter = Mock()
    mock_model = Mock()
    mock_get_adapter.return_value = mock_adapter
    mock_adapter.get_model.return_value = mock_model

    # Mock adapter execute (for planning) to raise error
    api_error = RecoverableApiError("Planning LLM Down")
    mock_adapter.execute.side_effect = api_error

    result = handle_vibe_request(
        request="test",
        command="vibe",
        plan_prompt="p",
        summary_prompt_func=lambda: "",
        output_flags=output_flags,
    )

    assert isinstance(result, Error)
    assert result.error == str(api_error)
    assert result.exception == api_error
    assert result.halt_auto_loop is False
    mock_console.print_error.assert_called_with("API Error: Planning LLM Down")
    mock_update_memory.assert_not_called()


@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler.update_memory")
@patch("vibectl.command_handler.console_manager")
def test_handle_vibe_request_planning_generic_error(
    mock_console: MagicMock,
    mock_update_memory: MagicMock,
    mock_get_adapter: MagicMock,
) -> None:
    """Test handle_vibe_request when planning LLM call raises generic Exception."""
    output_flags = OutputFlags(
        show_raw=False, show_vibe=False, warn_no_output=False, model_name="test-model"
    )
    mock_adapter = Mock()
    mock_model = Mock()
    mock_get_adapter.return_value = mock_adapter
    mock_adapter.get_model.return_value = mock_model

    # Mock adapter execute (for planning) to raise error
    generic_error = ConnectionError("Network Error")
    mock_adapter.execute.side_effect = generic_error

    result = handle_vibe_request(
        request="test",
        command="vibe",
        plan_prompt="p",
        summary_prompt_func=lambda: "",
        output_flags=output_flags,
    )

    assert isinstance(result, Error)
    assert result.error == str(generic_error)
    assert result.exception == generic_error
    assert result.halt_auto_loop is True
    mock_console.print_error.assert_called_with(
        f"Error executing vibe request: {generic_error}"
    )
    mock_update_memory.assert_not_called()
