"""Tests for the CLI memory commands.

This module tests the memory-related CLI commands and functionality.
"""

from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from vibectl.cli import cli


@pytest.fixture
def cli_runner() -> CliRunner:
    """Fixture providing a Click CLI test runner.

    Returns:
        CliRunner: A Click test runner instance
    """
    return CliRunner()


@patch("vibectl.cli.set_memory")
def test_memory_set_basic(mock_set_memory: Mock, cli_runner: CliRunner) -> None:
    """Test the basic memory set command with direct text input."""
    # Execute
    result = cli_runner.invoke(cli, ["memory", "set", "Test memory content"])

    # Assert
    assert result.exit_code == 0
    mock_set_memory.assert_called_once_with("Test memory content")
    assert "Memory set" in result.output


@patch("vibectl.cli.click.edit")
@patch("vibectl.cli.get_memory")
@patch("vibectl.cli.set_memory")
def test_memory_set_edit(
    mock_set_memory: Mock, mock_get_memory: Mock, mock_edit: Mock, cli_runner: CliRunner
) -> None:
    """Test the memory set command with editor."""
    # Setup
    mock_get_memory.return_value = "Initial content"
    mock_edit.return_value = "Edited content"

    # Execute
    result = cli_runner.invoke(cli, ["memory", "set", "--edit"])

    # Assert
    assert result.exit_code == 0
    mock_get_memory.assert_called_once()
    mock_edit.assert_called_once_with("Initial content")
    mock_set_memory.assert_called_once_with("Edited content")
    assert "Memory updated from editor" in result.output


@patch("vibectl.cli.click.edit")
@patch("vibectl.cli.get_memory")
@patch("vibectl.cli.set_memory")
def test_memory_set_edit_cancelled(
    mock_set_memory: Mock, mock_get_memory: Mock, mock_edit: Mock, cli_runner: CliRunner
) -> None:
    """Test memory set with editor when user cancels editing."""
    # Setup
    mock_get_memory.return_value = "Initial content"
    mock_edit.return_value = None  # Simulate user cancelling edit

    # Execute
    result = cli_runner.invoke(cli, ["memory", "set", "--edit"])

    # Assert
    assert result.exit_code == 0
    mock_get_memory.assert_called_once()
    mock_edit.assert_called_once_with("Initial content")
    mock_set_memory.assert_not_called()
    assert "Memory update cancelled" in result.output


@patch("vibectl.cli.set_memory")
def test_memory_set_no_text(mock_set_memory: Mock, cli_runner: CliRunner) -> None:
    """Test memory set with no text or edit flag."""
    # Execute
    result = cli_runner.invoke(cli, ["memory", "set"])

    # Assert
    assert result.exit_code == 0
    mock_set_memory.assert_not_called()
    assert "No text provided" in result.output


@patch("vibectl.cli.get_memory")
def test_memory_show_with_content(mock_get_memory: Mock, cli_runner: CliRunner) -> None:
    """Test memory show command with existing content."""
    # Setup
    mock_get_memory.return_value = "Test memory content"

    # Execute
    result = cli_runner.invoke(cli, ["memory", "show"])

    # Assert
    assert result.exit_code == 0
    mock_get_memory.assert_called_once()
    # Console output is tested elsewhere


@patch("vibectl.cli.get_memory")
def test_memory_show_empty(mock_get_memory: Mock, cli_runner: CliRunner) -> None:
    """Test memory show command with empty memory."""
    # Setup
    mock_get_memory.return_value = ""

    # Execute
    with patch("vibectl.cli.console_manager") as mock_console:
        result = cli_runner.invoke(cli, ["memory", "show"])

    # Assert
    assert result.exit_code == 0
    mock_get_memory.assert_called_once()
    mock_console.print_warning.assert_called_once()


@patch("vibectl.cli.clear_memory")
def test_memory_clear(mock_clear_memory: Mock, cli_runner: CliRunner) -> None:
    """Test memory clear command."""
    # Execute
    with patch("vibectl.cli.console_manager") as mock_console:
        result = cli_runner.invoke(cli, ["memory", "clear"])

    # Assert
    assert result.exit_code == 0
    mock_clear_memory.assert_called_once()
    mock_console.print_success.assert_called_once()


@patch("vibectl.cli.disable_memory")
def test_memory_freeze(mock_disable_memory: Mock, cli_runner: CliRunner) -> None:
    """Test memory freeze command."""
    # Execute
    with patch("vibectl.cli.console_manager") as mock_console:
        result = cli_runner.invoke(cli, ["memory", "freeze"])

    # Assert
    assert result.exit_code == 0
    mock_disable_memory.assert_called_once()
    mock_console.print_success.assert_called_once()


@patch("vibectl.cli.enable_memory")
def test_memory_unfreeze(mock_enable_memory: Mock, cli_runner: CliRunner) -> None:
    """Test memory unfreeze command."""
    # Execute
    with patch("vibectl.cli.console_manager") as mock_console:
        result = cli_runner.invoke(cli, ["memory", "unfreeze"])

    # Assert
    assert result.exit_code == 0
    mock_enable_memory.assert_called_once()
    mock_console.print_success.assert_called_once()


@patch("vibectl.cli.disable_memory")
@patch("vibectl.cli.clear_memory")
def test_memory_wipe(
    mock_clear_memory: Mock, mock_disable_memory: Mock, cli_runner: CliRunner
) -> None:
    """Test memory wipe command."""
    # Execute
    with patch("vibectl.cli.console_manager") as mock_console:
        result = cli_runner.invoke(cli, ["memory", "wipe"])

    # Assert
    assert result.exit_code == 0
    mock_clear_memory.assert_called_once()
    mock_disable_memory.assert_called_once()
    mock_console.print_success.assert_called_once()


@patch("vibectl.cli.disable_memory")
@patch("vibectl.cli.Config")
def test_configure_memory_flags_freeze(
    mock_config_class: Mock, mock_disable: Mock
) -> None:
    """Test memory flag configuration with freeze flag."""
    from vibectl.cli import configure_memory_flags

    # Setup
    mock_config = Mock()
    mock_config_class.return_value = mock_config

    # Execute
    configure_memory_flags(freeze=True, unfreeze=False)

    # Assert
    mock_disable.assert_called_once()


@patch("vibectl.cli.enable_memory")
@patch("vibectl.cli.Config")
def test_configure_memory_flags_unfreeze(
    mock_config_class: Mock, mock_enable: Mock
) -> None:
    """Test memory flag configuration with unfreeze flag."""
    from vibectl.cli import configure_memory_flags

    # Setup
    mock_config = Mock()
    mock_config_class.return_value = mock_config

    # Execute
    configure_memory_flags(freeze=False, unfreeze=True)

    # Assert
    mock_enable.assert_called_once()


@patch("vibectl.cli.Config")
def test_configure_memory_flags_none(mock_config_class: Mock) -> None:
    """Test memory flag configuration with no flags set."""
    from vibectl.cli import configure_memory_flags

    # Setup
    mock_config = Mock()
    mock_config_class.return_value = mock_config

    # Execute
    configure_memory_flags(freeze=False, unfreeze=False)

    # Assert
    mock_config.set.assert_not_called()
    mock_config.save.assert_not_called()


@patch("vibectl.cli.console_manager")
def test_configure_memory_flags_conflict(mock_console: Mock) -> None:
    """Test memory flag configuration with conflicting flags."""
    from vibectl.cli import configure_memory_flags

    # Execute and Assert
    with pytest.raises(ValueError) as excinfo:
        configure_memory_flags(freeze=True, unfreeze=True)

    assert "Cannot specify both" in str(excinfo.value)
