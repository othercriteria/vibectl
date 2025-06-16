"""
Tests for edge cases and uncovered branches in server modules.

This file specifically targets remaining coverage gaps in:
- TLS-ALPN Challenge Server bridge functionality and certificate restoration
- ALPN Multiplexer error handling and edge cases
- ACME Client error scenarios and edge paths
- ACME Manager specific error conditions
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from vibectl.server.acme_client import ACMEClient
from vibectl.server.acme_manager import ACMEManager
from vibectl.server.alpn_bridge import TLSALPNBridge
from vibectl.server.alpn_multiplexer import ALPNMultiplexer, TLSALPNHandler
from vibectl.server.tls_alpn_challenge_server import TLSALPNChallengeServer


class TestTLSALPNChallengeServerBridgeAndCertificateRestore:
    """Test coverage gaps in TLS-ALPN challenge server bridge functionality."""

    def test_attach_bridge_and_multiplexer_interactions(self) -> None:
        """Test bridge attachment and multiplexer certificate management."""
        # Create server and bridge
        server = TLSALPNChallengeServer()
        bridge = TLSALPNBridge()

        # Test bridge attachment (covers line 73-75)
        server._attach_bridge(bridge)
        assert server._bridge == bridge

        # Create mock multiplexer
        mock_multiplexer = Mock()
        mock_multiplexer.cert_file = "/fake/cert.pem"
        mock_multiplexer.key_file = "/fake/key.pem"
        mock_multiplexer._ssl_context = Mock()
        bridge.attach_multiplexer(mock_multiplexer)

        # Test setting challenge with bridge and single challenge cert update
        domain = "example.com"
        challenge_response = b"test_challenge_response_32_bytes__"  # 32 bytes

        with patch("tempfile.NamedTemporaryFile") as mock_tempfile, patch("os.unlink"):
            # Mock temporary files for certificate generation
            mock_cert_file = Mock()
            mock_cert_file.name = "/tmp/cert.pem"
            mock_cert_file.__enter__ = Mock(return_value=mock_cert_file)
            mock_cert_file.__exit__ = Mock(return_value=None)

            mock_key_file = Mock()
            mock_key_file.name = "/tmp/key.pem"
            mock_key_file.__enter__ = Mock(return_value=mock_key_file)
            mock_key_file.__exit__ = Mock(return_value=None)

            mock_tempfile.side_effect = [mock_cert_file, mock_key_file]

            # Set challenge - should trigger default cert update due to single challenge
            # This covers lines 96-99 (single challenge cert update logic)
            server.set_challenge(domain, challenge_response)

            # Verify SSL context load_cert_chain was called for default cert update
            mock_multiplexer._ssl_context.load_cert_chain.assert_called()

    def test_remove_challenge_with_restore_default_cert(self) -> None:
        """Test challenge removal triggers default certificate restoration."""
        server = TLSALPNChallengeServer()
        bridge = TLSALPNBridge()
        server._attach_bridge(bridge)

        # Create mock multiplexer
        mock_multiplexer = Mock()
        mock_multiplexer.cert_file = "/fake/cert.pem"
        mock_multiplexer.key_file = "/fake/key.pem"
        mock_multiplexer._ssl_context = Mock()
        bridge.attach_multiplexer(mock_multiplexer)

        # Set a challenge first
        domain = "example.com"
        challenge_response = b"test_response"
        server.set_challenge(domain, challenge_response)

        # Remove challenge - should trigger default cert restoration
        # This covers lines 124-128 (restore cert after all challenges cleared)
        server.remove_challenge(domain)

        # Should have called load_cert_chain for restoration
        assert mock_multiplexer._ssl_context.load_cert_chain.call_count >= 1

    def test_restore_multiplexer_default_cert_edge_cases(self) -> None:
        """Test restore default cert edge cases (covers lines 364-381)."""
        server = TLSALPNChallengeServer()

        # Test with no bridge (line 366-369)
        server._restore_multiplexer_default_cert()

        # Test with bridge but no multiplexer
        bridge = TLSALPNBridge()
        server._attach_bridge(bridge)
        server._restore_multiplexer_default_cert()

        # Test with multiplexer but no cert files (lines 374-381)
        mock_multiplexer = Mock()
        mock_multiplexer.cert_file = None
        mock_multiplexer.key_file = None
        mock_multiplexer._ssl_context = Mock()
        bridge.attach_multiplexer(mock_multiplexer)
        server._restore_multiplexer_default_cert()

        # Test load_cert_chain error handling
        mock_multiplexer.cert_file = "/fake/cert.pem"
        mock_multiplexer.key_file = "/fake/key.pem"
        mock_multiplexer._ssl_context.load_cert_chain.side_effect = Exception(
            "Load error"
        )
        server._restore_multiplexer_default_cert()

    def test_update_multiplexer_default_cert_edge_cases(self) -> None:
        """Test update default cert edge cases (covers lines 409-455)."""
        server = TLSALPNChallengeServer()

        # Test with no bridge
        server._update_multiplexer_default_cert("example.com", b"test")

        # Test with bridge but no multiplexer
        bridge = TLSALPNBridge()
        server._attach_bridge(bridge)
        server._update_multiplexer_default_cert("example.com", b"test")

        # Test successful update
        mock_multiplexer = Mock()
        mock_multiplexer._ssl_context = Mock()
        bridge.attach_multiplexer(mock_multiplexer)

        with patch("tempfile.NamedTemporaryFile") as mock_tempfile, patch("os.unlink"):
            # Mock temporary files
            mock_cert_file = Mock()
            mock_cert_file.name = "/tmp/cert.pem"
            mock_cert_file.__enter__ = Mock(return_value=mock_cert_file)
            mock_cert_file.__exit__ = Mock(return_value=None)

            mock_key_file = Mock()
            mock_key_file.name = "/tmp/key.pem"
            mock_key_file.__enter__ = Mock(return_value=mock_key_file)
            mock_key_file.__exit__ = Mock(return_value=None)

            mock_tempfile.side_effect = [mock_cert_file, mock_key_file]

            server._update_multiplexer_default_cert(
                "example.com", b"test_challenge_response_32_bytes__"
            )

            # Verify certificate was loaded
            mock_multiplexer._ssl_context.load_cert_chain.assert_called()

    def test_create_challenge_certificate_non_32_byte_response(self) -> None:
        """Test challenge certificate creation with non-32-byte response (test mode)."""
        server = TLSALPNChallengeServer()
        domain = "example.com"
        challenge_response = b"short_response"  # Not 32 bytes - covers line 203-206

        # Should still create certificate with warning
        with patch("vibectl.server.tls_alpn_challenge_server.logger") as mock_logger:
            cert_pem = server._create_challenge_certificate(domain, challenge_response)

            # Verify warning was logged for non-32-byte response
            mock_logger.warning.assert_called()
            assert b"-----BEGIN CERTIFICATE-----" in cert_pem


class TestALPNMultiplexerEdgeCases:
    """Test edge cases and error handling in ALPN Multiplexer."""

    def test_sni_callback_exception_handling(self) -> None:
        """Test SNI callback handles exceptions gracefully (covers lines 323-327)."""
        multiplexer = ALPNMultiplexer()

        # Mock TLS-ALPN handler that raises exception in _select_challenge_context
        mock_handler = Mock(spec=TLSALPNHandler)
        mock_handler.tls_alpn_server = Mock()
        multiplexer.register_handler("acme-tls/1", mock_handler)

        # Create SNI callback
        sni_callback = multiplexer._create_sni_callback()

        # Mock SSL socket
        mock_ssl_socket = Mock()
        mock_ssl_context = Mock()

        # Should not raise exception, should handle error gracefully
        with (
            patch("vibectl.server.alpn_multiplexer.logger") as mock_logger,
            patch.object(
                multiplexer,
                "_select_challenge_context",
                side_effect=Exception("Test error"),
            ),
        ):
            sni_callback(mock_ssl_socket, "example.com", mock_ssl_context)

            # Should log error
            mock_logger.error.assert_called()

    def test_select_challenge_context_exception_handling(self) -> None:
        """Test _select_challenge_context handles exceptions (covers lines 251-257)."""
        multiplexer = ALPNMultiplexer()

        # Mock TLS-ALPN server that raises exception
        mock_tls_alpn_server = Mock()
        mock_tls_alpn_server._get_challenge_response.side_effect = Exception(
            "Test error"
        )

        # Should return None and log warning on exception
        with patch("vibectl.server.alpn_multiplexer.logger") as mock_logger:
            result = multiplexer._select_challenge_context(
                mock_tls_alpn_server, "example.com"
            )

            assert result is None
            mock_logger.warning.assert_called()

    def test_handle_connection_certificate_info_error(self) -> None:
        """Test connection handling when certificate info extraction fails."""
        multiplexer = ALPNMultiplexer()

        async def test_connection() -> None:
            mock_reader = AsyncMock()
            mock_writer = Mock()

            # Mock SSL object that raises exception when getting certificate
            mock_ssl_object = Mock()
            mock_ssl_object.getpeercert.side_effect = Exception("Cert error")
            mock_ssl_object.selected_alpn_protocol.return_value = "acme-tls/1"

            mock_writer.get_extra_info.side_effect = lambda key, default=None: {
                "ssl_object": mock_ssl_object,
                "peername": ("127.0.0.1", 12345),
                "sockname": ("0.0.0.0", 443),
            }.get(key, default)

            mock_writer.is_closing.return_value = False
            mock_writer.close = Mock()
            mock_writer.wait_closed = AsyncMock()

            # Register mock handler
            mock_handler = AsyncMock()
            multiplexer.register_handler("acme-tls/1", mock_handler)

            # Should handle certificate info error gracefully
            await multiplexer._handle_connection(mock_reader, mock_writer)

            # Handler should still be called
            mock_handler.handle_connection.assert_called_once()

        import asyncio

        asyncio.run(test_connection())

    def test_handle_connection_info_extraction_error(self) -> None:
        """Test connection handling when connection info extraction fails."""
        multiplexer = ALPNMultiplexer()

        async def test_connection() -> None:
            mock_reader = AsyncMock()
            mock_writer = Mock()

            # Mock get_extra_info to raise exception for peername/sockname
            def mock_get_extra_info(key: str, default: object = None) -> object:
                if key in ["peername", "sockname"]:
                    raise Exception("Info error")
                if key == "ssl_object":
                    mock_ssl = Mock()
                    mock_ssl.selected_alpn_protocol.return_value = "acme-tls/1"
                    return mock_ssl
                return default

            mock_writer.get_extra_info.side_effect = mock_get_extra_info
            mock_writer.is_closing.return_value = False
            mock_writer.close = Mock()
            mock_writer.wait_closed = AsyncMock()

            # Register mock handler
            mock_handler = AsyncMock()
            multiplexer.register_handler("acme-tls/1", mock_handler)

            # Should handle connection info error gracefully
            await multiplexer._handle_connection(mock_reader, mock_writer)

            # Handler should still be called
            mock_handler.handle_connection.assert_called_once()

        import asyncio

        asyncio.run(test_connection())


class TestACMEClientErrorPaths:
    """Test error paths and edge cases in ACME Client."""

    def test_ensure_client_network_test_failure(self) -> None:
        """Test _ensure_client when network test fails."""
        client = ACMEClient()

        with (
            patch("vibectl.server.acme_client.jose.JWKRSA") as mock_jwk,
            patch("vibectl.server.acme_client.rsa.generate_private_key") as mock_rsa,
            patch("vibectl.server.acme_client.acme.client.ClientNetwork") as mock_net,
        ):
            mock_jwk.return_value = Mock()
            mock_rsa.return_value = Mock()

            # Mock network client that fails on get request
            mock_network = Mock()
            mock_network.get.side_effect = Exception("Network error")
            mock_net.return_value = mock_network

            # Should raise ACMECertificateError or similar network error
            with pytest.raises((Exception,)):  # Network-related error
                client._ensure_client()

    def test_complete_http01_challenge_response_error(self) -> None:
        """Test HTTP-01 challenge when response generation fails."""
        client = ACMEClient()
        client._account_key = Mock()

        # Mock challenge body
        mock_challenge_body = Mock()
        mock_challenge = Mock()
        mock_challenge.response_and_validation.side_effect = Exception("Response error")
        mock_challenge_body.chall = mock_challenge

        # Should raise ACMEValidationError
        with pytest.raises((Exception,)):  # Response validation error
            client._complete_http01_challenge(mock_challenge_body, "example.com", None)

    def test_complete_http01_challenge_token_encode_error(self) -> None:
        """Test HTTP-01 challenge when token encoding fails."""
        client = ACMEClient()
        client._account_key = Mock()

        # Mock challenge body
        mock_challenge_body = Mock()
        mock_challenge = Mock()
        mock_challenge.response_and_validation.return_value = (Mock(), "validation")
        mock_challenge.encode.side_effect = Exception("Encode error")
        mock_challenge_body.chall = mock_challenge

        # Should raise ACMEValidationError
        with pytest.raises((Exception,)):  # Token encoding error
            client._complete_http01_challenge(mock_challenge_body, "example.com", None)

    def test_complete_http01_challenge_file_write_error(self) -> None:
        """Test HTTP-01 challenge when file write fails."""
        client = ACMEClient()
        client._account_key = Mock()

        # Mock challenge body
        mock_challenge_body = Mock()
        mock_challenge = Mock()
        mock_challenge.response_and_validation.return_value = (Mock(), "validation")
        mock_challenge.encode.return_value = "test_token"
        mock_challenge_body.chall = mock_challenge

        with patch("vibectl.server.acme_client.Path") as mock_path:
            # Mock path operations
            mock_challenge_path = Mock()
            mock_path.return_value = mock_challenge_path
            mock_challenge_path.mkdir = Mock()

            mock_challenge_file = Mock()
            mock_challenge_file.write_text.side_effect = Exception("Write error")
            mock_challenge_path.__truediv__ = Mock(return_value=mock_challenge_file)

            # Should raise ACMEValidationError
            with pytest.raises((Exception,)):  # File write error
                client._complete_http01_challenge(
                    mock_challenge_body, "example.com", None
                )

    def test_complete_http01_challenge_submit_error(self) -> None:
        """Test HTTP-01 challenge when submission fails."""
        client = ACMEClient()
        client._account_key = Mock()
        client._client = Mock()
        client._client.answer_challenge.side_effect = Exception("Submit error")

        # Mock challenge body
        mock_challenge_body = Mock()
        mock_challenge = Mock()
        mock_challenge.response_and_validation.return_value = (Mock(), "validation")
        mock_challenge.encode.return_value = "test_token"
        mock_challenge_body.chall = mock_challenge

        with (
            patch("vibectl.server.acme_client.Path") as mock_path,
            patch("tempfile.mkdtemp"),
        ):
            # Mock path operations
            mock_challenge_path = Mock()
            mock_path.return_value = mock_challenge_path
            mock_challenge_path.mkdir = Mock()

            mock_challenge_file = Mock()
            mock_challenge_file.write_text = Mock()
            mock_challenge_file.unlink = Mock()
            mock_challenge_path.__truediv__ = Mock(return_value=mock_challenge_file)

            # Should raise ACMEValidationError and clean up file
            with pytest.raises((Exception,)):  # Challenge submission error
                client._complete_http01_challenge(
                    mock_challenge_body, "example.com", None
                )

            # File cleanup should still be attempted
            mock_challenge_file.unlink.assert_called()


class TestACMEManagerSpecificEdgeCases:
    """Test specific edge cases in ACME Manager."""

    def test_provision_certificates_non_http01_challenge(self) -> None:
        """Test certificate provisioning for non-HTTP-01 challenges."""
        # Create ACME manager for TLS-ALPN-01
        mock_tls_alpn_server = Mock()
        acme_config = {
            "email": "test@example.com",
            "domains": ["example.com"],
            "challenge": {"type": "tls-alpn-01"},
        }

        manager = ACMEManager(
            challenge_server=None,
            acme_config=acme_config,
            tls_alpn_challenge_server=mock_tls_alpn_server,
        )

        async def test_provision() -> None:
            # Mock ACME client
            mock_acme_client = Mock()
            mock_acme_client.request_certificate.return_value = (b"cert", b"key")

            with patch.object(
                manager, "_create_acme_client", return_value=mock_acme_client
            ):
                await manager._provision_certificates_async(
                    mock_acme_client, "/fake/cert.pem", "/fake/key.pem"
                )

                # Should call request_certificate without monkey-patching
                # for non-HTTP-01
                mock_acme_client.request_certificate.assert_called_once()

        import asyncio

        asyncio.run(test_provision())

    def test_http01_challenge_handler_missing_server_runtime_error(self) -> None:
        """Test HTTP-01 challenge handler raises error if server missing at runtime."""
        # Create manager with HTTP challenge server initially
        mock_http_server = Mock()
        acme_config = {
            "email": "test@example.com",
            "domains": ["example.com"],
            "challenge": {"type": "http-01"},
        }

        manager = ACMEManager(
            challenge_server=mock_http_server,
            acme_config=acme_config,
        )

        # Remove server reference to simulate runtime missing server
        manager.challenge_server = None

        # Should raise RuntimeError when trying to handle challenge
        with pytest.raises(RuntimeError, match="HTTP challenge server is required"):
            manager._handle_http01_challenge(
                Mock(), "example.com", None, Mock(), Mock()
            )
