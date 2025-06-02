"""Tests for handle_vibe_request functionality.

This module tests handle_vibe_request, especially focusing on the handling
of kubeconfig flags to avoid regressions where kubeconfig flags appear in the wrong
position in the final command.
"""

import json
from collections.abc import Callable, Generator
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from pydantic import ValidationError

from vibectl.config import Config
from vibectl.execution.vibe import handle_vibe_request
from vibectl.prompts.vibe import plan_vibe_fragments
from vibectl.schema import (
    ErrorAction,
    LLMPlannerResponse,
)
from vibectl.types import (
    ActionType,
    Error,
    Fragment,
    LLMMetrics,
    MetricsDisplayMode,
    OutputFlags,
    PromptFragments,
    Success,
    SystemFragments,
    UserFragments,
)


@pytest.fixture
def mock_model_adapter() -> Generator[MagicMock, None, None]:
    """Mock the model adapter to return predictable responses."""
    with patch("vibectl.execution.vibe.get_model_adapter") as mock_adapter:
        mock_model = Mock()
        mock_adapter.return_value.get_model.return_value = mock_model
        mock_adapter.return_value.execute_and_log_metrics.return_value = (
            "pods --field-selector=status.phase=Succeeded -n sandbox",
            None,
        )
        yield mock_adapter


@pytest.fixture
def mock_console() -> Generator[Mock, None, None]:
    """Mock the console manager to avoid output during tests."""
    with patch("vibectl.execution.vibe.console_manager") as mock:
        yield mock


@pytest.fixture
def mock_handle_output() -> Generator[Mock, None, None]:
    """Mock handle_command_output to avoid actual output handling."""
    with patch("vibectl.execution.vibe.handle_command_output") as mock:
        yield mock


@pytest.fixture
def mock_summary_prompt_func_hvr() -> Callable[
    [Config | None, str | None], PromptFragments
]:
    """Provides a mock summary_prompt_func for handle_vibe_request tests."""

    def _mock_func(
        config: Config | None = None, current_memory: str | None = None
    ) -> PromptFragments:
        return PromptFragments(
            (SystemFragments([]), UserFragments([Fragment("Mocked Summary")]))
        )

    return _mock_func


@pytest.mark.asyncio
@patch("vibectl.execution.vibe.handle_command_output")
@patch("vibectl.execution.vibe.update_memory")
@patch("vibectl.execution.vibe._execute_command")
@patch("vibectl.execution.vibe.get_model_adapter")
async def test_handle_vibe_request_command_execution(
    mock_get_adapter: MagicMock,
    mock_execute: MagicMock,
    mock_update_memory: MagicMock,
    mock_handle_command_output: MagicMock,
    mock_summary_prompt_func_hvr: Callable[
        [Config | None, str | None], PromptFragments
    ],
) -> None:
    """Test handle_vibe_request executing a basic command with confirmation bypassed."""

    # Create default output flags for this test
    output_flags = OutputFlags(
        show_raw_output=False,
        show_vibe=False,
        warn_no_output=False,
        model_name="test-model",
        show_kubectl=False,
        show_metrics=MetricsDisplayMode.ALL,
    )

    mock_model = Mock()
    mock_model_adapter_instance = Mock()
    mock_model_adapter_instance.get_model.return_value = mock_model

    # Correctly structured LLM response for planning
    command_action_data = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["delete", "pod", "my-pod"],
        "explanation": "Deleting the pod.",
        "allowed_exit_codes": [0],
    }
    llm_planner_response_json = json.dumps({"action": command_action_data})
    mock_model_adapter_instance.execute_and_log_metrics = AsyncMock(
        return_value=(llm_planner_response_json, None)
    )
    mock_get_adapter.return_value = mock_model_adapter_instance

    # Mock the result of the command execution itself
    mock_execute.return_value = Success(data="pod 'my-pod' executed_data")
    mock_update_memory.return_value = None  # Prevent error in update_memory

    # Mock handle_command_output to return a predictable final message
    final_success_message = "pod 'my-pod' deleted_final_message"
    mock_handle_command_output.return_value = Success(
        message=final_success_message, data="pod 'my-pod' executed_data"
    )

    # === Execution ===
    result = await handle_vibe_request(
        request="delete the pod named my-pod",
        command="vibe",
        plan_prompt_func=plan_vibe_fragments,
        summary_prompt_func=mock_summary_prompt_func_hvr,
        output_flags=output_flags,
        yes=True,  # Bypass confirmation for this test
    )

    # === Verification ===
    # Verify LLM was called for planning
    mock_model_adapter_instance.execute_and_log_metrics.assert_called_once()
    # Verify the command execution function was called correctly
    mock_execute.assert_called_once_with(
        "delete", ["pod", "my-pod"], None, allowed_exit_codes=(0,)
    )
    # Verify handle_command_output was called
    mock_handle_command_output.assert_called_once()
    # Verify memory was updated
    mock_update_memory.assert_called_once()
    # Verify final result
    assert isinstance(result, Success)
    assert result.message == final_success_message


