"""
Tests for coverage gaps in memory functionality.
"""

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from vibectl.cli import memory_group
from vibectl.memory import (
    clear_memory,
    disable_memory,
    enable_memory,
    get_memory,
    set_memory,
)


@pytest.fixture
def setup_and_cleanup_memory() -> Generator[None, None, None]:
    """Set up by setting a known memory state and clean up after test."""
    # Save original memory
    original_memory = get_memory()

    # Set test memory
    set_memory("Test memory content")

    yield

    # Restore original memory
    if original_memory:
        set_memory(original_memory)
    else:
        clear_memory()


def test_memory_freeze_unfreeze() -> None:
    """Test memory freeze and unfreeze functions."""
    # Test disabling (freezing) memory
    disable_memory()

    # Verify memory is disabled - pass no arguments to get_memory
    memory_disabled = get_memory()
    assert not memory_disabled or memory_disabled.startswith("[DISABLED]")

    # Enable memory
    enable_memory()

    # Verify memory is enabled
    memory = get_memory()
    assert memory is not None


def test_memory_clear(setup_and_cleanup_memory: Generator[None, None, None]) -> None:
    """Test memory clear functionality."""
    # Verify memory has content
    assert get_memory() is not None

    # Clear memory
    clear_memory()

    # Verify memory was cleared (None or empty string)
    memory = get_memory()
    assert not memory


@patch("click.edit")
def test_memory_set_with_editor(
    mock_edit: MagicMock, setup_and_cleanup_memory: Generator[None, None, None]
) -> None:
    """Test memory set using the editor."""
    # Create Click runner
    runner = CliRunner()

    # Mock the editor return value
    edited_content = "This is the edited memory content"
    mock_edit.return_value = edited_content

    # Run the memory_set command with edit flag
    with patch("vibectl.cli.console_manager"):
        result = runner.invoke(memory_group, ["set", "--edit"])

    # Check the command executed successfully
    assert result.exit_code == 0

    # Check the memory was updated with edited content
    assert get_memory() == edited_content

    # Verify mock was called
    mock_edit.assert_called_once()


@patch("vibectl.cli.llm")
def test_memory_update(
    mock_llm: MagicMock, setup_and_cleanup_memory: Generator[None, None, None]
) -> None:
    """Test memory update functionality."""
    # Create Click runner
    runner = CliRunner()

    # Set up mock response
    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.text.return_value = "Updated memory with new information"
    mock_model.prompt.return_value = mock_response
    mock_llm.get_model.return_value = mock_model

    # Run the memory_update command
    with patch("vibectl.cli.console_manager"):
        result = runner.invoke(memory_group, ["update", "Add", "new", "information"])

    # Check the command executed successfully
    assert result.exit_code == 0

    # Verify memory was updated
    assert get_memory() == "Updated memory with new information"

    # Verify mock was called
    mock_llm.get_model.assert_called_once()
    mock_model.prompt.assert_called_once()
    mock_response.text.assert_called_once()
