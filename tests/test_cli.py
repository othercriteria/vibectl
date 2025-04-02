"""
Tests for vibectl CLI
"""

import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner
from pytest import MonkeyPatch

from vibectl import __version__
from vibectl.cli import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def mock_config_dir(tmp_path: Path, monkeypatch: MonkeyPatch) -> Path:
    """Create a temporary config directory and set XDG_CONFIG_HOME"""
    config_dir = tmp_path / "config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return config_dir


def test_cli_version_flag(runner: CliRunner) -> None:
    """Test CLI --version flag"""
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "version" in result.output.lower()


def test_version_command(runner: CliRunner) -> None:
    """Test version command output and kubectl version handling"""
    # Mock successful kubectl version call
    mock_result = Mock()
    mock_result.stdout = (
        '{"clientVersion": {"major": "1", "minor": "27", "gitVersion": "v1.27.3"}}'
    )

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        result = runner.invoke(cli, ["version"])
        assert result.exit_code == 0
        assert f"vibectl version {__version__}" in result.output
        assert "kubectl client version" in result.output
        mock_run.assert_called_once_with(
            ["kubectl", "version", "--client", "--output=json"],
            check=True,
            text=True,
            capture_output=True,
        )

    # Test handling of missing kubectl
    with patch("subprocess.run", side_effect=FileNotFoundError()):
        result = runner.invoke(cli, ["version"])
        assert result.exit_code == 0
        assert f"vibectl version {__version__}" in result.output
        assert "kubectl version information not available" in result.output


def test_proxy_command(runner: CliRunner, mock_config_dir: Path) -> None:
    """Test that proxy properly forwards commands to kubectl with config"""
    mock_result = Mock()
    mock_result.stdout = "mock kubectl output\n"
    mock_result.stderr = ""

    # Mock the Config class to return a specific kubeconfig path
    mock_config = Mock()
    mock_config.get.return_value = "/test/kubeconfig"

    with patch("subprocess.run", return_value=mock_result) as mock_run, patch(
        "vibectl.cli.Config", return_value=mock_config
    ):
        result = runner.invoke(cli, ["proxy", "get", "pods"])

        assert result.exit_code == 0
        mock_run.assert_called_once()
        cmd_args = mock_run.call_args[0][0]
        assert cmd_args == [
            "kubectl",
            "--kubeconfig",
            "/test/kubeconfig",
            "get",
            "pods",
        ]


def test_proxy_command_no_args(runner: CliRunner, mock_config_dir: Path) -> None:
    """Test proxy command with no arguments"""
    result = runner.invoke(cli, ["proxy"])
    assert result.exit_code == 1
    assert "Usage: vibectl proxy <kubectl commands>" in result.output


def test_proxy_kubectl_not_found(runner: CliRunner, mock_config_dir: Path) -> None:
    """Test error handling when kubectl is not found"""
    with patch("subprocess.run", side_effect=FileNotFoundError()):
        result = runner.invoke(cli, ["proxy", "get", "pods"])
        assert result.exit_code == 1
        assert "kubectl not found" in result.output


def test_proxy_kubectl_error(runner: CliRunner, mock_config_dir: Path) -> None:
    """Test error handling when kubectl returns an error"""
    mock_error = subprocess.CalledProcessError(1, ["kubectl"])
    mock_error.stderr = "mock kubectl error\n"

    with patch("subprocess.run", side_effect=mock_error):
        result = runner.invoke(cli, ["proxy", "get", "pods"])
        assert result.exit_code == 1
        assert "Error:" in result.output


def test_config_show(runner: CliRunner, mock_config_dir: Path) -> None:
    """Test config show command"""
    result = runner.invoke(cli, ["config", "show"])
    assert result.exit_code == 0
    assert "vibectl Configuration" in result.output


def test_config_set_and_show(runner: CliRunner, mock_config_dir: Path) -> None:
    """Test config set command and verify with show"""
    # Set the config
    result = runner.invoke(cli, ["config", "set", "kubeconfig", "/test/path"])
    assert result.exit_code == 0
    assert "Set kubeconfig to /test/path" in result.output

    # Verify the config
    result = runner.invoke(cli, ["config", "show"])
    assert result.exit_code == 0
    assert "/test/path" in result.output


def test_vibe_command(runner: CliRunner, mock_config_dir: Path) -> None:
    """Test vibe command"""
    result = runner.invoke(cli, ["vibe"])
    assert result.exit_code == 0
    assert "Checking cluster vibes" in result.output


def test_cli_help(runner: CliRunner) -> None:
    """Test help output"""
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "Usage:" in result.output
    assert "Commands:" in result.output
    for command in ["config", "proxy", "version", "vibe"]:
        assert command in result.output


def test_config_help(runner: CliRunner) -> None:
    """Test config subcommand help output"""
    result = runner.invoke(cli, ["config", "--help"])
    assert result.exit_code == 0
    assert "Usage:" in result.output
    assert "Commands:" in result.output
    for subcommand in ["set", "show"]:
        assert subcommand in result.output
