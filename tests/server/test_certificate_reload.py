"""
Tests for certificate reload functionality.

Tests cover the _reload_server_certificates function and its behavior
with different types of server targets (ALPNMultiplexer vs GRPCServer).
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from vibectl.server.main import _reload_server_certificates


class TestReloadServerCertificates:
    """Test certificate reload functionality for different server types."""

    def test_reload_certificates_alpn_multiplexer_success(self) -> None:
        """Test successful hot certificate reload for ALPNMultiplexer."""
        # Create mock ALPNMultiplexer with _ssl_context
        mock_multiplexer = Mock()
        mock_ssl_context = Mock()
        mock_multiplexer._ssl_context = mock_ssl_context
        mock_multiplexer.cert_file = "/old/cert.crt"
        mock_multiplexer.key_file = "/old/key.key"

        # Test certificate reload
        _reload_server_certificates(mock_multiplexer, "/new/cert.crt", "/new/key.key")

        # Verify hot reload was performed
        mock_ssl_context.load_cert_chain.assert_called_once_with(
            "/new/cert.crt", "/new/key.key"
        )

        # Verify certificate paths were updated
        assert mock_multiplexer.cert_file == "/new/cert.crt"
        assert mock_multiplexer.key_file == "/new/key.key"

    def test_reload_certificates_alpn_multiplexer_missing_ssl_context(self) -> None:
        """Test ALPNMultiplexer without _ssl_context attribute."""
        # Create mock multiplexer without _ssl_context
        mock_multiplexer = Mock(spec=[])  # Empty spec, no _ssl_context attribute

        with patch("vibectl.server.main.logger") as mock_logger:
            _reload_server_certificates(
                mock_multiplexer, "/new/cert.crt", "/new/key.key"
            )

            # Should fall back to warning
            mock_logger.warning.assert_called_once()
            assert "Hot certificate reload not supported" in str(
                mock_logger.warning.call_args
            )

    def test_reload_certificates_grpc_server_success(self) -> None:
        """Test successful certificate reload for GRPCServer (requires restart)."""
        # Import GRPCServer to create a proper instance
        from vibectl.server.grpc_server import GRPCServer

        # Create mock GRPCServer
        mock_grpc_server = Mock(spec=GRPCServer)
        mock_grpc_server.cert_file = "/old/cert.crt"
        mock_grpc_server.key_file = "/old/key.key"

        # Test certificate reload
        _reload_server_certificates(mock_grpc_server, "/new/cert.crt", "/new/key.key")

        # Verify server was restarted
        mock_grpc_server.stop.assert_called_once_with(grace_period=2.0)
        mock_grpc_server.start.assert_called_once()

        # Verify certificate paths were updated
        assert mock_grpc_server.cert_file == "/new/cert.crt"
        assert mock_grpc_server.key_file == "/new/key.key"

    def test_reload_certificates_grpc_server_stop_failure(self) -> None:
        """Test GRPCServer restart when stop() raises exception."""
        from vibectl.server.grpc_server import GRPCServer

        # Create mock GRPCServer that fails to stop
        mock_grpc_server = Mock(spec=GRPCServer)
        mock_grpc_server.stop.side_effect = Exception("Stop failed")

        with patch("vibectl.server.main.logger") as mock_logger:
            _reload_server_certificates(
                mock_grpc_server, "/new/cert.crt", "/new/key.key"
            )

            # Should log error
            mock_logger.error.assert_called_once()
            assert "Failed to hot-reload certificates" in str(
                mock_logger.error.call_args
            )

            # Should not call start() after stop() failure
            mock_grpc_server.start.assert_not_called()

    def test_reload_certificates_grpc_server_start_failure(self) -> None:
        """Test GRPCServer restart when start() raises exception."""
        from vibectl.server.grpc_server import GRPCServer

        # Create mock GRPCServer that fails to start
        mock_grpc_server = Mock(spec=GRPCServer)
        mock_grpc_server.start.side_effect = Exception("Start failed")

        with patch("vibectl.server.main.logger") as mock_logger:
            _reload_server_certificates(
                mock_grpc_server, "/new/cert.crt", "/new/key.key"
            )

            # Should call stop() successfully
            mock_grpc_server.stop.assert_called_once_with(grace_period=2.0)

            # Should attempt start() but fail
            mock_grpc_server.start.assert_called_once()

            # Should log error
            mock_logger.error.assert_called_once()
            assert "Failed to hot-reload certificates" in str(
                mock_logger.error.call_args
            )

    def test_reload_certificates_unsupported_target(self) -> None:
        """Test certificate reload with unsupported target type."""

        # Create a simple object that doesn't have _ssl_context and isn't a GRPCServer
        class UnsupportedServer:
            pass

        mock_target = UnsupportedServer()

        with patch("vibectl.server.main.logger") as mock_logger:
            _reload_server_certificates(mock_target, "/new/cert.crt", "/new/key.key")

            # Should log warning about unsupported target
            mock_logger.warning.assert_called_once()
            # The warning is called with a format string and an argument
            warning_args = mock_logger.warning.call_args[0]
            assert len(warning_args) == 2  # Format string and type name
            assert (
                "Hot certificate reload not supported for target %s" in warning_args[0]
            )
            assert warning_args[1] == "UnsupportedServer"

    def test_reload_certificates_alpn_multiplexer_load_cert_chain_failure(self) -> None:
        """Test ALPNMultiplexer when load_cert_chain fails."""
        # Create mock ALPNMultiplexer with _ssl_context that fails
        mock_multiplexer = Mock()
        mock_ssl_context = Mock()
        mock_ssl_context.load_cert_chain.side_effect = Exception("SSL load failed")
        mock_multiplexer._ssl_context = mock_ssl_context

        with patch("vibectl.server.main.logger") as mock_logger:
            _reload_server_certificates(
                mock_multiplexer, "/new/cert.crt", "/new/key.key"
            )

            # Should attempt load_cert_chain
            mock_ssl_context.load_cert_chain.assert_called_once_with(
                "/new/cert.crt", "/new/key.key"
            )

            # Should log error
            mock_logger.error.assert_called_once()
            assert "Failed to hot-reload certificates" in str(
                mock_logger.error.call_args
            )

    def test_reload_certificates_logs_certificate_info(self) -> None:
        """Test that certificate reload logs the certificate paths."""
        # Create mock ALPNMultiplexer
        mock_multiplexer = Mock()
        mock_ssl_context = Mock()
        mock_multiplexer._ssl_context = mock_ssl_context

        with patch("vibectl.server.main.logger") as mock_logger:
            _reload_server_certificates(
                mock_multiplexer, "/test/cert.crt", "/test/key.key"
            )

            # Should log reload request with certificate paths
            mock_logger.info.assert_any_call(
                "Certificate reload requested: cert=%s, key=%s",
                "/test/cert.crt",
                "/test/key.key",
            )

            # Should log success
            mock_logger.info.assert_any_call(
                "🔄 Hot certificate reload completed successfully"
            )


class TestCertificateReloadIntegration:
    """Integration tests for certificate reload with real certificate files."""

    def test_reload_certificates_with_real_files(self) -> None:
        """Test certificate reload with actual certificate files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test certificate files
            cert_file = Path(temp_dir) / "test.crt"
            key_file = Path(temp_dir) / "test.key"

            cert_content = (
                "-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----"
            )
            key_content = "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----"

            cert_file.write_text(cert_content)
            key_file.write_text(key_content)

            # Create mock ALPNMultiplexer
            mock_multiplexer = Mock()
            mock_ssl_context = Mock()
            mock_multiplexer._ssl_context = mock_ssl_context

            # Test certificate reload with real file paths
            _reload_server_certificates(mock_multiplexer, str(cert_file), str(key_file))

            # Verify load_cert_chain was called with real paths
            mock_ssl_context.load_cert_chain.assert_called_once_with(
                str(cert_file), str(key_file)
            )
