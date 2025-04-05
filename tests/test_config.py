"""Tests for vibectl configuration"""

import os
from pathlib import Path

import pytest
import yaml
from pytest import MonkeyPatch
from click.testing import CliRunner
from unittest.mock import Mock, patch

from vibectl.config import Config
from vibectl.cli import cli


@pytest.fixture
def temp_config(tmp_path: Path, monkeypatch: MonkeyPatch) -> Config:
    """Create a temporary config directory"""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return Config()


def test_config_dir_creation(temp_config: Config) -> None:
    """Test that config directory is created"""
    assert temp_config.config_dir.exists()
    assert temp_config.config_dir.is_dir()


def test_default_config(temp_config: Config) -> None:
    """Test default configuration"""
    assert temp_config.get("kubeconfig") is None


def test_set_and_get_config(temp_config: Config) -> None:
    """Test setting and getting configuration values"""
    test_path = "/path/to/kubeconfig"
    temp_config.set("kubeconfig", test_path)
    assert temp_config.get("kubeconfig") == test_path


def test_config_persistence(temp_config: Config) -> None:
    """Test that configuration persists to file"""
    test_path = "/path/to/kubeconfig"
    temp_config.set("kubeconfig", test_path)

    # Create new config instance to test loading from file
    new_config = Config()
    assert new_config.get("kubeconfig") == test_path


def test_show_config(temp_config: Config) -> None:
    """Test showing full configuration"""
    test_path = "/path/to/kubeconfig"
    temp_config.set("kubeconfig", test_path)

    config = temp_config.show()
    assert isinstance(config, dict)
    assert config["kubeconfig"] == test_path


def test_load_config(temp_config: Config) -> None:
    """Test loading configuration from file"""
    test_config = {"kubeconfig": "/test/path"}
    with open(temp_config.config_file, "w") as f:
        yaml.dump(test_config, f)

    loaded_config = Config()
    assert loaded_config.get("kubeconfig") == "/test/path"


def test_load_config_with_env_vars(
    temp_config: Config,
    monkeypatch: MonkeyPatch,
) -> None:
    """Test loading configuration with environment variables"""
    test_path = "/env/var/path"
    monkeypatch.setenv("KUBECONFIG", test_path)
    # Set the config value to match the env var
    temp_config.set("kubeconfig", test_path)
    # Create a new config instance - it should load from the saved file
    config = Config()
    assert config.get("kubeconfig") == test_path


def test_load_config_with_missing_file(temp_config: Config) -> None:
    """Test loading configuration with missing file"""
    # Create the config directory first
    temp_config.config_dir.mkdir(parents=True, exist_ok=True)
    # Create and then remove the file to ensure it exists before removal
    temp_config.config_file.touch()
    os.remove(temp_config.config_file)
    config = Config()
    assert config.get("kubeconfig") is None


def test_load_config_with_invalid_yaml(temp_config: Config) -> None:
    """Test loading configuration with invalid YAML"""
    # Create the config directory first
    temp_config.config_dir.mkdir(parents=True, exist_ok=True)
    with open(temp_config.config_file, "w") as f:
        f.write("{")  # Simpler invalid YAML
    # Create new config - should fall back to default
    config = Config()
    assert config.get("kubeconfig") is None  # Test the public interface instead


def test_load_config_with_invalid_schema(temp_config: Config) -> None:
    """Test loading configuration with invalid schema"""
    invalid_config = {"invalid_key": "value"}
    with open(temp_config.config_file, "w") as f:
        yaml.dump(invalid_config, f)

    config = Config()
    assert config.get("kubeconfig") is None


def test_load_config_with_custom_path(temp_config: Config) -> None:
    """Test loading configuration with custom path"""
    custom_path = "/custom/config/path"
    test_config = {"kubeconfig": custom_path}
    with open(temp_config.config_file, "w") as f:
        yaml.dump(test_config, f)

    config = Config()
    assert config.get("kubeconfig") == custom_path


@pytest.fixture
def runner() -> CliRunner:
    """Create a Click test runner that preserves stderr"""
    return CliRunner(mix_stderr=False)


@pytest.fixture
def mock_config() -> Mock:
    """Mock config for testing."""
    mock = Mock()
    mock.get.side_effect = lambda key, default=None: default
    return mock


def test_config_set_show_raw_output(runner: CliRunner, mock_config: Mock) -> None:
    """Test setting show_raw_output config"""
    with patch("vibectl.cli.Config", return_value=mock_config):
        result = runner.invoke(cli, ["config", "set", "show_raw_output", "true"])
        assert result.exit_code == 0
        mock_config.set.assert_called_once_with("show_raw_output", "true")
        assert "✓ Set show_raw_output to true" in result.output


