"""Tests for the 'get' subcommand logic in vibectl/subcommands/get_cmd.py.

Fixtures used are provided by conftest.py and ../fixtures.py.
"""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from vibectl.cli import cli
from vibectl.command_handler import OutputFlags
from vibectl.types import Error, Success

# Assuming common fixtures like cli_runner, mock_run_kubectl, etc. are available
# from conftest.py or fixtures.py


@patch("vibectl.subcommands.get_cmd.handle_standard_command")
@pytest.mark.asyncio
async def test_get_basic(
    mock_handle_standard: MagicMock,
) -> None:
    """Test basic get command functionality."""
    mock_handle_standard.return_value = Success(data="test output")
    cmd_obj = cli.commands["get"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["pods"])
    assert exc_info.value.code == 0
    mock_handle_standard.assert_called_once()
    # Verify args passed to handle_standard_command
    args, kwargs = mock_handle_standard.call_args
    assert kwargs["command"] == "get"
    assert kwargs["resource"] == "pods"
    assert kwargs["args"] == ()


@patch("vibectl.subcommands.get_cmd.handle_standard_command")
@pytest.mark.asyncio
async def test_get_with_args(
    mock_handle_standard: MagicMock,
) -> None:
    """Test get command with additional arguments."""
    mock_handle_standard.return_value = Success(data="test output")
    cmd_obj = cli.commands["get"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["pods", "-n", "default"])
    assert exc_info.value.code == 0
    mock_handle_standard.assert_called_once()
    args, kwargs = mock_handle_standard.call_args
    assert kwargs["command"] == "get"
    assert kwargs["resource"] == "pods"
    assert kwargs["args"] == ("-n", "default")


@patch("vibectl.subcommands.get_cmd.handle_standard_command")
@pytest.mark.asyncio
async def test_get_no_output(
    mock_handle_standard: MagicMock,
) -> None:
    """Test get command when kubectl returns no output."""
    # Handler should still be called, but might return Success with empty data
    mock_handle_standard.return_value = Success(data="")
    cmd_obj = cli.commands["get"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["pods"])
    assert exc_info.value.code == 0
    mock_handle_standard.assert_called_once()


