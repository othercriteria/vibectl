"""Tests for the 'version' subcommand logic in vibectl/subcommands/version_cmd.py."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from vibectl.prompts.version import version_plan_prompt, version_prompt
from vibectl.subcommands.version_cmd import run_version_command
from vibectl.types import Error, MetricsDisplayMode, OutputFlags, Success


@pytest.fixture
def default_version_output_flags() -> OutputFlags:
    """Default OutputFlags for version command tests."""
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


class TestRunVersionCommand:
    """Test cases for the run_version_command function."""

    @pytest.mark.asyncio
    @patch("vibectl.subcommands.version_cmd.handle_standard_command")
    @patch("vibectl.subcommands.version_cmd.configure_output_flags")
    @patch("vibectl.subcommands.version_cmd.configure_memory_flags")
    async def test_version_standard_basic(
        self,
        mock_configure_memory: Mock,
        mock_configure_output: Mock,
        mock_handle_standard: AsyncMock,
        default_version_output_flags: OutputFlags,
    ) -> None:
        """Test basic version command functionality."""
        mock_configure_output.return_value = default_version_output_flags
        mock_handle_standard.return_value = Success(
            data='{"clientVersion": {"gitVersion": "v1.2.3"}}'
        )

        result = await run_version_command(
            args=(),
            show_vibe=True,
            freeze_memory=False,
            unfreeze_memory=False,
        )

        assert isinstance(result, Success)
        assert result.data == '{"clientVersion": {"gitVersion": "v1.2.3"}}'

        mock_configure_output.assert_called_once_with(
            show_vibe=True,
        )
        mock_configure_memory.assert_called_once_with(False, False)
        mock_handle_standard.assert_called_once_with(
            command="version",
            resource="",
            args=("--output=json",),
            output_flags=default_version_output_flags,
            summary_prompt_func=version_prompt,
        )

    @pytest.mark.asyncio
    @patch("vibectl.subcommands.version_cmd.handle_standard_command")
    @patch("vibectl.subcommands.version_cmd.configure_output_flags")
    @patch("vibectl.subcommands.version_cmd.configure_memory_flags")
    async def test_version_standard_with_existing_output_json(
        self,
        mock_configure_memory: Mock,
        mock_configure_output: Mock,
        mock_handle_standard: AsyncMock,
        default_version_output_flags: OutputFlags,
    ) -> None:
        """Test version command with --output=json already present."""
        mock_configure_output.return_value = default_version_output_flags
        mock_handle_standard.return_value = Success(
            data='{"clientVersion": {"gitVersion": "v1.2.3"}}'
        )

        result = await run_version_command(
            args=("--output=json", "--client"),
            show_vibe=False,
            freeze_memory=True,
            unfreeze_memory=False,
        )

        assert isinstance(result, Success)
        assert result.data == '{"clientVersion": {"gitVersion": "v1.2.3"}}'

        mock_configure_output.assert_called_once_with(
            show_vibe=False,
        )
        mock_configure_memory.assert_called_once_with(True, False)
        mock_handle_standard.assert_called_once_with(
            command="version",
            resource="",
            args=("--output=json", "--client"),
            output_flags=default_version_output_flags,
            summary_prompt_func=version_prompt,
        )

    @pytest.mark.asyncio
    @patch("vibectl.subcommands.version_cmd.handle_standard_command")
    @patch("vibectl.subcommands.version_cmd.configure_output_flags")
    @patch("vibectl.subcommands.version_cmd.configure_memory_flags")
    async def test_version_standard_error_propagation(
        self,
        mock_configure_memory: Mock,
        mock_configure_output: Mock,
        mock_handle_standard: AsyncMock,
        default_version_output_flags: OutputFlags,
    ) -> None:
        """Test that errors from handle_standard_command are propagated."""
        mock_configure_output.return_value = default_version_output_flags
        expected_error = Error(error="kubectl version failed")
        mock_handle_standard.return_value = expected_error

        result = await run_version_command(
            args=(),
            show_vibe=None,
            freeze_memory=False,
            unfreeze_memory=False,
        )

        assert isinstance(result, Error)
        assert result.error == "kubectl version failed"
        assert result == expected_error

    @pytest.mark.asyncio
    @patch("vibectl.subcommands.version_cmd.handle_vibe_request")
    @patch("vibectl.subcommands.version_cmd.configure_output_flags")
    @patch("vibectl.subcommands.version_cmd.configure_memory_flags")
    async def test_version_vibe_basic(
        self,
        mock_configure_memory: Mock,
        mock_configure_output: Mock,
        mock_handle_vibe: AsyncMock,
        default_version_output_flags: OutputFlags,
    ) -> None:
        """Test basic vibe version command functionality."""
        mock_configure_output.return_value = default_version_output_flags
        mock_handle_vibe.return_value = Success(data="version vibe completed")

        result = await run_version_command(
            args=("vibe", "what version of kubernetes am I running?"),
            show_vibe=True,
            freeze_memory=False,
            unfreeze_memory=True,
        )

        assert isinstance(result, Success)
        assert result.data == "version vibe completed"

        mock_configure_output.assert_called_once_with(
            show_vibe=True,
        )
        mock_configure_memory.assert_called_once_with(False, True)
        mock_handle_vibe.assert_called_once_with(
            request="what version of kubernetes am I running?",
            command="version",
            plan_prompt_func=version_plan_prompt,
            output_flags=default_version_output_flags,
            summary_prompt_func=version_prompt,
        )

    @pytest.mark.asyncio
    @patch("vibectl.subcommands.version_cmd.handle_vibe_request")
    @patch("vibectl.subcommands.version_cmd.configure_output_flags")
    @patch("vibectl.subcommands.version_cmd.configure_memory_flags")
    async def test_version_vibe_multi_word_request(
        self,
        mock_configure_memory: Mock,
        mock_configure_output: Mock,
        mock_handle_vibe: AsyncMock,
        default_version_output_flags: OutputFlags,
    ) -> None:
        """Test vibe version command with multi-word request."""
        mock_configure_output.return_value = default_version_output_flags
        mock_handle_vibe.return_value = Success(
            data="vibe version multi-word completed"
        )

        result = await run_version_command(
            args=("vibe", "check", "kubernetes", "version", "compatibility"),
            show_vibe=False,
            freeze_memory=True,
            unfreeze_memory=False,
        )

        assert isinstance(result, Success)
        assert result.data == "vibe version multi-word completed"

        mock_handle_vibe.assert_called_once_with(
            request="check kubernetes version compatibility",
            command="version",
            plan_prompt_func=version_plan_prompt,
            output_flags=default_version_output_flags,
            summary_prompt_func=version_prompt,
        )

    @pytest.mark.asyncio
    @patch("vibectl.subcommands.version_cmd.configure_output_flags")
    @patch("vibectl.subcommands.version_cmd.configure_memory_flags")
    async def test_version_vibe_no_request(
        self,
        mock_configure_memory: Mock,
        mock_configure_output: Mock,
        default_version_output_flags: OutputFlags,
    ) -> None:
        """Test vibe version command with no request returns an error."""
        mock_configure_output.return_value = default_version_output_flags

        result = await run_version_command(
            args=("vibe",),
            show_vibe=True,
            freeze_memory=False,
            unfreeze_memory=False,
        )

        assert isinstance(result, Error)
        assert "Missing request after 'vibe' command" in result.error

    @pytest.mark.asyncio
    @patch("vibectl.subcommands.version_cmd.handle_vibe_request")
    @patch("vibectl.subcommands.version_cmd.configure_output_flags")
    @patch("vibectl.subcommands.version_cmd.configure_memory_flags")
    async def test_version_vibe_error_propagation(
        self,
        mock_configure_memory: Mock,
        mock_configure_output: Mock,
        mock_handle_vibe: AsyncMock,
        default_version_output_flags: OutputFlags,
    ) -> None:
        """Test that errors from handle_vibe_request are propagated."""
        mock_configure_output.return_value = default_version_output_flags
        expected_error = Error(error="vibe request failed")
        mock_handle_vibe.return_value = expected_error

        result = await run_version_command(
            args=("vibe", "check kubernetes version"),
            show_vibe=True,
            freeze_memory=False,
            unfreeze_memory=False,
        )

        assert isinstance(result, Error)
        assert result.error == "vibe request failed"
        assert result == expected_error

    @pytest.mark.asyncio
    @patch("vibectl.subcommands.version_cmd.logger")
    @patch("vibectl.subcommands.version_cmd.handle_standard_command")
    @patch("vibectl.subcommands.version_cmd.configure_output_flags")
    @patch("vibectl.subcommands.version_cmd.configure_memory_flags")
    async def test_version_standard_logging(
        self,
        mock_configure_memory: Mock,
        mock_configure_output: Mock,
        mock_handle_standard: AsyncMock,
        mock_logger: Mock,
        default_version_output_flags: OutputFlags,
    ) -> None:
        """Test that version standard command logs appropriately."""
        mock_configure_output.return_value = default_version_output_flags
        mock_handle_standard.return_value = Success(data="version output")

        result = await run_version_command(
            args=(),
            show_vibe=True,
            freeze_memory=False,
            unfreeze_memory=False,
        )

        assert isinstance(result, Success)
        mock_logger.info.assert_any_call("Invoking 'version' subcommand with args: ()")
        mock_logger.info.assert_any_call("Handling standard 'version' command.")
        mock_logger.info.assert_any_call("Completed 'version' command.")

    @pytest.mark.asyncio
    @patch("vibectl.subcommands.version_cmd.logger")
    @patch("vibectl.subcommands.version_cmd.handle_vibe_request")
    @patch("vibectl.subcommands.version_cmd.configure_output_flags")
    @patch("vibectl.subcommands.version_cmd.configure_memory_flags")
    async def test_version_vibe_logging(
        self,
        mock_configure_memory: Mock,
        mock_configure_output: Mock,
        mock_handle_vibe: AsyncMock,
        mock_logger: Mock,
        default_version_output_flags: OutputFlags,
    ) -> None:
        """Test that version vibe command logs appropriately."""
        mock_configure_output.return_value = default_version_output_flags
        mock_handle_vibe.return_value = Success(data="vibe output")

        result = await run_version_command(
            args=("vibe", "test request"),
            show_vibe=True,
            freeze_memory=False,
            unfreeze_memory=False,
        )

        assert isinstance(result, Success)
        mock_logger.info.assert_any_call(
            "Invoking 'version' subcommand with args: ('vibe', 'test request')"
        )
        mock_logger.info.assert_any_call("Planning version query: test request")
        mock_logger.info.assert_any_call(
            "Completed 'version' command for vibe request."
        )

    @pytest.mark.asyncio
    @patch("vibectl.subcommands.version_cmd.handle_standard_command")
    @patch("vibectl.subcommands.version_cmd.configure_output_flags")
    @patch("vibectl.subcommands.version_cmd.configure_memory_flags")
    async def test_version_none_parameters(
        self,
        mock_configure_memory: Mock,
        mock_configure_output: Mock,
        mock_handle_standard: AsyncMock,
        default_version_output_flags: OutputFlags,
    ) -> None:
        """Test version command with None parameters."""
        mock_configure_output.return_value = default_version_output_flags
        mock_handle_standard.return_value = Success(data="version output")

        result = await run_version_command(
            args=(),
            show_vibe=None,
            freeze_memory=False,
            unfreeze_memory=False,
        )

        assert isinstance(result, Success)
        assert result.data == "version output"

        mock_configure_output.assert_called_once_with(
            show_vibe=None,
        )
