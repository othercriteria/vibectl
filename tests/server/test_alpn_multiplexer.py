"""
Tests for ALPN multiplexing server functionality.

Tests basic server lifecycle, handler registration, and connection routing
without requiring actual network connections.
"""

import asyncio
import contextlib
import ssl
import tempfile
import unittest.mock
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from vibectl.server.alpn_multiplexer import (
    ALPNMultiplexer,
    GRPCHandler,
    TLSALPNHandler,
    create_alpn_multiplexer_for_acme,
)
from vibectl.server.cert_utils import generate_self_signed_certificate


# Helper function to create valid test certificates
def _create_test_certificates() -> tuple[str, str]:
    """Create valid test certificates for SSL context testing.

    Returns:
        Tuple of (cert_file_path, key_file_path)
    """
    cert_data, key_data = generate_self_signed_certificate(
        hostname="test.local",
        days_valid=1,  # Short validity for tests
    )

    # Create temporary files
    with tempfile.NamedTemporaryFile(
        mode="wb", suffix=".pem", delete=False
    ) as cert_file:
        cert_file.write(cert_data)
        cert_file.flush()
        cert_file_name = cert_file.name

    with tempfile.NamedTemporaryFile(
        mode="wb", suffix=".pem", delete=False
    ) as key_file:
        key_file.write(key_data)
        key_file.flush()
        key_file_name = key_file.name

    return cert_file_name, key_file_name


class TestGRPCHandler:
    """Test gRPC handler for ALPN multiplexing."""

    def test_init_default_values(self) -> None:
        """Test handler initialization with default values."""
        handler = GRPCHandler()

        assert handler.grpc_server_port == 50051

    def test_init_custom_values(self) -> None:
        """Test handler initialization with custom values."""
        handler = GRPCHandler(grpc_server_port=8080)

        assert handler.grpc_server_port == 8080

    @patch("asyncio.open_connection")
    async def test_handle_connection_success(
        self, mock_open_connection: AsyncMock
    ) -> None:
        """Test successful connection handling."""
        handler = GRPCHandler()

        # Mock upstream connection
        mock_upstream_reader = AsyncMock()
        mock_upstream_writer = Mock()
        mock_upstream_writer.write = Mock()
        mock_upstream_writer.drain = AsyncMock()
        mock_upstream_writer.close = Mock()
        mock_upstream_writer.wait_closed = AsyncMock()
        mock_open_connection.return_value = (mock_upstream_reader, mock_upstream_writer)

        # Mock client connection with proper sync/async split
        mock_client_reader = AsyncMock()
        mock_client_writer = Mock()
        mock_client_writer.write = Mock()
        mock_client_writer.drain = AsyncMock()
        mock_client_writer.close = Mock()
        mock_client_writer.wait_closed = AsyncMock()
        mock_client_writer.is_closing.return_value = False

        # Mock data flow - simulate connection closing naturally
        mock_client_reader.read.side_effect = [b"test_data", b""]  # EOF
        mock_upstream_reader.read.side_effect = [b"response_data", b""]  # EOF

        await handler.handle_connection(mock_client_reader, mock_client_writer)

        # Verify upstream connection was established
        mock_open_connection.assert_called_once_with("127.0.0.1", 50051)

    @patch("asyncio.open_connection")
    async def test_handle_connection_upstream_failure(
        self, mock_open_connection: AsyncMock
    ) -> None:
        """Test connection handling when upstream connection fails."""
        handler = GRPCHandler()
        mock_open_connection.side_effect = OSError("Connection refused")

        mock_client_reader = AsyncMock()
        # Use regular Mock for the writer, but make async methods AsyncMock
        mock_client_writer = Mock()
        mock_client_writer.is_closing.return_value = False
        mock_client_writer.close = Mock()
        mock_client_writer.wait_closed = AsyncMock()

        # Should handle the error gracefully
        await handler.handle_connection(mock_client_reader, mock_client_writer)

        # In the implementation, when open_connection fails, the exception is caught
        # and logged, then cleanup happens in the finally block
        mock_client_writer.close.assert_called_once()
        mock_client_writer.wait_closed.assert_called_once()


class TestTLSALPNHandler:
    """Test TLS-ALPN handler for ALPN multiplexing."""

    def test_init(self) -> None:
        """Test handler initialization."""
        mock_tls_alpn_server = Mock()
        handler = TLSALPNHandler(mock_tls_alpn_server)

        assert handler.tls_alpn_server == mock_tls_alpn_server

    async def test_handle_connection_success(self) -> None:
        """Test successful connection handling."""
        mock_tls_alpn_server = AsyncMock()
        handler = TLSALPNHandler(mock_tls_alpn_server)

        mock_reader = AsyncMock()
        # Use Mock() for synchronous methods and AsyncMock() for async methods
        mock_writer = Mock()
        mock_ssl_object = Mock()
        mock_writer.get_extra_info.return_value = mock_ssl_object
        mock_writer.is_closing.return_value = False
        mock_writer.close = Mock()  # Synchronous method
        mock_writer.wait_closed = AsyncMock()  # Asynchronous method

        await handler.handle_connection(mock_reader, mock_writer)

        # Verify SSL object was extracted and connection was closed per RFC 8737
        # Should have calls for both peername (logging) and ssl_object (functionality)
        expected_calls = [
            unittest.mock.call("ssl_object"),
            unittest.mock.call("peername", "unknown"),
        ]
        mock_writer.get_extra_info.assert_has_calls(expected_calls, any_order=True)
        mock_writer.close.assert_called_once()
        mock_writer.wait_closed.assert_called_once()

    async def test_handle_connection_error(self) -> None:
        """Test connection handling with error."""
        mock_tls_alpn_server = AsyncMock()
        handler = TLSALPNHandler(mock_tls_alpn_server)

        mock_reader = AsyncMock()
        # Use Mock() for synchronous methods and AsyncMock() for async methods
        mock_writer = Mock()
        # Simulate get_extra_info raising an exception
        mock_writer.get_extra_info.side_effect = Exception("Test error")
        mock_writer.is_closing.return_value = False
        mock_writer.close = Mock()  # Synchronous method
        mock_writer.wait_closed = AsyncMock()  # Asynchronous method

        await handler.handle_connection(mock_reader, mock_writer)

        # Connection should still be closed despite the error per RFC 8737
        mock_writer.close.assert_called_once()
        mock_writer.wait_closed.assert_called_once()


