"""
Tests for ACME client functionality.

This test suite covers the complete ACME protocol implementation including:
- Account registration with ACME server
- Domain authorization and validation (HTTP-01 and DNS-01)
- Certificate signing request (CSR) generation
- Certificate issuance and retrieval
- Certificate renewal automation
- Error handling and edge cases
"""

from datetime import datetime, timedelta
from unittest.mock import Mock, mock_open, patch

import acme.challenges
import acme.client
import acme.errors
import acme.messages
import pytest

from vibectl.server.acme_client import (
    LETSENCRYPT_PRODUCTION,
    LETSENCRYPT_STAGING,
    ACMEClient,
    create_acme_client,
)
from vibectl.types import ACMECertificateError, ACMEValidationError


class TestACMEClient:
    """Test ACME client functionality."""

    def test_init_default_values(self) -> None:
        """Test ACMEClient initialization with default values."""
        client = ACMEClient()

        assert client.directory_url == "https://acme-v02.api.letsencrypt.org/directory"
        assert client.email is None
        assert client.key_size == 2048
        assert client._client is None
        assert client._account_key is None
        assert client._client_net is None

    def test_init_custom_values(self) -> None:
        """Test ACMEClient initialization with custom values."""
        client = ACMEClient(
            directory_url="https://example.com/acme",
            email="test@example.com",
            key_size=4096,
        )

        assert client.directory_url == "https://example.com/acme"
        assert client.email == "test@example.com"
        assert client.key_size == 4096

    @patch("vibectl.server.acme_client.jose.JWKRSA")
    @patch("vibectl.server.acme_client.rsa.generate_private_key")
    @patch("vibectl.server.acme_client.acme.client.ClientNetwork")
    @patch("vibectl.server.acme_client.acme.messages.Directory.from_json")
    @patch("vibectl.server.acme_client.acme.client.ClientV2")
    def test_ensure_client_initialization(
        self,
        mock_client_v2: Mock,
        mock_directory: Mock,
        mock_client_net_class: Mock,
        mock_rsa_gen: Mock,
        mock_jwk_rsa: Mock,
    ) -> None:
        """Test ACME client initialization in _ensure_client."""
        # Setup mocks
        mock_private_key = Mock()
        mock_rsa_gen.return_value = mock_private_key

        mock_account_key = Mock()
        mock_jwk_rsa.return_value = mock_account_key

        mock_client_net = Mock()
        mock_client_net_class.return_value = mock_client_net

        mock_response = Mock()
        mock_response.json.return_value = {"directory": "data"}
        mock_client_net.get.return_value = mock_response

        mock_directory_obj = Mock()
        mock_directory.return_value = mock_directory_obj

        mock_acme_client = Mock()
        mock_client_v2.return_value = mock_acme_client

        # Create client and call _ensure_client
        client = ACMEClient(directory_url="https://test.example.com/directory")
        client._ensure_client()

        # Verify initialization sequence
        mock_rsa_gen.assert_called_once_with(public_exponent=65537, key_size=2048)
        mock_jwk_rsa.assert_called_once_with(key=mock_private_key)
        mock_client_net_class.assert_called_once_with(
            key=mock_account_key, user_agent="vibectl-server/1.0"
        )
        mock_client_net.get.assert_called_once_with(
            "https://test.example.com/directory"
        )
        mock_directory.assert_called_once_with({"directory": "data"})
        mock_client_v2.assert_called_once_with(mock_directory_obj, net=mock_client_net)

        # Verify client state
        assert client._account_key == mock_account_key
        assert client._client_net == mock_client_net
        assert client._client == mock_acme_client

    @patch("vibectl.server.acme_client.ACMEClient._ensure_client")
    @patch("vibectl.server.acme_client.acme.messages.NewRegistration.from_data")
    def test_register_account_success(
        self, mock_new_reg: Mock, mock_ensure_client: Mock
    ) -> None:
        """Test successful account registration."""
        # Setup mocks
        mock_new_account = Mock()
        mock_new_reg.return_value = mock_new_account

        mock_acme_client = Mock()

        client = ACMEClient(email="test@example.com")
        client._client = mock_acme_client

        # Call register_account
        client.register_account()

        # Verify calls
        mock_ensure_client.assert_called_once()
        mock_new_reg.assert_called_once_with(
            email="test@example.com", terms_of_service_agreed=True
        )
        mock_acme_client.new_account.assert_called_once_with(mock_new_account)

    @patch("vibectl.server.acme_client.ACMEClient._ensure_client")
    @patch("vibectl.server.acme_client.acme.messages.NewRegistration.from_data")
    @patch("vibectl.server.acme_client.logger")
    def test_register_account_conflict_error(
        self, mock_logger: Mock, mock_new_reg: Mock, mock_ensure_client: Mock
    ) -> None:
        """Test account registration when account already exists."""
        # Setup mocks
        mock_new_account = Mock()
        mock_new_reg.return_value = mock_new_account

        mock_acme_client = Mock()
        mock_acme_client.new_account.side_effect = acme.errors.ConflictError(
            "Account exists"
        )

        client = ACMEClient(email="test@example.com")
        client._client = mock_acme_client

        # Call register_account
        client.register_account()

        # Verify account already exists message
        mock_logger.info.assert_called_with("ACME account already exists")

    @patch("vibectl.server.acme_client.ACMEClient._ensure_client")
    @patch("vibectl.server.acme_client.ACMEClient.register_account")
    @patch("vibectl.server.acme_client.ACMEClient._complete_authorization")
    @patch("vibectl.server.acme_client.ACMEClient._create_csr")
    @patch("vibectl.server.acme_client.rsa.generate_private_key")
    @patch("vibectl.server.acme_client.acme.messages.NewOrder")
    @patch("vibectl.server.acme_client.Path.mkdir")
    @patch("vibectl.server.acme_client.Path.write_bytes")
    def test_request_certificate_success(
        self,
        mock_write_bytes: Mock,
        mock_mkdir: Mock,
        mock_new_order: Mock,
        mock_rsa_gen: Mock,
        mock_create_csr: Mock,
        mock_complete_auth: Mock,
        mock_register: Mock,
        mock_ensure_client: Mock,
    ) -> None:
        """Test successful certificate request."""
        # Setup mocks
        domains = ["example.com", "www.example.com"]

        # Mock private key
        mock_private_key = Mock()
        mock_private_key.private_bytes.return_value = (
            b"-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----"
        )
        mock_rsa_gen.return_value = mock_private_key

        # Mock order creation
        mock_order_data = Mock()
        mock_new_order.from_data.return_value = mock_order_data

        mock_order = Mock()
        mock_order.uri = "https://acme.example.com/order/123"
        mock_order.authorizations = [Mock(), Mock()]  # Two domains

        mock_acme_client = Mock()
        mock_acme_client.new_order.return_value = mock_order

        # Mock CSR creation
        mock_csr = Mock()
        mock_csr.csr.public_bytes.return_value = b"test_csr_pem"
        mock_create_csr.return_value = mock_csr

        # Mock finalized order
        mock_finalized_order = Mock()
        mock_finalized_order.fullchain_pem = (
            "-----BEGIN CERTIFICATE-----\ntest cert\n-----END CERTIFICATE-----"
        )
        mock_acme_client.finalize_order.return_value = mock_finalized_order

        # Create client
        client = ACMEClient()
        client._client = mock_acme_client

        # Call request_certificate
        cert_bytes, key_bytes = client.request_certificate(
            domains=domains,
            challenge_type="http-01",
            cert_file="/tmp/cert.pem",
            key_file="/tmp/key.pem",
            challenge_dir="/tmp/challenges",
        )

        # Verify return values
        assert (
            cert_bytes
            == b"-----BEGIN CERTIFICATE-----\ntest cert\n-----END CERTIFICATE-----"
        )
        assert (
            key_bytes == b"-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----"
        )

        # Verify calls
        mock_ensure_client.assert_called_once()
        mock_register.assert_called_once()
        mock_rsa_gen.assert_called_once_with(public_exponent=65537, key_size=2048)
        mock_create_csr.assert_called_once_with(domains, mock_private_key)

        # Verify new_order was called with CSR PEM bytes
        mock_acme_client.new_order.assert_called_once_with(b"test_csr_pem")

        # Verify finalize_order was called
        mock_acme_client.finalize_order.assert_called_once()

        # Verify authorizations were completed
        assert mock_complete_auth.call_count == 2

        # Verify file operations
        assert mock_write_bytes.call_count == 2

    def test_request_certificate_validation_error(self) -> None:
        """Test certificate request with validation error."""
        client = ACMEClient()
        client._client = Mock()
        client._account_key = Mock()

        with (
            patch.object(client, "_ensure_client"),
            patch.object(client, "register_account"),
        ):
            client._client = Mock()
            # Create a mock authorization to pass to ValidationError
            mock_authz = Mock(spec=acme.messages.AuthorizationResource)
            client._client.new_order.side_effect = acme.errors.ValidationError(
                [mock_authz]
            )

            with pytest.raises(ACMEValidationError, match="Domain validation failed"):
                client.request_certificate(["example.com"])

    def test_request_certificate_acme_error(self) -> None:
        """Test certificate request with ACME error."""
        client = ACMEClient()
        client._client = Mock()
        client._account_key = Mock()

        with (
            patch.object(client, "_ensure_client"),
            patch.object(client, "register_account"),
            patch.object(client, "_create_csr") as mock_create_csr,
        ):
            mock_csr = Mock()
            mock_csr.csr.public_bytes.return_value = b"mock_csr_bytes"
            mock_create_csr.return_value = mock_csr

            client._client.new_order.side_effect = acme.errors.Error("ACME error")

            with pytest.raises(
                ACMECertificateError, match="ACME certificate request failed"
            ):
                client.request_certificate(["example.com"])

    def test_request_certificate_unexpected_error(self) -> None:
        """Test certificate request with unexpected error."""
        client = ACMEClient()

        with (
            patch.object(client, "_ensure_client"),
            patch.object(client, "register_account"),
            patch(
                "vibectl.server.acme_client.acme.messages.NewOrder"
            ) as mock_new_order,
        ):
            mock_new_order.from_data.side_effect = RuntimeError("Unexpected error")

            with pytest.raises(
                ACMECertificateError,
                match="Unexpected error during certificate request",
            ):
                client.request_certificate(["example.com"])

    def test_complete_authorization_http01(self) -> None:
        """Test completing HTTP-01 authorization."""
        # Mock authorization with HTTP-01 challenge
        mock_authz = Mock()
        mock_authz.body.identifier.value = "example.com"

        mock_http01_challenge = Mock()
        mock_http01_challenge.chall.typ = "http-01"

        mock_other_challenge = Mock()
        mock_other_challenge.chall.typ = "dns-01"

        mock_authz.body.challenges = [mock_other_challenge, mock_http01_challenge]

        client = ACMEClient()

        with (
            patch.object(client, "_complete_http01_challenge") as mock_http01,
            patch.object(client, "_wait_for_authorization_validation"),
        ):
            client._complete_authorization(mock_authz, "http-01", "/tmp/challenges")
            mock_http01.assert_called_once_with(
                mock_http01_challenge, "example.com", "/tmp/challenges"
            )

    def test_complete_authorization_dns01(self) -> None:
        """Test completing DNS-01 authorization."""
        # Mock authorization with DNS-01 challenge
        mock_authz = Mock()
        mock_authz.body.identifier.value = "example.com"

        mock_dns01_challenge = Mock()
        mock_dns01_challenge.chall.typ = "dns-01"

        mock_authz.body.challenges = [mock_dns01_challenge]

        client = ACMEClient()

        with (
            patch.object(client, "_complete_dns01_challenge") as mock_dns01,
            patch.object(client, "_wait_for_authorization_validation"),
        ):
            client._complete_authorization(mock_authz, "dns-01", None)
            mock_dns01.assert_called_once_with(mock_dns01_challenge, "example.com")

    def test_complete_authorization_challenge_not_found(self) -> None:
        """Test authorization when challenge type not found."""
        # Mock authorization without required challenge type
        mock_authz = Mock()
        mock_authz.body.identifier.value = "example.com"

        mock_other_challenge = Mock()
        mock_other_challenge.chall.typ = "dns-01"

        mock_authz.body.challenges = [mock_other_challenge]

        client = ACMEClient()

        with pytest.raises(
            ACMEValidationError,
            match="No http-01 challenge found for domain example.com",
        ):
            client._complete_authorization(mock_authz, "http-01", None)

    def test_complete_authorization_unsupported_challenge(self) -> None:
        """Test authorization with unsupported challenge type."""
        # Mock authorization with unsupported challenge type
        mock_authz = Mock()
        mock_authz.body.identifier.value = "example.com"
        mock_authz.body.challenges = []

        client = ACMEClient()

        with pytest.raises(
            ACMEValidationError, match="No tls-alpn-01 challenge found for domain"
        ):
            client._complete_authorization(mock_authz, "tls-alpn-01", None)

    def test_complete_authorization_truly_unsupported_challenge(self) -> None:
        """Test authorization with unsupported challenge type that has challenges."""
        # Mock authorization with an unsupported challenge type that has
        # challenges but is truly unsupported
        mock_authz = Mock()
        mock_authz.body.identifier.value = "example.com"

        # Mock challenge for the unsupported type
        mock_challenge = Mock()
        mock_challenge.typ = (
            "tls-alpn-01"  # This will be found but not supported by our implementation
        )
        mock_challenge_body = Mock()
        mock_challenge_body.chall = mock_challenge
        mock_authz.body.challenges = [mock_challenge_body]

        client = ACMEClient()

        # This should trigger the else clause on line 226
        with pytest.raises(
            ACMEValidationError, match="Unsupported challenge type: tls-alpn-01"
        ):
            client._complete_authorization(mock_authz, "tls-alpn-01", None)

    @patch("vibectl.server.acme_client.Path")
    @patch("vibectl.server.acme_client.logger")
    def test_complete_http01_challenge_success(
        self, mock_logger: Mock, mock_path_class: Mock
    ) -> None:
        """Test successful HTTP-01 challenge completion."""
        # Setup mocks - need to structure like ACME library
        mock_challenge_body = Mock()
        mock_challenge = Mock()
        mock_challenge.token = b"test_token"
        mock_challenge.response_and_validation.return_value = (
            Mock(),
            "test_validation",
        )
        # Properly structure the challenge body to match ACME library
        mock_challenge_body.chall = mock_challenge

        mock_challenge_path = Mock()
        mock_challenge_file = Mock()
        # Configure the path division operator correctly
        mock_challenge_path.__truediv__ = Mock(return_value=mock_challenge_file)
        mock_path_class.return_value = mock_challenge_path

        client = ACMEClient()
        client._client = Mock()
        client._account_key = Mock()

        with patch.object(client, "_wait_for_authorization_validation"):
            client._complete_http01_challenge(
                mock_challenge_body, "example.com", "/test/dir"
            )

        # Verify path operations
        mock_path_class.assert_called_with("/test/dir")
        mock_challenge_path.mkdir.assert_called_once_with(parents=True, exist_ok=True)
        mock_challenge_path.__truediv__.assert_called_once_with("test_token")
        mock_challenge_file.write_text.assert_called_once_with("test_validation")

    @patch("vibectl.server.acme_client.Path")
    @patch("vibectl.server.acme_client.logger")
    def test_complete_http01_challenge_default_dir(
        self, mock_logger: Mock, mock_path_class: Mock
    ) -> None:
        """Test HTTP-01 challenge with default challenge directory."""
        mock_challenge_body = Mock()
        mock_challenge = Mock()
        mock_challenge.token = b"test_token"
        mock_challenge.response_and_validation.return_value = (
            Mock(),
            "test_validation",
        )
        mock_challenge_body.chall = mock_challenge

        mock_challenge_path = Mock()
        mock_challenge_file = Mock()
        mock_challenge_path.__truediv__ = Mock(return_value=mock_challenge_file)
        mock_path_class.return_value = mock_challenge_path

        client = ACMEClient()
        client._client = Mock()
        client._account_key = Mock()

        with patch.object(client, "_wait_for_authorization_validation"):
            client._complete_http01_challenge(mock_challenge_body, "example.com", None)

        # Verify default directory is used
        mock_path_class.assert_called_with(".well-known/acme-challenge")

    @patch("vibectl.server.acme_client.Path")
    @patch("vibectl.server.acme_client.logger")
    def test_complete_http01_challenge_cleanup_error(
        self, mock_logger: Mock, mock_path_class: Mock
    ) -> None:
        """Test HTTP-01 challenge with cleanup error."""
        mock_challenge_body = Mock()
        mock_challenge = Mock()
        mock_challenge.token = b"test_token"
        mock_challenge.response_and_validation.return_value = (
            Mock(),
            "test_validation",
        )
        mock_challenge_body.chall = mock_challenge

        mock_challenge_path = Mock()
        mock_challenge_file = Mock()
        mock_challenge_file.unlink.side_effect = OSError("Cleanup failed")
        mock_challenge_path.__truediv__ = Mock(return_value=mock_challenge_file)
        mock_path_class.return_value = mock_challenge_path

        client = ACMEClient()
        client._client = Mock()
        client._account_key = Mock()

        with patch.object(client, "_wait_for_authorization_validation"):
            # Should not raise an exception, just log a warning
            client._complete_http01_challenge(
                mock_challenge_body, "example.com", "/test/dir"
            )

        # Verify warning was logged
        mock_logger.warning.assert_called_once()

    @patch("vibectl.server.acme_client.input")
    @patch("vibectl.server.acme_client.logger")
    def test_complete_dns01_challenge_success(
        self, mock_logger: Mock, mock_input: Mock
    ) -> None:
        """Test successful DNS-01 challenge completion."""
        mock_challenge_body = Mock()
        mock_challenge = Mock()
        mock_challenge.response_and_validation.return_value = (
            Mock(),
            "test_validation",
        )
        mock_challenge_body.chall = mock_challenge

        mock_acme_client = Mock()

        client = ACMEClient()
        client._client = mock_acme_client
        client._account_key = Mock()

        with patch.object(client, "_wait_for_authorization_validation"):
            client._complete_dns01_challenge(mock_challenge_body, "example.com")

            # Verify challenge response generation
            mock_challenge.response_and_validation.assert_called_once_with(
                client._account_key
            )

            # Verify DNS record instructions
            mock_logger.warning.assert_called_once()
            warning_message = mock_logger.warning.call_args[0][0]
            assert "_acme-challenge.example.com" in warning_message
            assert "test_validation" in warning_message

            # Verify user prompt
            mock_input.assert_called_once_with(
                "Press Enter after creating the DNS record..."
            )

            # Verify challenge submission
            mock_acme_client.answer_challenge.assert_called_once()

    @patch("vibectl.server.acme_client.time")
    def test_wait_for_authorization_validation_success(self, mock_time: Mock) -> None:
        """Test successful authorization validation."""
        # Set up time mock to simulate passage of time
        mock_time.time.side_effect = [0, 1]  # Start at 0, then advance to 1
        mock_time.sleep = Mock()

        client = ACMEClient()
        client._client = Mock()

        # Mock successful authorization
        mock_authz = Mock()
        mock_updated_authz = Mock()
        mock_updated_authz.body.status = acme.messages.STATUS_VALID

        client._client.poll.return_value = (mock_updated_authz, None)

        # Execute
        client._wait_for_authorization_validation(mock_authz, timeout=300)

        # Verify polling was called
        client._client.poll.assert_called_once_with(mock_authz)

    @patch("vibectl.server.acme_client.time")
    def test_wait_for_authorization_validation_invalid(self, mock_time: Mock) -> None:
        """Test authorization validation failure."""
        # Set up time mock
        mock_time.time.side_effect = [0, 1]
        mock_time.sleep = Mock()

        client = ACMEClient()
        client._client = Mock()

        # Mock failed authorization
        mock_authz = Mock()
        mock_updated_authz = Mock()
        mock_updated_authz.body.status = acme.messages.STATUS_INVALID

        client._client.poll.return_value = (mock_updated_authz, None)

        # Execute and expect exception
        with pytest.raises(
            ACMEValidationError, match="Authorization validation failed"
        ):
            client._wait_for_authorization_validation(mock_authz)

    @patch("vibectl.server.acme_client.time")
    def test_wait_for_authorization_validation_timeout(self, mock_time: Mock) -> None:
        """Test authorization validation timeout."""
        # Set up time mock to simulate timeout
        mock_time.time.side_effect = [0, 301]  # Start at 0, then exceed timeout
        mock_time.sleep = Mock()

        client = ACMEClient()
        client._client = Mock()

        # Mock pending authorization that never completes
        mock_authz = Mock()
        mock_updated_authz = Mock()
        mock_updated_authz.body.status = acme.messages.STATUS_PENDING

        client._client.poll.return_value = (mock_updated_authz, None)

        # Execute and expect timeout exception
        with pytest.raises(
            ACMEValidationError, match="Authorization validation timed out"
        ):
            client._wait_for_authorization_validation(mock_authz, timeout=300)

    @patch("vibectl.server.acme_client.time")
    def test_wait_for_authorization_validation_retry_on_pending(
        self, mock_time: Mock
    ) -> None:
        """Test retrying on pending exception."""
        # Mock time progression
        mock_time.time.side_effect = [0, 5, 10, 15]
        mock_time.sleep = Mock()

        # Mock authorization
        mock_authz = Mock()
        mock_updated_authz = Mock()
        mock_updated_authz.body.status = acme.messages.STATUS_VALID

        client = ACMEClient()
        client._client = Mock()
        # First call raises "still pending" error, second succeeds
        client._client.poll.side_effect = [
            Exception("Still pending validation"),
            (mock_updated_authz, None),
        ]

        # Should complete without exception after retry
        client._wait_for_authorization_validation(mock_authz, timeout=300)

        # Verify retry logic
        assert client._client.poll.call_count == 2
        mock_time.sleep.assert_called_with(5)

    @patch("vibectl.server.acme_client.time")
    def test_wait_for_authorization_validation_exception_retry(
        self, mock_time: Mock
    ) -> None:
        """Test retrying on exception containing 'still pending'."""
        # Mock time progression
        mock_time.time.side_effect = [0, 5, 10, 15]
        mock_time.sleep = Mock()

        # Mock authorization
        mock_authz = Mock()
        mock_updated_authz = Mock()
        mock_updated_authz.body.status = acme.messages.STATUS_VALID

        client = ACMEClient()
        client._client = Mock()
        # First call raises "still pending" error, second succeeds
        client._client.poll.side_effect = [
            Exception("Request is still pending validation"),
            (mock_updated_authz, None),
        ]

        # Should complete without exception after retry
        client._wait_for_authorization_validation(mock_authz, timeout=300)

        # Verify retry occurred
        assert client._client.poll.call_count == 2

    @patch("vibectl.server.acme_client.time")
    def test_wait_for_authorization_validation_unrecoverable_exception(
        self, mock_time: Mock
    ) -> None:
        """Test handling of unrecoverable exceptions."""
        # Mock time to return numbers, not MagicMock
        mock_time.time.side_effect = [0.0, 5.0]

        client = ACMEClient()
        client._client = Mock()

        # Mock authorization validation with unrecoverable exception
        mock_authz = Mock()
        client._client.poll.side_effect = Exception("Unrecoverable error")

        # Execute and verify exception propagation
        with pytest.raises(ACMEValidationError, match="Authorization validation error"):
            client._wait_for_authorization_validation(mock_authz, timeout=300)

    @patch("vibectl.server.acme_client.create_certificate_signing_request")
    def test_create_csr_single_domain(self, mock_create_csr: Mock) -> None:
        """Test CSR creation for single domain."""
        from cryptography.hazmat.primitives.asymmetric import rsa

        domains = ["example.com"]
        # Use real cryptographic key instead of Mock
        private_key = rsa.generate_private_key(
            public_exponent=65537, key_size=2048, backend=None
        )

        # Mock the generic CSR creation function
        mock_csr = Mock()
        mock_create_csr.return_value = mock_csr

        # Mock the ACME conversion
        mock_cert_request = Mock()

        client = ACMEClient()

        with patch(
            "vibectl.server.acme_client.acme.messages.CertificateRequest",
            return_value=mock_cert_request,
        ):
            result = client._create_csr(domains, private_key)

        assert result == mock_cert_request
        # Verify the generic CSR function was called correctly
        mock_create_csr.assert_called_once_with(domains, private_key)

    @patch("vibectl.server.acme_client.create_certificate_signing_request")
    def test_create_csr_multiple_domains(self, mock_create_csr: Mock) -> None:
        """Test CSR creation for multiple domains."""
        from cryptography.hazmat.primitives.asymmetric import rsa

        domains = ["example.com", "www.example.com", "api.example.com"]
        # Use real cryptographic key instead of Mock
        private_key = rsa.generate_private_key(
            public_exponent=65537, key_size=2048, backend=None
        )

        # Mock the generic CSR creation function
        mock_csr = Mock()
        mock_create_csr.return_value = mock_csr

        # Mock the ACME conversion
        mock_cert_request = Mock()

        client = ACMEClient()

        with patch(
            "vibectl.server.acme_client.acme.messages.CertificateRequest",
            return_value=mock_cert_request,
        ):
            result = client._create_csr(domains, private_key)

        assert result == mock_cert_request
        # Verify the generic CSR function was called correctly
        mock_create_csr.assert_called_once_with(domains, private_key)

    @patch("builtins.open", new_callable=mock_open, read_data=b"cert_data")
    @patch("vibectl.server.acme_client.x509.load_pem_x509_certificate")
    @patch("vibectl.server.acme_client.CertificateInfo")
    def test_check_certificate_expiry_success(
        self, mock_cert_info_class: Mock, mock_load_cert: Mock, mock_file: Mock
    ) -> None:
        """Test successful certificate expiry check."""
        # Mock certificate and expiry date
        mock_cert = Mock()
        mock_load_cert.return_value = mock_cert

        expiry_date = datetime(2024, 12, 31, 23, 59, 59)
        mock_cert_info = Mock()
        mock_cert_info.not_valid_after = expiry_date
        mock_cert_info_class.return_value = mock_cert_info

        client = ACMEClient()
        result = client.check_certificate_expiry("test.crt")

        assert result == expiry_date
        mock_file.assert_called_once_with("test.crt", "rb")
        mock_load_cert.assert_called_once_with(b"cert_data")
        mock_cert_info_class.assert_called_once_with(mock_cert)

    def test_check_certificate_expiry_file_not_found(self) -> None:
        """Test certificate expiry check when file doesn't exist."""
        client = ACMEClient()

        with patch("builtins.open", side_effect=FileNotFoundError):
            result = client.check_certificate_expiry("nonexistent.crt")

        assert result is None

    @patch("builtins.open", new_callable=mock_open, read_data=b"invalid_cert_data")
    @patch("vibectl.server.acme_client.x509.load_pem_x509_certificate")
    @patch("vibectl.server.acme_client.logger")
    def test_check_certificate_expiry_invalid_cert(
        self, mock_logger: Mock, mock_load_cert: Mock, mock_file: Mock
    ) -> None:
        """Test certificate expiry check with invalid certificate."""
        # Mock certificate loading error
        mock_load_cert.side_effect = ValueError("Invalid certificate")

        client = ACMEClient()
        result = client.check_certificate_expiry("invalid.crt")

        assert result is None
        mock_logger.warning.assert_called_once()

    def test_needs_renewal_no_certificate(self) -> None:
        """Test renewal check when certificate doesn't exist."""
        client = ACMEClient()

        with patch.object(client, "check_certificate_expiry", return_value=None):
            result = client.needs_renewal("nonexistent.crt")

        assert result is True

    def test_needs_renewal_expired_soon(self) -> None:
        """Test renewal check for certificate expiring soon."""
        client = ACMEClient()

        # Certificate expires in 25 days (less than default 30-day threshold)
        expiry_date = datetime.now().astimezone() + timedelta(days=25)

        with patch.object(client, "check_certificate_expiry", return_value=expiry_date):
            result = client.needs_renewal("expiring.crt")

        assert result is True

    def test_needs_renewal_not_yet(self) -> None:
        """Test renewal check for certificate not yet needing renewal."""
        client = ACMEClient()

        # Certificate expires in 35 days (more than default 30-day threshold)
        expiry_date = datetime.now().astimezone() + timedelta(days=35)

        with patch.object(client, "check_certificate_expiry", return_value=expiry_date):
            result = client.needs_renewal("valid.crt")

        assert result is False

    def test_needs_renewal_custom_threshold(self) -> None:
        """Test renewal check with custom threshold."""
        client = ACMEClient()

        # Certificate expires in 45 days
        expiry_date = datetime.now().astimezone() + timedelta(days=45)

        with patch.object(client, "check_certificate_expiry", return_value=expiry_date):
            # With 50-day threshold, should need renewal
            result = client.needs_renewal("valid.crt", days_before_expiry=50)

        assert result is True


