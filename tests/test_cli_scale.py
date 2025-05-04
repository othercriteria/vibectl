"""Tests for the CLI scale command.

This module tests the functionality of the scale command group and its subcommands.
"""

from unittest.mock import patch

from click.testing import CliRunner

from vibectl.cli import cli, scale
from vibectl.prompt import PLAN_SCALE_PROMPT
from vibectl.types import Error


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


def test_scale_vibe_no_request() -> None:
    """Test that the scale command properly handles missing vibe request
    by directly testing the run_scale_command function."""
    from vibectl.subcommands.scale_cmd import run_scale_command
    from vibectl.types import Error

    # Call the function directly with 'vibe' resource and no args
    result = run_scale_command(
        resource="vibe",
        args=(),  # empty tuple for no arguments
        show_raw_output=None,
        show_vibe=None,
        show_kubectl=None,
        model=None,
        freeze_memory=False,
        unfreeze_memory=False,
    )

    # The function should return an Error result
    assert isinstance(result, Error)
    assert "Missing request after 'vibe'" in result.error


def test_scale_no_subcommand(cli_runner: CliRunner) -> None:
    """Test that an error is displayed when no subcommand is provided for scale."""
    result = cli_runner.invoke(scale, [])

    # For the scale command, it uses Click's default behavior of showing help text
    # with exit code 2 when no required arguments are provided
    assert result.exit_code == 2
    # Click's default behavior doesn't call console_manager


def test_scale_deployment_success(cli_runner: CliRunner) -> None:
    """Test normal execution of the scale deployment command."""
    with (
        patch("vibectl.subcommands.scale_cmd.run_kubectl") as mock_run_kubectl,
        patch(
            "vibectl.subcommands.scale_cmd.handle_command_output"
        ) as mock_handle_output,
    ):
        # Configure mocks
        mock_run_kubectl.return_value = "deployment.apps/nginx scaled"

        # Execute the command
        result = cli_runner.invoke(scale, ["deployment", "nginx", "--replicas=5"])

        # Verify the kubectl command was correct
        assert result.exit_code == 0
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
    ):
        # Configure mocks
        mock_run_kubectl.return_value = "deployment.apps/nginx scaled"

        # Execute the command through the CLI
        result = cli_runner.invoke(
            cli,
            ["scale", "deployment", "nginx", "--replicas=5"],
        )

        # Verify the kubectl command was correct
        assert result.exit_code == 0
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
    ):
        # Setup return values
        mock_run_kubectl.return_value = "deployment.apps/nginx scaled"

        # Execute the command
        result = cli_runner.invoke(scale, ["deployment/nginx", "--replicas=3"])

        # Verify the functions were called correctly
        assert result.exit_code == 0
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
    ):
        # Setup return values
        mock_run_kubectl.return_value = ""

        # Execute
        result = cli_runner.invoke(scale, ["deployment/nginx", "--replicas=3"])

        # Verify the functions were called correctly
        assert result.exit_code == 0
        mock_run_kubectl.assert_called_once_with(
            ["scale", "deployment/nginx", "--replicas=3"], capture=True
        )
        # No output should not trigger handle_command_output
        mock_handle_output.assert_not_called()


def test_scale_error_handling(cli_runner: CliRunner) -> None:
    """Test error handling in scale command."""
    with (
        patch("vibectl.subcommands.scale_cmd.run_kubectl") as mock_run_kubectl,
        patch("vibectl.cli.handle_result") as mock_handle_result,
    ):
        # Setup an exception
        test_exception = Exception("Test error")
        mock_run_kubectl.side_effect = test_exception

        # Execute
        _ = cli_runner.invoke(cli, ["scale", "deployment/nginx", "--replicas=3"])

        # Assert error handling: check that handle_result was called once
        mock_handle_result.assert_called_once()

        # Assert that handle_result was called with an Error object
        args, _ = mock_handle_result.call_args
        assert len(args) == 1
        result_arg = args[0]
        assert isinstance(result_arg, Error)
        # Check the content of the Error object matches the generic message
        assert result_arg.error == "Exception running kubectl"
        assert result_arg.exception is test_exception


def test_scale_with_kubectl_flags(cli_runner: CliRunner) -> None:
    """Test scale command with additional kubectl flags."""
    with (
        patch("vibectl.subcommands.scale_cmd.run_kubectl") as mock_run_kubectl,
        patch(
            "vibectl.subcommands.scale_cmd.handle_command_output"
        ) as mock_handle_output,
    ):
        # Setup return values
        mock_run_kubectl.return_value = "deployment.apps/nginx scaled"

        # Execute the command with namespace and other flags
        result = cli_runner.invoke(
            scale, ["deployment/nginx", "--replicas=3", "-n", "default", "--record"]
        )

        # Verify kubectl received all arguments
        assert result.exit_code == 0
        mock_run_kubectl.assert_called_once_with(
            ["scale", "deployment/nginx", "--replicas=3", "-n", "default", "--record"],
            capture=True,
        )
        mock_handle_output.assert_called_once()
