"""Integration tests for the edit command module."""

from unittest.mock import Mock, patch

import pytest

from vibectl.subcommands.edit_cmd import run_edit_command
from vibectl.types import Error, Success


@pytest.mark.asyncio
class TestEditCommandIntegration:
    """Test the edit command integration."""

    async def test_edit_command_with_intelligent_edit_enabled(self) -> None:
        """Test edit command when intelligent edit is enabled."""
        with (
            patch("vibectl.subcommands.edit_cmd.Config") as mock_config_class,
            patch(
                "vibectl.subcommands.edit_cmd.run_intelligent_edit_workflow"
            ) as mock_intelligent_workflow,
        ):
            # Setup mock config
            mock_config = Mock()
            mock_config.get_typed.return_value = True  # intelligent_edit enabled
            mock_config_class.return_value = mock_config

            # Setup mock workflow
            mock_intelligent_workflow.return_value = Success("Edit completed")

            result = await run_edit_command(
                resource="deployment",
                args=("nginx",),
                show_raw_output=False,
                show_vibe=False,
                show_kubectl=False,
                model=None,
                freeze_memory=False,
                unfreeze_memory=False,
                show_metrics=False,
                show_streaming=False,
            )

            assert isinstance(result, Success)
            mock_intelligent_workflow.assert_called_once()

    async def test_edit_command_with_intelligent_edit_disabled(self) -> None:
        """Test edit command when intelligent edit is disabled."""
        with (
            patch("vibectl.subcommands.edit_cmd.Config") as mock_config_class,
            patch(
                "vibectl.subcommands.edit_cmd.handle_standard_command"
            ) as mock_standard_command,
        ):
            # Setup mock config
            mock_config = Mock()
            mock_config.get_typed.return_value = False  # intelligent_edit disabled
            mock_config_class.return_value = mock_config

            # Setup mock standard command
            mock_standard_command.return_value = Success("Standard edit completed")

            result = await run_edit_command(
                resource="deployment",
                args=("nginx",),
                show_raw_output=False,
                show_vibe=False,
                show_kubectl=False,
                model=None,
                freeze_memory=False,
                unfreeze_memory=False,
                show_metrics=False,
                show_streaming=False,
            )

            assert isinstance(result, Success)
            mock_standard_command.assert_called_once()

    async def test_edit_vibe_command_with_intelligent_edit_enabled(self) -> None:
        """Test edit vibe command when intelligent edit is enabled."""
        with (
            patch("vibectl.subcommands.edit_cmd.Config") as mock_config_class,
            patch(
                "vibectl.subcommands.edit_cmd.run_intelligent_vibe_edit_workflow"
            ) as mock_vibe_workflow,
        ):
            # Setup mock config
            mock_config = Mock()
            mock_config.get_typed.return_value = True  # intelligent_edit enabled
            mock_config_class.return_value = mock_config

            # Setup mock workflow
            mock_vibe_workflow.return_value = Success("Vibe edit completed")

            result = await run_edit_command(
                resource="vibe",
                args=("nginx deployment replicas",),
                show_raw_output=False,
                show_vibe=False,
                show_kubectl=False,
                model=None,
                freeze_memory=False,
                unfreeze_memory=False,
                show_metrics=False,
                show_streaming=False,
            )

            assert isinstance(result, Success)
            mock_vibe_workflow.assert_called_once_with(
                request="nginx deployment replicas",
                output_flags=mock_vibe_workflow.call_args[1]["output_flags"],
                config=mock_config,
            )

    async def test_edit_vibe_command_with_intelligent_edit_disabled(self) -> None:
        """Test edit vibe command when intelligent edit is disabled."""
        with (
            patch("vibectl.subcommands.edit_cmd.Config") as mock_config_class,
            patch(
                "vibectl.subcommands.edit_cmd.handle_vibe_request"
            ) as mock_vibe_request,
        ):
            # Setup mock config
            mock_config = Mock()
            mock_config.get_typed.return_value = False  # intelligent_edit disabled
            mock_config_class.return_value = mock_config

            # Setup mock vibe request
            mock_vibe_request.return_value = Success("Basic vibe completed")

            result = await run_edit_command(
                resource="vibe",
                args=("nginx deployment replicas",),
                show_raw_output=False,
                show_vibe=False,
                show_kubectl=False,
                model=None,
                freeze_memory=False,
                unfreeze_memory=False,
                show_metrics=False,
                show_streaming=False,
            )

            assert isinstance(result, Success)
            mock_vibe_request.assert_called_once()

    async def test_edit_vibe_command_missing_request(self) -> None:
        """Test edit vibe command with no request provided."""
        with patch("vibectl.subcommands.edit_cmd.Config") as mock_config_class:
            # Setup mock config
            mock_config = Mock()
            mock_config.get_typed.return_value = True  # intelligent_edit enabled
            mock_config_class.return_value = mock_config

            result = await run_edit_command(
                resource="vibe",
                args=(),  # Empty args
                show_raw_output=False,
                show_vibe=False,
                show_kubectl=False,
                model=None,
                freeze_memory=False,
                unfreeze_memory=False,
                show_metrics=False,
                show_streaming=False,
            )

            assert isinstance(result, Error)
            assert "Missing request after 'vibe' command" in result.error

    async def test_edit_command_with_all_flags_enabled(self) -> None:
        """Test edit command with all output flags enabled."""
        with (
            patch("vibectl.subcommands.edit_cmd.Config") as mock_config_class,
            patch(
                "vibectl.subcommands.edit_cmd.configure_output_flags"
            ) as mock_configure_output,
            patch(
                "vibectl.subcommands.edit_cmd.configure_memory_flags"
            ) as mock_configure_memory,
            patch(
                "vibectl.subcommands.edit_cmd.run_intelligent_edit_workflow"
            ) as mock_intelligent_workflow,
        ):
            # Setup mock config
            mock_config = Mock()
            mock_config.get_typed.return_value = True  # intelligent_edit enabled
            mock_config_class.return_value = mock_config

            # Setup mock workflow
            mock_intelligent_workflow.return_value = Success("Edit completed")

            result = await run_edit_command(
                resource="deployment",
                args=("nginx",),
                show_raw_output=True,
                show_vibe=True,
                show_kubectl=True,
                model="gpt-4",
                freeze_memory=True,
                unfreeze_memory=False,
                show_metrics=True,
                show_streaming=True,
            )

            assert isinstance(result, Success)

            # Verify flags were configured correctly
            mock_configure_output.assert_called_once_with(
                show_raw_output=True,
                show_vibe=True,
                model="gpt-4",
                show_kubectl=True,
                show_metrics=True,
                show_streaming=True,
            )
            mock_configure_memory.assert_called_once_with(True, False)