class TestALPNMultiplexer:
    """Test ALPN multiplexing server."""

    def test_init_default_values(self) -> None:
        """Test multiplexer initialization with default values."""
        multiplexer = ALPNMultiplexer()

        assert multiplexer.host == "0.0.0.0"
        assert multiplexer.port == 443
        assert multiplexer.cert_file is None
        assert multiplexer.key_file is None
        assert not multiplexer.is_running
        assert len(multiplexer._handlers) == 0

    def test_init_custom_values(self) -> None:
        """Test multiplexer initialization with custom values."""
        multiplexer = ALPNMultiplexer(
            host="127.0.0.1",
            port=8443,
            cert_file="/path/to/cert.pem",
            key_file="/path/to/key.pem",
        )

        assert multiplexer.host == "127.0.0.1"
        assert multiplexer.port == 8443
        assert multiplexer.cert_file == "/path/to/cert.pem"
        assert multiplexer.key_file == "/path/to/key.pem"

    def test_register_handler(self) -> None:
        """Test registering ALPN protocol handlers."""
        multiplexer = ALPNMultiplexer()
        mock_handler = Mock()

        multiplexer.register_handler("h2", mock_handler)

        assert "h2" in multiplexer._handlers
        assert multiplexer._handlers["h2"] == mock_handler

    def test_create_ssl_context_success(self) -> None:
        """Test SSL context creation with valid certificates."""
        with (
            tempfile.NamedTemporaryFile(suffix=".pem") as cert_file,
            tempfile.NamedTemporaryFile(suffix=".pem") as key_file,
        ):
            # Write dummy certificate data
            cert_file.write(
                b"-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----"
            )
            cert_file.flush()
            key_file.write(
                b"-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----"
            )
            key_file.flush()

            multiplexer = ALPNMultiplexer(
                cert_file=cert_file.name, key_file=key_file.name
            )
            multiplexer.register_handler("h2", Mock())

            with patch("ssl.create_default_context") as mock_ssl_context:
                mock_context = Mock()
                mock_ssl_context.return_value = mock_context

                context = multiplexer._create_ssl_context()

                assert context == mock_context
                mock_context.load_cert_chain.assert_called_once_with(
                    cert_file.name, key_file.name
                )
                mock_context.set_alpn_protocols.assert_called_once_with(["h2"])

    def test_create_ssl_context_no_certs(self) -> None:
        """Test SSL context creation without certificates."""
        multiplexer = ALPNMultiplexer()

        with pytest.raises(ValueError, match="cert_file and key_file must be provided"):
            multiplexer._create_ssl_context()

    async def test_handle_connection_success(self) -> None:
        """Test successful connection handling with ALPN protocol."""
        multiplexer = ALPNMultiplexer()

        mock_handler = AsyncMock()
        multiplexer.register_handler("h2", mock_handler)

        mock_reader = AsyncMock()
        # Use proper Mock setup for the writer
        mock_writer = Mock()
        mock_writer.is_closing.return_value = False
        mock_writer.close = Mock()
        mock_writer.wait_closed = AsyncMock()

        # Mock SSL object with ALPN protocol - fix the method call issue
        mock_ssl_object = Mock()
        mock_ssl_object.selected_alpn_protocol = Mock(return_value="h2")
        mock_ssl_object.version = Mock(return_value="TLSv1.3")

        # Fix the get_extra_info to return the SSL object directly
        mock_writer.get_extra_info = Mock(return_value=mock_ssl_object)

        await multiplexer._handle_connection(mock_reader, mock_writer)

        mock_handler.handle_connection.assert_called_once_with(mock_reader, mock_writer)

    async def test_handle_connection_no_ssl(self) -> None:
        """Test connection handling with no SSL object."""
        multiplexer = ALPNMultiplexer()

        mock_reader = AsyncMock()
        # Use regular Mock for sync methods, AsyncMock for async methods
        mock_writer = Mock()
        mock_writer.is_closing.return_value = False
        mock_writer.close = Mock()
        mock_writer.wait_closed = AsyncMock()

        # Fix get_extra_info to return None properly
        mock_writer.get_extra_info = Mock(return_value=None)

        await multiplexer._handle_connection(mock_reader, mock_writer)

        # The implementation now properly cleans up connections in error scenarios
        mock_writer.close.assert_called_once()
        mock_writer.wait_closed.assert_called_once()

    async def test_handle_connection_no_alpn(self) -> None:
        """Test connection handling with no ALPN protocol."""
        multiplexer = ALPNMultiplexer()

        mock_reader = AsyncMock()
        # Use regular Mock for sync methods, AsyncMock for async methods
        mock_writer = Mock()
        mock_writer.is_closing.return_value = False
        mock_writer.close = Mock()
        mock_writer.wait_closed = AsyncMock()

        mock_ssl_object = Mock()
        mock_ssl_object.selected_alpn_protocol = Mock(return_value=None)
        mock_ssl_object.version = Mock(return_value="TLSv1.3")

        # Fix get_extra_info to return SSL object properly
        mock_writer.get_extra_info = Mock(return_value=mock_ssl_object)

        await multiplexer._handle_connection(mock_reader, mock_writer)

        # The implementation now properly cleans up connections in error scenarios
        mock_writer.close.assert_called_once()
        mock_writer.wait_closed.assert_called_once()

    async def test_handle_connection_unknown_protocol(self) -> None:
        """Test connection handling with unknown ALPN protocol."""
        multiplexer = ALPNMultiplexer()
        multiplexer.register_handler("h2", Mock())

        mock_reader = AsyncMock()
        # Use regular Mock for sync methods, AsyncMock for async methods
        mock_writer = Mock()
        mock_writer.is_closing.return_value = False
        mock_writer.close = Mock()
        mock_writer.wait_closed = AsyncMock()

        mock_ssl_object = Mock()
        mock_ssl_object.selected_alpn_protocol = Mock(return_value="unknown-protocol")
        mock_ssl_object.version = Mock(return_value="TLSv1.3")

        # Fix get_extra_info to return SSL object properly
        mock_writer.get_extra_info = Mock(return_value=mock_ssl_object)

        await multiplexer._handle_connection(mock_reader, mock_writer)

        # The implementation now properly cleans up connections in error scenarios
        mock_writer.close.assert_called_once()
        mock_writer.wait_closed.assert_called_once()

    async def test_start_stop_lifecycle(self) -> None:
        """Test server start/stop lifecycle."""
        with (
            tempfile.NamedTemporaryFile(suffix=".pem") as cert_file,
            tempfile.NamedTemporaryFile(suffix=".pem") as key_file,
        ):
            # Write dummy certificate data
            cert_file.write(
                b"-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----"
            )
            cert_file.flush()
            key_file.write(
                b"-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----"
            )
            key_file.flush()

            multiplexer = ALPNMultiplexer(
                port=0,  # Use port 0 for random available port
                cert_file=cert_file.name,
                key_file=key_file.name,
            )
            multiplexer.register_handler("h2", Mock())

            # Initially not running
            assert not multiplexer.is_running

            with patch("ssl.create_default_context"):
                # Start the server
                await multiplexer.start()
                assert multiplexer.is_running

                # Stop the server
                await multiplexer.stop()
                assert not multiplexer.is_running

    async def test_start_no_handlers(self) -> None:
        """Test starting server with no handlers."""
        multiplexer = ALPNMultiplexer()

        with pytest.raises(ValueError, match="No ALPN handlers registered"):
            await multiplexer.start()

    async def test_wait_until_ready_success(self) -> None:
        """Test waiting for server to be ready."""
        with (
            tempfile.NamedTemporaryFile(suffix=".pem") as cert_file,
            tempfile.NamedTemporaryFile(suffix=".pem") as key_file,
        ):
            cert_file.write(
                b"-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----"
            )
            cert_file.flush()
            key_file.write(
                b"-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----"
            )
            key_file.flush()

            multiplexer = ALPNMultiplexer(
                port=0, cert_file=cert_file.name, key_file=key_file.name
            )
            multiplexer.register_handler("h2", Mock())

            with patch("ssl.create_default_context"):
                # Start server in background
                start_task = asyncio.create_task(multiplexer.start())

                # Wait for it to be ready
                ready = await multiplexer.wait_until_ready(timeout=2.0)
                assert ready
                assert multiplexer.is_running

                # Clean up
                await multiplexer.stop()
                await start_task

    async def test_wait_until_ready_timeout(self) -> None:
        """Test timeout while waiting for server to be ready."""
        multiplexer = ALPNMultiplexer(port=0)

        # Don't start the server
        ready = await multiplexer.wait_until_ready(timeout=0.1)
        assert not ready

    async def test_handle_connection_exception_in_protocol_handler(self) -> None:
        """Test connection handling when protocol handler raises exception."""
        multiplexer = ALPNMultiplexer()

        mock_handler = AsyncMock()
        mock_handler.handle_connection.side_effect = Exception("Handler error")
        multiplexer.register_handler("h2", mock_handler)

        mock_reader = AsyncMock()
        mock_writer = Mock()
        mock_writer.is_closing.return_value = False
        mock_writer.close = Mock()
        mock_writer.wait_closed = AsyncMock()

        mock_ssl_object = Mock()
        mock_ssl_object.selected_alpn_protocol = Mock(return_value="h2")
        mock_ssl_object.version = Mock(return_value="TLSv1.3")
        mock_writer.get_extra_info = Mock(return_value=mock_ssl_object)

        await multiplexer._handle_connection(mock_reader, mock_writer)

        # Handler should have been called
        mock_handler.handle_connection.assert_called_once_with(mock_reader, mock_writer)
        # Connection should still be cleaned up
        mock_writer.close.assert_called_once()
        mock_writer.wait_closed.assert_called_once()

    async def test_handle_connection_writer_already_closing(self) -> None:
        """Test connection handling when writer is already closing."""
        multiplexer = ALPNMultiplexer()

        mock_handler = AsyncMock()
        multiplexer.register_handler("h2", mock_handler)

        mock_reader = AsyncMock()
        mock_writer = Mock()
        mock_writer.is_closing.return_value = True  # Already closing
        mock_writer.close = Mock()
        mock_writer.wait_closed = AsyncMock()

        mock_ssl_object = Mock()
        mock_ssl_object.selected_alpn_protocol = Mock(return_value="h2")
        mock_ssl_object.version = Mock(return_value="TLSv1.3")
        mock_writer.get_extra_info = Mock(return_value=mock_ssl_object)

        await multiplexer._handle_connection(mock_reader, mock_writer)

        # Handler should have been called
        mock_handler.handle_connection.assert_called_once_with(mock_reader, mock_writer)
        # Close should not be called since writer is already closing
        mock_writer.close.assert_not_called()
        mock_writer.wait_closed.assert_not_called()

    async def test_start_error_cleanup(self) -> None:
        """Test cleanup happens when start fails."""
        multiplexer = ALPNMultiplexer(cert_file="/nonexistent", key_file="/nonexistent")
        multiplexer.register_handler("h2", Mock())

        # Mock cleanup method to verify it's called
        with patch.object(
            multiplexer, "_cleanup", new_callable=AsyncMock
        ) as mock_cleanup:
            with contextlib.suppress(Exception):
                await multiplexer.start()

            # Cleanup should have been called
            mock_cleanup.assert_called_once()

    async def test_start_multiple_calls(self) -> None:
        """Test calling start multiple times."""
        # Generate valid test certificates
        cert_file_path, key_file_path = _create_test_certificates()

        try:
            multiplexer = ALPNMultiplexer(
                port=0,  # Use random available port
                cert_file=cert_file_path,
                key_file=key_file_path,
            )
            multiplexer.register_handler("h2", Mock())

            await multiplexer.start()

            # Should succeed without error when called again
            await multiplexer.start()

            # Should be running
            assert multiplexer.is_running

            # Clean up
            await multiplexer.stop()
        finally:
            # Clean up test certificate files
            import os

            try:
                os.unlink(cert_file_path)
                os.unlink(key_file_path)
            except OSError:
                pass

    async def test_stop_multiple_calls(self) -> None:
        """Test calling stop multiple times."""
        multiplexer = ALPNMultiplexer()

        # Should not raise error even when not running
        await multiplexer.stop()
        await multiplexer.stop()

        assert not multiplexer.is_running

    async def test_cleanup_exception_handling(self) -> None:
        """Test cleanup handles exceptions gracefully."""
        multiplexer = ALPNMultiplexer()

        # Mock server to raise exception during cleanup
        mock_server = Mock()
        mock_server.close = Mock()
        mock_server.wait_closed = AsyncMock(side_effect=Exception("Cleanup error"))
        multiplexer._server = mock_server

        # Should not raise exception - the method catches and logs exceptions
        try:
            await multiplexer._cleanup()
        except Exception:
            pytest.fail("_cleanup should not raise exceptions")

        # Server should be set to None even when exceptions occur
        assert multiplexer._server is None

    async def test_wait_until_ready_already_ready(self) -> None:
        """Test wait_until_ready when server is already ready."""
        # Generate valid test certificates
        cert_file_path, key_file_path = _create_test_certificates()

        try:
            multiplexer = ALPNMultiplexer(
                port=0, cert_file=cert_file_path, key_file=key_file_path
            )
            multiplexer.register_handler("h2", Mock())

            await multiplexer.start()

            # Should return immediately since already ready
            ready = await multiplexer.wait_until_ready(timeout=1.0)
            assert ready is True

            await multiplexer.stop()
        finally:
            # Clean up test certificate files
            import os

            try:
                os.unlink(cert_file_path)
                os.unlink(key_file_path)
            except OSError:
                pass


