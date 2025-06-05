"""Tests for setup_proxy_cmd.py - LLM proxy configuration commands."""

from typing import Any
from unittest.mock import Mock, patch

import grpc
import pytest
from asyncclick.testing import CliRunner

from vibectl.cli import cli
from vibectl.subcommands.setup_proxy_cmd import (
    check_proxy_connection,
    configure_proxy_settings,
    disable_proxy,
    show_proxy_status,
    validate_proxy_url,
)
from vibectl.types import Error, Success


class TestValidateProxyUrl:
    """Test cases for validate_proxy_url function."""

    def test_validate_empty_url(self) -> None:
        """Test validation of empty URL."""
        valid, error = validate_proxy_url("")
        assert not valid
        assert error == "Proxy URL cannot be empty"

    def test_validate_whitespace_url(self) -> None:
        """Test validation of whitespace-only URL."""
        valid, error = validate_proxy_url("   ")
        assert not valid
        assert error == "Proxy URL cannot be empty"

    def test_validate_valid_url(self) -> None:
        """Test validation of valid URLs."""
        valid, error = validate_proxy_url("vibectl-server://myserver.com:443")
        assert valid
        assert error is None

    def test_validate_valid_insecure_url(self) -> None:
        """Test validation of valid insecure URLs."""
        valid, error = validate_proxy_url("vibectl-server-insecure://localhost:50051")
        assert valid
        assert error is None

    def test_validate_invalid_scheme(self) -> None:
        """Test validation of URL with invalid scheme."""
        valid, error = validate_proxy_url("http://myserver.com:443")
        assert not valid
        assert error is not None
        assert "Invalid URL scheme" in error
        assert "vibectl-server://" in error
        assert "vibectl-server-insecure://" in error

    def test_validate_missing_hostname(self) -> None:
        """Test validation of URL missing hostname."""
        valid, error = validate_proxy_url("vibectl-server://:443")
        assert not valid
        assert error is not None
        assert "URL must include a hostname" in error

    def test_validate_with_jwt_token(self) -> None:
        """Test validation of URL with JWT token."""
        # Use a realistic JWT token format: header.payload.signature
        jwt_token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0In0.0123456789abcdef"
        valid, error = validate_proxy_url(
            f"vibectl-server://{jwt_token}@myserver.com:443"
        )
        assert valid
        assert error is None

    def test_validate_exception_handling(self) -> None:
        """Test validation handles unexpected exceptions."""
        with patch("vibectl.subcommands.setup_proxy_cmd.parse_proxy_url") as mock_parse:
            mock_parse.side_effect = RuntimeError("Unexpected error")
            valid, error = validate_proxy_url("vibectl-server://test.com:443")
            assert not valid
            assert error is not None
            assert "URL validation failed: Unexpected error" in error


