"""
ACME client for automatic certificate provisioning via Let's Encrypt.

This module provides functionality for requesting, validating, and renewing
TLS certificates from ACME-compatible certificate authorities like Let's Encrypt.
"""

import logging
from datetime import datetime, timedelta

import acme.challenges
import acme.client
import acme.errors
import acme.messages
import josepy as jose
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import rsa

from vibectl.types import ACMECertificateError

from .ca_manager import CertificateInfo

logger = logging.getLogger(__name__)


class ACMEClient:
    """ACME client for automatic certificate provisioning.

    This client handles the ACME protocol flow:
    1. Account registration with the ACME server
    2. Domain authorization and validation
    3. Certificate signing request (CSR) generation
    4. Certificate issuance and retrieval
    5. Certificate renewal automation
    """

    def __init__(
        self,
        directory_url: str = "https://acme-v02.api.letsencrypt.org/directory",
        email: str | None = None,
        key_size: int = 2048,
    ):
        """Initialize ACME client.

        Args:
            directory_url: ACME directory URL (defaults to Let's Encrypt)
            email: Contact email for certificate registration
            key_size: RSA key size for generated keys
        """
        self.directory_url = directory_url
        self.email = email
        self.key_size = key_size
        self._client: acme.client.ClientV2 | None = None
        self._account_key: jose.JWKRSA | None = None
        self._client_net: acme.client.ClientNetwork | None = None

    def _ensure_client(self) -> None:
        """Ensure ACME client is initialized."""
        if self._client is None:
            # Generate account key if not provided
            if self._account_key is None:
                self._account_key = jose.JWKRSA(
                    key=rsa.generate_private_key(
                        public_exponent=65537,
                        key_size=2048,
                    )
                )

            # Create ACME client network interface
            self._client_net = acme.client.ClientNetwork(
                key=self._account_key, user_agent="vibectl-server/1.0"
            )

            # Initialize ACME client
            directory = acme.messages.Directory.from_json(
                self._client_net.get(self.directory_url).json()
            )
            self._client = acme.client.ClientV2(directory, net=self._client_net)

    def register_account(self) -> None:
        """Register ACME account with the CA."""
        self._ensure_client()

        try:
            # Create new account registration
            new_account = acme.messages.NewRegistration.from_data(
                email=self.email, terms_of_service_agreed=True
            )

            # Register account
            assert (
                self._client is not None
            )  # mypy hint - _ensure_client guarantees this
            self._client.new_account(new_account)
            logger.info("ACME account registered successfully")

        except acme.errors.ConflictError:
            # Account already exists
            logger.info("ACME account already exists")

    def request_certificate(
        self,
        domains: list[str],
        challenge_type: str = "http-01",
        cert_file: str | None = None,
        key_file: str | None = None,
        challenge_dir: str | None = None,
    ) -> tuple[bytes, bytes]:
        """Request a certificate for the specified domains.

        Args:
            domains: List of domain names to include in certificate
            challenge_type: ACME challenge type ("http-01" or "dns-01")
            cert_file: Optional path to save certificate
            key_file: Optional path to save private key
            challenge_dir: Directory for HTTP-01 challenge files

        Returns:
            Tuple of (cert_bytes, key_bytes)

        Raises:
            ACMECertificateError: If certificate request fails
        """
        # For now, this is a placeholder that shows the intended workflow
        # Full implementation would require careful handling of ACME protocol details
        raise ACMECertificateError(
            "ACME certificate provisioning not yet fully implemented. "
            "This is a placeholder for the Let's Encrypt "
            "integration planned in Phase 2."
        )

    def check_certificate_expiry(self, cert_file: str) -> datetime | None:
        """Check certificate expiration date.

        Args:
            cert_file: Path to certificate file

        Returns:
            Certificate expiration datetime, or None if file doesn't exist
        """
        try:
            with open(cert_file, "rb") as f:
                cert_data = f.read()

            cert = x509.load_pem_x509_certificate(cert_data)
            cert_info = CertificateInfo(cert)
            return cert_info.not_valid_after

        except FileNotFoundError:
            return None
        except Exception as e:
            logger.warning(f"Failed to check certificate expiry: {e}")
            return None

    def needs_renewal(self, cert_file: str, days_before_expiry: int = 30) -> bool:
        """Check if certificate needs renewal.

        Args:
            cert_file: Path to certificate file
            days_before_expiry: Number of days before expiry to trigger renewal

        Returns:
            True if certificate needs renewal, False otherwise
        """
        expiry_date = self.check_certificate_expiry(cert_file)
        if not expiry_date:
            return True  # Certificate doesn't exist, needs initial provisioning

        renewal_date = datetime.now().astimezone() + timedelta(days=days_before_expiry)
        return expiry_date <= renewal_date


def create_acme_client(
    directory_url: str = "https://acme-v02.api.letsencrypt.org/directory",
    email: str | None = None,
    staging: bool = False,
) -> ACMEClient:
    """Create an ACME client instance.

    Args:
        directory_url: ACME directory URL
        email: Contact email for registration
        staging: Use Let's Encrypt staging environment

    Returns:
        Configured ACME client
    """
    if staging:
        directory_url = "https://acme-staging-v02.api.letsencrypt.org/directory"

    return ACMEClient(directory_url=directory_url, email=email)