@patch("vibectl.subcommands.get_cmd.handle_standard_command")
@patch("vibectl.subcommands.get_cmd.configure_output_flags")
@pytest.mark.asyncio
async def test_get_with_flags(
    mock_configure_flags: Mock,
    mock_handle_standard: MagicMock,
) -> None:
    """Test get command with output flags."""
    mock_flags = OutputFlags(
        show_raw=True,
        show_vibe=False,
        model_name="test-model",
        warn_no_output=True,
        show_metrics=True,
    )
    mock_configure_flags.return_value = mock_flags
    mock_handle_standard.return_value = Success(data="test output")
    cmd_obj = cli.commands["get"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(
            [
                "pods",
                "--show-raw-output",
                "--no-show-vibe",
                "--model",
                "test-model",
            ]
        )
    assert exc_info.value.code == 0
    mock_handle_standard.assert_called_once()
    # Check that flags were passed correctly
    args, kwargs = mock_handle_standard.call_args
    assert kwargs["output_flags"] == mock_flags


@patch("vibectl.subcommands.get_cmd.handle_standard_command")
@patch("vibectl.subcommands.get_cmd.configure_output_flags")
@pytest.mark.asyncio
async def test_get_with_show_kubectl_flag(
    mock_configure_flags: Mock,
    mock_handle_standard: MagicMock,
) -> None:
    """Test get command with --show-kubectl flag."""
    mock_flags = OutputFlags(
        show_kubectl=True,
        show_raw=False,
        show_vibe=False,
        warn_no_output=True,
        model_name="default",
        show_metrics=True,
    )
    mock_configure_flags.return_value = mock_flags
    mock_handle_standard.return_value = Success(data="test output")
    cmd_obj = cli.commands["get"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["pods", "--show-kubectl"])
    assert exc_info.value.code == 0
    mock_handle_standard.assert_called_once()
    args, kwargs = mock_handle_standard.call_args
    assert kwargs["output_flags"] == mock_flags


# Tests for get vibe path
@patch("vibectl.subcommands.get_cmd.handle_vibe_request", new_callable=AsyncMock)
@patch("vibectl.subcommands.get_cmd.configure_output_flags")
@pytest.mark.asyncio
async def test_get_vibe_basic(
    mock_configure_flags: Mock,
    mock_handle_vibe: AsyncMock,
) -> None:
    """Test basic get vibe command."""
    mock_flags = OutputFlags(
        show_vibe=True,
        model_name="default",
        show_raw=False,
        warn_no_output=True,
        show_metrics=True,
    )
    mock_configure_flags.return_value = mock_flags
    mock_handle_vibe.return_value = Success()
    cmd_obj = cli.commands["get"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["vibe", "pods"])
    assert exc_info.value.code == 0
    mock_handle_vibe.assert_called_once()
    args, kwargs = mock_handle_vibe.call_args
    assert kwargs["request"] == "pods"
    assert kwargs["output_flags"] == mock_flags


@patch("vibectl.subcommands.get_cmd.handle_vibe_request", new_callable=AsyncMock)
@patch("vibectl.subcommands.get_cmd.configure_output_flags")
@pytest.mark.asyncio
async def test_get_vibe_with_output_flags(
    mock_configure_flags: Mock,
    mock_handle_vibe: AsyncMock,
) -> None:
    """Test get vibe command with output flags."""
    mock_flags = OutputFlags(
        show_raw=True,
        show_vibe=False,
        warn_no_output=True,
        model_name="default",
        show_metrics=True,
    )
    mock_configure_flags.return_value = mock_flags
    mock_handle_vibe.return_value = Success()
    cmd_obj = cli.commands["get"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["vibe", "pods", "--raw", "--no-vibe"])
    assert exc_info.value.code == 0
    mock_handle_vibe.assert_called_once()
    args, kwargs = mock_handle_vibe.call_args
    # Note: Cli flags like --raw are part of the 'request' string for vibe commands
    assert kwargs["request"] == "pods --raw --no-vibe"
    assert kwargs["output_flags"] == mock_flags


# Test get vibe missing request
@patch("vibectl.subcommands.get_cmd.configure_output_flags")
@pytest.mark.asyncio
async def test_cli_get_vibe_no_request(
    mock_configure_flags: Mock,
) -> None:
    """Test 'get vibe' without a request string produces an error."""
    cmd_obj = cli.commands["get"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["vibe"])
    assert exc_info.value.code != 0


# Test error handling for standard get
@patch("vibectl.subcommands.get_cmd.handle_standard_command")
@pytest.mark.asyncio
async def test_cli_get_error_handling(
    mock_handle_standard: MagicMock,
) -> None:
    """Test that errors from kubectl during 'get' are handled."""
    mock_handle_standard.return_value = Error(error="kubectl failed")
    cmd_obj = cli.commands["get"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["pods"])
    assert exc_info.value.code != 0
    mock_handle_standard.assert_called_once()


# --- Tests for --watch flag --- #
@patch(
    "vibectl.subcommands.get_cmd.handle_watch_with_live_display", new_callable=AsyncMock
)
@patch("vibectl.subcommands.get_cmd.configure_output_flags")
@pytest.mark.asyncio
async def test_get_watch_success(
    mock_configure_output: Mock,
    mock_handle_watch: AsyncMock,
) -> None:
    """Test 'get --watch' calls handle_watch_with_live_display and returns Success."""
    mock_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=True,
        model_name="default",
        show_metrics=True,
    )
    mock_configure_output.return_value = mock_flags
    mock_handle_watch.return_value = Success(message="Watch completed")

    cmd_obj = cli.commands["get"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["pods", "--watch"])

    assert exc_info.value.code == 0
    mock_handle_watch.assert_called_once()
    args, kwargs = mock_handle_watch.call_args
    assert kwargs["command"] == "get"
    assert kwargs["resource"] == "pods"
    assert "--watch" in kwargs["args"]
    assert kwargs["output_flags"] == mock_flags


@patch(
    "vibectl.subcommands.get_cmd.handle_watch_with_live_display", new_callable=AsyncMock
)
@patch("vibectl.subcommands.get_cmd.configure_output_flags")
@pytest.mark.asyncio
async def test_get_watch_error(
    mock_configure_output: Mock,
    mock_handle_watch: AsyncMock,
) -> None:
    """Test that 'get --watch' handles errors from handler."""
    mock_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=True,
        model_name="default",
        show_metrics=True,
    )
    mock_configure_output.return_value = mock_flags
    mock_handle_watch.return_value = Error(error="Watch failed")

    cmd_obj = cli.commands["get"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["pods", "-w"])

    assert exc_info.value.code != 0
    mock_handle_watch.assert_called_once()


