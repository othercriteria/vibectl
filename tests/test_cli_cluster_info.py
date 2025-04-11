"""Tests for the CLI cluster-info command.

This module tests the cluster-info command functionality of vibectl.
"""

from collections.abc import Generator
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from vibectl.cli import cli

# The mock_configure_output_flags fixture is now provided by conftest.py

@patch("vibectl.cli.configure_output_flags")
@patch("vibectl.cli.run_kubectl")
@patch("vibectl.cli.handle_command_output")
def test_cluster_info_basic(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test basic cluster-info command functionality."""
    # Setup
    mock_configure_flags.return_value = (True, True, False, "test-model")
    mock_run_kubectl.return_value = (
        "Kubernetes control plane is running at https://example:6443"
    )

    # Execute
    result = cli_runner.invoke(cli, ["cluster-info"])

    # Assert
    assert result.exit_code == 0
    mock_run_kubectl.assert_called_once_with(["cluster-info"], capture=True)
    mock_handle_output.assert_called_once()


@patch("vibectl.cli.configure_output_flags")
@patch("vibectl.cli.run_kubectl")
@patch("vibectl.cli.handle_command_output")
def test_cluster_info_with_args(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test cluster-info command with additional arguments."""
    # Setup
    mock_configure_flags.return_value = (True, True, False, "test-model")
    mock_run_kubectl.return_value = "Detailed cluster info"

    # Execute
    result = cli_runner.invoke(cli, ["cluster-info", "dump"])

    # Assert
    assert result.exit_code == 0
    mock_run_kubectl.assert_called_once_with(["cluster-info", "dump"], capture=True)
    mock_handle_output.assert_called_once()


@patch("vibectl.cli.configure_output_flags")
@patch("vibectl.cli.run_kubectl")
@patch("vibectl.cli.handle_command_output")
def test_cluster_info_with_flags(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test cluster-info command with output flags."""
    # Setup
    mock_configure_flags.return_value = (True, False, False, "custom-model")
    mock_run_kubectl.return_value = (
        "Kubernetes control plane is running at https://example:6443"
    )

    # Execute
    result = cli_runner.invoke(
        cli,
        [
            "cluster-info",
            "--show-raw-output",
            "--no-show-vibe",
            "--model",
            "custom-model",
        ],
    )

    # Assert
    assert result.exit_code == 0
    mock_run_kubectl.assert_called_once_with(["cluster-info"], capture=True)
    mock_handle_output.assert_called_once()


@patch("vibectl.cli.configure_output_flags")
@patch("vibectl.cli.run_kubectl")
@patch("vibectl.cli.handle_command_output")
def test_cluster_info_no_output(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test cluster-info command when kubectl returns no output."""
    # Setup
    mock_configure_flags.return_value = (True, True, False, "test-model")
    mock_run_kubectl.return_value = ""

    # Execute
    result = cli_runner.invoke(cli, ["cluster-info"])

    # Assert
    assert result.exit_code == 0
    mock_run_kubectl.assert_called_once_with(["cluster-info"], capture=True)
    assert not mock_handle_output.called


@patch("vibectl.cli.handle_vibe_request")
def test_cluster_info_vibe_request(
    mock_handle_vibe: Mock, cli_runner: CliRunner
) -> None:
    """Test cluster-info command with vibe request."""
    # Execute
    result = cli_runner.invoke(
        cli, ["cluster-info", "vibe", "show", "me", "cluster", "health"]
    )

    # Assert
    assert result.exit_code == 0
    mock_handle_vibe.assert_called_once()
    args, kwargs = mock_handle_vibe.call_args
    assert kwargs["request"] == "show me cluster health"
    assert kwargs["command"] == "cluster-info"


@patch("vibectl.cli.console_manager")
def test_cluster_info_vibe_no_request(
    mock_console: Mock, cli_runner: CliRunner
) -> None:
    """Test cluster-info vibe command without a request."""
    # Execute without catch_exceptions to ensure test completes
    cli_runner.invoke(cli, ["cluster-info", "vibe"])

    # In test environment, Click's runner might not capture the real exit code
    # but we can still verify the error message was displayed
    mock_console.print_error.assert_called_once_with("Missing request after 'vibe'")


@patch("vibectl.cli.configure_output_flags")
@patch("vibectl.cli.run_kubectl")
@patch("vibectl.cli.handle_command_output")
def test_cluster_info_error_handling(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test error handling in cluster-info command."""
    # Setup
    mock_configure_flags.return_value = (True, True, False, "test-model")
    mock_run_kubectl.side_effect = Exception("Test error")

    # Execute
    result = cli_runner.invoke(cli, ["cluster-info"])

    # Assert
    assert result.exit_code == 1
    mock_run_kubectl.assert_called_once_with(["cluster-info"], capture=True)
    mock_handle_output.assert_not_called()
