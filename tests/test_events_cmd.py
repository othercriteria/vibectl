"""Tests for the events subcommand of vibectl."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from click.testing import CliRunner

from vibectl.cli import cli
from vibectl.types import Error, Success


@patch("vibectl.subcommands.events_cmd.run_kubectl")
@patch("vibectl.subcommands.events_cmd.handle_command_output")
@pytest.mark.asyncio
async def test_events_error_handling(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test error handling in events command."""
    mock_run_kubectl.return_value = Error(error="Test error")

    cmd_obj = cli.commands["events"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main([])

    assert exc_info.value.code != 0
    mock_run_kubectl.assert_called_once_with(["events"], capture=True)
    mock_handle_output.assert_not_called()


@patch("vibectl.subcommands.events_cmd.run_kubectl")
@patch("vibectl.subcommands.events_cmd.handle_command_output")
@pytest.mark.asyncio
async def test_events_output_processing(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test events command output processing."""
    mock_run_kubectl.return_value = Success(data="Event data")

    cmd_obj = cli.commands["events"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main([])

    assert exc_info.value.code == 0
    mock_run_kubectl.assert_called_once_with(["events"], capture=True)
    mock_handle_output.assert_called_once()


@patch("vibectl.subcommands.events_cmd.handle_vibe_request", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_events_vibe_request(
    mock_handle_vibe: AsyncMock,
    cli_runner: CliRunner,
) -> None:
    """Test events command with vibe request."""
    mock_handle_vibe.return_value = Success()

    cmd_obj = cli.commands["events"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["vibe", "show", "me", "recent", "events"])

    assert exc_info.value.code == 0
    mock_handle_vibe.assert_called_once()
    args, kwargs = mock_handle_vibe.call_args
    assert kwargs["request"] == "show me recent events"
    assert kwargs["command"] == "events"


@pytest.mark.asyncio
async def test_events_vibe_no_request(
    cli_runner: CliRunner,
) -> None:
    """Test events vibe command without a request."""
    with (
        patch(
            "vibectl.subcommands.events_cmd.handle_vibe_request", new_callable=AsyncMock
        ) as mock_handle_vibe,
    ):
        cmd_obj = cli.commands["events"]
        with pytest.raises(SystemExit) as exc_info:
            await cmd_obj.main(["vibe"])

    assert exc_info.value.code != 0
    mock_handle_vibe.assert_not_called()