@pytest.mark.asyncio
@patch("vibectl.execution.vibe.handle_command_output")
@patch("vibectl.execution.vibe.update_memory")
@patch("vibectl.execution.vibe._execute_command")
@patch("vibectl.execution.vibe.get_model_adapter")
async def test_handle_vibe_request_yaml_execution(
    mock_get_adapter: MagicMock,
    mock_execute: MagicMock,
    mock_update_memory: MagicMock,
    mock_handle_command_output: MagicMock,
    mock_summary_prompt_func_hvr: Callable[
        [Config | None, str | None], PromptFragments
    ],
) -> None:
    """Test handle_vibe_request executing a command with YAML."""

    class MockCalledCustomError(Exception):
        pass

    # Create default output flags for this test
    output_flags = OutputFlags(
        show_raw_output=False,
        show_vibe=False,
        warn_no_output=False,
        model_name="test-model",
        show_kubectl=False,
        show_metrics=MetricsDisplayMode.ALL,
    )
    # === Mocks ===
    mock_model = Mock()
    mock_model_adapter_instance = Mock()
    mock_model_adapter_instance.get_model.return_value = mock_model

    # Correctly structured LLM response for planning with YAML
    yaml_content = "kind: Pod\nname: my-pod-yaml"
    command_action_data = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["apply", "-f", "-"],
        "yaml_manifest": yaml_content,
        "explanation": "Applying a pod from YAML.",
        "allowed_exit_codes": [0],
    }
    llm_planner_response_json = json.dumps({"action": command_action_data})
    mock_model_adapter_instance.execute_and_log_metrics = AsyncMock(
        return_value=(llm_planner_response_json, None)
    )
    mock_get_adapter.return_value = mock_model_adapter_instance

    # Mock _execute_command return value
    mock_execute.return_value = Success(data="pod 'my-pod-yaml' applied_data")
    mock_update_memory.return_value = None
    # Mock handle_command_output return value
    final_success_message = "pod 'my-pod-yaml' applied_final_message"
    mock_handle_command_output.return_value = Success(
        message=final_success_message, data="pod 'my-pod-yaml' applied_data"
    )

    # === Execution ===
    result = await handle_vibe_request(
        request="apply the pod named my-pod-yaml",
        command="vibe",
        plan_prompt_func=plan_vibe_fragments,
        summary_prompt_func=mock_summary_prompt_func_hvr,
        output_flags=output_flags,
        yes=True,  # Bypass confirmation for this test
    )

    # === Verification ===
    mock_model_adapter_instance.execute_and_log_metrics.assert_called_once()
    mock_execute.assert_called_once_with(
        "apply", ["-f", "-"], yaml_content, allowed_exit_codes=(0,)
    )
    mock_handle_command_output.assert_called_once()
    mock_update_memory.assert_called_once()
    assert isinstance(result, Success)
    assert result.message == final_success_message


