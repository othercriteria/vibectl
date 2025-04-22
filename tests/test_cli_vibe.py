from collections.abc import Generator
from unittest.mock import ANY, MagicMock, Mock, patch

import pytest
from click.testing import CliRunner

from vibectl.cli import cli, vibe
from vibectl.command_handler import OutputFlags
from vibectl.types import Error, Success


# Local fixtures specifically for these tests
@pytest.fixture
def mock_handle_vibe_request() -> Generator[Mock, None, None]:
    """Mock the handle_vibe_request function in vibe_cmd for CLI tests."""
    with patch("vibectl.subcommands.vibe_cmd.handle_vibe_request") as mock:
        mock.return_value = Success(message="Success")
        yield mock


@pytest.fixture
def mock_get_memory() -> Generator[Mock, None, None]:
    """Mock the get_memory function in vibe_cmd for CLI tests."""
    with patch("vibectl.subcommands.vibe_cmd.get_memory") as mock:
        mock.return_value = "Memory context"
        yield mock


def test_vibe_command_with_request(
    cli_runner: CliRunner,
    mock_handle_vibe_request: Mock,
    mock_get_memory: Mock,
    standard_output_flags: OutputFlags,
) -> None:
    """Test the main vibe command with a request and OutputFlags."""
    with patch("vibectl.command_handler.configure_output_flags") as mock_flags:
        mock_flags.return_value = standard_output_flags
        result = cli_runner.invoke(vibe, ["Create a deployment", "--show-raw-output"])
    assert result.exit_code == 0
    mock_handle_vibe_request.assert_called_once()
    args, kwargs = mock_handle_vibe_request.call_args
    assert "output_flags" in kwargs
    assert kwargs["output_flags"] == standard_output_flags
    assert kwargs["request"] == "Create a deployment"


def test_vibe_command_without_request(
    cli_runner: CliRunner,
    mock_handle_vibe_request: Mock,
    mock_get_memory: Mock,
    standard_output_flags: OutputFlags,
) -> None:
    """Test the main vibe command without a request and OutputFlags."""
    with patch("vibectl.command_handler.configure_output_flags") as mock_flags:
        mock_flags.return_value = standard_output_flags
        result = cli_runner.invoke(vibe, ["--show-raw-output"])
    assert result.exit_code == 0
    mock_handle_vibe_request.assert_called_once()
    args, kwargs = mock_handle_vibe_request.call_args
    assert "output_flags" in kwargs
    assert kwargs["output_flags"] == standard_output_flags
    assert kwargs["request"] == ""
    assert kwargs["autonomous_mode"] is True


def test_vibe_command_with_yes_flag(
    cli_runner: CliRunner,
    mock_handle_vibe_request: Mock,
    mock_get_memory: Mock,
    standard_output_flags: OutputFlags,
) -> None:
    """Test the main vibe command with the yes flag."""
    with patch("vibectl.command_handler.configure_output_flags") as mock_flags:
        mock_flags.return_value = standard_output_flags
        result = cli_runner.invoke(
            vibe, ["Create a deployment", "--yes", "--show-raw-output"]
        )
    assert result.exit_code == 0
    mock_handle_vibe_request.assert_called_once()
    args, kwargs = mock_handle_vibe_request.call_args
    assert "yes" in kwargs
    assert kwargs["yes"] is True


@patch("vibectl.subcommands.vibe_cmd.handle_vibe_request")
@patch("vibectl.subcommands.vibe_cmd.get_memory")
def test_vibe_command_with_no_arguments_plan_prompt(
    mock_get_memory: MagicMock, mock_handle_vibe: MagicMock, cli_runner: CliRunner
) -> None:
    """Test 'vibe' command with no arguments: plan prompt and processing message."""
    mock_get_memory.return_value = ""
    result = cli_runner.invoke(cli, ["vibe"])
    assert result.exit_code == 0
    mock_handle_vibe.assert_called_once()
    call_args = mock_handle_vibe.call_args[1]
    assert call_args["request"] == ""
    assert call_args["command"] == "vibe"
    assert call_args["autonomous_mode"] is True
    assert (
        "Recall the syntax requirements above and follow them strictly in responding to"
        in mock_handle_vibe.call_args_list[0][1]["plan_prompt"]
    )
    assert "Request: " in mock_handle_vibe.call_args_list[0][1]["plan_prompt"]


@patch("vibectl.subcommands.vibe_cmd.handle_vibe_request")
@patch("vibectl.subcommands.vibe_cmd.get_memory")
def test_vibe_command_with_existing_memory_plan_prompt(
    mock_get_memory: MagicMock, mock_handle_vibe: MagicMock, cli_runner: CliRunner
) -> None:
    """Test 'vibe' command with existing memory: plan prompt and processing message."""
    memory_value = "Working in namespace 'test' with deployment 'app'"
    mock_get_memory.return_value = memory_value
    result = cli_runner.invoke(cli, ["vibe"])
    assert result.exit_code == 0
    mock_handle_vibe.assert_called_once()
    call_args = mock_handle_vibe.call_args[1]
    assert call_args["request"] == ""
    assert call_args["command"] == "vibe"
    assert call_args["autonomous_mode"] is True
    assert call_args["memory_context"] == memory_value


