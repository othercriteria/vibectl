"""Tests for vibectl.subcommands.cluster_info_cmd."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from vibectl.config import DEFAULT_CONFIG
from vibectl.subcommands.cluster_info_cmd import run_cluster_info_command
from vibectl.types import Error, MetricsDisplayMode, OutputFlags, Success


@pytest.fixture
def default_cluster_info_output_flags() -> OutputFlags:
    """Provides default OutputFlags for cluster-info command tests."""
    # Need to cast from DEFAULT_CONFIG for type safety if linter complains
    return OutputFlags(
        show_raw_output=bool(DEFAULT_CONFIG["display"]["show_raw_output"]),
        show_vibe=bool(DEFAULT_CONFIG["display"]["show_vibe"]),
        warn_no_output=bool(DEFAULT_CONFIG["warnings"]["warn_no_output"]),
        model_name=str(DEFAULT_CONFIG["llm"]["model"]),
        show_metrics=MetricsDisplayMode.from_value(
            str(DEFAULT_CONFIG["display"]["show_metrics"])
        ),
        show_kubectl=bool(DEFAULT_CONFIG["display"]["show_kubectl"]),
        warn_no_proxy=bool(DEFAULT_CONFIG["warnings"]["warn_no_proxy"]),
    )


@pytest.mark.asyncio
@patch("vibectl.subcommands.cluster_info_cmd.run_kubectl")
@patch("vibectl.subcommands.cluster_info_cmd.handle_command_output")
async def test_cluster_info_basic(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    default_cluster_info_output_flags: OutputFlags,
) -> None:
    """Test basic cluster-info command functionality."""
    mock_run_kubectl.return_value = Success(
        data="Kubernetes control plane is running at https://example:6443"
    )
    mock_handle_output.return_value = Success()

    # Execute directly
    result = await run_cluster_info_command(
        args=(),
        show_raw_output=default_cluster_info_output_flags.show_raw_output,
        show_vibe=default_cluster_info_output_flags.show_vibe,
        freeze_memory=False,
        unfreeze_memory=False,
    )

    # Assert
    assert isinstance(result, Success)
    mock_run_kubectl.assert_called_once_with(["cluster-info"])
    # handle_command_output is called in a thread, so its mock should be checked
    mock_handle_output.assert_called_once()


@pytest.mark.asyncio
@patch("vibectl.subcommands.cluster_info_cmd.run_kubectl")
@patch("vibectl.subcommands.cluster_info_cmd.handle_command_output")
async def test_cluster_info_with_args(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    default_cluster_info_output_flags: OutputFlags,
) -> None:
    """Test cluster-info command with additional arguments."""
    mock_run_kubectl.return_value = Success(data="Detailed cluster info")
    mock_handle_output.return_value = Success()

    result = await run_cluster_info_command(
        args=("dump",),
        show_raw_output=default_cluster_info_output_flags.show_raw_output,
        show_vibe=default_cluster_info_output_flags.show_vibe,
        freeze_memory=False,
        unfreeze_memory=False,
    )

    assert isinstance(result, Success)
    mock_run_kubectl.assert_called_once_with(["cluster-info", "dump"])
    mock_handle_output.assert_called_once()


@pytest.mark.asyncio
@patch("vibectl.subcommands.cluster_info_cmd.configure_output_flags")
@patch("vibectl.subcommands.cluster_info_cmd.run_kubectl")
@patch("vibectl.subcommands.cluster_info_cmd.handle_command_output")
async def test_cluster_info_with_flags(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    mock_configure_flags: Mock,
) -> None:
    """Test with specific output flags passed to run_cluster_info_command."""
    configured_flags = OutputFlags(
        show_raw_output=True,
        show_vibe=False,
        warn_no_output=True,
        model_name="custom-model",
        show_metrics=MetricsDisplayMode.ALL,
        show_kubectl=True,
        warn_no_proxy=True,
    )
    mock_configure_flags.return_value = configured_flags

    mock_run_kubectl.return_value = Success(
        data="Kubernetes control plane is running at https://example:6443"
    )
    mock_handle_output.return_value = Success()

    result = await run_cluster_info_command(
        args=(),
        show_raw_output=True,
        show_vibe=False,
        freeze_memory=False,
        unfreeze_memory=False,
    )

    assert isinstance(result, Success)
    mock_run_kubectl.assert_called_once_with(["cluster-info"])
    mock_handle_output.assert_called_once()

    mock_configure_flags.assert_called_once_with(
        show_raw_output=True,
        show_vibe=False,
    )
    # Also check that handle_command_output received the flags from mock_configure_flags
    handle_output_call_kwargs = mock_handle_output.call_args.kwargs
    assert handle_output_call_kwargs.get("output_flags") == configured_flags


@pytest.mark.asyncio
@patch("vibectl.subcommands.cluster_info_cmd.run_kubectl")
@patch("vibectl.subcommands.cluster_info_cmd.handle_command_output")
async def test_cluster_info_no_output(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    default_cluster_info_output_flags: OutputFlags,
) -> None:
    """Test cluster-info command when kubectl returns no output (empty data)."""
    mock_run_kubectl.return_value = Success(data="")

    result = await run_cluster_info_command(
        args=(),
        show_raw_output=default_cluster_info_output_flags.show_raw_output,
        show_vibe=default_cluster_info_output_flags.show_vibe,
        freeze_memory=False,
        unfreeze_memory=False,
    )

    assert isinstance(result, Success)
    # The message might be specific to cluster_info_cmd's handling of no output
    # Based on cluster_info_cmd.py, it seems to still call handle_command_output.
    # Let's verify cluster_info_cmd.py's logic for empty output from run_kubectl.
    # cluster_info_cmd.py:
    #   if isinstance(output, Error): return output
    #   await asyncio.to_thread(handle_command_output, output=output, ...)
    # So, handle_command_output IS called. If output.data is empty,
    # handle_command_output behavior is tested elsewhere.
    # This test should ensure run_kubectl is called, and handle_command_output
    # is called with the Success(data="")

    mock_run_kubectl.assert_called_once_with(["cluster-info"])
    mock_handle_output.assert_called_once()
    handle_output_call_kwargs = mock_handle_output.call_args.kwargs
    assert (
        handle_output_call_kwargs.get("output") == mock_run_kubectl.return_value
    )  # output is the Success object


@pytest.mark.asyncio
@patch(
    "vibectl.subcommands.cluster_info_cmd.handle_vibe_request", new_callable=AsyncMock
)
async def test_cluster_info_vibe_no_request_direct(
    mock_handle_vibe_request: AsyncMock,
    default_cluster_info_output_flags: OutputFlags,
) -> None:
    """Test cluster-info vibe command without a request."""

    result = await run_cluster_info_command(
        args=("vibe",),  # Only 'vibe', no request
        show_raw_output=default_cluster_info_output_flags.show_raw_output,
        show_vibe=default_cluster_info_output_flags.show_vibe,
        freeze_memory=False,
        unfreeze_memory=False,
    )

    assert isinstance(result, Error)
    assert "Missing request after 'vibe'" in result.error
    mock_handle_vibe_request.assert_not_called()


@pytest.mark.asyncio
@patch("vibectl.subcommands.cluster_info_cmd.run_kubectl")
@patch("vibectl.subcommands.cluster_info_cmd.handle_command_output")
async def test_cluster_info_error_handling_direct(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    default_cluster_info_output_flags: OutputFlags,
) -> None:
    """Test error handling in cluster-info command."""
    test_exception = RuntimeError(
        "Kubectl simulated error"
    )  # Use RuntimeError for clarity
    # run_kubectl itself (the synchronous one) would return an Error object or raise.
    # If it raises, asyncio.to_thread would propagate it, and
    # run_cluster_info_command catches it.
    # If it returns Error, run_cluster_info_command returns that.
    mock_run_kubectl.return_value = Error(
        error="kubectl error", exception=test_exception
    )

    result = await run_cluster_info_command(
        args=(),
        show_raw_output=default_cluster_info_output_flags.show_raw_output,
        show_vibe=default_cluster_info_output_flags.show_vibe,
        freeze_memory=False,
        unfreeze_memory=False,
    )

    assert isinstance(result, Error)
    assert result.error == "kubectl error"
    assert result.exception is test_exception
    mock_run_kubectl.assert_called_once_with(["cluster-info"])
    mock_handle_output.assert_not_called()