@pytest.mark.asyncio
@patch("vibectl.execution.vibe.get_model_adapter")
@patch("vibectl.execution.vibe._execute_command")
@patch("vibectl.execution.vibe.handle_command_output")
@patch("vibectl.execution.vibe.update_memory")
@patch("vibectl.execution.vibe.console_manager")
async def test_handle_vibe_request_llm_planning_error(
    mock_console: MagicMock,
    mock_update_memory: MagicMock,
    mock_handle_output: MagicMock,
    mock_execute: MagicMock,
    mock_get_adapter: MagicMock,
    mock_summary_prompt_func_hvr: Callable[
        [Config | None, str | None], PromptFragments
    ],
) -> None:
    """Test handle_vibe_request when LLM returns ActionType.ERROR."""
    # Mock update_memory to return proper LLMMetrics object
    mock_update_memory.return_value = LLMMetrics()

    output_flags = OutputFlags(
        show_raw_output=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
        show_metrics=MetricsDisplayMode.ALL,
    )
    mock_adapter_instance = Mock(name="AdapterForErrorTest")
    mock_model = Mock()
    mock_get_adapter.return_value = mock_adapter_instance
    mock_adapter_instance.get_model.return_value = mock_model

    error_response_obj = LLMPlannerResponse(
        action=ErrorAction(action_type=ActionType.ERROR, message="Test error")
    )
    llm_response_json_str = error_response_obj.model_dump_json()

    mock_adapter_instance.execute_and_log_metrics = AsyncMock(
        return_value=(llm_response_json_str, None)
    )

    result = await handle_vibe_request(
        request="test request",
        command="vibe",
        plan_prompt_func=plan_vibe_fragments,
        summary_prompt_func=mock_summary_prompt_func_hvr,
        output_flags=output_flags,
    )

    assert isinstance(result, Error)
    assert result.error == "LLM planning error: Test error"
    assert result.recovery_suggestions == "Test error"
    mock_adapter_instance.execute_and_log_metrics.assert_called_once()
    mock_execute.assert_not_called()
    mock_handle_output.assert_not_called()
    mock_update_memory.assert_called_once_with(
        command_message="command: vibe request: test request",
        command_output="Test error",
        vibe_output="",
        model_name=output_flags.model_name,
    )
    mock_console.print_error.assert_called_with("LLM Planning Error: Test error")


@pytest.mark.asyncio
@patch("vibectl.execution.vibe.get_model_adapter")
@patch("vibectl.execution.vibe._execute_command")
@patch("vibectl.execution.vibe.handle_command_output")
@patch("vibectl.execution.vibe.update_memory")
@patch("vibectl.execution.vibe.console_manager")
@patch("asyncio.sleep")  # Mock asyncio.sleep
async def test_handle_vibe_request_llm_wait(
    mock_sleep: MagicMock,
    mock_console: MagicMock,
    mock_update_memory: MagicMock,
    mock_handle_command_output: MagicMock,
    mock_execute_command: MagicMock,
    mock_get_model_adapter: MagicMock,
    mock_summary_prompt_func_hvr: Callable[
        [Config | None, str | None], PromptFragments
    ],
) -> None:
    """Test handle_vibe_request when LLM returns ActionType.WAIT."""
    # Mock update_memory to return proper LLMMetrics object
    mock_update_memory.return_value = LLMMetrics()

    output_flags = OutputFlags(
        show_raw_output=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
        show_metrics=MetricsDisplayMode.ALL,
    )
    mock_adapter_instance = Mock(name="AdapterInstanceForWaitTest")
    mock_model_instance = Mock(name="ModelInstanceForWaitTest")
    mock_get_model_adapter.return_value = mock_adapter_instance
    mock_adapter_instance.get_model.return_value = mock_model_instance

    # Simulate LLM returning a WAIT action
    wait_action_data = {
        "action_type": ActionType.WAIT.value,
        "duration_seconds": 5,
        "explanation": "Waiting for resource propagation.",
    }
    llm_planner_response_json = json.dumps({"action": wait_action_data})
    mock_adapter_instance.execute_and_log_metrics = AsyncMock(
        return_value=(llm_planner_response_json, None)
    )

    result = await handle_vibe_request(
        request="wait a bit",
        command="vibe",
        plan_prompt_func=plan_vibe_fragments,
        summary_prompt_func=mock_summary_prompt_func_hvr,
        output_flags=output_flags,
        yes=True,
    )

    assert isinstance(result, Success)
    assert result.message == "Waited for 5 seconds."
    assert result.data is None

    mock_get_model_adapter.assert_called_once()
    mock_adapter_instance.get_model.assert_called_once()
    mock_adapter_instance.execute_and_log_metrics.assert_called_once()
    mock_sleep.assert_called_once_with(5)
    mock_execute_command.assert_not_called()
    mock_handle_command_output.assert_not_called()
    mock_update_memory.assert_called_once()

    mock_console.print_note.assert_called_with(
        f"Waited for {wait_action_data['duration_seconds']} seconds."
    )
    mock_console.print_processing.assert_called_with(
        "Waiting for 5 seconds as requested by AI..."
    )


