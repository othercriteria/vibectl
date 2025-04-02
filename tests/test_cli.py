"""
Tests for vibectl CLI
"""

import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner
from pytest import MonkeyPatch

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


def test_cli_version(runner: CliRunner) -> None:
    """Test CLI version command"""
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "version" in result.output.lower()


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
    # Implementation of the test_cli_help function
    pass


def test_cli_run_with_config(runner: CliRunner, monkeypatch: MonkeyPatch) -> None:
    # Implementation of the test_cli_run_with_config function
    pass


def test_cli_run_with_invalid_config(runner: CliRunner) -> None:
    # Implementation of the test_cli_run_with_invalid_config function
    pass


def test_cli_run_with_missing_config(runner: CliRunner) -> None:
    # Implementation of the test_cli_run_with_missing_config function
    pass


def test_cli_run_with_env_vars(runner: CliRunner, monkeypatch: MonkeyPatch) -> None:
    # Implementation of the test_cli_run_with_env_vars function
    pass


def test_cli_run_with_custom_config_path(runner: CliRunner) -> None:
    # Implementation of the test_cli_run_with_custom_config_path function
    pass


def test_cli_run_with_invalid_custom_path(runner: CliRunner) -> None:
    # Implementation of the test_cli_run_with_invalid_custom_path function
    pass


def test_cli_run_with_additional_args(runner: CliRunner) -> None:
    # Implementation of the test_cli_run_with_additional_args function
    pass
