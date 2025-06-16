"""
ACME client for automatic certificate provisioning via Let's Encrypt.

This module provides functionality for requesting, validating, and renewing
TLS certificates from ACME-compatible certificate authorities like Let's Encrypt.
"""

import hashlib
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

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
        ca_cert_file: str | None = None,
        tls_alpn_challenge_server: Any = None,
    ):
        """Initialize ACME client.

        Args:
            directory_url: ACME directory URL
            email: Email for account registration
            key_size: RSA key size for generated keys
            ca_cert_file: Path to custom CA certificate file for SSL verification
            tls_alpn_challenge_server: TLS-ALPN challenge server for
                                      TLS-ALPN-01 challenges
        """
        self.directory_url = directory_url
        self.email = email
        self.key_size = key_size
        self.ca_cert_file = ca_cert_file
        self.tls_alpn_challenge_server = tls_alpn_challenge_server
        self._client: client.ClientV2 | None = None
        self._account_key: jose.JWKRSA | None = None
        # Track HTTP-01 challenge files for cleanup after validation
        self._http01_challenge_files: dict[str, Path] = {}

    def _ensure_client(self) -> None:
        """Ensure the ACME client is initialized."""
        if self._client is not None:
            return

        from acme import client as acme_client, messages as acme_messages
        from acme.client import ClientNetwork

        # Generate account key if not provided
        if self._account_key is None:
            self._account_key = jose.JWKRSA(
                key=rsa.generate_private_key(
                    public_exponent=65537,
                    key_size=2048,
                )
            )

        try:
            # Configure CA certificate via REQUESTS_CA_BUNDLE environment variable
            if self.ca_cert_file and os.path.isfile(self.ca_cert_file):
                logger.info(f"Using custom CA certificate: {self.ca_cert_file}")
                logger.debug(
                    f"CA file size: {os.path.getsize(self.ca_cert_file)} bytes"
                )

                # Read and log CA certificate content preview
                with open(self.ca_cert_file) as f:
                    ca_content = f.read()
                    preview_lines = ca_content.split("\n")[:5]  # First 5 lines
                    logger.debug(
                        f"CA certificate content preview: {chr(10).join(preview_lines)}"
                    )
                    if len(ca_content) > 300:
                        end_lines = ca_content.split("\n")[-3:]  # Last 3 lines
                        logger.debug(
                            "CA certificate content ends with: "
                            f"...{chr(10).join(end_lines)}"
                        )

                # Set REQUESTS_CA_BUNDLE environment variable for server operations
                os.environ["REQUESTS_CA_BUNDLE"] = self.ca_cert_file
                logger.debug(f"Set REQUESTS_CA_BUNDLE={self.ca_cert_file}")

            # Create ClientNetwork with standard SSL verification
            net = ClientNetwork(
                key=self._account_key, verify_ssl=True, user_agent="vibectl-server/1.0"
            )
            logger.debug("Created ACME network client with standard SSL verification")

            # Test the network client connection
            logger.debug(
                f"Testing ACME network client connection to: {self.directory_url}"
            )
            try:
                directory_response = net.get(self.directory_url)
                logger.debug("ACME network client test successful")
            except Exception as net_test_error:
                logger.error(f"ACME network client test failed: {net_test_error}")
                raise ACMECertificateError(
                    f"Failed to connect to ACME server: {net_test_error}"
                ) from net_test_error

            # Parse directory
            directory = acme_messages.Directory.from_json(directory_response.json())

            # Create ACME client
            self._client = acme_client.ClientV2(directory, net=net)
            logger.debug("ACME client initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize ACME client: {e}")
            raise ACMECertificateError(f"Failed to initialize ACME client: {e}") from e

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
        challenge_type: str = "tls-alpn-01",
        cert_file: str | None = None,
        key_file: str | None = None,
        challenge_dir: str | None = None,
        _retry: bool = False,
    ) -> tuple[bytes, bytes]:
        """Request a certificate for the specified domains.

        Args:
            domains: List of domain names to include in certificate
            challenge_type: ACME challenge type ("http-01", "dns-01", or "tls-alpn-01")
            cert_file: Optional path to save certificate
            key_file: Optional path to save private key
            challenge_dir: Directory for HTTP-01 challenge files
            _retry: Whether to retry the request after a bad nonce error

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
                # Set secure permissions for certificate file (644)
                cert_path.chmod(0o644)
                logger.info(f"Certificate saved to {cert_file}")

            if key_file:
                key_path = Path(key_file)
                key_path.parent.mkdir(parents=True, exist_ok=True)
                key_path.write_bytes(private_key_bytes)
                # Set secure permissions for private key file (600)
                key_path.chmod(0o600)
                logger.info(f"Private key saved to {key_file}")

            logger.info("ACME certificate provisioning completed successfully")
            return cert_chain, private_key_bytes

        except acme.errors.ValidationError as e:
            raise ACMEValidationError(f"Domain validation failed: {e}") from e
        except acme.errors.BadNonce as e:
            # RFC 8555 §6.5 mandates the client to retry once with a fresh nonce
            # when the server returns badNonce.
            if _retry:
                raise ACMECertificateError(
                    f"ACME certificate request failed after nonce retry: {e}"
                ) from e

            logger.warning(
                "Bad nonce from ACME CA - fetching a fresh nonce and retrying once"
            )

            # Fetch a new nonce (directory['newNonce'] is guaranteed)
            assert self._client is not None
            try:
                _ = self._client.net.get(self._client.directory["newNonce"])
            except Exception as nonce_err:  # pragma: no cover - unlikely
                raise ACMECertificateError(
                    f"Failed to refresh nonce after badNonce error: {nonce_err}"
                ) from e

            # Retry the whole flow once
            return self.request_certificate(
                domains,
                challenge_type,
                cert_file,
                key_file,
                challenge_dir,
                _retry=True,
            )

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
            challenge_type: Type of challenge to complete
                           ("http-01", "dns-01", or "tls-alpn-01")
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
            available_types = [
                chall_body.chall.typ for chall_body in authz.body.challenges
            ]
            logger.error(
                f"No {challenge_type} challenge found. Available: {available_types}"
            )
            raise ACMEValidationError(
                f"No {challenge_type} challenge found for domain {domain}. "
                f"Available: {available_types}"
            )

        if challenge_type == "http-01":
            self._complete_http01_challenge(challenge_body, domain, challenge_dir)
        elif challenge_type == "dns-01":
            self._complete_dns01_challenge(challenge_body, domain)
        elif challenge_type == "tls-alpn-01":
            self._complete_tls_alpn01_challenge(challenge_body, domain)
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

        # Generate challenge response with debugging
        try:
            response, validation = challenge.response_and_validation(self._account_key)
        except Exception as response_error:
            logger.error(f"Error generating challenge response: {response_error}")
            raise ACMEValidationError(
                f"Failed to generate challenge response: {response_error}"
            ) from response_error

        # Determine challenge directory
        if challenge_dir is None:
            challenge_dir = ".well-known/acme-challenge"

        challenge_path = Path(challenge_dir)
        challenge_path.mkdir(parents=True, exist_ok=True)

        # Write challenge file
        try:
            token_str = challenge.encode("token")
        except Exception as encode_error:
            logger.error(f"Error encoding challenge token: {encode_error}")
            raise ACMEValidationError(
                f"Failed to encode challenge token: {encode_error}"
            ) from encode_error

        challenge_file = challenge_path / token_str

        try:
            challenge_file.write_text(validation)
        except Exception as write_error:
            logger.error(f"Error writing challenge file: {write_error}")
            raise ACMEValidationError(
                f"Failed to write challenge file: {write_error}"
            ) from write_error

        logger.info(f"Created HTTP-01 challenge file: {challenge_file}")
        logger.info(
            f"Challenge must be accessible at: http://{domain}/.well-known/acme-challenge/{token_str}"
        )

        # Store challenge file for later cleanup
        self._http01_challenge_files[domain] = challenge_file

        try:
            # Submit challenge response
            assert self._client is not None
            self._client.answer_challenge(challenge_body, response)

        except Exception as submit_error:
            logger.error(f"Error submitting challenge response: {submit_error}")
            # Clean up on submission error only
            self._cleanup_http01_challenge_file(domain)
            raise ACMEValidationError(
                f"Failed to submit challenge response: {submit_error}"
            ) from submit_error

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

        # Convert validation to string if it's bytes
        validation_str = (
            validation.decode("utf-8") if isinstance(validation, bytes) else validation
        )

        logger.warning(
            f"DNS-01 challenge requires manual DNS record creation:\n"
            f"Record: {dns_record}\n"
            f"Type: TXT\n"
            f"Value: {validation_str}\n"
            f"Please create this DNS record and press Enter to continue..."
        )

        # Wait for user confirmation (in a production system, this would
        # integrate with DNS APIs)
        input("Press Enter after creating the DNS record...")

        # Submit challenge response
        assert self._client is not None
        self._client.answer_challenge(challenge_body, response)

    def _complete_tls_alpn01_challenge(
        self, challenge_body: messages.ChallengeBody, domain: str
    ) -> None:
        """Complete TLS-ALPN-01 challenge.

        The TLS-ALPN-01 challenge requires the server to present a special
        self-signed certificate during the TLS handshake with ALPN extension
        "acme-tls/1" for the domain being validated.

        Args:
            challenge_body: TLS-ALPN-01 challenge body from authorization
            domain: Domain being validated
        """
        logger.debug(f"Starting TLS-ALPN-01 challenge for domain: {domain}")

        # Ensure we have the account key
        assert self._account_key is not None

        # Ensure we have a TLS-ALPN challenge server
        if self.tls_alpn_challenge_server is None:
            raise ACMEValidationError(
                "TLS-ALPN-01 challenge requires a TLS-ALPN challenge server instance"
            )

        # Get the actual challenge object
        challenge = challenge_body.chall

        # Generate challenge response
        response, validation = challenge.response_and_validation(
            self._account_key, domain=domain
        )
        logger.debug("Challenge response generated successfully")

        logger.info(f"TLS-ALPN-01 challenge initiated for domain: {domain}")

        # For TLS-ALPN-01, validation contains (Certificate, PrivateKey), but we need
        # the challenge response hash for our certificate extension.
        # Extract the hash from the response instead.

        key_authorization = challenge.key_authorization(self._account_key)

        # Ensure key_authorization is bytes for hashing
        if isinstance(key_authorization, str):
            key_authorization_bytes = key_authorization.encode("utf-8")
        elif isinstance(key_authorization, bytes):
            key_authorization_bytes = key_authorization
        else:
            key_authorization_bytes = str(key_authorization).encode("utf-8")

        challenge_hash = hashlib.sha256(key_authorization_bytes).digest()

        # Redact sensitive data in debug logs while preserving usefulness
        # Handle both string and Mock objects for testing
        key_auth_info = (
            f"{len(key_authorization)} bytes"
            if hasattr(key_authorization, "__len__")
            and not hasattr(key_authorization, "_mock_name")
            else "redacted (test mock)"
        )
        hash_info = (
            f"{challenge_hash.hex()[:8]}..."
            if hasattr(challenge_hash, "hex")
            and not hasattr(challenge_hash, "_mock_name")
            else "redacted (test mock)"
        )
        logger.debug(f"Key authorization length: {key_auth_info}")
        logger.debug(f"Challenge hash (first 8 hex chars): {hash_info}")

        # Set the challenge response hash in the TLS-ALPN challenge server
        logger.info(
            f"🚀 Setting challenge response in TLS-ALPN server for domain: {domain}"
        )
        logger.debug(f"🔑 Challenge hash: {challenge_hash.hex()[:32]}...")

        # Track timing for challenge setup
        import time

        set_start = time.time()
        self.tls_alpn_challenge_server.set_challenge(domain, challenge_hash)
        set_duration = (time.time() - set_start) * 1000
        logger.debug(f"⏱️ Challenge set completed in {set_duration:.1f}ms")

        self._wait_for_tls_port_ready(domain, 443, timeout=15.0)

        try:
            # Submit challenge response to ACME server
            assert self._client is not None
            submit_start = time.time()
            self._client.answer_challenge(challenge_body, response)
            submit_duration = (time.time() - submit_start) * 1000
            logger.info(
                "✅ Challenge response submitted successfully "
                f"in {submit_duration:.1f}ms"
            )

            logger.info(
                "🎯 TLS-ALPN-01 challenge setup complete, ACME server "
                "will now validate..."
            )

        except Exception as submit_error:
            # Clean up challenge response on error
            logger.warning(
                f"⚠️ Challenge submission failed, cleaning up for domain: {domain}"
            )
            self.tls_alpn_challenge_server.remove_challenge(domain)
            logger.debug(f"🧹 Cleaned up TLS-ALPN challenge for domain: {domain}")
            logger.error(f"❌ Error submitting challenge response: {submit_error}")
            raise ACMEValidationError(
                f"Failed to submit challenge response: {submit_error}"
            ) from submit_error

    def _wait_for_authorization_validation(
        self, authz: messages.AuthorizationResource, timeout: int = 300
    ) -> None:
        """Wait for authorization validation to complete."""
        domain_value = authz.body.identifier.value
        logger.info(f"🕐 Waiting for validation of domain: {domain_value}")

        start_time = time.time()
        poll_interval = 1.0  # Start with 1 second

        logger.info(
            f"🔄 Starting authorization validation polling for domain: {domain_value}"
        )
        logger.debug(f"📊 Using fixed polling interval, timeout: {timeout}s")

        # Log current challenge state at start of polling
        if (
            hasattr(self, "tls_alpn_challenge_server")
            and self.tls_alpn_challenge_server
        ):
            active_domains = (
                self.tls_alpn_challenge_server._get_active_challenge_domains()
            )
            logger.info(f"📋 Active challenges at polling start: {active_domains}")

        while time.time() - start_time < timeout:
            try:
                assert self._client is not None
                updated_authz, _ = self._client.poll(authz)

                if updated_authz.body.status == messages.STATUS_VALID:
                    logger.info(
                        "Authorization validation completed successfully "
                        f"for domain: {domain_value}"
                    )
                    # Clean up challenge on success
                    self._cleanup_completed_challenge(updated_authz)
                    return

                elif updated_authz.body.status == messages.STATUS_INVALID:
                    # Extract error details for better logging
                    error_detail = "unknown error"
                    for challenge in updated_authz.body.challenges:
                        if challenge.error:
                            error_detail = challenge.error.detail or str(
                                challenge.error
                            )
                            break

                    logger.error(
                        "❌ Authorization validation failed for domain: "
                        f"{domain_value} - {error_detail}"
                    )
                    # Clean up challenge on failure
                    self._cleanup_completed_challenge(updated_authz)
                    raise ACMEValidationError(
                        "Authorization validation failed for domain "
                        f"{updated_authz.body.identifier.value}: {error_detail}"
                    )

                # Still pending - use fixed polling interval
                elif updated_authz.body.status == messages.STATUS_PENDING:
                    elapsed = time.time() - start_time
                    logger.debug(
                        f"Authorization still pending for domain: {domain_value} "
                        f"(elapsed: {elapsed:.1f}s)"
                    )
                    time.sleep(poll_interval)

                else:
                    # Unknown status
                    logger.warning(
                        f"Unexpected authorization status: {updated_authz.body.status}"
                    )
                    time.sleep(poll_interval)

            except Exception as e:
                if "still pending" in str(e).lower():
                    time.sleep(poll_interval)
                    continue

                logger.error(f"Error during authorization validation polling: {e}")
                raise ACMEValidationError(f"Authorization validation error: {e}") from e

        # Timeout reached - clean up and fail
        elapsed = time.time() - start_time
        logger.error(
            f"Authorization validation timed out after {elapsed:.1f}s "
            f"for domain: {domain_value}"
        )
        # Clean up challenge on timeout
        self._cleanup_completed_challenge(authz)
        raise ACMEValidationError(
            f"Authorization validation timed out after {timeout} seconds"
        )

    def _cleanup_http01_challenge_file(self, domain: str) -> None:
        """Clean up HTTP-01 challenge file for a specific domain.

        Args:
            domain: Domain whose challenge file should be cleaned up
        """
        if domain not in self._http01_challenge_files:
            logger.debug(f"No HTTP-01 challenge file to clean up for domain: {domain}")
            return

        challenge_file = self._http01_challenge_files[domain]
        try:
            challenge_file.unlink()
            logger.info(f"Cleaned up HTTP-01 challenge file: {challenge_file}")
        except Exception as e:
            logger.warning(f"Failed to clean up HTTP-01 challenge file: {e}")
        finally:
            # Remove from tracking regardless of success/failure
            del self._http01_challenge_files[domain]

    def _cleanup_completed_challenge(
        self, authz: messages.AuthorizationResource
    ) -> None:
        """Clean up challenge responses after authorization completion.

        Args:
            authz: Completed authorization resource
        """
        # Extract domain from authorization identifier
        domain = authz.body.identifier.value

        logger.info(f"🧹 Cleaning up challenge for domain: {domain}")

        # Clean up HTTP-01 challenge files
        self._cleanup_http01_challenge_file(domain)

        # Clean up TLS-ALPN challenge server if available
        if self.tls_alpn_challenge_server is not None:
            # Log current state before cleanup
            active_domains_before = (
                self.tls_alpn_challenge_server._get_active_challenge_domains()
            )
            logger.debug(
                f"📋 Active challenges before cleanup: {active_domains_before}"
            )

            # Remove the challenge response from the TLS-ALPN server
            self.tls_alpn_challenge_server.remove_challenge(domain)

            # Log state after cleanup
            active_domains_after = (
                self.tls_alpn_challenge_server._get_active_challenge_domains()
            )
            logger.info(f"✅ Cleaned up TLS-ALPN challenge for domain: {domain}")
            logger.debug(f"📋 Active challenges after cleanup: {active_domains_after}")
        else:
            logger.debug("🚫 No TLS-ALPN challenge server available for cleanup")

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

    @staticmethod
    def _wait_for_tls_port_ready(
        hostname: str, port: int, timeout: float = 15.0, interval: float = 0.5
    ) -> None:
        """Block until TCP connect() to hostname:port succeeds or timeout expires.

        This helps ensure that the Kubernetes Service endpoint has propagated and the
        vibectl-server pod is Ready before we ask the ACME server to connect.

        Args:
            hostname: DNS name or IP to test.
            port: TCP port number.
            timeout: Max seconds to wait.
            interval: Seconds between attempts.
        """
        import socket
        import time

        start = time.time()
        while True:
            try:
                with socket.create_connection((hostname, port), timeout=2):
                    logger.debug(
                        f"✅ Port {port} on {hostname} is reachable - "
                        "continuing with challenge submission"
                    )
                    return
            except (
                socket.gaierror
            ) as exc:  # DNS resolution failure (common in unit tests)
                logger.debug(
                    f"🛑 DNS resolution failed for {hostname}: {exc}. "
                    "Assuming test environment and skipping readiness wait."
                )
                return
            except Exception as exc:  # pylint: disable=broad-except
                elapsed = time.time() - start
                if elapsed >= timeout:
                    logger.warning(
                        "⚠️ Port %s on %s not reachable after %.1fs: %s",
                        port,
                        hostname,
                        elapsed,
                        exc,
                    )
                    return  # we still proceed; ACME server will tell us if it fails
                time.sleep(interval)


def create_acme_client(
    directory_url: str = LETSENCRYPT_PRODUCTION,
    email: str | None = None,
    ca_cert_file: str | None = None,
    tls_alpn_challenge_server: Any = None,
) -> ACMEClient:
    """Create an ACME client instance.

    Args:
        directory_url: ACME directory URL (defaults to Let's Encrypt production)
        email: Contact email for registration
        ca_cert_file: Path to custom CA certificate file for SSL verification
        tls_alpn_challenge_server: TLS-ALPN challenge server for TLS-ALPN-01 challenges

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

        # Custom ACME server with custom CA
        client = create_acme_client(
            directory_url="https://ca.example.com/acme/directory",
            email="admin@example.com",
            ca_cert_file="/path/to/ca.pem"
        )

        # With TLS-ALPN challenge server
        client = create_acme_client(
            email="admin@example.com",
            tls_alpn_challenge_server=challenge_server
        )
    """
    return ACMEClient(
        directory_url=directory_url,
        email=email,
        ca_cert_file=ca_cert_file,
        tls_alpn_challenge_server=tls_alpn_challenge_server,
    )