# --- Tests for Error propagation --- #
@patch("vibectl.subcommands.get_cmd.handle_standard_command")
@patch("vibectl.subcommands.get_cmd.configure_output_flags")
@pytest.mark.asyncio
async def test_get_standard_command_error_propagation(
    mock_configure_output: Mock,
    mock_handle_standard: MagicMock,
) -> None:
    """Test errors from handle_standard_command are propagated."""
    mock_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=True,
        model_name="default",
        show_metrics=True,
    )
    mock_configure_output.return_value = mock_flags
    mock_handle_standard.return_value = Error(error="Standard failed")

    cmd_obj = cli.commands["get"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["pods"])

    assert exc_info.value.code != 0
    mock_handle_standard.assert_called_once()


@patch("vibectl.subcommands.get_cmd.handle_vibe_request", new_callable=AsyncMock)
@patch("vibectl.subcommands.get_cmd.configure_output_flags")
@pytest.mark.asyncio
async def test_get_vibe_request_error_propagation(
    mock_configure_output: Mock,
    mock_handle_vibe: AsyncMock,
) -> None:
    """Test errors from handle_vibe_request are propagated."""
    mock_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=True,
        model_name="default",
        show_metrics=True,
    )
    mock_configure_output.return_value = mock_flags
    mock_handle_vibe.return_value = Error(error="Vibe failed")

    cmd_obj = cli.commands["get"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["vibe", "request"])

    assert exc_info.value.code != 0
    mock_handle_vibe.assert_called_once()


# --- Test for top-level exception handling --- #
@patch("vibectl.subcommands.get_cmd.configure_output_flags")
@patch("vibectl.subcommands.get_cmd.logger")
@pytest.mark.asyncio
async def test_get_top_level_exception(
    mock_logger: Mock,
    mock_configure_output: Mock,
) -> None:
    """Test the top-level exception handler in run_get_command."""
    test_exception = ValueError("Config error")
    mock_configure_output.side_effect = test_exception

    cmd_obj = cli.commands["get"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["pods"])

    assert exc_info.value.code != 0
    mock_logger.error.assert_called_once()
    args, kwargs = mock_logger.error.call_args
    assert "Error in 'get' subcommand:" in args[0]
    assert args[1] == test_exception


# --- Tests for specific success/edge cases --- #
@patch("vibectl.subcommands.get_cmd.handle_standard_command")
@patch("vibectl.subcommands.get_cmd.configure_output_flags")
@pytest.mark.asyncio
async def test_get_standard_command_success_no_data(
    mock_configure_output: Mock,
    mock_handle_standard: MagicMock,
) -> None:
    """Test success path when handler returns Success with no data."""
    mock_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=True,
        model_name="default",
        show_metrics=True,
    )
    mock_configure_output.return_value = mock_flags
    mock_handle_standard.return_value = Success(data=None)

    cmd_obj = cli.commands["get"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["pods"])

    assert exc_info.value.code == 0
    mock_handle_standard.assert_called_once()


@patch("vibectl.subcommands.get_cmd.handle_vibe_request", new_callable=AsyncMock)
@patch("vibectl.subcommands.get_cmd.configure_output_flags")
@pytest.mark.asyncio
async def test_get_vibe_request_success_no_data(
    mock_configure_output: Mock,
    mock_handle_vibe: AsyncMock,
) -> None:
    """Test success path when vibe handler returns Success with no data."""
    mock_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=True,
        model_name="default",
        show_metrics=True,
    )
    mock_configure_output.return_value = mock_flags
    mock_handle_vibe.return_value = Success(data=None)

    cmd_obj = cli.commands["get"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["vibe", "request"])

    assert exc_info.value.code == 0
    mock_handle_vibe.assert_called_once()


# Test get vibe missing request - renamed from test_get_vibe_missing_request_arg
@patch("vibectl.subcommands.get_cmd.configure_output_flags")
@pytest.mark.asyncio
async def test_get_vibe_missing_request(
    mock_configure_output_flags: Mock,
) -> None:
    """Test that 'get vibe' without a request string produces an error."""
    cmd_obj = cli.commands["get"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["vibe"])
    assert exc_info.value.code != 0


# Remove redundant test covered by test_get_standard_command_error_propagation
# test_run_get_command_propagates_handler_error

# Remove redundant test covered by test_cli_get_vibe_no_request
# test_run_get_command_vibe_no_args
