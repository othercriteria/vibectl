"""Common test fixtures for vibectl tests.

This module contains shared fixtures used across multiple test files.
"""

import shutil
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest
from rich.console import Console

# Import all fixtures from fixtures.py
from vibectl.config import Config
from vibectl.console import ConsoleManager


@pytest.fixture(scope="session", autouse=True)
def protect_user_config() -> Generator[None, None, None]:
    """Protect user's live config by backing it up and restoring after tests.

    This fixture runs automatically for all tests and ensures that the user's
    live configuration is never modified during testing.
    """
    # Get user's home directory config path
    user_config_dir = Path.home() / ".vibectl"
    user_config_file = user_config_dir / "config.yaml"
    backup_file = user_config_dir / "config.yaml.bak"

    # Track whether we had an original config
    had_original = user_config_file.exists()
    had_original_dir = user_config_dir.exists()

    try:
        # Create config directory if it doesn't exist
        user_config_dir.mkdir(parents=True, exist_ok=True)

        # Backup existing config if it exists
        if had_original:
            shutil.copy2(user_config_file, backup_file)

        yield

    finally:
        try:
            # Restore from backup if we had an original
            if had_original and backup_file.exists():
                shutil.copy2(backup_file, user_config_file)
                backup_file.unlink()
            # Remove test config if we didn't have an original
            elif not had_original and user_config_file.exists():
                user_config_file.unlink()

            # Clean up directory if it didn't exist originally
            if (
                not had_original_dir
                and user_config_dir.exists()
                and not any(user_config_dir.iterdir())
            ):
                user_config_dir.rmdir()

        except Exception as e:
            # Log error but don't fail the test
            print(f"Warning: Error during config cleanup: {e}")


@pytest.fixture
def mock_k8s_config() -> Generator[MagicMock, None, None]:
    """Mock kubernetes.config to prevent actual cluster access.

    Returns:
        MagicMock: Mocked kubernetes config object.
    """
    with patch("kubernetes.config") as mock_config:
        yield mock_config


@pytest.fixture
def mock_k8s_client() -> Generator[MagicMock, None, None]:
    """Mock kubernetes.client to prevent actual API calls.

    Returns:
        MagicMock: Mocked kubernetes client object.
    """
    with patch("kubernetes.client") as mock_client:
        yield mock_client


@pytest.fixture
def mock_llm() -> Generator[MagicMock, None, None]:
    """Mock LLM client to prevent actual API calls.

    Returns:
        MagicMock: Mocked LLM client object.
    """
    with patch("llm.get_model") as mock_get_model:
        mock_model = Mock()
        mock_model.prompt.return_value = Mock(text=lambda: "Test response")
        mock_get_model.return_value = mock_model
        yield mock_get_model


@pytest.fixture
def test_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[Config, None, None]:
    """Create a test configuration with temporary paths.

    Args:
        tmp_path: pytest fixture providing temporary directory
        monkeypatch: pytest fixture for patching

    Returns:
        Config: Test configuration object.
    """
    # Create an isolated test config directory
    test_config_dir = tmp_path / "test_config"
    test_config_dir.mkdir(parents=True, exist_ok=True)

    # Patch HOME environment variable to isolate config location
    monkeypatch.setenv("HOME", str(test_config_dir))

    config = Config(base_dir=test_config_dir)

    # Set test values using set() method
    config.set("kubeconfig", str(tmp_path / "kubeconfig"))
    config.set(
        "model", "claude-3.7-sonnet"
    )  # Use a valid model from CONFIG_VALID_VALUES
    config.set("show_raw_output", "true")
    config.set("show_vibe", "true")
    config.set("suppress_warning", "false")
    config.set("theme", "default")

    yield config

    # Clean up test config directory after test
    shutil.rmtree(test_config_dir, ignore_errors=True)


@pytest.fixture
def test_console() -> Generator[ConsoleManager, None, None]:
    """Create a test console manager with a string buffer.

    Returns:
        ConsoleManager: Test console manager object.
    """
    console_manager = ConsoleManager()
    theme = console_manager.themes["default"]  # Get the default theme

    # Create consoles with string buffers
    console_manager.console = Console(record=True, theme=theme)
    console_manager.error_console = Console(
        record=True, theme=theme
    )  # Remove stderr=True to capture output

    yield console_manager


@pytest.fixture
def sample_pod_list() -> list[dict[str, Any]]:
    """Create a sample list of pod resources for testing."""
    return [
        {
            "kind": "Pod",
            "apiVersion": "v1",
            "metadata": {
                "name": f"test-pod-{i}",
                "namespace": "default",
                "labels": {"app": "test"},
            },
            "spec": {
                "containers": [{"name": "nginx", "image": "nginx:latest"}],
            },
            "status": {
                "phase": "Running" if i % 2 == 0 else "Pending",
                "conditions": [
                    {
                        "type": "Ready",
                        "status": "True" if i % 2 == 0 else "False",
                    }
                ],
            },
        }
        for i in range(5)
    ]


@pytest.fixture
def sample_deployment_list() -> list[dict[str, Any]]:
    """Create a sample list of deployment resources for testing."""
    return [
        {
            "kind": "Deployment",
            "apiVersion": "apps/v1",
            "metadata": {
                "name": f"test-deployment-{i}",
                "namespace": "default",
            },
            "spec": {
                "replicas": i + 1,
                "selector": {
                    "matchLabels": {"app": f"test-{i}"},
                },
                "template": {
                    "metadata": {
                        "labels": {"app": f"test-{i}"},
                    },
                    "spec": {
                        "containers": [
                            {
                                "name": "nginx",
                                "image": "nginx:latest",
                            }
                        ],
                    },
                },
            },
            "status": {
                "availableReplicas": i if i < 3 else 3,
                "readyReplicas": i if i < 3 else 3,
                "replicas": i + 1,
                "updatedReplicas": i + 1,
            },
        }
        for i in range(5)
    ]
