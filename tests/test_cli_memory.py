"""Tests for the memory-related CLI commands.

This module tests the memory commands of vibectl.
"""

from collections.abc import Generator

# Import Any for type hinting
from unittest.mock import AsyncMock, Mock, patch

import pytest
from asyncclick.testing import CliRunner

from vibectl.cli import cli
from vibectl.config import DEFAULT_CONFIG
from vibectl.model_adapter import LLMMetrics
from vibectl.subcommands.memory_update_cmd import Error, Success


# Common fixture for mocking Config
@pytest.fixture
def mock_config() -> Generator[Mock, None, None]:
    """Fixture providing a mocked Config instance."""
    with patch("vibectl.cli.Config") as mock_config_class:
        mock_config_instance = Mock()
        # Default behavior for get_model_key to avoid TypeErrors with os.environ
        mock_config_instance.get_model_key.return_value = None
        # Default behavior for general .get() calls if needed,
        # can be overridden in tests
        # Example: mock_config_instance.get.return_value = "default-value"
        mock_config_class.return_value = mock_config_instance
        yield mock_config_instance


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
    with patch("vibectl.cli.get_memory") as mock_get_memory:
        mock_get_memory.return_value = "Test memory content"

        await show_cmd.main([], standalone_mode=False)

        mock_get_memory.assert_called_once()


@pytest.mark.asyncio
async def test_memory_show_empty(mock_config: Mock, mock_console: Mock) -> None:
    """Test the memory show command with empty memory."""
    show_cmd = cli.commands["memory"].commands["show"]  # type: ignore[attr-defined]
    with patch("vibectl.cli.get_memory") as mock_get_memory:
        mock_get_memory.return_value = ""

        await show_cmd.main([], standalone_mode=False)

        mock_get_memory.assert_called_once()
        mock_console.print.assert_not_called()


@pytest.mark.asyncio
async def test_memory_enable(mock_config: Mock, mock_console: Mock) -> None:
    """Test enabling memory."""
    unfreeze_cmd = cli.commands["memory"].commands["unfreeze"]  # type: ignore[attr-defined]
    with patch("vibectl.cli.enable_memory") as mock_enable:
        await unfreeze_cmd.main([], standalone_mode=False)

        mock_enable.assert_called_once_with()
        mock_console.print_success.assert_called_once()


@pytest.mark.asyncio
async def test_memory_disable(mock_config: Mock, mock_console: Mock) -> None:
    """Test disabling memory."""
    freeze_cmd = cli.commands["memory"].commands["freeze"]  # type: ignore[attr-defined]
    with patch("vibectl.cli.disable_memory") as mock_disable:
        await freeze_cmd.main([], standalone_mode=False)

        mock_disable.assert_called_once_with()
        mock_console.print_success.assert_called_once()


@pytest.mark.asyncio
async def test_memory_clear(mock_config: Mock, mock_console: Mock) -> None:
    """Test clearing memory."""
    clear_cmd = cli.commands["memory"].commands["clear"]  # type: ignore[attr-defined]
    with patch("vibectl.cli.clear_memory") as mock_clear:
        await clear_cmd.main([], standalone_mode=False)

        mock_clear.assert_called_once_with()
        mock_console.print_success.assert_called_once()


@pytest.mark.asyncio
async def test_memory_clear_error(mock_config: Mock) -> None:
    """Test error handling when clearing memory."""
    clear_cmd = cli.commands["memory"].commands["clear"]  # type: ignore[attr-defined]
    with (
        patch("vibectl.cli.clear_memory") as mock_clear,
        patch("vibectl.cli.handle_exception") as mock_handle_exception,
    ):
        test_exception = ValueError("Test error")
        mock_clear.side_effect = test_exception

        await clear_cmd.main([], standalone_mode=False)

        mock_clear.assert_called_once_with()
        mock_handle_exception.assert_called_once_with(test_exception)