class TestGRPCHandlerCoverage:
    """Additional tests for GRPCHandler to improve coverage."""

    @patch("asyncio.open_connection")
    async def test_handle_connection_data_flow_errors(
        self, mock_open_connection: AsyncMock
    ) -> None:
        """Test connection handling with errors in data flow."""
        handler = GRPCHandler()

        # Mock upstream connection
        mock_upstream_reader = AsyncMock()
        mock_upstream_writer = Mock()
        mock_upstream_writer.write = Mock()
        mock_upstream_writer.drain = AsyncMock()
        mock_upstream_writer.close = Mock()
        mock_upstream_writer.wait_closed = AsyncMock()
        mock_open_connection.return_value = (mock_upstream_reader, mock_upstream_writer)

        # Mock client connection
        mock_client_reader = AsyncMock()
        mock_client_writer = Mock()
        mock_client_writer.write = Mock()
        mock_client_writer.drain = AsyncMock(side_effect=Exception("Drain error"))
        mock_client_writer.close = Mock()
        mock_client_writer.wait_closed = AsyncMock()
        mock_client_writer.is_closing.return_value = False

        # Mock data flow with error in drain
        mock_client_reader.read.side_effect = [b"test_data", b""]
        mock_upstream_reader.read.side_effect = [b"response_data", b""]

        await handler.handle_connection(mock_client_reader, mock_client_writer)

        # Should still clean up properly
        mock_client_writer.close.assert_called()

    @patch("asyncio.open_connection")
    async def test_handle_connection_exception_in_gather(
        self, mock_open_connection: AsyncMock
    ) -> None:
        """Test connection handling with exception in asyncio.gather."""
        handler = GRPCHandler()

        # Mock upstream connection
        mock_upstream_reader = AsyncMock()
        mock_upstream_writer = Mock()
        mock_upstream_writer.write = Mock()
        mock_upstream_writer.drain = AsyncMock()
        mock_upstream_writer.close = Mock()
        mock_upstream_writer.wait_closed = AsyncMock()
        mock_open_connection.return_value = (mock_upstream_reader, mock_upstream_writer)

        # Mock client connection
        mock_client_reader = AsyncMock()
        mock_client_writer = Mock()
        mock_client_writer.write = Mock()
        mock_client_writer.drain = AsyncMock()
        mock_client_writer.close = Mock()
        mock_client_writer.wait_closed = AsyncMock()
        mock_client_writer.is_closing.return_value = False

        # Mock data flow with exception
        mock_client_reader.read.side_effect = Exception("Read error")
        mock_upstream_reader.read.side_effect = [b"response_data", b""]

        await handler.handle_connection(mock_client_reader, mock_client_writer)

        # Should clean up properly even with exception
        mock_client_writer.close.assert_called()
        # Upstream writer might not be closed if the connection failed early
        # The updated implementation only closes writers that exist and are not
        # already closing

    @patch("asyncio.open_connection")
    async def test_handle_connection_cleanup_exception(
        self, mock_open_connection: AsyncMock
    ) -> None:
        """Test connection handling with cleanup exceptions."""
        handler = GRPCHandler()

        # Mock upstream connection
        mock_upstream_reader = AsyncMock()
        mock_upstream_writer = Mock()
        mock_upstream_writer.write = Mock()
        mock_upstream_writer.drain = AsyncMock()
        mock_upstream_writer.close = Mock()
        mock_upstream_writer.wait_closed = AsyncMock(
            side_effect=Exception("Cleanup error")
        )
        mock_open_connection.return_value = (mock_upstream_reader, mock_upstream_writer)

        # Mock client connection
        mock_client_reader = AsyncMock()
        mock_client_writer = Mock()
        mock_client_writer.write = Mock()
        mock_client_writer.drain = AsyncMock()
        mock_client_writer.close = Mock()
        mock_client_writer.wait_closed = AsyncMock()
        mock_client_writer.is_closing.return_value = False

        # Mock normal data flow
        mock_client_reader.read.side_effect = [b"test_data", b""]
        mock_upstream_reader.read.side_effect = [b"response_data", b""]

        # Should not raise exception despite cleanup error
        await handler.handle_connection(mock_client_reader, mock_client_writer)


