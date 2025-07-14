"""Tests for status functionality in setup_proxy_cmd.py - proxy status display."""

import os
import tempfile
from typing import Any
from unittest.mock import Mock, patch

import pytest
from asyncclick.testing import CliRunner

from vibectl.cli import cli
from vibectl.config import Config
from vibectl.subcommands.setup_proxy_cmd import show_proxy_status


class TestShowProxyStatus:
    """Test cases for show_proxy_status function."""

    def test_show_status_enabled(
        self, in_memory_config: Any, test_console: Any
    ) -> None:
        """Test showing status when proxy is enabled."""
        # Set up profile-based proxy configuration
        profile_config = {
            "server_url": "vibectl-server://test.com:443",
            "timeout_seconds": 45,
            "retry_attempts": 4,
        }
        in_memory_config.set_proxy_profile("test-profile", profile_config)
        in_memory_config.set_active_proxy_profile("test-profile")

        with (
            patch(
                "vibectl.subcommands.setup_proxy_cmd.Config",
                return_value=in_memory_config,
            ),
            patch("vibectl.subcommands.setup_proxy_cmd.console_manager", test_console),
        ):
            show_proxy_status()

            # Verify output contains expected information
            output = test_console.console.export_text()
            assert "Proxy Configuration Status" in output
            assert "True" in output
            assert "vibectl-server://test.com:443" in output

    def test_show_status_disabled(
        self, in_memory_config: Any, test_console: Any
    ) -> None:
        """Test showing status when proxy is disabled."""
        # No active profile = proxy disabled
        in_memory_config.set_active_proxy_profile(None)

        with (
            patch(
                "vibectl.subcommands.setup_proxy_cmd.Config",
                return_value=in_memory_config,
            ),
            patch("vibectl.subcommands.setup_proxy_cmd.console_manager", test_console),
        ):
            show_proxy_status()

            # Verify output shows disabled status
            output = test_console.console.export_text()
            assert "Proxy Configuration Status" in output
            assert "False" in output
            assert "Not configured" in output

    def test_show_status_exception_handling(self) -> None:
        """Test exception handling in show_proxy_status - lines 476-477."""
        with (
            patch.object(Config, "__init__", side_effect=Exception("Config error")),
            patch(
                "vibectl.subcommands.setup_proxy_cmd.handle_exception"
            ) as mock_handle,
        ):
            show_proxy_status()
            mock_handle.assert_called_once()

    def test_show_status_env_ca_bundle_exists(
        self, in_memory_config: Any, test_console: Any
    ) -> None:
        """Test status with environment CA bundle that exists."""
        # Set up profile-based proxy configuration
        profile_config = {"server_url": "vibectl-server://test.com:443"}
        in_memory_config.set_proxy_profile("test-profile", profile_config)
        in_memory_config.set_active_proxy_profile("test-profile")

        # Create a temporary CA bundle file
        with tempfile.NamedTemporaryFile(suffix=".crt", delete=False) as ca_file:
            ca_file.write(b"dummy ca bundle content")
            ca_bundle_path = ca_file.name

        try:
            with (
                patch(
                    "vibectl.subcommands.setup_proxy_cmd.Config",
                    return_value=in_memory_config,
                ),
                patch(
                    "vibectl.subcommands.setup_proxy_cmd.console_manager", test_console
                ),
                patch("os.environ.get") as mock_env,
            ):
                mock_env.return_value = ca_bundle_path
                show_proxy_status()

                output = test_console.console.export_text()
                assert "CA Bundle Path" in output
                assert "(from environment)" in output
                assert "✓ Found" in output
        finally:
            os.unlink(ca_bundle_path)

    def test_show_status_env_ca_bundle_missing(
        self, in_memory_config: Any, test_console: Any
    ) -> None:
        """Test status with environment CA bundle that doesn't exist."""
        # Set up profile-based proxy configuration
        profile_config = {"server_url": "vibectl-server://test.com:443"}
        in_memory_config.set_proxy_profile("test-profile", profile_config)
        in_memory_config.set_active_proxy_profile("test-profile")

        non_existent_path = "/path/to/nonexistent/ca-bundle.crt"

        with (
            patch(
                "vibectl.subcommands.setup_proxy_cmd.Config",
                return_value=in_memory_config,
            ),
            patch("vibectl.subcommands.setup_proxy_cmd.console_manager", test_console),
            patch("os.environ.get") as mock_env,
        ):
            mock_env.return_value = non_existent_path
            show_proxy_status()

            output = test_console.console.export_text()
            assert "CA Bundle Path" in output
            assert "(from environment)" in output
            assert "❌ Missing" in output

    def test_show_status_config_ca_bundle_exists(
        self, in_memory_config: Any, test_console: Any
    ) -> None:
        """Test status with config CA bundle that exists - covers lines 416-418."""
        # Create a temporary CA bundle file
        with tempfile.NamedTemporaryFile(suffix=".crt", delete=False) as ca_file:
            ca_file.write(b"dummy ca bundle content")
            ca_bundle_path = ca_file.name

        # Set up profile-based proxy configuration
        profile_config = {
            "server_url": "vibectl-server://test.com:443",
            "ca_bundle_path": ca_bundle_path,
        }
        in_memory_config.set_proxy_profile("test-profile", profile_config)
        in_memory_config.set_active_proxy_profile("test-profile")

        try:
            with (
                patch(
                    "vibectl.subcommands.setup_proxy_cmd.Config",
                    return_value=in_memory_config,
                ),
                patch(
                    "vibectl.subcommands.setup_proxy_cmd.console_manager", test_console
                ),
                patch(
                    "vibectl.subcommands.setup_proxy_cmd.os.environ.get"
                ) as mock_env_get,
            ):
                # Mock only the specific environment variable calls we care about
                def env_get_side_effect(key: str, default: Any = None) -> Any:
                    if key == "VIBECTL_CA_BUNDLE":
                        return None  # No env CA bundle
                    elif key == "VIBECTL_JWT_TOKEN":
                        return None
                    # For any other environment variable requests, return the default
                    return default

                mock_env_get.side_effect = env_get_side_effect
                show_proxy_status()

                output = test_console.console.export_text()
                assert "CA Bundle Path" in output
                assert "(from profile)" in output
                assert "✓ Found" in output
        finally:
            os.unlink(ca_bundle_path)

    def test_show_status_config_ca_bundle_missing(
        self, in_memory_config: Any, test_console: Any
    ) -> None:
        """Test status with config CA bundle that doesn't exist."""
        non_existent_path = "/path/to/nonexistent/ca-bundle.crt"

        # Set up profile-based proxy configuration
        profile_config = {
            "server_url": "vibectl-server://test.com:443",
            "ca_bundle_path": non_existent_path,
        }
        in_memory_config.set_proxy_profile("test-profile", profile_config)
        in_memory_config.set_active_proxy_profile("test-profile")

        with (
            patch(
                "vibectl.subcommands.setup_proxy_cmd.Config",
                return_value=in_memory_config,
            ),
            patch("vibectl.subcommands.setup_proxy_cmd.console_manager", test_console),
            patch("vibectl.subcommands.setup_proxy_cmd.os.environ.get") as mock_env_get,
        ):
            # Mock only the specific environment variable calls we care about
            def env_get_side_effect(key: str, default: Any = None) -> Any:
                if key == "VIBECTL_CA_BUNDLE":
                    return None  # No env CA bundle
                elif key == "VIBECTL_JWT_TOKEN":
                    return None
                # For any other environment variable requests, return the default
                return default

            mock_env_get.side_effect = env_get_side_effect
            show_proxy_status()

            output = test_console.console.export_text()
            assert "CA Bundle Path" in output
            assert "(from profile)" in output
            assert "❌ Missing" in output

    def test_show_status_env_jwt_token(
        self, in_memory_config: Any, test_console: Any
    ) -> None:
        """Test status with environment JWT token - covers line 431."""
        # Set up profile-based proxy configuration
        profile_config = {"server_url": "vibectl-server://test.com:443"}
        in_memory_config.set_proxy_profile("test-profile", profile_config)
        in_memory_config.set_active_proxy_profile("test-profile")

        with (
            patch(
                "vibectl.subcommands.setup_proxy_cmd.Config",
                return_value=in_memory_config,
            ),
            patch("vibectl.subcommands.setup_proxy_cmd.console_manager", test_console),
            patch("os.environ.get") as mock_env,
        ):

            def env_get_side_effect(key: str, default: Any = None) -> Any:
                if key == "VIBECTL_JWT_TOKEN":
                    return "fake-jwt-token"
                elif key == "VIBECTL_CA_BUNDLE":
                    return None
                return default

            mock_env.side_effect = env_get_side_effect
            show_proxy_status()

            output = test_console.console.export_text()
            assert "JWT Token" in output
            assert "*** (from environment)" in output

    def test_show_status_config_jwt_path_exists(
        self, in_memory_config: Any, test_console: Any
    ) -> None:
        """Test status with config JWT path that exists."""
        # Create a temporary JWT file
        with tempfile.NamedTemporaryFile(suffix=".jwt", delete=False) as jwt_file:
            jwt_file.write(b"fake-jwt-token")
            jwt_path = jwt_file.name

        # Set up profile-based proxy configuration
        profile_config = {
            "server_url": "vibectl-server://test.com:443",
            "jwt_path": jwt_path,
        }
        in_memory_config.set_proxy_profile("test-profile", profile_config)
        in_memory_config.set_active_proxy_profile("test-profile")

        try:
            with (
                patch(
                    "vibectl.subcommands.setup_proxy_cmd.Config",
                    return_value=in_memory_config,
                ),
                patch(
                    "vibectl.subcommands.setup_proxy_cmd.console_manager", test_console
                ),
                patch("os.environ.get", new_callable=Mock) as mock_env,
            ):

                def env_get_side_effect(key: str, default: Any = None) -> Any:
                    if key == "VIBECTL_JWT_TOKEN" or key == "VIBECTL_CA_BUNDLE":
                        return None
                    return default

                mock_env.side_effect = env_get_side_effect
                show_proxy_status()

                output = test_console.console.export_text()
                assert "JWT Token Path" in output
                assert "(from profile)" in output
                assert "✓ Found" in output
        finally:
            os.unlink(jwt_path)

    def test_show_status_config_jwt_path_missing(
        self, in_memory_config: Any, test_console: Any
    ) -> None:
        """Test status with config JWT path that doesn't exist."""
        non_existent_path = "/path/to/nonexistent/token.jwt"

        # Set up profile-based proxy configuration
        profile_config = {
            "server_url": "vibectl-server://test.com:443",
            "jwt_path": non_existent_path,
        }
        in_memory_config.set_proxy_profile("test-profile", profile_config)
        in_memory_config.set_active_proxy_profile("test-profile")

        with (
            patch(
                "vibectl.subcommands.setup_proxy_cmd.Config",
                return_value=in_memory_config,
            ),
            patch("vibectl.subcommands.setup_proxy_cmd.console_manager", test_console),
            patch("os.environ.get") as mock_env,
        ):

            def env_get_side_effect(key: str, default: Any = None) -> Any:
                if key == "VIBECTL_JWT_TOKEN" or key == "VIBECTL_CA_BUNDLE":
                    return None
                return default

            mock_env.side_effect = env_get_side_effect
            show_proxy_status()

            output = test_console.console.export_text()
            assert "JWT Token Path" in output
            assert "(from profile)" in output
            assert "❌ Missing" in output

    def test_show_status_embedded_jwt_token(
        self, in_memory_config: Any, test_console: Any
    ) -> None:
        """Test status with embedded JWT token in URL."""
        jwt_url = "vibectl-server://fake-jwt-token@test.com:443"

        # Set up profile-based proxy configuration
        profile_config = {"server_url": jwt_url}
        in_memory_config.set_proxy_profile("test-profile", profile_config)
        in_memory_config.set_active_proxy_profile("test-profile")

        # Mock parse_proxy_url to return a config with JWT token
        mock_proxy_config = Mock()
        mock_proxy_config.jwt_token = "fake-jwt-token"

        with (
            patch(
                "vibectl.subcommands.setup_proxy_cmd.Config",
                return_value=in_memory_config,
            ),
            patch("vibectl.subcommands.setup_proxy_cmd.console_manager", test_console),
            patch("vibectl.subcommands.setup_proxy_cmd.os.environ.get") as mock_env_get,
            patch(
                "vibectl.subcommands.setup_proxy_cmd.parse_proxy_url",
                return_value=mock_proxy_config,
            ),
        ):
            # Mock only the specific environment variable calls we care about
            def env_get_side_effect(key: str, default: Any = None) -> Any:
                if key == "VIBECTL_JWT_TOKEN" or key == "VIBECTL_CA_BUNDLE":
                    return None
                # For any other environment variable requests, return the default
                return default

            mock_env_get.side_effect = env_get_side_effect
            show_proxy_status()

            output = test_console.console.export_text()
            assert "JWT Token" in output
            assert "*** (embedded in URL)" in output

    def test_show_status_tls_configuration_messages(
        self, in_memory_config: Any, test_console: Any, capsys: Any
    ) -> None:
        """Test TLS configuration messages."""
        # Set up profile-based proxy configuration
        profile_config = {"server_url": "vibectl-server-insecure://test.com:443"}
        in_memory_config.set_proxy_profile("test-profile", profile_config)
        in_memory_config.set_active_proxy_profile("test-profile")

        with (
            patch(
                "vibectl.subcommands.setup_proxy_cmd.Config",
                return_value=in_memory_config,
            ),
            patch("vibectl.subcommands.setup_proxy_cmd.console_manager", test_console),
            patch("vibectl.subcommands.setup_proxy_cmd.os.environ.get") as mock_env_get,
        ):
            # Mock only the specific environment variable calls we care about
            def env_get_side_effect(key: str, default: Any = None) -> Any:
                if key == "VIBECTL_CA_BUNDLE" or key == "VIBECTL_JWT_TOKEN":
                    return None
                # For any other environment variable requests, return the default
                return default

            mock_env_get.side_effect = env_get_side_effect
            show_proxy_status()

            # Check that warning about insecure connection is shown in the
            # captured output
            captured = capsys.readouterr()
            assert "Using insecure connection (no TLS)" in captured.err
            assert "Only use for local development" in captured.err


class TestSetupProxyStatusCLI:
    """Test cases for setup-proxy status CLI command."""

    @pytest.mark.asyncio
    async def test_status_command(self) -> None:
        """Test proxy status command."""
        with patch(
            "vibectl.subcommands.setup_proxy_cmd.show_proxy_status"
        ) as mock_status:
            runner = CliRunner()
            result = await runner.invoke(
                cli,
                ["setup-proxy", "status"],
                catch_exceptions=False,
            )

            assert result.exit_code == 0
            mock_status.assert_called_once()
