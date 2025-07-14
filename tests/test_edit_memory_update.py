"""Test that edit command properly captures vibe output for memory updates."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from vibectl.execution.edit import _apply_patch, run_intelligent_edit_workflow
from vibectl.types import MetricsDisplayMode, OutputFlags, Success


@pytest.mark.asyncio
async def test_apply_patch_captures_vibe_output_for_memory() -> None:
    """Test _apply_patch captures vibe output from handle_command_output for memory."""

    # Mock the kubectl result
    mock_kubectl_result = Success(
        data='{"kind": "Deployment", "metadata": {"name": "test"}}'
    )

    # Mock the vibe output from handle_command_output
    expected_vibe_output = (
        "✅ Successfully updated deployment/test with new resource limits"
    )
    mock_handle_output_result = Success(message=expected_vibe_output)

    with (
        patch("vibectl.execution.edit.run_kubectl", return_value=mock_kubectl_result),
        patch(
            "vibectl.execution.edit.handle_command_output",
            return_value=mock_handle_output_result,
        ) as mock_handle_output,
        patch("vibectl.execution.edit.console_manager") as _mock_console,
    ):
        config = Mock()
        output_flags = OutputFlags(
            show_raw_output=False,
            show_vibe=True,
            warn_no_output=False,
            model_name="test-model",
            show_metrics=MetricsDisplayMode.NONE,
            show_streaming=False,
        )

        # Call _apply_patch
        result = await _apply_patch(
            patch_commands=["deployment", "test", "-p", '{"spec":{"replicas":3}}'],
            output_flags=output_flags,
            config=config,
        )

        # Verify handle_command_output was called
        mock_handle_output.assert_called_once()

        # Verify the result contains the vibe output in the data field
        assert isinstance(result, Success)
        assert result.data == expected_vibe_output
        assert result.message == "Patch applied successfully"


@pytest.mark.asyncio
async def test_apply_patch_handles_vibe_error() -> None:
    """Test that _apply_patch handles errors from handle_command_output gracefully."""
    from vibectl.types import Error

    # Mock the kubectl result
    mock_kubectl_result = Success(
        data='{"kind": "Deployment", "metadata": {"name": "test"}}'
    )

    # Mock handle_command_output returning an error
    mock_handle_output_error = Error(error="Vibe processing failed")

    with (
        patch("vibectl.execution.edit.run_kubectl", return_value=mock_kubectl_result),
        patch(
            "vibectl.execution.edit.handle_command_output",
            return_value=mock_handle_output_error,
        ),
        patch("vibectl.execution.edit.console_manager"),
    ):
        config = Mock()
        output_flags = OutputFlags(
            show_raw_output=False,
            show_vibe=True,
            warn_no_output=False,
            model_name="test-model",
            show_metrics=MetricsDisplayMode.NONE,
            show_streaming=False,
        )

        # Call _apply_patch
        result = await _apply_patch(
            patch_commands=["deployment", "test", "-p", '{"spec":{"replicas":3}}'],
            output_flags=output_flags,
            config=config,
        )

        # Verify the result falls back to raw kubectl output when vibe fails
        assert isinstance(result, Success)
        assert result.data == mock_kubectl_result.data
        assert result.message == "Patch applied successfully"


@pytest.mark.asyncio
async def test_apply_patch_with_show_raw() -> None:
    """Test that _apply_patch works correctly when show_raw is True."""

    # Mock the kubectl result
    mock_kubectl_result = Success(
        data='{"kind": "Deployment", "metadata": {"name": "test"}}'
    )

    with (
        patch("vibectl.execution.edit.run_kubectl", return_value=mock_kubectl_result),
        patch("vibectl.execution.edit.handle_command_output") as mock_handle_output,
        patch("vibectl.execution.edit.console_manager") as mock_console,
    ):
        config = Mock()
        output_flags = OutputFlags(
            show_raw_output=True,
            show_vibe=False,  # Raw mode, no vibe
            warn_no_output=False,
            model_name="test-model",
            show_metrics=MetricsDisplayMode.NONE,
            show_streaming=False,
        )

        # Call _apply_patch
        result = await _apply_patch(
            patch_commands=["deployment", "test", "-p", '{"spec":{"replicas":3}}'],
            output_flags=output_flags,
            config=config,
        )

        # Verify handle_command_output was NOT called (raw mode)
        mock_handle_output.assert_not_called()

        # Verify console.print was called with raw output
        mock_console.print.assert_called_once_with(mock_kubectl_result.data)

        # Verify the result contains the raw kubectl output
        assert isinstance(result, Success)
        assert result.data == mock_kubectl_result.data
        assert result.message == "Patch applied successfully"


@pytest.mark.asyncio
async def test_intelligent_edit_workflow_updates_memory_with_patch_context() -> None:
    """Test that the intelligent edit workflow includes patch context in memory."""

    # Mock all the dependencies
    mock_resource_yaml = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-deployment
spec:
  replicas: 1
"""

    mock_original_summary = "Deployment test-deployment with 1 replica"
    mock_edited_summary = "Deployment test-deployment with 3 replicas"
    mock_patch_commands = [
        "deployment",
        "test-deployment",
        "-p",
        '{"spec":{"replicas":3}}',
    ]
    mock_vibe_output = (
        "✅ Successfully updated deployment/test-deployment with 3 replicas"
    )

    with (
        patch(
            "vibectl.execution.edit._fetch_resource",
            return_value=Success(data=mock_resource_yaml),
        ),
        patch(
            "vibectl.execution.edit._summarize_resource",
            return_value=Success(data=mock_original_summary),
        ),
        patch(
            "vibectl.execution.edit._invoke_editor",
            return_value=Success(data=mock_edited_summary),
        ),
        patch(
            "vibectl.execution.edit._generate_patch_from_changes",
            return_value=Success(data=mock_patch_commands),
        ),
        patch(
            "vibectl.execution.edit._apply_patch",
            return_value=Success(
                data=mock_vibe_output, message="Patch applied successfully"
            ),
        ),
        patch(
            "vibectl.execution.edit.update_memory", new_callable=AsyncMock
        ) as mock_update_memory,
        patch("vibectl.execution.edit.console_manager"),
    ):
        # Mock update_memory to return metrics
        from vibectl.types import LLMMetrics

        mock_metrics = LLMMetrics(
            token_input=50,
            token_output=25,
            latency_ms=100.0,
            total_processing_duration_ms=150.0,
        )
        mock_update_memory.return_value = mock_metrics

        config = Mock()
        output_flags = OutputFlags(
            show_raw_output=False,
            show_vibe=True,
            warn_no_output=False,
            model_name="test-model",
            show_metrics=MetricsDisplayMode.NONE,
            show_streaming=False,
        )

        # Call the intelligent edit workflow
        result = await run_intelligent_edit_workflow(
            resource="deployment/test-deployment",
            args=(),
            output_flags=output_flags,
            config=config,
        )

        # Verify the workflow succeeded
        assert isinstance(result, Success)

        # Verify update_memory was called twice:
        # 1. For patch context (step 6)
        # 2. For operation result (step 8)
        assert mock_update_memory.call_count == 2

        # Check the first call (patch context)
        first_call = mock_update_memory.call_args_list[0]
        first_call_kwargs = first_call[1]
        assert (
            "Generated patch for deployment/test-deployment"
            in first_call_kwargs["command_message"]
        )
        assert "Generated patch commands" in first_call_kwargs["command_output"]
        assert "deployment test-deployment -p" in first_call_kwargs["command_output"]

        # Check the second call (operation result)
        second_call = mock_update_memory.call_args_list[1]
        second_call_kwargs = second_call[1]
        assert (
            "Intelligent edit: deployment/test-deployment"
            in second_call_kwargs["command_message"]
        )
        assert second_call_kwargs["command_output"] == mock_vibe_output
