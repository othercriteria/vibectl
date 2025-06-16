"""Tests for configure command in setup_proxy_cmd.py - configuration management."""

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest
from asyncclick.testing import CliRunner

from vibectl.cli import cli
from vibectl.config import Config
from vibectl.subcommands.setup_proxy_cmd import configure_proxy_settings
from vibectl.types import Error, Success


class TestConfigureProxySettings:
    """Test cases for configure_proxy_settings function."""

    def test_configure_valid_url(self, in_memory_config: Any) -> None:
        """Test configuring proxy with valid URL."""
        with patch(
            "vibectl.subcommands.setup_proxy_cmd.Config",
            return_value=in_memory_config,
        ):
            result = configure_proxy_settings(
                "vibectl-server://myserver.com:443",
            )

            assert isinstance(result, Success)
            assert "✓ Proxy configured successfully" in result.message

            # Verify configuration was saved
            assert in_memory_config.get("proxy.enabled") is True
            assert (
                in_memory_config.get("proxy.server_url")
                == "vibectl-server://myserver.com:443"
            )

    def test_configure_with_jwt_path(self, in_memory_config: Any) -> None:
        """Test configuring proxy with JWT path."""
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".jwt"
        ) as jwt_file:
            jwt_file.write("test-jwt-token")
            jwt_file.flush()
            jwt_path = jwt_file.name

        try:
            with patch(
                "vibectl.subcommands.setup_proxy_cmd.Config",
                return_value=in_memory_config,
            ):
                result = configure_proxy_settings(
                    "vibectl-server://myserver.com:443",
                    ca_bundle=None,
                    jwt_path=jwt_path,
                )

                assert isinstance(result, Success)
                assert "✓ Proxy configured successfully" in result.message

                # Verify JWT path was saved
                assert in_memory_config.get("proxy.jwt_path") == str(
                    Path(jwt_path).expanduser().absolute()
                )
        finally:
            # Clean up temporary file
            Path(jwt_path).unlink(missing_ok=True)

    def test_configure_with_ca_bundle(self, in_memory_config: Any) -> None:
        """Test configuring proxy with CA bundle."""
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".crt"
        ) as ca_file:
            ca_file.write(
                "-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----"
            )
            ca_file.flush()
            ca_path = ca_file.name

        try:
            with patch(
                "vibectl.subcommands.setup_proxy_cmd.Config",
                return_value=in_memory_config,
            ):
                result = configure_proxy_settings(
                    "vibectl-server://myserver.com:443",
                    ca_bundle=ca_path,
                )

                assert isinstance(result, Success)
                assert "✓ Proxy configured successfully" in result.message

                # Verify CA bundle path was saved
                assert in_memory_config.get("proxy.ca_bundle_path") == str(
                    Path(ca_path).expanduser().absolute()
                )
        finally:
            # Clean up temporary file
            Path(ca_path).unlink(missing_ok=True)

    def test_configure_clean_url_with_embedded_jwt(self, in_memory_config: Any) -> None:
        """Test that embedded JWT tokens are removed from stored URL."""
        with patch(
            "vibectl.subcommands.setup_proxy_cmd.Config",
            return_value=in_memory_config,
        ):
            result = configure_proxy_settings(
                "vibectl-server://jwt-token-123@myserver.com:443",
            )

            assert isinstance(result, Success)

            # Verify URL is stored without JWT token
            stored_url = in_memory_config.get("proxy.server_url")
            assert stored_url == "vibectl-server://myserver.com:443"

    def test_configure_jwt_path_not_found(self, in_memory_config: Any) -> None:
        """Test configuring proxy with non-existent JWT path."""
        result = configure_proxy_settings(
            "vibectl-server://myserver.com:443",
            jwt_path="/nonexistent/path.jwt",
        )

        assert isinstance(result, Error)
        assert "JWT file not found" in result.error

    def test_configure_jwt_path_not_file(self, in_memory_config: Any) -> None:
        """Test configuring proxy with JWT path pointing to directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            result = configure_proxy_settings(
                "vibectl-server://myserver.com:443",
                jwt_path=temp_dir,
            )

            assert isinstance(result, Error)
            assert "JWT path is not a file" in result.error

    def test_configure_ca_bundle_not_found(self, in_memory_config: Any) -> None:
        """Test configuring proxy with non-existent CA bundle."""
        result = configure_proxy_settings(
            "vibectl-server://myserver.com:443",
            ca_bundle="/nonexistent/ca.crt",
        )

        assert isinstance(result, Error)
        assert "CA bundle file not found" in result.error

    def test_configure_invalid_url(self, in_memory_config: Any) -> None:
        """Test configuring proxy with invalid URL."""
        result = configure_proxy_settings("http://invalid.com", None)

        assert isinstance(result, Error)
        assert (
            "Invalid URL scheme. Must be one of: vibectl-server://, vibectl-server-insecure://"
            in result.error
        )

    def test_configure_parse_error(self, in_memory_config: Any) -> None:
        """Test configuration with parse error."""
        with (
            patch(
                "vibectl.subcommands.setup_proxy_cmd.Config",
                return_value=in_memory_config,
            ),
            patch(
                "vibectl.subcommands.setup_proxy_cmd.validate_proxy_url",
                return_value=(True, None),
            ),
            patch(
                "vibectl.subcommands.setup_proxy_cmd.parse_proxy_url", return_value=None
            ),
        ):
            result = configure_proxy_settings("invalid-url", None)

            assert isinstance(result, Error)
            assert "Invalid proxy URL format" in result.error

    def test_configure_exception_handling(self, in_memory_config: Any) -> None:
        """Test configuration handles unexpected exceptions."""
        with (
            patch(
                "vibectl.subcommands.setup_proxy_cmd.Config",
                return_value=in_memory_config,
            ),
            patch(
                "vibectl.subcommands.setup_proxy_cmd.validate_proxy_url"
            ) as mock_validate,
        ):
            mock_validate.side_effect = RuntimeError("Config error")

            result = configure_proxy_settings("vibectl-server://test.com:443", None)

            assert isinstance(result, Error)
            assert "Failed to configure proxy: Config error" in result.error

    def test_ca_bundle_path_validation_errors(self) -> None:
        """Test CA bundle path validation error cases."""
        # Test non-existent CA bundle
        result = configure_proxy_settings(
            "vibectl-server://test.com:443", ca_bundle="/nonexistent/ca.crt"
        )
        assert isinstance(result, Error)
        assert "CA bundle file not found: /nonexistent/ca.crt" in result.error

        # Test CA bundle that's not a file (create a directory)
        with tempfile.TemporaryDirectory() as temp_dir:
            ca_dir_path = Path(temp_dir) / "ca_directory"
            ca_dir_path.mkdir()
            result = configure_proxy_settings(
                "vibectl-server://test.com:443", ca_bundle=str(ca_dir_path)
            )
            assert isinstance(result, Error)
            assert "CA bundle path is not a file:" in result.error

    def test_jwt_path_validation_errors(self) -> None:
        """Test JWT path validation error cases."""
        # Test non-existent JWT file
        result = configure_proxy_settings(
            "vibectl-server://test.com:443", jwt_path="/nonexistent/token.jwt"
        )
        assert isinstance(result, Error)
        assert "JWT file not found: /nonexistent/token.jwt" in result.error

        # Test JWT path that's not a file (create a directory)
        with tempfile.TemporaryDirectory() as temp_dir:
            jwt_dir_path = Path(temp_dir) / "jwt_directory"
            jwt_dir_path.mkdir()
            result = configure_proxy_settings(
                "vibectl-server://test.com:443", jwt_path=str(jwt_dir_path)
            )
            assert isinstance(result, Error)
            assert "JWT path is not a file:" in result.error

    def test_url_rebuilding_with_embedded_jwt(self) -> None:
        """Test URL rebuilding when JWT token is embedded."""
        # Mock parse_proxy_url to return a config with embedded JWT
        mock_config = Mock()
        mock_config.jwt_token = "embedded-token"
        mock_config.use_tls = True
        mock_config.host = "test.com"
        mock_config.port = 443

        with (
            patch(
                "vibectl.subcommands.setup_proxy_cmd.parse_proxy_url",
                return_value=mock_config,
            ),
            patch(
                "vibectl.subcommands.setup_proxy_cmd.validate_proxy_url",
                return_value=(True, None),
            ),
            patch.object(Config, "set") as mock_set,
            patch.object(Config, "__init__", return_value=None),
        ):
            result = configure_proxy_settings(
                "vibectl-server://embedded-token@test.com:443"
            )

        assert isinstance(result, Success)
        # Check that the clean URL was stored (without the JWT token)
        mock_set.assert_any_call("proxy.server_url", "vibectl-server://test.com:443")

        # Test with insecure scheme
        mock_config.use_tls = False
        with (
            patch(
                "vibectl.subcommands.setup_proxy_cmd.parse_proxy_url",
                return_value=mock_config,
            ),
            patch(
                "vibectl.subcommands.setup_proxy_cmd.validate_proxy_url",
                return_value=(True, None),
            ),
            patch.object(Config, "set") as mock_set,
            patch.object(Config, "__init__", return_value=None),
        ):
            result = configure_proxy_settings(
                "vibectl-server-insecure://embedded-token@test.com:443"
            )

        assert isinstance(result, Success)
        # Check that the clean URL was stored with insecure scheme
        mock_set.assert_any_call(
            "proxy.server_url", "vibectl-server-insecure://test.com:443"
        )


class TestSetupProxyConfigureCLI:
    """Test cases for setup-proxy configure CLI command."""

    @pytest.mark.asyncio
    async def test_configure_success_with_test(self) -> None:
        """Test successful proxy configuration with connection test."""
        mock_server_info = {
            "server_name": "Test Server",
            "version": "1.0.0",
            "supported_models": ["model1", "model2"],
            "limits": {
                "max_request_size": 4096,
                "max_concurrent_requests": 10,
                "timeout_seconds": 30,
            },
        }

        with (
            patch(
                "vibectl.subcommands.setup_proxy_cmd.check_proxy_connection"
            ) as mock_test,
            patch(
                "vibectl.subcommands.setup_proxy_cmd.configure_proxy_settings"
            ) as mock_configure,
            patch(
                "vibectl.subcommands.setup_proxy_cmd.show_proxy_status"
            ) as mock_status,
            patch(
                "vibectl.subcommands.setup_proxy_cmd.console_manager"
            ) as _mock_console,
        ):
            mock_test.return_value = Success(data=mock_server_info)
            mock_configure.return_value = Success(
                message="Proxy configured successfully"
            )

            runner = CliRunner()
            result = await runner.invoke(
                cli,
                ["setup-proxy", "configure", "vibectl-server://test.com:443"],
                catch_exceptions=False,
            )

            assert result.exit_code == 0
            mock_test.assert_called_once_with(
                "vibectl-server://test.com:443",
                timeout_seconds=30,
                jwt_path=None,
                ca_bundle=None,
            )
            mock_configure.assert_called_once_with(
                "vibectl-server://test.com:443", ca_bundle=None, jwt_path=None
            )
            mock_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_configure_success_no_test(self) -> None:
        """Test successful proxy configuration without connection test."""
        with (
            patch(
                "vibectl.subcommands.setup_proxy_cmd.check_proxy_connection"
            ) as mock_test,
            patch(
                "vibectl.subcommands.setup_proxy_cmd.configure_proxy_settings"
            ) as mock_configure,
            patch(
                "vibectl.subcommands.setup_proxy_cmd.show_proxy_status"
            ) as mock_status,
            patch(
                "vibectl.subcommands.setup_proxy_cmd.console_manager"
            ) as _mock_console,
        ):
            mock_configure.return_value = Success(
                message="Proxy configured successfully"
            )

            runner = CliRunner()
            result = await runner.invoke(
                cli,
                [
                    "setup-proxy",
                    "configure",
                    "vibectl-server://test.com:443",
                    "--no-test",
                ],
                catch_exceptions=False,
            )

            assert result.exit_code == 0
            mock_test.assert_not_called()
            mock_configure.assert_called_once_with(
                "vibectl-server://test.com:443", ca_bundle=None, jwt_path=None
            )
            mock_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_configure_connection_test_failed(self) -> None:
        """Test proxy configuration when connection test fails."""
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
                ["setup-proxy", "configure", "vibectl-server://bad.com:443"],
                catch_exceptions=False,
            )

            mock_test.assert_called_once()
            # CliRunner catches sys.exit and converts to exit_code
            assert result.exit_code == 1

    @pytest.mark.asyncio
    async def test_configure_config_failed(self) -> None:
        """Test proxy configuration when configuration fails."""
        with (
            patch(
                "vibectl.subcommands.setup_proxy_cmd.check_proxy_connection"
            ) as mock_test,
            patch(
                "vibectl.subcommands.setup_proxy_cmd.configure_proxy_settings"
            ) as mock_configure,
            patch(
                "vibectl.subcommands.setup_proxy_cmd.console_manager"
            ) as _mock_console,
        ):
            mock_test.return_value = Success(data={})
            mock_configure.return_value = Error(error="Configuration failed")

            runner = CliRunner()
            result = await runner.invoke(
                cli,
                [
                    "setup-proxy",
                    "configure",
                    "vibectl-server://test.com:443",
                    "--no-test",
                ],
                catch_exceptions=False,
            )

            mock_configure.assert_called_once()
            # CliRunner catches sys.exit and converts to exit_code
            assert result.exit_code == 1

    @pytest.mark.asyncio
    async def test_configure_exception_handling(self) -> None:
        """Test configure command handles exceptions."""
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
                ["setup-proxy", "configure", "vibectl-server://test.com:443"],
                catch_exceptions=True,
            )

            mock_handle.assert_called_once()

    @pytest.mark.asyncio
    async def test_configure_ca_bundle_not_found(self) -> None:
        """Test configure command with non-existent CA bundle."""
        with (
            patch("vibectl.subcommands.setup_proxy_cmd.os.environ.get") as mock_env_get,
            patch(
                "vibectl.subcommands.setup_proxy_cmd.console_manager"
            ) as _mock_console,
        ):
            # Mock only the VIBECTL_CA_BUNDLE environment variable
            def env_get_side_effect(key: str, default: Any = None) -> Any:
                if key == "VIBECTL_CA_BUNDLE":
                    return None  # No env CA bundle
                # For any other environment variable requests, return the default
                return default

            mock_env_get.side_effect = env_get_side_effect

            runner = CliRunner()
            result = await runner.invoke(
                cli,
                [
                    "setup-proxy",
                    "configure",
                    "vibectl-server://test.com:443",
                    "--ca-bundle",
                    "/path/to/nonexistent/ca-bundle.crt",
                ],
                catch_exceptions=False,
            )

            # Should exit with error code 1 due to CA bundle not found
            assert result.exit_code == 1

    @pytest.mark.asyncio
    async def test_configure_recovery_suggestions_displayed(self) -> None:
        """Test configure command shows recovery suggestions."""
        with (
            patch(
                "vibectl.subcommands.setup_proxy_cmd.check_proxy_connection"
            ) as mock_test,
            patch(
                "vibectl.subcommands.setup_proxy_cmd.console_manager"
            ) as mock_console,
        ):
            # Mock connection test to return error with recovery suggestions
            mock_test.return_value = Error(
                error="Connection failed",
                recovery_suggestions="Try these steps: 1. Check server...",
            )

            runner = CliRunner()
            result = await runner.invoke(
                cli,
                ["setup-proxy", "configure", "vibectl-server://test.com:443"],
                catch_exceptions=False,
            )

            # Should show recovery suggestions and exit with error
            assert result.exit_code == 1
            mock_console.print_note.assert_called_with(
                "Try these steps: 1. Check server..."
            )

    @pytest.mark.asyncio
    async def test_configure_no_recovery_suggestions_fallback(self) -> None:
        """Test configure command fallback message when no recovery suggestions."""
        with (
            patch(
                "vibectl.subcommands.setup_proxy_cmd.check_proxy_connection"
            ) as mock_test,
            patch(
                "vibectl.subcommands.setup_proxy_cmd.console_manager"
            ) as mock_console,
        ):
            # Mock connection test to return error without recovery suggestions
            mock_test.return_value = Error(error="Connection failed")

            runner = CliRunner()
            result = await runner.invoke(
                cli,
                ["setup-proxy", "configure", "vibectl-server://test.com:443"],
                catch_exceptions=False,
            )

            # Should show fallback message and exit with error
            assert result.exit_code == 1
            mock_console.print_note.assert_called_with(
                "You can skip the connection test with --no-test if the "
                "server is not running yet."
            )
