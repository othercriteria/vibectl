"""Tests for the CLI scale command.

This module tests the functionality of the scale command group and its subcommands.
"""

from unittest.mock import patch

from click.testing import CliRunner

from vibectl.cli import cli, scale
from vibectl.prompt import PLAN_SCALE_PROMPT


def test_scale_vibe_request(cli_runner: CliRunner) -> None:
    """Test that the scale command handles vibe requests properly."""
    with patch("vibectl.subcommands.scale_cmd.handle_vibe_request") as mock_handle_vibe:
        result = cli_runner.invoke(
            scale, ["vibe", "scale the frontend deployment to 5 replicas"]
        )

        assert result.exit_code == 0
        mock_handle_vibe.assert_called_once()
        _, kwargs = mock_handle_vibe.call_args
        assert kwargs["request"] == "scale the frontend deployment to 5 replicas"
        assert kwargs["command"] == "scale"
        assert kwargs["plan_prompt"] == PLAN_SCALE_PROMPT


def test_scale_vibe_no_request(cli_runner: CliRunner) -> None:
    """Test that the scale command properly handles missing vibe request."""
    with patch("vibectl.subcommands.scale_cmd.console_manager") as mock_console:
        result = cli_runner.invoke(scale, ["vibe"])

        assert result.exit_code == 1
        mock_console.print_error.assert_called_once_with("Missing request after 'vibe'")


def test_scale_no_subcommand(cli_runner: CliRunner) -> None:
    """Test that an error is displayed when no subcommand is provided for scale."""
    with patch("vibectl.cli.console_manager") as mock_console:
        result = cli_runner.invoke(scale, [])

        # For the scale command, it uses Click's default behavior of showing help text
        # with exit code 2 when no required arguments are provided
        assert result.exit_code == 2
        # Click's default behavior doesn't call console_manager
        mock_console.print_error.assert_not_called()


def test_scale_deployment_success(cli_runner: CliRunner) -> None:
    """Test normal execution of the scale deployment command."""
    with (
        patch("vibectl.subcommands.scale_cmd.run_kubectl") as mock_run_kubectl,
        patch(
            "vibectl.subcommands.scale_cmd.handle_command_output"
        ) as mock_handle_output,
        patch("vibectl.subcommands.scale_cmd.configure_output_flags") as mock_configure,
        patch("sys.exit"),  # Prevent test from exiting
    ):
        # Configure mocks
        mock_run_kubectl.return_value = "deployment.apps/nginx scaled"
        mock_configure.return_value = (False, True, False, "test-model")

        # Execute the command
        _ = cli_runner.invoke(scale, ["deployment", "nginx", "--replicas=5"])

        # Verify the kubectl command was correct
        mock_run_kubectl.assert_called_once_with(
            ["scale", "deployment", "nginx", "--replicas=5"], capture=True
        )
        mock_handle_output.assert_called_once()


def test_scale_integration_flow(cli_runner: CliRunner) -> None:
    """Test the integration between scale parent command and kubectl command."""
    with (
        patch("vibectl.subcommands.scale_cmd.run_kubectl") as mock_run_kubectl,
        patch(
            "vibectl.subcommands.scale_cmd.handle_command_output"
        ) as mock_handle_output,
        patch("vibectl.subcommands.scale_cmd.configure_output_flags") as mock_configure,
        patch("sys.exit"),  # Prevent test from exiting
    ):
        # Configure mocks
        mock_run_kubectl.return_value = "deployment.apps/nginx scaled"
        mock_configure.return_value = (False, True, False, "test-model")

        # Execute the command through the CLI
        _ = cli_runner.invoke(cli, ["scale", "deployment", "nginx", "--replicas=5"])

        # Verify the kubectl command was correct
        mock_run_kubectl.assert_called_once_with(
            ["scale", "deployment", "nginx", "--replicas=5"], capture=True
        )
        mock_handle_output.assert_called_once()


