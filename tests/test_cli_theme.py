"""Tests for the theme command in the CLI interface."""

import pytest
from click.testing import CliRunner
from unittest.mock import Mock, patch, call

from vibectl.cli import cli


@pytest.fixture
def cli_runner() -> CliRunner:
    """Fixture providing a Click CLI test runner."""
    return CliRunner()


@patch("vibectl.cli.console_manager")
def test_theme_list_basic(mock_console: Mock, cli_runner: CliRunner) -> None:
    """Test basic theme list functionality."""
    mock_console.get_available_themes.return_value = ["light", "dark", "custom"]

    result = cli_runner.invoke(cli, ["theme", "list"])

    assert result.exit_code == 0
    mock_console.print_note.assert_called_once_with("Available themes:")
    mock_console.print.assert_has_calls([
        call("  - light"),
        call("  - dark"),
        call("  - custom")
    ])


@patch("vibectl.cli.console_manager")
def test_theme_list_error(mock_console: Mock, cli_runner: CliRunner) -> None:
    """Test theme list command handles error."""
    mock_console.get_available_themes.side_effect = Exception("Failed to get themes")

    result = cli_runner.invoke(cli, ["theme", "list"])
    assert result.exit_code == 1
    assert "Failed to get themes" in result.output


@patch("vibectl.cli.console_manager")
def test_theme_set_invalid_theme(mock_console: Mock, cli_runner: CliRunner) -> None:
    """Test theme set command handles invalid theme."""
    mock_console.get_available_themes.return_value = ["dark", "light"]

    result = cli_runner.invoke(cli, ["theme", "set", "invalid"])
    assert result.exit_code == 1
    mock_console.print_error.assert_called_once_with(
        "Invalid theme 'invalid'. Available themes: dark, light"
    )


@patch("vibectl.cli.console_manager")
@patch("vibectl.cli.Config")
def test_theme_set_save_error(mock_config_class: Mock, mock_console: Mock, cli_runner: CliRunner) -> None:
    """Test theme set command handles save error."""
    mock_config = Mock()
    mock_config_class.return_value = mock_config
    mock_console.get_available_themes.return_value = ["dark", "light"]
    mock_config.save.side_effect = Exception("Failed to save theme")

    result = cli_runner.invoke(cli, ["theme", "set", "dark"])
    assert result.exit_code == 1
    assert "Failed to save theme" in result.output 