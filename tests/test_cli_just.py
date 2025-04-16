"""Tests for the 'just' subcommand of the CLI.

Fixtures used are provided by conftest.py and fixtures.py.
"""

import subprocess
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from vibectl.cli import cli


@patch("vibectl.subcommands.just_cmd.subprocess.run")
@patch("vibectl.subcommands.just_cmd.Config")
def test_just_basic(mock_config: Mock, mock_subprocess_run: Mock) -> None:
    """Test basic just command functionality."""
    mock_config.return_value.get.return_value = None  # No kubeconfig set
    result = CliRunner().invoke(cli, ["just", "get", "pods"])
    assert result.exit_code == 0
    mock_subprocess_run.assert_called_once_with(
        ["kubectl", "get", "pods"], check=True, text=True, capture_output=True
    )


@patch("vibectl.subcommands.just_cmd.subprocess.run")
@patch("vibectl.subcommands.just_cmd.Config")
def test_just_with_kubeconfig(mock_config: Mock, mock_subprocess_run: Mock) -> None:
    """Test just command with kubeconfig."""
    mock_config.return_value.get.return_value = "/path/to/kubeconfig"
    result = CliRunner().invoke(cli, ["just", "get", "pods"])
    assert result.exit_code == 0
    mock_subprocess_run.assert_called_once_with(
        ["kubectl", "--kubeconfig", "/path/to/kubeconfig", "get", "pods"],
        check=True,
        text=True,
        capture_output=True,
    )


def test_just_no_args(cli_runner: CliRunner, caplog: pytest.LogCaptureFixture) -> None:
    """Test just command without arguments."""
    result = cli_runner.invoke(cli, ["just"])
    assert result.exit_code == 1
    assert "No arguments provided to 'just' subcommand." in caplog.text


@patch("vibectl.subcommands.just_cmd.subprocess.run")
@patch("vibectl.subcommands.just_cmd.Config")
def test_just_kubectl_not_found(
    mock_config: Mock, mock_subprocess_run: Mock, cli_runner: CliRunner
) -> None:
    """Test just command when kubectl is not found."""
    mock_subprocess_run.side_effect = FileNotFoundError()
    result = cli_runner.invoke(cli, ["just", "get", "pods"])
    assert result.exit_code == 1
    assert "kubectl not found in PATH" in result.output


@patch("vibectl.subcommands.just_cmd.subprocess.run")
@patch("vibectl.subcommands.just_cmd.Config")
def test_just_called_process_error_with_stderr(
    mock_config: Mock, mock_subprocess_run: Mock, cli_runner: CliRunner
) -> None:
    """Test just command with CalledProcessError and stderr."""
    error = subprocess.CalledProcessError(1, ["kubectl"], stderr="test error")
    mock_subprocess_run.side_effect = error
    result = cli_runner.invoke(cli, ["just", "get", "pods"])
    assert result.exit_code == 1
    assert "Error: test error" in result.output


@patch("vibectl.subcommands.just_cmd.subprocess.run")
@patch("vibectl.subcommands.just_cmd.Config")
def test_just_called_process_error_no_stderr(
    mock_config: Mock, mock_subprocess_run: Mock, cli_runner: CliRunner
) -> None:
    """Test just command with CalledProcessError but no stderr."""
    error = subprocess.CalledProcessError(1, ["kubectl"], stderr="")
    mock_subprocess_run.side_effect = error
    result = cli_runner.invoke(cli, ["just", "get", "pods"])
    assert result.exit_code == 1
    assert "Error: Command failed with exit code 1" in result.output
