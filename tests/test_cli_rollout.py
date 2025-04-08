"""Tests for the CLI rollout command.

This module tests the functionality of the rollout command group and its subcommands.
"""

from unittest.mock import patch

from click.testing import CliRunner

from vibectl.cli import cli, history, pause, restart, resume, rollout, status, undo
from vibectl.prompt import (
    PLAN_ROLLOUT_PROMPT,
    rollout_general_prompt,
    rollout_history_prompt,
    rollout_status_prompt,
)


def test_rollout_vibe_request(cli_runner: CliRunner) -> None:
    """Test that the rollout command handles vibe requests properly."""
    with patch("vibectl.cli.handle_vibe_request") as mock_handle_vibe:
        result = cli_runner.invoke(
            rollout, ["vibe", "check status of frontend deployment"]
        )

        assert result.exit_code == 0
        mock_handle_vibe.assert_called_once()
        _, kwargs = mock_handle_vibe.call_args
        assert kwargs["request"] == "check status of frontend deployment"
        assert kwargs["command"] == "rollout"
        assert kwargs["plan_prompt"] == PLAN_ROLLOUT_PROMPT


def test_rollout_vibe_no_request(cli_runner: CliRunner) -> None:
    """Test that the rollout command properly handles missing vibe request."""
    with patch("vibectl.cli.console_manager") as mock_console:
        result = cli_runner.invoke(rollout, ["vibe"])

        assert result.exit_code == 1
        mock_console.print_error.assert_called_once_with("Missing request after 'vibe'")


def test_rollout_no_subcommand(cli_runner: CliRunner) -> None:
    """Test that an error is displayed when no subcommand is provided for rollout."""
    with patch("vibectl.cli.console_manager") as mock_console:
        result = cli_runner.invoke(rollout, [])

        assert result.exit_code == 1
        mock_console.print_error.assert_called_once_with(
            "Missing subcommand for rollout. "
            "Use one of: status, history, undo, restart, pause, resume"
        )


def test_rollout_status(cli_runner: CliRunner) -> None:
    """Test normal execution of the rollout status command."""
    with (
        patch("vibectl.cli.run_kubectl") as mock_run_kubectl,
        patch("vibectl.cli.handle_command_output") as mock_handle_output,
        patch("vibectl.cli.configure_output_flags") as mock_configure,
        patch("sys.exit") as mock_exit,  # Prevent test from exiting
    ):
        # Setup return values
        mock_run_kubectl.return_value = "deployment/nginx successfully rolled out"
        mock_configure.return_value = (False, True, False, "test-model")
        mock_exit.side_effect = lambda code=0: None  # Do nothing instead of exiting

        # Execute the command
        _ = cli_runner.invoke(status, ["deployment/nginx"])

        # With sys.exit mocked, we can't rely on exit code checks
        # Just verify the functions were called correctly
        mock_run_kubectl.assert_called_once_with(
            ["rollout", "status", "deployment/nginx"], capture=True
        )
        mock_handle_output.assert_called_once()
        _, kwargs = mock_handle_output.call_args
        assert kwargs["summary_prompt_func"] == rollout_status_prompt


def test_rollout_history(cli_runner: CliRunner) -> None:
    """Test normal execution of the rollout history command."""
    with (
        patch("vibectl.cli.run_kubectl") as mock_run_kubectl,
        patch("vibectl.cli.handle_command_output") as mock_handle_output,
        patch("vibectl.cli.configure_output_flags") as mock_configure,
        patch("sys.exit") as mock_exit,  # Prevent test from exiting
    ):
        # Setup return values
        revision_output = "REVISION  CHANGE-CAUSE\n1         <none>\n2         <none>"
        mock_run_kubectl.return_value = revision_output
        mock_configure.return_value = (False, True, False, "test-model")
        mock_exit.side_effect = lambda code=0: None  # Do nothing instead of exiting

        # Execute the command
        _ = cli_runner.invoke(history, ["deployment/nginx"])

        # With sys.exit mocked, we can't rely on exit code checks
        # Just verify the functions were called correctly
        mock_run_kubectl.assert_called_once_with(
            ["rollout", "history", "deployment/nginx"], capture=True
        )
        mock_handle_output.assert_called_once()
        _, kwargs = mock_handle_output.call_args
        assert kwargs["summary_prompt_func"] == rollout_history_prompt


def test_rollout_undo_with_confirmation(cli_runner: CliRunner) -> None:
    """Test rollout undo command with user confirmation."""
    with (
        patch("vibectl.cli.run_kubectl") as mock_run_kubectl,
        patch("vibectl.cli.handle_command_output") as mock_handle_output,
        patch("vibectl.cli.configure_output_flags") as mock_configure,
        patch("click.confirm") as mock_confirm,
        patch("sys.exit") as mock_exit,  # Prevent test from exiting
    ):
        # Setup return values
        mock_run_kubectl.return_value = "rollback to revision 2 deployment/nginx"
        mock_configure.return_value = (False, True, False, "test-model")
        mock_confirm.return_value = True
        mock_exit.side_effect = lambda code=0: None  # Do nothing instead of exiting

        # Execute the command
        _ = cli_runner.invoke(undo, ["deployment/nginx", "--to-revision=2"])

        # With sys.exit mocked, we can't rely on exit code checks
        # Just verify the functions were called correctly
        mock_confirm.assert_called_once()
        mock_run_kubectl.assert_called_once_with(
            ["rollout", "undo", "deployment/nginx", "--to-revision=2"], capture=True
        )
        mock_handle_output.assert_called_once()
        _, kwargs = mock_handle_output.call_args
        assert kwargs["summary_prompt_func"] == rollout_general_prompt


