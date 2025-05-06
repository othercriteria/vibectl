"""Tests for the CLI delete command.

This module tests the delete command functionality of vibectl with focus on
error handling and confirmation functionality.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vibectl.cli import cli


@pytest.mark.asyncio
async def test_delete_vibe_request() -> None:
    """Test delete vibe request handling."""
    with patch(
        "vibectl.subcommands.delete_cmd.handle_vibe_request", new_callable=AsyncMock
    ) as mock_handle_vibe_request:
        from vibectl.types import Success

        mock_handle_vibe_request.return_value = Success()

        cmd_obj = cli.commands["delete"]
        with pytest.raises(SystemExit) as exc_info:
            await cmd_obj.main(["vibe", "delete the nginx pod"])

        assert exc_info.value.code == 0
        mock_handle_vibe_request.assert_called_once()
        args, kwargs = mock_handle_vibe_request.call_args
        assert kwargs["request"] == "delete the nginx pod"
        assert kwargs["command"] == "delete"
        assert kwargs["yes"] is False


@pytest.mark.asyncio
async def test_delete_vibe_request_with_yes_flag() -> None:
    """Test delete vibe request with yes flag."""
    with patch(
        "vibectl.subcommands.delete_cmd.handle_vibe_request", new_callable=AsyncMock
    ) as mock_handle_vibe_request:
        from vibectl.types import Success

        mock_handle_vibe_request.return_value = Success()

        cmd_obj = cli.commands["delete"]
        with pytest.raises(SystemExit) as exc_info:
            await cmd_obj.main(["vibe", "delete the nginx pod", "--yes"])

        assert exc_info.value.code == 0
        mock_handle_vibe_request.assert_called_once()
        args, kwargs = mock_handle_vibe_request.call_args
        assert kwargs["yes"] is True


@patch("vibectl.subcommands.delete_cmd.handle_standard_command")
@pytest.mark.asyncio
async def test_delete_standard(
    mock_handle_standard_command: MagicMock,
) -> None:
    """Test standard delete command has no confirmation."""
    from vibectl.types import Success

    mock_handle_standard_command.return_value = Success()

    cmd_obj = cli.commands["delete"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["pod", "nginx-pod"])

    assert exc_info.value.code == 0
    mock_handle_standard_command.assert_called_once()


@patch("vibectl.subcommands.delete_cmd.handle_standard_command")
@pytest.mark.asyncio
async def test_delete_handles_exception(
    mock_handle_standard_command: MagicMock,
) -> None:
    """Test error handling in delete command."""
    mock_error = ValueError("Test error")
    mock_handle_standard_command.side_effect = mock_error

    cmd_obj = cli.commands["delete"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["pod", "nginx-pod"])

    assert exc_info.value.code == 1
    mock_handle_standard_command.assert_called_once()
