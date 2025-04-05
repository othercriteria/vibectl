"""Shared pytest fixtures."""

from pathlib import Path
from typing import Any, Generator
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from vibectl.config import Config


@pytest.fixture
def runner() -> CliRunner:
    """Fixture that provides a CliRunner instance for testing Click applications."""
    return CliRunner()


@pytest.fixture
def mock_console_manager() -> Generator[Mock, None, None]:
    """Mock the console manager for testing."""
    with patch("vibectl.console.console_manager") as mock_manager:
        # Mock all the methods we use in tests
        mock_manager.print_error.return_value = None
        mock_manager.print_warning.return_value = None
        mock_manager.print.return_value = None
        mock_manager.print_raw.return_value = None
        mock_manager.set_theme.return_value = None
        mock_manager.print_config_table.return_value = None
        yield mock_manager


@pytest.fixture(autouse=True)
def mock_theme_setup() -> Generator[Any, None, None]:
    """Mock theme setup to avoid theme-related errors in tests."""
    with patch("vibectl.cli.console_manager.set_theme") as _:
        yield


@pytest.fixture
def mock_config_dir(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a mock config directory for testing."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    with patch.object(Config, "config_dir", config_dir), patch.object(
        Config, "config_file", config_dir / "config.yaml"
    ):
        yield config_dir


@pytest.fixture
def temp_config(mock_config_dir: Path) -> Config:
    """Return a Config instance using the mock directory."""
    return Config()


@pytest.fixture
def mock_plan_response() -> str:
    """Mock response for the plan command."""
    return (
        "-n\ndefault\n---\napiVersion: v1\nkind: Pod\nmetadata:\n"
        "  name: test-pod\nspec:\n  containers:\n  - name: test\n"
        "    image: nginx:latest"
    )


@pytest.fixture
def mock_llm_response() -> str:
    """Mock response for the LLM."""
    return "Created test-pod in default namespace"
