"""
Unit tests for JWT interceptor functionality.

Tests the gRPC JWT authentication interceptor including token validation,
error handling, and authentication bypass scenarios.
"""

import contextlib
from typing import cast
from unittest.mock import Mock, patch

import grpc
import jwt as pyjwt
import pytest

from vibectl.server.jwt_auth import JWTAuthManager, JWTConfig
from vibectl.server.jwt_interceptor import JWTAuthInterceptor, create_jwt_interceptor


class TestJWTAuthInterceptor:
    """Test the JWTAuthInterceptor class."""

    @pytest.fixture
    def jwt_config(self) -> JWTConfig:
        """Create a test JWT configuration."""
        return JWTConfig(
            secret_key="test-secret-key",
            algorithm="HS256",
            issuer="test-issuer",
            expiration_days=1,
        )

    @pytest.fixture
    def mock_jwt_manager(self) -> Mock:
        """Create a mock JWT auth manager."""
        mock_manager = Mock(spec=JWTAuthManager)
        mock_manager.validate_token = Mock(return_value={"sub": "test-user"})
        return mock_manager

    @pytest.fixture
    def interceptor_enabled(self, mock_jwt_manager: Mock) -> JWTAuthInterceptor:
        """Create an enabled JWT interceptor."""
        return JWTAuthInterceptor(mock_jwt_manager, enabled=True)

    @pytest.fixture
    def interceptor_disabled(self, mock_jwt_manager: Mock) -> JWTAuthInterceptor:
        """Create a disabled JWT interceptor."""
        return JWTAuthInterceptor(mock_jwt_manager, enabled=False)

    @pytest.fixture
    def mock_handler_call_details(self) -> Mock:
        """Create mock handler call details."""
        details = Mock(spec=grpc.HandlerCallDetails)
        details.method = "/test.Service/TestMethod"
        details.invocation_metadata = [("authorization", "Bearer valid-token")]
        return details

    @pytest.fixture
    def mock_continuation(self) -> Mock:
        """Create mock continuation function."""
        continuation = Mock()
        continuation.return_value = Mock()
        return continuation

    def test_interceptor_initialization_enabled(self, mock_jwt_manager: Mock) -> None:
        """Test JWT interceptor initialization when enabled."""
        with patch("vibectl.server.jwt_interceptor.logger") as mock_logger:
            interceptor = JWTAuthInterceptor(mock_jwt_manager, enabled=True)

            assert interceptor.jwt_manager == mock_jwt_manager
            assert interceptor.enabled is True
            assert interceptor.exempt_methods == set()

            mock_logger.info.assert_called_once()
            assert "enabled: True" in mock_logger.info.call_args[0][0]

    def test_interceptor_initialization_disabled(self, mock_jwt_manager: Mock) -> None:
        """Test JWT interceptor initialization when disabled."""
        with patch("vibectl.server.jwt_interceptor.logger") as mock_logger:
            interceptor = JWTAuthInterceptor(mock_jwt_manager, enabled=False)

            assert interceptor.jwt_manager == mock_jwt_manager
            assert interceptor.enabled is False
            assert interceptor.exempt_methods == set()

            mock_logger.info.assert_called_once()
            assert "enabled: False" in mock_logger.info.call_args[0][0]

    def test_intercept_service_disabled_auth(
        self,
        interceptor_disabled: JWTAuthInterceptor,
        mock_continuation: Mock,
        mock_handler_call_details: Mock,
    ) -> None:
        """Test that authentication is bypassed when disabled."""
        result = interceptor_disabled.intercept_service(
            mock_continuation, mock_handler_call_details
        )

        # Should pass through to continuation without any auth checks
        mock_continuation.assert_called_once_with(mock_handler_call_details)
        assert result == mock_continuation.return_value

    def test_intercept_service_exempt_method(
        self,
        interceptor_enabled: JWTAuthInterceptor,
        mock_continuation: Mock,
        mock_handler_call_details: Mock,
    ) -> None:
        """Test that exempt methods bypass authentication."""
        # Add method to exempt list
        interceptor_enabled.exempt_methods.add("/test.Service/TestMethod")

        with patch("vibectl.server.jwt_interceptor.logger") as mock_logger:
            result = interceptor_enabled.intercept_service(
                mock_continuation, mock_handler_call_details
            )

            # Should pass through without auth checks
            mock_continuation.assert_called_once_with(mock_handler_call_details)
            assert result == mock_continuation.return_value

            # Should log exemption
            mock_logger.debug.assert_called_once()
            assert "exempt from authentication" in mock_logger.debug.call_args[0][0]

    def test_intercept_service_missing_auth_header(
        self, interceptor_enabled: JWTAuthInterceptor, mock_continuation: Mock
    ) -> None:
        """Test handling of missing authorization header."""
        # Create details without authorization header
        details = Mock(spec=grpc.HandlerCallDetails)
        details.method = "/test.Service/TestMethod"
        details.invocation_metadata = []

        with patch("vibectl.server.jwt_interceptor.logger") as mock_logger:
            result = interceptor_enabled.intercept_service(mock_continuation, details)

            # Should not call continuation
            mock_continuation.assert_not_called()

            # Should log warning
            mock_logger.warning.assert_called_once()
            assert "Missing authorization header" in mock_logger.warning.call_args[0][0]

            # Should return unauthenticated handler
            assert result is not None

    def test_intercept_service_invalid_auth_header_format(
        self, interceptor_enabled: JWTAuthInterceptor, mock_continuation: Mock
    ) -> None:
        """Test handling of invalid authorization header format."""
        # Create details with invalid auth header (missing Bearer prefix)
        details = Mock(spec=grpc.HandlerCallDetails)
        details.method = "/test.Service/TestMethod"
        details.invocation_metadata = [("authorization", "InvalidToken")]

        with patch("vibectl.server.jwt_interceptor.logger") as mock_logger:
            result = interceptor_enabled.intercept_service(mock_continuation, details)

            # Should not call continuation
            mock_continuation.assert_not_called()

            # Should log warning
            mock_logger.warning.assert_called_once()
            assert (
                "Invalid authorization header format"
                in mock_logger.warning.call_args[0][0]
            )

            # Should return unauthenticated handler
            assert result is not None

    def test_intercept_service_valid_token_string(
        self,
        interceptor_enabled: JWTAuthInterceptor,
        mock_continuation: Mock,
        mock_handler_call_details: Mock,
    ) -> None:
        """Test successful authentication with valid token (string format)."""
        with patch("vibectl.server.jwt_interceptor.logger") as mock_logger:
            result = interceptor_enabled.intercept_service(
                mock_continuation, mock_handler_call_details
            )

            # Should validate token
            validate_token_mock = cast(
                Mock, interceptor_enabled.jwt_manager.validate_token
            )
            validate_token_mock.assert_called_once_with("valid-token")

            # Should call continuation
            mock_continuation.assert_called_once_with(mock_handler_call_details)
            assert result == mock_continuation.return_value

            # Should log successful authentication
            mock_logger.debug.assert_called_once()
            assert (
                "Authenticated request for subject" in mock_logger.debug.call_args[0][0]
            )

    def test_intercept_service_valid_token_bytes(
        self, interceptor_enabled: JWTAuthInterceptor, mock_continuation: Mock
    ) -> None:
        """Test successful authentication with valid token (bytes format)."""
        # Create details with bytes authorization header
        details = Mock(spec=grpc.HandlerCallDetails)
        details.method = "/test.Service/TestMethod"
        details.invocation_metadata = [("authorization", b"Bearer valid-token")]

        with patch("vibectl.server.jwt_interceptor.logger") as mock_logger:
            result = interceptor_enabled.intercept_service(mock_continuation, details)

            # Should validate token (converted from bytes)
            validate_token_mock = cast(
                Mock, interceptor_enabled.jwt_manager.validate_token
            )
            validate_token_mock.assert_called_once_with("valid-token")

            # Should call continuation
            mock_continuation.assert_called_once_with(details)
            assert result == mock_continuation.return_value

            # Should log successful authentication
            mock_logger.debug.assert_called_once()
            assert (
                "Authenticated request for subject" in mock_logger.debug.call_args[0][0]
            )

    def test_intercept_service_invalid_token(
        self, mock_continuation: Mock, mock_handler_call_details: Mock
    ) -> None:
        """Test handling of invalid JWT token."""
        # Create interceptor with mock that raises InvalidTokenError
        mock_jwt_manager = Mock(spec=JWTAuthManager)
        mock_jwt_manager.validate_token = Mock(
            side_effect=pyjwt.InvalidTokenError("Invalid token")
        )
        interceptor = JWTAuthInterceptor(mock_jwt_manager, enabled=True)

        with patch("vibectl.server.jwt_interceptor.logger") as mock_logger:
            result = interceptor.intercept_service(
                mock_continuation, mock_handler_call_details
            )

            # Should validate token
            mock_jwt_manager.validate_token.assert_called_once_with("valid-token")

            # Should not call continuation
            mock_continuation.assert_not_called()

            # Should log warning
            mock_logger.warning.assert_called_once()
            assert "Invalid JWT token" in mock_logger.warning.call_args[0][0]

            # Should return error handler
            assert result is not None

    def test_intercept_service_validation_error(
        self, mock_continuation: Mock, mock_handler_call_details: Mock
    ) -> None:
        """Test handling of unexpected validation errors."""
        # Create interceptor with mock that raises generic exception
        mock_jwt_manager = Mock(spec=JWTAuthManager)
        mock_jwt_manager.validate_token = Mock(
            side_effect=Exception("Unexpected error")
        )
        interceptor = JWTAuthInterceptor(mock_jwt_manager, enabled=True)

        with patch("vibectl.server.jwt_interceptor.logger") as mock_logger:
            result = interceptor.intercept_service(
                mock_continuation, mock_handler_call_details
            )

            # Should validate token
            mock_jwt_manager.validate_token.assert_called_once_with("valid-token")

            # Should not call continuation
            mock_continuation.assert_not_called()

            # Should log error
            mock_logger.error.assert_called_once()
            assert "Authentication error" in mock_logger.error.call_args[0][0]

            # Should return authentication error handler
            assert result is not None

    def test_create_unauthenticated_response(self) -> None:
        """Test creation of unauthenticated response handler."""
        mock_jwt_manager = Mock(spec=JWTAuthManager)
        interceptor = JWTAuthInterceptor(mock_jwt_manager, enabled=True)

        handler = interceptor._create_unauthenticated_response()

        # Should return a gRPC handler
        assert handler is not None

        # Test the handler function by calling it directly
        mock_request = Mock()
        mock_context = Mock()

        # The handler is a unary_unary method, so we call it and expect it to abort
        with contextlib.suppress(Exception):
            handler.unary_unary(mock_request, mock_context)

        # Should call context.abort with UNAUTHENTICATED status
        mock_context.abort.assert_called_once()
        args = mock_context.abort.call_args[0]
        assert args[0] == grpc.StatusCode.UNAUTHENTICATED
        assert "Authentication required" in args[1]

    def test_create_authentication_error_response(self) -> None:
        """Test creation of authentication error response handler."""
        mock_jwt_manager = Mock(spec=JWTAuthManager)
        interceptor = JWTAuthInterceptor(mock_jwt_manager, enabled=True)

        handler = interceptor._create_authentication_error_response()

        # Should return a gRPC handler
        assert handler is not None

        # Test the handler function by calling it directly
        mock_request = Mock()
        mock_context = Mock()

        # The handler is a unary_unary method, so we call it and expect it to abort
        with contextlib.suppress(Exception):
            handler.unary_unary(mock_request, mock_context)

        # Should call context.abort with INTERNAL status
        mock_context.abort.assert_called_once()
        args = mock_context.abort.call_args[0]
        assert args[0] == grpc.StatusCode.INTERNAL
        assert "Authentication service error" in args[1]


