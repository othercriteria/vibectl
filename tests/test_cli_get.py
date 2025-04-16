"""Tests for the 'get' subcommand of the CLI.

Fixtures used are provided by conftest.py and fixtures.py.
"""

from unittest.mock import Mock, patch

from click.testing import CliRunner

from vibectl.cli import cli


def test_get_basic(
    cli_runner: CliRunner,
    mock_run_kubectl: Mock,
    mock_handle_command_output: Mock,
) -> None:
    """Test basic get command functionality."""
    with (
        patch("vibectl.command_handler.run_kubectl") as cmd_mock_run_kubectl,
        patch("vibectl.command_handler.handle_command_output") as cmd_mock_handle_output,
    ):
        cmd_mock_run_kubectl.return_value = "test output"
        result = cli_runner.invoke(cli, ["get", "pods"])
        assert result.exit_code == 0
        cmd_mock_run_kubectl.assert_called_once_with(["get", "pods"], capture=True)
        cmd_mock_handle_output.assert_called_once()


def test_get_with_args(
    cli_runner: CliRunner,
    mock_run_kubectl: Mock,
    mock_handle_command_output: Mock,
) -> None:
    """Test get command with additional arguments."""
    with (
        patch("vibectl.command_handler.run_kubectl") as cmd_mock_run_kubectl,
        patch("vibectl.command_handler.handle_command_output") as cmd_mock_handle_output,
    ):
        cmd_mock_run_kubectl.return_value = "test output"
        result = cli_runner.invoke(cli, ["get", "pods", "-n", "default"])
        assert result.exit_code == 0
        cmd_mock_run_kubectl.assert_called_once_with(["get", "pods", "-n", "default"], capture=True)
        cmd_mock_handle_output.assert_called_once()


def test_get_no_output(
    cli_runner: CliRunner,
    mock_run_kubectl: Mock,
    mock_handle_command_output: Mock,
) -> None:
    """Test get command when kubectl returns no output."""
    with (
        patch("vibectl.command_handler.run_kubectl") as cmd_mock_run_kubectl,
        patch("vibectl.command_handler.handle_command_output"),
    ):
        cmd_mock_run_kubectl.return_value = ""
        result = cli_runner.invoke(cli, ["get", "pods"])
        assert result.exit_code == 0
        cmd_mock_run_kubectl.assert_called_once_with(["get", "pods"], capture=True)


def test_get_with_flags(
    cli_runner: CliRunner,
    mock_run_kubectl: Mock,
    mock_handle_command_output: Mock,
) -> None:
    """Test get command with output flags."""
    with (
        patch("vibectl.command_handler.run_kubectl") as cmd_mock_run_kubectl,
        patch("vibectl.command_handler.handle_command_output"),
    ):
        cmd_mock_run_kubectl.return_value = "test output"
        result = cli_runner.invoke(
            cli,
            [
                "get",
                "pods",
                "--show-raw-output",
                "--no-show-vibe",
                "--model",
                "test-model",
            ],
        )
        assert result.exit_code == 0
        cmd_mock_run_kubectl.assert_called_once_with(["get", "pods"], capture=True)


def test_get_with_show_kubectl_flag(
    cli_runner: CliRunner,
    mock_run_kubectl: Mock,
    mock_handle_command_output: Mock,
) -> None:
    """Test get command with --show-kubectl flag."""
    with patch("vibectl.command_handler.run_kubectl") as cmd_mock_run_kubectl:
        cmd_mock_run_kubectl.return_value = "test output"
        result = cli_runner.invoke(cli, ["get", "pods", "--show-kubectl"])
        assert result.exit_code == 0
        cmd_mock_run_kubectl.assert_called_once_with(["get", "pods"], capture=True)

# Add any additional get subcommand tests here as needed
