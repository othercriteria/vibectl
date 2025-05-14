"""Tests for the logs subcommand CLI interface.

These tests were moved from test_cli.py for clarity and maintainability.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from click.testing import CliRunner

from vibectl.cli import cli
from vibectl.config import DEFAULT_CONFIG


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
    mock_run_kubectl.assert_called_once_with(["logs", "pod", "my-pod"], capture=True)
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
    mock_run_kubectl.assert_called_once_with(
        ["logs", "pod", "my-pod", "-n", "default"], capture=True
    )
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
    mock_run_kubectl.assert_called_once_with(["logs", "pod", "my-pod"], capture=True)
    mock_handle_output.assert_called_once()

    # Verify configure_output_flags called correctly by the subcommand's run function
    # (assuming run_logs_command calls it like run_get_command does)
    mock_configure_flags.assert_called_once_with(
        show_raw_output=True,
        show_vibe=False,
        model="test-model-foo",
        show_kubectl=None,  # Assert None, as flag wasn't passed and default is None
        show_metrics=None,  # Expect None when flag not explicitly passed
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
    mock_run_kubectl.assert_called_once_with(["logs", "pod", "my-pod"], capture=True)
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
    mock_run_kubectl.assert_called_once_with(["logs", "pod", "my-pod"], capture=True)
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
    from vibectl.prompt import logs_prompt
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
    from vibectl.prompt import logs_prompt
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
    """Test \'logs --follow --show-vibe\' configures output flags correctly."""
    import typing  # For cast

    from vibectl.command_handler import OutputFlags
    from vibectl.types import Success

    # Expected OutputFlags when --show-vibe is passed and --model is not.
    # model_name should fall back to the default model from config.
    # Cast to str to satisfy linter, as DEFAULT_CONFIG["model"] might be typed broadly.
    default_model = typing.cast(str, DEFAULT_CONFIG["model"])
    expected_flags = OutputFlags(
        show_vibe=True,
        show_raw=False,
        model_name=default_model,  # Use default model (casted)
        show_kubectl=False,
        warn_no_output=True,
        show_metrics=True,
    )
    mock_configure_output_flags.return_value = expected_flags
    mock_handle_watch_with_live_display.return_value = Success(
        data="live display output"
    )

    cmd_obj = cli.commands["logs"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["my-pod", "--follow", "--show-vibe"])

    assert exc_info.value.code == 0
    mock_handle_watch_with_live_display.assert_called_once()

    # Verify configure_output_flags was called correctly by run_logs_command
    mock_configure_output_flags.assert_called_once_with(
        show_raw_output=None,
        show_vibe=True,
        model=None,
        show_kubectl=None,
        show_metrics=None,  # Expect None when flag not explicitly passed
    )

    # Verify that the OutputFlags instance passed to handle_watch_with_live_display
    # is the one returned by our mock_configure_output_flags
    call_kwargs = mock_handle_watch_with_live_display.call_args.kwargs
    assert call_kwargs["output_flags"] == expected_flags


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
    mock_run_kubectl.assert_called_once_with(
        ["logs", "my-pod", "-n", "test-ns"], capture=True
    )
    mock_handle_command_output.assert_called_once()
