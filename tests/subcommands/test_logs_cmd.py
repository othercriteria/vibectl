"""Tests for the logs subcommand CLI interface.

These tests were moved from test_cli.py for clarity and maintainability.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from click.testing import CliRunner

from vibectl.cli import cli
from vibectl.config import DEFAULT_CONFIG
from vibectl.prompts.logs import logs_prompt

# Ensure DEFAULT_MODEL is always a string for use in OutputFlags
DEFAULT_MODEL = str(DEFAULT_CONFIG["model"])


@patch("vibectl.subcommands.logs_cmd.run_kubectl")
@patch("vibectl.subcommands.logs_cmd.handle_command_output")
@pytest.mark.asyncio
async def test_logs_basic(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test basic logs command functionality."""
    from vibectl.types import Success

    mock_run_kubectl.return_value = Success(data="test output")

    cmd_obj = cli.commands["logs"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["pod", "my-pod"])

    assert exc_info.value.code == 0
    mock_run_kubectl.assert_called_once_with(["logs", "pod", "my-pod"])
    mock_handle_output.assert_called_once()


@patch("vibectl.subcommands.logs_cmd.run_kubectl")
@patch("vibectl.subcommands.logs_cmd.handle_command_output")
@pytest.mark.asyncio
async def test_logs_with_args(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test logs command with additional arguments."""
    from vibectl.types import Success

    mock_run_kubectl.return_value = Success(data="test output")

    cmd_obj = cli.commands["logs"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["pod", "my-pod", "-n", "default"])

    assert exc_info.value.code == 0
    mock_run_kubectl.assert_called_once_with(["logs", "pod", "my-pod", "-n", "default"])
    mock_handle_output.assert_called_once()


@patch("vibectl.subcommands.logs_cmd.configure_output_flags")
@patch("vibectl.subcommands.logs_cmd.run_kubectl")
@patch("vibectl.subcommands.logs_cmd.handle_command_output")
@pytest.mark.asyncio
async def test_logs_with_flags(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test logs command with output flags."""
    from vibectl.command_handler import OutputFlags
    from vibectl.types import Success

    mock_flags = OutputFlags(
        show_raw=True,
        show_vibe=False,
        model_name="test-model-foo",
        warn_no_output=True,
        show_kubectl=False,
        show_metrics=True,
    )
    mock_configure_flags.return_value = mock_flags
    mock_configure_flags.model_name_check = "test-model-bar"

    mock_run_kubectl.return_value = Success(data="test output")

    cmd_obj = cli.commands["logs"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(
            [
                "pod",
                "my-pod",
                "--show-raw-output",
                "--no-show-vibe",
                "--model",
                "test-model-foo",
            ]
        )

    assert exc_info.value.code == 0
    mock_run_kubectl.assert_called_once_with(["logs", "pod", "my-pod"])
    mock_handle_output.assert_called_once()

    # Verify configure_output_flags called correctly by the subcommand's run function
    # (assuming run_logs_command calls it like run_get_command does)
    mock_configure_flags.assert_called_once_with(
        show_raw_output=True,
        show_vibe=False,
        model="test-model-foo",
        show_kubectl=None,
        show_metrics=None,
        show_streaming=None,
    )
    # Verify the original mock object attribute wasn't changed
    assert mock_configure_flags.model_name_check == "test-model-bar"


@patch("vibectl.subcommands.logs_cmd.run_kubectl")
@patch("vibectl.subcommands.logs_cmd.handle_command_output")
@pytest.mark.asyncio
async def test_logs_no_output(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test logs command when kubectl returns no output."""
    from vibectl.types import Success

    mock_run_kubectl.return_value = Success(data="")

    cmd_obj = cli.commands["logs"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["pod", "my-pod"])

    assert exc_info.value.code == 0
    mock_run_kubectl.assert_called_once_with(["logs", "pod", "my-pod"])
    mock_handle_output.assert_not_called()


@patch("vibectl.subcommands.logs_cmd.run_kubectl")
@patch("vibectl.subcommands.logs_cmd.handle_command_output")
@pytest.mark.asyncio
async def test_logs_truncation_warning(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test logs command with output that might need truncation."""
    from vibectl.types import Success

    # Create a large output that exceeds MAX_TOKEN_LIMIT * LOGS_TRUNCATION_RATIO
    large_output = "x" * (10000 * 3 + 1)  # Just over the limit
    mock_run_kubectl.return_value = Success(data=large_output)

    cmd_obj = cli.commands["logs"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["pod", "my-pod"])

    assert exc_info.value.code == 0
    mock_run_kubectl.assert_called_once_with(["logs", "pod", "my-pod"])
    mock_handle_output.assert_called_once()


@patch("vibectl.subcommands.logs_cmd.handle_vibe_request", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_logs_vibe_request(
    mock_handle_vibe: AsyncMock,
    cli_runner: CliRunner,
) -> None:
    """Test logs command with vibe request."""
    from vibectl.types import Success

    mock_handle_vibe.return_value = Success()

    cmd_obj = cli.commands["logs"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["vibe", "show", "me", "pod", "logs"])

    assert exc_info.value.code == 0
    mock_handle_vibe.assert_called_once()
    args, kwargs = mock_handle_vibe.call_args
    assert kwargs["request"] == "show me pod logs"
    assert kwargs["command"] == "logs"


@pytest.mark.asyncio
async def test_logs_vibe_no_request(
    cli_runner: CliRunner,
) -> None:
    """Test logs vibe command without a request."""
    cmd_obj = cli.commands["logs"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["vibe"])

    assert exc_info.value.code != 0


@patch("vibectl.subcommands.logs_cmd.configure_output_flags")
@patch("vibectl.subcommands.logs_cmd.run_kubectl")
@patch("vibectl.subcommands.logs_cmd.handle_command_output")
@pytest.mark.asyncio
async def test_logs_error_handling(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test logs command error handling."""
    from vibectl.command_handler import OutputFlags
    from vibectl.types import Error

    # Configure output flags
    mock_configure_flags.return_value = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="model-xyz-1.2.3",
        show_kubectl=False,
        show_metrics=True,
    )

    # Setup mock to return an Error
    mock_run_kubectl.return_value = Error(error="Test error")

    # Invoke the command
    cmd_obj = cli.commands["logs"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["pod", "my-pod"])

    # Verify error handling
    assert exc_info.value.code != 0
    mock_handle_output.assert_not_called()


@patch(
    "vibectl.subcommands.logs_cmd.handle_watch_with_live_display",
    new_callable=AsyncMock,
)
@patch("vibectl.subcommands.logs_cmd.run_kubectl")
@patch("vibectl.subcommands.logs_cmd.handle_command_output")
@pytest.mark.asyncio
async def test_logs_follow_uses_live_display(
    mock_handle_command_output: Mock,
    mock_run_kubectl: Mock,
    mock_handle_watch_with_live_display: AsyncMock,
    cli_runner: CliRunner,
) -> None:
    """Test \'logs --follow\' uses handle_watch_with_live_display."""
    from vibectl.types import Success

    mock_handle_watch_with_live_display.return_value = Success(
        data="live display output"
    )

    cmd_obj = cli.commands["logs"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["my-pod", "--follow", "-n", "test-ns"])

    assert exc_info.value.code == 0
    mock_handle_watch_with_live_display.assert_called_once()
    mock_run_kubectl.assert_not_called()
    mock_handle_command_output.assert_not_called()

    args, kwargs = mock_handle_watch_with_live_display.call_args
    assert kwargs["command"] == "logs"
    assert kwargs["resource"] == "my-pod"
    assert "--follow" in kwargs["args"]
    assert "-n" in kwargs["args"]
    assert "test-ns" in kwargs["args"]
    assert kwargs["summary_prompt_func"] == logs_prompt


@patch(
    "vibectl.subcommands.logs_cmd.handle_watch_with_live_display",
    new_callable=AsyncMock,
)
@patch("vibectl.subcommands.logs_cmd.run_kubectl")
@patch("vibectl.subcommands.logs_cmd.handle_command_output")
@pytest.mark.asyncio
async def test_logs_follow_short_flag_uses_live_display(
    mock_handle_command_output: Mock,
    mock_run_kubectl: Mock,
    mock_handle_watch_with_live_display: AsyncMock,
    cli_runner: CliRunner,
) -> None:
    """Test \'logs -f\' uses handle_watch_with_live_display."""
    from vibectl.types import Success

    mock_handle_watch_with_live_display.return_value = Success(
        data="live display output"
    )

    cmd_obj = cli.commands["logs"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["another-pod", "-f"])

    assert exc_info.value.code == 0
    mock_handle_watch_with_live_display.assert_called_once()
    mock_run_kubectl.assert_not_called()
    mock_handle_command_output.assert_not_called()

    args, kwargs = mock_handle_watch_with_live_display.call_args
    assert kwargs["command"] == "logs"
    assert kwargs["resource"] == "another-pod"
    assert "-f" in kwargs["args"]
    assert kwargs["summary_prompt_func"] == logs_prompt


@patch("vibectl.subcommands.logs_cmd.configure_output_flags")
@patch(
    "vibectl.subcommands.logs_cmd.handle_watch_with_live_display",
    new_callable=AsyncMock,
)
@pytest.mark.asyncio
async def test_logs_follow_with_show_vibe_flag(
    mock_handle_watch_with_live_display: AsyncMock,
    mock_configure_output_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test logs --follow with --show-vibe uses live display and correct flags."""
    from vibectl.command_handler import OutputFlags
    from vibectl.types import Success

    # Configure output flags mock
    mock_flags = OutputFlags(
        show_raw=False,  # Default for this test path
        show_vibe=True,  # Explicitly set by --show-vibe flag
        warn_no_output=False,
        model_name=DEFAULT_MODEL,  # Use defined DEFAULT_MODEL
        show_kubectl=False,  # Default
        show_metrics=False,  # Default
        show_streaming=True,  # Assumed True when show_vibe is True for logs
    )
    mock_configure_output_flags.return_value = mock_flags

    # Mock handle_watch_with_live_display behavior
    mock_handle_watch_with_live_display.return_value = Success(
        data="Live display finished"
    )

    cmd_obj = cli.commands["logs"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["podname", "--follow", "--show-vibe"])

    assert exc_info.value.code == 0

    # Verify configure_output_flags was called correctly
    mock_configure_output_flags.assert_called_once_with(
        show_raw_output=None,  # CLI passes None if not specified
        show_vibe=True,  # Explicitly passed by --show-vibe
        model=None,  # CLI passes None if not specified
        show_kubectl=None,  # Default from common_command_options
        show_metrics=None,  # Default from common_command_options
        show_streaming=None,  # CLI passes None if not specified
    )

    # Verify handle_watch_with_live_display was called correctly
    mock_handle_watch_with_live_display.assert_called_once_with(
        command="logs",
        resource="podname",
        args=("--follow",),
        output_flags=mock_flags,
        summary_prompt_func=logs_prompt,
    )


@patch(
    "vibectl.subcommands.logs_cmd.handle_watch_with_live_display",
    new_callable=AsyncMock,
)
@patch("vibectl.subcommands.logs_cmd.run_kubectl")
@patch("vibectl.subcommands.logs_cmd.handle_command_output")
@pytest.mark.asyncio
async def test_logs_no_follow_does_not_use_live_display(
    mock_handle_command_output: Mock,
    mock_run_kubectl: Mock,
    mock_handle_watch_with_live_display: AsyncMock,
    cli_runner: CliRunner,
) -> None:
    """Test plain \'logs\' (no --follow) does NOT use handle_watch_with_live_display."""
    from vibectl.types import Success

    mock_run_kubectl.return_value = Success(data="standard log output")

    cmd_obj = cli.commands["logs"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["my-pod", "-n", "test-ns"])

    assert exc_info.value.code == 0
    mock_handle_watch_with_live_display.assert_not_called()
    mock_run_kubectl.assert_called_once_with(["logs", "my-pod", "-n", "test-ns"])
    mock_handle_command_output.assert_called_once()
