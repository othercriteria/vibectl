"""Tests for the theme command in the CLI interface."""

from collections.abc import Generator
from unittest.mock import Mock, call, patch

import pytest

from vibectl.cli import _set_theme_logic, cli


# Common fixtures (move to conftest.py if used widely)
@pytest.fixture
def mock_console() -> Generator[Mock, None, None]:
    with patch("vibectl.cli.console_manager") as mock:
        yield mock


@pytest.fixture
def mock_config() -> Generator[Mock, None, None]:
    with patch("vibectl.cli.Config") as mock_config_class:
        mock_config_instance = Mock()
        mock_config_class.return_value = mock_config_instance
        yield mock_config_instance


@pytest.fixture
def mock_handle_exception() -> Generator[Mock, None, None]:
    with patch("vibectl.cli.handle_exception") as mock:
        yield mock


@pytest.mark.asyncio
async def test_theme_list_basic(mock_console: Mock) -> None:
    """Test basic theme list functionality."""
    # Access list command via cli.commands, assuming it might become async
    list_cmd = cli.commands["theme"].commands["list"]  # type: ignore[attr-defined]
    mock_console.get_available_themes.return_value = ["light", "dark", "custom"]

    # Execute directly
    await list_cmd.main([], standalone_mode=False)

    mock_console.print_note.assert_called_once_with("Available themes:")
    mock_console.print.assert_has_calls(
        [call("  - light"), call("  - dark"), call("  - custom")]
    )


@pytest.mark.asyncio
async def test_theme_list_error(
    mock_console: Mock, mock_handle_exception: Mock
) -> None:
    """Test theme list command handles error."""
    # Access list command via cli.commands
    list_cmd = cli.commands["theme"].commands["list"]  # type: ignore[attr-defined]
    error = Exception("Failed to get themes")
    mock_console.get_available_themes.side_effect = error

    # Execute directly
    await list_cmd.main([], standalone_mode=False)

    # Verify handle_exception was called
    mock_handle_exception.assert_called_once_with(error)


# This test is now synchronous as it tests the helper directly
def test_theme_set_invalid_theme_logic(
    mock_console: Mock,  # Keep console mock to check get_available_themes
) -> None:
    """Test _set_theme_logic raises ValueError for invalid theme."""
    mock_console.get_available_themes.return_value = ["dark", "light"]
    invalid_theme = "invalid"

    # Assert that ValueError is raised
    with pytest.raises(ValueError) as excinfo:
        _set_theme_logic(invalid_theme)

    # Optionally, assert the exception message
    expected_msg = f"Invalid theme '{invalid_theme}'. Available themes: dark, light"
    assert str(excinfo.value) == expected_msg

    # Verify get_available_themes was called
    mock_console.get_available_themes.assert_called_once()


# Test successful theme setting via the helper
def test_theme_set_valid_theme_logic(mock_console: Mock, mock_config: Mock) -> None:
    """Test _set_theme_logic sets theme correctly."""
    mock_console.get_available_themes.return_value = ["dark", "light", "default"]
    valid_theme = "dark"

    # Call the helper function
    _set_theme_logic(valid_theme)

    # Verify config.set and config.save were called
    mock_config.set.assert_called_once_with("theme", valid_theme)
    mock_config.save.assert_called_once()
    # Verify success message was printed
    mock_console.print_success.assert_called_once_with(f"Theme set to '{valid_theme}'.")


# Keep this test for the command's error handling integration
@pytest.mark.asyncio
async def test_theme_set_save_error(
    mock_handle_exception: Mock,
    mock_config: Mock,
    mock_console: Mock,
) -> None:
    """Test theme set command handles save error."""
    # Access set command via cli.commands
    set_cmd = cli.commands["theme"].commands["set"]  # type: ignore[attr-defined]
    mock_console.get_available_themes.return_value = ["dark", "light"]
    error = Exception("Failed to save theme")
    mock_config.save.side_effect = error

    # Execute directly
    await set_cmd.main(["dark"], standalone_mode=False)

    # Verify handle_exception was called with the correct error
    mock_handle_exception.assert_called_once_with(error)
