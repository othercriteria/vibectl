"""Tests for the CLI instructions command.

This module tests the instructions management functionality of vibectl.
"""

from collections.abc import Generator
from unittest.mock import Mock, patch

import pytest

from vibectl.cli import cli


@pytest.fixture
def mock_config() -> Generator[Mock, None, None]:
    """Fixture providing a mocked Config instance."""
    with patch("vibectl.cli.Config") as mock_config_class:
        mock_config = Mock()
        mock_config_class.return_value = mock_config
        yield mock_config


@pytest.mark.asyncio
async def test_instructions_set_basic(mock_config: Mock) -> None:
    """Test setting instructions with direct text input."""
    set_cmd = cli.commands["instructions"].commands["set"]  # type: ignore[attr-defined]

    await set_cmd.main(["Test instructions"], standalone_mode=False)  # type: ignore[attr-defined]

    mock_config.set.assert_called_once_with(
        "system.custom_instructions", "Test instructions"
    )
    mock_config.save.assert_called_once()


@pytest.mark.asyncio
@patch("vibectl.cli.Config")
@patch("vibectl.cli.click.edit")
async def test_instructions_set_with_editor(
    mock_edit: Mock,
    mock_config_class: Mock,
) -> None:
    """Test setting instructions using the editor."""
    set_cmd = cli.commands["instructions"].commands["set"]  # type: ignore[attr-defined]
    mock_config = mock_config_class.return_value
    mock_config.get.return_value = "Existing instructions"
    mock_edit.return_value = "Edited instructions"

    await set_cmd.main(["--edit"], standalone_mode=False)  # type: ignore[attr-defined]

    mock_config.get.assert_called_once_with("system.custom_instructions", "")
    mock_edit.assert_called_once_with("Existing instructions")
    mock_config.set.assert_called_once_with(
        "system.custom_instructions", "Edited instructions"
    )
    mock_config.save.assert_called_once()


@pytest.mark.asyncio
@patch("vibectl.cli.Config")
@patch("vibectl.cli.click.edit")
async def test_instructions_set_editor_cancelled(
    mock_edit: Mock,
    mock_config_class: Mock,
) -> None:
    """Test handling when editor is closed without saving."""
    set_cmd = cli.commands["instructions"].commands["set"]  # type: ignore[attr-defined]
    mock_config = mock_config_class.return_value
    mock_config.get.return_value = "Existing instructions"
    mock_edit.return_value = None

    await set_cmd.main(["--edit"], standalone_mode=False)  # type: ignore[attr-defined]

    mock_config.set.assert_not_called()
    mock_config.save.assert_not_called()


@pytest.mark.asyncio
@patch("vibectl.cli.Config")
@patch("sys.stdin")
async def test_instructions_set_no_text(
    mock_stdin: Mock,
    mock_config_class: Mock,
) -> None:
    """Test handling when no instructions text is provided (and not TTY)."""
    set_cmd = cli.commands["instructions"].commands["set"]  # type: ignore[attr-defined]

    mock_stdin.isatty.return_value = False
    mock_stdin.read.return_value = ""

    # With centralized exception handling, the ValueError should propagate
    with pytest.raises(ValueError, match="No instructions provided via stdin"):
        await set_cmd.main([], standalone_mode=False)  # type: ignore[attr-defined]

    mock_config_class.return_value.set.assert_not_called()


@pytest.mark.asyncio
@patch("vibectl.cli.Config")
@patch("vibectl.cli.handle_exception", new_callable=Mock)
async def test_instructions_set_config_save_error(
    mock_handle_exception: Mock,
    mock_config_class: Mock,
) -> None:
    """Test handling when config save fails."""
    # Configure the mock to be synchronous
    mock_handle_exception.return_value = None
    mock_handle_exception.side_effect = None

    set_cmd = cli.commands["instructions"].commands["set"]  # type: ignore[attr-defined]
    mock_config = mock_config_class.return_value
    mock_config.save.side_effect = Exception("Save error")

    await set_cmd.main(["Test instructions"], standalone_mode=False)  # type: ignore[attr-defined]

    mock_config.set.assert_called_once()
    mock_handle_exception.assert_called_once_with(mock_config.save.side_effect)


