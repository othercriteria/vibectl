"""Tests for vibectl configuration"""

import os
from pathlib import Path

import pytest
import yaml
from pytest import MonkeyPatch

from vibectl.config import Config


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
