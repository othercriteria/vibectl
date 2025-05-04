"""Tests for the logs subcommand CLI interface.

These tests were moved from test_cli.py for clarity and maintainability.
"""

from unittest.mock import Mock, patch

from click.testing import CliRunner

from vibectl.cli import cli


@patch("vibectl.subcommands.logs_cmd.run_kubectl")
@patch("vibectl.subcommands.logs_cmd.handle_command_output")
def test_logs_basic(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test basic logs command functionality."""
    from vibectl.types import Success

    mock_run_kubectl.return_value = Success(data="test output")

    result = cli_runner.invoke(cli, ["logs", "pod", "my-pod"])

    assert result.exit_code == 0
    mock_run_kubectl.assert_called_once_with(["logs", "pod", "my-pod"], capture=True)
    mock_handle_output.assert_called_once()


@patch("vibectl.subcommands.logs_cmd.run_kubectl")
@patch("vibectl.subcommands.logs_cmd.handle_command_output")
def test_logs_with_args(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test logs command with additional arguments."""
    from vibectl.types import Success

    mock_run_kubectl.return_value = Success(data="test output")

    # Use -- to separate options from arguments
    result = cli_runner.invoke(cli, ["logs", "pod", "my-pod", "--", "-n", "default"])

    assert result.exit_code == 0
    mock_run_kubectl.assert_called_once_with(
        ["logs", "pod", "my-pod", "-n", "default"], capture=True
    )
    mock_handle_output.assert_called_once()


@patch("vibectl.subcommands.logs_cmd.configure_output_flags")
@patch("vibectl.subcommands.logs_cmd.run_kubectl")
@patch("vibectl.subcommands.logs_cmd.handle_command_output")
def test_logs_with_flags(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test logs command with output flags."""
    from vibectl.types import Success

    mock_configure_flags.model_name = "test-model-bar"
    mock_run_kubectl.return_value = Success(data="test output")

    result = cli_runner.invoke(
        cli,
        [
            "logs",
            "pod",
            "my-pod",
            "--show-raw-output",
            "--no-show-vibe",
            "--model",
            "test-model-foo",
        ],
    )

    assert result.exit_code == 0
    mock_run_kubectl.assert_called_once_with(["logs", "pod", "my-pod"], capture=True)
    mock_handle_output.assert_called_once()

    # Verify the configured model name is not modified
    assert mock_configure_flags.model_name == "test-model-bar"


@patch("vibectl.subcommands.logs_cmd.run_kubectl")
@patch("vibectl.subcommands.logs_cmd.handle_command_output")
def test_logs_no_output(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test logs command when kubectl returns no output."""
    from vibectl.types import Success

    mock_run_kubectl.return_value = Success(data="")

    result = cli_runner.invoke(cli, ["logs", "pod", "my-pod"])

    assert result.exit_code == 0
    mock_run_kubectl.assert_called_once_with(["logs", "pod", "my-pod"], capture=True)
    mock_handle_output.assert_not_called()


@patch("vibectl.subcommands.logs_cmd.run_kubectl")
@patch("vibectl.subcommands.logs_cmd.handle_command_output")
def test_logs_truncation_warning(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test logs command with output that might need truncation."""
    from vibectl.types import Success

    # Create a large output that exceeds MAX_TOKEN_LIMIT * LOGS_TRUNCATION_RATIO
    large_output = "x" * (10000 * 3 + 1)  # Just over the limit
    mock_run_kubectl.return_value = Success(data=large_output)

    result = cli_runner.invoke(cli, ["logs", "pod", "my-pod"])

    assert result.exit_code == 0
    mock_run_kubectl.assert_called_once_with(["logs", "pod", "my-pod"], capture=True)
    mock_handle_output.assert_called_once()


@patch("vibectl.subcommands.logs_cmd.handle_vibe_request")
def test_logs_vibe_request(mock_handle_vibe: Mock, cli_runner: CliRunner) -> None:
    """Test logs command with vibe request."""
    result = cli_runner.invoke(cli, ["logs", "vibe", "show", "me", "pod", "logs"])
    assert result.exit_code == 0
    mock_handle_vibe.assert_called_once()
    args, kwargs = mock_handle_vibe.call_args
    assert kwargs["request"] == "show me pod logs"
    assert kwargs["command"] == "logs"


def test_logs_vibe_no_request(cli_runner: CliRunner) -> None:
    """Test logs vibe command without a request."""
    result = cli_runner.invoke(cli, ["logs", "vibe"])
    assert "Missing request after 'vibe'" in result.output


@patch("vibectl.subcommands.logs_cmd.configure_output_flags")
@patch("vibectl.subcommands.logs_cmd.run_kubectl")
def test_logs_error_handling(
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
    )

    # Setup mock to return an Error
    mock_run_kubectl.return_value = Error(error="Test error")

    # Invoke the command
    result = cli_runner.invoke(cli, ["logs", "pod", "my-pod"])

    # Verify error handling
    assert result.exit_code == 1
    assert "Error running kubectl: Test error" in result.output
