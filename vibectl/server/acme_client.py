"""
ACME client for automatic certificate provisioning via Let's Encrypt.

This module provides functionality for requesting, validating, and renewing
TLS certificates from ACME-compatible certificate authorities like Let's Encrypt.
"""

import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

import acme
import acme.errors
import josepy as jose
from acme import client, messages
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from vibectl.types import (
    ACMECertificateError,
    ACMEValidationError,
)

from .ca_manager import CertificateInfo
from .cert_utils import create_certificate_signing_request

logger = logging.getLogger(__name__)

# ACME Directory URL Constants
LETSENCRYPT_PRODUCTION = "https://acme-v02.api.letsencrypt.org/directory"
LETSENCRYPT_STAGING = "https://acme-staging-v02.api.letsencrypt.org/directory"


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
        directory_url: str = LETSENCRYPT_PRODUCTION,
        email: str | None = None,
        key_size: int = 2048,
    ):
        """Initialize ACME client.

        Args:
            directory_url: ACME directory URL (defaults to Let's Encrypt production)
            email: Contact email for certificate registration
            key_size: RSA key size for generated keys
        """
        self.directory_url = directory_url
        self.email = email
        self.key_size = key_size
        self._client: client.ClientV2 | None = None
        self._account_key: jose.JWKRSA | None = None
        self._client_net: client.ClientNetwork | None = None

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
            self._client_net = client.ClientNetwork(
                key=self._account_key, user_agent="vibectl-server/1.0"
            )

            # Initialize ACME client
            directory = messages.Directory.from_json(
                self._client_net.get(self.directory_url).json()
            )
            self._client = client.ClientV2(directory, net=self._client_net)

    def register_account(self) -> None:
        """Register ACME account with the CA."""
        self._ensure_client()

        try:
            # Create new account registration
            new_account = messages.NewRegistration.from_data(
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
            ACMEValidationError: If domain validation fails
        """
        logger.info(f"Requesting ACME certificate for domains: {domains}")

        try:
            self._ensure_client()
            assert self._client is not None  # mypy hint

            # Register account if needed
            self.register_account()

            # Generate private key for the certificate
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=self.key_size,
            )

            # Create CSR for the domains
            csr = self._create_csr(domains, private_key)

            # Create order with CSR PEM bytes (correct ACME API usage)
            order = self._client.new_order(
                csr.csr.public_bytes(serialization.Encoding.PEM)
            )
            logger.info(f"Created ACME order: {order.uri}")

            # Process authorizations for each domain
            for authz in order.authorizations:
                self._complete_authorization(authz, challenge_type, challenge_dir)

            # Finalize the order - the ACME client will handle polling automatically
            final_order = self._client.finalize_order(
                order, datetime.now() + timedelta(seconds=300)
            )

            # Extract certificate chain
            cert_chain = final_order.fullchain_pem.encode("utf-8")

            # Serialize private key
            private_key_bytes = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )

            # Save to files if requested
            if cert_file:
                cert_path = Path(cert_file)
                cert_path.parent.mkdir(parents=True, exist_ok=True)
                cert_path.write_bytes(cert_chain)
                logger.info(f"Certificate saved to {cert_file}")

            if key_file:
                key_path = Path(key_file)
                key_path.parent.mkdir(parents=True, exist_ok=True)
                key_path.write_bytes(private_key_bytes)
                logger.info(f"Private key saved to {key_file}")

            logger.info("ACME certificate provisioning completed successfully")
            return cert_chain, private_key_bytes

        except acme.errors.ValidationError as e:
            raise ACMEValidationError(f"Domain validation failed: {e}") from e
        except acme.errors.Error as e:
            raise ACMECertificateError(f"ACME certificate request failed: {e}") from e
        except Exception as e:
            raise ACMECertificateError(
                f"Unexpected error during certificate request: {e}"
            ) from e

    def _complete_authorization(
        self,
        authz: messages.AuthorizationResource,
        challenge_type: str,
        challenge_dir: str | None,
    ) -> None:
        """Complete domain authorization using the specified challenge type.

        Args:
            authz: Authorization resource from ACME server
            challenge_type: Type of challenge to complete ("http-01" or "dns-01")
            challenge_dir: Directory for HTTP-01 challenge files
        """
        domain = authz.body.identifier.value
        logger.info(f"Completing authorization for domain: {domain}")

        # Find the appropriate challenge
        challenge_body = None
        for chall_body in authz.body.challenges:
            if chall_body.chall.typ == challenge_type:
                challenge_body = chall_body
                break

        if challenge_body is None:
            raise ACMEValidationError(
                f"No {challenge_type} challenge found for domain {domain}"
            )

        if challenge_type == "http-01":
            self._complete_http01_challenge(challenge_body, domain, challenge_dir)
        elif challenge_type == "dns-01":
            self._complete_dns01_challenge(challenge_body, domain)
        else:
            raise ACMEValidationError(f"Unsupported challenge type: {challenge_type}")

        # Wait for authorization validation
        self._wait_for_authorization_validation(authz)

    def _complete_http01_challenge(
        self,
        challenge_body: messages.ChallengeBody,
        domain: str,
        challenge_dir: str | None,
    ) -> None:
        """Complete HTTP-01 challenge by creating the required challenge file.

        Args:
            challenge_body: HTTP-01 challenge body from authorization
            domain: Domain being validated
            challenge_dir: Directory to place challenge files
        """
        # Ensure we have the account key
        assert self._account_key is not None

        # Get the actual challenge object
        challenge = challenge_body.chall

        # Generate challenge response
        response, validation = challenge.response_and_validation(self._account_key)

        # Determine challenge directory
        if challenge_dir is None:
            challenge_dir = ".well-known/acme-challenge"

        challenge_path = Path(challenge_dir)
        challenge_path.mkdir(parents=True, exist_ok=True)

        # Write challenge file
        # Decode token if it's bytes, otherwise use as-is
        token_str = (
            challenge.token.decode("utf-8")
            if isinstance(challenge.token, bytes)
            else challenge.token
        )
        challenge_file = challenge_path / token_str
        challenge_file.write_text(validation)

        logger.info(f"Created HTTP-01 challenge file: {challenge_file}")
        logger.info(
            f"Challenge must be accessible at: http://{domain}/.well-known/acme-challenge/{token_str}"
        )

        try:
            # Submit challenge response
            assert self._client is not None
            self._client.answer_challenge(challenge_body, response)

        finally:
            # Clean up challenge file
            try:
                challenge_file.unlink()
                logger.info(f"Cleaned up challenge file: {challenge_file}")
            except Exception as e:
                logger.warning(f"Failed to clean up challenge file: {e}")

    def _complete_dns01_challenge(
        self, challenge_body: messages.ChallengeBody, domain: str
    ) -> None:
        """Complete DNS-01 challenge.

        Args:
            challenge_body: DNS-01 challenge body from authorization
            domain: Domain being validated
        """
        # Ensure we have the account key
        assert self._account_key is not None

        # Get the actual challenge object
        challenge = challenge_body.chall

        # Generate challenge response
        response, validation = challenge.response_and_validation(self._account_key)

        # Calculate the DNS record value
        dns_record = f"_acme-challenge.{domain}"

        logger.warning(
            f"DNS-01 challenge requires manual DNS record creation:\n"
            f"Record: {dns_record}\n"
            f"Type: TXT\n"
            f"Value: {validation}\n"
            f"Please create this DNS record and press Enter to continue..."
        )

        # Wait for user confirmation (in a production system, this would
        # integrate with DNS APIs)
        input("Press Enter after creating the DNS record...")

        # Submit challenge response
        assert self._client is not None
        self._client.answer_challenge(challenge_body, response)

    def _wait_for_authorization_validation(
        self, authz: messages.AuthorizationResource, timeout: int = 300
    ) -> None:
        """Wait for authorization validation to complete.

        Args:
            authz: Authorization resource to wait for
            timeout: Maximum time to wait in seconds
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                assert self._client is not None
                updated_authz, _ = self._client.poll(authz)

                if updated_authz.body.status == messages.STATUS_VALID:
                    logger.info("Authorization validation completed successfully")
                    return
                elif updated_authz.body.status == messages.STATUS_INVALID:
                    raise ACMEValidationError(
                        f"Authorization validation failed: {updated_authz.body}"
                    )

                # Still pending, wait and retry
                time.sleep(5)

            except Exception as e:
                if "still pending" in str(e).lower():
                    time.sleep(5)
                    continue
                raise ACMEValidationError(f"Authorization validation error: {e}") from e

        raise ACMEValidationError(
            f"Authorization validation timed out after {timeout} seconds"
        )

    def _create_csr(
        self, domains: list[str], private_key: rsa.RSAPrivateKey
    ) -> messages.CertificateRequest:
        """Create a Certificate Signing Request for the given domains.

        Args:
            domains: List of domain names
            private_key: Private key for the certificate

        Returns:
            CSR object for ACME submission
        """
        # Use generic CSR creation function
        csr = create_certificate_signing_request(domains, private_key)

        # Convert to ACME format
        return messages.CertificateRequest(csr=csr)

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
    directory_url: str = LETSENCRYPT_PRODUCTION,
    email: str | None = None,
) -> ACMEClient:
    """Create an ACME client instance.

    Args:
        directory_url: ACME directory URL (defaults to Let's Encrypt production)
        email: Contact email for registration

    Returns:
        Configured ACME client

    Examples:
        # Production Let's Encrypt
        client = create_acme_client(email="admin@example.com")

        # Staging Let's Encrypt
        client = create_acme_client(
            directory_url=LETSENCRYPT_STAGING,
            email="admin@example.com"
        )

        # Custom ACME server
        client = create_acme_client(
            directory_url="https://ca.example.com/acme/directory",
            email="admin@example.com"
        )
    """
    return ACMEClient(directory_url=directory_url, email=email)