def test_rollout_undo_with_yes_flag(cli_runner: CliRunner) -> None:
    """Test rollout undo command with --yes flag."""
    with (
        patch("vibectl.cli.run_kubectl") as mock_run_kubectl,
        patch("vibectl.cli.handle_command_output") as mock_handle_output,
        patch("vibectl.cli.configure_output_flags") as mock_configure,
        patch("click.confirm") as mock_confirm,
        patch("sys.exit") as mock_exit,  # Prevent test from exiting
    ):
        # Setup return values
        mock_run_kubectl.return_value = "rollback to revision 2 deployment/nginx"
        mock_configure.return_value = (False, True, False, "test-model")
        mock_exit.side_effect = lambda code=0: None  # Do nothing instead of exiting

        # Execute the command with --yes flag
        _ = cli_runner.invoke(undo, ["deployment/nginx", "--to-revision=2", "--yes"])

        # With sys.exit mocked, we can't rely on exit code checks
        # Just verify the functions were called correctly
        mock_confirm.assert_not_called()  # Should skip confirmation
        mock_run_kubectl.assert_called_once_with(
            ["rollout", "undo", "deployment/nginx", "--to-revision=2"], capture=True
        )
        mock_handle_output.assert_called_once()


def test_rollout_undo_cancelled(cli_runner: CliRunner) -> None:
    """Test rollout undo command when user cancels the confirmation."""
    with (
        patch("vibectl.cli.run_kubectl") as mock_run_kubectl,
        patch("vibectl.cli.handle_command_output") as mock_handle_output,
        patch("vibectl.cli.configure_output_flags") as mock_configure,
        patch("click.confirm") as mock_confirm,
        patch("vibectl.cli.console_manager") as mock_console,
        patch("sys.exit") as mock_exit,  # Prevent test from exiting
    ):
        # Setup return values
        mock_configure.return_value = (False, True, False, "test-model")
        mock_confirm.return_value = False
        mock_exit.side_effect = lambda code=0: None  # Do nothing instead of exiting

        # Execute the command
        _ = cli_runner.invoke(undo, ["deployment/nginx"])

        # With sys.exit mocked, we can't rely on exit code checks
        # Just verify the functions were called correctly
        mock_confirm.assert_called_once()
        mock_run_kubectl.assert_not_called()  # Should not run kubectl if cancelled
        mock_handle_output.assert_not_called()  # Should not handle output if cancelled
        mock_console.print_note.assert_called_once_with("Operation cancelled")


def test_rollout_restart(cli_runner: CliRunner) -> None:
    """Test normal execution of the rollout restart command."""
    with (
        patch("vibectl.cli.run_kubectl") as mock_run_kubectl,
        patch("vibectl.cli.handle_command_output") as mock_handle_output,
        patch("vibectl.cli.configure_output_flags") as mock_configure,
        patch("sys.exit") as mock_exit,  # Prevent test from exiting
    ):
        # Setup return values
        mock_run_kubectl.return_value = "deployment.apps/nginx restarted"
        mock_configure.return_value = (False, True, False, "test-model")
        mock_exit.side_effect = lambda code=0: None  # Do nothing instead of exiting

        # Execute the command
        _ = cli_runner.invoke(restart, ["deployment/nginx"])

        # With sys.exit mocked, we can't rely on exit code checks
        # Just verify the functions were called correctly
        mock_run_kubectl.assert_called_once_with(
            ["rollout", "restart", "deployment/nginx"], capture=True
        )
        mock_handle_output.assert_called_once()
        _, kwargs = mock_handle_output.call_args
        assert kwargs["summary_prompt_func"] == rollout_general_prompt


def test_rollout_pause(cli_runner: CliRunner) -> None:
    """Test normal execution of the rollout pause command."""
    with (
        patch("vibectl.cli.run_kubectl") as mock_run_kubectl,
        patch("vibectl.cli.handle_command_output") as mock_handle_output,
        patch("vibectl.cli.configure_output_flags") as mock_configure,
        patch("sys.exit") as mock_exit,  # Prevent test from exiting
    ):
        # Setup return values
        mock_run_kubectl.return_value = "deployment.apps/nginx paused"
        mock_configure.return_value = (False, True, False, "test-model")
        mock_exit.side_effect = lambda code=0: None  # Do nothing instead of exiting

        # Execute the command
        _ = cli_runner.invoke(pause, ["deployment/nginx"])

        # With sys.exit mocked, we can't rely on exit code checks
        # Just verify the functions were called correctly
        mock_run_kubectl.assert_called_once_with(
            ["rollout", "pause", "deployment/nginx"], capture=True
        )
        mock_handle_output.assert_called_once()
        _, kwargs = mock_handle_output.call_args
        assert kwargs["summary_prompt_func"] == rollout_general_prompt


