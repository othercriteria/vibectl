"""Tests for the CLI delete command.

This module tests the delete command functionality of vibectl with focus on
error handling and confirmation functionality.
"""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from vibectl.cli import delete
from vibectl.prompt import PLAN_DELETE_PROMPT


def test_delete_vibe_request(cli_runner: CliRunner) -> None:
    """Test delete vibe request handling."""
    with patch(
        "vibectl.subcommands.delete_cmd.handle_vibe_request"
    ) as mock_handle_vibe_request:
        # Execute
        with patch("sys.exit"):
            result = cli_runner.invoke(delete, ["vibe", "delete the nginx pod"])

        # Assert
        assert result.exit_code == 0
        mock_handle_vibe_request.assert_called_once()
        args, kwargs = mock_handle_vibe_request.call_args
        assert kwargs["request"] == "delete the nginx pod"
        assert kwargs["command"] == "delete"
        assert "plan_prompt" in kwargs
        assert kwargs["plan_prompt"] == PLAN_DELETE_PROMPT
        assert kwargs["yes"] is False  # Verify yes flag is passed as False by default


def test_delete_vibe_request_with_yes_flag(cli_runner: CliRunner) -> None:
    """Test delete vibe request with yes flag to bypass confirmation."""
    with patch(
        "vibectl.subcommands.delete_cmd.handle_vibe_request"
    ) as mock_handle_vibe_request:
        # Execute with yes flag
        with patch("sys.exit"):
            result = cli_runner.invoke(
                delete, ["vibe", "delete the nginx pod", "--yes"]
            )

        # Assert
        assert result.exit_code == 0
        mock_handle_vibe_request.assert_called_once()
        args, kwargs = mock_handle_vibe_request.call_args
        assert kwargs["yes"] is True  # Verify yes flag is passed as True


@patch("vibectl.subcommands.delete_cmd.handle_standard_command")
def test_delete_standard(
    mock_handle_standard_command: MagicMock,
    cli_runner: CliRunner,
) -> None:
    """Test standard delete command has no confirmation."""
    # Execute delete command
    result = cli_runner.invoke(delete, ["pod", "nginx-pod"])

    # Assert standard command is called directly without confirmation
    assert result.exit_code == 0
    mock_handle_standard_command.assert_called_once()


@patch("vibectl.subcommands.delete_cmd.handle_standard_command")
def test_delete_handles_exception(
    mock_handle_standard_command: MagicMock,
    cli_runner: CliRunner,
) -> None:
    """Test error handling in delete command."""
    # Setup mock to raise an exception
    mock_error = ValueError("Test error")
    mock_handle_standard_command.side_effect = mock_error

    # Execute delete command
    result = cli_runner.invoke(delete, ["pod", "nginx-pod"])

    # Assert error output or exit code
    assert result.exit_code == 1
    assert "Error: Test error" in result.output
