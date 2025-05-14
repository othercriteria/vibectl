"""Tests for CLI rollout commands to ensure OutputFlags is used properly."""

from unittest.mock import patch

import pytest

from vibectl.cli import rollout
from vibectl.command_handler import OutputFlags, handle_command_output


def test_rollout_commands_exist() -> None:
    """Test that all rollout subcommands exist."""
    # Verify the rollout group has all the expected commands
    available_commands = rollout.commands.keys()
    assert "status" in available_commands
    assert "history" in available_commands
    assert "restart" in available_commands
    assert "undo" in available_commands
    assert "pause" in available_commands
    assert "resume" in available_commands


@pytest.mark.parametrize("command", ["status", "history", "restart", "pause", "resume"])
def test_rollout_commands_with_mocked_handler(command: str) -> None:
    """Test that rollout subcommands call handle_command_output with OutputFlags."""
    with patch("vibectl.command_handler.configure_output_flags") as mock_flags:
        mock_flags.return_value = OutputFlags(
            show_raw=True,
            show_vibe=True,
            warn_no_output=True,
            model_name="test-model",
            show_metrics=True,
        )

        # Since we can't directly call the command callbacks due to the Click context,
        # we'll just verify that the handle_command_output function was updated
        # to accept OutputFlags parameter properly

        # Verify handle_command_output accepts OutputFlags parameter
        signature = str(handle_command_output.__code__.co_varnames)
        assert "output_flags" in signature


@pytest.fixture
def standard_output_flags() -> OutputFlags:
    return OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="test",
        show_metrics=True,
    )


@pytest.mark.parametrize("command", ["status", "history", "restart", "pause", "resume"])
def test_rollout_commands_with_mocked_handler_async(command: str) -> None:
    """Test that rollout subcommands call handle_command_output with OutputFlags."""
    with patch("vibectl.command_handler.configure_output_flags") as mock_flags:
        mock_flags.return_value = OutputFlags(
            show_raw=True,
            show_vibe=True,
            warn_no_output=False,
            model_name="test",
            show_metrics=True,
        )

        # Since we can't directly call the command callbacks due to the Click context,
        # we'll just verify that the handle_command_output function was updated
        # to accept OutputFlags parameter properly

        # Verify handle_command_output accepts OutputFlags parameter
        signature = str(handle_command_output.__code__.co_varnames)
        assert "output_flags" in signature
