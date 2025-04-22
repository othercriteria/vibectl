"""Tests for the theme command in the CLI interface."""

from unittest.mock import Mock, call, patch

from click.testing import CliRunner

from vibectl.cli import cli

# The cli_runner fixture is now provided by conftest.py


@patch("vibectl.cli.console_manager")
def test_theme_list_basic(mock_console: Mock, cli_runner: CliRunner) -> None:
    """Test basic theme list functionality."""
    mock_console.get_available_themes.return_value = ["light", "dark", "custom"]

    result = cli_runner.invoke(cli, ["theme", "list"])

    assert result.exit_code == 0
    mock_console.print_note.assert_called_once_with("Available themes:")
    mock_console.print.assert_has_calls(
        [call("  - light"), call("  - dark"), call("  - custom")]
    )


@patch("vibectl.cli.console_manager")
def test_theme_list_error(mock_console: Mock, cli_runner: CliRunner) -> None:
    """Test theme list command handles error."""
    mock_console.get_available_themes.side_effect = Exception("Failed to get themes")

    result = cli_runner.invoke(cli, ["theme", "list"])
    assert result.exit_code == 1
    assert "Failed to get themes" in result.output


@patch("vibectl.cli.console_manager")
@patch("vibectl.cli.sys")
def test_theme_set_invalid_theme(
    mock_sys: Mock, mock_console: Mock, cli_runner: CliRunner
) -> None:
    """Test theme set command handles invalid theme."""
    mock_console.get_available_themes.return_value = ["dark", "light"]

    # Run the command but don't check exit code, as click testing doesn't propagate it
    cli_runner.invoke(cli, ["theme", "set", "invalid"])

    # Verify the error message was shown
    expected_msg = "Invalid theme 'invalid'. Available themes: dark, light"
    mock_console.print_error.assert_called_once_with(expected_msg)

    # Verify that sys.exit was called with 1
    mock_sys.exit.assert_called_once_with(1)


@patch("vibectl.cli.console_manager")
@patch("vibectl.cli.Config")
@patch("vibectl.cli.handle_exception")
def test_theme_set_save_error(
    mock_handle_exception: Mock,
    mock_config_class: Mock,
    mock_console: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test theme set command handles save error."""
    mock_config = Mock()
    mock_config_class.return_value = mock_config
    mock_console.get_available_themes.return_value = ["dark", "light"]
    error = Exception("Failed to save theme")
    mock_config.save.side_effect = error

    # Run the command but don't check exit code
    cli_runner.invoke(cli, ["theme", "set", "dark"])

    # Verify handle_exception was called with the correct error
    mock_handle_exception.assert_called_once_with(error)