@pytest.mark.asyncio
async def test_instructions_show_basic(mock_config: Mock) -> None:
    """Test showing instructions when they are set."""
    show_cmd = cli.commands["instructions"].commands["show"]  # type: ignore[attr-defined]
    mock_config.get.return_value = "Test instructions"

    with patch("vibectl.cli.console_manager") as mock_console:
        await show_cmd.main([], standalone_mode=False)  # type: ignore[attr-defined]

        mock_config.get.assert_called_once_with("system.custom_instructions", "")
        mock_console.print_note.assert_called_once_with("Custom instructions:")
        mock_console.print.assert_called_once_with("Test instructions")


@pytest.mark.asyncio
@patch("vibectl.cli.Config")
async def test_instructions_show_empty(mock_config_class: Mock) -> None:
    """Test showing instructions when none are set."""
    show_cmd = cli.commands["instructions"].commands["show"]  # type: ignore[attr-defined]
    mock_config = mock_config_class.return_value
    mock_config.get.return_value = ""

    with patch("vibectl.cli.console_manager") as mock_console:
        await show_cmd.main([], standalone_mode=False)  # type: ignore[attr-defined]

        mock_config.get.assert_called_once_with("system.custom_instructions", "")
        mock_console.print_note.assert_called_once_with("No custom instructions set")
        mock_console.print.assert_not_called()


@pytest.mark.asyncio
@patch("vibectl.cli.Config")
@patch("vibectl.cli.handle_exception", new_callable=Mock)
async def test_instructions_show_get_error(
    mock_handle_exception: Mock,
    mock_config_class: Mock,
) -> None:
    """Test handling when config get fails."""
    # Configure the mock to be synchronous
    mock_handle_exception.return_value = None
    mock_handle_exception.side_effect = None

    show_cmd = cli.commands["instructions"].commands["show"]  # type: ignore[attr-defined]
    mock_config = mock_config_class.return_value
    mock_config.get.side_effect = Exception("Get error")

    await show_cmd.main([], standalone_mode=False)  # type: ignore[attr-defined]

    mock_handle_exception.assert_called_once_with(mock_config.get.side_effect)


@pytest.mark.asyncio
@patch("vibectl.cli.Config")
async def test_instructions_clear_basic(mock_config_class: Mock) -> None:
    """Test clearing instructions."""
    clear_cmd = cli.commands["instructions"].commands["clear"]  # type: ignore[attr-defined]
    mock_config = mock_config_class.return_value

    await clear_cmd.main([], standalone_mode=False)  # type: ignore[attr-defined]

    mock_config.set.assert_called_once_with("system.custom_instructions", "")
    mock_config.save.assert_called_once()


@pytest.mark.asyncio
@patch("vibectl.cli.Config")
@patch("vibectl.cli.handle_exception", new_callable=Mock)
async def test_instructions_clear_unset_error(
    mock_handle_exception: Mock,
    mock_config_class: Mock,
) -> None:
    """Test handling when config set fails during clear."""
    # Configure the mock to be synchronous
    mock_handle_exception.return_value = None
    mock_handle_exception.side_effect = None

    clear_cmd = cli.commands["instructions"].commands["clear"]  # type: ignore[attr-defined]
    mock_config = mock_config_class.return_value
    mock_config.set.side_effect = Exception("Set error")

    await clear_cmd.main([], standalone_mode=False)  # type: ignore[attr-defined]

    mock_handle_exception.assert_called_once_with(mock_config.set.side_effect)


@pytest.mark.asyncio
@patch("vibectl.cli.Config")
@patch("sys.stdin")
async def test_instructions_set_stdin_accepted(
    mock_stdin: Mock,
    mock_config_class: Mock,
) -> None:
    """Test that instructions set accepts piped input (stdin) and sets instructions."""
    set_cmd = cli.commands["instructions"].commands["set"]  # type: ignore[attr-defined]
    mock_config = mock_config_class.return_value
    test_input = "Instructions from stdin!"

    mock_stdin.isatty.return_value = False
    mock_stdin.read.return_value = test_input

    await set_cmd.main([], standalone_mode=False)  # type: ignore[attr-defined]

    mock_config.set.assert_called_once_with("system.custom_instructions", test_input)
    mock_config.save.assert_called_once()
