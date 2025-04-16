"""Tests for the CLI create command.

This module tests the create command functionality of vibectl with focus on
error handling.
"""

from unittest.mock import Mock, patch

from click.testing import CliRunner

from vibectl.cli import cli

# The cli_runner fixture is now provided by conftest.py


@patch("vibectl.subcommands.create_cmd.configure_output_flags")
@patch("vibectl.subcommands.create_cmd.run_kubectl")
@patch("vibectl.subcommands.create_cmd.handle_command_output")
def test_create_basic(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test basic create command functionality."""
    mock_configure_flags.return_value = (False, True, False, "model-xyz-1.2.3")
    mock_run_kubectl.return_value = "test output"

    result = cli_runner.invoke(cli, ["create", "pod", "my-pod"])

    assert result.exit_code == 0
    mock_run_kubectl.assert_called_once_with(["create", "pod", "my-pod"], capture=True)
    mock_handle_output.assert_called_once()


@patch("vibectl.subcommands.create_cmd.configure_output_flags")
@patch("vibectl.subcommands.create_cmd.run_kubectl")
@patch("vibectl.subcommands.create_cmd.handle_command_output")
def test_create_with_args(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test create command with additional arguments."""
    mock_configure_flags.return_value = (False, True, False, "model-xyz-1.2.3")
    mock_run_kubectl.return_value = "test output"

    result = cli_runner.invoke(cli, ["create", "pod", "my-pod", "--", "-n", "default"])

    assert result.exit_code == 0
    mock_run_kubectl.assert_called_once_with(
        ["create", "pod", "my-pod", "-n", "default"], capture=True
    )
    mock_handle_output.assert_called_once()


@patch("vibectl.subcommands.create_cmd.configure_output_flags")
@patch("vibectl.subcommands.create_cmd.run_kubectl")
@patch("vibectl.subcommands.create_cmd.handle_command_output")
def test_create_with_flags(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test create command with output flags."""
    mock_configure_flags.return_value = (True, False, False, "test-model")
    mock_run_kubectl.return_value = "test output"

    result = cli_runner.invoke(
        cli,
        [
            "create",
            "pod",
            "my-pod",
            "--show-raw-output",
            "--no-show-vibe",
            "--model",
            "test-model",
        ],
    )

    assert result.exit_code == 0
    mock_run_kubectl.assert_called_once_with(["create", "pod", "my-pod"], capture=True)
    mock_handle_output.assert_called_once()


@patch("vibectl.subcommands.create_cmd.configure_output_flags")
@patch("vibectl.subcommands.create_cmd.run_kubectl")
@patch("vibectl.subcommands.create_cmd.handle_command_output")
def test_create_no_output(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test create command when kubectl returns no output."""
    mock_configure_flags.return_value = (False, True, False, "model-xyz-1.2.3")
    mock_run_kubectl.return_value = ""

    result = cli_runner.invoke(cli, ["create", "pod", "my-pod"])

    assert result.exit_code == 0
    mock_run_kubectl.assert_called_once_with(["create", "pod", "my-pod"], capture=True)
    mock_handle_output.assert_not_called()


@patch("vibectl.subcommands.create_cmd.handle_vibe_request")
def test_create_vibe_request(mock_handle_vibe: Mock, cli_runner: CliRunner) -> None:
    """Test create command with vibe request."""
    result = cli_runner.invoke(cli, ["create", "vibe", "create", "a", "new", "pod"])

    assert result.exit_code == 0
    mock_handle_vibe.assert_called_once()
    args, kwargs = mock_handle_vibe.call_args
    assert kwargs["request"] == "create a new pod"
    assert kwargs["command"] == "create"


def test_create_vibe_no_request(cli_runner: CliRunner) -> None:
    """Test create vibe command without a request."""
    result = cli_runner.invoke(cli, ["create", "vibe"])
    assert "Missing request after 'vibe'" in result.output


@patch("vibectl.subcommands.create_cmd.configure_output_flags")
@patch("vibectl.subcommands.create_cmd.run_kubectl")
def test_create_error_handling(
    mock_run_kubectl: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test create command error handling."""
    mock_configure_flags.return_value = (False, True, False, "model-xyz-1.2.3")
    mock_run_kubectl.side_effect = Exception("Test error")

    result = cli_runner.invoke(cli, ["create", "pod", "my-pod"])

    assert result.exit_code == 1  # Should exit with error code