@patch("vibectl.subcommands.vibe_cmd.handle_vibe_request")
@patch("vibectl.subcommands.vibe_cmd.get_memory")
def test_vibe_command_with_explicit_request_plan_prompt(
    mock_get_memory: MagicMock, mock_handle_vibe: MagicMock
) -> None:
    """Test 'vibe' command with an explicit request."""
    from vibectl.subcommands.vibe_cmd import run_vibe_command

    # Set up mocks
    mock_get_memory.return_value = "Working in namespace 'test'"
    mock_handle_vibe.return_value = Success(message="Command executed successfully")

    # Call the function directly instead of through the CLI
    request = "scale deployment app to 3 replicas"
    result = run_vibe_command(
        request=request,
        show_raw_output=None,
        show_vibe=None,
        show_kubectl=None,
        model=None,
    )

    # Verify results
    assert isinstance(result, Success)
    mock_handle_vibe.assert_called_once()
    call_args = mock_handle_vibe.call_args[1]
    assert call_args["request"] == "scale deployment app to 3 replicas"
    assert call_args["command"] == "vibe"
    assert call_args["autonomous_mode"] is True
    assert call_args["memory_context"] == "Working in namespace 'test'"


def test_vibe_command_handle_vibe_request_exception() -> None:
    """Test that an exception in handle_vibe_request is caught and returns Error."""
    from vibectl.subcommands.vibe_cmd import run_vibe_command

    with (
        patch(
            "vibectl.subcommands.vibe_cmd.handle_vibe_request",
            side_effect=Exception("fail!"),
        ),
        patch("vibectl.subcommands.vibe_cmd.get_memory", return_value="mem"),
        patch("vibectl.subcommands.vibe_cmd.logger") as mock_logger,
    ):
        result = run_vibe_command(
            "do something", None, None, None, None, exit_on_error=False
        )
        assert isinstance(result, Error)
        assert "Exception in handle_vibe_request" in result.error
        mock_logger.error.assert_any_call(
            "Error in handle_vibe_request: %s", ANY, exc_info=True
        )


def test_vibe_command_outer_exception() -> None:
    """Test that an exception in the outer try/except returns Error."""
    from vibectl.subcommands.vibe_cmd import run_vibe_command

    with (
        patch(
            "vibectl.subcommands.vibe_cmd.configure_output_flags",
            side_effect=Exception("outer fail"),
        ),
        patch("vibectl.subcommands.vibe_cmd.logger") as mock_logger,
    ):
        result = run_vibe_command(
            "do something", None, None, None, None, exit_on_error=False
        )
        assert isinstance(result, Error)
        assert "Exception in 'vibe' subcommand" in result.error
        mock_logger.error.assert_any_call(
            "Error in 'vibe' subcommand: %s", ANY, exc_info=True
        )


def test_vibe_command_logs_and_console_for_empty_request() -> None:
    """Test that logger is called for empty request."""
    from vibectl.subcommands.vibe_cmd import run_vibe_command

    with (
        patch(
            "vibectl.subcommands.vibe_cmd.handle_vibe_request",
            return_value=Success(),
        ),
        patch("vibectl.subcommands.vibe_cmd.get_memory", return_value="mem"),
        patch("vibectl.subcommands.vibe_cmd.logger") as mock_logger,
        patch("vibectl.subcommands.vibe_cmd.configure_output_flags"),
        patch("vibectl.subcommands.vibe_cmd.configure_memory_flags"),
    ):
        result = run_vibe_command("", None, None, None, None, exit_on_error=False)
        assert isinstance(result, Success)
        mock_logger.info.assert_any_call(
            "No request provided; using memory context for planning."
        )


def test_vibe_command_logs_and_console_for_nonempty_request() -> None:
    """Test that logger is called for non-empty request."""
    from vibectl.subcommands.vibe_cmd import run_vibe_command

    with (
        patch(
            "vibectl.subcommands.vibe_cmd.handle_vibe_request",
            return_value=Success(),
        ),
        patch("vibectl.subcommands.vibe_cmd.get_memory", return_value="mem"),
        patch("vibectl.subcommands.vibe_cmd.logger") as mock_logger,
    ):
        result = run_vibe_command("do something", None, None, None, None)
        assert isinstance(result, Success)
        mock_logger.info.assert_any_call("Planning how to: do something")


def test_vibe_command_handle_vibe_request_exception_exit_on_error_true() -> None:
    """Test that an exception in handle_vibe_request is raised if exit_on_error=True."""
    import pytest

    from vibectl.subcommands.vibe_cmd import run_vibe_command

    with (
        patch(
            "vibectl.subcommands.vibe_cmd.handle_vibe_request",
            side_effect=Exception("fail!"),
        ),
        patch("vibectl.subcommands.vibe_cmd.get_memory", return_value="mem"),
        patch("vibectl.subcommands.vibe_cmd.logger") as mock_logger,
    ):
        with pytest.raises(Exception) as excinfo:
            run_vibe_command("do something", None, None, None, None, exit_on_error=True)
        assert "fail!" in str(excinfo.value)
        mock_logger.error.assert_any_call(
            "Error in handle_vibe_request: %s", ANY, exc_info=True
        )


def test_vibe_command_outer_exception_exit_on_error_true() -> None:
    """Test that an exception in outer try/except is raised if exit_on_error=True."""
    import pytest

    from vibectl.subcommands.vibe_cmd import run_vibe_command

    with (
        patch(
            "vibectl.subcommands.vibe_cmd.configure_output_flags",
            side_effect=Exception("outer fail"),
        ),
        patch("vibectl.subcommands.vibe_cmd.logger") as mock_logger,
    ):
        with pytest.raises(Exception) as excinfo:
            run_vibe_command("do something", None, None, None, None, exit_on_error=True)
        assert "outer fail" in str(excinfo.value)
        mock_logger.error.assert_any_call(
            "Error in 'vibe' subcommand: %s", ANY, exc_info=True
        )