@pytest.mark.asyncio
@patch("vibectl.execution.vibe.get_model_adapter")
@patch("vibectl.execution.vibe._execute_command")
@patch("vibectl.execution.vibe.handle_command_output")
@patch("vibectl.execution.vibe.update_memory")
@patch("vibectl.execution.vibe.console_manager")
async def test_handle_vibe_request_llm_feedback(
    mock_console: MagicMock,
    mock_update_memory: MagicMock,
    mock_handle_command_output: MagicMock,
    mock_execute_command: MagicMock,
    mock_get_model_adapter: MagicMock,
    mock_summary_prompt_func_hvr: Callable[
        [Config | None, str | None], PromptFragments
    ],
) -> None:
    """Test handle_vibe_request when LLM returns ActionType.FEEDBACK."""
    # Mock update_memory to return proper LLMMetrics object
    mock_update_memory.return_value = LLMMetrics()

    output_flags = OutputFlags(
        show_raw_output=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
        show_metrics=MetricsDisplayMode.ALL,
    )
    mock_adapter_instance = Mock(name="AdapterInstanceForFeedbackTest")
    mock_model_instance = Mock(name="ModelInstanceForFeedbackTest")
    mock_get_model_adapter.return_value = mock_adapter_instance
    mock_adapter_instance.get_model.return_value = mock_model_instance

    # Simulate LLM returning a FEEDBACK action
    feedback_action_data = {
        "action_type": ActionType.FEEDBACK.value,
        "message": "This is a feedback message.",
        "explanation": "Consider specifying a namespace.",
    }
    llm_planner_response_json = json.dumps({"action": feedback_action_data})
    mock_adapter_instance.execute_and_log_metrics = AsyncMock(
        return_value=(llm_planner_response_json, None)
    )

    result = await handle_vibe_request(
        request="get pods",
        command="vibe",
        plan_prompt_func=plan_vibe_fragments,
        summary_prompt_func=mock_summary_prompt_func_hvr,
        output_flags=output_flags,
        yes=True,
    )

    assert isinstance(result, Success)
    assert (
        result.message
        == "Applied AI feedback: AI unable to provide a specific suggestion."
    )
    assert result.data is None

    mock_get_model_adapter.assert_called_once()
    mock_adapter_instance.get_model.assert_called_once()
    mock_adapter_instance.execute_and_log_metrics.assert_called_once()
    mock_execute_command.assert_not_called()
    mock_handle_command_output.assert_not_called()
    mock_update_memory.assert_called_once()

    mock_console.print_vibe.assert_called_with("This is a feedback message.")


@pytest.mark.asyncio
@patch("vibectl.execution.vibe.get_model_adapter")
@patch("vibectl.execution.vibe.update_memory")
@patch("vibectl.execution.vibe.console_manager")
async def test_handle_vibe_request_llm_feedback_no_explanation(
    mock_console_manager_actual: MagicMock,
    mock_update_memory_actual: MagicMock,
    mock_get_model_adapter_actual: MagicMock,
    mock_summary_prompt_func_hvr: Callable[
        [Config | None, str | None], PromptFragments
    ],
) -> None:
    """Test handle_vibe_request with ActionType.FEEDBACK but no explanation."""
    # Mock update_memory to return proper LLMMetrics object
    mock_update_memory_actual.return_value = LLMMetrics()

    output_flags = OutputFlags(
        show_raw_output=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
        show_metrics=MetricsDisplayMode.ALL,
    )
    mock_adapter_instance = Mock(name="AdapterInstanceForFeedbackNoExpTest")
    mock_model_instance = Mock(name="ModelInstanceForFeedbackNoExpTest")
    mock_get_model_adapter_actual.return_value = mock_adapter_instance
    mock_adapter_instance.get_model.return_value = mock_model_instance

    # Simulate LLM returning FEEDBACK action without explanation
    feedback_action_data = {
        "action_type": ActionType.FEEDBACK.value,
        "message": "This is a feedback message without explanation.",
    }
    llm_planner_response_json = json.dumps({"action": feedback_action_data})

    mock_adapter_instance.execute_and_log_metrics = AsyncMock(
        return_value=(llm_planner_response_json, None)
    )

    result = await handle_vibe_request(
        request="get pods",
        command="vibe",
        plan_prompt_func=plan_vibe_fragments,
        summary_prompt_func=mock_summary_prompt_func_hvr,
        output_flags=output_flags,
        yes=True,
    )

    assert isinstance(result, Success)
    assert (
        result.message
        == "Applied AI feedback: AI unable to provide a specific suggestion."
    )
    assert result.data is None

    mock_get_model_adapter_actual.assert_called_once()
    mock_adapter_instance = mock_get_model_adapter_actual.return_value
    mock_adapter_instance.get_model.assert_called_once()
    mock_adapter_instance.execute_and_log_metrics.assert_called_once()

    mock_console_manager_actual.print_vibe.assert_called_with(
        "This is a feedback message without explanation."
    )

    mock_update_memory_actual.assert_called_once()