class TestTestProxyConnection:
    """Test cases for test_proxy_connection function."""

    @pytest.mark.asyncio
    async def test_grpc_not_available(self) -> None:
        """Test behavior when gRPC modules are not available."""
        with patch("vibectl.subcommands.setup_proxy_cmd.GRPC_AVAILABLE", False):
            result = await check_proxy_connection("vibectl-server://test.com:443")
            assert isinstance(result, Error)
            assert "gRPC modules are not available" in result.error
            assert isinstance(result.exception, ImportError)

    @pytest.mark.asyncio
    async def test_invalid_url_format(self) -> None:
        """Test connection test with invalid URL format."""
        with patch(
            "vibectl.subcommands.setup_proxy_cmd.parse_proxy_url", return_value=None
        ):
            result = await check_proxy_connection("invalid-url")
            assert isinstance(result, Error)
            assert "Invalid proxy URL format" in result.error

    @pytest.mark.asyncio
    async def test_successful_connection_secure(self) -> None:
        """Test successful connection to secure server."""
        mock_proxy_config = Mock()
        mock_proxy_config.host = "test.com"
        mock_proxy_config.port = 443
        mock_proxy_config.use_tls = True
        mock_proxy_config.jwt_token = None

        mock_response = Mock()
        mock_response.server_version = "1.0.0"
        mock_response.available_models = [
            Mock(model_id="model1"),
            Mock(model_id="model2"),
        ]
        mock_response.limits.max_input_length = 4096
        mock_response.limits.max_concurrent_requests = 10
        mock_response.limits.request_timeout_seconds = 30

        with (
            patch(
                "vibectl.subcommands.setup_proxy_cmd.parse_proxy_url",
                return_value=mock_proxy_config,
            ),
            patch("grpc.secure_channel") as mock_secure_channel,
            patch("grpc.ssl_channel_credentials") as _mock_ssl_creds,
            patch(
                "vibectl.subcommands.setup_proxy_cmd.llm_proxy_pb2_grpc.VibectlLLMProxyStub"
            ) as _mock_stub_class,
            patch(
                "vibectl.subcommands.setup_proxy_cmd.llm_proxy_pb2.GetServerInfoRequest"
            ) as _mock_request_class,
            patch("asyncio.wait_for") as mock_wait_for,
            patch("asyncio.get_event_loop") as _mock_get_loop,
        ):
            mock_channel = Mock()
            mock_secure_channel.return_value = mock_channel
            mock_stub = Mock()
            _mock_stub_class.return_value = mock_stub
            mock_request = Mock()
            _mock_request_class.return_value = mock_request

            # Mock the executor call
            mock_loop = Mock()
            _mock_get_loop.return_value = mock_loop
            mock_wait_for.return_value = mock_response

            result = await check_proxy_connection("vibectl-server://test.com:443")

            assert isinstance(result, Success)
            data = result.data
            assert data is not None
            assert data["version"] == "1.0.0"
            assert data["supported_models"] == ["model1", "model2"]
            assert data["limits"]["max_request_size"] == 4096
            mock_channel.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_successful_connection_insecure_with_jwt(self) -> None:
        """Test successful connection to insecure server with JWT token."""
        mock_proxy_config = Mock()
        mock_proxy_config.host = "localhost"
        mock_proxy_config.port = 50051
        mock_proxy_config.use_tls = False
        mock_proxy_config.jwt_token = "jwt-token-123"

        mock_response = Mock()
        mock_response.server_version = "1.0.0"
        mock_response.available_models = []
        mock_response.limits.max_input_length = 2048
        mock_response.limits.max_concurrent_requests = 5
        mock_response.limits.request_timeout_seconds = 15

        with (
            patch(
                "vibectl.subcommands.setup_proxy_cmd.parse_proxy_url",
                return_value=mock_proxy_config,
            ),
            patch("grpc.insecure_channel") as mock_insecure_channel,
            patch(
                "vibectl.subcommands.setup_proxy_cmd.llm_proxy_pb2_grpc.VibectlLLMProxyStub"
            ) as _mock_stub_class,
            patch(
                "vibectl.subcommands.setup_proxy_cmd.llm_proxy_pb2.GetServerInfoRequest"
            ) as _mock_request_class,
            patch("asyncio.wait_for") as mock_wait_for,
            patch("asyncio.get_event_loop") as _mock_get_loop,
        ):
            mock_channel = Mock()
            mock_insecure_channel.return_value = mock_channel
            mock_stub = Mock()
            _mock_stub_class.return_value = mock_stub

            mock_wait_for.return_value = mock_response

            result = await check_proxy_connection(
                "vibectl-server-insecure://jwt-token-123@localhost:50051"
            )

            assert isinstance(result, Success)
            data = result.data
            assert data is not None
            assert data["version"] == "1.0.0"
            assert data["supported_models"] == []
            mock_channel.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_connection_unavailable_error(self) -> None:
        """Test connection error when server is unavailable."""
        mock_proxy_config = Mock()
        mock_proxy_config.host = "unreachable.com"
        mock_proxy_config.port = 443
        mock_proxy_config.use_tls = True
        mock_proxy_config.jwt_token = None

        # Create a proper gRPC error - use a callable that raises
        # when used as side_effect
        def create_grpc_error() -> Exception:
            class MockRpcError(grpc.RpcError):
                def code(self) -> grpc.StatusCode:
                    return grpc.StatusCode.UNAVAILABLE

                def details(self) -> str:
                    return "Connection refused"

            return MockRpcError()

        with (
            patch(
                "vibectl.subcommands.setup_proxy_cmd.parse_proxy_url",
                return_value=mock_proxy_config,
            ),
            patch("grpc.secure_channel") as mock_secure_channel,
            patch(
                "vibectl.subcommands.setup_proxy_cmd.llm_proxy_pb2_grpc.VibectlLLMProxyStub"
            ) as _mock_stub_class,
            patch("asyncio.wait_for") as mock_wait_for,
        ):
            mock_channel = Mock()
            mock_secure_channel.return_value = mock_channel
            mock_wait_for.side_effect = create_grpc_error()

            result = await check_proxy_connection(
                "vibectl-server://unreachable.com:443"
            )

            assert isinstance(result, Error)
            assert "Server unavailable at unreachable.com:443" in result.error
            assert "Connection refused" in result.error
            mock_channel.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_connection_auth_error(self) -> None:
        """Test connection error for authentication failure."""
        mock_proxy_config = Mock()
        mock_proxy_config.host = "test.com"
        mock_proxy_config.port = 443
        mock_proxy_config.use_tls = True
        mock_proxy_config.jwt_token = None

        # Create a proper gRPC error - use a callable that raises
        # when used as side_effect
        def create_grpc_error() -> Exception:
            class MockRpcError(grpc.RpcError):
                def code(self) -> grpc.StatusCode:
                    return grpc.StatusCode.UNAUTHENTICATED

                def details(self) -> str:
                    return "Authentication required"

            return MockRpcError()

        with (
            patch(
                "vibectl.subcommands.setup_proxy_cmd.parse_proxy_url",
                return_value=mock_proxy_config,
            ),
            patch("grpc.secure_channel") as mock_secure_channel,
            patch("asyncio.wait_for") as mock_wait_for,
        ):
            mock_channel = Mock()
            mock_secure_channel.return_value = mock_channel
            mock_wait_for.side_effect = create_grpc_error()

            result = await check_proxy_connection("vibectl-server://test.com:443")

            assert isinstance(result, Error)
            assert "Authentication failed" in result.error
            assert "Server requires JWT authentication" in result.error

    @pytest.mark.asyncio
    async def test_connection_permission_denied(self) -> None:
        """Test connection error for permission denied."""
        mock_proxy_config = Mock()
        mock_proxy_config.host = "test.com"
        mock_proxy_config.port = 443
        mock_proxy_config.use_tls = True
        mock_proxy_config.jwt_token = "expired-token"

        # Create a proper gRPC error - use a callable that raises
        # when used as side_effect
        def create_grpc_error() -> Exception:
            class MockRpcError(grpc.RpcError):
                def code(self) -> grpc.StatusCode:
                    return grpc.StatusCode.PERMISSION_DENIED

                def details(self) -> str:
                    return "Token expired"

            return MockRpcError()

        with (
            patch(
                "vibectl.subcommands.setup_proxy_cmd.parse_proxy_url",
                return_value=mock_proxy_config,
            ),
            patch("grpc.secure_channel") as mock_secure_channel,
            patch("asyncio.wait_for") as mock_wait_for,
        ):
            mock_channel = Mock()
            mock_secure_channel.return_value = mock_channel
            mock_wait_for.side_effect = create_grpc_error()

            result = await check_proxy_connection(
                "vibectl-server://expired-token@test.com:443"
            )

            assert isinstance(result, Error)
            assert "Permission denied" in result.error
            assert "JWT token may be invalid or expired" in result.error

    @pytest.mark.asyncio
    async def test_connection_timeout_error(self) -> None:
        """Test connection timeout error."""
        mock_proxy_config = Mock()
        mock_proxy_config.host = "slow.com"
        mock_proxy_config.port = 443
        mock_proxy_config.use_tls = True
        mock_proxy_config.jwt_token = None

        with (
            patch(
                "vibectl.subcommands.setup_proxy_cmd.parse_proxy_url",
                return_value=mock_proxy_config,
            ),
            patch("grpc.secure_channel") as mock_secure_channel,
            patch("asyncio.wait_for") as mock_wait_for,
        ):
            mock_channel = Mock()
            mock_secure_channel.return_value = mock_channel
            mock_wait_for.side_effect = TimeoutError()

            result = await check_proxy_connection(
                "vibectl-server://slow.com:443", timeout_seconds=5
            )

            assert isinstance(result, Error)
            assert "Connection timeout after 5 seconds" in result.error
            mock_channel.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_connection_unimplemented_error(self) -> None:
        """Test connection error for unimplemented service."""
        mock_proxy_config = Mock()
        mock_proxy_config.host = "test.com"
        mock_proxy_config.port = 443
        mock_proxy_config.use_tls = True
        mock_proxy_config.jwt_token = None

        # Create a proper gRPC error - use a callable that raises
        # when used as side_effect
        def create_grpc_error() -> Exception:
            class MockRpcError(grpc.RpcError):
                def code(self) -> grpc.StatusCode:
                    return grpc.StatusCode.UNIMPLEMENTED

                def details(self) -> str:
                    return "Service not implemented"

            return MockRpcError()

        with (
            patch(
                "vibectl.subcommands.setup_proxy_cmd.parse_proxy_url",
                return_value=mock_proxy_config,
            ),
            patch("grpc.secure_channel") as mock_secure_channel,
            patch("asyncio.wait_for") as mock_wait_for,
        ):
            mock_channel = Mock()
            mock_secure_channel.return_value = mock_channel
            mock_wait_for.side_effect = create_grpc_error()

            result = await check_proxy_connection("vibectl-server://test.com:443")

            assert isinstance(result, Error)
            assert "Server does not support the required service" in result.error

    @pytest.mark.asyncio
    async def test_connection_generic_error(self) -> None:
        """Test connection error for generic gRPC errors."""
        mock_proxy_config = Mock()
        mock_proxy_config.host = "test.com"
        mock_proxy_config.port = 443
        mock_proxy_config.use_tls = True
        mock_proxy_config.jwt_token = None

        # Create a proper gRPC error - use a callable that raises
        # when used as side_effect
        def create_grpc_error() -> Exception:
            class MockRpcError(grpc.RpcError):
                def code(self) -> grpc.StatusCode:
                    return grpc.StatusCode.INTERNAL

                def details(self) -> str:
                    return "Internal server error"

            return MockRpcError()

        with (
            patch(
                "vibectl.subcommands.setup_proxy_cmd.parse_proxy_url",
                return_value=mock_proxy_config,
            ),
            patch("grpc.secure_channel") as mock_secure_channel,
            patch("asyncio.wait_for") as mock_wait_for,
        ):
            mock_channel = Mock()
            mock_secure_channel.return_value = mock_channel
            mock_wait_for.side_effect = create_grpc_error()

            result = await check_proxy_connection("vibectl-server://test.com:443")

            assert isinstance(result, Error)
            assert "gRPC error (INTERNAL): Internal server error" in result.error

    @pytest.mark.asyncio
    async def test_connection_unexpected_exception(self) -> None:
        """Test connection error for unexpected exceptions."""
        with patch("vibectl.subcommands.setup_proxy_cmd.parse_proxy_url") as mock_parse:
            mock_parse.side_effect = RuntimeError("Unexpected error")

            result = await check_proxy_connection("vibectl-server://test.com:443")

            assert isinstance(result, Error)
            assert "Connection test failed: Unexpected error" in result.error


