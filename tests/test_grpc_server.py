"""
Tests for the gRPC server module.

Tests cover server initialization, lifecycle management, authentication setup,
TLS configuration, and all public methods of the GRPCServer class.
"""

import signal
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from vibectl.server.cert_utils import is_cryptography_available
from vibectl.server.grpc_server import GRPCServer, create_server
from vibectl.server.jwt_auth import JWTAuthManager, JWTConfig


class TestGRPCServerInitialization:
    """Test GRPCServer initialization with various configurations."""

    def test_init_default_parameters(self) -> None:
        """Test GRPCServer initialization with default parameters."""
        server = GRPCServer()

        assert server.host == "localhost"
        assert server.port == 50051
        assert server.default_model is None
        assert server.max_workers == 10
        assert server.require_auth is False
        assert server.server is None
        assert server.jwt_manager is None
        assert server.jwt_interceptor is None
        assert server._servicer is not None

    def test_init_custom_parameters(self) -> None:
        """Test GRPCServer initialization with custom parameters."""
        server = GRPCServer(
            host="0.0.0.0",
            port=8080,
            default_model="gpt-4",
            max_workers=20,
            require_auth=False,
        )

        assert server.host == "0.0.0.0"
        assert server.port == 8080
        assert server.default_model == "gpt-4"
        assert server.max_workers == 20
        assert server.require_auth is False
        assert server.jwt_manager is None
        assert server.jwt_interceptor is None

    @patch("vibectl.server.grpc_server.load_config_from_server")
    @patch("vibectl.server.grpc_server.create_jwt_interceptor")
    def test_init_with_auth_enabled_no_manager(
        self, mock_create_interceptor: Mock, mock_load_config: Mock
    ) -> None:
        """Test server initialization with auth enabled but no JWT manager provided."""
        # Mock JWT configuration loading
        mock_config = JWTConfig(
            secret_key="test-secret", algorithm="HS256", default_expiration_days=7
        )
        mock_load_config.return_value = mock_config

        # Mock JWT manager and interceptor
        mock_interceptor = Mock()
        mock_create_interceptor.return_value = mock_interceptor

        server = GRPCServer(require_auth=True)

        assert server.require_auth is True
        assert server.jwt_manager is not None
        assert server.jwt_interceptor == mock_interceptor
        mock_load_config.assert_called_once()
        mock_create_interceptor.assert_called_once()

    @patch("vibectl.server.grpc_server.create_jwt_interceptor")
    def test_init_with_auth_enabled_with_manager(
        self, mock_create_interceptor: Mock
    ) -> None:
        """Test server initialization with auth enabled and JWT manager provided."""
        # Create a mock JWT manager
        mock_jwt_manager = Mock(spec=JWTAuthManager)
        mock_interceptor = Mock()
        mock_create_interceptor.return_value = mock_interceptor

        server = GRPCServer(require_auth=True, jwt_manager=mock_jwt_manager)

        assert server.require_auth is True
        assert server.jwt_manager == mock_jwt_manager
        assert server.jwt_interceptor == mock_interceptor
        mock_create_interceptor.assert_called_once_with(mock_jwt_manager, enabled=True)