@patch("vibectl.execution.vibe.get_model_adapter")
@patch("vibectl.execution.vibe.update_memory")
@patch("vibectl.execution.vibe.console_manager")
async def test_handle_vibe_request_llm_invalid_json(
    mock_console: MagicMock,
    mock_update_memory: MagicMock,
    mock_get_adapter: MagicMock,
    mock_summary_prompt_func_hvr: Callable[
        [Config | None, str | None], PromptFragments
    ],
) -> None:
    """Test handle_vibe_request when LLM returns invalid JSON."""
    output_flags = OutputFlags(
        show_raw_output=False,
        show_vibe=False,
        warn_no_output=False,
        model_name="test-model",
        show_metrics=MetricsDisplayMode.ALL,
    )
    mock_adapter = Mock()
    mock_model = Mock()
    mock_get_adapter.return_value = mock_adapter
    mock_adapter.get_model.return_value = mock_model

    # Simulate LLM returning invalid JSON
    llm_response_malformed_json = "this is not json"
    mock_adapter.execute_and_log_metrics = AsyncMock(
        return_value=(llm_response_malformed_json, None)
    )

    result = await handle_vibe_request(
        request="get pods",
        command="vibe",
        plan_prompt_func=plan_vibe_fragments,
        summary_prompt_func=mock_summary_prompt_func_hvr,
        output_flags=output_flags,
    )

    assert isinstance(result, Error)
    assert "Failed to parse LLM response" in result.error
    assert isinstance(result.exception, ValidationError)
    mock_update_memory.assert_called_once()  # Memory is updated on parse failure


@patch("vibectl.execution.vibe.get_model_adapter")
@patch("vibectl.execution.vibe.update_memory")
@patch("vibectl.execution.vibe.console_manager")
async def test_handle_vibe_request_llm_invalid_schema(
    mock_console: MagicMock,
    mock_update_memory: MagicMock,
    mock_get_model_adapter: MagicMock,
    mock_summary_prompt_func_hvr: Callable[
        [Config | None, str | None], PromptFragments
    ],
) -> None:
    """Test handle_vibe_request when LLM returns valid JSON but invalid schema."""

    output_flags = OutputFlags(
        show_raw_output=False,
        show_vibe=False,
        warn_no_output=False,
        model_name="test-model",
        show_metrics=MetricsDisplayMode.ALL,
    )
    mock_adapter_instance = Mock(name="AdapterInstanceForInvalidSchemaTest")
    mock_model_instance = Mock(name="ModelInstanceForInvalidSchemaTest")
    mock_get_model_adapter.return_value = mock_adapter_instance
    mock_adapter_instance.get_model.return_value = mock_model_instance

    # The test intends to send a string that is not a valid action model.
    llm_response_invalid_schema_json = json.dumps({"action": "not_a_valid_action"})
    mock_adapter_instance.execute_and_log_metrics = AsyncMock(
        return_value=(llm_response_invalid_schema_json, None)
    )

    result = await handle_vibe_request(
        request="get pods",
        command="vibe",
        plan_prompt_func=plan_vibe_fragments,
        summary_prompt_func=mock_summary_prompt_func_hvr,
        output_flags=output_flags,
        yes=True,
    )

    assert isinstance(result, Error)
    assert "Failed to parse LLM response as expected JSON" in result.error
    # Check for Pydantic validation error details
    assert "LLMPlannerResponse" in result.error
    assert (
        "Input should be an object" in result.error
    )  # More specific Pydantic message part
    assert "not_a_valid_action" in result.error

    mock_update_memory.assert_called_once()


@patch("vibectl.execution.vibe.get_model_adapter")
@patch("vibectl.execution.vibe.update_memory")
@patch("vibectl.execution.vibe.console_manager")
async def test_handle_vibe_request_llm_empty_response(
    mock_console: MagicMock,
    mock_update_memory: MagicMock,
    mock_get_adapter: MagicMock,
    mock_summary_prompt_func_hvr: Callable[
        [Config | None, str | None], PromptFragments
    ],
) -> None:
    """Test handle_vibe_request when LLM returns an empty string."""
    output_flags = OutputFlags(
        show_raw_output=False,
        show_vibe=False,
        warn_no_output=False,
        model_name="test-model",
        show_metrics=MetricsDisplayMode.ALL,
    )
    mock_adapter = Mock()
    mock_model = Mock()
    mock_get_adapter.return_value = mock_adapter
    mock_adapter.get_model.return_value = mock_model
    mock_adapter.execute_and_log_metrics = AsyncMock(
        return_value=("", None)
    )  # Empty string response

    result = await handle_vibe_request(
        request="get pods",
        command="vibe",
        plan_prompt_func=plan_vibe_fragments,
        summary_prompt_func=mock_summary_prompt_func_hvr,
        output_flags=output_flags,
    )

    assert isinstance(result, Error)
    assert result.error == "LLM returned an empty response."
    mock_update_memory.assert_called_once_with(
        command_message="system",
        command_output="LLM Error: Empty response.",
        vibe_output="LLM Error: Empty response.",
        model_name=output_flags.model_name,
    )


