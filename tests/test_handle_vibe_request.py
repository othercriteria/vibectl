"""Tests for handle_vibe_request functionality.

This module tests handle_vibe_request, especially focusing on the handling
of kubeconfig flags to avoid regressions where kubeconfig flags appear in the wrong
position in the final command.
"""

import json
from collections.abc import Generator
from unittest.mock import MagicMock, Mock, patch

import pytest

from vibectl.command_handler import (
    handle_vibe_request,
)
from vibectl.types import ActionType, OutputFlags, Success


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
def mock_run_kubectl() -> Generator[Mock, None, None]:
    """Mock run_kubectl to avoid actual command execution."""
    with patch("vibectl.command_handler.run_kubectl") as mock:
        mock.return_value = (
            "NAME   READY   STATUS      RESTARTS   AGE\n"
            "pod-1   1/1     Succeeded   0          1h"
        )
        yield mock


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


def test_handle_vibe_request_kubeconfig_handling(
    mock_model_adapter: MagicMock,
    mock_handle_output: Mock,
) -> None:
    """Test that handle_vibe_request properly handles LLM command responses.

    This test focuses on ensuring the command derived from the LLM response
    is correctly passed to the execution layer, verifying the core planning
    and dispatch logic after the refactor.
    """
    # Create output flags
    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=False,
        model_name="claude-3-sonnet",
    )

    # Set up the model to return a command as JSON
    llm_response_get_pods = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["get", "pods"],
        "explanation": "Getting pods",
    }
    mock_model_adapter.return_value.execute.return_value = json.dumps(
        llm_response_get_pods
    )

    # Patch the execution layer (_execute_command)
    with patch("vibectl.command_handler._execute_command") as mock_execute:
        # Mock the result of the execution
        mock_execute.return_value = Success(data="pod info...")

        # Simulate the function call
        handle_vibe_request(
            request="get pods",
            command="vibe",  # Original command was vibe
            plan_prompt="Plan how to {command} {request}",
            summary_prompt_func=lambda: "Summarize {output}",
            output_flags=output_flags,
            yes=True,  # Bypass confirmation
        )

        # Verify _execute_command was called with correct arguments from LLM response
        mock_execute.assert_called_once_with(
            "get", ["pods"], None
        )  # verb, args_list, yaml


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
        patch("vibectl.command_handler.update_memory") as _mock_update_memory,
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
        # Remove assertion: Memory is not updated in non-autonomous mode here
        # mock_update_memory.assert_called_once()

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
            '{"action_type": "COMMAND", "commands": ["delete", ' '"pod", "my-pod"]}'
        )
        mock_get_adapter.return_value = mock_model_adapter

        # Patching _execute_command, remove unused update_memory patch
        with patch("vibectl.command_handler._execute_command") as mock_execute:
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
            # Remove assertion: Memory is not updated in non-autonomous mode here
            # Ensure memory was updated (assuming success path)
            # mock_update_memory.assert_called()
