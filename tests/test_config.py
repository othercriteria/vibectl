"""Tests for vibectl configuration"""

import pytest

from vibectl.config import Config


@pytest.fixture
def temp_config(tmp_path, monkeypatch):
    """Create a temporary config directory"""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return Config()


def test_config_dir_creation(temp_config):
    """Test that config directory is created"""
    assert temp_config.config_dir.exists()
    assert temp_config.config_dir.is_dir()


def test_default_config(temp_config):
    """Test default configuration"""
    assert temp_config.get("kubeconfig") is None


def test_set_and_get_config(temp_config):
    """Test setting and getting configuration values"""
    test_path = "/path/to/kubeconfig"
    temp_config.set("kubeconfig", test_path)
    assert temp_config.get("kubeconfig") == test_path


def test_config_persistence(temp_config):
    """Test that configuration persists to file"""
    test_path = "/path/to/kubeconfig"
    temp_config.set("kubeconfig", test_path)

    # Create new config instance to test loading from file
    new_config = Config()
    assert new_config.get("kubeconfig") == test_path


def test_show_config(temp_config):
    """Test showing full configuration"""
    test_path = "/path/to/kubeconfig"
    temp_config.set("kubeconfig", test_path)

    config = temp_config.show()
    assert isinstance(config, dict)
    assert config["kubeconfig"] == test_path
