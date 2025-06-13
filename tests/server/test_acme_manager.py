"""Tests for ACME certificate manager functionality."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from vibectl.server.acme_manager import ACMEChallengeResponder, ACMEManager
from vibectl.server.http_challenge_server import HTTPChallengeServer
from vibectl.types import ACMECertificateError, Error, Success


@pytest.fixture
def mock_http_challenge_server() -> Mock:
    """Create a mock HTTP challenge server."""
    server = Mock(spec=HTTPChallengeServer)
    server.set_challenge = Mock()
    server.remove_challenge = Mock()
    return server


@pytest.fixture
def mock_tls_alpn_challenge_server() -> Mock:
    """Create a mock TLS-ALPN challenge server."""
    server = Mock()
    server.set_challenge = Mock()
    server.remove_challenge = Mock()
    server.stop = AsyncMock()
    return server


@pytest.fixture
def acme_config_http() -> dict[str, str | list[str]]:
    """Basic ACME configuration for HTTP-01 challenges."""
    return {
        "email": "test@example.com",
        "domains": ["example.com"],
        "challenge_type": "http-01",
        "directory_url": "https://acme-test.example.com/directory",
    }


@pytest.fixture
def acme_config_tls_alpn() -> dict[str, str | list[str]]:
    """ACME configuration for TLS-ALPN-01 challenges."""
    return {
        "email": "test@example.com",
        "domains": ["example.com"],
        "challenge_type": "tls-alpn-01",
        "directory_url": "https://acme-test.example.com/directory",
    }


@pytest.fixture
def acme_config_with_ca() -> dict[str, str | list[str]]:
    """ACME configuration with custom CA certificate."""
    return {
        "email": "test@example.com",
        "domains": ["example.com"],
        "challenge_type": "tls-alpn-01",
        "directory_url": "https://pebble.example.com:14000/dir",
        "ca_cert_file": "/test/ca.crt",
    }


class TestACMEManagerInit:
    """Test ACME manager initialization."""

    def test_init_http_challenge_valid(
        self,
        mock_http_challenge_server: Mock,
        acme_config_http: dict[str, str | list[str]],
    ) -> None:
        """Test initialization with HTTP challenge server."""
        manager = ACMEManager(
            challenge_server=mock_http_challenge_server,
            acme_config=acme_config_http,
        )

        assert manager.challenge_server == mock_http_challenge_server
        assert manager.acme_config == acme_config_http
        assert manager.tls_alpn_challenge_server is None
        assert not manager.is_running

    def test_init_tls_alpn_challenge_valid(
        self,
        mock_tls_alpn_challenge_server: Mock,
        acme_config_tls_alpn: dict[str, str | list[str]],
    ) -> None:
        """Test initialization with TLS-ALPN challenge server."""
        manager = ACMEManager(
            challenge_server=None,
            acme_config=acme_config_tls_alpn,
            tls_alpn_challenge_server=mock_tls_alpn_challenge_server,
        )

        assert manager.challenge_server is None
        assert manager.tls_alpn_challenge_server == mock_tls_alpn_challenge_server
        assert manager.acme_config == acme_config_tls_alpn

    def test_init_http_challenge_missing_server(
        self, acme_config_http: dict[str, str | list[str]]
    ) -> None:
        """Test initialization fails when HTTP challenge server is missing."""
        with pytest.raises(ValueError, match="HTTP challenge server is required"):
            ACMEManager(
                challenge_server=None,
                acme_config=acme_config_http,
            )

    def test_init_tls_alpn_challenge_missing_server(
        self, acme_config_tls_alpn: dict[str, str | list[str]]
    ) -> None:
        """Test initialization fails when TLS-ALPN challenge server is missing."""
        with pytest.raises(ValueError, match="TLS-ALPN challenge server is required"):
            ACMEManager(
                challenge_server=None,
                acme_config=acme_config_tls_alpn,
            )

    def test_init_with_cert_reload_callback(
        self,
        mock_http_challenge_server: Mock,
        acme_config_http: dict[str, str | list[str]],
    ) -> None:
        """Test initialization with certificate reload callback."""
        callback = Mock()
        manager = ACMEManager(
            challenge_server=mock_http_challenge_server,
            acme_config=acme_config_http,
            cert_reload_callback=callback,
        )

        assert manager.cert_reload_callback == callback


class TestACMEManagerStartStop:
    """Test ACME manager start/stop functionality."""

    @pytest.mark.asyncio
    async def test_start_already_running(
        self,
        mock_http_challenge_server: Mock,
        acme_config_http: dict[str, str | list[str]],
    ) -> None:
        """Test starting manager when already running."""
        manager = ACMEManager(
            challenge_server=mock_http_challenge_server,
            acme_config=acme_config_http,
        )

        # Mark as running
        manager._running = True

        result = await manager.start()
        assert isinstance(result, Success)
        assert "already running" in result.message

    @pytest.mark.asyncio
    async def test_stop_not_running(
        self,
        mock_http_challenge_server: Mock,
        acme_config_http: dict[str, str | list[str]],
    ) -> None:
        """Test stopping manager when not running."""
        manager = ACMEManager(
            challenge_server=mock_http_challenge_server,
            acme_config=acme_config_http,
        )

        # Should complete without error
        await manager.stop()

    @pytest.mark.asyncio
    async def test_start_with_certificate_provisioning_error(
        self,
        mock_http_challenge_server: Mock,
        acme_config_http: dict[str, str | list[str]],
    ) -> None:
        """Test start behavior when certificate provisioning fails."""
        manager = ACMEManager(
            challenge_server=mock_http_challenge_server,
            acme_config=acme_config_http,
        )

        # Mock certificate provisioning to fail
        with patch.object(manager, "_provision_initial_certificates") as mock_provision:
            mock_provision.return_value = Error(error="Certificate provisioning failed")

            result = await manager.start()
            assert isinstance(result, Error)
            assert "Certificate provisioning failed" in result.error
            assert not manager.is_running

    @pytest.mark.asyncio
    async def test_start_stop_with_renewal_task(
        self,
        mock_http_challenge_server: Mock,
        acme_config_http: dict[str, str | list[str]],
    ) -> None:
        """Test start/stop with renewal task management."""
        manager = ACMEManager(
            challenge_server=mock_http_challenge_server,
            acme_config=acme_config_http,
        )

        # Mock successful certificate provisioning
        with patch.object(manager, "_provision_initial_certificates") as mock_provision:
            mock_provision.return_value = Success(message="Certificates provisioned")

            # Start manager
            result = await manager.start()
            assert isinstance(result, Success)
            assert manager.is_running
            assert manager._renewal_task is not None

            # Stop manager
            await manager.stop()
            assert not manager.is_running
            assert manager._renewal_task.cancelled()


class TestACMEManagerCertificateProvisioning:
    """Test certificate provisioning functionality."""

    @pytest.mark.asyncio
    async def test_provision_initial_certificates_http(
        self,
        mock_http_challenge_server: Mock,
        acme_config_http: dict[str, str | list[str]],
        tmp_path: str,
    ) -> None:
        """Test initial certificate provisioning for HTTP-01."""
        manager = ACMEManager(
            challenge_server=mock_http_challenge_server,
            acme_config=acme_config_http,
        )

        # Mock cert directory
        with patch.object(manager, "_get_cert_directory") as mock_get_dir:
            mock_get_dir.return_value = tmp_path

            # Mock ACME client
            with patch.object(manager, "_create_acme_client") as mock_create_client:
                mock_client = Mock()
                mock_client.needs_renewal.return_value = True
                mock_create_client.return_value = mock_client

                # Mock certificate provisioning
                with patch.object(
                    manager, "_provision_certificates_async"
                ) as mock_provision:
                    mock_provision.return_value = Success(
                        message="Certificates provisioned"
                    )

                    result = await manager._provision_initial_certificates()

                    assert isinstance(result, Success)
                    assert manager.cert_file is not None
                    assert manager.key_file is not None
                    assert "example.com.crt" in manager.cert_file
                    assert "example.com.key" in manager.key_file
                    mock_provision.assert_called_once()

    @pytest.mark.asyncio
    async def test_provision_initial_certificates_tls_alpn(
        self,
        mock_tls_alpn_challenge_server: Mock,
        acme_config_tls_alpn: dict[str, str | list[str]],
        tmp_path: str,
    ) -> None:
        """Test initial certificate provisioning for TLS-ALPN-01."""
        manager = ACMEManager(
            challenge_server=None,
            acme_config=acme_config_tls_alpn,
            tls_alpn_challenge_server=mock_tls_alpn_challenge_server,
        )

        with patch.object(manager, "_get_cert_directory") as mock_get_dir:
            mock_get_dir.return_value = tmp_path

            with patch.object(manager, "_create_acme_client") as mock_create_client:
                mock_client = Mock()
                mock_client.needs_renewal.return_value = True
                mock_create_client.return_value = mock_client

                with patch.object(
                    manager, "_provision_certificates_async"
                ) as mock_provision:
                    mock_provision.return_value = Success(
                        message="Certificates provisioned"
                    )

                    result = await manager._provision_initial_certificates()

                    assert isinstance(result, Success)
                    assert manager.cert_file is not None
                    assert manager.key_file is not None

    @pytest.mark.asyncio
    async def test_provision_initial_certificates_with_callback(
        self,
        mock_http_challenge_server: Mock,
        acme_config_http: dict[str, str | list[str]],
        tmp_path: str,
    ) -> None:
        """Test certificate provisioning with reload callback."""
        callback = Mock()
        manager = ACMEManager(
            challenge_server=mock_http_challenge_server,
            acme_config=acme_config_http,
            cert_reload_callback=callback,
        )

        with patch.object(manager, "_get_cert_directory") as mock_get_dir:
            mock_get_dir.return_value = tmp_path

            with patch.object(manager, "_create_acme_client") as mock_create_client:
                mock_client = Mock()
                mock_client.needs_renewal.return_value = True
                mock_create_client.return_value = mock_client

                with patch.object(
                    manager, "_provision_certificates_async"
                ) as mock_provision:
                    mock_provision.return_value = Success(
                        message="Certificates provisioned"
                    )

                    result = await manager._provision_initial_certificates()

                    assert isinstance(result, Success)
                    callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_provision_initial_certificates_callback_error(
        self,
        mock_http_challenge_server: Mock,
        acme_config_http: dict[str, str | list[str]],
        tmp_path: str,
    ) -> None:
        """Test certificate provisioning when callback fails."""

        def failing_callback(cert_file: str, key_file: str) -> None:
            raise Exception("Callback failed")

        manager = ACMEManager(
            challenge_server=mock_http_challenge_server,
            acme_config=acme_config_http,
            cert_reload_callback=failing_callback,
        )

        with patch.object(manager, "_get_cert_directory") as mock_get_dir:
            mock_get_dir.return_value = tmp_path

            with patch.object(manager, "_create_acme_client") as mock_create_client:
                mock_client = Mock()
                mock_client.needs_renewal.return_value = True
                mock_create_client.return_value = mock_client

                with patch.object(
                    manager, "_provision_certificates_async"
                ) as mock_provision:
                    mock_provision.return_value = Success(
                        message="Certificates provisioned"
                    )

                    # Should still succeed even if callback fails
                    result = await manager._provision_initial_certificates()
                    assert isinstance(result, Success)

    @pytest.mark.asyncio
    async def test_provision_certificates_async_http(
        self,
        mock_http_challenge_server: Mock,
        acme_config_http: dict[str, str | list[str]],
    ) -> None:
        """Test async certificate provisioning for HTTP-01."""
        manager = ACMEManager(
            challenge_server=mock_http_challenge_server,
            acme_config=acme_config_http,
        )

        mock_client = Mock()

        # Mock the async execution properly
        with patch("asyncio.get_event_loop") as mock_get_loop:
            mock_loop = AsyncMock()  # Use AsyncMock for the loop
            mock_get_loop.return_value = mock_loop

            # Create proper async mock for run_in_executor
            cert_bytes = b"certificate data"
            key_bytes = b"key data"
            mock_loop.run_in_executor = AsyncMock(return_value=(cert_bytes, key_bytes))

            result = await manager._provision_certificates_async(
                mock_client, "/test/cert.crt", "/test/cert.key"
            )

            assert isinstance(result, Success)
            mock_loop.run_in_executor.assert_called_once()

    @pytest.mark.asyncio
    async def test_provision_certificates_async_tls_alpn(
        self,
        mock_tls_alpn_challenge_server: Mock,
        acme_config_tls_alpn: dict[str, str | list[str]],
    ) -> None:
        """Test async certificate provisioning for TLS-ALPN-01."""
        manager = ACMEManager(
            challenge_server=None,
            acme_config=acme_config_tls_alpn,
            tls_alpn_challenge_server=mock_tls_alpn_challenge_server,
        )

        mock_client = Mock()

        with patch("asyncio.get_event_loop") as mock_get_loop:
            mock_loop = AsyncMock()  # Use AsyncMock for the loop
            mock_get_loop.return_value = mock_loop

            # Create proper async mock for run_in_executor
            cert_bytes = b"certificate data"
            key_bytes = b"key data"
            mock_loop.run_in_executor = AsyncMock(return_value=(cert_bytes, key_bytes))

            result = await manager._provision_certificates_async(
                mock_client, "/test/cert.crt", "/test/cert.key"
            )

            assert isinstance(result, Success)
            mock_loop.run_in_executor.assert_called_once()


class TestACMEManagerHTTPChallenge:
    """Test HTTP-01 challenge handling."""

    def test_handle_http01_challenge(
        self,
        mock_http_challenge_server: Mock,
        acme_config_http: dict[str, str | list[str]],
    ) -> None:
        """Test HTTP-01 challenge handling."""
        manager = ACMEManager(
            challenge_server=mock_http_challenge_server,
            acme_config=acme_config_http,
        )

        # Mock challenge components
        mock_challenge_body = Mock()
        mock_challenge = Mock()
        mock_challenge_body.chall = mock_challenge
        mock_challenge.encode.return_value = "test-token"
        mock_challenge.response_and_validation.return_value = ("response", "validation")

        # Mock ACME client
        mock_acme_client = Mock()
        mock_acme_client._account_key = "test-key"
        mock_acme_client._client.answer_challenge = Mock()

        # Mock original method (not used but required)
        original_method = Mock()

        # Call the challenge handler
        manager._handle_http01_challenge(
            mock_challenge_body, "example.com", None, original_method, mock_acme_client
        )

        # Verify challenge was set and removed
        mock_http_challenge_server.set_challenge.assert_called_once_with(
            "test-token", "validation"
        )
        mock_http_challenge_server.remove_challenge.assert_called_once_with(
            "test-token"
        )
        mock_acme_client._client.answer_challenge.assert_called_once()

    def test_handle_http01_challenge_no_server(
        self, acme_config_http: dict[str, str | list[str]]
    ) -> None:
        """Test HTTP-01 challenge handling fails without server."""
        # Should raise ValueError when no HTTP challenge server is provided for HTTP-01
        with pytest.raises(
            ValueError, match="HTTP challenge server is required for HTTP-01 challenges"
        ):
            ACMEManager(
                challenge_server=None,  # No server provided
                acme_config=acme_config_http,
            )

    def test_handle_http01_challenge_submit_error(
        self,
        mock_http_challenge_server: Mock,
        acme_config_http: dict[str, str | list[str]],
    ) -> None:
        """Test HTTP-01 challenge handling when submission fails."""
        manager = ACMEManager(
            challenge_server=mock_http_challenge_server,
            acme_config=acme_config_http,
        )

        # Mock challenge components
        mock_challenge_body = Mock()
        mock_challenge = Mock()
        mock_challenge_body.chall = mock_challenge
        mock_challenge.encode.return_value = "test-token"
        mock_challenge.response_and_validation.return_value = ("response", "validation")

        # Mock ACME client with failing submission
        mock_acme_client = Mock()
        mock_acme_client._account_key = "test-key"
        mock_acme_client._client.answer_challenge.side_effect = Exception(
            "Submission failed"
        )

        original_method = Mock()

        with pytest.raises(Exception, match="Submission failed"):
            manager._handle_http01_challenge(
                mock_challenge_body,
                "example.com",
                None,
                original_method,
                mock_acme_client,
            )

        # Verify cleanup still happened
        mock_http_challenge_server.remove_challenge.assert_called_once_with(
            "test-token"
        )


class TestACMEManagerUtils:
    """Test ACME manager utility methods."""

    def test_create_acme_client_http(
        self,
        mock_http_challenge_server: Mock,
        acme_config_http: dict[str, str | list[str]],
    ) -> None:
        """Test ACME client creation for HTTP-01."""
        manager = ACMEManager(
            challenge_server=mock_http_challenge_server,
            acme_config=acme_config_http,
        )

        with patch("vibectl.server.acme_manager.create_acme_client") as mock_create:
            mock_client = Mock()
            mock_create.return_value = mock_client

            client = manager._create_acme_client()

            mock_create.assert_called_once_with(
                directory_url=acme_config_http["directory_url"],
                email=acme_config_http["email"],
                ca_cert_file=None,
                tls_alpn_challenge_server=None,
            )
            assert client == mock_client

    def test_create_acme_client_tls_alpn(
        self,
        mock_tls_alpn_challenge_server: Mock,
        acme_config_tls_alpn: dict[str, str | list[str]],
    ) -> None:
        """Test ACME client creation for TLS-ALPN-01."""
        manager = ACMEManager(
            challenge_server=None,
            acme_config=acme_config_tls_alpn,
            tls_alpn_challenge_server=mock_tls_alpn_challenge_server,
        )

        with patch("vibectl.server.acme_manager.create_acme_client") as mock_create:
            mock_client = Mock()
            mock_create.return_value = mock_client

            manager._create_acme_client()

            mock_create.assert_called_once_with(
                directory_url=acme_config_tls_alpn["directory_url"],
                email=acme_config_tls_alpn["email"],
                ca_cert_file=None,
                tls_alpn_challenge_server=mock_tls_alpn_challenge_server,
            )

    def test_create_acme_client_with_ca_cert(
        self,
        mock_tls_alpn_challenge_server: Mock,
        acme_config_with_ca: dict[str, str | list[str]],
    ) -> None:
        """Test ACME client creation with custom CA certificate."""
        manager = ACMEManager(
            challenge_server=None,
            acme_config=acme_config_with_ca,
            tls_alpn_challenge_server=mock_tls_alpn_challenge_server,
        )

        with patch("vibectl.server.acme_manager.create_acme_client") as mock_create:
            mock_client = Mock()
            mock_create.return_value = mock_client

            manager._create_acme_client()

            mock_create.assert_called_once_with(
                directory_url=acme_config_with_ca["directory_url"],
                email=acme_config_with_ca["email"],
                ca_cert_file=acme_config_with_ca["ca_cert_file"],
                tls_alpn_challenge_server=mock_tls_alpn_challenge_server,
            )

    def test_get_cert_directory(
        self,
        mock_http_challenge_server: Mock,
        acme_config_http: dict[str, str | list[str]],
    ) -> None:
        """Test certificate directory path generation."""
        manager = ACMEManager(
            challenge_server=mock_http_challenge_server,
            acme_config=acme_config_http,
        )

        cert_dir = manager._get_cert_directory()

        assert cert_dir.name == "acme-certs"
        assert "vibectl" in str(cert_dir)
        assert "server" in str(cert_dir)

    def test_get_certificate_files(
        self,
        mock_http_challenge_server: Mock,
        acme_config_http: dict[str, str | list[str]],
    ) -> None:
        """Test getting certificate file paths."""
        manager = ACMEManager(
            challenge_server=mock_http_challenge_server,
            acme_config=acme_config_http,
        )

        # Initially None
        cert_file, key_file = manager.get_certificate_files()
        assert cert_file is None
        assert key_file is None

        # After setting
        manager.cert_file = "/test/cert.crt"
        manager.key_file = "/test/cert.key"

        cert_file, key_file = manager.get_certificate_files()
        assert cert_file == "/test/cert.crt"
        assert key_file == "/test/cert.key"


class TestACMEChallengeResponder:
    """Test ACME challenge responder functionality."""

    def test_create_challenge_file(self, mock_http_challenge_server: Mock) -> None:
        """Test challenge file creation."""
        responder = ACMEChallengeResponder(mock_http_challenge_server)

        responder.create_challenge_file("test-token", "test-content")

        mock_http_challenge_server.set_challenge.assert_called_once_with(
            "test-token", "test-content"
        )

    def test_cleanup_challenge_file(self, mock_http_challenge_server: Mock) -> None:
        """Test challenge file cleanup."""
        responder = ACMEChallengeResponder(mock_http_challenge_server)

        responder.cleanup_challenge_file("test-token")

        mock_http_challenge_server.remove_challenge.assert_called_once_with(
            "test-token"
        )


@pytest.mark.asyncio
class TestACMEManagerRenewal:
    """Test certificate renewal functionality."""

    async def test_check_and_renew_certificates_no_files(
        self,
        mock_http_challenge_server: Mock,
        acme_config_http: dict[str, str | list[str]],
    ) -> None:
        """Test renewal check when no certificate files are configured."""
        manager = ACMEManager(
            challenge_server=mock_http_challenge_server,
            acme_config=acme_config_http,
        )

        # Should complete without error when no files are set
        await manager._check_and_renew_certificates()

        # No actual renewal should happen
        assert manager.cert_file is None
        assert manager.key_file is None

    async def test_check_and_renew_certificates_no_renewal_needed(
        self,
        mock_http_challenge_server: Mock,
        acme_config_http: dict[str, str | list[str]],
    ) -> None:
        """Test renewal check when certificates are still valid."""
        manager = ACMEManager(
            challenge_server=mock_http_challenge_server,
            acme_config=acme_config_http,
        )

        # Set certificate files
        manager.cert_file = "/test/cert.crt"
        manager.key_file = "/test/cert.key"

        with patch.object(manager, "_create_acme_client") as mock_create_client:
            mock_client = Mock()
            mock_client.needs_renewal.return_value = False
            mock_create_client.return_value = mock_client

            await manager._check_and_renew_certificates()

            mock_client.needs_renewal.assert_called_once()

    async def test_check_and_renew_certificates_renewal_success(
        self,
        mock_http_challenge_server: Mock,
        acme_config_http: dict[str, str | list[str]],
    ) -> None:
        """Test successful certificate renewal."""
        callback = Mock()
        manager = ACMEManager(
            challenge_server=mock_http_challenge_server,
            acme_config=acme_config_http,
            cert_reload_callback=callback,
        )

        manager.cert_file = "/test/cert.crt"
        manager.key_file = "/test/cert.key"

        with patch.object(manager, "_create_acme_client") as mock_create_client:
            mock_client = Mock()
            mock_client.needs_renewal.return_value = True
            mock_create_client.return_value = mock_client

            with patch.object(
                manager, "_provision_certificates_async"
            ) as mock_provision:
                mock_provision.return_value = Success(message="Renewed")

                await manager._check_and_renew_certificates()

                mock_provision.assert_called_once()
                callback.assert_called_once_with("/test/cert.crt", "/test/cert.key")

    async def test_check_and_renew_certificates_renewal_failure(
        self,
        mock_http_challenge_server: Mock,
        acme_config_http: dict[str, str | list[str]],
    ) -> None:
        """Test certificate renewal failure."""
        manager = ACMEManager(
            challenge_server=mock_http_challenge_server,
            acme_config=acme_config_http,
        )

        manager.cert_file = "/test/cert.crt"
        manager.key_file = "/test/cert.key"

        with patch.object(manager, "_create_acme_client") as mock_create_client:
            mock_client = Mock()
            mock_client.needs_renewal.return_value = True
            mock_create_client.return_value = mock_client

            with patch.object(
                manager, "_provision_certificates_async"
            ) as mock_provision:
                mock_provision.return_value = Error(error="Renewal failed")

                # Should not raise exception, just log error
                await manager._check_and_renew_certificates()

                mock_provision.assert_called_once()

    async def test_start_tls_alpn_continues_on_initial_failure(self) -> None:
        """Test TLS-ALPN-01 manager keeps running even if initial provisioning fails."""
        mock_acme_client = AsyncMock()
        mock_acme_client.request_certificate.side_effect = ACMECertificateError(
            "Initial certificate request failed"
        )

        # Configure for TLS-ALPN-01
        config = {
            "enabled": True,
            "email": "test@example.com",
            "domains": ["test.example.com"],
            "directory_url": "https://acme.example.com/directory",
            "challenge_type": "tls-alpn-01",
            "ca_cert_file": None,
        }

        mock_tls_alpn_server = AsyncMock()

        with patch(
            "vibectl.server.acme_manager.create_acme_client",
            return_value=mock_acme_client,
        ):
            manager = ACMEManager(
                challenge_server=None,
                acme_config=config,
                tls_alpn_challenge_server=mock_tls_alpn_server,
            )

            # Start should succeed even though initial provisioning fails
            result = await manager.start()

            # Should continue running for TLS-ALPN-01
            assert isinstance(result, Success)
            assert manager.is_running

            await manager.stop()

    async def test_start_http01_exits_on_initial_failure(self) -> None:
        """Test HTTP-01 manager exits when initial provisioning fails."""
        mock_acme_client = AsyncMock()
        mock_acme_client.request_certificate.side_effect = ACMECertificateError(
            "Initial certificate request failed"
        )

        # Configure for HTTP-01
        config = {
            "enabled": True,
            "email": "test@example.com",
            "domains": ["test.example.com"],
            "directory_url": "https://acme.example.com/directory",
            "challenge_type": "http-01",
            "ca_cert_file": None,
        }

        mock_http_challenge_server = AsyncMock()

        with patch(
            "vibectl.server.acme_manager.create_acme_client",
            return_value=mock_acme_client,
        ):
            manager = ACMEManager(
                challenge_server=mock_http_challenge_server, acme_config=config
            )

            # Start should fail and manager should not be running
            result = await manager.start()

            # Should fail for HTTP-01
            assert isinstance(result, Error)
            assert not manager.is_running

    async def test_start_tls_alpn_background_retry_success(self) -> None:
        """Test TLS-ALPN-01 manager retries in background and eventually succeeds."""
        mock_acme_client = AsyncMock()

        # First call fails, second call succeeds
        mock_acme_client.request_certificate.side_effect = [
            ACMECertificateError("Initial failure"),
            (b"cert_data", b"key_data"),  # Success on retry
        ]

        config = {
            "enabled": True,
            "email": "test@example.com",
            "domains": ["test.example.com"],
            "directory_url": "https://acme.example.com/directory",
            "challenge_type": "tls-alpn-01",
            "ca_cert_file": None,
            "cert_file": "/tmp/test_cert.pem",
            "key_file": "/tmp/test_key.pem",
        }

        mock_tls_alpn_server = AsyncMock()

        with (
            patch(
                "vibectl.server.acme_manager.create_acme_client",
                return_value=mock_acme_client,
            ),
            patch("pathlib.Path.write_bytes"),
            patch("pathlib.Path.parent") as mock_parent,
        ):
            mock_parent.mkdir = Mock()

            manager = ACMEManager(
                challenge_server=None,
                acme_config=config,
                tls_alpn_challenge_server=mock_tls_alpn_server,
            )

            result = await manager.start()
            assert isinstance(result, Success)
            assert manager.is_running

            await manager.stop()

    async def test_start_tls_alpn_background_retry_stops_on_manager_stop(self) -> None:
        """Test TLS-ALPN-01 background retry stops when manager is stopped."""
        mock_acme_client = AsyncMock()

        # Always fail on certificate request
        mock_acme_client.request_certificate.side_effect = ACMECertificateError(
            "Persistent failure"
        )

        config = {
            "enabled": True,
            "email": "test@example.com",
            "domains": ["test.example.com"],
            "directory_url": "https://acme.example.com/directory",
            "challenge_type": "tls-alpn-01",
            "ca_cert_file": None,
        }

        mock_tls_alpn_server = AsyncMock()

        with patch(
            "vibectl.server.acme_manager.create_acme_client",
            return_value=mock_acme_client,
        ):
            manager = ACMEManager(
                challenge_server=None,
                acme_config=config,
                tls_alpn_challenge_server=mock_tls_alpn_server,
            )

            result = await manager.start()
            assert isinstance(result, Success)
            assert manager.is_running

            # Stop should succeed and stop background retry
            await manager.stop()
            assert not manager.is_running
