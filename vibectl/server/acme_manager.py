"""
Async ACME Certificate Manager.

This module provides asynchronous ACME certificate management that works
in coordination with an HTTP challenge server. It handles certificate
provisioning, renewal, and hot-reloading without blocking the main server.
"""

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from vibectl.types import Error, Result, Success

from .acme_client import create_acme_client
from .http_challenge_server import HTTPChallengeServer

logger = logging.getLogger(__name__)

# Type alias for challenge servers
ChallengeServer = HTTPChallengeServer


class ACMEManager:
    """Async ACME certificate manager.

    Manages ACME certificate lifecycle asynchronously:
    - Certificate provisioning in background
    - Automatic renewal monitoring
    - Integration with challenge servers (HTTP-01, TLS-ALPN-01, etc.)
    - Hot certificate reloading
    - Graceful error handling and retries
    """

    def __init__(
        self,
        challenge_server: HTTPChallengeServer | None,
        acme_config: dict[str, Any],
        cert_reload_callback: Callable[[str, str], None] | None = None,
        tls_alpn_challenge_server: Any | None = None,
    ):
        """Initialize ACME manager.

        Args:
            challenge_server: Optional HTTP challenge server instance.
                             Required for HTTP-01 challenges.
            acme_config: ACME configuration dictionary
            cert_reload_callback: Optional callback for certificate updates
                                 Called with (cert_file, key_file) when certs change
            tls_alpn_challenge_server: Optional TLS-ALPN challenge server.
                                      Required for TLS-ALPN-01 challenges.
        """
        self.challenge_server = challenge_server
        self.tls_alpn_challenge_server = tls_alpn_challenge_server
        self.acme_config = acme_config
        self.cert_reload_callback = cert_reload_callback

        # Validate configuration
        challenge_config = acme_config.get("challenge", {})
        challenge_type = challenge_config.get("type", "tls-alpn-01")
        if challenge_type == "http-01" and challenge_server is None:
            raise ValueError("HTTP challenge server is required for HTTP-01 challenges")
        if challenge_type == "tls-alpn-01" and tls_alpn_challenge_server is None:
            raise ValueError(
                "TLS-ALPN challenge server is required for TLS-ALPN-01 challenges"
            )

        # Certificate state
        self.cert_file: str | None = None
        self.key_file: str | None = None
        self.last_cert_check = 0.0

        # Manager state
        self._running = False
        self._renewal_task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

        # Configuration
        self.renewal_check_interval = 3600  # Check every hour
        self.renewal_threshold_days = 30  # Renew 30 days before expiry

    async def start(self) -> Result:
        """Start the ACME manager.

        Returns:
            Result indicating success or failure
        """
        if self._running:
            logger.warning("ACME manager is already running")
            return Success(message="ACME manager already running")

        try:
            logger.info("Starting ACME certificate manager")

            self._running = True
            self._stop_event.clear()

            # Start background renewal monitoring
            self._renewal_task = asyncio.create_task(self._renewal_monitor())

            # Perform initial certificate provisioning
            initial_result = await self._provision_initial_certificates()
            if isinstance(initial_result, Error):
                # Continue running even if initial provisioning fails
                # The server needs to stay up to handle challenge requests
                # and retry later
                challenge_config = self.acme_config.get("challenge", {})
                challenge_type = challenge_config.get("type", "tls-alpn-01")
                logger.warning(
                    f"Initial certificate provisioning failed for {challenge_type}: "
                    f"{initial_result.error}"
                )
                logger.info(
                    "Continuing server operation - certificate provisioning will "
                    "be retried during renewal check"
                )

            logger.info("ACME manager started successfully")
            return Success(message="ACME manager started")

        except Exception as e:
            await self.stop()
            return Error(error=f"Failed to start ACME manager: {e}", exception=e)

    async def stop(self) -> None:
        """Stop the ACME manager."""
        if not self._running:
            return

        logger.info("Stopping ACME manager...")

        self._running = False
        self._stop_event.set()

        # Cancel renewal task
        if self._renewal_task and not self._renewal_task.done():
            self._renewal_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._renewal_task

        logger.info("ACME manager stopped")

    async def _provision_initial_certificates(self) -> Result:
        """Provision initial certificates."""
        try:
            logger.info("Provisioning initial ACME certificates")

            # Ensure certificate directory exists
            cert_dir = self._get_cert_directory()
            cert_dir.mkdir(parents=True, exist_ok=True)

            # Determine certificate file paths
            primary_domain = self.acme_config["domains"][0]
            cert_file = str(cert_dir / f"{primary_domain}.crt")
            key_file = str(cert_dir / f"{primary_domain}.key")

            # Check if certificates need renewal
            acme_client = self._create_acme_client()
            if acme_client.needs_renewal(
                cert_file, days_before_expiry=self.renewal_threshold_days
            ):
                logger.info("Certificates need provisioning or renewal")

                # Wait for HTTP-01 readiness
                await self._wait_for_http01_readiness()

                # Provision new certificates
                provision_result = await self._provision_certificates_async(
                    acme_client, cert_file, key_file
                )
                if isinstance(provision_result, Error):
                    return provision_result

            else:
                logger.info("Existing certificates are still valid")

            # Update certificate state
            self.cert_file = cert_file
            self.key_file = key_file
            self.last_cert_check = time.time()

            # Notify callback about new certificates
            if self.cert_reload_callback:
                try:
                    self.cert_reload_callback(cert_file, key_file)
                    logger.info("Certificate reload callback executed successfully")
                except Exception as e:
                    logger.error(f"Certificate reload callback failed: {e}")
                    # Don't fail the whole operation for callback errors

            return Success(
                message="Initial certificate provisioning completed",
                data=(cert_file, key_file),
            )

        except Exception as e:
            return Error(
                error=f"Initial certificate provisioning failed: {e}", exception=e
            )

    async def _provision_certificates_async(
        self,
        acme_client: Any,
        cert_file: str,
        key_file: str,
    ) -> Result:
        """Provision certificates asynchronously."""
        try:
            logger.debug(
                "Starting async certificate provisioning for domains: "
                f"{self.acme_config['domains']}"
            )

            challenge_config = self.acme_config.get("challenge", {})
            challenge_type = challenge_config.get("type", "tls-alpn-01")

            # Only monkey-patch for HTTP-01 challenges
            if challenge_type == "http-01":
                # Temporarily monkey-patch the ACME client for our challenge server
                original_complete_http01 = acme_client._complete_http01_challenge
                acme_client._complete_http01_challenge = (
                    lambda cb, domain, challenge_dir: self._handle_http01_challenge(
                        cb, domain, challenge_dir, original_complete_http01, acme_client
                    )
                )

                try:
                    # Request certificate with patched challenge handling
                    (
                        cert_bytes,
                        key_bytes,
                    ) = await asyncio.get_event_loop().run_in_executor(
                        None,
                        acme_client.request_certificate,
                        self.acme_config["domains"],
                        challenge_type,
                        cert_file,
                        key_file,
                        None,  # challenge_dir - we handle this differently
                    )
                finally:
                    # Restore original method
                    acme_client._complete_http01_challenge = original_complete_http01
            else:
                # For non-HTTP-01 challenges, use ACME client directly
                cert_bytes, key_bytes = await asyncio.get_event_loop().run_in_executor(
                    None,
                    acme_client.request_certificate,
                    self.acme_config["domains"],
                    challenge_type,
                    cert_file,
                    key_file,
                )

            logger.info("ACME certificate provisioning completed successfully")
            return Success(message="Certificate provisioned successfully")

        except Exception as e:
            logger.error(f"Certificate provisioning failed: {e}")
            logger.debug(
                f"Certificate provisioning error details: {type(e).__name__}: {e}"
            )
            return Error(error=f"Certificate provisioning failed: {e}", exception=e)

    def _handle_http01_challenge(
        self,
        challenge_body: Any,
        domain: str,
        challenge_dir: str | None,
        original_method: Callable,
        acme_client: Any,
    ) -> None:
        """Handle HTTP-01 challenge using our challenge server."""
        if self.challenge_server is None:
            raise RuntimeError(
                "HTTP challenge server is required for HTTP-01 challenges"
            )

        # Extract challenge details
        challenge = challenge_body.chall

        # Get account key from the EXISTING client (don't create a new one!)
        account_key = acme_client._account_key

        # Generate challenge response
        response, validation = challenge.response_and_validation(account_key)

        # Get token
        token_str = challenge.encode("token")

        logger.info(
            f"Created HTTP-01 challenge file: .well-known/acme-challenge/{token_str}"
        )
        logger.info(
            "Challenge must be accessible at: "
            f"http://{domain}/.well-known/acme-challenge/{token_str}"
        )

        # Set challenge in our HTTP server
        self.challenge_server.set_challenge(token_str, validation)

        try:
            # Submit challenge response using the SAME client
            acme_client._client.answer_challenge(challenge_body, response)
        except Exception as e:
            logger.error(f"Error submitting challenge response: {e}")
            # FIXED: Only clean up on submission error, not always in finally block
            # This allows ACME server to validate the challenge token
            self.challenge_server.remove_challenge(token_str)
            logger.info(
                "Cleaned up challenge file after error: "
                f".well-known/acme-challenge/{token_str}"
            )
            raise

        # The challenge will be cleaned up later by the ACME client after
        # validation completes

    async def _renewal_monitor(self) -> None:
        """Background task to monitor certificate renewal needs."""
        logger.info("Starting certificate renewal monitor")

        while self._running:
            try:
                # Wait for check interval or stop signal
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(), timeout=self.renewal_check_interval
                    )
                    # Stop event was set
                    break
                except TimeoutError:
                    # Timeout reached, perform renewal check
                    pass

                if not self._running:
                    break

                # Check if certificates need renewal
                await self._check_and_renew_certificates()

            except asyncio.CancelledError:
                logger.info("Renewal monitor cancelled")
                break
            except Exception as e:
                logger.error(f"Error in renewal monitor: {e}")
                # Continue monitoring despite errors
                await asyncio.sleep(60)  # Wait a bit before retrying

        logger.info("Certificate renewal monitor stopped")

    async def _check_and_renew_certificates(self) -> None:
        """Check and renew certificates if needed."""
        if not self.cert_file or not self.key_file:
            logger.warning("No certificate files configured for renewal check")
            return

        try:
            logger.debug("Checking certificate renewal status")

            acme_client = self._create_acme_client()
            needs_renewal = acme_client.needs_renewal(
                self.cert_file, days_before_expiry=self.renewal_threshold_days
            )

            if needs_renewal:
                logger.info("Certificates need renewal - starting renewal process")

                renewal_result = await self._provision_certificates_async(
                    acme_client, self.cert_file, self.key_file
                )

                if isinstance(renewal_result, Success):
                    logger.info("Certificate renewal completed successfully")

                    # Notify callback about renewed certificates
                    if self.cert_reload_callback:
                        try:
                            self.cert_reload_callback(self.cert_file, self.key_file)
                            logger.info(
                                "Certificate reload callback executed after renewal"
                            )
                        except Exception as e:
                            logger.error(
                                f"Certificate reload callback failed after renewal: {e}"
                            )
                else:
                    logger.error(f"Certificate renewal failed: {renewal_result.error}")
            else:
                logger.debug("Certificates are still valid, no renewal needed")

            self.last_cert_check = time.time()

        except Exception as e:
            logger.error(f"Error during certificate renewal check: {e}")

    def _create_acme_client(self) -> Any:
        """Create ACME client with current configuration."""
        from .acme_client import LETSENCRYPT_PRODUCTION

        # Determine if we need to pass a TLS-ALPN challenge server
        challenge_config = self.acme_config.get("challenge", {})
        challenge_type = challenge_config.get("type", "tls-alpn-01")
        tls_alpn_server = (
            self.tls_alpn_challenge_server if challenge_type == "tls-alpn-01" else None
        )

        return create_acme_client(
            directory_url=self.acme_config.get("directory_url", LETSENCRYPT_PRODUCTION),
            email=self.acme_config["email"],
            ca_cert_file=self.acme_config.get("ca_cert_file"),
            tls_alpn_challenge_server=tls_alpn_server,
        )

    def _get_cert_directory(self) -> Path:
        """Get the certificate storage directory."""
        return Path.home() / ".config" / "vibectl" / "server" / "acme-certs"

    @property
    def is_running(self) -> bool:
        """Check if the ACME manager is running."""
        return self._running

    def get_certificate_files(self) -> tuple[str | None, str | None]:
        """Get current certificate file paths.

        Returns:
            Tuple of (cert_file, key_file), both may be None if not available
        """
        return self.cert_file, self.key_file

    async def _wait_for_http01_readiness(self, timeout: float = 30.0) -> None:
        """Wait until the in-cluster Service that fronts the HTTP-01 challenge
        server is routable.

        The ACME CA (Pebble, Let's Encrypt, …) connects to the service on
        port 80. Right after the pod starts it can take a few seconds until the
        pod is marked *Ready* and added to the Endpoint list. If we try to
        complete the challenge before that happens the CA will receive
        connection-refused errors and invalidate the order.  By waiting here we
        make sure the Service is ready before we kick off the ACME flow.
        """

        # Only relevant for HTTP-01 and when we actually have a running
        # in-process challenge server (i.e. in production).  Unit tests often
        # construct an ACMEManager with ``challenge_server`` mocked out or set
        # to ``None``; in that scenario we skip the readiness wait entirely so
        # tests run instantly.

        challenge_config = self.acme_config.get("challenge", {})
        challenge_type = challenge_config.get("type", "tls-alpn-01")
        if challenge_type != "http-01" or not isinstance(
            self.challenge_server, HTTPChallengeServer
        ):
            return

        host = self.acme_config["domains"][0]
        port = int(self.acme_config.get("http_port", 80))

        logger.debug(
            "Waiting for HTTP-01 challenge service to accept connections at "
            f"{host}:{port}"
        )

        start = asyncio.get_event_loop().time()
        while (asyncio.get_event_loop().time() - start) < timeout:
            try:
                reader, writer = await asyncio.open_connection(host, port)
                writer.close()
                with contextlib.suppress(AttributeError):
                    # For Python < 3.7 compatibility - ignore
                    await writer.wait_closed()
                logger.debug("HTTP-01 challenge service is reachable")
                return
            except Exception as e:
                # Most likely connection-refused or DNS still propagating
                logger.debug(f"HTTP-01 readiness probe failed: {e}")
                await asyncio.sleep(1)

        logger.warning(
            "Timed out waiting for HTTP-01 service to become reachable; "
            "proceeding with ACME anyway."
        )


class ACMEChallengeResponder:
    """Challenge responder that integrates with HTTPChallengeServer."""

    def __init__(self, challenge_server: HTTPChallengeServer):
        """Initialize with challenge server instance."""
        self.challenge_server = challenge_server

    def create_challenge_file(self, token: str, content: str) -> None:
        """Create a challenge response (called by ACME client).

        Args:
            token: Challenge token
            content: Challenge response content
        """
        logger.info(
            f"Created HTTP-01 challenge file: .well-known/acme-challenge/{token}"
        )
        logger.info(
            f"Challenge must be accessible at: http://*/..well-known/acme-challenge/{token}"
        )

        # Set challenge in the HTTP server
        self.challenge_server.set_challenge(token, content)

    def cleanup_challenge_file(self, token: str) -> None:
        """Clean up a challenge response (called by ACME client).

        Args:
            token: Challenge token to remove
        """
        logger.info(f"Cleaned up challenge file: .well-known/acme-challenge/{token}")

        # Remove challenge from the HTTP server
        self.challenge_server.remove_challenge(token)
