"""Tests for the events subcommand of vibectl."""

from unittest.mock import Mock, patch

from click.testing import CliRunner

from vibectl.cli import cli


@patch("vibectl.subcommands.events_cmd.configure_output_flags")
@patch("vibectl.subcommands.events_cmd.run_kubectl")
@patch("vibectl.subcommands.events_cmd.handle_command_output")
def test_events_error_handling(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test error handling in events command."""
    mock_configure_flags.return_value = (True, True, False, "test-model")
    mock_run_kubectl.side_effect = Exception("Test error")

    result = cli_runner.invoke(cli, ["events"])

    assert result.exit_code == 1
    mock_run_kubectl.assert_called_once_with(["events"], capture=True)
    mock_handle_output.assert_not_called()


@patch("vibectl.subcommands.events_cmd.configure_output_flags")
@patch("vibectl.subcommands.events_cmd.run_kubectl")
@patch("vibectl.subcommands.events_cmd.handle_command_output")
def test_events_output_processing(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test events command output processing."""
    mock_configure_flags.return_value = (True, True, False, "test-model")
    mock_run_kubectl.return_value = "Event data"

    result = cli_runner.invoke(cli, ["events"])

    assert result.exit_code == 0
    mock_run_kubectl.assert_called_once_with(["events"], capture=True)
    mock_handle_output.assert_called_once()


@patch("vibectl.subcommands.events_cmd.handle_vibe_request")
def test_events_vibe_request(mock_handle_vibe: Mock, cli_runner: CliRunner) -> None:
    """Test events command with vibe request."""
    result = cli_runner.invoke(
        cli, ["events", "vibe", "show", "me", "recent", "events"]
    )

    # Should succeed and call handle_vibe_request
    assert result.exit_code == 0
    mock_handle_vibe.assert_called_once()
    args, kwargs = mock_handle_vibe.call_args
    assert kwargs["request"] == "show me recent events"
    assert kwargs["command"] == "events"


def test_events_vibe_no_request(cli_runner: CliRunner, mock_console: Mock) -> None:
    """Test events vibe command without a request."""
    result = cli_runner.invoke(cli, ["events", "vibe"])
    # Check error message in output
    assert "Missing request after 'vibe'" in result.output
