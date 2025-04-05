"""Tests for the CLI."""

import subprocess
from pathlib import Path
from typing import Any
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


@pytest.fixture
def mock_kubectl_version() -> Mock:
    """Mock successful kubectl version call with JSON output"""
    mock_result = Mock()
    mock_result.stdout = (
        "{"
        '"clientVersion": {'
        '"major": "1", "minor": "27", "gitVersion": "v1.27.3"'
        "}, "
        '"kustomizeVersion": "v5.0.1", '
        '"serverVersion": {'
        '"major": "1", "minor": "27", "gitVersion": "v1.27.3", '
        '"platform": "linux/amd64", "goVersion": "go1.20.3"'
        "}"
        "}"
    )
    return mock_result


@pytest.fixture
def mock_kubectl_success() -> Mock:
    """Mock successful kubectl command execution"""
    mock_result = Mock()
    mock_result.stdout = "mock kubectl output\n"
    mock_result.stderr = ""
    return mock_result


@pytest.fixture
def mock_kubectl_error() -> subprocess.CalledProcessError:
    """Mock kubectl error response"""
    mock_error = subprocess.CalledProcessError(1, ["kubectl"])
    mock_error.stderr = "mock kubectl error\n"
    return mock_error


@pytest.fixture
def mock_config() -> Mock:
    """Mock Config class with test kubeconfig path"""
    mock_config = Mock()
    mock_config.get.return_value = "/test/kubeconfig"
    return mock_config


@pytest.fixture
def mock_llm_response() -> Mock:
    """Mock LLM response for vibe commands"""
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: "mocked response")
    return mock_model


class TestCLIBasics:
    """Basic CLI functionality tests"""

    def test_cli_version_flag(self, runner: CliRunner) -> None:
        """Test CLI --version flag"""
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "version" in result.output.lower()

    def test_cli_help(self, runner: CliRunner) -> None:
        """Test help output"""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "Commands:" in result.output
        for command in ["config", "just", "version", "vibe"]:
            assert command in result.output

    def test_config_help(self, runner: CliRunner) -> None:
        """Test config subcommand help output"""
        result = runner.invoke(cli, ["config", "--help"])
        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "Commands:" in result.output
        for subcommand in ["set", "show"]:
            assert subcommand in result.output


class TestVersionCommand:
    """Version command tests"""

    def test_version_command_json(
        self, runner: CliRunner, mock_kubectl_version: Mock
    ) -> None:
        """Test version command with JSON output"""
        mock_model = Mock()
        mock_model.prompt.return_value = Mock(
            text=lambda: "Interpreted version information"
        )

        with patch("subprocess.run", return_value=mock_kubectl_version), patch(
            "llm.get_model", return_value=mock_model
        ):
            result = runner.invoke(cli, ["version"])
            assert result.exit_code == 0
            assert "Interpreted version information" in result.output

    @pytest.mark.parametrize(
        "error,expected_output",
        [
            (FileNotFoundError(), "kubectl version information not available"),
            (Exception("test error"), "test error"),
        ],
    )
    def test_version_command_errors(
        self, runner: CliRunner, error: Exception, expected_output: str
    ) -> None:
        """Test version command error handling"""
        mock_model = Mock()
        mock_model.prompt.side_effect = Exception("LLM error")

        with patch("subprocess.run", side_effect=error), patch(
            "llm.get_model", return_value=mock_model
        ):
            result = runner.invoke(cli, ["version"])
            assert result.exit_code == 0
            assert expected_output in result.output


class TestJustCommand:
    """Just command tests"""

    def test_just_command(
        self,
        runner: CliRunner,
        mock_config_dir: Path,
        mock_kubectl_success: Mock,
        mock_config: Mock,
    ) -> None:
        """Test that just properly forwards commands to kubectl with config"""

        # Set up a side_effect function to return different values for different keys
        def get_side_effect(key: str, default: Any = None) -> Any:
            if key == "theme":
                return "default"
            if key == "kubeconfig":
                return "/test/kubeconfig"
            return default

        mock_config.get.side_effect = get_side_effect

        with patch(
            "subprocess.run", return_value=mock_kubectl_success
        ) as mock_run, patch("vibectl.cli.Config", return_value=mock_config):
            result = runner.invoke(cli, ["just", "get", "pods"])

            assert result.exit_code == 0
            # Check that kubectl was called with the right arguments
            mock_run.assert_called_once()
            cmd_args = mock_run.call_args[0][0]
            # First check the kubectl command itself
            assert cmd_args[0] == "kubectl"
            # Check that kubeconfig flag is included
            assert "--kubeconfig" in cmd_args
            # Check that the kubeconfig path is correct
            assert "/test/kubeconfig" in cmd_args
            # Check that the "get pods" arguments are included
            assert "get" in cmd_args
            assert "pods" in cmd_args

    def test_just_command_no_args(
        self, runner: CliRunner, mock_config_dir: Path
    ) -> None:
        """Test just command with no arguments"""
        result = runner.invoke(cli, ["just"])
        assert result.exit_code == 1
        assert "Usage: vibectl just <kubectl commands>" in result.output

    @pytest.mark.parametrize(
        "error,expected_output",
        [
            (FileNotFoundError(), "kubectl not found"),
            (subprocess.CalledProcessError(1, ["kubectl"]), "Error:"),
        ],
    )
    def test_just_command_errors(
        self,
        runner: CliRunner,
        mock_config_dir: Path,
        error: Exception,
        expected_output: str,
    ) -> None:
        """Test just command error handling"""
        with patch("subprocess.run", side_effect=error):
            result = runner.invoke(cli, ["just", "get", "pods"])
            assert result.exit_code == 1
            assert expected_output in result.output


class TestConfigCommands:
    """Config command tests"""

    def test_config_show(self, runner: CliRunner, mock_config_dir: Path) -> None:
        """Test config show command"""
        # First set a test value
        runner.invoke(cli, ["config", "set", "kubeconfig", "/test/path"])

        # Then verify it shows up in config show
        with patch(
            "vibectl.cli.console_manager.print_config_table"
        ) as mock_print_table:
            result = runner.invoke(cli, ["config", "show"])
            assert result.exit_code == 0
            # Verify that print_config_table was called
            mock_print_table.assert_called_once()

    def test_config_set_and_show(
        self, runner: CliRunner, mock_config_dir: Path
    ) -> None:
        """Test config set command and verify with show"""
        # Set the config
        result = runner.invoke(cli, ["config", "set", "kubeconfig", "/test/path"])
        assert result.exit_code == 0
        assert "Set kubeconfig to /test/path" in result.output

        # Verify the config
        result = runner.invoke(cli, ["config", "show"])
        assert result.exit_code == 0
        assert "/test/path" in result.output


class TestVibeCommand:
    """Vibe command tests"""

    def test_vibe_command(
        self, runner: CliRunner, mock_config_dir: Path, mock_llm_response: Mock
    ) -> None:
        """Test vibe command"""
        with patch("llm.get_model", return_value=mock_llm_response):
            result = runner.invoke(cli, ["vibe"])
            assert result.exit_code == 0
            assert "Checking cluster vibes" in result.output
