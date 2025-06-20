"""Tests for disable functionality in setup_proxy_cmd.py - proxy disabling."""

from typing import Any
from unittest.mock import patch

import pytest
from asyncclick.testing import CliRunner

from vibectl.cli import cli
from vibectl.subcommands.setup_proxy_cmd import disable_proxy
from vibectl.types import Error, Success


class TestDisableProxy:
    """Test cases for disable_proxy function."""

    def test_disable_proxy_success(self, in_memory_config: Any) -> None:
        """Test successfully disabling proxy."""
        # Set up initial proxy configuration using profiles
        profile_config = {
            "server_url": "vibectl-server://test.com:443",
            "timeout_seconds": 60,
            "retry_attempts": 5,
        }
        in_memory_config.set_proxy_profile("test-profile", profile_config)
        in_memory_config.set_active_proxy_profile("test-profile")

        with patch(
            "vibectl.subcommands.setup_proxy_cmd.Config", return_value=in_memory_config
        ):
            result = disable_proxy()

            assert isinstance(result, Success)
            assert result.data == "Proxy disabled"
            # Verify proxy was disabled
            assert in_memory_config.get_active_proxy_profile() is None
            assert not in_memory_config.is_proxy_enabled()

    def test_disable_proxy_already_disabled(self, in_memory_config: Any) -> None:
        """Test disabling proxy when already disabled."""
        # Ensure proxy is disabled (no active profile)
        in_memory_config.set_active_proxy_profile(None)
        assert in_memory_config.get_active_proxy_profile() is None

        with patch(
            "vibectl.subcommands.setup_proxy_cmd.Config", return_value=in_memory_config
        ):
            result = disable_proxy()

            assert isinstance(result, Success)
            assert result.data == "Proxy is already disabled"

    def test_disable_proxy_exception_handling(self, in_memory_config: Any) -> None:
        """Test disable proxy handles exceptions."""
        # Set proxy enabled initially so it tries to disable
        profile_config = {"server_url": "vibectl-server://test.com:443"}
        in_memory_config.set_proxy_profile("test-profile", profile_config)
        in_memory_config.set_active_proxy_profile("test-profile")

        with (
            patch(
                "vibectl.subcommands.setup_proxy_cmd.Config",
                return_value=in_memory_config,
            ),
            patch.object(
                in_memory_config,
                "set_active_proxy_profile",
                side_effect=RuntimeError("Config error"),
            ),
        ):
            result = disable_proxy()

            assert isinstance(result, Error)
            assert "Failed to disable proxy: Config error" in result.error