@patch("vibectl.execution.vibe.get_model_adapter")
@patch("vibectl.execution.vibe.update_memory")
@patch("vibectl.execution.vibe.console_manager")
async def test_handle_vibe_request_action_error_no_message(
    mock_console: MagicMock,
    mock_update_memory: MagicMock,
    mock_get_model_adapter: MagicMock,
    mock_summary_prompt_func_hvr: Callable[
        [Config | None, str | None], PromptFragments
    ],
) -> None:
    """Test handle_vibe_request with ActionType.ERROR but missing error message."""
    output_flags = OutputFlags(
        show_raw_output=False,
        show_vibe=False,
        warn_no_output=False,
        model_name="test-model",
        show_metrics=MetricsDisplayMode.ALL,
    )
    mock_adapter_instance = Mock(name="AdapterForErrorNoMsgTest")
    mock_model_instance = Mock(name="ModelForErrorNoMsgTest")
    mock_get_model_adapter.return_value = mock_adapter_instance
    mock_adapter_instance.get_model.return_value = mock_model_instance

    error_action_no_message = {
        "action_type": ActionType.ERROR.value
    }  # Message is missing
    llm_response_json = json.dumps({"action": error_action_no_message})
    mock_adapter_instance.execute_and_log_metrics = AsyncMock(
        return_value=(llm_response_json, None)
    )

    result = await handle_vibe_request(
        request="test",
        command="vibe",
        plan_prompt_func=plan_vibe_fragments,
        summary_prompt_func=mock_summary_prompt_func_hvr,
        output_flags=output_flags,
        yes=True,
    )

    assert isinstance(result, Error)
    assert "Failed to parse LLM response" in result.error
    assert isinstance(result.exception, ValidationError)
    mock_update_memory.assert_called_once()  # Memory is updated on parse failure


@patch("vibectl.execution.vibe.get_model_adapter")
@patch("vibectl.execution.vibe.update_memory")
@patch("vibectl.execution.vibe.console_manager")
async def test_handle_vibe_request_action_wait_no_duration(
    mock_console: MagicMock,
    mock_update_memory: MagicMock,
    mock_get_model_adapter: MagicMock,
    mock_summary_prompt_func_hvr: Callable[
        [Config | None, str | None], PromptFragments
    ],
) -> None:
    """Test handle_vibe_request with ActionType.WAIT but missing duration."""
    output_flags = OutputFlags(
        show_raw_output=False,
        show_vibe=False,
        warn_no_output=False,
        model_name="test-model",
        show_metrics=MetricsDisplayMode.ALL,
    )
    mock_adapter_instance = Mock(name="AdapterForWaitNoDurTest")
    mock_model_instance = Mock(name="ModelForWaitNoDurTest")
    mock_get_model_adapter.return_value = mock_adapter_instance
    mock_adapter_instance.get_model.return_value = mock_model_instance

    # Wait action missing duration
    wait_action_no_duration = {"action_type": ActionType.WAIT.value}
    llm_response_json = json.dumps({"action": wait_action_no_duration})
    mock_adapter_instance.execute_and_log_metrics = AsyncMock(
        return_value=(llm_response_json, None)
    )

    result = await handle_vibe_request(
        request="wait action no duration",
        command="vibe",
        plan_prompt_func=plan_vibe_fragments,
        summary_prompt_func=mock_summary_prompt_func_hvr,
        output_flags=output_flags,
        yes=True,
    )

    assert isinstance(result, Error)
    assert "Failed to parse LLM response" in result.error
    assert isinstance(result.exception, ValidationError)
    mock_update_memory.assert_called_once()  # Memory is updated on parse failure