def test_scale_normal_execution(cli_runner: CliRunner) -> None:
    """Test normal execution of the scale command with mocks for internal functions."""
    with (
        patch("vibectl.subcommands.scale_cmd.run_kubectl") as mock_run_kubectl,
        patch(
            "vibectl.subcommands.scale_cmd.handle_command_output"
        ) as mock_handle_output,
        patch("vibectl.subcommands.scale_cmd.configure_output_flags") as mock_configure,
        patch("sys.exit"),  # Prevent test from exiting
    ):
        # Setup return values
        mock_run_kubectl.return_value = "deployment.apps/nginx scaled"
        mock_configure.return_value = (False, True, False, "test-model")

        # Execute the command
        _ = cli_runner.invoke(scale, ["deployment/nginx", "--replicas=3"])

        # With sys.exit mocked, we can't rely on exit code checks
        # Just verify the functions were called correctly
        mock_run_kubectl.assert_called_once_with(
            ["scale", "deployment/nginx", "--replicas=3"], capture=True
        )
        mock_handle_output.assert_called_once()


def test_scale_no_output(cli_runner: CliRunner) -> None:
    """Test scale command when there's no output from kubectl."""
    with (
        patch("vibectl.subcommands.scale_cmd.run_kubectl") as mock_run_kubectl,
        patch(
            "vibectl.subcommands.scale_cmd.handle_command_output"
        ) as mock_handle_output,
        patch("vibectl.subcommands.scale_cmd.configure_output_flags") as mock_configure,
        patch("sys.exit"),  # Prevent test from exiting
    ):
        # Setup return values
        mock_run_kubectl.return_value = ""
        mock_configure.return_value = (False, True, False, "test-model")

        # Execute
        _ = cli_runner.invoke(scale, ["deployment/nginx", "--replicas=3"])

        # With sys.exit mocked, we can't rely on exit code checks
        # Just verify the functions were called correctly
        mock_run_kubectl.assert_called_once_with(
            ["scale", "deployment/nginx", "--replicas=3"], capture=True
        )
        # No output should not trigger handle_command_output
        mock_handle_output.assert_not_called()


def test_scale_error_handling(cli_runner: CliRunner) -> None:
    """Test error handling in scale command."""
    with (
        patch("vibectl.subcommands.scale_cmd.run_kubectl") as mock_run_kubectl,
        patch("vibectl.subcommands.scale_cmd.configure_output_flags") as mock_configure,
        patch("sys.exit"),  # Prevent test from exiting
    ):
        # Setup an exception
        mock_run_kubectl.side_effect = Exception("Test error")
        mock_configure.return_value = (False, True, False, "test-model")

        # Execute
        result = cli_runner.invoke(scale, ["deployment/nginx", "--replicas=3"])

        # Assert error output or exit code
        assert result.exit_code == 0
        assert "Test error" in result.output


def test_scale_with_kubectl_flags(cli_runner: CliRunner) -> None:
    """Test scale command with additional kubectl flags."""
    with (
        patch("vibectl.subcommands.scale_cmd.run_kubectl") as mock_run_kubectl,
        patch(
            "vibectl.subcommands.scale_cmd.handle_command_output"
        ) as mock_handle_output,
        patch("vibectl.subcommands.scale_cmd.configure_output_flags") as mock_configure,
        patch("sys.exit"),  # Prevent test from exiting
    ):
        # Setup return values
        mock_run_kubectl.return_value = "deployment.apps/nginx scaled"
        mock_configure.return_value = (False, True, False, "test-model")

        # Execute the command with namespace and other flags
        _ = cli_runner.invoke(
            scale, ["deployment/nginx", "--replicas=3", "-n", "default", "--record"]
        )

        # Verify kubectl received all arguments
        mock_run_kubectl.assert_called_once_with(
            ["scale", "deployment/nginx", "--replicas=3", "-n", "default", "--record"],
            capture=True,
        )
        mock_handle_output.assert_called_once()