class TestCreateALPNMultiplexerForACME:
    """Test the ACME-specific ALPN multiplexer creation."""

    async def test_create_alpn_multiplexer_for_acme_success(self) -> None:
        """Test successful creation of ALPN multiplexer for ACME."""
        mock_grpc_server = Mock()
        mock_grpc_server.start = Mock()
        mock_grpc_server.stop = Mock()

        mock_tls_alpn_server = Mock()

        # Generate valid test certificates
        cert_file_path, key_file_path = _create_test_certificates()

        try:
            multiplexer = await create_alpn_multiplexer_for_acme(
                host="127.0.0.1",
                port=0,  # Use random available port
                cert_file=cert_file_path,
                key_file=key_file_path,
                grpc_server=mock_grpc_server,
                tls_alpn_server=mock_tls_alpn_server,
                grpc_internal_port=8080,
            )

            # Should have started gRPC server
            mock_grpc_server.start.assert_called_once()

            # Should have set gRPC server properties
            assert mock_grpc_server.port == 8080
            assert mock_grpc_server.host == "127.0.0.1"
            assert mock_grpc_server.use_tls is False

            # Should have registered handlers
            assert "h2" in multiplexer._handlers
            assert "acme-tls/1" in multiplexer._handlers

            # Should be running
            assert multiplexer.is_running

            await multiplexer.stop()
        finally:
            # Clean up test certificate files
            import os

            try:
                os.unlink(cert_file_path)
                os.unlink(key_file_path)
            except OSError:
                pass

    async def test_create_alpn_multiplexer_for_acme_grpc_failure(self) -> None:
        """Test ALPN multiplexer creation when gRPC server fails to start."""
        mock_grpc_server = Mock()
        mock_grpc_server.start = Mock(side_effect=Exception("gRPC start failed"))
        mock_grpc_server.stop = Mock()

        mock_tls_alpn_server = Mock()

        with (
            tempfile.NamedTemporaryFile(suffix=".pem") as cert_file,
            tempfile.NamedTemporaryFile(suffix=".pem") as key_file,
        ):
            # Write dummy certificate data
            cert_file.write(
                b"-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----"
            )
            cert_file.flush()
            key_file.write(
                b"-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----"
            )
            key_file.flush()

            with pytest.raises(Exception, match="gRPC start failed"):
                await create_alpn_multiplexer_for_acme(
                    host="127.0.0.1",
                    port=0,
                    cert_file=cert_file.name,
                    key_file=key_file.name,
                    grpc_server=mock_grpc_server,
                    tls_alpn_server=mock_tls_alpn_server,
                )

            # Should have attempted to stop gRPC server during cleanup
            mock_grpc_server.stop.assert_called_once()

    @patch("vibectl.server.alpn_multiplexer.ALPNMultiplexer.start")
    async def test_create_alpn_multiplexer_for_acme_multiplexer_failure(
        self, mock_start: AsyncMock
    ) -> None:
        """Test ALPN multiplexer creation when multiplexer fails to start."""
        mock_grpc_server = Mock()
        mock_grpc_server.start = Mock()
        mock_grpc_server.stop = Mock()

        mock_tls_alpn_server = Mock()

        # Make the multiplexer start method raise an exception
        mock_start.side_effect = RuntimeError("Multiplexer start failed")

        # Use valid certificate files since the error should come from start() failing
        cert_file, key_file = _create_test_certificates()

        try:
            with pytest.raises(RuntimeError, match="Multiplexer start failed"):
                await create_alpn_multiplexer_for_acme(
                    host="127.0.0.1",
                    port=0,
                    cert_file=cert_file,
                    key_file=key_file,
                    grpc_server=mock_grpc_server,
                    tls_alpn_server=mock_tls_alpn_server,
                )

            # Should have attempted to stop gRPC server during cleanup
            mock_grpc_server.stop.assert_called_once()

        finally:
            # Clean up test files
            Path(cert_file).unlink(missing_ok=True)
            Path(key_file).unlink(missing_ok=True)