class TestCreateACMEClient:
    """Test ACME client creation helper function."""

    def test_create_acme_client_default(self) -> None:
        """Test creating ACME client with default settings."""
        client = create_acme_client()

        assert isinstance(client, ACMEClient)
        assert client.directory_url == LETSENCRYPT_PRODUCTION
        assert client.email is None

    def test_create_acme_client_custom_settings(self) -> None:
        """Test creating ACME client with custom settings."""
        client = create_acme_client(
            directory_url="https://custom.acme.com/directory",
            email="test@example.com",
        )

        assert isinstance(client, ACMEClient)
        assert client.directory_url == "https://custom.acme.com/directory"
        assert client.email == "test@example.com"

    def test_create_acme_client_staging(self) -> None:
        """Test creating ACME client with staging environment."""
        client = create_acme_client(directory_url=LETSENCRYPT_STAGING)

        assert isinstance(client, ACMEClient)
        assert client.directory_url == LETSENCRYPT_STAGING

    def test_create_acme_client_with_explicit_production(self) -> None:
        """Test creating ACME client with explicit production URL."""
        client = create_acme_client(directory_url=LETSENCRYPT_PRODUCTION)

        assert isinstance(client, ACMEClient)
        assert client.directory_url == LETSENCRYPT_PRODUCTION
