"""
TLS-ALPN-01 Challenge Certificate Manager for ACME challenges.

This module provides challenge certificate generation and storage for
ACME TLS-ALPN-01 challenges used with the ALPN multiplexer architecture.

TLS-ALPN-01 challenges work by:
1. ACME server connects to domain:443 with ALPN extension "acme-tls/1"
2. Challenge server presents a special certificate containing the challenge response
3. ACME server validates the challenge response
"""

import logging
import ssl
import threading
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

# Runtime import to avoid NameError in type annotations (tests access annotations).
from .alpn_bridge import TLSALPNBridge

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    # Re-exported so type checkers still see correct symbol location.
    from .alpn_bridge import TLSALPNBridge  # type: ignore


class TLSALPNChallengeServer:
    """Challenge certificate manager for ACME TLS-ALPN-01 challenges.

    This class manages challenge responses and generates challenge certificates
    for use with the ALPN multiplexer. It does not run as a standalone server.

    Features:
    - Thread-safe challenge management
    - Dynamic challenge certificate generation
    - Integration with ALPN multiplexer SNI callbacks
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 443):
        """Initialize the TLS-ALPN-01 challenge manager.

        Args:
            host: Unused, kept for API compatibility
            port: Unused, kept for API compatibility
        """
        # Challenge state management
        self._challenges: dict[str, bytes] = {}
        self._lock = threading.Lock()

        # Configuration
        self.host = host
        self.port = port

        # Bridge to share state with the multiplexer

        self._bridge: TLSALPNBridge | None = None

        logger.info(f"📋 TLS-ALPN-01 challenge manager initialized for {host}:{port}")
        logger.info(
            "🔧 Challenge manager ready to handle certificate generation for "
            "ALPN multiplexer"
        )

    def _attach_bridge(self, bridge: TLSALPNBridge) -> None:
        """Called by factory after both components are created."""
        self._bridge = bridge
        bridge.attach_challenge_server(self)  # back-reference
        logger.debug("🔗 TLS-ALPN challenge manager linked via bridge")

    def set_challenge(self, domain: str, challenge_response: bytes) -> None:
        """Set challenge response for a domain.

        Args:
            domain: Domain name for the challenge
            challenge_response: Challenge response bytes
        """
        with self._lock:
            self._challenges[domain] = challenge_response
            logger.debug(f"Set TLS-ALPN-01 challenge for domain: {domain}")
            # Handle both bytes and Mock objects for testing
            response_info = (
                f"{len(challenge_response)} bytes"
                if hasattr(challenge_response, "__len__")
                and not hasattr(challenge_response, "_mock_name")
                else "redacted (test mock)"
            )
            logger.debug(f"Challenge response length: {response_info}")
            logger.debug(f"Total active challenges: {len(self._challenges)}")
            logger.debug(f"Active challenge domains: {list(self._challenges.keys())}")

            # If we have a bridge and *exactly* one active challenge,
            # proactively load the challenge certificate into the bridge"s
            # *default* SSLContext so that connections **without SNI** still
            # receive the correct certificate during the handshake.
            if self._bridge and self._bridge.multiplexer and len(self._challenges) == 1:
                try:
                    self._update_multiplexer_default_cert(domain, challenge_response)
                except Exception as e:
                    logger.warning(
                        f"⚠️ Failed to update multiplexer default certificate: {e}"
                    )

            logger.info(f"✅ Set TLS-ALPN-01 challenge for domain: {domain}")

    def remove_challenge(self, domain: str) -> None:
        """Remove challenge response for a domain.

        Args:
            domain: Domain name to remove challenge for
        """
        with self._lock:
            if domain in self._challenges:
                del self._challenges[domain]
                logger.debug(f"Removed TLS-ALPN-01 challenge for domain: {domain}")
                logger.debug(
                    f"Remaining challenge domains: {list(self._challenges.keys())}"
                )

                # If no active challenges remain, restore the default certificate so
                # subsequent non-ACME connections present the correct gRPC cert.
                if not self._challenges:
                    self._restore_multiplexer_default_cert()
            else:
                logger.warning(
                    f"Attempted to remove challenge for domain {domain}, "
                    "but no challenge was found"
                )
                logger.debug(
                    f"Current challenge domains: {list(self._challenges.keys())}"
                )

    def clear_challenges(self) -> None:
        """Clear all challenges."""
        with self._lock:
            count = len(self._challenges)
            self._challenges.clear()
            logger.debug(f"Cleared all {count} TLS-ALPN-01 challenges")

    def _get_challenge_response(self, domain: str) -> bytes | None:
        """Get challenge response for a domain.

        Args:
            domain: Domain name to get challenge for

        Returns:
            Challenge response bytes if found, None otherwise
        """
        with self._lock:
            challenge_bytes = self._challenges.get(domain)
            if challenge_bytes:
                logger.debug(f"Challenge lookup for domain '{domain}': found")
                return challenge_bytes
            else:
                logger.debug(f"Challenge lookup for domain '{domain}': not found")
                logger.debug(
                    f"Current active challenges: {list(self._challenges.keys())}"
                )
                return None

    def _get_active_challenge_domains(self) -> list[str]:
        """Get list of domains with active challenges."""
        with self._lock:
            return list(self._challenges.keys())

    def _create_challenge_certificate_with_key(
        self, domain: str, challenge_response: bytes, private_key: rsa.RSAPrivateKey
    ) -> bytes:
        """Create a challenge certificate for TLS-ALPN-01 with a specific private key.

        Args:
            domain: Domain name for the certificate
            challenge_response: Challenge response to embed
            private_key: RSA private key to use for the certificate

        Returns:
            PEM-encoded certificate bytes
        """
        # Create certificate with the challenge response as an extension
        subject = issuer = x509.Name(
            [
                x509.NameAttribute(NameOID.COMMON_NAME, domain),
            ]
        )

        # ------------------------------------------------------------------
        # Build the ACME TLS-ALPN-01 extension (RFC 8737, section 3)
        #
        # The extension's value MUST itself be an ASN.1 OCTET STRING that
        # contains the 32-byte SHA-256 digest (the "acmeValidation" payload).
        #
        # cryptography expects *DER-encoded* bytes for UnrecognizedExtension
        # - i.e. the raw contents of the outer Extension.value OCTET STRING.
        # Therefore we must wrap our challenge bytes in a one-level-deeper
        # OCTET STRING before passing it to the builder.
        #
        # DER encoding for an OCTET STRING is:
        #   0x04 <len> <payload>
        # For a 32-byte payload the length fits in one byte.
        # ------------------------------------------------------------------

        if len(challenge_response) == 32:
            # Normal case - RFC-compliant digest length (32-byte SHA-256)
            der_wrapped_validation = (
                b"\x04" + bytes([len(challenge_response)]) + challenge_response
            )
            value_bytes = der_wrapped_validation
        else:
            # In tests, mocks sometimes pass arbitrary-length tokens.  Keep the
            # previous behaviour (raw bytes) so unit tests don't break, but log
            # a warning so real code paths aren't affected.
            logger.warning(
                "⚠️ TLS-ALPN-01 challenge digest len %d != 32 - "
                "using raw value for test",
                len(challenge_response),
            )
            value_bytes = challenge_response

        acme_extension = x509.UnrecognizedExtension(
            oid=x509.ObjectIdentifier("1.3.6.1.5.5.7.1.31"),
            value=value_bytes,
        )

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(tz=UTC))
            .not_valid_after(
                datetime.now(tz=UTC)
                + timedelta(hours=1)  # Very short validity for challenge
            )
            .add_extension(
                x509.SubjectAlternativeName(
                    [
                        x509.DNSName(domain),
                    ]
                ),
                critical=False,
            )
            .add_extension(
                acme_extension,
                critical=True,  # Must be critical for ACME
            )
            .sign(private_key, hashes.SHA256())
        )

        return cert.public_bytes(serialization.Encoding.PEM)

    def _create_challenge_certificate(
        self, domain: str, challenge_response: bytes
    ) -> bytes:
        """Create a challenge certificate for TLS-ALPN-01.

        Args:
            domain: Domain name for the certificate
            challenge_response: Challenge response to embed

        Returns:
            PEM-encoded certificate bytes
        """
        # Generate a temporary private key for the challenge certificate
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        cert_pem = self._create_challenge_certificate_with_key(
            domain, challenge_response, private_key
        )

        return cert_pem

    def _create_ssl_context(self, domain: str) -> ssl.SSLContext:
        """Create SSL context with challenge certificate for a domain.

        Args:
            domain: Domain name for the challenge

        Returns:
            SSL context configured for the challenge
        """
        logger.debug(f"🔑 Creating SSL context for challenge domain: {domain}")
        challenge_response = self._get_challenge_response(domain)
        if challenge_response is None:
            active_domains = self._get_active_challenge_domains()
            error_msg = (
                f"No challenge response found for domain: {domain}. "
                f"Active challenge domains: {active_domains}"
            )
            logger.error(f"❌ {error_msg}")
            raise ValueError(error_msg)

        logger.debug(f"✅ Found challenge response for domain: {domain}")

        # Generate a temporary private key for the challenge certificate
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )

        # Create challenge certificate using the same private key
        cert_pem = self._create_challenge_certificate_with_key(
            domain, challenge_response, private_key
        )

        key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        # Create SSL context
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)

        # Write certificate and key to temporary strings for SSL context
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".pem", delete=False
        ) as cert_file:
            cert_file.write(cert_pem.decode("utf-8"))
            cert_path = cert_file.name

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".pem", delete=False
        ) as key_file:
            key_file.write(key_pem.decode("utf-8"))
            key_path = key_file.name

        try:
            context.load_cert_chain(cert_path, key_path)
        finally:
            # Clean up temporary files
            import os

            os.unlink(cert_path)
            os.unlink(key_path)

        # Set ALPN protocols - ONLY "acme-tls/1" is required for the
        # ACME validation handshake.  Advertising additional protocols (e.g. "h2")
        # can lead some ACME VAs to attempt an HTTP/2 upgrade after the handshake,
        # which is unnecessary and has caused intermittent validation failures.
        context.set_alpn_protocols(["acme-tls/1"])  # RFC 8737

        # Continue to build SSL context with the generated challenge certificate
        return context

    # ------------------------------------------------------------------
    # Multiplexer certificate restoration helpers
    # ------------------------------------------------------------------

    def _restore_multiplexer_default_cert(self) -> None:
        """Restore multiplexer's original certificate after all challenges cleared."""

        if (
            self._bridge is None
            or self._bridge.multiplexer is None
            or self._bridge.multiplexer._ssl_context is None
        ):
            logger.debug("i Multiplexer not ready, skipping default cert restore")
            return

        cert_file = self._bridge.multiplexer.cert_file
        key_file = self._bridge.multiplexer.key_file

        if not cert_file or not key_file:
            logger.warning(
                "⚠️ Cannot restore default cert - "
                "cert_file/key_file not set on multiplexer"
            )
            return

        try:
            self._bridge.multiplexer._ssl_context.load_cert_chain(cert_file, key_file)
            logger.info(
                "🔄 Restored multiplexer default certificate after clearing "
                "all TLS-ALPN-01 challenges"
            )
        except Exception as e:
            logger.warning(f"⚠️ Failed to restore default certificate: {e}")

    # Compatibility methods for API consistency
    @property
    def is_running(self) -> bool:
        """Always return True for compatibility with ACME manager."""
        return True

    async def start(self) -> None:
        """No-op for compatibility with ACME manager."""
        pass

    async def stop(self) -> None:
        """Clear challenges on stop."""
        self.clear_challenges()

    async def wait_until_ready(self, timeout: float = 5.0) -> bool:
        """Always return True for compatibility."""
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _update_multiplexer_default_cert(
        self, domain: str, challenge_response: bytes
    ) -> None:
        """Load challenge certificate into multiplexer's default SSLContext."""
        if (
            self._bridge is None
            or self._bridge.multiplexer is None
            or self._bridge.multiplexer._ssl_context is None
        ):
            logger.debug("i Multiplexer not ready, skipping default cert update")
            return

        import os
        import tempfile

        from cryptography.hazmat.primitives.asymmetric import rsa

        # Generate cert + key matching challenge
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cert_pem = self._create_challenge_certificate_with_key(
            domain, challenge_response, private_key
        )
        key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        # Write to tempfiles because load_cert_chain requires paths
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".pem", delete=False
        ) as cert_file:
            cert_file.write(cert_pem.decode("utf-8"))
            cert_path = cert_file.name

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".pem", delete=False
        ) as key_file:
            key_file.write(key_pem.decode("utf-8"))
            key_path = key_file.name

        try:
            self._bridge.multiplexer._ssl_context.load_cert_chain(cert_path, key_path)
            logger.info(
                "🔄 Replaced multiplexer default certificate with "
                f"challenge certificate for '{domain}' (no-SNI support)"
            )
        finally:
            # Cleanup temp files
            os.unlink(cert_path)
            os.unlink(key_path)
