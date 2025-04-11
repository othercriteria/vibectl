"""Tests for the CLI instructions command.

This module tests the instructions management functionality of vibectl.
"""

from collections.abc import Generator
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from vibectl.cli import clear, instructions_set, instructions_show

# The cli_runner fixture is now provided by conftest.py


@pytest.fixture
def mock_config() -> Generator[Mock, None, None]:
    """Fixture providing a mocked Config instance."""
    with patch("vibectl.cli.Config") as mock_config_class:
        mock_config = Mock()
        mock_config_class.return_value = mock_config
        yield mock_config


def test_instructions_set_basic(mock_config: Mock, cli_runner: CliRunner) -> None:
    """Test setting instructions with direct text input."""
    result = cli_runner.invoke(instructions_set, ["Test instructions"])

    assert result.exit_code == 0
    mock_config.set.assert_called_once_with("custom_instructions", "Test instructions")
    mock_config.save.assert_called_once()


@patch("vibectl.cli.Config")
@patch("click.edit")
def test_instructions_set_with_editor(
    mock_edit: Mock,
    mock_config_class: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test setting instructions using the editor."""
    # Setup
    mock_config = Mock()
    mock_config_class.return_value = mock_config
    mock_config.get.return_value = "Existing instructions"
    mock_edit.return_value = "Edited instructions"

    # Execute
    result = cli_runner.invoke(instructions_set, ["--edit"])

    # Assert
    assert result.exit_code == 0
    mock_config.get.assert_called_once_with("custom_instructions", "")
    mock_edit.assert_called_once_with("Existing instructions")
    mock_config.set.assert_called_once_with(
        "custom_instructions", "Edited instructions"
    )
    mock_config.save.assert_called_once()


@patch("vibectl.cli.Config")
@patch("click.edit")
def test_instructions_set_editor_cancelled(
    mock_edit: Mock,
    mock_config_class: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test handling when editor is closed without saving."""
    # Setup
    mock_config = Mock()
    mock_config_class.return_value = mock_config
    mock_config.get.return_value = "Existing instructions"
    mock_edit.return_value = None  # Editor was closed without saving

    # Execute
    result = cli_runner.invoke(instructions_set, ["--edit"])

    # Assert
    assert result.exit_code == 0
    mock_config.set.assert_not_called()
    mock_config.save.assert_not_called()


@patch("vibectl.cli.Config")
def test_instructions_set_no_text(
    mock_config_class: Mock, cli_runner: CliRunner
) -> None:
    """Test handling when no instructions text is provided."""
    # Execute
    result = cli_runner.invoke(instructions_set, [])

    # Assert
    assert result.exit_code == 1
    mock_config_class.return_value.set.assert_not_called()


@patch("vibectl.cli.Config")
def test_instructions_set_config_save_error(
    mock_config_class: Mock, cli_runner: CliRunner
) -> None:
    """Test handling when config save fails."""
    # Setup
    mock_config = Mock()
    mock_config_class.return_value = mock_config
    mock_config.save.side_effect = Exception("Save error")

    # Execute
    result = cli_runner.invoke(instructions_set, ["Test instructions"])

    # Assert
    assert result.exit_code == 1
    mock_config.set.assert_called_once()


def test_instructions_show_basic(cli_runner: CliRunner, mock_config: Mock) -> None:
    """Test showing instructions when they are set."""
    # Setup direct mock for get_memory
    mock_config.get.return_value = "Test instructions"

    with patch("vibectl.cli.console_manager") as mock_console:
        # Execute
        result = cli_runner.invoke(instructions_show)

        # Assert
        assert result.exit_code == 0
        mock_config.get.assert_called_once_with("custom_instructions", "")
        mock_console.print_note.assert_called_once_with("Custom instructions:")
        mock_console.print.assert_called_once_with("Test instructions")


@patch("vibectl.cli.Config")
def test_instructions_show_empty(
    mock_config_class: Mock, cli_runner: CliRunner
) -> None:
    """Test showing instructions when none are set."""
    # Setup
    mock_config = Mock()
    mock_config_class.return_value = mock_config
    mock_config.get.return_value = ""

    with patch("vibectl.cli.console_manager") as mock_console:
        # Execute
        result = cli_runner.invoke(instructions_show)

        # Assert
        assert result.exit_code == 0
        mock_config.get.assert_called_once_with("custom_instructions", "")
        mock_console.print_note.assert_called_once_with("No custom instructions set")
        mock_console.print.assert_not_called()


@patch("vibectl.cli.Config")
def test_instructions_show_get_error(
    mock_config_class: Mock, cli_runner: CliRunner
) -> None:
    """Test handling when config get fails."""
    # Setup
    mock_config = Mock()
    mock_config_class.return_value = mock_config
    mock_config.get.side_effect = Exception("Get error")

    # Execute
    result = cli_runner.invoke(instructions_show)

    # Assert
    assert result.exit_code == 1


@patch("vibectl.cli.Config")
def test_instructions_clear_basic(
    mock_config_class: Mock, cli_runner: CliRunner
) -> None:
    """Test clearing instructions."""
    # Setup
    mock_config = Mock()
    mock_config_class.return_value = mock_config

    # Execute
    result = cli_runner.invoke(clear)

    # Assert
    assert result.exit_code == 0
    mock_config.set.assert_called_once_with("custom_instructions", "")
    mock_config.save.assert_called_once()


@patch("vibectl.cli.Config")
def test_instructions_clear_unset_error(
    mock_config_class: Mock, cli_runner: CliRunner
) -> None:
    """Test handling when config unset fails."""
    # Setup
    mock_config = Mock()
    mock_config_class.return_value = mock_config
    mock_config.set.side_effect = Exception("Unset error")

    # Execute
    result = cli_runner.invoke(clear)

    # Assert
    assert result.exit_code == 1
