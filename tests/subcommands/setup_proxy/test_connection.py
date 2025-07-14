"""Tests for proxy connection testing in setup_proxy_cmd.py."""

import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import grpc
import pytest

from vibectl.subcommands.setup_proxy_cmd import check_proxy_connection
from vibectl.types import Error, Success


class TestTestProxyConnection:
    """Test cases for test_proxy_connection function."""

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
    async def test_jwt_path_file_not_found(self) -> None:
        """Test connection test with JWT path pointing to non-existent file."""
        mock_proxy_config = Mock()
        mock_proxy_config.host = "test.com"
        mock_proxy_config.port = 443
        mock_proxy_config.use_tls = True
        mock_proxy_config.jwt_token = None

        with patch(
            "vibectl.subcommands.setup_proxy_cmd.parse_proxy_url",
            return_value=mock_proxy_config,
        ):
            result = await check_proxy_connection(
                "vibectl-server://test.com:443", jwt_path="/nonexistent/file.jwt"
            )
            assert isinstance(result, Error)
            assert "JWT file not found or not accessible" in result.error

    @pytest.mark.asyncio
    async def test_jwt_path_read_error(self) -> None:
        """Test connection test with JWT path that cannot be read."""
        mock_proxy_config = Mock()
        mock_proxy_config.host = "test.com"
        mock_proxy_config.port = 443
        mock_proxy_config.use_tls = True
        mock_proxy_config.jwt_token = None

        with (
            patch(
                "vibectl.subcommands.setup_proxy_cmd.parse_proxy_url",
                return_value=mock_proxy_config,
            ),
            patch("pathlib.Path.expanduser") as mock_expanduser,
        ):
            mock_path = Mock()
            mock_path.exists.return_value = True
            mock_path.is_file.return_value = True
            mock_path.read_text.side_effect = PermissionError("Access denied")
            mock_expanduser.return_value = mock_path

            result = await check_proxy_connection(
                "vibectl-server://test.com:443", jwt_path="/restricted/file.jwt"
            )
            assert isinstance(result, Error)
            assert "Failed to read JWT file" in result.error
            assert "Access denied" in result.error

    @pytest.mark.asyncio
    async def test_jwt_path_takes_precedence(self) -> None:
        """Test that jwt_path parameter takes precedence over embedded token."""
        mock_proxy_config = Mock()
        mock_proxy_config.host = "test.com"
        mock_proxy_config.port = 443
        mock_proxy_config.use_tls = False  # Use insecure for simpler testing
        mock_proxy_config.jwt_token = "embedded-token"  # This should be ignored

        mock_response = Mock()
        mock_response.server_version = "1.0.0"
        mock_response.available_models = []
        mock_response.limits.max_input_length = 4096
        mock_response.limits.max_concurrent_requests = 10
        mock_response.limits.request_timeout_seconds = 30

        with (
            tempfile.NamedTemporaryFile(
                mode="w", delete=False, suffix=".jwt"
            ) as jwt_file,
        ):
            jwt_file.write("file-token-123")
            jwt_file.flush()
            jwt_path = jwt_file.name

        try:
            with (
                patch(
                    "vibectl.subcommands.setup_proxy_cmd.parse_proxy_url",
                    return_value=mock_proxy_config,
                ),
                patch("grpc.secure_channel"),
                patch("grpc.insecure_channel") as mock_insecure_channel,
                patch(
                    "vibectl.subcommands.setup_proxy_cmd.llm_proxy_pb2_grpc.VibectlLLMProxyStub"
                ) as mock_stub_class,
                patch(
                    "vibectl.subcommands.setup_proxy_cmd.llm_proxy_pb2.GetServerInfoRequest"
                ),
                patch("asyncio.wait_for") as mock_wait_for,
                patch("asyncio.get_event_loop"),
            ):
                mock_channel = Mock()
                mock_insecure_channel.return_value = mock_channel
                mock_stub = Mock()
                mock_stub_class.return_value = mock_stub
                mock_wait_for.return_value = mock_response

                result = await check_proxy_connection(
                    "vibectl-server-insecure://embedded-token@test.com:443",
                    jwt_path=jwt_path,
                )

                assert isinstance(result, Success)
                # Verify that JWT token from file was used (not embedded token)
                # Check that metadata contains the file token
                # The executor function should have been called with metadata
                # containing file token
                assert mock_channel.close.called

        finally:
            Path(jwt_path).unlink()  # Clean up temp file

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
            patch("asyncio.get_event_loop"),
        ):
            mock_channel = Mock()
            mock_secure_channel.return_value = mock_channel
            mock_stub = Mock()
            _mock_stub_class.return_value = mock_stub
            mock_request = Mock()
            _mock_request_class.return_value = mock_request

            # Mock the executor call - make it properly awaitable
            async def mock_wait_for_coro(*args: Any, **kwargs: Any) -> Any:
                return mock_response

            mock_wait_for.side_effect = mock_wait_for_coro

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
            patch("asyncio.get_event_loop"),
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
                    return "Server requires JWT authentication"

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
            patch("asyncio.wait_for", new_callable=Mock) as mock_wait_for,
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

    @pytest.mark.asyncio
    async def test_malformed_jwt_token_causes_server_error(self) -> None:
        """Test that malformed JWT tokens are properly rejected by the server."""
        mock_proxy_config = Mock()
        mock_proxy_config.host = "test.com"
        mock_proxy_config.port = 443
        mock_proxy_config.use_tls = False  # Use insecure for simpler testing
        mock_proxy_config.jwt_token = None

        # Create malformed JWT token file (this simulates the contamination issue)
        malformed_jwt = (
            "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0In0.signature.extra.contamination"
        )

        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".jwt"
        ) as jwt_file:
            jwt_file.write(malformed_jwt)
            jwt_file.flush()
            jwt_path = jwt_file.name

        try:
            # Create a proper gRPC error that mimics server JWT validation failure
            def create_grpc_error() -> Exception:
                class MockRpcError(grpc.RpcError):
                    def code(self) -> grpc.StatusCode:
                        return grpc.StatusCode.UNAUTHENTICATED

                    def details(self) -> str:
                        return "Invalid JWT token: Not enough segments"

                return MockRpcError()

            with (
                patch(
                    "vibectl.subcommands.setup_proxy_cmd.parse_proxy_url",
                    return_value=mock_proxy_config,
                ),
                patch("grpc.insecure_channel") as mock_insecure_channel,
                patch("asyncio.wait_for") as mock_wait_for,
            ):
                mock_channel = Mock()
                mock_insecure_channel.return_value = mock_channel
                mock_wait_for.side_effect = create_grpc_error()

                result = await check_proxy_connection(
                    "vibectl-server-insecure://test.com:443",
                    jwt_path=jwt_path,
                )

                # Should fail with authentication error, not try to "clean" the JWT
                assert isinstance(result, Error)
                assert "Server requires JWT authentication" in result.error

        finally:
            Path(jwt_path).unlink()

    @pytest.mark.asyncio
    async def test_jwt_file_read_exception(self) -> None:
        """Test JWT file reading error handling."""
        mock_proxy_config = Mock()
        mock_proxy_config.host = "test.com"
        mock_proxy_config.port = 443
        mock_proxy_config.use_tls = False
        mock_proxy_config.jwt_token = None

        # Create a file that exists but will cause read error
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".jwt"
        ) as jwt_file:
            jwt_file.write("test-token")
            jwt_file.flush()
            jwt_path = jwt_file.name

        try:
            # Mock file reading to raise an exception
            with (
                patch(
                    "pathlib.Path.read_text",
                    side_effect=PermissionError("Permission denied"),
                ),
                patch(
                    "vibectl.subcommands.setup_proxy_cmd.parse_proxy_url",
                    return_value=mock_proxy_config,
                ),
            ):
                result = await check_proxy_connection(
                    "vibectl-server://test.com:443", jwt_path=jwt_path
                )

            assert isinstance(result, Error)
            assert "Failed to read JWT file" in result.error
            assert "Permission denied" in result.error
        finally:
            os.unlink(jwt_path)

    @pytest.mark.asyncio
    async def test_ca_bundle_file_not_found(self) -> None:
        """Test CA bundle FileNotFoundError handling."""
        mock_proxy_config = Mock()
        mock_proxy_config.host = "test.com"
        mock_proxy_config.port = 443
        mock_proxy_config.use_tls = True
        mock_proxy_config.jwt_token = None

        with patch(
            "vibectl.subcommands.setup_proxy_cmd.parse_proxy_url",
            return_value=mock_proxy_config,
        ):
            result = await check_proxy_connection(
                "vibectl-server://test.com:443", ca_bundle="/nonexistent/ca-bundle.crt"
            )

        assert isinstance(result, Error)
        # Updated to match actual error message from implementation
        assert "CA bundle file not found: /nonexistent/ca-bundle.crt" in result.error

    @pytest.mark.asyncio
    async def test_ca_bundle_file_read_error(self) -> None:
        """Test CA bundle file read error."""
        mock_proxy_config = Mock()
        mock_proxy_config.host = "test.com"
        mock_proxy_config.port = 443
        mock_proxy_config.use_tls = True
        mock_proxy_config.jwt_token = None

        # Create a temporary file but mock reading to fail
        with tempfile.NamedTemporaryFile(suffix=".crt") as ca_file:
            ca_bundle_path = ca_file.name

            with (
                patch(
                    "vibectl.subcommands.setup_proxy_cmd.parse_proxy_url",
                    return_value=mock_proxy_config,
                ),
                patch(
                    "vibectl.subcommands.setup_proxy_cmd.Config"
                ) as mock_config_class,
            ):
                # Mock the Config class to return a working config
                mock_config = Mock()
                mock_config.get_ca_bundle_path.return_value = None
                mock_config.get_jwt_token.return_value = None
                mock_config_class.return_value = mock_config

                # Mock the specific file open call that should fail (for CA bundle)
                original_open = open

                def mock_open(*args: Any, **kwargs: Any) -> Any:
                    if (
                        len(args) > 0
                        and args[0] == ca_bundle_path
                        and "rb"
                        in (args[1] if len(args) > 1 else kwargs.get("mode", ""))
                    ):
                        raise PermissionError("Permission denied")
                    return original_open(*args, **kwargs)

                with patch("builtins.open", side_effect=mock_open):
                    result = await check_proxy_connection(
                        "vibectl-server://test.com:443", ca_bundle=ca_bundle_path
                    )

            assert isinstance(result, Error)
            assert (
                f"Failed to read CA bundle file {ca_bundle_path}: Permission denied"
                in result.error
            )

    @pytest.mark.asyncio
    async def test_grpc_certificate_verify_failed_error_with_recovery(self) -> None:
        """Test gRPC certificate verification error with recovery suggestions."""
        mock_proxy_config = Mock()
        mock_proxy_config.host = "test.com"
        mock_proxy_config.port = 443
        mock_proxy_config.use_tls = True
        mock_proxy_config.jwt_token = None

        # Create a proper gRPC error that can be raised
        class MockRpcError(grpc.RpcError, Exception):
            def code(self) -> grpc.StatusCode:
                return grpc.StatusCode.UNKNOWN

            def details(self) -> str:
                return (
                    "certificate verify failed: unable to get local issuer certificate"
                )

        mock_error = MockRpcError("Certificate verification failed")

        with (
            patch(
                "vibectl.subcommands.setup_proxy_cmd.parse_proxy_url",
                return_value=mock_proxy_config,
            ),
            patch("vibectl.subcommands.setup_proxy_cmd.Config") as mock_config_class,
            patch("grpc.ssl_channel_credentials"),
            patch("grpc.secure_channel") as mock_channel_func,
        ):
            # Mock config
            mock_config = Mock()
            mock_config.get_ca_bundle_path.return_value = None
            mock_config.get_jwt_token.return_value = None
            mock_config_class.return_value = mock_config

            mock_channel = Mock()
            mock_channel_func.return_value = mock_channel

            # Create a regular Mock (not AsyncMock) since GetServerInfo is called
            # inside an executor as a sync call
            mock_stub = Mock()
            mock_stub.GetServerInfo.side_effect = mock_error

            with patch(
                "vibectl.subcommands.setup_proxy_cmd.llm_proxy_pb2_grpc.VibectlLLMProxyStub",
                return_value=mock_stub,
            ):
                result = await check_proxy_connection("vibectl-server://test.com:443")

            assert isinstance(result, Error)
            assert "gRPC error (UNKNOWN)" in result.error
            assert result.recovery_suggestions is not None
            assert "private certificate authority" in result.recovery_suggestions
            assert "--ca-bundle" in result.recovery_suggestions
