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
@pytest.mark.asyncio
async def test_just_basic(mock_config: Mock, mock_subprocess_run: Mock) -> None:
    """Test basic just command functionality."""
    mock_config.return_value.get.return_value = None  # No kubeconfig set
    mock_subprocess_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="output", stderr=""
    )

    cmd_obj = cli.commands["just"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["get", "pods"])

    assert exc_info.value.code == 0
    mock_subprocess_run.assert_called_once_with(
        ["kubectl", "get", "pods"], check=True, text=True, capture_output=True
    )


@patch("vibectl.subcommands.just_cmd.subprocess.run")
@patch("vibectl.subcommands.just_cmd.Config")
@pytest.mark.asyncio
async def test_just_with_kubeconfig(
    mock_config: Mock, mock_subprocess_run: Mock
) -> None:
    """Test just command with kubeconfig."""
    mock_config.return_value.get.return_value = "/path/to/kubeconfig"
    mock_subprocess_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="output", stderr=""
    )

    cmd_obj = cli.commands["just"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["get", "pods"])

    assert exc_info.value.code == 0
    mock_subprocess_run.assert_called_once_with(
        ["kubectl", "--kubeconfig", "/path/to/kubeconfig", "get", "pods"],
        check=True,
        text=True,
        capture_output=True,
    )


@pytest.mark.asyncio
async def test_just_no_args(
    cli_runner: CliRunner, caplog: pytest.LogCaptureFixture
) -> None:
    """Test just command without arguments."""
    cmd_obj = cli.commands["just"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main([])

    assert exc_info.value.code != 0
    assert "No arguments provided to 'just' subcommand." in caplog.text


@patch("vibectl.subcommands.just_cmd.subprocess.run")
@pytest.mark.asyncio
async def test_just_kubectl_not_found(
    mock_subprocess_run: Mock, cli_runner: CliRunner
) -> None:
    """Test just command when kubectl is not found."""
    mock_subprocess_run.side_effect = FileNotFoundError()

    cmd_obj = cli.commands["just"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["get", "pods"])

    assert exc_info.value.code != 0


@patch("vibectl.subcommands.just_cmd.subprocess.run")
@pytest.mark.asyncio
async def test_just_called_process_error_with_stderr(
    mock_subprocess_run: Mock, cli_runner: CliRunner
) -> None:
    """Test just command with CalledProcessError and stderr."""
    error = subprocess.CalledProcessError(1, ["kubectl"], stderr="test error")
    mock_subprocess_run.side_effect = error

    cmd_obj = cli.commands["just"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["get", "pods"])

    assert exc_info.value.code != 0


@patch("vibectl.subcommands.just_cmd.subprocess.run")
@pytest.mark.asyncio
async def test_just_called_process_error_no_stderr(
    mock_subprocess_run: Mock, cli_runner: CliRunner
) -> None:
    """Test just command with CalledProcessError but no stderr."""
    error = subprocess.CalledProcessError(1, ["kubectl"], stderr="")
    mock_subprocess_run.side_effect = error

    cmd_obj = cli.commands["just"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["get", "pods"])

    assert exc_info.value.code != 0
