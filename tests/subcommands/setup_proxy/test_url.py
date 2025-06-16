"""Tests for URL command functionality in setup_proxy_cmd.py - URL building."""

from unittest.mock import patch

import pytest
from asyncclick.testing import CliRunner

from vibectl.cli import cli


class TestSetupProxyUrlCLI:
    """Test cases for setup-proxy url CLI command."""

    @pytest.mark.asyncio
    async def test_build_url_basic(self) -> None:
        """Test basic URL building."""
        with (
            patch("vibectl.subcommands.setup_proxy_cmd.build_proxy_url") as mock_build,
            patch(
                "vibectl.subcommands.setup_proxy_cmd.console_manager"
            ) as _mock_console,
        ):
            mock_build.return_value = "vibectl-server://test.com:443"

            runner = CliRunner()
            result = await runner.invoke(
                cli,
                ["setup-proxy", "url", "test.com", "443"],
                catch_exceptions=False,
            )

            assert result.exit_code == 0
            mock_build.assert_called_once_with("test.com", 443, None)

    @pytest.mark.asyncio
    async def test_build_url_with_jwt_token(self) -> None:
        """Test URL building with JWT token."""
        with (
            patch("vibectl.subcommands.setup_proxy_cmd.build_proxy_url") as mock_build,
            patch(
                "vibectl.subcommands.setup_proxy_cmd.console_manager"
            ) as _mock_console,
        ):
            mock_build.return_value = "vibectl-server://token123@test.com:443"

            runner = CliRunner()
            result = await runner.invoke(
                cli,
                ["setup-proxy", "url", "test.com", "443", "--jwt-token", "token123"],
                catch_exceptions=False,
            )

            assert result.exit_code == 0
            mock_build.assert_called_once_with("test.com", 443, "token123")

    @pytest.mark.asyncio
    async def test_build_url_insecure(self) -> None:
        """Test URL building with insecure flag."""
        with (
            patch("vibectl.subcommands.setup_proxy_cmd.build_proxy_url") as mock_build,
            patch(
                "vibectl.subcommands.setup_proxy_cmd.console_manager"
            ) as _mock_console,
        ):
            mock_build.return_value = "vibectl-server://test.com:8080"

            runner = CliRunner()
            result = await runner.invoke(
                cli,
                ["setup-proxy", "url", "test.com", "8080", "--insecure"],
                catch_exceptions=False,
            )

            assert result.exit_code == 0
            mock_build.assert_called_once_with("test.com", 8080, None)
            # Check that output was modified for insecure
            _mock_console.print.assert_called()

    @pytest.mark.asyncio
    async def test_build_url_exception_handling(self) -> None:
        """Test URL building handles exceptions."""
        with (
            patch("vibectl.subcommands.setup_proxy_cmd.build_proxy_url") as mock_build,
            patch(
                "vibectl.subcommands.setup_proxy_cmd.handle_exception"
            ) as mock_handle,
        ):
            mock_build.side_effect = RuntimeError("Build error")

            runner = CliRunner()
            _result = await runner.invoke(
                cli,
                ["setup-proxy", "url", "test.com", "443"],
                catch_exceptions=True,
            )

            mock_handle.assert_called_once()
