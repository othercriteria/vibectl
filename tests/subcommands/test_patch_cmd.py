"""Tests for the 'patch' subcommand logic in vibectl/subcommands/patch_cmd.py."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from vibectl.prompts.patch import patch_plan_prompt, patch_resource_prompt
from vibectl.subcommands.patch_cmd import run_patch_command
from vibectl.types import Error, MetricsDisplayMode, OutputFlags, Success


@pytest.fixture
def default_patch_output_flags() -> OutputFlags:
    """Default OutputFlags for patch command tests."""
    return OutputFlags(
        show_raw_output=False,
        show_vibe=True,
        warn_no_output=True,
        model_name="default-model",
        show_metrics=MetricsDisplayMode.NONE,
        show_kubectl=False,
        warn_no_proxy=True,
        show_streaming=True,
    )


class TestRunPatchCommand:
    """Test cases for the run_patch_command function."""

    @pytest.mark.asyncio
    @patch("vibectl.subcommands.patch_cmd.handle_standard_command")
    @patch("vibectl.subcommands.patch_cmd.configure_output_flags")
    @patch("vibectl.subcommands.patch_cmd.configure_memory_flags")
    async def test_patch_standard_basic(
        self,
        mock_configure_memory: Mock,
        mock_configure_output: Mock,
        mock_handle_standard: AsyncMock,
        default_patch_output_flags: OutputFlags,
    ) -> None:
        """Test basic patch command functionality."""
        mock_configure_output.return_value = default_patch_output_flags
        mock_handle_standard.return_value = Success(
            data="deployment.apps/nginx patched"
        )

        result = await run_patch_command(
            resource="deployment",
            args=("nginx", "-p", '{"spec":{"replicas":3}}'),
            show_raw_output=False,
            show_vibe=True,
            show_kubectl=False,
            model="default-model",
            freeze_memory=False,
            unfreeze_memory=False,
            show_metrics=MetricsDisplayMode.NONE,
            show_streaming=True,
        )

        assert isinstance(result, Success)
        assert result.data == "deployment.apps/nginx patched"

        mock_configure_output.assert_called_once_with(
            show_raw_output=False,
            show_vibe=True,
            model="default-model",
            show_kubectl=False,
            show_metrics=MetricsDisplayMode.NONE,
            show_streaming=True,
        )
        mock_configure_memory.assert_called_once_with(False, False)
        mock_handle_standard.assert_called_once_with(
            command="patch",
            resource="deployment",
            args=("nginx", "-p", '{"spec":{"replicas":3}}'),
            output_flags=default_patch_output_flags,
            summary_prompt_func=patch_resource_prompt,
        )

    @pytest.mark.asyncio
    @patch("vibectl.subcommands.patch_cmd.handle_standard_command")
    @patch("vibectl.subcommands.patch_cmd.configure_output_flags")
    @patch("vibectl.subcommands.patch_cmd.configure_memory_flags")
    async def test_patch_standard_with_patch_file(
        self,
        mock_configure_memory: Mock,
        mock_configure_output: Mock,
        mock_handle_standard: AsyncMock,
        default_patch_output_flags: OutputFlags,
    ) -> None:
        """Test patch command with patch file."""
        mock_configure_output.return_value = default_patch_output_flags
        mock_handle_standard.return_value = Success(data="service/web-service patched")

        result = await run_patch_command(
            resource="service",
            args=("web-service", "--patch-file", "patch.yaml"),
            show_raw_output=True,
            show_vibe=False,
            show_kubectl=True,
            model="test-model",
            freeze_memory=True,
            unfreeze_memory=False,
            show_metrics=MetricsDisplayMode.ALL,
            show_streaming=False,
        )

        assert isinstance(result, Success)
        assert result.data == "service/web-service patched"

        mock_configure_output.assert_called_once_with(
            show_raw_output=True,
            show_vibe=False,
            model="test-model",
            show_kubectl=True,
            show_metrics=MetricsDisplayMode.ALL,
            show_streaming=False,
        )
        mock_configure_memory.assert_called_once_with(True, False)
        mock_handle_standard.assert_called_once_with(
            command="patch",
            resource="service",
            args=("web-service", "--patch-file", "patch.yaml"),
            output_flags=default_patch_output_flags,
            summary_prompt_func=patch_resource_prompt,
        )

    @pytest.mark.asyncio
    @patch("vibectl.subcommands.patch_cmd.handle_standard_command")
    @patch("vibectl.subcommands.patch_cmd.configure_output_flags")
    @patch("vibectl.subcommands.patch_cmd.configure_memory_flags")
    async def test_patch_standard_error_propagation(
        self,
        mock_configure_memory: Mock,
        mock_configure_output: Mock,
        mock_handle_standard: AsyncMock,
        default_patch_output_flags: OutputFlags,
    ) -> None:
        """Test that errors from handle_standard_command are propagated."""
        mock_configure_output.return_value = default_patch_output_flags
        expected_error = Error(error="kubectl patch failed")
        mock_handle_standard.return_value = expected_error

        result = await run_patch_command(
            resource="deployment",
            args=("nginx", "-p", '{"spec":{"replicas":5}}'),
            show_raw_output=None,
            show_vibe=None,
            show_kubectl=None,
            model=None,
            freeze_memory=False,
            unfreeze_memory=False,
            show_metrics=None,
            show_streaming=None,
        )

        assert isinstance(result, Error)
        assert result.error == "kubectl patch failed"
        assert result == expected_error

    @pytest.mark.asyncio
    @patch("vibectl.subcommands.patch_cmd.handle_vibe_request")
    @patch("vibectl.subcommands.patch_cmd.configure_output_flags")
    @patch("vibectl.subcommands.patch_cmd.configure_memory_flags")
    async def test_patch_vibe_basic(
        self,
        mock_configure_memory: Mock,
        mock_configure_output: Mock,
        mock_handle_vibe: AsyncMock,
        default_patch_output_flags: OutputFlags,
    ) -> None:
        """Test basic vibe patch command functionality."""
        mock_configure_output.return_value = default_patch_output_flags
        mock_handle_vibe.return_value = Success(data="vibe patch completed")

        result = await run_patch_command(
            resource="vibe",
            args=("scale nginx deployment to 5 replicas",),
            show_raw_output=False,
            show_vibe=True,
            show_kubectl=True,
            model="claude-3.5-sonnet",
            freeze_memory=False,
            unfreeze_memory=True,
            show_metrics=MetricsDisplayMode.ALL,
            show_streaming=False,
        )

        assert isinstance(result, Success)
        assert result.data == "vibe patch completed"

        mock_configure_output.assert_called_once_with(
            show_raw_output=False,
            show_vibe=True,
            model="claude-3.5-sonnet",
            show_kubectl=True,
            show_metrics=MetricsDisplayMode.ALL,
            show_streaming=False,
        )
        mock_configure_memory.assert_called_once_with(False, True)
        mock_handle_vibe.assert_called_once()

        # Verify handle_vibe_request was called with correct parameters
        call_kwargs = mock_handle_vibe.call_args.kwargs
        assert call_kwargs["request"] == "scale nginx deployment to 5 replicas"
        assert call_kwargs["command"] == "patch"
        assert call_kwargs["output_flags"] == default_patch_output_flags
        assert call_kwargs["summary_prompt_func"] == patch_resource_prompt

        # Test that plan_prompt_func returns PLAN_PATCH_PROMPT
        plan_prompt_func = call_kwargs["plan_prompt_func"]
        assert plan_prompt_func() == patch_plan_prompt()

    @pytest.mark.asyncio
    @patch("vibectl.subcommands.patch_cmd.handle_vibe_request")
    @patch("vibectl.subcommands.patch_cmd.configure_output_flags")
    @patch("vibectl.subcommands.patch_cmd.configure_memory_flags")
    async def test_patch_vibe_multi_word_request(
        self,
        mock_configure_memory: Mock,
        mock_configure_output: Mock,
        mock_handle_vibe: AsyncMock,
        default_patch_output_flags: OutputFlags,
    ) -> None:
        """Test vibe patch command with multi-word request."""
        mock_configure_output.return_value = default_patch_output_flags
        mock_handle_vibe.return_value = Success(data="complex vibe patch completed")

        result = await run_patch_command(
            resource="vibe",
            args=("update", "container", "image", "to", "nginx:1.21", "in", "my-app"),
            show_raw_output=None,
            show_vibe=None,
            show_kubectl=None,
            model=None,
            freeze_memory=False,
            unfreeze_memory=False,
            show_metrics=None,
            show_streaming=None,
        )

        assert isinstance(result, Success)

        # Verify the request was joined correctly
        call_kwargs = mock_handle_vibe.call_args.kwargs
        assert (
            call_kwargs["request"] == "update container image to nginx:1.21 in my-app"
        )

    @pytest.mark.asyncio
    @patch("vibectl.subcommands.patch_cmd.configure_output_flags")
    @patch("vibectl.subcommands.patch_cmd.configure_memory_flags")
    async def test_patch_vibe_no_request(
        self,
        mock_configure_memory: Mock,
        mock_configure_output: Mock,
        default_patch_output_flags: OutputFlags,
    ) -> None:
        """Test vibe patch command with no request - should return error."""
        mock_configure_output.return_value = default_patch_output_flags

        result = await run_patch_command(
            resource="vibe",
            args=(),
            show_raw_output=None,
            show_vibe=None,
            show_kubectl=None,
            model=None,
            freeze_memory=False,
            unfreeze_memory=False,
            show_metrics=None,
            show_streaming=None,
        )

        assert isinstance(result, Error)
        assert "Missing request after 'vibe' command" in result.error
        assert (
            'vibectl patch vibe "scale nginx deployment to 5 replicas"' in result.error
        )

        # Should still configure flags
        mock_configure_output.assert_called_once()
        mock_configure_memory.assert_called_once_with(False, False)

    @pytest.mark.asyncio
    @patch("vibectl.subcommands.patch_cmd.handle_vibe_request")
    @patch("vibectl.subcommands.patch_cmd.configure_output_flags")
    @patch("vibectl.subcommands.patch_cmd.configure_memory_flags")
    async def test_patch_vibe_error_propagation(
        self,
        mock_configure_memory: Mock,
        mock_configure_output: Mock,
        mock_handle_vibe: AsyncMock,
        default_patch_output_flags: OutputFlags,
    ) -> None:
        """Test that errors from handle_vibe_request are propagated."""
        mock_configure_output.return_value = default_patch_output_flags
        expected_error = Error(error="vibe processing failed")
        mock_handle_vibe.return_value = expected_error

        result = await run_patch_command(
            resource="vibe",
            args=("some patch request",),
            show_raw_output=None,
            show_vibe=None,
            show_kubectl=None,
            model=None,
            freeze_memory=False,
            unfreeze_memory=False,
            show_metrics=None,
            show_streaming=None,
        )

        assert isinstance(result, Error)
        assert result.error == "vibe processing failed"
        assert result == expected_error

    @pytest.mark.asyncio
    @patch("vibectl.subcommands.patch_cmd.logger")
    @patch("vibectl.subcommands.patch_cmd.handle_standard_command")
    @patch("vibectl.subcommands.patch_cmd.configure_output_flags")
    @patch("vibectl.subcommands.patch_cmd.configure_memory_flags")
    async def test_patch_standard_logging(
        self,
        mock_configure_memory: Mock,
        mock_configure_output: Mock,
        mock_handle_standard: AsyncMock,
        mock_logger: Mock,
        default_patch_output_flags: OutputFlags,
    ) -> None:
        """Test that appropriate logging calls are made for standard patch."""
        mock_configure_output.return_value = default_patch_output_flags
        mock_handle_standard.return_value = Success(data="patched")

        await run_patch_command(
            resource="deployment",
            args=("nginx", "-p", '{"spec":{"replicas":3}}'),
            show_raw_output=None,
            show_vibe=None,
            show_kubectl=None,
            model=None,
            freeze_memory=False,
            unfreeze_memory=False,
            show_metrics=None,
            show_streaming=None,
        )

        # Check logging calls
        mock_logger.info.assert_any_call(
            "Invoking 'patch' subcommand with resource: deployment, "
            "args: ('nginx', '-p', '{\"spec\":{\"replicas\":3}}')"
        )
        mock_logger.info.assert_any_call("Handling standard 'patch' command.")
        mock_logger.info.assert_any_call(
            "Completed 'patch' command for resource: deployment"
        )

    @pytest.mark.asyncio
    @patch("vibectl.subcommands.patch_cmd.logger")
    @patch("vibectl.subcommands.patch_cmd.handle_vibe_request")
    @patch("vibectl.subcommands.patch_cmd.configure_output_flags")
    @patch("vibectl.subcommands.patch_cmd.configure_memory_flags")
    async def test_patch_vibe_logging(
        self,
        mock_configure_memory: Mock,
        mock_configure_output: Mock,
        mock_handle_vibe: AsyncMock,
        mock_logger: Mock,
        default_patch_output_flags: OutputFlags,
    ) -> None:
        """Test that appropriate logging calls are made for vibe patch."""
        mock_configure_output.return_value = default_patch_output_flags
        mock_handle_vibe.return_value = Success(data="vibe completed")

        await run_patch_command(
            resource="vibe",
            args=("scale deployment to 5",),
            show_raw_output=None,
            show_vibe=None,
            show_kubectl=None,
            model=None,
            freeze_memory=False,
            unfreeze_memory=False,
            show_metrics=None,
            show_streaming=None,
        )

        # Check logging calls
        mock_logger.info.assert_any_call(
            "Invoking 'patch' subcommand with resource: vibe, "
            "args: ('scale deployment to 5',)"
        )
        mock_logger.info.assert_any_call(
            "Planning patch operation: scale deployment to 5"
        )
        mock_logger.info.assert_any_call("Completed 'patch' command for vibe request.")

    @pytest.mark.asyncio
    @patch("vibectl.subcommands.patch_cmd.handle_standard_command")
    @patch("vibectl.subcommands.patch_cmd.configure_output_flags")
    @patch("vibectl.subcommands.patch_cmd.configure_memory_flags")
    async def test_patch_json_patch_type(
        self,
        mock_configure_memory: Mock,
        mock_configure_output: Mock,
        mock_handle_standard: AsyncMock,
        default_patch_output_flags: OutputFlags,
    ) -> None:
        """Test patch command with JSON patch type."""
        mock_configure_output.return_value = default_patch_output_flags
        mock_handle_standard.return_value = Success(
            data="namespace/stuck-namespace patched"
        )

        result = await run_patch_command(
            resource="namespace",
            args=(
                "stuck-namespace",
                "--type",
                "json",
                "-p",
                '[{"op": "remove", "path": "/metadata/finalizers"}]',
            ),
            show_raw_output=None,
            show_vibe=None,
            show_kubectl=None,
            model=None,
            freeze_memory=False,
            unfreeze_memory=False,
            show_metrics=None,
            show_streaming=None,
        )

        assert isinstance(result, Success)
        mock_handle_standard.assert_called_once_with(
            command="patch",
            resource="namespace",
            args=(
                "stuck-namespace",
                "--type",
                "json",
                "-p",
                '[{"op": "remove", "path": "/metadata/finalizers"}]',
            ),
            output_flags=default_patch_output_flags,
            summary_prompt_func=patch_resource_prompt,
        )

    @pytest.mark.asyncio
    @patch("vibectl.subcommands.patch_cmd.handle_standard_command")
    @patch("vibectl.subcommands.patch_cmd.configure_output_flags")
    @patch("vibectl.subcommands.patch_cmd.configure_memory_flags")
    async def test_patch_empty_args(
        self,
        mock_configure_memory: Mock,
        mock_configure_output: Mock,
        mock_handle_standard: AsyncMock,
        default_patch_output_flags: OutputFlags,
    ) -> None:
        """Test patch command with empty args."""
        mock_configure_output.return_value = default_patch_output_flags
        mock_handle_standard.return_value = Success(data="pod/test patched")

        result = await run_patch_command(
            resource="pod",
            args=(),
            show_raw_output=None,
            show_vibe=None,
            show_kubectl=None,
            model=None,
            freeze_memory=False,
            unfreeze_memory=False,
            show_metrics=None,
            show_streaming=None,
        )

        assert isinstance(result, Success)
        mock_handle_standard.assert_called_once_with(
            command="patch",
            resource="pod",
            args=(),
            output_flags=default_patch_output_flags,
            summary_prompt_func=patch_resource_prompt,
        )

    @pytest.mark.asyncio
    @patch("vibectl.subcommands.patch_cmd.handle_standard_command")
    @patch("vibectl.subcommands.patch_cmd.configure_output_flags")
    @patch("vibectl.subcommands.patch_cmd.configure_memory_flags")
    async def test_patch_none_parameters(
        self,
        mock_configure_memory: Mock,
        mock_configure_output: Mock,
        mock_handle_standard: AsyncMock,
        default_patch_output_flags: OutputFlags,
    ) -> None:
        """Test that None values are handled properly in configuration."""
        mock_configure_output.return_value = default_patch_output_flags
        mock_handle_standard.return_value = Success(data="success")

        result = await run_patch_command(
            resource="service",
            args=("web-service",),
            show_raw_output=None,
            show_vibe=None,
            show_kubectl=None,
            model=None,
            freeze_memory=False,
            unfreeze_memory=False,
            show_metrics=None,
            show_streaming=None,
        )

        # Verify configuration was called with None values
        mock_configure_output.assert_called_once_with(
            show_raw_output=None,
            show_vibe=None,
            model=None,
            show_kubectl=None,
            show_metrics=None,
            show_streaming=None,
        )
        mock_configure_memory.assert_called_once_with(False, False)

        assert isinstance(result, Success)

    @pytest.mark.asyncio
    @patch("vibectl.subcommands.patch_cmd.handle_vibe_request")
    @patch("vibectl.subcommands.patch_cmd.configure_output_flags")
    @patch("vibectl.subcommands.patch_cmd.configure_memory_flags")
    async def test_patch_vibe_empty_string_request(
        self,
        mock_configure_memory: Mock,
        mock_configure_output: Mock,
        mock_handle_vibe: AsyncMock,
        default_patch_output_flags: OutputFlags,
    ) -> None:
        """Test vibe patch command with empty string request."""
        mock_configure_output.return_value = default_patch_output_flags
        mock_handle_vibe.return_value = Success(data="empty request handled")

        result = await run_patch_command(
            resource="vibe",
            args=("",),  # Empty string
            show_raw_output=None,
            show_vibe=None,
            show_kubectl=None,
            model=None,
            freeze_memory=False,
            unfreeze_memory=False,
            show_metrics=None,
            show_streaming=None,
        )

        # Should not return an error since args is not empty
        assert isinstance(result, Success)

        # Should call handle_vibe_request with empty string
        mock_handle_vibe.assert_called_once()
        call_kwargs = mock_handle_vibe.call_args.kwargs
        assert call_kwargs["request"] == ""