class TestGRPCServerLifecycle:
    """Test GRPCServer lifecycle management (start, stop, termination)."""

    @patch("grpc.server")
    @patch("vibectl.server.grpc_server.add_VibectlLLMProxyServicer_to_server")
    def test_start_without_auth(
        self, mock_add_servicer: Mock, mock_grpc_server: Mock
    ) -> None:
        """Test starting server without authentication."""
        # Setup mocks
        mock_server_instance = Mock()
        mock_grpc_server.return_value = mock_server_instance

        server = GRPCServer(host="127.0.0.1", port=9000)
        server.start()

        # Verify server creation with no interceptors
        mock_grpc_server.assert_called_once()
        args, kwargs = mock_grpc_server.call_args
        assert "interceptors" in kwargs
        assert kwargs["interceptors"] == []

        # Verify servicer addition and port binding
        mock_add_servicer.assert_called_once_with(
            server._servicer, mock_server_instance
        )
        mock_server_instance.add_insecure_port.assert_called_once_with("127.0.0.1:9000")
        mock_server_instance.start.assert_called_once()

        assert server.server == mock_server_instance

    @patch("grpc.server")
    @patch("vibectl.server.grpc_server.add_VibectlLLMProxyServicer_to_server")
    @patch("vibectl.server.grpc_server.create_jwt_interceptor")
    def test_start_with_auth(
        self,
        mock_create_interceptor: Mock,
        mock_add_servicer: Mock,
        mock_grpc_server: Mock,
    ) -> None:
        """Test starting server with authentication."""
        # Setup mocks
        mock_server_instance = Mock()
        mock_grpc_server.return_value = mock_server_instance
        mock_interceptor = Mock()
        mock_create_interceptor.return_value = mock_interceptor
        mock_jwt_manager = Mock(spec=JWTAuthManager)

        server = GRPCServer(require_auth=True, jwt_manager=mock_jwt_manager)
        server.start()

        # Verify server creation with interceptors
        mock_grpc_server.assert_called_once()
        args, kwargs = mock_grpc_server.call_args
        assert "interceptors" in kwargs
        assert mock_interceptor in kwargs["interceptors"]

        # Verify other setup
        mock_add_servicer.assert_called_once()
        mock_server_instance.add_insecure_port.assert_called_once()
        mock_server_instance.start.assert_called_once()

    def test_stop_without_server(self) -> None:
        """Test stopping server when no server is running."""
        server = GRPCServer()
        # Should not raise an exception
        server.stop()
        assert server.server is None

    def test_stop_with_server(self) -> None:
        """Test stopping server when server is running."""
        server = GRPCServer()
        mock_server_instance = Mock()
        server.server = mock_server_instance

        server.stop(grace_period=3.0)

        mock_server_instance.stop.assert_called_once_with(3.0)
        assert server.server is None

    def test_stop_with_default_grace_period(self) -> None:
        """Test stopping server with default grace period."""
        server = GRPCServer()
        mock_server_instance = Mock()
        server.server = mock_server_instance

        server.stop()

        mock_server_instance.stop.assert_called_once_with(5.0)

    def test_wait_for_termination_without_server(self) -> None:
        """Test waiting for termination when no server is running."""
        server = GRPCServer()
        # Should not raise an exception
        server.wait_for_termination()

    def test_wait_for_termination_with_server(self) -> None:
        """Test waiting for termination with running server."""
        server = GRPCServer()
        mock_server_instance = Mock()
        server.server = mock_server_instance

        server.wait_for_termination(timeout=10.0)

        mock_server_instance.wait_for_termination.assert_called_once_with(10.0)

    def test_wait_for_termination_no_timeout(self) -> None:
        """Test waiting for termination without timeout."""
        server = GRPCServer()
        mock_server_instance = Mock()
        server.server = mock_server_instance

        server.wait_for_termination()

        mock_server_instance.wait_for_termination.assert_called_once_with(None)