class TestALPNMultiplexerSNICallback:
    """Test SNI callback functionality for TLS-ALPN-01 challenges."""

    def test_create_ssl_context(self) -> None:
        """Test SSL context creation with SNI callback."""
        cert_file, key_file = _create_test_certificates()

        try:
            multiplexer = ALPNMultiplexer(cert_file=cert_file, key_file=key_file)

            # Register a TLS-ALPN handler
            mock_tls_alpn_server = Mock()
            tls_alpn_handler = TLSALPNHandler(mock_tls_alpn_server)
            multiplexer.register_handler("acme-tls/1", tls_alpn_handler)

            ssl_context = multiplexer._create_ssl_context()

            # Should return an SSL context with SNI callback set
            assert isinstance(ssl_context, ssl.SSLContext)
            assert ssl_context.sni_callback is not None
            assert callable(ssl_context.sni_callback)

        finally:
            # Clean up test files
            Path(cert_file).unlink(missing_ok=True)
            Path(key_file).unlink(missing_ok=True)

    def test_sni_callback_with_challenge(self) -> None:
        """Test SNI callback modifies SSL socket context when challenge exists."""
        cert_file, key_file = _create_test_certificates()

        try:
            multiplexer = ALPNMultiplexer(cert_file=cert_file, key_file=key_file)

            # Create mock TLS-ALPN server with challenge
            mock_tls_alpn_server = Mock()
            mock_tls_alpn_server._get_challenge_response.return_value = (
                "challenge_response"
            )
            mock_challenge_context = Mock(spec=ssl.SSLContext)
            mock_tls_alpn_server._create_ssl_context.return_value = (
                mock_challenge_context
            )

            tls_alpn_handler = TLSALPNHandler(mock_tls_alpn_server)
            multiplexer.register_handler("acme-tls/1", tls_alpn_handler)

            ssl_context = multiplexer._create_ssl_context()
            callback = ssl_context.sni_callback

            # Call the callback with a domain that has a challenge
            mock_ssl_socket = Mock()
            mock_ssl_socket.context = Mock(spec=ssl.SSLContext)  # Initialize context
            mock_ssl_context = Mock(spec=ssl.SSLContext)

            assert callback is not None  # Ensure callback exists
            result = callback(mock_ssl_socket, "example.com", mock_ssl_context)

            # SNI callback should return None and modify the socket's context
            assert result is None
            assert mock_ssl_socket.context == mock_challenge_context
            mock_tls_alpn_server._get_challenge_response.assert_called_once_with(
                "example.com"
            )
            mock_tls_alpn_server._create_ssl_context.assert_called_once_with(
                "example.com"
            )

        finally:
            Path(cert_file).unlink(missing_ok=True)
            Path(key_file).unlink(missing_ok=True)

    def test_sni_callback_no_challenge(self) -> None:
        """Test SNI callback does not modify context when no challenge exists."""
        cert_file, key_file = _create_test_certificates()

        try:
            multiplexer = ALPNMultiplexer(cert_file=cert_file, key_file=key_file)

            # Create mock TLS-ALPN server without challenge for this domain
            mock_tls_alpn_server = Mock()
            mock_tls_alpn_server._get_challenge_response.return_value = None

            tls_alpn_handler = TLSALPNHandler(mock_tls_alpn_server)
            multiplexer.register_handler("acme-tls/1", tls_alpn_handler)

            ssl_context = multiplexer._create_ssl_context()
            callback = ssl_context.sni_callback

            # Call the callback with a domain that has no challenge
            mock_ssl_socket = Mock()
            mock_ssl_socket.context = Mock(spec=ssl.SSLContext)  # Initialize context
            mock_ssl_context = Mock(spec=ssl.SSLContext)
            original_context = mock_ssl_socket.context

            assert callback is not None  # Ensure callback exists
            result = callback(mock_ssl_socket, "example.com", mock_ssl_context)

            # Should not modify the socket context
            assert result is None
            assert mock_ssl_socket.context == original_context  # No change
            mock_tls_alpn_server._get_challenge_response.assert_called_once_with(
                "example.com"
            )
            mock_tls_alpn_server._create_ssl_context.assert_not_called()

        finally:
            Path(cert_file).unlink(missing_ok=True)
            Path(key_file).unlink(missing_ok=True)

    def test_sni_callback_no_server_name_no_challenges(self) -> None:
        """Test SNI callback handles missing server name (no SNI) with no challenges."""
        cert_file, key_file = _create_test_certificates()

        try:
            multiplexer = ALPNMultiplexer(cert_file=cert_file, key_file=key_file)

            # Create mock TLS-ALPN server with no active challenges
            mock_tls_alpn_server = Mock()
            mock_tls_alpn_server._get_active_challenge_domains.return_value = []
            tls_alpn_handler = TLSALPNHandler(mock_tls_alpn_server)
            multiplexer.register_handler("acme-tls/1", tls_alpn_handler)

            ssl_context = multiplexer._create_ssl_context()
            callback = ssl_context.sni_callback

            # Call the callback with no server name (None)
            mock_ssl_socket = Mock()
            mock_ssl_socket.context = Mock(spec=ssl.SSLContext)  # Initialize context
            mock_ssl_context = Mock(spec=ssl.SSLContext)
            original_context = mock_ssl_socket.context

            assert callback is not None  # Ensure callback exists
            callback(mock_ssl_socket, None, mock_ssl_context)  # type: ignore[arg-type]

            # Should not modify context when no challenges exist
            assert mock_ssl_socket.context == original_context
            mock_tls_alpn_server._get_active_challenge_domains.assert_called_once()
            mock_tls_alpn_server._get_challenge_response.assert_not_called()
            mock_tls_alpn_server._create_ssl_context.assert_not_called()

        finally:
            Path(cert_file).unlink(missing_ok=True)
            Path(key_file).unlink(missing_ok=True)

    def test_sni_callback_no_server_name_single_challenge(self) -> None:
        """Test SNI callback uses single active challenge when no SNI provided."""
        cert_file, key_file = _create_test_certificates()

        try:
            multiplexer = ALPNMultiplexer(cert_file=cert_file, key_file=key_file)

            # Create mock TLS-ALPN server with one active challenge
            mock_tls_alpn_server = Mock()
            mock_tls_alpn_server._get_active_challenge_domains.return_value = [
                "example.com"
            ]
            mock_challenge_context = Mock(spec=ssl.SSLContext)
            mock_tls_alpn_server._create_ssl_context.return_value = (
                mock_challenge_context
            )

            tls_alpn_handler = TLSALPNHandler(mock_tls_alpn_server)
            multiplexer.register_handler("acme-tls/1", tls_alpn_handler)

            ssl_context = multiplexer._create_ssl_context()
            callback = ssl_context.sni_callback

            # Call the callback with no server name (None)
            mock_ssl_socket = Mock()
            mock_ssl_socket.context = Mock(spec=ssl.SSLContext)  # Initialize context
            mock_ssl_context = Mock(spec=ssl.SSLContext)

            callback(mock_ssl_socket, None, mock_ssl_context)  # type: ignore[misc,arg-type]

            # Should use the single active challenge certificate
            assert mock_ssl_socket.context == mock_challenge_context
            mock_tls_alpn_server._get_active_challenge_domains.assert_called_once()
            mock_tls_alpn_server._create_ssl_context.assert_called_once_with(
                "example.com"
            )

        finally:
            Path(cert_file).unlink(missing_ok=True)
            Path(key_file).unlink(missing_ok=True)

    def test_sni_callback_no_server_name_multiple_challenges(self) -> None:
        """Test SNI callback warns but doesn't modify context if multiple challenges."""
        cert_file, key_file = _create_test_certificates()

        try:
            multiplexer = ALPNMultiplexer(cert_file=cert_file, key_file=key_file)

            # Create mock TLS-ALPN server with multiple active challenges
            mock_tls_alpn_server = Mock()
            mock_tls_alpn_server._get_active_challenge_domains.return_value = [
                "example1.com",
                "example2.com",
            ]

            tls_alpn_handler = TLSALPNHandler(mock_tls_alpn_server)
            multiplexer.register_handler("acme-tls/1", tls_alpn_handler)

            ssl_context = multiplexer._create_ssl_context()
            callback = ssl_context.sni_callback

            # Call the callback with no server name (None)
            mock_ssl_socket = Mock()
            mock_ssl_socket.context = Mock(spec=ssl.SSLContext)  # Initialize context
            mock_ssl_context = Mock(spec=ssl.SSLContext)
            original_context = mock_ssl_socket.context

            callback(mock_ssl_socket, None, mock_ssl_context)  # type: ignore[misc,arg-type]

            # Should not modify context when multiple challenges exist (ambiguous)
            assert mock_ssl_socket.context == original_context
            mock_tls_alpn_server._get_active_challenge_domains.assert_called_once()
            mock_tls_alpn_server._create_ssl_context.assert_not_called()

        finally:
            Path(cert_file).unlink(missing_ok=True)
            Path(key_file).unlink(missing_ok=True)

    # Keep the original test as is for backward compatibility (rename for clarity)
    def test_sni_callback_no_server_name(self) -> None:
        """Test SNI callback handles missing server name (no SNI) - legacy behavior."""
        cert_file, key_file = _create_test_certificates()

        try:
            multiplexer = ALPNMultiplexer(cert_file=cert_file, key_file=key_file)

            # Create mock TLS-ALPN server
            mock_tls_alpn_server = Mock()
            mock_tls_alpn_server._get_active_challenge_domains.return_value = []
            tls_alpn_handler = TLSALPNHandler(mock_tls_alpn_server)
            multiplexer.register_handler("acme-tls/1", tls_alpn_handler)

            ssl_context = multiplexer._create_ssl_context()
            callback = ssl_context.sni_callback

            # Call the callback with no server name (None)
            mock_ssl_socket = Mock()
            mock_ssl_socket.context = Mock(spec=ssl.SSLContext)  # Initialize context
            mock_ssl_context = Mock(spec=ssl.SSLContext)
            original_context = mock_ssl_socket.context

            callback(mock_ssl_socket, None, mock_ssl_context)  # type: ignore[misc,arg-type]

            # Should not modify context or call TLS-ALPN server for challenge lookup
            assert mock_ssl_socket.context == original_context
            mock_tls_alpn_server._get_active_challenge_domains.assert_called_once()

        finally:
            Path(cert_file).unlink(missing_ok=True)
            Path(key_file).unlink(missing_ok=True)

    def test_sni_callback_no_tls_alpn_handler(self) -> None:
        """Test SNI callback when no TLS-ALPN handler is registered."""
        cert_file, key_file = _create_test_certificates()

        try:
            multiplexer = ALPNMultiplexer(cert_file=cert_file, key_file=key_file)

            # Register only gRPC handler, no TLS-ALPN handler
            grpc_handler = GRPCHandler()
            multiplexer.register_handler("h2", grpc_handler)

            ssl_context = multiplexer._create_ssl_context()

            # When no TLS-ALPN handler is registered, no SNI callback should be set
            assert ssl_context.sni_callback is None

        finally:
            Path(cert_file).unlink(missing_ok=True)
            Path(key_file).unlink(missing_ok=True)

    def test_sni_callback_exception_handling(self) -> None:
        """Test SNI callback handles exceptions gracefully."""
        cert_file, key_file = _create_test_certificates()

        try:
            multiplexer = ALPNMultiplexer(cert_file=cert_file, key_file=key_file)

            # Create mock TLS-ALPN server that raises exception
            mock_tls_alpn_server = Mock()
            mock_tls_alpn_server._get_challenge_response.side_effect = Exception(
                "Test error"
            )

            tls_alpn_handler = TLSALPNHandler(mock_tls_alpn_server)
            multiplexer.register_handler("acme-tls/1", tls_alpn_handler)

            ssl_context = multiplexer._create_ssl_context()
            callback = ssl_context.sni_callback

            # Call the callback - should handle exception gracefully
            mock_ssl_socket = Mock()
            mock_ssl_socket.context = Mock(spec=ssl.SSLContext)  # Initialize context
            mock_ssl_context = Mock(spec=ssl.SSLContext)
            original_context = mock_ssl_socket.context

            callback(mock_ssl_socket, "example.com", mock_ssl_context)  # type: ignore[misc]

            # Should not modify context despite the exception
            assert mock_ssl_socket.context == original_context

        finally:
            Path(cert_file).unlink(missing_ok=True)
            Path(key_file).unlink(missing_ok=True)

    def test_create_ssl_context_with_handlers(self) -> None:
        """Test SSL context creation with registered handlers."""
        cert_file, key_file = _create_test_certificates()

        try:
            multiplexer = ALPNMultiplexer(cert_file=cert_file, key_file=key_file)

            # Register handlers to test ALPN configuration
            grpc_handler = GRPCHandler()
            tls_alpn_handler = TLSALPNHandler(Mock())
            multiplexer.register_handler("h2", grpc_handler)
            multiplexer.register_handler("acme-tls/1", tls_alpn_handler)

            context = multiplexer._create_ssl_context()

            assert isinstance(context, ssl.SSLContext)
            # The context should be configured with the registered ALPN protocols
            # Note: We can't easily test the ALPN protocols directly as they're
            # internal to SSLContext

        finally:
            Path(cert_file).unlink(missing_ok=True)
            Path(key_file).unlink(missing_ok=True)

    def test_create_ssl_context_no_certs(self) -> None:
        """Test SSL context creation fails without certificates."""
        multiplexer = ALPNMultiplexer()

        with pytest.raises(ValueError, match="cert_file and key_file must be provided"):
            multiplexer._create_ssl_context()

    @patch("asyncio.start_server")
    async def test_start_with_sni_callback(self, mock_start_server: AsyncMock) -> None:
        """Test server start has SSL context with SNI callback for TLS-ALPN handler."""
        cert_file, key_file = _create_test_certificates()

        try:
            multiplexer = ALPNMultiplexer(cert_file=cert_file, key_file=key_file)

            # Register TLS-ALPN handler to trigger SNI callback mode
            mock_tls_alpn_server = Mock()
            tls_alpn_handler = TLSALPNHandler(mock_tls_alpn_server)
            multiplexer.register_handler("acme-tls/1", tls_alpn_handler)

            # Mock successful server start
            mock_server = Mock()
            mock_start_server.return_value = mock_server

            await multiplexer.start()

            # Verify start_server was called with SSL context that has SNI callback set
            mock_start_server.assert_called_once()
            call_args = mock_start_server.call_args

            # Check that ssl parameter is an SSLContext with SNI callback set
            ssl_param = call_args.kwargs.get("ssl")
            assert isinstance(ssl_param, ssl.SSLContext)
            assert ssl_param.sni_callback is not None
            assert callable(ssl_param.sni_callback)

            await multiplexer.stop()

        finally:
            Path(cert_file).unlink(missing_ok=True)
            Path(key_file).unlink(missing_ok=True)

    @patch("asyncio.start_server")
    async def test_start_without_sni_callback(
        self, mock_start_server: AsyncMock
    ) -> None:
        """Test server start uses static SSL context when no TLS-ALPN handler."""
        cert_file, key_file = _create_test_certificates()

        try:
            multiplexer = ALPNMultiplexer(cert_file=cert_file, key_file=key_file)

            # Register only gRPC handler (no TLS-ALPN handler)
            grpc_handler = GRPCHandler()
            multiplexer.register_handler("h2", grpc_handler)

            # Mock successful server start
            mock_server = Mock()
            mock_start_server.return_value = mock_server

            await multiplexer.start()

            # Verify start_server was called with SSL context (not callable)
            mock_start_server.assert_called_once()
            call_args = mock_start_server.call_args

            # Check that ssl parameter is SSLContext (not callable)
            ssl_param = call_args.kwargs.get("ssl")
            assert isinstance(ssl_param, ssl.SSLContext)
            assert not callable(ssl_param)

            await multiplexer.stop()

        finally:
            Path(cert_file).unlink(missing_ok=True)
            Path(key_file).unlink(missing_ok=True)

    def test_sni_integration_with_tls_alpn_challenge(self) -> None:
        """Test that SNI callback correctly integrates with TLS-ALPN challenge server.

        This test verifies the fix for the root connectivity issue where
        asyncio.start_server was being passed a callback function instead
        of an SSL context object.
        """
        cert_file, key_file = _create_test_certificates()

        try:
            multiplexer = ALPNMultiplexer(cert_file=cert_file, key_file=key_file)

            # Create a TLS-ALPN server with a challenge response
            mock_tls_alpn_server = Mock()
            mock_tls_alpn_server._get_challenge_response.return_value = (
                "test_challenge_response"
            )

            # Mock the challenge certificate creation
            mock_challenge_context = Mock(spec=ssl.SSLContext)
            mock_tls_alpn_server._create_ssl_context.return_value = (
                mock_challenge_context
            )

            # Register the TLS-ALPN handler
            tls_alpn_handler = TLSALPNHandler(mock_tls_alpn_server)
            multiplexer.register_handler("acme-tls/1", tls_alpn_handler)

            # Create SSL context with SNI callback
            ssl_context = multiplexer._create_ssl_context()

            # Verify we get an SSL context, not a callback function
            assert isinstance(ssl_context, ssl.SSLContext)
            assert ssl_context.sni_callback is not None

            # Test the SNI callback behavior
            callback = ssl_context.sni_callback
            mock_ssl_socket = Mock()
            mock_ssl_socket.context = Mock(spec=ssl.SSLContext)

            # Call SNI callback for a domain with challenge
            callback(mock_ssl_socket, "example.com", Mock())

            # Verify the challenge was looked up and SSL context was replaced
            mock_tls_alpn_server._get_challenge_response.assert_called_once_with(
                "example.com"
            )
            mock_tls_alpn_server._create_ssl_context.assert_called_once_with(
                "example.com"
            )
            assert mock_ssl_socket.context == mock_challenge_context

        finally:
            Path(cert_file).unlink(missing_ok=True)
            Path(key_file).unlink(missing_ok=True)
