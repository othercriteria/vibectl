"""Tests for edit command patch generation functionality."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from vibectl.execution.edit import _generate_patch_from_changes
from vibectl.types import Error, LLMMetrics, MetricsDisplayMode, OutputFlags, Success


@pytest.fixture
def output_flags() -> OutputFlags:
    """Standard output flags for testing."""
    return OutputFlags(
        show_raw_output=False,
        show_vibe=True,
        show_kubectl=False,
        warn_no_output=False,
        model_name="claude-3.7-sonnet",
        show_metrics=MetricsDisplayMode.NONE,
        show_streaming=False,
    )


@pytest.fixture
def mock_config() -> Mock:
    """Mock config for testing."""
    config = Mock()
    config.get.return_value = "claude-3.7-sonnet"
    return config


@pytest.fixture
def sample_inputs() -> tuple[str, tuple[str, ...], str, str, str]:
    """Sample inputs for patch generation testing."""
    resource = "deployment/nginx"
    args = ("-n", "default")
    original_summary = "Nginx deployment with 3 replicas"
    summary_diff = (
        "+Nginx deployment with 5 replicas\n-Nginx deployment with 3 replicas"
    )
    original_yaml = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx
  namespace: default
spec:
  replicas: 3
"""
    return resource, args, original_summary, summary_diff, original_yaml


@pytest.mark.asyncio
async def test_generate_patch_handles_error_action(
    sample_inputs: tuple[str, tuple[str, ...], str, str, str],
    output_flags: OutputFlags,
    mock_config: Mock,
) -> None:
    """Test that _generate_patch_from_changes handles ERROR action properly."""
    resource, args, original_summary, summary_diff, original_yaml = sample_inputs

    # Mock LLM response with ERROR action
    error_response_json = """
    {
        "action": {
            "action_type": "ERROR",
            "message": "Cannot generate patch: insufficient information..."
        }
    }
    """

    mock_metrics = LLMMetrics(
        token_input=100,
        token_output=50,
        latency_ms=500,
    )

    with (
        patch("vibectl.execution.edit.get_model_adapter") as mock_get_adapter,
        patch("vibectl.execution.edit.console_manager") as mock_console,
    ):
        # Setup mock adapter
        mock_adapter = Mock()
        mock_model = Mock()
        mock_get_adapter.return_value = mock_adapter
        mock_adapter.get_model.return_value = mock_model

        # Mock the execute_and_log_metrics to return ERROR action
        mock_adapter.execute_and_log_metrics = AsyncMock(
            return_value=(error_response_json, mock_metrics)
        )

        # Call the function
        result = await _generate_patch_from_changes(
            resource=resource,
            args=args,
            original_summary=original_summary,
            summary_diff=summary_diff,
            original_yaml=original_yaml,
            output_flags=output_flags,
            config=mock_config,
        )

        # Verify it returns an Error with the LLM's error message
        assert isinstance(result, Error)
        assert "LLM patch generation error" in result.error
        assert "insufficient information" in result.error
        assert result.metrics == mock_metrics

        # Verify console output was called
        mock_console.print_error.assert_called_once()
        error_call_args = mock_console.print_error.call_args[0][0]
        assert "LLM Patch Generation Error" in error_call_args
        assert "insufficient information" in error_call_args


@pytest.mark.asyncio
async def test_generate_patch_successful_command_action(
    sample_inputs: tuple[str, tuple[str, ...], str, str, str],
    output_flags: OutputFlags,
    mock_config: Mock,
) -> None:
    """Test that _generate_patch_from_changes handles successful COMMAND action."""
    resource, args, original_summary, summary_diff, original_yaml = sample_inputs

    # Mock LLM response with COMMAND action
    command_response_json = """
    {
        "action": {
            "action_type": "COMMAND",
            "commands": [
                "deployment",
                "nginx",
                "-p",
                "[{\\"op\\": \\"replace\\", \\"path\\": \\"/foo\\", \\"value\\": 5}]"
            ],
            "explanation": "Scaling deployment from 3 to 5 replicas based..."
        }
    }
    """

    mock_metrics = LLMMetrics(
        token_input=150,
        token_output=100,
        latency_ms=1000,
    )

    with (
        patch("vibectl.execution.edit.get_model_adapter") as mock_get_adapter,
        patch("vibectl.execution.edit.console_manager") as _mock_console,
    ):
        # Setup mock adapter
        mock_adapter = Mock()
        mock_model = Mock()
        mock_get_adapter.return_value = mock_adapter
        mock_adapter.get_model.return_value = mock_model

        # Mock the execute_and_log_metrics to return COMMAND action
        mock_adapter.execute_and_log_metrics = AsyncMock(
            return_value=(command_response_json, mock_metrics)
        )

        # Call the function
        result = await _generate_patch_from_changes(
            resource=resource,
            args=args,
            original_summary=original_summary,
            summary_diff=summary_diff,
            original_yaml=original_yaml,
            output_flags=output_flags,
            config=mock_config,
        )

        # Verify it returns Success with the patch commands
        assert isinstance(result, Success)
        assert result.metrics == mock_metrics

        # Verify the commands are correct
        expected_commands = [
            "deployment",
            "nginx",
            "-p",
            '[{"op": "replace", "path": "/foo", "value": 5}]',
        ]
        assert result.data == expected_commands