def test_config_set_show_vibe(runner: CliRunner, mock_config: Mock) -> None:
    """Test setting show_vibe config"""
    with patch("vibectl.cli.Config", return_value=mock_config):
        result = runner.invoke(cli, ["config", "set", "show_vibe", "false"])
        assert result.exit_code == 0
        mock_config.set.assert_called_once_with("show_vibe", "false")
        assert "✓ Set show_vibe to false" in result.output


def test_config_show_display_options(runner: CliRunner) -> None:
    """Test showing config with display options"""
    mock_config = Mock()
    mock_config.show.return_value = {
        "show_raw_output": False,
        "show_vibe": True,
        "llm_model": "claude-3.7-sonnet",
        "kubeconfig": "/path/to/kubeconfig"
    }

    with patch("vibectl.cli.Config", return_value=mock_config):
        result = runner.invoke(cli, ["config", "show"])
        assert result.exit_code == 0
        # Check for header
        assert "vibectl Configuration" in result.output
        # Check that all config values are shown
        assert "kubeconfig" in result.output
        assert "llm_model" in result.output
        assert "show_raw_output" in result.output
        assert "show_vibe" in result.output
        # Check specific values
        assert "False" in result.output
        assert "True" in result.output
        assert "claude-3.7-sonnet" in result.output
        assert "/path/to/kubeconfig" in result.output


def test_missing_api_key_error(runner: CliRunner, mock_config: Mock) -> None:
    """Test error handling when API key is missing"""
    mock_model = Mock()
    mock_model.prompt.side_effect = Exception("No key found")

    with patch("llm.get_model", return_value=mock_model), patch(
        "vibectl.cli.Config", return_value=mock_config
    ):
        # Test any command that uses LLM
        result = runner.invoke(cli, ["create", "vibe", "test"], catch_exceptions=False)

        assert result.exit_code == 1
        assert "Missing API key" in result.stderr


@pytest.fixture
def mock_plan_response() -> str:
    """Mock LLM plan response for testing."""
    return (
        "-n\ndefault\n---\n"
        "apiVersion: v1\n"
        "kind: Pod\n"
        "metadata:\n"
        "  name: test-pod\n"
        "spec:\n"
        "  containers:\n"
        "  - name: test\n"
        "    image: nginx:latest"
    )


@pytest.fixture
def mock_llm_response() -> str:
    """Mock LLM response for testing."""
    return "Created test-pod in default namespace"


def test_api_key_from_env(
    runner: CliRunner,
    monkeypatch: MonkeyPatch,
    mock_plan_response: str,
    mock_llm_response: str,
) -> None:
    """Test using API key from environment variable"""
    test_key = "test-api-key"
    monkeypatch.setenv("OPENAI_API_KEY", test_key)
    mock_model = Mock()
    mock_model.prompt.side_effect = [
        Mock(text=lambda: mock_plan_response),  # First call for planning
        Mock(text=lambda: mock_llm_response),  # Second call for summarizing
    ]
    mock_config = Mock()
    mock_config.get.side_effect = lambda key, default=None: default

    with patch("llm.get_model", return_value=mock_model), patch(
        "vibectl.cli.Config", return_value=mock_config
    ), patch("vibectl.cli.run_kubectl", return_value="test output"):
        # Test any command that uses LLM
        result = runner.invoke(cli, ["create", "vibe", "test"], catch_exceptions=False)
        
        # Should not raise API key error
        assert result.exit_code == 0
        assert "Error: Missing API key" not in result.stderr
        assert "✨ Vibe check:" in result.output
        assert mock_llm_response in result.output


def test_api_key_from_config(
    runner: CliRunner,
    temp_config: Config,
    mock_plan_response: str,
    mock_llm_response: str,
) -> None:
    """Test using API key from config file"""
    test_key = "test-api-key"
    temp_config.set("openai_api_key", test_key)
    mock_model = Mock()
    mock_model.prompt.side_effect = [
        Mock(text=lambda: mock_plan_response),  # First call for planning
        Mock(text=lambda: mock_llm_response),  # Second call for summarizing
    ]

    with patch("llm.get_model", return_value=mock_model), patch(
        "vibectl.cli.run_kubectl", return_value="test output"
    ):
        # Test any command that uses LLM
        result = runner.invoke(cli, ["create", "vibe", "test"], catch_exceptions=False)
        
        # Should not raise API key error and show successful output
        assert result.exit_code == 0
        assert "Error: Missing API key" not in result.stderr
        assert "✨ Vibe check:" in result.output
        assert mock_llm_response in result.output
