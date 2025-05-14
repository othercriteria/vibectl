"""
Tests for coverage gaps in memory functionality.
"""

from collections.abc import Generator
from unittest.mock import MagicMock, Mock, patch

import pytest

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


# Marker for consistency, even if underlying funcs are sync
@pytest.mark.asyncio
async def test_memory_freeze_unfreeze() -> None:
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


# Marker for consistency, even if underlying funcs are sync
@pytest.mark.asyncio
async def test_memory_clear(
    setup_and_cleanup_memory: Generator[None, None, None],
) -> None:
    """Test memory clear functionality."""
    # Verify memory has content
    assert get_memory() is not None

    # Clear memory
    clear_memory()

    # Verify memory was cleared (None or empty string)
    memory = get_memory()
    assert not memory


@pytest.mark.asyncio
@patch("vibectl.cli.click.edit")  # Patch click.edit used within the command
async def test_memory_set_with_editor(
    mock_edit: MagicMock, setup_and_cleanup_memory: Generator[None, None, None]
) -> None:
    """Test memory set using the editor."""
    set_cmd = memory_group.commands["set"]  # Get the set command object

    # Mock the editor return value
    edited_content = "This is the edited memory content"
    mock_edit.return_value = edited_content

    # Run the memory_set command directly
    with patch("vibectl.cli.console_manager"):  # Mock console if needed by command
        await set_cmd.main(["--edit"], standalone_mode=False)  # Use await and call main

    # Check the memory was updated with edited content
    assert get_memory() == edited_content

    # Verify mock was called
    mock_edit.assert_called_once()


@pytest.mark.asyncio
# @patch("vibectl.cli.llm") # Old patch, no longer correct
@patch("vibectl.cli.get_model_adapter")  # Patch get_model_adapter at the CLI level
async def test_memory_update(
    mock_get_model_adapter: MagicMock,  # New mock argument
    setup_and_cleanup_memory: Generator[None, None, None],
) -> None:
    """Test memory update functionality."""
    update_cmd = memory_group.commands["update"]  # Get the update command object

    # Configure the mock model adapter
    mock_adapter_instance = (
        Mock()
    )  # spec=ModelAdapter can be added if ModelAdapter is importable here
    mock_get_model_adapter.return_value = mock_adapter_instance

    # Mock the model that the adapter will return
    mock_model_instance = MagicMock()
    mock_adapter_instance.get_model.return_value = mock_model_instance

    # Configure the response from execute_and_log_metrics
    expected_updated_memory = "Updated memory with new information"
    mock_adapter_instance.execute_and_log_metrics.return_value = (
        expected_updated_memory,
        None,  # No metrics for this test
    )

    # Run the memory_update command directly
    # The command itself is synchronous, but called via async click runner
    # Mock config within the command if needed, or assume default config is used
    with patch("vibectl.cli.console_manager"):  # Mock console if needed by command
        # It seems memory_update in cli.py is synchronous, so no await here on main.
        # However, the test is marked asyncio, and calls it via await.
        # Assuming async main.
        await update_cmd.main(["Add", "new", "information"], standalone_mode=False)

    # Verify memory was updated
    assert get_memory() == expected_updated_memory

    # Verify mocks
    mock_get_model_adapter.assert_called_once()  # Check an adapter was requested
    # The CLI command will get a default model name from Config if not specified.
    # For this test, we assume it gets a model, e.g., the default.
    mock_adapter_instance.get_model.assert_called_once()  # TODO: Add model name
    mock_adapter_instance.execute_and_log_metrics.assert_called_once()