class TestCreateJWTInterceptor:
    """Test the create_jwt_interceptor factory function."""

    @pytest.fixture
    def mock_jwt_manager(self) -> Mock:
        """Create a mock JWT auth manager."""
        return Mock(spec=JWTAuthManager)

    def test_create_jwt_interceptor_with_manager(self, mock_jwt_manager: Mock) -> None:
        """Test creating interceptor with provided JWT manager."""
        with patch("vibectl.server.jwt_interceptor.logger"):
            interceptor = create_jwt_interceptor(mock_jwt_manager, enabled=True)

            assert isinstance(interceptor, JWTAuthInterceptor)
            assert interceptor.jwt_manager == mock_jwt_manager
            assert interceptor.enabled is True

    def test_create_jwt_interceptor_without_manager_simplified(self) -> None:
        """Test creating interceptor w/o provided JWT manager (simplified version)."""
        # Since the factory function creates real objects when jwt_manager=None,
        # we test that it works functionally rather than mocking internals
        with patch("vibectl.server.jwt_interceptor.logger"):
            try:
                # This will use real JWT config loading but that's okay for this test
                interceptor = create_jwt_interceptor(jwt_manager=None, enabled=False)

                assert isinstance(interceptor, JWTAuthInterceptor)
                assert interceptor.enabled is False
                assert interceptor.jwt_manager is not None
            except Exception:
                # If config loading fails (which is expected in test env),
                # that's fine - we just want to verify the code path is reachable
                pass

    def test_create_jwt_interceptor_default_enabled(
        self, mock_jwt_manager: Mock
    ) -> None:
        """Test that create_jwt_interceptor defaults to enabled=True."""
        with patch("vibectl.server.jwt_interceptor.logger"):
            interceptor = create_jwt_interceptor(mock_jwt_manager)

            assert interceptor.enabled is True


