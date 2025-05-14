"""Tests for the CLI rollout command.

This module tests the functionality of the rollout command group and its subcommands.
"""

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from vibectl.prompt import (
    rollout_general_prompt,
    rollout_history_prompt,
    rollout_status_prompt,
)


@pytest.mark.asyncio
async def test_rollout_status(cli_runner: CliRunner) -> None:
    """Test normal execution of the rollout status command."""
    from vibectl.cli import _rollout_common  # Import helper
    from vibectl.types import Success

    with (
        patch("vibectl.subcommands.rollout_cmd.run_kubectl") as mock_run_kubectl,
        patch(
            "vibectl.subcommands.rollout_cmd.handle_command_output"
        ) as mock_handle_output,
        patch("vibectl.cli.handle_result") as mock_handle_result,
    ):
        mock_run_kubectl.return_value = Success(
            data="deployment/nginx successfully rolled out"
        )

        await _rollout_common(
            subcommand="status",
            resource="deployment/nginx",
            args=("-n", "default"),
            show_raw_output=None,
            show_vibe=None,
            model=None,
            freeze_memory=False,
            unfreeze_memory=False,
            show_kubectl=None,
        )

        mock_run_kubectl.assert_called_once_with(
            ["rollout", "status", "deployment/nginx", "-n", "default"]
        )
        mock_handle_output.assert_called_once()
        _, kwargs = mock_handle_output.call_args
        assert kwargs["summary_prompt_func"] == rollout_status_prompt
        mock_handle_result.assert_called_once()
        call_args, _ = mock_handle_result.call_args
        assert isinstance(call_args[0], Success)


@pytest.mark.asyncio
async def test_rollout_history(cli_runner: CliRunner) -> None:
    """Test normal execution of the rollout history command."""
    from vibectl.cli import _rollout_common
    from vibectl.types import Success

    with (
        patch("vibectl.subcommands.rollout_cmd.run_kubectl") as mock_run_kubectl,
        patch(
            "vibectl.subcommands.rollout_cmd.handle_command_output"
        ) as mock_handle_output,
        patch("vibectl.cli.handle_result") as mock_handle_result,
    ):
        revision_output = "REVISION  CHANGE-CAUSE\n1         <none>\n2         <none>"
        mock_run_kubectl.return_value = Success(data=revision_output)

        await _rollout_common(
            subcommand="history",
            resource="deployment/nginx",
            args=(),
            show_raw_output=None,
            show_vibe=None,
            model=None,
            freeze_memory=False,
            unfreeze_memory=False,
            show_kubectl=None,
        )

        mock_run_kubectl.assert_called_once_with(
            ["rollout", "history", "deployment/nginx"]
        )
        mock_handle_output.assert_called_once()
        _, kwargs = mock_handle_output.call_args
        assert kwargs["summary_prompt_func"] == rollout_history_prompt
        mock_handle_result.assert_called_once()
        call_args, _ = mock_handle_result.call_args
        assert isinstance(call_args[0], Success)


@pytest.mark.asyncio
async def test_rollout_undo_with_confirmation(cli_runner: CliRunner) -> None:
    """Test rollout undo command with user confirmation."""
    # Import the helper function directly
    from vibectl.cli import _rollout_common

    # Import or mock necessary types/functions if needed
    from vibectl.types import Success

    with (
        patch("vibectl.subcommands.rollout_cmd.run_kubectl") as mock_run_kubectl,
        patch(
            "vibectl.subcommands.rollout_cmd.handle_command_output"
        ) as mock_handle_output,
        patch("click.confirm") as mock_confirm,
        patch("vibectl.cli.handle_result") as mock_handle_result,
    ):  # Mock handle_result
        mock_run_kubectl.return_value = Success(
            data="rollback to revision 2 deployment/nginx"
        )
        mock_confirm.return_value = True

        # Call the helper function directly
        await _rollout_common(
            subcommand="undo",
            resource="deployment/nginx",
            args=("--to-revision=2",),
            show_raw_output=None,  # Pass defaults or specific values
            show_vibe=None,
            model=None,
            freeze_memory=False,
            unfreeze_memory=False,
            show_kubectl=None,
            yes=False,
        )

        mock_confirm.assert_called_once()
        mock_run_kubectl.assert_called_once_with(
            ["rollout", "undo", "deployment/nginx", "--to-revision=2"]
        )
        mock_handle_output.assert_called_once()
        _, kwargs = mock_handle_output.call_args
        assert kwargs["summary_prompt_func"] == rollout_general_prompt
        # Assert that handle_result was called with a Success object
        mock_handle_result.assert_called_once()
        call_args, _ = mock_handle_result.call_args
        assert isinstance(call_args[0], Success)