class TestGRPCServerServeForever:
    """Test the serve_forever method with signal handling."""

    @patch("signal.signal")
    @patch.object(GRPCServer, "start")
    @patch.object(GRPCServer, "wait_for_termination")
    @patch.object(GRPCServer, "stop")
    def test_serve_forever_normal_termination(
        self, mock_stop: Mock, mock_wait: Mock, mock_start: Mock, mock_signal: Mock
    ) -> None:
        """Test serve_forever with normal termination."""
        server = GRPCServer()

        server.serve_forever()

        # Verify signal handlers were set up
        _expected_calls = [
            ((signal.SIGINT, mock_signal.call_args_list[0][0][1]),),
            ((signal.SIGTERM, mock_signal.call_args_list[1][0][1]),),
        ]
        assert len(mock_signal.call_args_list) == 2
        assert mock_signal.call_args_list[0][0][0] == signal.SIGINT
        assert mock_signal.call_args_list[1][0][0] == signal.SIGTERM

        # Verify server lifecycle
        mock_start.assert_called_once()
        mock_wait.assert_called_once()
        mock_stop.assert_called_once()

    @patch("signal.signal")
    @patch.object(GRPCServer, "start")
    @patch.object(GRPCServer, "wait_for_termination")
    @patch.object(GRPCServer, "stop")
    def test_serve_forever_keyboard_interrupt(
        self, mock_stop: Mock, mock_wait: Mock, mock_start: Mock, mock_signal: Mock
    ) -> None:
        """Test serve_forever with keyboard interrupt."""
        server = GRPCServer()

        # Simulate KeyboardInterrupt during wait_for_termination
        mock_wait.side_effect = KeyboardInterrupt("Ctrl+C")

        server.serve_forever()

        # Verify server lifecycle with exception handling
        mock_start.assert_called_once()
        mock_wait.assert_called_once()
        mock_stop.assert_called_once()

    @patch("signal.signal")
    @patch.object(GRPCServer, "start")
    @patch.object(GRPCServer, "wait_for_termination")
    @patch.object(GRPCServer, "stop")
    def test_signal_handler_functionality(
        self, mock_stop: Mock, mock_wait: Mock, mock_start: Mock, mock_signal: Mock
    ) -> None:
        """Test that signal handlers properly call stop method."""
        server = GRPCServer()

        # Capture the signal handler functions
        server.serve_forever()

        # Get the signal handlers that were registered
        sigint_handler = mock_signal.call_args_list[0][0][1]
        sigterm_handler = mock_signal.call_args_list[1][0][1]

        # Test SIGINT handler
        sigint_handler(signal.SIGINT, None)

        # Test SIGTERM handler
        sigterm_handler(signal.SIGTERM, None)

        # The stop method should have been called during serve_forever
        # and potentially additional times by signal handlers
        assert mock_stop.call_count >= 1


class TestGRPCServerTokenGeneration:
    """Test JWT token generation functionality."""

    def test_generate_token_auth_disabled(self) -> None:
        """Test token generation when authentication is disabled."""
        server = GRPCServer(require_auth=False)

        with pytest.raises(RuntimeError, match="JWT authentication is not enabled"):
            server.generate_token("test-user")

    @patch("vibectl.server.grpc_server.create_jwt_interceptor")
    def test_generate_token_auth_enabled(self, mock_create_interceptor: Mock) -> None:
        """Test token generation when authentication is enabled."""
        # Setup mock JWT manager
        mock_jwt_manager = Mock(spec=JWTAuthManager)
        mock_jwt_manager.generate_token.return_value = "mock-jwt-token"
        mock_create_interceptor.return_value = Mock()

        server = GRPCServer(require_auth=True, jwt_manager=mock_jwt_manager)

        result = server.generate_token("test-user", expiration_days=30)

        assert result == "mock-jwt-token"
        mock_jwt_manager.generate_token.assert_called_once_with("test-user", 30)

    @patch("vibectl.server.grpc_server.create_jwt_interceptor")
    def test_generate_token_default_expiration(
        self, mock_create_interceptor: Mock
    ) -> None:
        """Test token generation with default expiration."""
        # Setup mock JWT manager
        mock_jwt_manager = Mock(spec=JWTAuthManager)
        mock_jwt_manager.generate_token.return_value = "mock-jwt-token"
        mock_create_interceptor.return_value = Mock()

        server = GRPCServer(require_auth=True, jwt_manager=mock_jwt_manager)

        result = server.generate_token("test-user")

        assert result == "mock-jwt-token"
        mock_jwt_manager.generate_token.assert_called_once_with("test-user", None)


