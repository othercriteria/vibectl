"""Tests for test command functionality in setup_proxy_cmd.py - connection testing."""

from typing import Any
from unittest.mock import patch

import pytest
from asyncclick.testing import CliRunner

from vibectl.cli import cli
from vibectl.types import Error, Success


class TestSetupProxyTestCLI:
    """Test cases for setup-proxy test CLI command."""

    @pytest.mark.asyncio
    async def test_test_with_url_success(self) -> None:
        """Test proxy connection test with provided URL."""
        mock_server_info = {
            "server_name": "Test Server",
            "version": "1.0.0",
            "supported_models": ["model1"],
        }

        with (
            patch(
                "vibectl.subcommands.setup_proxy_cmd.check_proxy_connection"
            ) as mock_test,
            patch(
                "vibectl.subcommands.setup_proxy_cmd.console_manager"
            ) as _mock_console,
        ):
            mock_test.return_value = Success(data=mock_server_info)

            runner = CliRunner()
            result = await runner.invoke(
                cli,
                ["setup-proxy", "test", "vibectl-server://test.com:443"],
                catch_exceptions=False,
            )

            assert result.exit_code == 0
            mock_test.assert_called_once_with(
                "vibectl-server://test.com:443", timeout_seconds=10, jwt_path=None
            )

    @pytest.mark.asyncio
    async def test_test_with_configured_url(self, in_memory_config: Any) -> None:
        """Test proxy connection test with configured URL."""
        in_memory_config.set("proxy.server_url", "vibectl-server://configured.com:443")

        with (
            patch(
                "vibectl.subcommands.setup_proxy_cmd.Config",
                return_value=in_memory_config,
            ),
            patch(
                "vibectl.subcommands.setup_proxy_cmd.check_proxy_connection"
            ) as mock_test,
            patch(
                "vibectl.subcommands.setup_proxy_cmd.console_manager"
            ) as _mock_console,
        ):
            mock_test.return_value = Success(data={})

            runner = CliRunner()
            result = await runner.invoke(
                cli,
                ["setup-proxy", "test"],
                catch_exceptions=False,
            )

            assert result.exit_code == 0
            mock_test.assert_called_once_with(
                "vibectl-server://configured.com:443", timeout_seconds=10, jwt_path=None
            )

    @pytest.mark.asyncio
    async def test_test_no_url_configured(self, in_memory_config: Any) -> None:
        """Test proxy connection test when no URL is configured."""
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
                ["setup-proxy", "test"],
                catch_exceptions=False,
            )

            # CliRunner catches sys.exit and converts to exit_code
            assert result.exit_code == 1

    @pytest.mark.asyncio
    async def test_test_with_timeout(self) -> None:
        """Test proxy connection test with custom timeout."""
        with (
            patch(
                "vibectl.subcommands.setup_proxy_cmd.check_proxy_connection"
            ) as mock_test,
            patch(
                "vibectl.subcommands.setup_proxy_cmd.console_manager"
            ) as _mock_console,
        ):
            mock_test.return_value = Success(data={})

            runner = CliRunner()
            result = await runner.invoke(
                cli,
                [
                    "setup-proxy",
                    "test",
                    "vibectl-server://test.com:443",
                    "--timeout",
                    "30",
                ],
                catch_exceptions=False,
            )

            assert result.exit_code == 0
            mock_test.assert_called_once_with(
                "vibectl-server://test.com:443", timeout_seconds=30, jwt_path=None
            )

    @pytest.mark.asyncio
    async def test_test_connection_failed(self) -> None:
        """Test proxy connection test when connection fails."""
        with (
            patch(
                "vibectl.subcommands.setup_proxy_cmd.check_proxy_connection"
            ) as mock_test,
            patch(
                "vibectl.subcommands.setup_proxy_cmd.console_manager"
            ) as _mock_console,
        ):
            mock_test.return_value = Error(error="Connection failed")

            runner = CliRunner()
            result = await runner.invoke(
                cli,
                ["setup-proxy", "test", "vibectl-server://bad.com:443"],
                catch_exceptions=False,
            )

            # CliRunner catches sys.exit and converts to exit_code
            assert result.exit_code == 1

    @pytest.mark.asyncio
    async def test_test_exception_handling(self) -> None:
        """Test test command handles exceptions."""
        with (
            patch(
                "vibectl.subcommands.setup_proxy_cmd.console_manager"
            ) as _mock_console,
            patch(
                "vibectl.subcommands.setup_proxy_cmd.handle_exception"
            ) as mock_handle,
        ):
            _mock_console.print.side_effect = RuntimeError("Console error")

            runner = CliRunner()
            _result = await runner.invoke(
                cli,
                ["setup-proxy", "test", "vibectl-server://test.com:443"],
                catch_exceptions=True,
            )

            mock_handle.assert_called_once()
