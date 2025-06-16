"""
Tests for TLS-ALPN-01 challenge server functionality.

Tests basic server lifecycle, challenge management, and certificate generation
without requiring actual network connections.
"""

import contextlib
from unittest.mock import Mock, patch

import pytest
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import rsa

from vibectl.server.tls_alpn_challenge_server import TLSALPNChallengeServer


class TestTLSALPNChallengeServer:
    """Test TLS-ALPN challenge certificate manager functionality."""

    def test_init_default_values(self) -> None:
        """Test challenge manager initialization with default values."""
        server = TLSALPNChallengeServer()

        # Challenge manager is always ready
        assert server.is_running

    def test_init_custom_values(self) -> None:
        """Test challenge manager initialization with custom values."""
        server = TLSALPNChallengeServer(host="127.0.0.1", port=8443)

        # Challenge manager is always ready (host/port are for API compatibility)
        assert server.is_running

    def test_set_challenge(self) -> None:
        """Test setting challenge response."""
        server = TLSALPNChallengeServer()
        domain = "example.com"
        challenge_response = b"test_challenge_response"

        server.set_challenge(domain, challenge_response)

        # Verify challenge is stored
        assert server._get_challenge_response(domain) == challenge_response

    def test_remove_challenge(self) -> None:
        """Test removing challenge response."""
        server = TLSALPNChallengeServer()
        domain = "example.com"
        challenge_response = b"test_challenge_response"

        # Set and then remove challenge
        server.set_challenge(domain, challenge_response)
        assert server._get_challenge_response(domain) == challenge_response

        server.remove_challenge(domain)
        assert server._get_challenge_response(domain) is None

    def test_clear_challenges(self) -> None:
        """Test clearing all challenges."""
        server = TLSALPNChallengeServer()

        # Set multiple challenges
        server.set_challenge("example1.com", b"response1")
        server.set_challenge("example2.com", b"response2")

        # Clear all challenges
        server.clear_challenges()

        assert server._get_challenge_response("example1.com") is None
        assert server._get_challenge_response("example2.com") is None

    def test_create_challenge_certificate(self) -> None:
        """Test challenge certificate generation."""
        server = TLSALPNChallengeServer()
        domain = "example.com"
        challenge_response = b"test_challenge_response"

        # Generate certificate
        cert_pem = server._create_challenge_certificate(domain, challenge_response)

        # Verify it's valid PEM
        assert b"-----BEGIN CERTIFICATE-----" in cert_pem
        assert b"-----END CERTIFICATE-----" in cert_pem

        # Parse the certificate
        cert = x509.load_pem_x509_certificate(cert_pem)

        # Verify basic properties
        assert (
            cert.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)[0].value
            == domain
        )

        # Verify SAN
        san_ext = cert.extensions.get_extension_for_oid(
            x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME
        )
        san_names = [name.value for name in san_ext.value]  # type: ignore[attr-defined]
        assert domain in san_names

        # Verify ACME extension exists and is critical
        acme_ext = None
        with contextlib.suppress(x509.ExtensionNotFound):
            acme_ext = cert.extensions.get_extension_for_oid(
                x509.ObjectIdentifier("1.3.6.1.5.5.7.1.31")
            )

        assert acme_ext is not None
        assert acme_ext.critical is True
        assert acme_ext.value.value == challenge_response  # type: ignore[attr-defined]

    def test_create_challenge_certificate_with_key(self) -> None:
        """Test challenge certificate generation with specific key."""
        server = TLSALPNChallengeServer()
        domain = "example.com"
        challenge_response = b"test_challenge_response"

        # Generate a private key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )

        # Generate certificate with specific key
        cert_pem = server._create_challenge_certificate_with_key(
            domain, challenge_response, private_key
        )

        # Parse the certificate
        cert = x509.load_pem_x509_certificate(cert_pem)

        # Verify the public key matches
        cert_public_key = cert.public_key()
        assert isinstance(cert_public_key, rsa.RSAPublicKey)
        expected_public_key = private_key.public_key()

        # Compare public key numbers
        assert (
            cert_public_key.public_numbers().n == expected_public_key.public_numbers().n
        )
        assert (
            cert_public_key.public_numbers().e == expected_public_key.public_numbers().e
        )

    def test_create_ssl_context(self) -> None:
        """Test SSL context creation for challenge."""
        server = TLSALPNChallengeServer()
        domain = "example.com"
        challenge_response = b"test_challenge_response"

        # Set challenge
        server.set_challenge(domain, challenge_response)

        with (
            patch("tempfile.NamedTemporaryFile") as mock_tempfile,
            patch("ssl.create_default_context") as mock_ssl_context,
            patch("os.unlink"),
        ):
            # Mock context manager for temporary files
            mock_cert_file = Mock()
            mock_cert_file.name = "/tmp/cert.pem"
            mock_cert_file.__enter__ = Mock(return_value=mock_cert_file)
            mock_cert_file.__exit__ = Mock(return_value=None)

            mock_key_file = Mock()
            mock_key_file.name = "/tmp/key.pem"
            mock_key_file.__enter__ = Mock(return_value=mock_key_file)
            mock_key_file.__exit__ = Mock(return_value=None)

            mock_tempfile.side_effect = [mock_cert_file, mock_key_file]

            mock_context = Mock()
            mock_ssl_context.return_value = mock_context

            # Create SSL context
            context = server._create_ssl_context(domain)

            # Verify SSL context configuration
            assert context == mock_context
            mock_context.load_cert_chain.assert_called_once()
            mock_context.set_alpn_protocols.assert_called_once_with(["acme-tls/1"])

    def test_create_ssl_context_no_challenge(self) -> None:
        """Test SSL context creation with no challenge."""
        server = TLSALPNChallengeServer()
        domain = "example.com"

        # Should raise ValueError for missing challenge
        with pytest.raises(ValueError, match="No challenge response found"):
            server._create_ssl_context(domain)

    async def test_lifecycle_methods(self) -> None:
        """Test start/stop lifecycle methods (no-ops for compatibility)."""
        server = TLSALPNChallengeServer()

        # Challenge manager is always ready
        assert server.is_running

        # Start is a no-op
        await server.start()
        assert server.is_running

        # Stop clears challenges
        server.set_challenge("test.com", b"response")
        await server.stop()
        assert server.is_running  # Still "running" but challenges cleared
        assert server._get_challenge_response("test.com") is None

    async def test_wait_until_ready(self) -> None:
        """Test waiting for challenge manager to be ready."""
        server = TLSALPNChallengeServer()

        # Challenge manager is always ready
        ready = await server.wait_until_ready(timeout=2.0)
        assert ready

    def test_get_active_challenge_domains(self) -> None:
        """Test getting list of active challenge domains."""
        server = TLSALPNChallengeServer()

        # Initially empty
        assert server._get_active_challenge_domains() == []

        # Add some challenges
        server.set_challenge("example1.com", b"response1")
        server.set_challenge("example2.com", b"response2")

        # Should return domains
        domains = server._get_active_challenge_domains()
        assert set(domains) == {"example1.com", "example2.com"}

        # Remove one challenge
        server.remove_challenge("example1.com")
        domains = server._get_active_challenge_domains()
        assert domains == ["example2.com"]

        # Clear all
        server.clear_challenges()
        assert server._get_active_challenge_domains() == []

    @patch("vibectl.server.tls_alpn_challenge_server.logger")
    def test_sensitive_challenge_response_redaction_in_logs(
        self, mock_logger: Mock
    ) -> None:
        """Test that challenge response data is redacted in debug logs."""
        server = TLSALPNChallengeServer()

        # Test challenge response data that should be redacted
        test_domain = "test.example.com"
        test_challenge_response = (
            b"secret_challenge_response_data_32bytes!!"  # 32 bytes
        )

        # Set challenge
        server.set_challenge(test_domain, test_challenge_response)

        # Verify debug log redacts the challenge response
        debug_calls = list(mock_logger.debug.call_args_list)
        challenge_length_logged = False

        for call in debug_calls:
            call_msg = call[0][0] if call[0] else ""
            if "Challenge response length:" in call_msg:
                challenge_length_logged = True
                # Should log length but not the actual response data
                assert str(len(test_challenge_response)) in call_msg
                assert (
                    test_challenge_response.hex() not in call_msg
                )  # Hex data should not be logged
                assert (
                    "secret_challenge_response" not in call_msg
                )  # Original data should not be logged

        assert challenge_length_logged, "Challenge response length should be logged"

        # Verify other debug information is still present
        domain_logged = False
        active_challenges_logged = False

        for call in debug_calls:
            call_msg = call[0][0] if call[0] else ""
            if f"Set TLS-ALPN-01 challenge for domain: {test_domain}" in call_msg:
                domain_logged = True
            if "Total active challenges:" in call_msg:
                active_challenges_logged = True

        assert domain_logged, "Domain should still be logged"
        assert active_challenges_logged, "Active challenge count should still be logged"