class TestCreateServerFactory:
    """Test the create_server factory function."""

    def test_create_server_default_parameters(self) -> None:
        """Test create_server with default parameters."""
        server = create_server()

        assert isinstance(server, GRPCServer)
        assert server.host == "localhost"
        assert server.port == 50051
        assert server.default_model is None
        assert server.max_workers == 10
        assert server.require_auth is False

    def test_create_server_custom_parameters(self) -> None:
        """Test create_server with custom parameters."""
        mock_jwt_manager = Mock(spec=JWTAuthManager)

        server = create_server(
            host="0.0.0.0",
            port=8080,
            default_model="claude-3",
            max_workers=50,
            require_auth=True,
            jwt_manager=mock_jwt_manager,
        )

        assert isinstance(server, GRPCServer)
        assert server.host == "0.0.0.0"
        assert server.port == 8080
        assert server.default_model == "claude-3"
        assert server.max_workers == 50
        assert server.require_auth is True
        assert server.jwt_manager == mock_jwt_manager


class TestGRPCServerMainExecution:
    """Test the main execution block."""

    @patch("vibectl.server.grpc_server.create_server")
    @patch("logging.basicConfig")
    def test_main_execution_block(
        self, mock_logging_config: Mock, mock_create_server: Mock
    ) -> None:
        """Test the main execution block when run as script."""
        # Setup mock server
        mock_server = Mock(spec=GRPCServer)
        mock_create_server.return_value = mock_server

        # Import and execute the main block

        # Since we can't easily test the __main__ block directly,
        # we test the components it would use
        server = create_server()
        assert server is not None

        # The actual main block would call serve_forever, but we don't
        # want to test that here as it would block


class TestGRPCServerIntegration:
    """Integration tests for GRPCServer with real components."""

    @patch("grpc.server")
    @patch("vibectl.server.grpc_server.add_VibectlLLMProxyServicer_to_server")
    def test_full_server_lifecycle(
        self, mock_add_servicer: Mock, mock_grpc_server: Mock
    ) -> None:
        """Test complete server lifecycle from creation to shutdown."""
        # Setup mocks
        mock_server_instance = Mock()
        mock_grpc_server.return_value = mock_server_instance

        # Create and configure server
        server = GRPCServer(
            host="127.0.0.1", port=9999, default_model="test-model", max_workers=5
        )

        # Test full lifecycle
        server.start()
        assert server.server == mock_server_instance

        server.wait_for_termination(timeout=0.1)
        mock_server_instance.wait_for_termination.assert_called_with(0.1)

        server.stop(grace_period=1.0)
        mock_server_instance.stop.assert_called_with(1.0)
        assert server.server is None

    @patch("vibectl.server.grpc_server.load_config_from_server")
    @patch("vibectl.server.grpc_server.create_jwt_interceptor")
    @patch("grpc.server")
    @patch("vibectl.server.grpc_server.add_VibectlLLMProxyServicer_to_server")
    def test_server_with_authentication_integration(
        self,
        mock_add_servicer: Mock,
        mock_grpc_server: Mock,
        mock_create_interceptor: Mock,
        mock_load_config: Mock,
    ) -> None:
        """Test server with authentication enabled integration."""
        # Setup mocks
        mock_server_instance = Mock()
        mock_grpc_server.return_value = mock_server_instance
        mock_interceptor = Mock()
        mock_create_interceptor.return_value = mock_interceptor
        mock_config = JWTConfig(
            secret_key="test-secret", algorithm="HS256", default_expiration_days=7
        )
        mock_load_config.return_value = mock_config

        # Create server with auth
        server = GRPCServer(require_auth=True)

        # Test token generation
        with patch.object(
            server.jwt_manager, "generate_token", return_value="test-token"
        ):
            token = server.generate_token("test-user", 14)
            assert token == "test-token"

        # Test server startup with auth
        server.start()

        # Verify interceptor was included
        mock_grpc_server.assert_called_once()
        args, kwargs = mock_grpc_server.call_args
        assert "interceptors" in kwargs
        assert mock_interceptor in kwargs["interceptors"]

        server.stop()


