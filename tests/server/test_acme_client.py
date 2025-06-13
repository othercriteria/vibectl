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

        assert client.directory_url == LETSENCRYPT_PRODUCTION
        assert client.email is None
        assert client.key_size == 2048
        assert client.ca_cert_file is None
        assert client.tls_alpn_challenge_server is None
        assert client._client is None
        assert client._account_key is None

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
            key=mock_account_key, user_agent="vibectl-server/1.0", verify_ssl=True
        )
        mock_client_net.get.assert_called_once_with(
            "https://test.example.com/directory"
        )
        mock_directory.assert_called_once_with({"directory": "data"})
        mock_client_v2.assert_called_once_with(mock_directory_obj, net=mock_client_net)

        # Verify client state
        assert client._account_key == mock_account_key
        assert client._client == mock_acme_client

    @patch("vibectl.server.acme_client.jose.JWKRSA")
    @patch("vibectl.server.acme_client.rsa.generate_private_key")
    @patch("os.environ", new_callable=dict)
    @patch("os.path.getsize")
    @patch("os.path.exists")
    @patch("os.path.isfile")
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data=(
            "-----BEGIN CERTIFICATE-----\n"
            "fake_ca_cert_content\n"
            "-----END CERTIFICATE-----\n"
        ),
    )
    @patch("requests.Session")
    @patch("vibectl.server.acme_client.acme.client.ClientNetwork")
    @patch("vibectl.server.acme_client.acme.messages.Directory.from_json")
    @patch("vibectl.server.acme_client.acme.client.ClientV2")
    @patch("vibectl.server.acme_client.logger")
    def test_ensure_client_with_custom_ca_certificate(
        self,
        mock_logger: Mock,
        mock_client_v2: Mock,
        mock_directory: Mock,
        mock_client_net_class: Mock,
        mock_session_class: Mock,
        mock_open_file: Mock,
        mock_isfile: Mock,
        mock_exists: Mock,
        mock_getsize: Mock,
        mock_environ: dict,
        mock_rsa_gen: Mock,
        mock_jwk_rsa: Mock,
    ) -> None:
        """Test ACME client initialization with custom CA certificate."""
        # Setup mocks
        mock_exists.return_value = True  # Make the CA cert file check pass
        mock_isfile.return_value = True  # Make the isfile check pass
        mock_getsize.return_value = 1024  # Mock file size
        mock_private_key = Mock()
        mock_rsa_gen.return_value = mock_private_key

        mock_account_key = Mock()
        mock_jwk_rsa.return_value = mock_account_key

        # Mock the custom session
        mock_session = Mock()
        mock_session.get.return_value = Mock(status_code=200)
        mock_session_class.return_value = mock_session

        mock_client_net = Mock()
        mock_client_net_class.return_value = mock_client_net

        mock_response = Mock()
        mock_response.json.return_value = {"directory": "data"}
        mock_client_net.get.return_value = mock_response

        mock_directory_obj = Mock()
        mock_directory.return_value = mock_directory_obj

        mock_acme_client = Mock()
        mock_client_v2.return_value = mock_acme_client

        # Create client with custom CA certificate and call _ensure_client
        ca_cert_file = "/path/to/ca.crt"
        client = ACMEClient(
            directory_url="https://test.example.com/directory",
            ca_cert_file=ca_cert_file,
        )
        client._ensure_client()

        # Verify that the custom CA certificate was used
        mock_isfile.assert_called_with(ca_cert_file)
        mock_getsize.assert_called_with(ca_cert_file)  # Verify getsize was called
        mock_logger.info.assert_any_call(f"Using custom CA certificate: {ca_cert_file}")
        mock_logger.debug.assert_any_call("CA file size: 1024 bytes")

        # Verify ClientNetwork was created with standard SSL verification
        mock_client_net_class.assert_called_once_with(
            key=mock_account_key,
            user_agent="vibectl-server/1.0",
            verify_ssl=True,
        )

        # Verify that REQUESTS_CA_BUNDLE environment variable was set
        assert mock_environ.get("REQUESTS_CA_BUNDLE") == ca_cert_file
        mock_logger.debug.assert_any_call(f"Set REQUESTS_CA_BUNDLE={ca_cert_file}")

        # Verify that no custom session was created (using REQUESTS_CA_BUNDLE instead)
        mock_session_class.assert_not_called()

        # Verify ACME client was created
        mock_client_v2.assert_called_once()
        assert client._client == mock_acme_client

    @patch("vibectl.server.acme_client.jose.JWKRSA")
    @patch("vibectl.server.acme_client.rsa.generate_private_key")
    @patch("vibectl.server.acme_client.acme.client.ClientNetwork")
    @patch("vibectl.server.acme_client.acme.messages.Directory.from_json")
    @patch("vibectl.server.acme_client.acme.client.ClientV2")
    def test_ensure_client_without_custom_ca_certificate(
        self,
        mock_client_v2: Mock,
        mock_directory: Mock,
        mock_client_net_class: Mock,
        mock_rsa_gen: Mock,
        mock_jwk_rsa: Mock,
    ) -> None:
        """Test ACME client initialization without custom CA certificate."""
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

        # Create client without CA certificate and call _ensure_client
        client = ACMEClient(
            directory_url="https://test.example.com/directory",
            ca_cert_file=None,  # Explicitly test None case
        )
        client._ensure_client()

        # Verify default client network initialization (no custom SSL config)
        mock_client_net_class.assert_called_once_with(
            key=mock_account_key,
            user_agent="vibectl-server/1.0",
            verify_ssl=True,
        )

        # Verify ACME client initialization
        mock_client_net.get.assert_called_once_with(
            "https://test.example.com/directory"
        )
        mock_directory.assert_called_once_with({"directory": "data"})
        mock_client_v2.assert_called_once_with(mock_directory_obj, net=mock_client_net)

        # Verify client state
        assert client._account_key == mock_account_key
        assert client._client == mock_acme_client

    def test_init_with_ca_cert_file(self) -> None:
        """Test ACMEClient initialization with custom CA certificate file."""
        ca_cert_file = "/path/to/ca.crt"
        client = ACMEClient(
            directory_url="https://example.com/acme",
            email="test@example.com",
            key_size=4096,
            ca_cert_file=ca_cert_file,
        )

        assert client.directory_url == "https://example.com/acme"
        assert client.email == "test@example.com"
        assert client.key_size == 4096
        assert client.ca_cert_file == ca_cert_file

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
            # Create a properly structured mock authorization for ValidationError
            mock_authz = Mock(spec=acme.messages.AuthorizationResource)
            mock_authz.body = Mock()
            mock_authz.body.identifier = Mock()
            mock_authz.body.identifier.value = "example.com"
            mock_authz.body.challenges = []  # Empty list to avoid iteration errors

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
        mock_challenge.typ = "fake-challenge-01"
        mock_challenge_body = Mock()
        mock_challenge_body.chall = mock_challenge
        mock_authz.body.challenges = [mock_challenge_body]

        client = ACMEClient()

        with pytest.raises(
            ACMEValidationError, match="Unsupported challenge type: fake-challenge-01"
        ):
            client._complete_authorization(mock_authz, "fake-challenge-01", None)

    @patch("vibectl.server.acme_client.Path")
    @patch("vibectl.server.acme_client.logger")
    def test_complete_http01_challenge_success(
        self, mock_logger: Mock, mock_path_class: Mock
    ) -> None:
        """Test successful HTTP-01 challenge completion."""
        # Setup mocks - need to structure like ACME library
        mock_challenge_body = Mock()
        mock_challenge = Mock()
        # Set up the encode method to return the proper token string
        mock_challenge.encode.return_value = "test_token"
        mock_challenge.response_and_validation.return_value = (
            Mock(),
            b"test_validation",
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
        mock_challenge_file.write_text.assert_called_once_with(b"test_validation")
        # Verify that encode method was called with "token"
        mock_challenge.encode.assert_called_once_with("token")

    @patch("vibectl.server.acme_client.Path")
    @patch("vibectl.server.acme_client.logger")
    def test_complete_http01_challenge_default_dir(
        self, mock_logger: Mock, mock_path_class: Mock
    ) -> None:
        """Test HTTP-01 challenge with default challenge directory."""
        mock_challenge_body = Mock()
        mock_challenge = Mock()
        mock_challenge.encode.return_value = "test_token"
        mock_challenge.response_and_validation.return_value = (
            Mock(),
            b"test_validation",
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
        mock_challenge.encode.return_value = "test_token"
        mock_challenge.response_and_validation.return_value = (
            Mock(),
            b"test_validation",
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
        # Setup challenge mock
        mock_challenge = Mock()
        mock_challenge.response_and_validation.return_value = (
            Mock(),
            b"dns_validation_value",
        )

        mock_challenge_body = Mock()
        mock_challenge_body.chall = mock_challenge

        # Setup client
        client = ACMEClient()
        client._account_key = Mock()
        client._client = Mock()

        # Mock user input
        mock_input.return_value = ""

        # Execute challenge completion
        client._complete_dns01_challenge(mock_challenge_body, "example.com")

        # Verify challenge response generation
        mock_challenge.response_and_validation.assert_called_once_with(
            client._account_key
        )

        # Verify challenge submission
        client._client.answer_challenge.assert_called_once_with(
            mock_challenge_body, mock_challenge.response_and_validation.return_value[0]
        )

        # Verify user instructions logged
        mock_logger.warning.assert_called_once()
        warning_message = mock_logger.warning.call_args[0][0]
        assert "_acme-challenge.example.com" in warning_message
        assert "dns_validation_value" in warning_message

    @patch("vibectl.server.acme_client.logger")
    def test_complete_tls_alpn01_challenge_success(self, mock_logger: Mock) -> None:
        """Test successful TLS-ALPN-01 challenge completion."""
        # Setup challenge mock
        mock_challenge = Mock()
        mock_challenge.response_and_validation.return_value = (
            Mock(),
            b"tls_alpn_validation_token",
        )

        mock_challenge_body = Mock()
        mock_challenge_body.chall = mock_challenge

        # Setup TLS-ALPN challenge server mock
        mock_tls_alpn_server = Mock()

        # Setup client with TLS-ALPN challenge server
        client = ACMEClient(tls_alpn_challenge_server=mock_tls_alpn_server)
        client._account_key = Mock()
        client._client = Mock()

        # Execute challenge completion
        client._complete_tls_alpn01_challenge(mock_challenge_body, "example.com")

        # Verify challenge response generation - updated to match actual implementation
        mock_challenge.response_and_validation.assert_called_once_with(
            client._account_key, domain="example.com"
        )

        # Verify challenge server was configured with challenge hash (bytes)
        mock_tls_alpn_server.set_challenge.assert_called_once()
        # The second argument should be the SHA256 hash of the key authorization
        call_args = mock_tls_alpn_server.set_challenge.call_args[0]
        assert call_args[0] == "example.com"
        assert isinstance(call_args[1], bytes)  # Should be challenge hash

        # Verify challenge submission
        client._client.answer_challenge.assert_called_once_with(
            mock_challenge_body, mock_challenge.response_and_validation.return_value[0]
        )

        # Verify appropriate logging occurred
        mock_logger.info.assert_called()

        # Get all log calls (both info and debug)
        info_calls = [call[0][0] for call in mock_logger.info.call_args_list]
        debug_calls = [call[0][0] for call in mock_logger.debug.call_args_list]
        all_log_calls = info_calls + debug_calls

        # Check that the domain and validation token are mentioned in logs
        assert any("example.com" in call for call in all_log_calls)
        # The validation token is converted to challenge_hash hex, so
        # we check for debug logs
        assert any("Challenge hash (hex):" in call for call in debug_calls)
        assert any("TLS-ALPN-01 challenge initiated" in call for call in info_calls)

    def test_complete_tls_alpn01_challenge_no_server(self) -> None:
        """Test TLS-ALPN-01 challenge completion without TLS-ALPN challenge server."""
        # Setup challenge mock
        mock_challenge = Mock()
        mock_challenge.response_and_validation.return_value = (
            Mock(),
            b"tls_alpn_validation_token",
        )

        mock_challenge_body = Mock()
        mock_challenge_body.chall = mock_challenge

        # Setup client without TLS-ALPN challenge server
        client = ACMEClient()
        client._account_key = Mock()
        client._client = Mock()

        # Execute challenge completion and expect failure
        with pytest.raises(
            ACMEValidationError,
            match="TLS-ALPN-01 challenge requires a TLS-ALPN challenge server instance",
        ):
            client._complete_tls_alpn01_challenge(mock_challenge_body, "example.com")

    @patch("vibectl.server.acme_client.logger")
    def test_complete_tls_alpn01_challenge_submission_error(
        self, mock_logger: Mock
    ) -> None:
        """Test TLS-ALPN-01 challenge completion with submission error."""
        # Setup challenge mock
        mock_challenge = Mock()
        mock_challenge.response_and_validation.return_value = (
            Mock(),
            b"tls_alpn_validation_token",
        )

        mock_challenge_body = Mock()
        mock_challenge_body.chall = mock_challenge

        # Setup TLS-ALPN challenge server mock
        mock_tls_alpn_server = Mock()

        # Setup client with TLS-ALPN challenge server
        client = ACMEClient(tls_alpn_challenge_server=mock_tls_alpn_server)
        client._account_key = Mock()
        client._client = Mock()

        # Make answer_challenge raise an exception
        client._client.answer_challenge.side_effect = Exception(
            "ACME submission failed"
        )

        # Execute challenge completion and expect failure
        with pytest.raises(
            ACMEValidationError,
            match="Failed to submit challenge response: ACME submission failed",
        ):
            client._complete_tls_alpn01_challenge(mock_challenge_body, "example.com")

        # Verify challenge server was configured with challenge hash (bytes)
        mock_tls_alpn_server.set_challenge.assert_called_once()
        # The second argument should be the SHA256 hash of the key authorization
        call_args = mock_tls_alpn_server.set_challenge.call_args[0]
        assert call_args[0] == "example.com"
        assert isinstance(call_args[1], bytes)  # Should be challenge hash

        # Verify challenge was cleaned up after error
        mock_tls_alpn_server.remove_challenge.assert_called_once_with("example.com")

    @patch("vibectl.server.acme_client.time")
    def test_wait_for_authorization_validation_success(self, mock_time: Mock) -> None:
        """Test successful authorization validation."""
        # Set up time mock to simulate passage of time
        mock_time.time.side_effect = [0, 1]  # Start at 0, then advance to 1
        mock_time.sleep = Mock()

        # Setup TLS-ALPN challenge server mock
        mock_tls_alpn_server = Mock()

        client = ACMEClient(tls_alpn_challenge_server=mock_tls_alpn_server)
        client._client = Mock()

        # Mock successful authorization
        mock_authz = Mock()
        mock_updated_authz = Mock()
        mock_updated_authz.body.status = acme.messages.STATUS_VALID
        mock_updated_authz.body.identifier.value = "example.com"

        client._client.poll.return_value = (mock_updated_authz, None)

        # Execute
        client._wait_for_authorization_validation(mock_authz, timeout=300)

        # Verify polling was called
        client._client.poll.assert_called_once_with(mock_authz)

        # Verify cleanup was called
        mock_tls_alpn_server.remove_challenge.assert_called_once_with("example.com")

    @patch("vibectl.server.acme_client.time")
    def test_wait_for_authorization_validation_invalid(self, mock_time: Mock) -> None:
        """Test authorization validation failure."""
        # Set up time mock with more values for the new retry logic (8 attempts)
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

        # Setup TLS-ALPN challenge server mock
        mock_tls_alpn_server = Mock()

        client = ACMEClient(tls_alpn_challenge_server=mock_tls_alpn_server)
        client._client = Mock()

        # Mock failed authorization with challenges for error details
        mock_authz = Mock()
        mock_updated_authz = Mock()
        mock_updated_authz.body.status = acme.messages.STATUS_INVALID
        mock_updated_authz.body.identifier.value = "example.com"
        mock_updated_authz.body.challenges = [
            Mock(error=Mock(detail="Connection failed"))
        ]

        client._client.poll.return_value = (mock_updated_authz, None)

        # Execute and expect exception on first invalid
        with pytest.raises(
            ACMEValidationError,
        ) as excinfo:
            client._wait_for_authorization_validation(mock_authz)
        # Check error message content
        msg = str(excinfo.value)
        assert "Authorization validation failed for domain example.com" in msg
        assert "Connection failed" in msg

        # Verify cleanup was called even on failure
        mock_tls_alpn_server.remove_challenge.assert_called_once_with("example.com")

    def test_cleanup_completed_challenge_with_server(self) -> None:
        """Test cleanup of completed challenge with TLS-ALPN server."""
        # Setup TLS-ALPN challenge server mock
        mock_tls_alpn_server = Mock()

        client = ACMEClient(tls_alpn_challenge_server=mock_tls_alpn_server)

        # Mock authorization
        mock_authz = Mock()
        mock_authz.body.identifier.value = "example.com"

        # Execute cleanup
        client._cleanup_completed_challenge(mock_authz)

        # Verify cleanup was called
        mock_tls_alpn_server.remove_challenge.assert_called_once_with("example.com")

    def test_cleanup_completed_challenge_without_server(self) -> None:
        """Test cleanup of completed challenge without TLS-ALPN server."""
        client = ACMEClient()

        # Mock authorization
        mock_authz = Mock()
        mock_authz.body.identifier.value = "example.com"

        # Execute cleanup - should not raise an exception
        client._cleanup_completed_challenge(mock_authz)

    @patch("vibectl.server.acme_client.time")
    def test_wait_for_authorization_validation_timeout(self, mock_time: Mock) -> None:
        """Test authorization validation timeout."""
        # Set up time mock - the pending path has multiple time.time() calls:
        # start, timeout check, elapsed for pending log, timeout again, cleanup elapsed
        mock_time.time.side_effect = [
            0,
            301,
            301,
            301,
            301,
        ]  # Enough values for all paths
        mock_time.sleep = Mock()

        # Setup TLS-ALPN challenge server mock
        mock_tls_alpn_server = Mock()

        client = ACMEClient(tls_alpn_challenge_server=mock_tls_alpn_server)
        client._client = Mock()

        # Mock pending authorization that never completes
        mock_authz = Mock()
        mock_authz.body.identifier.value = "example.com"
        mock_updated_authz = Mock()
        mock_updated_authz.body.status = acme.messages.STATUS_PENDING
        mock_updated_authz.body.identifier.value = "example.com"

        client._client.poll.return_value = (mock_updated_authz, None)

        # Execute and expect timeout exception
        with pytest.raises(
            ACMEValidationError,
            match="Authorization validation timed out after 300 seconds",
        ):
            client._wait_for_authorization_validation(mock_authz, timeout=300)

        # Verify cleanup was called on timeout
        mock_tls_alpn_server.remove_challenge.assert_called_once_with("example.com")

    @patch("vibectl.server.acme_client.time")
    def test_wait_for_authorization_validation_retry_on_pending(
        self, mock_time: Mock
    ) -> None:
        """Test retrying on pending exception."""
        # Mock time progression for exponential backoff
        mock_time.time.side_effect = [0, 5, 10, 15, 20]
        mock_time.sleep = Mock()

        # Mock authorization
        mock_authz = Mock()
        mock_authz.body.identifier.value = "example.com"
        mock_updated_authz = Mock()
        mock_updated_authz.body.status = acme.messages.STATUS_VALID
        mock_updated_authz.body.identifier.value = "example.com"

        # Setup TLS-ALPN challenge server mock
        mock_tls_alpn_server = Mock()

        client = ACMEClient(tls_alpn_challenge_server=mock_tls_alpn_server)
        client._client = Mock()
        # First call raises "still pending" error, second succeeds
        client._client.poll.side_effect = [
            Exception("Still pending validation"),
            (mock_updated_authz, None),
        ]

        # Should complete without exception after retry
        client._wait_for_authorization_validation(mock_authz, timeout=300)

        # Verify retry logic - poll should be called twice
        assert client._client.poll.call_count == 2
        # Verify sleep was called for retry
        mock_time.sleep.assert_called()
        # Verify cleanup was called after success
        mock_tls_alpn_server.remove_challenge.assert_called_once_with("example.com")

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
        """Test authorization validation with unrecoverable exception."""
        # Setup mocks
        client = ACMEClient()
        client._client = Mock()

        # Mock time.time() to track elapsed time
        mock_time.time.side_effect = [0, 1]  # Start time, then 1 second elapsed

        # Mock poll to raise unrecoverable exception
        client._client.poll.side_effect = Exception("Network error")

        # Create mock authorization
        authz = Mock()
        authz.body.identifier.value = "test.example.com"

        # Mock the cleanup method
        with patch.object(client, "_cleanup_completed_challenge"):
            # Should raise ACMEValidationError
            with pytest.raises(
                ACMEValidationError, match="Authorization validation error"
            ):
                client._wait_for_authorization_validation(authz)

            # Should have attempted to poll once
            client._client.poll.assert_called_once_with(authz)


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

    def test_create_acme_client_with_ca_cert_file(self) -> None:
        """Test creating ACME client with custom CA certificate file."""
        ca_cert_file = "/path/to/ca.crt"
        client = create_acme_client(
            directory_url="https://pebble.example.com/dir",
            email="test@example.com",
            ca_cert_file=ca_cert_file,
        )

        assert isinstance(client, ACMEClient)
        assert client.directory_url == "https://pebble.example.com/dir"
        assert client.email == "test@example.com"
        assert client.ca_cert_file == ca_cert_file

    def test_create_acme_client_with_tls_alpn_challenge_server(self) -> None:
        """Test creating ACME client with TLS-ALPN challenge server."""
        mock_tls_alpn_server = Mock()

        client = create_acme_client(
            email="test@example.com",
            tls_alpn_challenge_server=mock_tls_alpn_server,
        )

        assert isinstance(client, ACMEClient)
        assert client.email == "test@example.com"
        assert client.tls_alpn_challenge_server == mock_tls_alpn_server
        assert client.directory_url == LETSENCRYPT_PRODUCTION  # Default