@pytest.mark.asyncio
async def test_rollout_undo_with_yes_flag(cli_runner: CliRunner) -> None:
    """Test rollout undo command with --yes flag."""
    from vibectl.cli import _rollout_common
    from vibectl.types import Success

    with (
        patch("vibectl.subcommands.rollout_cmd.run_kubectl") as mock_run_kubectl,
        patch(
            "vibectl.subcommands.rollout_cmd.handle_command_output"
        ) as mock_handle_output,
        patch("click.confirm") as mock_confirm,
        patch("vibectl.cli.handle_result") as mock_handle_result,
    ):
        mock_run_kubectl.return_value = Success(
            data="rollback to revision 2 deployment/nginx"
        )

        await _rollout_common(
            subcommand="undo",
            resource="deployment/nginx",
            args=("--to-revision=2",),  # Pass args directly
            show_raw_output=None,
            show_vibe=None,
            model=None,
            freeze_memory=False,
            unfreeze_memory=False,
            show_kubectl=None,
            yes=True,  # Set yes flag
        )

        mock_confirm.assert_not_called()
        mock_run_kubectl.assert_called_once_with(
            ["rollout", "undo", "deployment/nginx", "--to-revision=2"]
        )
        mock_handle_output.assert_called_once()
        mock_handle_result.assert_called_once()
        call_args, _ = mock_handle_result.call_args
        assert isinstance(call_args[0], Success)


@pytest.mark.asyncio
async def test_rollout_undo_cancelled(cli_runner: CliRunner) -> None:
    """Test rollout undo command when user cancels the confirmation."""
    from vibectl.cli import _rollout_common
    from vibectl.types import Success

    with (
        patch("vibectl.subcommands.rollout_cmd.run_kubectl") as mock_run_kubectl,
        patch(
            "vibectl.subcommands.rollout_cmd.handle_command_output"
        ) as mock_handle_output,
        patch("click.confirm") as mock_confirm,
        patch("vibectl.subcommands.rollout_cmd.console_manager") as mock_console,
        patch("vibectl.cli.handle_result") as mock_handle_result,
    ):
        mock_confirm.return_value = False

        await _rollout_common(
            subcommand="undo",
            resource="deployment/nginx",
            args=(),
            show_raw_output=None,
            show_vibe=None,
            model=None,
            freeze_memory=False,
            unfreeze_memory=False,
            show_kubectl=None,
            yes=False,
        )

        mock_confirm.assert_called_once()
        mock_run_kubectl.assert_not_called()
        mock_handle_output.assert_not_called()
        mock_console.print_note.assert_called_once_with("Operation cancelled")
        # Check that handle_result was called with the cancellation Success message
        mock_handle_result.assert_called_once()
        call_args, _ = mock_handle_result.call_args
        assert isinstance(call_args[0], Success)
        assert call_args[0].message == "Operation cancelled"


@pytest.mark.asyncio
async def test_rollout_restart(cli_runner: CliRunner) -> None:
    """Test normal execution of the rollout restart command."""
    from vibectl.cli import _rollout_common
    from vibectl.types import Success

    with (
        patch("vibectl.subcommands.rollout_cmd.run_kubectl") as mock_run_kubectl,
        patch(
            "vibectl.subcommands.rollout_cmd.handle_command_output"
        ) as mock_handle_output,
        patch("vibectl.cli.handle_result") as mock_handle_result,
    ):
        mock_run_kubectl.return_value = Success(data="deployment.apps/nginx restarted")

        await _rollout_common(
            subcommand="restart",
            resource="deployment/nginx",
            args=(),
            show_raw_output=None,
            show_vibe=None,
            model=None,
            freeze_memory=False,
            unfreeze_memory=False,
            show_kubectl=None,
        )

        mock_run_kubectl.assert_called_once_with(
            ["rollout", "restart", "deployment/nginx"]
        )
        mock_handle_output.assert_called_once()
        _, kwargs = mock_handle_output.call_args
        assert kwargs["summary_prompt_func"] == rollout_general_prompt
        mock_handle_result.assert_called_once()
        call_args, _ = mock_handle_result.call_args
        assert isinstance(call_args[0], Success)


@pytest.mark.asyncio
async def test_rollout_pause(cli_runner: CliRunner) -> None:
    """Test normal execution of the rollout pause command."""
    from vibectl.cli import _rollout_common
    from vibectl.types import Success

    with (
        patch("vibectl.subcommands.rollout_cmd.run_kubectl") as mock_run_kubectl,
        patch(
            "vibectl.subcommands.rollout_cmd.handle_command_output"
        ) as mock_handle_output,
        patch("vibectl.cli.handle_result") as mock_handle_result,
    ):
        mock_run_kubectl.return_value = Success(data="deployment.apps/nginx paused")

        await _rollout_common(
            subcommand="pause",
            resource="deployment/nginx",
            args=(),
            show_raw_output=None,
            show_vibe=None,
            model=None,
            freeze_memory=False,
            unfreeze_memory=False,
            show_kubectl=None,
        )

        mock_run_kubectl.assert_called_once_with(
            ["rollout", "pause", "deployment/nginx"]
        )
        mock_handle_output.assert_called_once()
        _, kwargs = mock_handle_output.call_args
        assert kwargs["summary_prompt_func"] == rollout_general_prompt
        mock_handle_result.assert_called_once()
        call_args, _ = mock_handle_result.call_args
        assert isinstance(call_args[0], Success)