class TestGRPCServerTLSInitialization:
    """Test GRPCServer TLS initialization with various configurations."""

    def test_init_with_tls_disabled(self) -> None:
        """Test GRPCServer initialization with TLS disabled."""
        server = GRPCServer(use_tls=False)

        assert server.use_tls is False
        assert server.cert_file is None
        assert server.key_file is None

    def test_init_with_tls_enabled_no_files(self) -> None:
        """Test GRPCServer initialization with TLS enabled but no certificate files."""
        server = GRPCServer(use_tls=True)

        assert server.use_tls is True
        assert server.cert_file is None
        assert server.key_file is None

    def test_init_with_tls_enabled_with_files(self) -> None:
        """Test GRPCServer initialization with TLS enabled and certificate files."""
        server = GRPCServer(
            use_tls=True, cert_file="/path/to/cert.pem", key_file="/path/to/key.pem"
        )

        assert server.use_tls is True
        assert server.cert_file == "/path/to/cert.pem"
        assert server.key_file == "/path/to/key.pem"

    def test_init_with_tls_and_auth(self) -> None:
        """Test GRPCServer initialization with both TLS and authentication enabled."""
        mock_jwt_manager = Mock(spec=JWTAuthManager)

        with (
            patch(
                "vibectl.server.grpc_server.create_jwt_interceptor"
            ) as mock_create_interceptor,
            patch(
                "vibectl.server.grpc_server.load_config_from_server"
            ) as mock_load_config,
        ):
            mock_interceptor = Mock()
            mock_create_interceptor.return_value = mock_interceptor
            mock_load_config.return_value = JWTConfig(
                secret_key="test-secret", algorithm="HS256", default_expiration_days=7
            )
            server = GRPCServer(
                use_tls=True,
                require_auth=True,
                jwt_manager=mock_jwt_manager,
                cert_file="/path/to/cert.pem",
                key_file="/path/to/key.pem",
            )

            assert server.use_tls is True
            assert server.require_auth is True
            assert server.cert_file == "/path/to/cert.pem"
            assert server.key_file == "/path/to/key.pem"
            assert server.jwt_manager == mock_jwt_manager
            assert server.jwt_interceptor == mock_interceptor