def test_rollout_resume(cli_runner: CliRunner) -> None:
    """Test normal execution of the rollout resume command."""
    with (
        patch("vibectl.cli.run_kubectl") as mock_run_kubectl,
        patch("vibectl.cli.handle_command_output") as mock_handle_output,
        patch("vibectl.cli.configure_output_flags") as mock_configure,
        patch("sys.exit") as mock_exit,  # Prevent test from exiting
    ):
        # Setup return values
        mock_run_kubectl.return_value = "deployment.apps/nginx resumed"
        mock_configure.return_value = (False, True, False, "test-model")
        mock_exit.side_effect = lambda code=0: None  # Do nothing instead of exiting

        # Execute the command
        _ = cli_runner.invoke(resume, ["deployment/nginx"])

        # With sys.exit mocked, we can't rely on exit code checks
        # Just verify the functions were called correctly
        mock_run_kubectl.assert_called_once_with(
            ["rollout", "resume", "deployment/nginx"], capture=True
        )
        mock_handle_output.assert_called_once()
        _, kwargs = mock_handle_output.call_args
        assert kwargs["summary_prompt_func"] == rollout_general_prompt


def test_rollout_no_output(cli_runner: CliRunner) -> None:
    """Test rollout command when there's no output from kubectl."""
    with (
        patch("vibectl.cli.run_kubectl") as mock_run_kubectl,
        patch("vibectl.cli.handle_command_output") as mock_handle_output,
        patch("vibectl.cli.configure_output_flags") as mock_configure,
        patch("sys.exit") as mock_exit,  # Prevent test from exiting
    ):
        # Setup return values
        mock_run_kubectl.return_value = ""
        mock_configure.return_value = (False, True, False, "test-model")
        mock_exit.side_effect = lambda code=0: None  # Do nothing instead of exiting

        # Execute
        _ = cli_runner.invoke(status, ["deployment/nginx"])

        # With sys.exit mocked, we can't rely on exit code checks
        # Just verify the functions were called correctly
        mock_run_kubectl.assert_called_once_with(
            ["rollout", "status", "deployment/nginx"], capture=True
        )
        # No output should not trigger handle_command_output
        mock_handle_output.assert_not_called()


def test_rollout_error_handling(cli_runner: CliRunner) -> None:
    """Test error handling in rollout command."""
    with (
        patch("vibectl.cli.run_kubectl") as mock_run_kubectl,
        patch("vibectl.cli.handle_exception") as mock_handle_exception,
        patch("vibectl.cli.configure_output_flags") as mock_configure,
        patch("sys.exit") as mock_exit,  # Prevent test from exiting
    ):
        # Setup an exception
        mock_run_kubectl.side_effect = Exception("Test error")
        mock_configure.return_value = (False, True, False, "test-model")
        mock_exit.side_effect = lambda code=0: None  # Do nothing instead of exiting

        # Execute
        _ = cli_runner.invoke(status, ["deployment/nginx"])

        # With sys.exit mocked, we can't rely on exit code checks
        # Verify the exception was handled
        mock_handle_exception.assert_called_once()


def test_rollout_with_args(cli_runner: CliRunner) -> None:
    """Test rollout command with additional arguments."""
    with (
        patch("vibectl.cli.run_kubectl") as mock_run_kubectl,
        patch("vibectl.cli.handle_command_output") as mock_handle_output,
        patch("vibectl.cli.configure_output_flags") as mock_configure,
        patch("sys.exit") as mock_exit,  # Prevent test from exiting
    ):
        # Setup return values
        mock_run_kubectl.return_value = "deployment.apps/nginx history"
        mock_configure.return_value = (False, True, False, "test-model")
        mock_exit.side_effect = lambda code=0: None  # Do nothing instead of exiting

        # Execute with namespace argument
        _ = cli_runner.invoke(history, ["deployment", "nginx", "-n", "default"])

        # With sys.exit mocked, we can't rely on exit code checks
        # Just verify the functions were called correctly
        mock_run_kubectl.assert_called_once_with(
            ["rollout", "history", "deployment", "nginx", "-n", "default"],
            capture=True,
        )
        mock_handle_output.assert_called_once()


def test_rollout_integration_flow(cli_runner: CliRunner) -> None:
    """Test the integration between rollout parent command and subcommands."""
    with (
        patch("vibectl.cli.handle_vibe_request") as mock_handle_vibe,
        patch("sys.exit") as mock_exit,  # Prevent test from exiting
    ):
        mock_exit.side_effect = lambda code=0: None  # Do nothing instead of exiting

        # Execute rollout with subcommand status
        result = cli_runner.invoke(cli, ["rollout", "status", "deployment/nginx"])

        # The pass-through in rollout should happen, not triggering handle_vibe_request
        mock_handle_vibe.assert_not_called()

        # The status subcommand should be invoked, we can check this by having a
        # non-error exit code (thanks to the mocked sys.exit)
        assert result.exit_code == 0
