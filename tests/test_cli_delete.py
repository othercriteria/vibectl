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
    with patch("vibectl.cli.handle_vibe_request") as mock_handle_vibe_request:
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


@patch("vibectl.cli.handle_standard_command")
@patch("vibectl.cli.click.confirm")
def test_delete_with_confirmation(
    mock_confirm: MagicMock,
    mock_handle_standard_command: MagicMock,
    cli_runner: CliRunner,
) -> None:
    """Test delete command with confirmation that gets confirmed."""
    # Setup mocks
    mock_confirm.return_value = True  # User confirms deletion

    # Execute delete command without yes flag
    result = cli_runner.invoke(delete, ["pod", "nginx-pod"])

    # Assert
    assert result.exit_code == 0
    mock_confirm.assert_called_once()


@patch("vibectl.cli.handle_standard_command")
@patch("vibectl.cli.click.confirm")
def test_delete_with_confirmation_cancelled(
    mock_confirm: MagicMock,
    mock_handle_standard_command: MagicMock,
    cli_runner: CliRunner,
) -> None:
    """Test delete command with confirmation that gets cancelled."""
    # Setup mocks
    mock_confirm.return_value = False  # User cancels deletion

    # Execute delete command without yes flag
    result = cli_runner.invoke(delete, ["pod", "nginx-pod"])

    # Assert
    assert result.exit_code == 0
    mock_confirm.assert_called_once()
    mock_handle_standard_command.assert_not_called()


@patch("vibectl.cli.handle_standard_command")
@patch("vibectl.cli.click.confirm")
def test_delete_yes_flag_bypasses_confirmation(
    mock_confirm: MagicMock,
    mock_handle_standard_command: MagicMock,
    cli_runner: CliRunner,
) -> None:
    """Test that yes flag bypasses confirmation."""
    # Execute delete command with --yes
    result = cli_runner.invoke(delete, ["pod", "nginx-pod", "--yes"])

    # Assert
    assert result.exit_code == 0
    mock_confirm.assert_not_called()
    mock_handle_standard_command.assert_called_once()


@patch("vibectl.cli.handle_standard_command")
@patch("vibectl.cli.handle_exception")
def test_delete_handles_exception(
    mock_handle_exception: MagicMock,
    mock_handle_standard_command: MagicMock,
    cli_runner: CliRunner,
) -> None:
    """Test error handling in delete command."""
    # Setup mock to raise an exception
    mock_error = ValueError("Test error")
    mock_handle_standard_command.side_effect = mock_error

    # Execute delete command with --yes to bypass confirmation
    cli_runner.invoke(delete, ["pod", "nginx-pod", "--yes"])

    # Assert exception handling was called
    mock_handle_exception.assert_called_once_with(mock_error)