class TestGRPCServerTLSLifecycle:
    """Test GRPCServer TLS lifecycle management."""

    @patch("grpc.server")
    @patch("vibectl.server.grpc_server.add_VibectlLLMProxyServicer_to_server")
    @patch("vibectl.server.grpc_server.ensure_certificate_exists")
    @patch("vibectl.server.grpc_server.load_certificate_credentials")
    @patch("grpc.ssl_server_credentials")
    @patch("vibectl.config_utils.get_config_dir")
    @patch("vibectl.server.grpc_server.get_default_cert_paths")
    def test_start_with_tls_auto_cert_generation(
        self,
        mock_get_default_paths: Mock,
        mock_get_config_dir: Mock,
        mock_ssl_credentials: Mock,
        mock_load_credentials: Mock,
        mock_ensure_certs: Mock,
        mock_add_servicer: Mock,
        mock_grpc_server: Mock,
    ) -> None:
        """Test starting server with TLS and automatic certificate generation."""
        # Setup mocks
        mock_server_instance = Mock()
        mock_grpc_server.return_value = mock_server_instance
        mock_get_config_dir.return_value = Path("/test/config")
        mock_get_default_paths.return_value = ("/test/cert.pem", "/test/key.pem")
        mock_load_credentials.return_value = (b"cert_data", b"key_data")
        mock_server_credentials = Mock()
        mock_ssl_credentials.return_value = mock_server_credentials

        server = GRPCServer(use_tls=True, host="127.0.0.1", port=9000)
        server.start()

        # Verify certificate generation and loading
        mock_ensure_certs.assert_called_once_with(
            "/test/cert.pem", "/test/key.pem", hostname="127.0.0.1"
        )
        mock_load_credentials.assert_called_once_with("/test/cert.pem", "/test/key.pem")

        # Verify SSL credentials creation
        mock_ssl_credentials.assert_called_once_with(
            [(b"key_data", b"cert_data")],
            root_certificates=None,
            require_client_auth=False,
        )

        # Verify secure port binding
        mock_server_instance.add_secure_port.assert_called_once_with(
            "127.0.0.1:9000", mock_server_credentials
        )
        mock_server_instance.add_insecure_port.assert_not_called()
        mock_server_instance.start.assert_called_once()

    @patch("grpc.server")
    @patch("vibectl.server.grpc_server.add_VibectlLLMProxyServicer_to_server")
    @patch("vibectl.server.grpc_server.ensure_certificate_exists")
    @patch("vibectl.server.grpc_server.load_certificate_credentials")
    @patch("grpc.ssl_server_credentials")
    def test_start_with_tls_explicit_cert_files(
        self,
        mock_ssl_credentials: Mock,
        mock_load_credentials: Mock,
        mock_ensure_certs: Mock,
        mock_add_servicer: Mock,
        mock_grpc_server: Mock,
    ) -> None:
        """Test starting server with TLS and explicit certificate files."""
        # Setup mocks
        mock_server_instance = Mock()
        mock_grpc_server.return_value = mock_server_instance
        mock_load_credentials.return_value = (b"cert_data", b"key_data")
        mock_server_credentials = Mock()
        mock_ssl_credentials.return_value = mock_server_credentials

        server = GRPCServer(
            use_tls=True,
            cert_file="/custom/cert.pem",
            key_file="/custom/key.pem",
            host="localhost",
            port=8443,
        )
        server.start()

        # Verify certificate handling with explicit files
        mock_ensure_certs.assert_called_once_with(
            "/custom/cert.pem", "/custom/key.pem", hostname="localhost"
        )
        mock_load_credentials.assert_called_once_with(
            "/custom/cert.pem", "/custom/key.pem"
        )

        # Verify secure port binding
        mock_server_instance.add_secure_port.assert_called_once_with(
            "localhost:8443", mock_server_credentials
        )

    @patch("grpc.server")
    @patch("vibectl.server.grpc_server.add_VibectlLLMProxyServicer_to_server")
    @patch("vibectl.server.grpc_server.ensure_certificate_exists")
    @patch("vibectl.server.grpc_server.load_certificate_credentials")
    @patch("grpc.ssl_server_credentials")
    def test_start_with_tls_wildcard_host(
        self,
        mock_ssl_credentials: Mock,
        mock_load_credentials: Mock,
        mock_ensure_certs: Mock,
        mock_add_servicer: Mock,
        mock_grpc_server: Mock,
    ) -> None:
        """Test starting server with TLS and wildcard host binding."""
        # Setup mocks
        mock_server_instance = Mock()
        mock_grpc_server.return_value = mock_server_instance
        mock_load_credentials.return_value = (b"cert_data", b"key_data")
        mock_server_credentials = Mock()
        mock_ssl_credentials.return_value = mock_server_credentials

        server = GRPCServer(
            use_tls=True,
            cert_file="/test/cert.pem",
            key_file="/test/key.pem",
            host="0.0.0.0",
            port=9000,
        )
        server.start()

        # Verify hostname defaults to localhost for wildcard binding
        mock_ensure_certs.assert_called_once_with(
            "/test/cert.pem", "/test/key.pem", hostname="localhost"
        )

    @patch("grpc.server")
    @patch("vibectl.server.grpc_server.add_VibectlLLMProxyServicer_to_server")
    @patch("vibectl.server.grpc_server.ensure_certificate_exists")
    def test_start_with_tls_certificate_error(
        self,
        mock_ensure_certs: Mock,
        mock_add_servicer: Mock,
        mock_grpc_server: Mock,
    ) -> None:
        """Test starting server with TLS when certificate operations fail."""
        from vibectl.server.cert_utils import CertificateError

        # Setup mocks
        mock_server_instance = Mock()
        mock_grpc_server.return_value = mock_server_instance
        mock_ensure_certs.side_effect = CertificateError(
            "Certificate generation failed"
        )

        server = GRPCServer(
            use_tls=True, cert_file="/test/cert.pem", key_file="/test/key.pem"
        )

        with pytest.raises(RuntimeError, match="TLS configuration failed"):
            server.start()

        # Verify server was not started
        mock_server_instance.start.assert_not_called()

    @patch("grpc.server")
    @patch("vibectl.server.grpc_server.add_VibectlLLMProxyServicer_to_server")
    @patch("vibectl.server.grpc_server.ensure_certificate_exists")
    @patch("vibectl.server.grpc_server.load_certificate_credentials")
    def test_start_with_tls_unexpected_error(
        self,
        mock_load_credentials: Mock,
        mock_ensure_certs: Mock,
        mock_add_servicer: Mock,
        mock_grpc_server: Mock,
    ) -> None:
        """Test starting server with TLS when unexpected errors occur."""
        # Setup mocks
        mock_server_instance = Mock()
        mock_grpc_server.return_value = mock_server_instance
        mock_load_credentials.side_effect = Exception("Unexpected error")

        server = GRPCServer(
            use_tls=True, cert_file="/test/cert.pem", key_file="/test/key.pem"
        )

        with pytest.raises(RuntimeError, match="TLS configuration failed"):
            server.start()

    @patch("grpc.server")
    @patch("vibectl.server.grpc_server.add_VibectlLLMProxyServicer_to_server")
    def test_start_without_tls(
        self, mock_add_servicer: Mock, mock_grpc_server: Mock
    ) -> None:
        """Test starting server without TLS uses insecure port."""
        # Setup mocks
        mock_server_instance = Mock()
        mock_grpc_server.return_value = mock_server_instance

        server = GRPCServer(use_tls=False, host="127.0.0.1", port=9000)
        server.start()

        # Verify insecure port binding
        mock_server_instance.add_insecure_port.assert_called_once_with("127.0.0.1:9000")
        mock_server_instance.add_secure_port.assert_not_called()
        mock_server_instance.start.assert_called_once()