class TestConfigureProxySettings:
    """Test cases for configure_proxy_settings function."""

    def test_configure_valid_url(self, in_memory_config: Any) -> None:
        """Test configuring proxy with valid URL."""
        with patch(
            "vibectl.subcommands.setup_proxy_cmd.Config", return_value=in_memory_config
        ):
            result = configure_proxy_settings("vibectl-server://test.com:443")

            assert isinstance(result, Success)
            assert "Proxy configured successfully" in result.message
            # Verify config was set
            assert in_memory_config.get("proxy.enabled") is True
            assert (
                in_memory_config.get("proxy.server_url")
                == "vibectl-server://test.com:443"
            )

    def test_configure_invalid_url(self, in_memory_config: Any) -> None:
        """Test configuring proxy with invalid URL."""
        with patch(
            "vibectl.subcommands.setup_proxy_cmd.Config", return_value=in_memory_config
        ):
            result = configure_proxy_settings("")

            assert isinstance(result, Error)
            assert "Proxy URL cannot be empty" in result.error

    def test_configure_parse_error(self, in_memory_config: Any) -> None:
        """Test configuring proxy when URL parsing fails."""
        with (
            patch(
                "vibectl.subcommands.setup_proxy_cmd.Config",
                return_value=in_memory_config,
            ),
            patch(
                "vibectl.subcommands.setup_proxy_cmd.parse_proxy_url", return_value=None
            ),
        ):
            result = configure_proxy_settings("invalid-url")

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

            result = configure_proxy_settings("vibectl-server://test.com:443")

            assert isinstance(result, Error)
            assert "Failed to configure proxy: Config error" in result.error


