"""Tests for the CLI scale command.

This module tests the functionality of the scale command group and its subcommands.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from vibectl.cli import cli
from vibectl.prompts.scale import scale_plan_prompt, scale_resource_prompt
from vibectl.types import Error, Success


@pytest.mark.asyncio
async def test_scale_vibe_request() -> None:
    """Test that the scale command handles vibe requests properly."""
    scale_cmd = cli.commands["scale"]  # type: ignore[attr-defined]
    with (
        patch(
            "vibectl.subcommands.scale_cmd.handle_vibe_request", new_callable=AsyncMock
        ) as mock_handle_vibe,
        patch("vibectl.cli.handle_result") as mock_handle_result,
    ):
        mock_handle_vibe.return_value = Success(message="Vibe request handled")

        await scale_cmd.main(
            ["vibe", "scale the frontend deployment to 5 replicas"],
            standalone_mode=False,
        )

        mock_handle_vibe.assert_called_once()
        _, kwargs = mock_handle_vibe.call_args
        assert kwargs["request"] == "scale the frontend deployment to 5 replicas"
        assert kwargs["command"] == "scale"
        assert callable(kwargs["plan_prompt_func"])
        assert kwargs["plan_prompt_func"] == scale_plan_prompt
        assert kwargs["summary_prompt_func"] == scale_resource_prompt
        assert kwargs["config"] is None
        mock_handle_result.assert_called_once_with(mock_handle_vibe.return_value)


@pytest.mark.asyncio
async def test_scale_vibe_no_request() -> None:
    """Test that the scale command properly handles missing vibe request
    by directly testing the run_scale_command function."""
    from vibectl.subcommands.scale_cmd import run_scale_command

    result = await run_scale_command(
        resource="vibe",
        args=(),
        show_vibe=None,
        freeze_memory=False,
        unfreeze_memory=False,
    )

    assert isinstance(result, Error)
    assert "Missing request after 'vibe'" in result.error


@pytest.mark.asyncio
async def test_scale_deployment_success() -> None:
    """Test normal execution of the scale deployment command."""
    scale_cmd = cli.commands["scale"]  # type: ignore[attr-defined]
    with (
        patch(
            "vibectl.subcommands.scale_cmd.run_kubectl", new_callable=Mock
        ) as mock_run_kubectl,
        patch(
            "vibectl.subcommands.scale_cmd.handle_command_output"
        ) as mock_handle_output,
        patch("vibectl.cli.handle_result") as mock_handle_result,
    ):
        mock_run_kubectl.return_value = Success(data="deployment.apps/nginx scaled")

        await scale_cmd.main(
            ["deployment", "nginx", "--replicas=5"], standalone_mode=False
        )

        mock_run_kubectl.assert_called_once_with(
            ["scale", "deployment", "nginx", "--replicas=5"]
        )
        mock_handle_output.assert_called_once()
        mock_handle_result.assert_called_once()
        args, _ = mock_handle_result.call_args
        assert isinstance(args[0], Success)


@pytest.mark.asyncio
async def test_scale_integration_flow() -> None:
    """Test the integration between scale parent command and kubectl command."""
    scale_cmd = cli.commands["scale"]  # type: ignore[attr-defined]
    with (
        patch(
            "vibectl.subcommands.scale_cmd.run_kubectl", new_callable=Mock
        ) as mock_run_kubectl,
        patch(
            "vibectl.subcommands.scale_cmd.handle_command_output"
        ) as mock_handle_output,
        patch("vibectl.cli.handle_result") as mock_handle_result,
    ):
        mock_run_kubectl.return_value = Success(data="deployment.apps/nginx scaled")

        await scale_cmd.main(
            ["deployment", "nginx", "--replicas=5"], standalone_mode=False
        )

        mock_run_kubectl.assert_called_once_with(
            ["scale", "deployment", "nginx", "--replicas=5"]
        )
        mock_handle_output.assert_called_once()
        mock_handle_result.assert_called_once()
        args, _ = mock_handle_result.call_args
        assert isinstance(args[0], Success)


@pytest.mark.asyncio
async def test_scale_normal_execution() -> None:
    """Test normal execution of the scale command with mocks for internal functions."""
    scale_cmd = cli.commands["scale"]  # type: ignore[attr-defined]
    with (
        patch(
            "vibectl.subcommands.scale_cmd.run_kubectl", new_callable=Mock
        ) as mock_run_kubectl,
        patch(
            "vibectl.subcommands.scale_cmd.handle_command_output"
        ) as mock_handle_output,
        patch("vibectl.cli.handle_result") as mock_handle_result,
    ):
        mock_run_kubectl.return_value = Success(data="deployment.apps/nginx scaled")

        await scale_cmd.main(
            ["deployment/nginx", "--replicas=3"], standalone_mode=False
        )

        mock_run_kubectl.assert_called_once_with(
            ["scale", "deployment/nginx", "--replicas=3"]
        )
        mock_handle_output.assert_called_once()
        mock_handle_result.assert_called_once()
        args, _ = mock_handle_result.call_args
        assert isinstance(args[0], Success)


@pytest.mark.asyncio
async def test_scale_no_output() -> None:
    """Test scale command when there's no output from kubectl."""
    scale_cmd = cli.commands["scale"]  # type: ignore[attr-defined]
    with (
        patch(
            "vibectl.subcommands.scale_cmd.run_kubectl", new_callable=Mock
        ) as mock_run_kubectl,
        patch(
            "vibectl.subcommands.scale_cmd.handle_command_output"
        ) as mock_handle_output,
        patch("vibectl.cli.handle_result") as mock_handle_result,
    ):
        mock_run_kubectl.return_value = Success(data="")

        await scale_cmd.main(
            ["deployment/nginx", "--replicas=3"], standalone_mode=False
        )

        mock_run_kubectl.assert_called_once_with(
            ["scale", "deployment/nginx", "--replicas=3"]
        )
        mock_handle_output.assert_not_called()
        mock_handle_result.assert_called_once()
        args, _ = mock_handle_result.call_args
        assert isinstance(args[0], Success)
        assert args[0].message == "No output from kubectl scale command."