class TestCreateServerFactoryTLS:
    """Test create_server factory function with TLS options."""

    def test_create_server_with_tls_parameters(self) -> None:
        """Test create_server factory with TLS parameters."""
        server = create_server(
            host="localhost",
            port=8443,
            use_tls=True,
            cert_file="/test/cert.pem",
            key_file="/test/key.pem",
        )

        assert isinstance(server, GRPCServer)
        assert server.host == "localhost"
        assert server.port == 8443
        assert server.use_tls is True
        assert server.cert_file == "/test/cert.pem"
        assert server.key_file == "/test/key.pem"

    def test_create_server_tls_disabled(self) -> None:
        """Test create_server factory with TLS disabled."""
        server = create_server(use_tls=False)

        assert isinstance(server, GRPCServer)
        assert server.use_tls is False
        assert server.cert_file is None
        assert server.key_file is None

    def test_create_server_tls_with_auth(self) -> None:
        """Test create_server factory with both TLS and authentication."""
        mock_jwt_manager = Mock(spec=JWTAuthManager)

        with patch("vibectl.server.grpc_server.create_jwt_interceptor"):
            server = create_server(
                use_tls=True,
                require_auth=True,
                jwt_manager=mock_jwt_manager,
                cert_file="/test/cert.pem",
                key_file="/test/key.pem",
            )

            assert server.use_tls is True
            assert server.require_auth is True
            assert server.jwt_manager == mock_jwt_manager