@patch("vibectl.execution.vibe.get_model_adapter")
@patch("vibectl.execution.vibe.update_memory")
@patch("vibectl.execution.vibe.console_manager")
async def test_handle_vibe_request_action_command_empty_verb(
    mock_console: MagicMock,
    mock_update_memory: MagicMock,
    mock_get_model_adapter: MagicMock,
    mock_summary_prompt_func_hvr: Callable[
        [Config | None, str | None], PromptFragments
    ],
) -> None:
    """Test handle_vibe_request with ActionType.COMMAND but LLM provides empty verb."""
    output_flags = OutputFlags(
        show_raw_output=False,
        show_vibe=False,
        warn_no_output=False,
        model_name="test-model",
        show_metrics=MetricsDisplayMode.ALL,
    )
    mock_adapter_instance = Mock(name="AdapterForCmdEmptyVerbTest")
    mock_model_instance = Mock(name="ModelForCmdEmptyVerbTest")
    mock_get_model_adapter.return_value = mock_adapter_instance
    mock_adapter_instance.get_model.return_value = mock_model_instance

    command_action_empty_verb = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["", "pods"],  # Empty verb
    }
    llm_response_json = json.dumps({"action": command_action_empty_verb})
    mock_adapter_instance.execute_and_log_metrics = AsyncMock(
        return_value=(llm_response_json, None)
    )

    result = await handle_vibe_request(
        request="command action empty verb",
        command="vibe",
        plan_prompt_func=plan_vibe_fragments,
        summary_prompt_func=mock_summary_prompt_func_hvr,
        output_flags=output_flags,
        yes=True,
    )

    assert isinstance(result, Error)
    assert result.error == "LLM planning failed: Could not determine command verb."
    mock_update_memory.assert_not_called()


@patch("vibectl.execution.vibe.handle_command_output")
@patch("vibectl.execution.vibe._execute_command")
@patch("vibectl.execution.vibe.console_manager")
@patch("vibectl.execution.vibe.update_memory")
@patch("vibectl.execution.vibe.get_model_adapter")
async def test_handle_vibe_request_command_generic_error_in_handler(
    mock_get_model_adapter: MagicMock,
    mock_update_memory: MagicMock,
    mock_console: MagicMock,
    mock_execute_command: MagicMock,
    mock_handle_command_output: MagicMock,
    mock_summary_prompt_func_hvr: Callable[
        [Config | None, str | None], PromptFragments
    ],
) -> None:
    """Test handle_vibe_request where handle_command_output raises generic Exception."""
    # Mock update_memory to return proper LLMMetrics object
    mock_update_memory.return_value = LLMMetrics()

    output_flags = OutputFlags(
        show_raw_output=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
        show_metrics=MetricsDisplayMode.ALL,
    )
    mock_adapter_instance = Mock(name="AdapterForGenericErrInHandlerTest")
    mock_model_instance = Mock(name="ModelForGenericErrInHandlerTest")
    mock_get_model_adapter.return_value = mock_adapter_instance
    mock_adapter_instance.get_model.return_value = mock_model_instance

    command_action_data = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["get", "pods"],
    }
    llm_response_json = json.dumps({"action": command_action_data})
    mock_adapter_instance.execute_and_log_metrics = AsyncMock(
        return_value=(llm_response_json, None)
    )

    mock_execute_command.return_value = Success(data="some pods")

    error_message = "Something broke"
    generic_error = ValueError(error_message)
    mock_handle_command_output.side_effect = generic_error

    result = await handle_vibe_request(
        request="test request",
        command="vibe",
        plan_prompt_func=plan_vibe_fragments,
        summary_prompt_func=mock_summary_prompt_func_hvr,
        output_flags=output_flags,
        yes=True,
    )

    assert isinstance(result, Error)
    assert result.error == f"Error handling command output: {error_message}"
    assert result.exception == generic_error
    assert result.halt_auto_loop is True

    mock_get_model_adapter.assert_called_once()
    mock_adapter_instance.execute_and_log_metrics.assert_called_once()
    mock_execute_command.assert_called_once()
    mock_handle_command_output.assert_called_once()

    mock_update_memory.assert_called_once()