class TestSetupProxyDisableCLI:
    """Test cases for setup-proxy disable CLI command."""

    @pytest.mark.asyncio
    async def test_disable_with_confirmation(self, in_memory_config: Any) -> None:
        """Test disable command with confirmation prompt."""
        # Set up proxy profile to enable proxy
        profile_config = {"server_url": "vibectl-server://test.com:443"}
        in_memory_config.set_proxy_profile("test-profile", profile_config)
        in_memory_config.set_active_proxy_profile("test-profile")

        with (
            patch(
                "vibectl.subcommands.setup_proxy_cmd.Config",
                return_value=in_memory_config,
            ),
            patch("vibectl.subcommands.setup_proxy_cmd.disable_proxy") as mock_disable,
            patch(
                "vibectl.subcommands.setup_proxy_cmd.show_proxy_status"
            ) as mock_status,
            patch(
                "vibectl.subcommands.setup_proxy_cmd.console_manager"
            ) as _mock_console,
            patch("asyncclick.confirm", return_value=True) as mock_confirm,
        ):
            mock_disable.return_value = Success(data="Proxy disabled")

            runner = CliRunner()
            result = await runner.invoke(
                cli,
                ["setup-proxy", "disable"],
                catch_exceptions=False,
            )

            assert result.exit_code == 0
            mock_confirm.assert_called_once()
            mock_disable.assert_called_once()
            mock_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_disable_with_auto_mode(self) -> None:
        """Test disable command with --mode auto (skip confirmation)."""
        with (
            patch("vibectl.subcommands.setup_proxy_cmd.disable_proxy") as mock_disable,
            patch(
                "vibectl.subcommands.setup_proxy_cmd.show_proxy_status"
            ) as mock_status,
            patch(
                "vibectl.subcommands.setup_proxy_cmd.console_manager"
            ) as _mock_console,
            patch("asyncclick.confirm") as mock_confirm,
        ):
            mock_disable.return_value = Success(data="Proxy disabled")

            runner = CliRunner()
            result = await runner.invoke(
                cli,
                ["setup-proxy", "disable", "--mode", "auto"],
                catch_exceptions=False,
            )

            assert result.exit_code == 0
            mock_confirm.assert_not_called()
            mock_disable.assert_called_once()
            mock_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_disable_already_disabled(self, in_memory_config: Any) -> None:
        """Test disable command when proxy is already disabled."""
        # Proxy is disabled by default (no active profile)
        in_memory_config.set_active_proxy_profile(None)
        assert in_memory_config.get_active_proxy_profile() is None

        with (
            patch(
                "vibectl.subcommands.setup_proxy_cmd.Config",
                return_value=in_memory_config,
            ),
            patch(
                "vibectl.subcommands.setup_proxy_cmd.console_manager"
            ) as _mock_console,
        ):
            runner = CliRunner()
            result = await runner.invoke(
                cli,
                ["setup-proxy", "disable", "--mode", "auto"],
                catch_exceptions=False,
            )

            assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_disable_confirmation_declined(self, in_memory_config: Any) -> None:
        """Test disable command when user declines confirmation."""
        # Set up proxy profile to enable proxy
        profile_config = {"server_url": "vibectl-server://test.com:443"}
        in_memory_config.set_proxy_profile("test-profile", profile_config)
        in_memory_config.set_active_proxy_profile("test-profile")

        with (
            patch(
                "vibectl.subcommands.setup_proxy_cmd.Config",
                return_value=in_memory_config,
            ),
            patch(
                "vibectl.subcommands.setup_proxy_cmd.console_manager"
            ) as _mock_console,
            patch("asyncclick.confirm", return_value=False) as mock_confirm,
        ):
            runner = CliRunner()
            result = await runner.invoke(
                cli,
                ["setup-proxy", "disable"],
                catch_exceptions=False,
            )

            assert result.exit_code == 0
            mock_confirm.assert_called_once()

    @pytest.mark.asyncio
    async def test_disable_error_handling(self) -> None:
        """Test disable command error handling."""
        with (
            patch("vibectl.subcommands.setup_proxy_cmd.disable_proxy") as mock_disable,
            patch(
                "vibectl.subcommands.setup_proxy_cmd.console_manager"
            ) as _mock_console,
        ):
            mock_disable.return_value = Error(error="Disable failed")

            runner = CliRunner()
            result = await runner.invoke(
                cli,
                ["setup-proxy", "disable", "--mode", "auto"],
                catch_exceptions=False,
            )

            # CliRunner catches sys.exit and converts to exit_code
            assert result.exit_code == 1

    @pytest.mark.asyncio
    async def test_disable_exception_handling(self) -> None:
        """Test disable command handles exceptions."""
        with (
            patch(
                "vibectl.subcommands.setup_proxy_cmd.console_manager"
            ) as _mock_console,
            patch(
                "vibectl.subcommands.setup_proxy_cmd.handle_exception"
            ) as mock_handle,
        ):
            _mock_console.print_note.side_effect = RuntimeError("Console error")

            runner = CliRunner()
            _result = await runner.invoke(
                cli,
                ["setup-proxy", "disable", "--mode", "auto"],
                catch_exceptions=True,
            )

            mock_handle.assert_called_once()