class TestDisableProxy:
    """Test cases for disable_proxy function."""

    def test_disable_proxy_success(self, in_memory_config: Any) -> None:
        """Test successfully disabling proxy."""
        # Set up initial proxy configuration
        in_memory_config.set("proxy.enabled", True)
        in_memory_config.set("proxy.server_url", "vibectl-server://test.com:443")
        in_memory_config.set("proxy.timeout_seconds", 60)
        in_memory_config.set("proxy.retry_attempts", 5)

        with patch(
            "vibectl.subcommands.setup_proxy_cmd.Config", return_value=in_memory_config
        ):
            result = disable_proxy()

            assert isinstance(result, Success)
            assert result.data == "Proxy disabled"
            # Verify proxy was disabled
            assert in_memory_config.get("proxy.enabled") is False
            assert in_memory_config.get("proxy.server_url") is None

    def test_disable_proxy_already_disabled(self, in_memory_config: Any) -> None:
        """Test disabling proxy when already disabled."""
        # Ensure proxy is disabled
        in_memory_config.set("proxy.enabled", False)

        with patch(
            "vibectl.subcommands.setup_proxy_cmd.Config", return_value=in_memory_config
        ):
            result = disable_proxy()

            assert isinstance(result, Success)
            assert result.data == "Proxy is already disabled"

    def test_disable_proxy_exception_handling(self, in_memory_config: Any) -> None:
        """Test disable proxy handles exceptions."""
        # Set proxy enabled initially so it tries to disable
        in_memory_config.set("proxy.enabled", True)

        with (
            patch(
                "vibectl.subcommands.setup_proxy_cmd.Config",
                return_value=in_memory_config,
            ),
            patch.object(
                in_memory_config, "set", side_effect=RuntimeError("Config error")
            ),
        ):
            result = disable_proxy()

            assert isinstance(result, Error)
            assert "Failed to disable proxy: Config error" in result.error