@pytest.mark.asyncio
async def test_rollout_resume(cli_runner: CliRunner) -> None:
    """Test normal execution of the rollout resume command."""
    from vibectl.cli import _rollout_common
    from vibectl.types import Success

    with (
        patch("vibectl.subcommands.rollout_cmd.run_kubectl") as mock_run_kubectl,
        patch(
            "vibectl.subcommands.rollout_cmd.handle_command_output"
        ) as mock_handle_output,
        patch("vibectl.cli.handle_result") as mock_handle_result,
    ):
        mock_run_kubectl.return_value = Success(data="deployment.apps/nginx resumed")

        await _rollout_common(
            subcommand="resume",
            resource="deployment/nginx",
            args=(),
            show_raw_output=None,
            show_vibe=None,
            model=None,
            freeze_memory=False,
            unfreeze_memory=False,
            show_kubectl=None,
        )

        mock_run_kubectl.assert_called_once_with(
            ["rollout", "resume", "deployment/nginx"]
        )
        mock_handle_output.assert_called_once()
        _, kwargs = mock_handle_output.call_args
        assert kwargs["summary_prompt_func"] == rollout_general_prompt
        mock_handle_result.assert_called_once()
        call_args, _ = mock_handle_result.call_args
        assert isinstance(call_args[0], Success)


@pytest.mark.asyncio
async def test_rollout_no_output(cli_runner: CliRunner) -> None:
    """Test rollout command when there's no output from kubectl."""
    from vibectl.cli import _rollout_common
    from vibectl.types import Success

    with (
        patch("vibectl.subcommands.rollout_cmd.run_kubectl") as mock_run_kubectl,
        patch(
            "vibectl.subcommands.rollout_cmd.handle_command_output"
        ) as mock_handle_output,
        patch(
            "vibectl.subcommands.rollout_cmd.console_manager"
        ) as mock_console_manager,
        patch("vibectl.cli.handle_result") as mock_handle_result,
    ):
        mock_run_kubectl.return_value = Success(data="")

        await _rollout_common(
            subcommand="status",
            resource="deployment/nginx",
            args=(),
            show_raw_output=None,
            show_vibe=None,
            model=None,
            freeze_memory=False,
            unfreeze_memory=False,
            show_kubectl=None,
        )

        mock_run_kubectl.assert_called_once_with(
            ["rollout", "status", "deployment/nginx"]
        )
        mock_handle_output.assert_not_called()
        mock_console_manager.print_note.assert_called_once_with(
            "No output from kubectl rollout command."
        )
        mock_handle_result.assert_called_once()
        call_args, _ = mock_handle_result.call_args
        assert isinstance(call_args[0], Success)
        assert call_args[0].message == "No output from kubectl rollout command."


@pytest.mark.asyncio
async def test_rollout_error_handling(cli_runner: CliRunner) -> None:
    """Test error handling in rollout command."""
    from vibectl.cli import _rollout_common
    from vibectl.types import Error

    with (
        patch("vibectl.subcommands.rollout_cmd.run_kubectl") as mock_run_kubectl,
        patch(
            "vibectl.subcommands.rollout_cmd.handle_command_output"
        ) as mock_handle_output,
        patch("vibectl.cli.handle_result") as mock_handle_result,
    ):
        mock_run_kubectl.return_value = Error(error="Test error")

        await _rollout_common(
            subcommand="status",
            resource="deployment/nginx",
            args=(),
            show_raw_output=None,
            show_vibe=None,
            model=None,
            freeze_memory=False,
            unfreeze_memory=False,
            show_kubectl=None,
        )

        mock_run_kubectl.assert_called_once_with(
            ["rollout", "status", "deployment/nginx"]
        )
        mock_handle_output.assert_not_called()
        mock_handle_result.assert_called_once()
        call_args, _ = mock_handle_result.call_args
        assert isinstance(call_args[0], Error)
        assert call_args[0].error == "Test error"


@pytest.mark.asyncio
async def test_rollout_with_args(cli_runner: CliRunner) -> None:
    """Test rollout command with additional arguments."""
    from vibectl.cli import _rollout_common
    from vibectl.types import Success

    with (
        patch("vibectl.subcommands.rollout_cmd.run_kubectl") as mock_run_kubectl,
        patch(
            "vibectl.subcommands.rollout_cmd.handle_command_output"
        ) as mock_handle_output,
        patch("vibectl.cli.handle_result") as mock_handle_result,
    ):
        mock_run_kubectl.return_value = Success(data="deployment.apps/nginx history")

        await _rollout_common(
            subcommand="history",
            resource="deployment",
            args=("nginx", "-n", "default"),
            show_raw_output=None,
            show_vibe=None,
            model=None,
            freeze_memory=False,
            unfreeze_memory=False,
            show_kubectl=None,
        )

        mock_run_kubectl.assert_called_once_with(
            ["rollout", "history", "deployment", "nginx", "-n", "default"]
        )
        mock_handle_output.assert_called_once()
        mock_handle_result.assert_called_once()
        call_args, _ = mock_handle_result.call_args
        assert isinstance(call_args[0], Success)
