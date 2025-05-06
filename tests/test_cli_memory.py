"""Tests for the memory-related CLI commands.

This module tests the memory commands of vibectl.
"""

from collections.abc import Generator
from unittest.mock import Mock, patch

import pytest

from vibectl.cli import cli


# Common fixture for mocking Config
@pytest.fixture
def mock_config() -> Generator[Mock, None, None]:
    """Fixture providing a mocked Config instance."""
    with patch("vibectl.cli.Config") as mock_config_class:
        mock_config = Mock()
        mock_config_class.return_value = mock_config
        yield mock_config


# Fixture to mock console_manager (if needed, assuming it's used by the functions)
@pytest.fixture
def mock_console() -> Generator[Mock, None, None]:
    """Fixture providing a mocked console_manager."""
    with patch("vibectl.cli.console_manager") as mock_console_manager:
        yield mock_console_manager


@pytest.mark.asyncio
async def test_memory_show(mock_config: Mock, mock_console: Mock) -> None:
    """Test the memory show command."""
    show_cmd = cli.commands["memory"].commands["show"]  # type: ignore[attr-defined]
    # Setup direct mock for get_memory
    with patch("vibectl.cli.get_memory") as mock_get_memory:
        mock_get_memory.return_value = "Test memory content"

        # Execute directly
        await show_cmd.main([], standalone_mode=False)  # type: ignore[attr-defined]

        mock_get_memory.assert_called_once()


@pytest.mark.asyncio
async def test_memory_show_empty(mock_config: Mock, mock_console: Mock) -> None:
    """Test the memory show command with empty memory."""
    show_cmd = cli.commands["memory"].commands["show"]  # type: ignore[attr-defined]
    # Setup direct mock for get_memory
    with patch("vibectl.cli.get_memory") as mock_get_memory:
        mock_get_memory.return_value = ""

        # Execute directly
        await show_cmd.main([], standalone_mode=False)  # type: ignore[attr-defined]

        mock_get_memory.assert_called_once()
        # mock_console.print_note.assert_called_once_with("Memory is currently empty.")
        # mock_console.print.assert_not_called()


@pytest.mark.asyncio
async def test_memory_enable(mock_config: Mock, mock_console: Mock) -> None:
    """Test enabling memory."""
    unfreeze_cmd = cli.commands["memory"].commands["unfreeze"]  # type: ignore[attr-defined]
    # Setup direct mock for enable_memory
    with patch("vibectl.cli.enable_memory") as mock_enable:
        # Execute directly
        await unfreeze_cmd.main([], standalone_mode=False)  # type: ignore[attr-defined]

        mock_enable.assert_called_once_with()  # Function likely accesses config
        # mock_console.print_success.assert_called_once()


@pytest.mark.asyncio
async def test_memory_disable(mock_config: Mock, mock_console: Mock) -> None:
    """Test disabling memory."""
    freeze_cmd = cli.commands["memory"].commands["freeze"]  # type: ignore[attr-defined]
    # Setup direct mock for disable_memory
    with patch("vibectl.cli.disable_memory") as mock_disable:
        # Execute directly
        await freeze_cmd.main([], standalone_mode=False)  # type: ignore[attr-defined]

        mock_disable.assert_called_once_with()  # Function likely accesses config
        # internally
        # mock_console.print_success.assert_called_once()


@pytest.mark.asyncio
async def test_memory_clear(mock_config: Mock, mock_console: Mock) -> None:
    """Test clearing memory."""
    clear_cmd = cli.commands["memory"].commands["clear"]  # type: ignore[attr-defined]
    # Setup direct mock for clear_memory
    with patch("vibectl.cli.clear_memory") as mock_clear:
        # Execute directly
        await clear_cmd.main([], standalone_mode=False)  # type: ignore[attr-defined]

        mock_clear.assert_called_once_with()  # Function likely accesses config
        # internally
        # mock_console.print_success.assert_called_once()


@pytest.mark.asyncio
async def test_memory_clear_error(mock_config: Mock) -> None:
    """Test error handling when clearing memory."""
    clear_cmd = cli.commands["memory"].commands["clear"]  # type: ignore[attr-defined]
    # Setup direct mock to throw an error
    with (
        patch("vibectl.cli.clear_memory") as mock_clear,
        patch("vibectl.cli.handle_exception") as mock_handle_exception,
    ):
        test_exception = ValueError("Test error")
        mock_clear.side_effect = test_exception

        # Execute directly
        await clear_cmd.main([], standalone_mode=False)  # type: ignore[attr-defined]

        mock_clear.assert_called_once_with()
        mock_handle_exception.assert_called_once_with(test_exception)


@pytest.mark.asyncio
async def test_memory_config_error(mock_config: Mock) -> None:
    """Test error handling for memory commands with config errors."""
    show_cmd = cli.commands["memory"].commands["show"]  # type: ignore[attr-defined]
    # Setup direct mock to throw an error
    with (
        patch("vibectl.cli.get_memory") as mock_get_memory,
        patch("vibectl.cli.handle_exception") as mock_handle_exception,
    ):
        test_exception = ValueError("Config error")
        mock_get_memory.side_effect = test_exception

        # Execute directly
        await show_cmd.main([], standalone_mode=False)  # type: ignore[attr-defined]

        mock_get_memory.assert_called_once_with()
        mock_handle_exception.assert_called_once_with(test_exception)


