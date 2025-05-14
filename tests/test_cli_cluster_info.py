"""Tests for the CLI cluster-info command.

This module tests the cluster-info command functionality of vibectl.
"""

from unittest.mock import Mock, patch

import pytest

from vibectl.subcommands.cluster_info_cmd import run_cluster_info_command
from vibectl.types import Error, Success


@pytest.mark.asyncio
@patch("vibectl.subcommands.cluster_info_cmd.run_kubectl")
@patch("vibectl.subcommands.cluster_info_cmd.handle_command_output")
async def test_cluster_info_basic(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
) -> None:
    """Test basic cluster-info command functionality."""
    # Setup
    mock_run_kubectl.return_value = (
        "Kubernetes control plane is running at https://example:6443"
    )
    mock_handle_output.return_value = Success()

    # Execute directly
    result = await run_cluster_info_command(
        args=(),
        show_raw_output=None,
        show_vibe=None,
        model=None,
        freeze_memory=False,
        unfreeze_memory=False,
        show_kubectl=None,
    )

    # Assert
    assert isinstance(result, Success)
    mock_run_kubectl.assert_called_once_with(["cluster-info"], capture=True)
    mock_handle_output.assert_called_once()


@pytest.mark.asyncio
@patch("vibectl.subcommands.cluster_info_cmd.run_kubectl")
@patch("vibectl.subcommands.cluster_info_cmd.handle_command_output")
async def test_cluster_info_with_args(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
) -> None:
    """Test cluster-info command with additional arguments."""
    # Setup
    mock_run_kubectl.return_value = "Detailed cluster info"
    mock_handle_output.return_value = Success()

    # Execute directly
    result = await run_cluster_info_command(
        args=("dump",),
        show_raw_output=None,
        show_vibe=None,
        model=None,
        freeze_memory=False,
        unfreeze_memory=False,
        show_kubectl=None,
    )

    # Assert
    assert isinstance(result, Success)
    mock_run_kubectl.assert_called_once_with(["cluster-info", "dump"], capture=True)
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
    """Test cluster-info command with output flags."""
    # Setup
    mock_configure_flags.return_value = (True, False, False, "custom-model")
    mock_run_kubectl.return_value = (
        "Kubernetes control plane is running at https://example:6443"
    )
    mock_handle_output.return_value = Success()

    # Execute directly
    result = await run_cluster_info_command(
        args=(),
        show_raw_output=True,
        show_vibe=False,
        model="custom-model",
        freeze_memory=False,
        unfreeze_memory=False,
        show_kubectl=None,
    )

    # Assert
    assert isinstance(result, Success)
    mock_run_kubectl.assert_called_once_with(["cluster-info"], capture=True)
    mock_handle_output.assert_called_once()
    mock_configure_flags.assert_called_once_with(
        show_raw_output=True,
        show_vibe=False,
        model="custom-model",
        show_kubectl=None,
        show_metrics=None,
    )


@pytest.mark.asyncio
@patch("vibectl.subcommands.cluster_info_cmd.run_kubectl")
@patch("vibectl.subcommands.cluster_info_cmd.handle_command_output")
async def test_cluster_info_no_output(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
) -> None:
    """Test cluster-info command when kubectl returns no output."""
    # Setup
    mock_run_kubectl.return_value = ""

    # Execute directly
    result = await run_cluster_info_command(
        args=(),
        show_raw_output=None,
        show_vibe=None,
        model=None,
        freeze_memory=False,
        unfreeze_memory=False,
        show_kubectl=None,
    )

    # Assert
    assert isinstance(result, Success)
    mock_run_kubectl.assert_called_once_with(["cluster-info"], capture=True)
    assert not mock_handle_output.called


@pytest.mark.asyncio
@patch("vibectl.subcommands.cluster_info_cmd.configure_output_flags")
@patch("vibectl.subcommands.cluster_info_cmd.configure_memory_flags")
@patch("vibectl.subcommands.cluster_info_cmd.logger")
async def test_cluster_info_vibe_no_request(
    mock_logger: Mock,
    mock_configure_memory: Mock,
    mock_configure_output: Mock,
) -> None:
    """Test cluster-info vibe command without a request."""
    # Execute directly
    result = await run_cluster_info_command(
        args=("vibe",),
        show_raw_output=None,
        show_vibe=None,
        model=None,
        freeze_memory=False,
        unfreeze_memory=False,
        show_kubectl=None,
    )

    # Assert Error is returned
    assert isinstance(result, Error)
    assert "Missing request after 'vibe'" in result.error


@pytest.mark.asyncio
@patch("vibectl.subcommands.cluster_info_cmd.run_kubectl")
@patch("vibectl.subcommands.cluster_info_cmd.handle_command_output")
async def test_cluster_info_error_handling(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
) -> None:
    """Test error handling in cluster-info command."""
    # Setup
    test_exception = Exception("Test error")
    mock_run_kubectl.side_effect = test_exception

    # Execute directly
    result = await run_cluster_info_command(
        args=(),
        show_raw_output=None,
        show_vibe=None,
        model=None,
        freeze_memory=False,
        unfreeze_memory=False,
        show_kubectl=None,
    )

    # Assert
    assert isinstance(result, Error)
    assert result.exception is test_exception
    mock_run_kubectl.assert_called_once_with(["cluster-info"], capture=True)
    mock_handle_output.assert_not_called()