class TestShowProxyStatus:
    """Test cases for show_proxy_status function."""

    def test_show_status_enabled(
        self, in_memory_config: Any, test_console: Any
    ) -> None:
        """Test showing status when proxy is enabled."""
        in_memory_config.set("proxy.enabled", True)
        in_memory_config.set("proxy.server_url", "vibectl-server://test.com:443")
        in_memory_config.set("proxy.timeout_seconds", 45)
        in_memory_config.set("proxy.retry_attempts", 4)

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
        in_memory_config.set("proxy.enabled", False)

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

    def test_show_status_exception_handling(self, in_memory_config: Any) -> None:
        """Test status display handles exceptions."""
        with (
            patch(
                "vibectl.subcommands.setup_proxy_cmd.Config",
                return_value=in_memory_config,
            ),
            patch.object(
                in_memory_config, "get", side_effect=RuntimeError("Config error")
            ),
            patch(
                "vibectl.subcommands.setup_proxy_cmd.handle_exception"
            ) as mock_handle,
        ):
            show_proxy_status()

            mock_handle.assert_called_once()


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
                "vibectl-server://test.com:443", timeout_seconds=30
            )
            mock_configure.assert_called_once_with("vibectl-server://test.com:443")
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
            mock_configure.assert_called_once_with("vibectl-server://test.com:443")
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
                "vibectl-server://test.com:443", timeout_seconds=10
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
                "vibectl-server://configured.com:443", timeout_seconds=10
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
                "vibectl-server://test.com:443", timeout_seconds=30
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


class TestSetupProxyDisableCLI:
    """Test cases for setup-proxy disable CLI command."""

    @pytest.mark.asyncio
    async def test_disable_with_confirmation(self, in_memory_config: Any) -> None:
        """Test disable command with confirmation prompt."""
        in_memory_config.set("proxy.enabled", True)

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
    async def test_disable_with_yes_flag(self) -> None:
        """Test disable command with --yes flag."""
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
                ["setup-proxy", "disable", "--yes"],
                catch_exceptions=False,
            )

            assert result.exit_code == 0
            mock_confirm.assert_not_called()
            mock_disable.assert_called_once()
            mock_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_disable_already_disabled(self, in_memory_config: Any) -> None:
        """Test disable command when proxy is already disabled."""
        in_memory_config.set("proxy.enabled", False)

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
                ["setup-proxy", "disable", "--yes"],
                catch_exceptions=False,
            )

            assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_disable_confirmation_declined(self, in_memory_config: Any) -> None:
        """Test disable command when user declines confirmation."""
        in_memory_config.set("proxy.enabled", True)

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
                ["setup-proxy", "disable", "--yes"],
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
                ["setup-proxy", "disable", "--yes"],
                catch_exceptions=True,
            )

            mock_handle.assert_called_once()


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


class TestSetupProxyGroup:
    """Test cases for setup-proxy command group."""

    @pytest.mark.asyncio
    async def test_setup_proxy_group_help(self) -> None:
        """Test setup-proxy group shows help."""
        runner = CliRunner()
        result = await runner.invoke(
            cli,
            ["setup-proxy", "--help"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        assert "Setup and manage proxy configuration" in result.output
        assert "configure" in result.output
        assert "test" in result.output
        assert "status" in result.output
        assert "disable" in result.output

    @pytest.mark.asyncio
    async def test_setup_proxy_subcommands_exist(self) -> None:
        """Test that all expected subcommands exist."""
        # Test by invoking help for each expected subcommand
        runner = CliRunner()
        expected_commands = ["configure", "test", "status", "disable", "url"]

        for cmd_name in expected_commands:
            result = await runner.invoke(
                cli,
                ["setup-proxy", cmd_name, "--help"],
                catch_exceptions=False,
            )
            # If the command exists, help should succeed
            assert result.exit_code == 0