@pytest.mark.asyncio
async def test_scale_error_handling() -> None:
    """Test error handling in scale command."""
    scale_cmd = cli.commands["scale"]  # type: ignore[attr-defined]
    with (
        patch(
            "vibectl.subcommands.scale_cmd.run_kubectl", new_callable=Mock
        ) as mock_run_kubectl,
        patch("vibectl.cli.handle_result") as mock_handle_result,
    ):
        test_exception = Exception("Test error")
        expected_error = Error(error="kubectl failed", exception=test_exception)
        mock_run_kubectl.return_value = expected_error

        await scale_cmd.main(
            ["deployment/nginx", "--replicas=3"], standalone_mode=False
        )

        mock_run_kubectl.assert_called_once()
        mock_handle_result.assert_called_once_with(expected_error)


@pytest.mark.asyncio
async def test_scale_with_kubectl_flags() -> None:
    """Test scale command with additional kubectl flags."""
    scale_cmd = cli.commands["scale"]  # type: ignore[attr-defined]
    with (
        patch(
            "vibectl.subcommands.scale_cmd.run_kubectl", new_callable=Mock
        ) as mock_run_kubectl,
        patch(
            "vibectl.subcommands.scale_cmd.handle_command_output"
        ) as mock_handle_output,
        patch("vibectl.cli.handle_result") as mock_handle_result,
    ):
        mock_run_kubectl.return_value = Success(data="deployment.apps/nginx scaled")

        await scale_cmd.main(
            ["deployment/nginx", "--replicas=3", "-n", "default", "--record"],
            standalone_mode=False,
        )

        mock_run_kubectl.assert_called_once_with(
            ["scale", "deployment/nginx", "--replicas=3", "-n", "default", "--record"],
        )
        mock_handle_output.assert_called_once()
        mock_handle_result.assert_called_once()
        args, _ = mock_handle_result.call_args
        assert isinstance(args[0], Success)