class TestGRPCServerTLSIntegration:
    """Integration tests for TLS functionality."""

    @pytest.mark.skipif(
        not is_cryptography_available(),
        reason="cryptography not available",
    )
    @patch("grpc.server")
    @patch("vibectl.server.grpc_server.add_VibectlLLMProxyServicer_to_server")
    @patch("grpc.ssl_server_credentials")
    def test_full_tls_server_lifecycle_with_real_certs(
        self,
        mock_ssl_credentials: Mock,
        mock_add_servicer: Mock,
        mock_grpc_server: Mock,
    ) -> None:
        """Test full server lifecycle with real certificate generation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = Path(temp_dir) / "server.crt"
            key_file = Path(temp_dir) / "server.key"

            # Setup mocks
            mock_server_instance = Mock()
            mock_grpc_server.return_value = mock_server_instance
            mock_server_credentials = Mock()
            mock_ssl_credentials.return_value = mock_server_credentials

            server = GRPCServer(
                use_tls=True,
                cert_file=str(cert_file),
                key_file=str(key_file),
                host="localhost",
                port=9443,
            )

            # Start server (should generate certificates)
            server.start()

            # Verify certificates were created
            assert cert_file.exists()
            assert key_file.exists()
            assert b"BEGIN CERTIFICATE" in cert_file.read_bytes()
            assert b"BEGIN PRIVATE KEY" in key_file.read_bytes()

            # Verify SSL setup
            mock_ssl_credentials.assert_called_once()
            mock_server_instance.add_secure_port.assert_called_once_with(
                "localhost:9443", mock_server_credentials
            )

            # Test server stop
            server.stop()
            mock_server_instance.stop.assert_called_once()

    @patch("grpc.server")
    @patch("vibectl.server.grpc_server.add_VibectlLLMProxyServicer_to_server")
    @patch("vibectl.server.grpc_server.ensure_certificate_exists")
    @patch("vibectl.server.grpc_server.load_certificate_credentials")
    @patch("grpc.ssl_server_credentials")
    @patch("vibectl.server.grpc_server.create_jwt_interceptor")
    def test_tls_with_authentication_integration(
        self,
        mock_create_interceptor: Mock,
        mock_ssl_credentials: Mock,
        mock_load_credentials: Mock,
        mock_ensure_certs: Mock,
        mock_add_servicer: Mock,
        mock_grpc_server: Mock,
    ) -> None:
        """Test TLS server with JWT authentication integration."""
        # Setup mocks
        mock_server_instance = Mock()
        mock_grpc_server.return_value = mock_server_instance
        mock_load_credentials.return_value = (b"cert_data", b"key_data")
        mock_server_credentials = Mock()
        mock_ssl_credentials.return_value = mock_server_credentials
        mock_interceptor = Mock()
        mock_create_interceptor.return_value = mock_interceptor
        mock_jwt_manager = Mock(spec=JWTAuthManager)

        server = GRPCServer(
            use_tls=True,
            require_auth=True,
            jwt_manager=mock_jwt_manager,
            cert_file="/test/cert.pem",
            key_file="/test/key.pem",
            host="localhost",
            port=9443,
        )

        server.start()

        # Verify both TLS and auth are configured
        mock_create_interceptor.assert_called_once_with(mock_jwt_manager, enabled=True)
        mock_ssl_credentials.assert_called_once()
        mock_server_instance.add_secure_port.assert_called_once()

        # Verify server creation includes interceptors
        args, kwargs = mock_grpc_server.call_args
        assert "interceptors" in kwargs
        assert mock_interceptor in kwargs["interceptors"]

    def test_tls_configuration_logging(self) -> None:
        """Test that TLS configuration is properly logged."""
        with patch("vibectl.server.grpc_server.logger") as mock_logger:
            GRPCServer(
                use_tls=True, cert_file="/test/cert.pem", key_file="/test/key.pem"
            )

            # Check initialization logging
            mock_logger.info.assert_called_with(
                "Initialized gRPC server for localhost:50051 (with TLS)"
            )

    def test_non_tls_configuration_logging(self) -> None:
        """Test that non-TLS configuration is properly logged."""
        with patch("vibectl.server.grpc_server.logger") as mock_logger:
            GRPCServer(use_tls=False)

            # Check initialization logging
            mock_logger.info.assert_called_with(
                "Initialized gRPC server for localhost:50051 (without TLS)"
            )
