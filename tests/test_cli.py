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
        '{"clientVersion":{"major":"1","minor":"27"},'
        '"serverVersion":{"major":"1","minor":"27"}}'
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
    """Test config commands"""

    def test_config_show(self, runner: CliRunner, mock_config_dir: Path) -> None:
        """Test config show command"""
        # First set a test value
        runner.invoke(cli, ["config", "set", "kubeconfig", "/test/path"])

        # Then verify it shows up in config show
        result = runner.invoke(cli, ["config", "show"])
        assert result.exit_code == 0
        # We now directly print to console rather than using print_config_table
        assert "vibectl Configuration" in result.output

    def test_config_set_and_show(
        self, runner: CliRunner, mock_config_dir: Path
    ) -> None:
        """Test config set command and verify with show"""
        # Set the config
        result = runner.invoke(cli, ["config", "set", "kubeconfig", "/test/path"])
        assert result.exit_code == 0
        assert "Configuration kubeconfig set to /test/path" in result.output

        # Verify it was set
        result = runner.invoke(cli, ["config", "show"])
        assert result.exit_code == 0
        assert "kubeconfig" in result.output
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


class TestInstructionsCommands:
    """Test custom instructions commands"""

    def test_instructions_set(self, runner: CliRunner, mock_config_dir: Path) -> None:
        """Test instructions set command"""
        # Set the instructions
        result = runner.invoke(cli, ["instructions", "set", "Use a ton of emojis! 😁"])
        assert result.exit_code == 0
        assert "Custom instructions set successfully" in result.output

        # Verify they were set
        result = runner.invoke(cli, ["instructions", "show"])
        assert result.exit_code == 0
        assert "Use a ton of emojis! 😁" in result.output

    def test_instructions_clear(self, runner: CliRunner, mock_config_dir: Path) -> None:
        """Test instructions clear command"""
        # First set some instructions
        runner.invoke(cli, ["instructions", "set", "Use a ton of emojis! 😁"])

        # Then clear them
        result = runner.invoke(cli, ["instructions", "clear"])
        assert result.exit_code == 0
        assert "Custom instructions cleared" in result.output

        # Verify they were cleared
        result = runner.invoke(cli, ["instructions", "show"])
        assert result.exit_code == 0
        assert "No custom instructions set" in result.output

    def test_instructions_multiline_input(
        self, runner: CliRunner, mock_config_dir: Path
    ) -> None:
        """Test setting multiline instructions via stdin"""
        # Create multiline input
        input_text = "Focus on security issues.\nRedact the last 3 octets of IPs."

        # Set instructions with multiline input
        result = runner.invoke(cli, ["instructions", "set"], input=input_text)
        assert result.exit_code == 0
        assert "Custom instructions set successfully" in result.output

        # Verify they were set
        result = runner.invoke(cli, ["instructions", "show"])
        assert result.exit_code == 0
        assert "Focus on security issues." in result.output
        assert "Redact the last 3 octets of IPs." in result.output