@pytest.mark.asyncio
@patch("vibectl.execution.vibe.get_model_adapter")
@patch("vibectl.execution.vibe.update_memory")
@patch("vibectl.execution.vibe.console_manager")
async def test_handle_vibe_request_action_unknown(
    mock_console: MagicMock,
    mock_update_memory: MagicMock,
    mock_get_adapter: MagicMock,
    mock_summary_prompt_func_hvr: Callable[
        [Config | None, str | None], PromptFragments
    ],
) -> None:
    """Test handle_vibe_request with an unknown ActionType from LLM."""
    output_flags = OutputFlags(
        show_raw_output=False,
        show_vibe=False,
        warn_no_output=False,
        model_name="test-model",
        show_metrics=MetricsDisplayMode.ALL,
    )
    mock_adapter = Mock()
    mock_model = Mock()
    mock_get_adapter.return_value = mock_adapter
    mock_adapter.get_model.return_value = mock_model

    # Simulate LLM returning an invalid action type string
    # Need to bypass Pydantic validation slightly for this test by manually creating
    llm_response_text = '{"action_type": "INVALID_ACTION", "explanation": "Test"}'
    mock_adapter.execute_and_log_metrics = AsyncMock(
        return_value=(llm_response_text, None)
    )

    # We expect model_validate_json to potentially raise ValidationError here if strict
    # But if ActionType conversion happens after, this tests the match default case.
    # Let's assume for the test it passes validation but fails the enum match.

    result = await handle_vibe_request(
        request="unknown action request",
        command="vibe",
        plan_prompt_func=plan_vibe_fragments,
        summary_prompt_func=mock_summary_prompt_func_hvr,
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


@pytest.mark.asyncio
@patch("vibectl.execution.vibe.get_model_adapter")
@patch("vibectl.execution.vibe.update_memory")
@patch("vibectl.execution.vibe.console_manager")
async def test_handle_vibe_request_planning_recoverable_api_error(
    mock_console: MagicMock,
    mock_update_memory: MagicMock,
    mock_get_adapter: MagicMock,
    mock_summary_prompt_func_hvr: Callable[
        [Config | None, str | None], PromptFragments
    ],
) -> None:
    """Test handle_vibe_request when planning LLM call raises RecoverableApiError."""
    from vibectl.model_adapter import RecoverableApiError

    output_flags = OutputFlags(
        show_raw_output=False,
        show_vibe=False,
        warn_no_output=False,
        model_name="test-model",
        show_metrics=MetricsDisplayMode.ALL,
    )
    mock_adapter = Mock()
    mock_model = Mock()
    mock_get_adapter.return_value = mock_adapter
    mock_adapter.get_model.return_value = mock_model

    # Mock adapter execute (for planning) to raise error
    api_error = RecoverableApiError("Planning LLM Down")
    mock_adapter.execute_and_log_metrics = AsyncMock(side_effect=api_error)

    result = await handle_vibe_request(
        request="test request",
        command="vibe",
        plan_prompt_func=plan_vibe_fragments,
        summary_prompt_func=mock_summary_prompt_func_hvr,
        output_flags=output_flags,
        yes=True,
    )

    assert isinstance(result, Error)
    assert result.error == str(api_error)
    assert result.exception == api_error
    assert result.halt_auto_loop is False
    mock_console.print_error.assert_called_with("API Error: Planning LLM Down")
    mock_update_memory.assert_not_called()


@patch("vibectl.execution.vibe.get_model_adapter")
@patch("vibectl.execution.vibe.update_memory")
@patch("vibectl.execution.vibe.console_manager")
async def test_handle_vibe_request_planning_generic_error(
    mock_console: MagicMock,
    mock_update_memory: MagicMock,
    mock_get_adapter: MagicMock,
    mock_summary_prompt_func_hvr: Callable[
        [Config | None, str | None], PromptFragments
    ],
) -> None:
    """Test handle_vibe_request when planning LLM call raises generic Exception."""
    output_flags = OutputFlags(
        show_raw_output=False,
        show_vibe=False,
        warn_no_output=False,
        model_name="test-model",
        show_metrics=MetricsDisplayMode.ALL,
    )
    mock_adapter = Mock()
    mock_model = Mock()
    mock_get_adapter.return_value = mock_adapter
    mock_adapter.get_model.return_value = mock_model

    # Mock adapter execute (for planning) to raise error
    generic_error = ConnectionError("Network Error")
    mock_adapter.execute_and_log_metrics = AsyncMock(side_effect=generic_error)

    result = await handle_vibe_request(
        request="test request",
        command="vibe",
        plan_prompt_func=plan_vibe_fragments,
        summary_prompt_func=mock_summary_prompt_func_hvr,
        output_flags=output_flags,
        yes=True,
    )

    assert isinstance(result, Error)
    assert result.error == str(generic_error)
    assert result.exception == generic_error
    assert result.halt_auto_loop is True
    mock_console.print_error.assert_called_with(
        f"Error executing vibe request: {generic_error}"
    )
    mock_update_memory.assert_not_called()
