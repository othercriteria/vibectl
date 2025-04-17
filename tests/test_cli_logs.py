"""Tests for the logs subcommand CLI interface.

These tests were moved from test_cli.py for clarity and maintainability.
"""

from unittest.mock import Mock, patch

from click.testing import CliRunner

from vibectl.cli import cli

# --- Logs tests begin here ---


@patch("vibectl.subcommands.logs_cmd.configure_output_flags")
@patch("vibectl.subcommands.logs_cmd.run_kubectl")
@patch("vibectl.subcommands.logs_cmd.handle_command_output")
def test_logs_basic(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test basic logs command functionality."""
    mock_configure_flags.return_value = (False, True, False, "model-xyz-1.2.3")
    mock_run_kubectl.return_value = "test output"

    result = cli_runner.invoke(cli, ["logs", "pod", "my-pod"])

    assert result.exit_code == 0
    mock_run_kubectl.assert_called_once_with(["logs", "pod", "my-pod"], capture=True)
    mock_handle_output.assert_called_once()


@patch("vibectl.subcommands.logs_cmd.configure_output_flags")
@patch("vibectl.subcommands.logs_cmd.run_kubectl")
@patch("vibectl.subcommands.logs_cmd.handle_command_output")
def test_logs_with_args(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test logs command with additional arguments."""
    mock_configure_flags.return_value = (False, True, False, "model-xyz-1.2.3")
    mock_run_kubectl.return_value = "test output"

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
    mock_configure_flags.return_value = (True, False, False, "test-model")
    mock_run_kubectl.return_value = "test output"

    result = cli_runner.invoke(
        cli,
        [
            "logs",
            "pod",
            "my-pod",
            "--show-raw-output",
            "--no-show-vibe",
            "--model",
            "test-model",
        ],
    )

    assert result.exit_code == 0
    mock_run_kubectl.assert_called_once_with(["logs", "pod", "my-pod"], capture=True)
    mock_handle_output.assert_called_once()


@patch("vibectl.subcommands.logs_cmd.configure_output_flags")
@patch("vibectl.subcommands.logs_cmd.run_kubectl")
@patch("vibectl.subcommands.logs_cmd.handle_command_output")
def test_logs_no_output(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test logs command when kubectl returns no output."""
    mock_configure_flags.return_value = (False, True, False, "model-xyz-1.2.3")
    mock_run_kubectl.return_value = ""

    result = cli_runner.invoke(cli, ["logs", "pod", "my-pod"])

    assert result.exit_code == 0
    mock_run_kubectl.assert_called_once_with(["logs", "pod", "my-pod"], capture=True)
    mock_handle_output.assert_not_called()


@patch("vibectl.subcommands.logs_cmd.configure_output_flags")
@patch("vibectl.subcommands.logs_cmd.run_kubectl")
@patch("vibectl.subcommands.logs_cmd.handle_command_output")
def test_logs_truncation_warning(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test logs command with output that might need truncation."""
    mock_configure_flags.return_value = (False, True, False, "model-xyz-1.2.3")
    # Create a large output that exceeds MAX_TOKEN_LIMIT * LOGS_TRUNCATION_RATIO
    mock_run_kubectl.return_value = "x" * (10000 * 3 + 1)  # Just over the limit

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
@patch("vibectl.subcommands.logs_cmd.handle_command_output")
def test_logs_error_handling(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test logs command error handling."""
    from vibectl.command_handler import OutputFlags

    mock_configure_flags.return_value = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="model-xyz-1.2.3",
    )
    mock_run_kubectl.side_effect = Exception("Test error")

    result = cli_runner.invoke(cli, ["logs", "pod", "my-pod"])
    assert result.exit_code == 1
    assert "Error: Test error" in result.output


# --- Logs tests end here ---