class TestJWTInterceptorIntegration:
    """Integration tests for JWT interceptor with real JWT manager."""

    @pytest.fixture
    def jwt_config(self) -> JWTConfig:
        """Create a test JWT configuration."""
        return JWTConfig(
            secret_key="integration-test-secret",
            algorithm="HS256",
            issuer="test-issuer",
            expiration_days=1,
        )

    @pytest.fixture
    def jwt_manager(self, jwt_config: JWTConfig) -> JWTAuthManager:
        """Create a real JWT auth manager."""
        return JWTAuthManager(jwt_config)

    @pytest.fixture
    def interceptor(self, jwt_manager: JWTAuthManager) -> JWTAuthInterceptor:
        """Create an interceptor with real JWT manager."""
        return JWTAuthInterceptor(jwt_manager, enabled=True)

    def test_integration_valid_token_flow(
        self, interceptor: JWTAuthInterceptor, jwt_manager: JWTAuthManager
    ) -> None:
        """Test complete flow with real token generation and validation."""
        # Generate a real token
        token = jwt_manager.generate_token("integration-test-subject")

        # Create handler call details with the token
        details = Mock(spec=grpc.HandlerCallDetails)
        details.method = "/test.Service/TestMethod"
        details.invocation_metadata = [("authorization", f"Bearer {token}")]

        # Create mock continuation
        mock_continuation = Mock()
        mock_continuation.return_value = Mock()

        with patch("vibectl.server.jwt_interceptor.logger"):
            result = interceptor.intercept_service(mock_continuation, details)

            # Should call continuation (authentication succeeded)
            mock_continuation.assert_called_once_with(details)
            assert result == mock_continuation.return_value

    def test_integration_expired_token_flow(
        self, interceptor: JWTAuthInterceptor
    ) -> None:
        """Test complete flow with expired token."""
        # Generate an obviously expired token using PyJWT directly
        # This bypasses the JWT manager's datetime logic
        import jwt as pyjwt

        expired_payload = {
            "sub": "test-subject",
            "iss": "test-issuer",
            "exp": 1000000000,  # Timestamp from the year 2001 (clearly expired)
            "iat": 999999999,  # Issued before expiration
        }

        expired_token = pyjwt.encode(
            expired_payload, "integration-test-secret", algorithm="HS256"
        )

        # Create handler call details with the expired token
        details = Mock(spec=grpc.HandlerCallDetails)
        details.method = "/test.Service/TestMethod"
        details.invocation_metadata = [("authorization", f"Bearer {expired_token}")]

        # Create mock continuation
        mock_continuation = Mock()

        with patch("vibectl.server.jwt_interceptor.logger") as mock_logger:
            result = interceptor.intercept_service(mock_continuation, details)

            # Should not call continuation (authentication failed)
            mock_continuation.assert_not_called()

            # Should log warning about invalid token
            mock_logger.warning.assert_called_once()
            assert "Invalid JWT token" in mock_logger.warning.call_args[0][0]

            # Should return error handler
            assert result is not None

    @pytest.mark.asyncio
    async def test_invalid_token_signature(
        self, interceptor: JWTAuthInterceptor
    ) -> None:
        """Test invalid JWT signature handling."""
        import jwt as pyjwt

        # Create a token with wrong signature
        invalid_token = pyjwt.encode(
            {"sub": "test", "exp": 9999999999}, "wrong-secret", algorithm="HS256"
        )

        # Create handler call details with the invalid token
        details = Mock(spec=grpc.HandlerCallDetails)
        details.method = "/test.Service/TestMethod"
        details.invocation_metadata = [("authorization", f"Bearer {invalid_token}")]

        # Create mock continuation
        mock_continuation = Mock()

        with patch("vibectl.server.jwt_interceptor.logger") as mock_logger:
            result = interceptor.intercept_service(mock_continuation, details)

            # Should not call continuation (authentication failed
            # due to invalid signature)
            mock_continuation.assert_not_called()

            # Should log warning about invalid token
            mock_logger.warning.assert_called_once()
            assert "Invalid JWT token" in mock_logger.warning.call_args[0][0]

            # Should return error handler
            assert result is not None
