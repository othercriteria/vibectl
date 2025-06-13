"""
Comprehensive tests for ACME TLS-ALPN-01 flow beyond initial setup.

This module tests the complete ACME certificate provisioning flow for TLS-ALPN-01
challenges, particularly the parts where the demo appears to hang - the actual
certificate request, challenge validation, and certificate retrieval.
"""

import asyncio
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest

from vibectl.server.acme_client import (
    ACMEClient,
    ACMEValidationError,
)
from vibectl.types import Success


class TestComprehensiveACMETLSALPN01Flow:
    """Test the complete TLS-ALPN-01 ACME flow beyond initial setup."""

    @patch("vibectl.server.acme_client.time.sleep")  # Mock sleep to prevent hanging
    @patch("vibectl.server.acme_client.client.ClientV2")
    @patch("vibectl.server.acme_client.jose.JWKRSA")
    @patch("vibectl.server.acme_client.rsa.generate_private_key")
    @patch("vibectl.server.acme_client.messages")
    @patch("vibectl.server.acme_client.create_certificate_signing_request")
    @patch("vibectl.server.acme_client.Path.mkdir")
    @patch("vibectl.server.acme_client.Path.write_bytes")
    @pytest.mark.asyncio
    async def test_complete_tls_alpn01_certificate_request_flow(
        self,
        mock_write_bytes: Mock,
        mock_mkdir: Mock,
        mock_create_csr: Mock,
        mock_messages: Mock,
        mock_rsa_gen: Mock,
        mock_jwk_class: Mock,
        mock_client_class: Mock,
        mock_sleep: Mock,
    ) -> None:
        """Test complete TLS-ALPN-01 certificate request from start to finish."""
        # Setup mocks for the entire ACME flow
        mock_tls_alpn_server = Mock()
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        # Mock account key
        mock_account_key = Mock()
        mock_jwk_class.return_value = mock_account_key

        # Mock private key generation
        mock_private_key = Mock()
        mock_private_key.private_bytes.return_value = (
            b"-----BEGIN PRIVATE KEY-----\ntest_key\n-----END PRIVATE KEY-----"
        )
        mock_rsa_gen.return_value = mock_private_key

        # Mock CSR creation
        mock_csr = Mock()
        mock_csr.csr.public_bytes.return_value = (
            b"-----BEGIN CERTIFICATE REQUEST-----\n"
            b"test_csr\n"
            b"-----END CERTIFICATE REQUEST-----"
        )
        mock_create_csr.return_value = mock_csr

        # Mock directory and account registration
        mock_client.directory = Mock()
        mock_client.directory.new_account = "https://acme.test/new-acct"
        mock_client.new_account = Mock()

        # Mock authorization with TLS-ALPN-01 challenge
        mock_authz = Mock()
        mock_authz.body.identifier.value = "vibectl.test"
        mock_authz.body.status = "pending"

        # Create mock TLS-ALPN-01 challenge - fix the call signature
        mock_tls_alpn_challenge = Mock()
        mock_tls_alpn_challenge.typ = "tls-alpn-01"

        # The actual implementation calls response_and_validation with domain parameter
        def mock_response_and_validation(
            account_key: Any, domain: str | None = None
        ) -> tuple[Mock, bytes]:
            return Mock(), b"challenge_validation_token_12345"

        mock_tls_alpn_challenge.response_and_validation = mock_response_and_validation

        mock_challenge_body = Mock()
        mock_challenge_body.chall = mock_tls_alpn_challenge

        mock_authz.body.challenges = [mock_challenge_body]

        # Mock order creation - authorizations should contain actual
        # authorization objects, not URLs
        mock_order = Mock()
        mock_order.body.identifiers = [Mock(value="vibectl.test")]
        mock_order.authorizations = [
            mock_authz
        ]  # Should contain authorization objects directly
        mock_client.new_order.return_value = mock_order

        # Mock challenge submission and polling
        mock_client.answer_challenge = Mock()

        # Mock authorization polling - first pending, then valid
        mock_authz_pending = Mock()
        mock_authz_pending.body.status = "pending"
        mock_authz_valid = Mock()
        mock_authz_valid.body.status = "valid"
        mock_authz_valid.body.identifier.value = "vibectl.test"

        # First poll returns pending, second returns valid
        mock_client.poll.side_effect = [
            (mock_authz_pending, Mock()),
            (mock_authz_valid, Mock()),
        ]

        # Mock order finalization - returns order with certificate data
        mock_finalized_order = Mock()
        mock_finalized_order.fullchain_pem = (
            "-----BEGIN CERTIFICATE-----\ntest_cert_data\n-----END CERTIFICATE-----"
        )
        mock_client.finalize_order.return_value = mock_finalized_order

        # Mock messages module
        mock_messages.STATUS_VALID = "valid"
        mock_messages.STATUS_INVALID = "invalid"
        mock_messages.STATUS_PENDING = "pending"
        mock_messages.CertificateRequest = Mock()

        # Create ACME client
        client = ACMEClient(
            directory_url="https://pebble.test:14000/dir",
            email="admin@vibectl.test",
            ca_cert_file="/pebble-ca/ca.crt",
            tls_alpn_challenge_server=mock_tls_alpn_server,
        )

        # Mock _ensure_client to set up internal state
        client._client = mock_client
        client._account_key = mock_account_key

        # Create temporary files for certificate storage
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = f"{temp_dir}/vibectl.test.crt"
            key_file = f"{temp_dir}/vibectl.test.key"

            # Request certificate - this is where the demo hangs
            cert_bytes, key_bytes = client.request_certificate(
                domains=["vibectl.test"],
                challenge_type="tls-alpn-01",
                cert_file=cert_file,
                key_file=key_file,
            )

        # Verify the complete flow was executed
        mock_client.new_order.assert_called_once()
        # Verify challenge server was configured with challenge hash (bytes)
        mock_tls_alpn_server.set_challenge.assert_called_once()
        # The second argument should be the SHA256 hash of the key authorization
        call_args = mock_tls_alpn_server.set_challenge.call_args[0]
        assert call_args[0] == "vibectl.test"
        assert isinstance(call_args[1], bytes)  # Should be challenge hash
        mock_client.answer_challenge.assert_called_once()
        assert mock_client.poll.call_count == 2  # Pending then valid
        mock_tls_alpn_server.remove_challenge.assert_called_once_with("vibectl.test")
        mock_client.finalize_order.assert_called_once()

        # Verify certificate files were mocked to be written
        # Path.write_bytes is mocked, so files won't actually exist
        # Check that write_bytes was called to write the certificate and key
        assert mock_write_bytes.call_count == 2  # Called for cert and key
        assert (
            cert_bytes
            == b"-----BEGIN CERTIFICATE-----\ntest_cert_data\n-----END CERTIFICATE-----"
        )
        assert key_bytes is not None

    @patch(
        "vibectl.server.acme_client.time"
    )  # Mock entire time module including sleep and time()
    @patch("vibectl.server.acme_client.client.ClientV2")
    @patch("vibectl.server.acme_client.jose.JWKRSA")
    @patch("vibectl.server.acme_client.messages")
    def test_tls_alpn01_challenge_validation_timeout(
        self,
        mock_messages: Mock,
        mock_jwk_class: Mock,
        mock_client_class: Mock,
        mock_time: Mock,
    ) -> None:
        """Test TLS-ALPN-01 challenge when validation times out."""
        # Setup time mocks to prevent real sleep calls - enough for timeout paths
        mock_time.time.side_effect = [
            0,
            1.5,
            1.5,
            1.5,
            1.5,
        ]  # Start, timeout, pending, timeout, cleanup
        mock_time.sleep = Mock()

        # Setup mocks
        mock_tls_alpn_server = Mock()
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        mock_account_key = Mock()
        mock_jwk_class.return_value = mock_account_key

        # Mock challenge setup - fix the call signature
        mock_tls_alpn_challenge = Mock()
        mock_tls_alpn_challenge.typ = "tls-alpn-01"

        def mock_response_and_validation(
            account_key: Any, domain: str | None = None
        ) -> tuple[Mock, bytes]:
            return Mock(), b"validation_token"

        mock_tls_alpn_challenge.response_and_validation = mock_response_and_validation

        mock_challenge_body = Mock()
        mock_challenge_body.chall = mock_tls_alpn_challenge

        mock_authz = Mock()
        mock_authz.body.identifier.value = "vibectl.test"
        mock_authz.body.challenges = [mock_challenge_body]

        # Mock authorization that never becomes valid (timeout scenario)
        mock_authz_pending = Mock()
        mock_authz_pending.body.status = "pending"
        mock_client.poll.return_value = (mock_authz_pending, Mock())

        mock_messages.STATUS_VALID = "valid"
        mock_messages.STATUS_INVALID = "invalid"
        mock_messages.STATUS_PENDING = "pending"

        client = ACMEClient(tls_alpn_challenge_server=mock_tls_alpn_server)
        client._client = mock_client
        client._account_key = mock_account_key

        # Test just the TLS-ALPN challenge setup and then the timeout separately
        # First test the challenge setup
        client._complete_tls_alpn01_challenge(mock_challenge_body, "vibectl.test")

        # Verify challenge was set up properly - check for challenge hash
        # instead of raw token
        mock_tls_alpn_server.set_challenge.assert_called_once()
        call_args = mock_tls_alpn_server.set_challenge.call_args[0]
        assert call_args[0] == "vibectl.test"
        assert isinstance(call_args[1], bytes)  # Should be challenge hash

        # Test the validation timeout scenario separately
        with pytest.raises(
            ACMEValidationError,
            match="Authorization validation timed out after 1 seconds",
        ):
            # Use a very short timeout (1 second) so test doesn't hang
            client._wait_for_authorization_validation(mock_authz, timeout=1)

        # With the new enhanced validation logic, cleanup IS called on timeout
        mock_tls_alpn_server.remove_challenge.assert_called_once_with("vibectl.test")

    @patch(
        "vibectl.server.acme_client.time"
    )  # Mock entire time module including sleep and time()
    @patch("vibectl.server.acme_client.client.ClientV2")
    @patch("vibectl.server.acme_client.jose.JWKRSA")
    @patch("vibectl.server.acme_client.messages")
    def test_tls_alpn01_challenge_validation_failure(
        self,
        mock_messages: Mock,
        mock_jwk_class: Mock,
        mock_client_class: Mock,
        mock_time: Mock,
    ) -> None:
        """Test TLS-ALPN-01 challenge when validation fails."""
        # Setup time mocks to prevent real sleep calls - enough for 8 retry attempts
        mock_time.time.side_effect = [
            0,  # Start time
            1,
            2,  # First attempt (elapsed, retry)
            3,
            4,  # Second attempt
            5,
            6,  # Third attempt
            7,
            8,  # Fourth attempt
            9,
            10,  # Fifth attempt
            11,
            12,  # Sixth attempt
            13,
            14,  # Seventh attempt
            15,
            16,  # Eighth attempt (final)
            17,  # After max retries reached
        ]
        mock_time.sleep = Mock()

        # Setup mocks
        mock_tls_alpn_server = Mock()
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        mock_account_key = Mock()
        mock_jwk_class.return_value = mock_account_key

        # Mock challenge setup - fix the call signature
        mock_tls_alpn_challenge = Mock()
        mock_tls_alpn_challenge.typ = "tls-alpn-01"

        def mock_response_and_validation(
            account_key: Any, domain: str | None = None
        ) -> tuple[Mock, bytes]:
            return Mock(), b"validation_token"

        mock_tls_alpn_challenge.response_and_validation = mock_response_and_validation

        mock_challenge_body = Mock()
        mock_challenge_body.chall = mock_tls_alpn_challenge

        mock_authz = Mock()
        mock_authz.body.identifier.value = "vibectl.test"
        mock_authz.body.challenges = [mock_challenge_body]

        # Mock authorization that becomes invalid
        mock_authz_invalid = Mock()
        mock_authz_invalid.body.status = "invalid"
        mock_authz_invalid.body.identifier.value = "vibectl.test"
        mock_authz_invalid.body.challenges = [
            Mock(error=Mock(detail="Connection failed"))
        ]
        mock_client.poll.return_value = (mock_authz_invalid, Mock())

        mock_messages.STATUS_VALID = "valid"
        mock_messages.STATUS_INVALID = "invalid"
        mock_messages.STATUS_PENDING = "pending"

        client = ACMEClient(tls_alpn_challenge_server=mock_tls_alpn_server)
        client._client = mock_client
        client._account_key = mock_account_key

        # Complete TLS-ALPN challenge setup
        client._complete_tls_alpn01_challenge(mock_challenge_body, "vibectl.test")

        # Test validation failure - with new retry tolerance, this will try 8 times
        with pytest.raises(
            ACMEValidationError,
        ) as excinfo:
            client._wait_for_authorization_validation(mock_authz)
        # Check error message content
        msg = str(excinfo.value)
        assert "Authorization validation failed" in msg
        assert "Connection failed" in msg

        # Verify challenge cleanup was called
        mock_tls_alpn_server.remove_challenge.assert_called_once_with("vibectl.test")

    @patch("vibectl.server.acme_client.client.ClientV2")
    @patch("vibectl.server.acme_client.jose.JWKRSA")
    def test_tls_alpn01_challenge_server_unreachable(
        self, mock_jwk_class: Mock, mock_client_class: Mock
    ) -> None:
        """Test TLS-ALPN-01 challenge when challenge server is unreachable."""
        # Setup mocks
        mock_tls_alpn_server = Mock()
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        mock_account_key = Mock()
        mock_jwk_class.return_value = mock_account_key

        # Mock challenge setup - fix the call signature
        mock_tls_alpn_challenge = Mock()
        mock_tls_alpn_challenge.typ = "tls-alpn-01"

        def mock_response_and_validation(
            account_key: Any, domain: str | None = None
        ) -> tuple[Mock, bytes]:
            return Mock(), b"validation_token"

        mock_tls_alpn_challenge.response_and_validation = mock_response_and_validation

        mock_challenge_body = Mock()
        mock_challenge_body.chall = mock_tls_alpn_challenge

        # Mock answer_challenge to fail (simulating unreachable server)
        mock_client.answer_challenge.side_effect = Exception("Connection refused")

        client = ACMEClient(tls_alpn_challenge_server=mock_tls_alpn_server)
        client._client = mock_client
        client._account_key = mock_account_key

        # Should raise validation error
        with pytest.raises(
            ACMEValidationError, match="Failed to submit challenge response"
        ):
            client._complete_tls_alpn01_challenge(mock_challenge_body, "vibectl.test")

        # Verify challenge was set up and then cleaned up on error
        mock_tls_alpn_server.set_challenge.assert_called_once()
        call_args = mock_tls_alpn_server.set_challenge.call_args[0]
        assert call_args[0] == "vibectl.test"
        assert isinstance(call_args[1], bytes)  # Should be challenge hash
        mock_tls_alpn_server.remove_challenge.assert_called_once_with("vibectl.test")

    @patch(
        "vibectl.server.acme_manager.create_acme_client"
    )  # Mock at ACMEManager level
    @pytest.mark.asyncio
    async def test_tls_alpn_acme_manager_complete_flow(
        self, mock_create_client: Mock
    ) -> None:
        """Test the complete TLS-ALPN ACME manager provisioning flow."""
        from vibectl.server.acme_manager import ACMEManager

        # Mock TLS-ALPN server
        mock_tls_alpn_server = Mock()

        # Mock certificate reload callback
        mock_cert_reload = Mock()

        acme_config = {
            "email": "admin@vibectl.test",
            "domains": ["vibectl.test"],
            "directory_url": "https://pebble.test:14000/dir",
            "ca_cert_file": "/pebble-ca/ca.crt",
            "challenge_type": "tls-alpn-01",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create initial bootstrap certificates (like the demo does)
            cert_path = Path(str(temp_dir)) / "server.crt"
            key_path = Path(str(temp_dir)) / "server.key"
            cert_path.parent.mkdir(parents=True, exist_ok=True)

            cert_path.write_text(
                "-----BEGIN CERTIFICATE-----\nbootstrap\n-----END CERTIFICATE-----"
            )
            key_path.write_text(
                "-----BEGIN PRIVATE KEY-----\nbootstrap\n-----END PRIVATE KEY-----"
            )

            # Mock ACME client
            mock_acme_client = Mock()
            mock_create_client.return_value = mock_acme_client

            # Mock successful certificate request
            mock_acme_client.request_certificate.return_value = (
                b"-----BEGIN CERTIFICATE-----\nreal_cert\n-----END CERTIFICATE-----",
                b"-----BEGIN PRIVATE KEY-----\nreal_key\n-----END PRIVATE KEY-----",
            )

            # Create the ACME manager with TLS-ALPN challenge server
            acme_manager = ACMEManager(
                challenge_server=None,  # No HTTP challenge server for TLS-ALPN-01
                acme_config=acme_config,
                cert_reload_callback=mock_cert_reload,
                tls_alpn_challenge_server=mock_tls_alpn_server,
            )

            # Start the manager (this should trigger certificate provisioning)
            start_result = await acme_manager.start()
            assert isinstance(start_result, Success)

            # Allow time for the background task to run
            await asyncio.sleep(0.2)

            # Verify the exact call that would provision certificates
            mock_create_client.assert_called_once_with(
                directory_url="https://pebble.test:14000/dir",
                email="admin@vibectl.test",
                ca_cert_file="/pebble-ca/ca.crt",
                tls_alpn_challenge_server=mock_tls_alpn_server,
            )

            # The ACMEManager uses its own configured cert paths and positional
            # arguments
            mock_acme_client.request_certificate.assert_called_once_with(
                ["vibectl.test"],  # domains (positional)
                "tls-alpn-01",  # challenge_type (positional)
                str(
                    Path.home()
                    / ".config"
                    / "vibectl"
                    / "server"
                    / "acme-certs"
                    / "vibectl.test.crt"
                ),
                str(
                    Path.home()
                    / ".config"
                    / "vibectl"
                    / "server"
                    / "acme-certs"
                    / "vibectl.test.key"
                ),
            )

            # Clean up
            await acme_manager.stop()

    @patch(
        "vibectl.server.acme_manager.create_acme_client"
    )  # Mock at ACMEManager level
    @pytest.mark.asyncio
    async def test_tls_alpn_acme_manager_certificate_request_failure(
        self, mock_create_client: Mock
    ) -> None:
        """Test TLS-ALPN ACME manager when certificate request fails."""
        from vibectl.server.acme_manager import ACMEManager

        # Mock TLS-ALPN server
        mock_tls_alpn_server = Mock()

        # Mock certificate reload callback
        mock_cert_reload = Mock()

        acme_config = {
            "email": "admin@vibectl.test",
            "domains": ["vibectl.test"],
            "directory_url": "https://pebble.test:14000/dir",
            "challenge_type": "tls-alpn-01",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create initial bootstrap certificates
            cert_path = Path(str(temp_dir)) / "server.crt"
            key_path = Path(str(temp_dir)) / "server.key"
            cert_path.parent.mkdir(parents=True, exist_ok=True)

            cert_path.write_text(
                "-----BEGIN CERTIFICATE-----\nbootstrap\n-----END CERTIFICATE-----"
            )
            key_path.write_text(
                "-----BEGIN PRIVATE KEY-----\nbootstrap\n-----END PRIVATE KEY-----"
            )

            # Mock ACME client to fail - patch at the ACMEManager import level
            mock_acme_client = Mock()
            mock_create_client.return_value = mock_acme_client

            # Mock failed certificate request (like what happens in the hanging demo)
            def hanging_request_certificate(*args: Any, **kwargs: Any) -> None:
                # Simulate hanging by sleeping (in real test, we'll mock this)
                raise Exception(
                    "Connection timeout during TLS-ALPN-01 challenge validation"
                )

            mock_acme_client.request_certificate.side_effect = (
                hanging_request_certificate
            )

            # Create the ACME manager with TLS-ALPN challenge server
            acme_manager = ACMEManager(
                challenge_server=None,  # No HTTP challenge server for TLS-ALPN-01
                acme_config=acme_config,
                cert_reload_callback=mock_cert_reload,
                tls_alpn_challenge_server=mock_tls_alpn_server,
            )

            # Start the manager
            start_result = await acme_manager.start()

            # Should return Success when certificate provisioning fails
            # during startup for TLS-ALPN-01 because the server continues
            # operation and retries in background
            assert isinstance(start_result, Success)
            assert "ACME manager started" in start_result.message

            # Manager should be running even though initial provisioning failed
            assert acme_manager.is_running

            # Verify ACME client was created correctly (even though provisioning failed)
            mock_create_client.assert_called_once_with(
                directory_url="https://pebble.test:14000/dir",
                email="admin@vibectl.test",
                ca_cert_file=None,  # No ca_cert_file in this test
                tls_alpn_challenge_server=mock_tls_alpn_server,
            )

            # Verify certificate request was attempted - using ACMEManager's
            # own paths and positional args
            mock_acme_client.request_certificate.assert_called_once_with(
                ["vibectl.test"],  # domains (positional)
                "tls-alpn-01",  # challenge_type (positional)
                str(
                    Path.home()
                    / ".config"
                    / "vibectl"
                    / "server"
                    / "acme-certs"
                    / "vibectl.test.crt"
                ),
                str(
                    Path.home()
                    / ".config"
                    / "vibectl"
                    / "server"
                    / "acme-certs"
                    / "vibectl.test.key"
                ),
            )

            # Clean up
            await acme_manager.stop()

    @patch("vibectl.server.acme_client.time.sleep")  # Mock sleep to prevent hanging
    @patch(
        "vibectl.server.acme_client.ACMEClient._ensure_client"
    )  # Mock client initialization
    @patch(
        "vibectl.server.acme_client.ACMEClient.request_certificate"
    )  # Mock certificate request
    @patch("vibectl.server.acme_client.client.ClientV2")
    @patch("vibectl.server.acme_client.client.ClientNetwork")
    @patch("vibectl.server.acme_client.jose.JWKRSA")
    @patch("vibectl.server.acme_client.messages")
    @pytest.mark.asyncio
    async def test_tls_alpn_acme_manager_pebble_connectivity_issue(
        self,
        mock_messages: Mock,
        mock_jwk_class: Mock,
        mock_network_class: Mock,
        mock_client_class: Mock,
        mock_request_cert: Mock,
        mock_ensure_client: Mock,
        mock_sleep: Mock,
    ) -> None:
        """Test TLS-ALPN ACME manager when Pebble server is unreachable."""
        from vibectl.server.acme_manager import ACMEManager

        # Mock TLS-ALPN server
        mock_tls_alpn_server = Mock()

        # Mock certificate reload callback
        mock_cert_reload = Mock()

        acme_config = {
            "email": "admin@vibectl.test",
            "domains": ["vibectl.test"],
            "directory_url": "https://pebble.test:14000/dir",
            "ca_cert_file": "/pebble-ca/ca.crt",
            "challenge_type": "tls-alpn-01",
        }

        # Mock ACME client methods to prevent network calls
        mock_ensure_client.return_value = None
        mock_request_cert.return_value = (
            b"-----BEGIN CERTIFICATE-----\ntest cert\n-----END CERTIFICATE-----",
            b"-----BEGIN PRIVATE KEY-----\ntest key\n-----END PRIVATE KEY-----",
        )

        # Mock network client to fail early to prevent actual connections
        mock_net = Mock()
        mock_network_class.return_value = mock_net

        # Simulate connection timeout/failure during directory fetch
        from requests.exceptions import ConnectionError

        mock_net.get.side_effect = ConnectionError(
            "HTTPSConnectionPool(host='pebble.test', port=14000): Max retries exceeded"
        )

        # Mock other components
        mock_jwk_class.return_value = Mock()
        mock_messages.STATUS_VALID = "valid"
        mock_messages.STATUS_INVALID = "invalid"
        mock_messages.STATUS_PENDING = "pending"

        # Create the ACME manager
        acme_manager = ACMEManager(
            challenge_server=None,  # No HTTP challenge server needed for TLS-ALPN-01
            acme_config=acme_config,
            cert_reload_callback=mock_cert_reload,
            tls_alpn_challenge_server=mock_tls_alpn_server,
        )

        # Start the manager (this should succeed even with connectivity issues
        # because we mocked the ACME client)
        start_result = await acme_manager.start()

        # Should succeed because ACME client methods are mocked
        assert isinstance(start_result, Success)

        # Allow time for the background task to run
        await asyncio.sleep(0.3)

        # Verify that the ACME client was used (request_certificate was called)
        mock_request_cert.assert_called()

        # Clean up
        await acme_manager.stop()


class TestACMEIntegrationIssues:
    """Test ACME integration issues that could cause demo hanging."""

    @patch("vibectl.server.acme_client.jose.JWKRSA")  # Mock key generation
    @patch("vibectl.server.acme_client.client.ClientV2")
    @patch(
        "vibectl.server.acme_client.client.ClientNetwork"
    )  # Mock network client to prevent actual connections
    @patch(
        "vibectl.server.acme_client.time.sleep"
    )  # Mock sleep to prevent actual timeout
    def test_acme_client_network_timeout_during_directory_fetch(
        self,
        mock_sleep: Mock,
        mock_network_class: Mock,
        mock_client_class: Mock,
        mock_jwk_class: Mock,
    ) -> None:
        """Test ACME client when directory fetch times out."""
        # Mock network client to timeout on get request
        mock_net = Mock()
        mock_network_class.return_value = mock_net
        mock_net.get.side_effect = Exception("Timeout connecting to ACME directory")

        # Mock client initialization to not be called since network fails
        mock_client_class.side_effect = Exception(
            "Should not be called - network failed"
        )

        # Mock key generation to prevent actual key operations
        mock_account_key = Mock()
        mock_jwk_class.return_value = mock_account_key

        client = ACMEClient(
            directory_url="https://10.43.179.11:14000/dir",
            email="admin@vibectl.test",
            ca_cert_file="/pebble-ca/ca.crt",
        )

        # Should raise error during client initialization
        with pytest.raises(Exception, match="Timeout connecting to ACME directory"):
            client._ensure_client()

    @patch("vibectl.server.acme_client.client.ClientV2")
    @patch(
        "vibectl.server.acme_client.client.ClientNetwork"
    )  # Mock network client to prevent actual connections
    @patch("vibectl.server.acme_client.jose.JWKRSA")
    def test_acme_client_ssl_verification_failure(
        self, mock_jwk_class: Mock, mock_network_class: Mock, mock_client_class: Mock
    ) -> None:
        """Test ACME client when SSL verification fails."""
        # Mock network client to fail with SSL error
        mock_net = Mock()
        mock_network_class.return_value = mock_net
        mock_net.get.side_effect = Exception("SSL: CERTIFICATE_VERIFY_FAILED")

        client = ACMEClient(
            directory_url="https://pebble.test:14000/dir",
            email="admin@vibectl.test",
            ca_cert_file="/nonexistent/ca.crt",  # Invalid CA cert path
        )

        # Should raise ACMECertificateError wrapping the SSL error
        with pytest.raises(
            Exception,
            match="Failed to connect to ACME server.*SSL: CERTIFICATE_VERIFY_FAILED",
        ):
            client._ensure_client()

    @patch("vibectl.server.acme_client.client.ClientV2")
    @patch("vibectl.server.acme_client.jose.JWKRSA")
    @patch("vibectl.server.acme_client.messages")
    def test_acme_client_challenge_response_generation_failure(
        self, mock_messages: Mock, mock_jwk_class: Mock, mock_client_class: Mock
    ) -> None:
        """Test when challenge response generation fails."""
        # Setup mocks
        mock_tls_alpn_server = Mock()
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        mock_account_key = Mock()
        mock_jwk_class.return_value = mock_account_key

        # Mock challenge with failing response generation - fix the call signature
        mock_tls_alpn_challenge = Mock()
        mock_tls_alpn_challenge.typ = "tls-alpn-01"

        def mock_response_and_validation(
            account_key: Any, domain: str | None = None
        ) -> None:
            raise Exception("Invalid domain format for TLS-ALPN-01 challenge")

        mock_tls_alpn_challenge.response_and_validation = mock_response_and_validation

        mock_challenge_body = Mock()
        mock_challenge_body.chall = mock_tls_alpn_challenge

        client = ACMEClient(tls_alpn_challenge_server=mock_tls_alpn_server)
        client._client = mock_client
        client._account_key = mock_account_key

        # Should raise the exception directly, not wrapped in ACMEValidationError
        # because the exception happens during response generation, before submission
        with pytest.raises(
            Exception, match="Invalid domain format for TLS-ALPN-01 challenge"
        ):
            client._complete_tls_alpn01_challenge(
                mock_challenge_body, "invalid..domain"
            )

    def test_missing_tls_alpn_challenge_server(self) -> None:
        """Test TLS-ALPN-01 challenge without challenge server."""
        client = ACMEClient(
            directory_url="https://pebble.test:14000/dir",
            email="admin@vibectl.test",
            tls_alpn_challenge_server=None,  # Missing challenge server
        )

        # Set up account key to pass the assertion check
        from unittest.mock import Mock

        mock_account_key = Mock()
        client._account_key = mock_account_key

        mock_challenge_body = Mock()
        mock_challenge_body.chall = Mock(typ="tls-alpn-01")

        # Should raise validation error about missing challenge server
        with pytest.raises(
            ACMEValidationError,
            match="TLS-ALPN-01 challenge requires a TLS-ALPN challenge server instance",
        ):
            client._complete_tls_alpn01_challenge(mock_challenge_body, "vibectl.test")

    @patch(
        "vibectl.server.acme_client.time"
    )  # Mock entire time module to prevent real sleeps
    @patch("vibectl.server.acme_client.client.ClientV2")
    @patch("vibectl.server.acme_client.jose.JWKRSA")
    @patch("vibectl.server.acme_client.messages")
    def test_acme_client_authorization_polling_infinite_pending(
        self,
        mock_messages: Mock,
        mock_jwk_class: Mock,
        mock_client_class: Mock,
        mock_time: Mock,
    ) -> None:
        """Test when authorization polling never resolves (infinite pending)."""
        # Setup time mocks to simulate timeout immediately - enough for timeout paths
        mock_time.time.side_effect = [
            0,
            6,
            6,
            6,
            6,
        ]  # Start, timeout, pending, timeout, cleanup
        mock_time.sleep = Mock()

        # Setup mocks
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        # Mock authorization that stays pending forever
        mock_authz_pending = Mock()
        mock_authz_pending.body.status = "pending"
        mock_authz_pending.body.identifier.value = "test.domain"
        mock_client.poll.return_value = (mock_authz_pending, Mock())

        mock_messages.STATUS_VALID = "valid"
        mock_messages.STATUS_INVALID = "invalid"
        mock_messages.STATUS_PENDING = "pending"

        # Setup TLS-ALPN challenge server mock for cleanup
        mock_tls_alpn_server = Mock()

        client = ACMEClient(tls_alpn_challenge_server=mock_tls_alpn_server)
        client._client = mock_client

        # Should timeout and raise error
        with pytest.raises(
            ACMEValidationError,
            match="Authorization validation timed out after 5 seconds",
        ):
            # Use very short timeout for test
            mock_authz = Mock()
            mock_authz.body.identifier.value = "test.domain"
            client._wait_for_authorization_validation(mock_authz, timeout=5)

        # Verify cleanup was called on timeout
        mock_tls_alpn_server.remove_challenge.assert_called_once_with("test.domain")


class TestACMEDemoDebugging:
    """Tests specifically for debugging the hanging demo scenario."""

    @patch(
        "vibectl.server.acme_client.ACMEClient._ensure_client"
    )  # Mock client initialization
    @patch(
        "vibectl.server.acme_client.ACMEClient.request_certificate"
    )  # Mock certificate request
    @patch("vibectl.server.acme_client.time.sleep")  # Mock sleep to prevent hanging
    @pytest.mark.asyncio
    async def test_demo_hanging_scenario_reproduction(
        self, mock_sleep: Mock, mock_request_cert: Mock, mock_ensure_client: Mock
    ) -> None:
        """Test scenario that could cause demo hanging - with proper mocking."""
        import asyncio

        from vibectl.server.acme_manager import ACMEManager

        # Mock TLS-ALPN server
        mock_tls_alpn_server = Mock()

        # Mock certificate reload callback
        mock_cert_reload = Mock()

        acme_config = {
            "email": "admin@vibectl.test",
            "domains": ["vibectl.test"],
            "directory_url": "https://10.43.179.11:14000/dir",
            "ca_cert_file": "/pebble-ca/ca.crt",
            "challenge_type": "tls-alpn-01",
        }

        # Mock ACME client methods to prevent network calls and hanging
        mock_ensure_client.return_value = None
        mock_request_cert.return_value = (
            b"-----BEGIN CERTIFICATE-----\ntest cert\n-----END CERTIFICATE-----",
            b"-----BEGIN PRIVATE KEY-----\ntest key\n-----END PRIVATE KEY-----",
        )

        # Create the ACME manager
        acme_manager = ACMEManager(
            challenge_server=None,  # No HTTP challenge server needed for TLS-ALPN-01
            acme_config=acme_config,
            cert_reload_callback=mock_cert_reload,
            tls_alpn_challenge_server=mock_tls_alpn_server,
        )

        # Start the manager (should not hang with mocked client)
        start_result = await acme_manager.start()

        # Should succeed because we mocked the ACME client operations
        assert isinstance(start_result, Success)

        # Allow some time for background task to run
        await asyncio.sleep(0.2)

        # Verify that certificate request was called
        mock_request_cert.assert_called()

        # Clean up
        await acme_manager.stop()

    @patch("vibectl.server.acme_client.client.ClientV2")
    @patch(
        "vibectl.server.acme_client.client.ClientNetwork"
    )  # Mock network client to prevent actual connections
    @patch("vibectl.server.acme_client.jose.JWKRSA")
    @patch("vibectl.server.acme_client.messages")
    @patch("vibectl.server.acme_client.time.sleep")  # Mock sleep to prevent hanging
    def test_demo_pebble_connectivity_debugging(
        self,
        mock_sleep: Mock,
        mock_messages: Mock,
        mock_jwk_class: Mock,
        mock_network_class: Mock,
        mock_client_class: Mock,
    ) -> None:
        """Test the specific Pebble connectivity issues from the demo."""
        # Mock network client to simulate Pebble connection issues
        mock_net = Mock()
        mock_network_class.return_value = mock_net
        mock_net.get.side_effect = Exception("Connection refused to Pebble server")

        client = ACMEClient(
            directory_url="https://10.43.179.11:14000/dir",
            email="admin@vibectl.test",
            ca_cert_file="/pebble-ca/ca.crt",
        )

        # Should raise ACMECertificateError wrapping the connection error
        with pytest.raises(
            Exception,
            match=(
                "Failed to connect to ACME server.*Connection refused to Pebble server"
            ),
        ):
            client._ensure_client()

    @patch("vibectl.server.acme_client.client.ClientV2")
    @patch("vibectl.server.acme_client.jose.JWKRSA")
    @patch("vibectl.server.acme_client.messages")
    def test_demo_alpn_multiplexer_integration_issue(
        self, mock_messages: Mock, mock_jwk_class: Mock, mock_client_class: Mock
    ) -> None:
        """Test integration issues between ACME client and ALPN multiplexer."""
        # Setup mocks
        mock_tls_alpn_server = Mock()
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        mock_account_key = Mock()
        mock_jwk_class.return_value = mock_account_key

        # Mock challenge setup - fix the call signature
        mock_tls_alpn_challenge = Mock()
        mock_tls_alpn_challenge.typ = "tls-alpn-01"

        def mock_response_and_validation(
            account_key: Any, domain: str | None = None
        ) -> tuple[Mock, bytes]:
            return Mock(), b"test_validation_token"

        mock_tls_alpn_challenge.response_and_validation = mock_response_and_validation

        mock_challenge_body = Mock()
        mock_challenge_body.chall = mock_tls_alpn_challenge

        client = ACMEClient(tls_alpn_challenge_server=mock_tls_alpn_server)
        client._client = mock_client
        client._account_key = mock_account_key

        # Complete the TLS-ALPN challenge
        client._complete_tls_alpn01_challenge(mock_challenge_body, "vibectl.test")

        # Verify challenge was set up in the multiplexer
        mock_tls_alpn_server.set_challenge.assert_called_once()
        call_args = mock_tls_alpn_server.set_challenge.call_args[0]
        assert call_args[0] == "vibectl.test"
        assert isinstance(call_args[1], bytes)  # Should be challenge hash

        # Verify challenge submission to ACME server
        mock_client.answer_challenge.assert_called_once()
