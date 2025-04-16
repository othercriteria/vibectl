"""Tests for the memory-related CLI commands.

This module tests the memory commands of vibectl.
"""

from unittest.mock import Mock, patch

from click.testing import CliRunner

from vibectl.cli import cli


def test_memory_show(
    cli_runner: CliRunner, mock_config: Mock, mock_console: Mock
) -> None:
    """Test the memory show command."""
    # Setup direct mock for get_memory
    with patch("vibectl.cli.get_memory") as mock_get_memory:
        mock_get_memory.return_value = "Test memory content"

        # Execute with full CLI environment
        result = cli_runner.invoke(cli, ["memory", "show"], catch_exceptions=False)

        # Assert based on exit code only - the actual output formatting
        # is handled by the console manager which is mocked
        assert result.exit_code == 0
        mock_get_memory.assert_called_once()


def test_memory_show_empty(
    cli_runner: CliRunner, mock_config: Mock, mock_console: Mock
) -> None:
    """Test the memory show command with empty memory."""
    # Setup direct mock for get_memory
    with patch("vibectl.cli.get_memory") as mock_get_memory:
        mock_get_memory.return_value = ""

        # Execute with full CLI environment
        result = cli_runner.invoke(cli, ["memory", "show"], catch_exceptions=False)

        # Assert based on exit code only
        assert result.exit_code == 0
        mock_get_memory.assert_called_once()


def test_memory_enable(
    cli_runner: CliRunner, mock_config: Mock, mock_console: Mock
) -> None:
    """Test enabling memory."""
    # Setup direct mock for enable_memory
    with patch("vibectl.cli.enable_memory") as mock_enable:
        # Execute with full CLI environment
        result = cli_runner.invoke(cli, ["memory", "unfreeze"], catch_exceptions=False)

        # Assert based on exit code only
        assert result.exit_code == 0
        mock_enable.assert_called_once()


def test_memory_disable(
    cli_runner: CliRunner, mock_config: Mock, mock_console: Mock
) -> None:
    """Test disabling memory."""
    # Setup direct mock for disable_memory
    with patch("vibectl.cli.disable_memory") as mock_disable:
        # Execute with full CLI environment
        result = cli_runner.invoke(cli, ["memory", "freeze"], catch_exceptions=False)

        # Assert based on exit code only
        assert result.exit_code == 0
        mock_disable.assert_called_once()


def test_memory_clear(
    cli_runner: CliRunner, mock_config: Mock, mock_console: Mock
) -> None:
    """Test clearing memory."""
    # Setup direct mock for clear_memory
    with patch("vibectl.cli.clear_memory") as mock_clear:
        # Execute with full CLI environment
        result = cli_runner.invoke(cli, ["memory", "clear"], catch_exceptions=False)

        # Assert based on exit code only
        assert result.exit_code == 0
        mock_clear.assert_called_once()


def test_memory_clear_error(
    cli_runner: CliRunner, mock_config: Mock, mock_console: Mock
) -> None:
    """Test error handling when clearing memory."""
    # Setup direct mock to throw an error
    with patch("vibectl.cli.clear_memory") as mock_clear:
        mock_clear.side_effect = ValueError("Test error")

        # Handle the expected error - Click doesn't pass through to our
        # custom error handler in test environment, so we expect the exception
        result = cli_runner.invoke(cli, ["memory", "clear"])

        # In CLI testing environment, exceptions result in exit_code=1
        assert result.exit_code == 1
        mock_clear.assert_called_once()
        # Error is reflected in output if using catch_exceptions=True (default)
        assert "error" in result.output.lower()


def test_memory_config_error(cli_runner: CliRunner, mock_config: Mock) -> None:
    """Test error handling for memory commands with config errors."""
    # Setup direct mock to throw an error
    with patch("vibectl.cli.get_memory") as mock_get_memory:
        mock_get_memory.side_effect = ValueError("Test error")

        # Execute with error capture
        result = cli_runner.invoke(cli, ["memory", "show"])

        # Assert the error is handled in some way, either through exit code
        # or try-except in the code
        assert result.exit_code != 0 or "error" in result.output.lower()


def test_memory_integration(
    cli_runner: CliRunner, mock_config: Mock, mock_console: Mock
) -> None:
    """End-to-end test for memory commands.

    This test verifies that memory commands work together correctly.
    """
    # Setup mocks for CLI memory functions
    with (
        patch("vibectl.cli.get_memory") as mock_get_memory,
        patch("vibectl.cli.clear_memory") as mock_clear,
        patch("vibectl.cli.enable_memory") as mock_enable,
        patch("vibectl.cli.disable_memory") as mock_disable,
    ):
        # Configure get_memory to return empty string
        mock_get_memory.return_value = ""

        # Test clearing memory
        result = cli_runner.invoke(cli, ["memory", "clear"], catch_exceptions=False)
        assert result.exit_code == 0
        mock_clear.assert_called_once()

        # Test enabling memory (unfreeze)
        result = cli_runner.invoke(cli, ["memory", "unfreeze"], catch_exceptions=False)
        assert result.exit_code == 0
        mock_enable.assert_called_once()

        # Test showing memory content
        result = cli_runner.invoke(cli, ["memory", "show"], catch_exceptions=False)
        assert result.exit_code == 0
        mock_get_memory.assert_called()

        # Test disabling memory (freeze)
        result = cli_runner.invoke(cli, ["memory", "freeze"], catch_exceptions=False)
        assert result.exit_code == 0
        mock_disable.assert_called_once()

        # Test clearing memory again
        mock_clear.reset_mock()
        result = cli_runner.invoke(cli, ["memory", "clear"], catch_exceptions=False)
        assert result.exit_code == 0
        mock_clear.assert_called_once()


def test_memory_update(
    cli_runner: CliRunner, mock_config: Mock, mock_console: Mock
) -> None:
    """Test the memory update command."""
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
        mock_model.prompt.return_value.text.return_value = "Updated memory content"
        mock_get_model.return_value = mock_model

        # Execute the command
        result = cli_runner.invoke(
            cli,
            ["memory", "update", "Additional context about deployment"],
            catch_exceptions=False,
        )

        # Assert based on exit code and function calls
        assert result.exit_code == 0
        mock_get_memory.assert_called_once()
        mock_get_model.assert_called_once()
        mock_model.prompt.assert_called_once()
        mock_set_memory.assert_called_once_with("Updated memory content", mock_config)


def test_memory_update_error(
    cli_runner: CliRunner, mock_config: Mock, mock_console: Mock
) -> None:
    """Test error handling in the memory update command."""
    # Setup mocks with error
    with (
        patch("vibectl.cli.get_memory") as mock_get_memory,
        patch("vibectl.cli.llm.get_model") as mock_get_model,
    ):
        # Configure get_memory to return existing memory
        mock_get_memory.return_value = "Existing memory content"

        # Mock the model to raise an exception
        mock_get_model.side_effect = Exception("Test LLM error")

        # Execute the command
        result = cli_runner.invoke(
            cli, ["memory", "update", "Additional context about deployment"]
        )

        # Assert based on exit code
        assert result.exit_code != 0
        mock_get_memory.assert_called_once()
        mock_get_model.assert_called_once()
