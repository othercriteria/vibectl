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
        patch(
            "vibectl.command_handler.handle_command_output"
        ) as cmd_mock_handle_output,
        patch("vibectl.types.Success") as mock_success,
    ):
        # Set up mock return value to return a Success object
        success_instance = Mock()
        mock_success.return_value = success_instance
        success_instance.data = "test output"
        cmd_mock_run_kubectl.return_value = success_instance

        # Make handle_command_output return a Success object
        cmd_mock_handle_output.return_value = success_instance

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
        patch(
            "vibectl.command_handler.handle_command_output"
        ) as cmd_mock_handle_output,
        patch("vibectl.types.Success") as mock_success,
    ):
        # Set up mock return value to return a Success object
        success_instance = Mock()
        mock_success.return_value = success_instance
        success_instance.data = "test output"
        cmd_mock_run_kubectl.return_value = success_instance

        # Make handle_command_output return a Success object
        cmd_mock_handle_output.return_value = success_instance

        result = cli_runner.invoke(cli, ["get", "pods", "-n", "default"])
        assert result.exit_code == 0
        cmd_mock_run_kubectl.assert_called_once_with(
            ["get", "pods", "-n", "default"], capture=True
        )
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
        patch("vibectl.types.Success") as mock_success,
    ):
        # Set up mock return value to return a Success object
        success_instance = Mock()
        mock_success.return_value = success_instance
        success_instance.data = ""  # Empty output
        cmd_mock_run_kubectl.return_value = success_instance

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
        patch("vibectl.types.Success") as mock_success,
    ):
        # Set up mock return value to return a Success object
        success_instance = Mock()
        mock_success.return_value = success_instance
        success_instance.data = "test output"
        cmd_mock_run_kubectl.return_value = success_instance

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
    with (
        patch("vibectl.command_handler.run_kubectl") as cmd_mock_run_kubectl,
        patch("vibectl.command_handler.handle_command_output"),
        patch("vibectl.types.Success") as mock_success,
    ):
        # Set up mock return value to return a Success object
        success_instance = Mock()
        mock_success.return_value = success_instance
        success_instance.data = "test output"
        cmd_mock_run_kubectl.return_value = success_instance

        result = cli_runner.invoke(cli, ["get", "pods", "--show-kubectl"])
        assert result.exit_code == 0
        cmd_mock_run_kubectl.assert_called_once_with(["get", "pods"], capture=True)