@pytest.mark.asyncio
async def test_memory_integration(mock_config: Mock, mock_console: Mock) -> None:
    """End-to-end test for memory commands.

    This test verifies that memory commands work together correctly.
    """
    clear_cmd = cli.commands["memory"].commands["clear"]  # type: ignore[attr-defined]
    unfreeze_cmd = cli.commands["memory"].commands["unfreeze"]  # type: ignore[attr-defined]
    show_cmd = cli.commands["memory"].commands["show"]  # type: ignore[attr-defined]
    freeze_cmd = cli.commands["memory"].commands["freeze"]  # type: ignore[attr-defined]

    # Setup mocks for CLI memory functions
    with (
        patch("vibectl.cli.get_memory") as mock_get_memory,
        patch("vibectl.cli.clear_memory") as mock_clear,
        patch("vibectl.cli.enable_memory") as mock_enable,
        patch("vibectl.cli.disable_memory") as mock_disable,
    ):
        # Configure get_memory to return empty string initially, then updated
        mock_get_memory.side_effect = ["", "Updated memory content"]

        # Test clearing memory
        await clear_cmd.main([], standalone_mode=False)  # type: ignore[attr-defined]
        mock_clear.assert_called_once_with()

        # Test enabling memory (unfreeze)
        await unfreeze_cmd.main([], standalone_mode=False)  # type: ignore[attr-defined]
        mock_enable.assert_called_once_with()

        # Test showing memory content (should be empty first)
        await show_cmd.main([], standalone_mode=False)  # type: ignore[attr-defined]
        assert mock_get_memory.call_count == 1  # Called once so far
        # Add assertion for empty state if needed - Removed console check

        # Simulate some action that updates memory (outside this test's direct scope)
        # Now configure get_memory to return the updated content for the next call
        # (This part is conceptual as the update isn't directly tested here)
        # For the test, we just check the sequence of calls

        # Test disabling memory (freeze)
        await freeze_cmd.main([], standalone_mode=False)  # type: ignore[attr-defined]
        mock_disable.assert_called_once_with()

        # Test clearing memory again
        mock_clear.reset_mock()
        await clear_cmd.main([], standalone_mode=False)  # type: ignore[attr-defined]
        mock_clear.assert_called_once_with()


@pytest.mark.asyncio
async def test_memory_update(mock_config: Mock, mock_console: Mock) -> None:
    """Test the memory update command."""
    update_cmd = cli.commands["memory"].commands["update"]  # type: ignore[attr-defined]
    # Setup mocks
    with (
        patch("vibectl.cli.get_memory") as mock_get_memory,
        patch("vibectl.cli.set_memory") as mock_set_memory,
        patch("vibectl.cli.llm.get_model") as mock_get_model,
    ):
        # Configure get_memory to return existing memory
        mock_get_memory.return_value = "Existing memory content"

        # Mock the model response
        mock_model = Mock()
        mock_response = Mock()
        mock_response.text.return_value = "Updated memory content"
        mock_model.prompt.return_value = (
            mock_response  # Simulate the llm library structure
        )
        mock_get_model.return_value = mock_model

        # Execute the command directly
        await update_cmd.main(
            ["Additional context about deployment"],
            standalone_mode=False,  # type: ignore[attr-defined]
        )

        mock_get_memory.assert_called_once_with()
        mock_get_model.assert_called_once()
        mock_model.prompt.assert_called_once()
        # Verify the prompt content
        prompt_call_args = mock_model.prompt.call_args.args
        assert "Existing memory content" in prompt_call_args[0]
        assert "Additional context about deployment" in prompt_call_args[0]

        mock_set_memory.assert_called_once_with(
            "Updated memory content", mock_config
        )  # Function likely accesses config internally
        # mock_console.print_success.assert_called_once()


@pytest.mark.asyncio
async def test_memory_update_error(mock_config: Mock) -> None:
    """Test error handling in the memory update command."""
    update_cmd = cli.commands["memory"].commands["update"]  # type: ignore[attr-defined]
    # Setup mocks with error
    with (
        patch("vibectl.cli.get_memory") as mock_get_memory,
        patch("vibectl.cli.llm.get_model") as mock_get_model,
        patch("vibectl.cli.handle_exception") as mock_handle_exception,
    ):
        # Configure get_memory to return existing memory
        mock_get_memory.return_value = "Existing memory content"
        test_exception = Exception("Test LLM error")
        # Mock the model to raise an exception
        mock_get_model.side_effect = test_exception

        # Execute the command directly
        await update_cmd.main(
            ["Additional context about deployment"], standalone_mode=False
        )  # type: ignore[attr-defined]

        mock_get_memory.assert_called_once_with()
        mock_get_model.assert_called_once()
        mock_handle_exception.assert_called_once_with(test_exception)


@pytest.mark.asyncio
@patch("sys.stdin")
async def test_memory_set_stdin_accepted(
    mock_stdin: Mock, mock_config: Mock, mock_console: Mock
) -> None:
    """Test that memory set accepts piped input (stdin) and sets memory content."""
    set_cmd = cli.commands["memory"].commands["set"]  # type: ignore[attr-defined]
    test_input = "Memory from stdin!"
    mock_stdin.isatty.return_value = False
    mock_stdin.read.return_value = test_input

    with patch("vibectl.cli.set_memory") as mock_set_memory:
        await set_cmd.main([], standalone_mode=False)  # type: ignore[attr-defined]

    mock_set_memory.assert_called_once_with(
        test_input
    )  # Function likely accesses config internally
    # mock_console.print_success.assert_called_once()
