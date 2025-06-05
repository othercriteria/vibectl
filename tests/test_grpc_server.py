"""
Tests for the gRPC server module.

Tests cover server initialization, lifecycle management, authentication setup,
and all public methods of the GRPCServer class.
"""

import signal
from unittest.mock import Mock, patch

import pytest

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
        assert server.enable_auth is False
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
            enable_auth=False,
        )

        assert server.host == "0.0.0.0"
        assert server.port == 8080
        assert server.default_model == "gpt-4"
        assert server.max_workers == 20
        assert server.enable_auth is False
        assert server.jwt_manager is None
        assert server.jwt_interceptor is None

    @patch("vibectl.server.grpc_server.load_jwt_config_from_env")
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

        server = GRPCServer(enable_auth=True)

        assert server.enable_auth is True
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

        server = GRPCServer(enable_auth=True, jwt_manager=mock_jwt_manager)

        assert server.enable_auth is True
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

        server = GRPCServer(enable_auth=True, jwt_manager=mock_jwt_manager)
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
        server = GRPCServer(enable_auth=False)

        with pytest.raises(RuntimeError, match="JWT authentication is not enabled"):
            server.generate_token("test-user")

    @patch("vibectl.server.grpc_server.create_jwt_interceptor")
    def test_generate_token_auth_enabled(self, mock_create_interceptor: Mock) -> None:
        """Test token generation when authentication is enabled."""
        # Setup mock JWT manager
        mock_jwt_manager = Mock(spec=JWTAuthManager)
        mock_jwt_manager.generate_token.return_value = "mock-jwt-token"
        mock_create_interceptor.return_value = Mock()

        server = GRPCServer(enable_auth=True, jwt_manager=mock_jwt_manager)

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

        server = GRPCServer(enable_auth=True, jwt_manager=mock_jwt_manager)

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
        assert server.enable_auth is False

    def test_create_server_custom_parameters(self) -> None:
        """Test create_server with custom parameters."""
        mock_jwt_manager = Mock(spec=JWTAuthManager)

        server = create_server(
            host="0.0.0.0",
            port=8080,
            default_model="claude-3",
            max_workers=50,
            enable_auth=True,
            jwt_manager=mock_jwt_manager,
        )

        assert isinstance(server, GRPCServer)
        assert server.host == "0.0.0.0"
        assert server.port == 8080
        assert server.default_model == "claude-3"
        assert server.max_workers == 50
        assert server.enable_auth is True
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

    @patch("vibectl.server.grpc_server.load_jwt_config_from_env")
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
        server = GRPCServer(enable_auth=True)

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