@pytest.mark.asyncio
async def test_memory_config_error(mock_config: Mock) -> None:
    """Test error handling for memory commands with config errors."""
    show_cmd = cli.commands["memory"].commands["show"]  # type: ignore[attr-defined]
    with (
        patch("vibectl.cli.get_memory") as mock_get_memory,
        patch("vibectl.cli.handle_exception") as mock_handle_exception,
    ):
        test_exception = ValueError("Config error")
        mock_get_memory.side_effect = test_exception

        await show_cmd.main([], standalone_mode=False)

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
async def test_memory_update(mock_config: Mock) -> None:
    """Test the memory update command."""
    # Path to the new logic function, targeting where it's imported in cli.py
    run_logic_path = "vibectl.cli.run_memory_update_logic"

    with patch(run_logic_path, new_callable=AsyncMock) as mock_run_logic:
        mock_config.get.side_effect = lambda key, default=None: DEFAULT_CONFIG.get(
            key, default
        )

        # Mock the return value of the core logic function
        expected_updated_memory = "Updated memory from mock logic"
        mock_llm_metrics = Mock(spec=LLMMetrics)
        mock_llm_metrics.latency_ms = 123.45
        # Set input and output tokens instead of total_tokens
        mock_llm_metrics.token_input = 20
        mock_llm_metrics.token_output = 30
        mock_llm_metrics.total_processing_duration_ms = (
            None  # Explicitly set if spec requires
        )
        mock_llm_metrics.fragments_used = None
        mock_llm_metrics.call_count = 1

        expected_data_string = (
            f"Memory updated successfully.\n"
            f"Updated Memory Content:\n{expected_updated_memory}"
        )
        total_tokens = mock_llm_metrics.token_input + mock_llm_metrics.token_output
        if total_tokens > 0:
            expected_data_string += (
                f"\nLLM Metrics: Latency={mock_llm_metrics.latency_ms:.2f}ms, "
                f"Tokens={total_tokens}"
            )
        else:
            expected_data_string += (
                f"\nLLM Metrics: Latency={mock_llm_metrics.latency_ms:.2f}ms"
            )

        mock_run_logic.return_value = Success(
            data=expected_data_string,
            metrics=mock_llm_metrics,
        )

        # Use CliRunner to invoke the command
        runner = CliRunner()
        # Pass --show-streaming to the CLI to ensure it's handled at that layer,
        # even if not propagated to run_memory_update_logic
        cli_result = await runner.invoke(
            cli,
            ["memory", "update", "New context to add to memory", "--show-streaming"],
        )

        # Assertions
        assert cli_result.exit_code == 0, (
            f"CLI exited with {cli_result.exit_code}, output: {cli_result.output}"
        )
        # Check that the mocked logic function was called
        mock_run_logic.assert_called_once_with(
            update_text_str="New context to add to memory",
            model_name=None,
        )

        assert "Updated memory from mock logic" in cli_result.output
        assert "LLM Metrics: Latency=123.45ms, Tokens=50" in cli_result.output


@pytest.mark.asyncio
async def test_memory_update_error(mock_config: Mock) -> None:
    """Test the memory update command error handling."""
    run_logic_path = "vibectl.cli.run_memory_update_logic"
    with patch(run_logic_path, new_callable=AsyncMock) as mock_run_logic:
        mock_config.get.side_effect = lambda key, default=None: DEFAULT_CONFIG.get(
            key, default
        )

        # Mock the return value of the core logic function to be an error
        expected_error_message = "LLM failed to update memory as simulated"
        mock_run_logic.return_value = Error(error=expected_error_message)

        # Use CliRunner to invoke the command
        runner = CliRunner()
        # Pass --show-streaming to the CLI to ensure it's handled at that layer
        cli_result = await runner.invoke(
            cli, ["memory", "update", "Some failing context", "--show-streaming"]
        )

        # Assertions
        assert cli_result.exit_code != 0, (
            f"CLI exited with {cli_result.exit_code}, output: {cli_result.output}"
        )

        # Check that the mocked logic function was called
        mock_run_logic.assert_called_once_with(
            update_text_str="Some failing context",
            model_name=None,  # Assuming no --model flag was passed
            # show_metrics is not a param of run_memory_update_logic
            # show_streaming is also not a param of run_memory_update_logic
        )
        assert expected_error_message in cli_result.output

        # Verify memory was not updated (assuming error prevents update)


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


@pytest.mark.asyncio
async def test_memory_off_does_not_call_set_memory_on_clear(
    mock_config: Mock, mock_console: Mock
) -> None:
    """Test that memory is off and does not call set_memory on clear."""
    clear_cmd = cli.commands["memory"].commands["clear"]  # type: ignore[attr-defined]
    with (
        patch("vibectl.cli.clear_memory") as mock_clear,
        patch("vibectl.cli.set_memory") as mock_set_memory,
        patch("vibectl.cli.handle_exception") as mock_handle_exception,
    ):
        mock_config.get.side_effect = (
            lambda key, default=None: default if key == "memory_off" else None
        )

        await clear_cmd.main([], standalone_mode=False)

        mock_clear.assert_called_once_with()
        mock_set_memory.assert_not_called()
        mock_handle_exception.assert_not_called()
