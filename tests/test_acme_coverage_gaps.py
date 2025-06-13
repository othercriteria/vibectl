"""
Tests for specific coverage gaps in ACME client and manager functionality.

This test suite specifically targets the uncovered lines identified in the coverage report.
These tests complement the existing comprehensive test suites.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, mock_open
from datetime import datetime, timedelta

import pytest
import acme.errors

from vibectl.server.acme_client import ACMEClient, ACMECertificateError
from vibectl.server.acme_manager import ACMEManager
from vibectl.types import Error, Success


class TestACMEClientCoverageGaps:
    """Test cases to improve code coverage for ACMEClient gaps."""

    def test_cleanup_no_longer_needed(self) -> None:
        """Test that cleanup methods are no longer needed with session-based approach."""
        client = ACMEClient(ca_cert_file="/fake/ca.crt")

        # No cleanup methods should exist anymore
        assert not hasattr(client, "_restore_ca_bundle")
        assert not hasattr(client, "cleanup")
        assert not hasattr(client, "__del__")

    def test_ca_file_read_error_handling(self) -> None:
        """Test CA file read error in _ensure_client."""
        client = ACMEClient(ca_cert_file="/fake/ca.crt")

        with (
            patch("os.path.isfile", return_value=True),
            patch("os.path.getsize", return_value=1024),
            patch(
                "builtins.open",
                mock_open(
                    read_data="-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----\n"
                ),
            ),
            patch(
                "vibectl.server.acme_client.acme.client.ClientNetwork"
            ) as mock_client_net_class,
        ):
            # Mock ClientNetwork to fail during get request
            mock_client_net = Mock()
            mock_client_net.get.side_effect = Exception("Connection failed")
            mock_client_net_class.return_value = mock_client_net

            with pytest.raises(
                ACMECertificateError, match="Failed to connect to ACME server"
            ):
                client._ensure_client()

    def test_certificate_expiry_check_file_not_found(self) -> None:
        """Test certificate expiry check when file doesn't exist (lines 401-403)."""
        client = ACMEClient()

        with patch("pathlib.Path.exists", return_value=False):
            result = client.check_certificate_expiry("/nonexistent/cert.pem")
            assert result is None

    def test_certificate_expiry_check_parse_error(self) -> None:
        """Test certificate expiry check with invalid certificate (lines 417-419)."""
        client = ACMEClient()

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.read_bytes", return_value=b"invalid cert data"),
        ):
            # Should return None when certificate parsing fails
            result = client.check_certificate_expiry("/fake/cert.pem")
            assert result is None

    def test_needs_renewal_file_not_found(self) -> None:
        """Test needs_renewal when certificate file doesn't exist (lines 427-429)."""
        client = ACMEClient()

        with patch.object(client, "check_certificate_expiry", return_value=None):
            # Should return True when cert file doesn't exist (needs renewal)
            result = client.needs_renewal("/nonexistent/cert.pem")
            assert result is True

    def test_needs_renewal_expiry_check_failed(self) -> None:
        """Test needs_renewal when expiry check fails (lines 441-443)."""
        client = ACMEClient()

        with patch.object(client, "check_certificate_expiry", return_value=None):
            # Should return True when expiry check fails (needs renewal)
            result = client.needs_renewal("/fake/cert.pem")
            assert result is True


class TestACMEManagerCoverageGaps:
    """Test specific uncovered lines in ACMEManager."""

    @pytest.fixture
    def mock_http_challenge_server(self) -> Mock:
        """Mock HTTP challenge server."""
        server = Mock()
        server.set_challenge = Mock()
        server.remove_challenge = Mock()
        return server

    @pytest.fixture
    def basic_acme_config(self) -> dict:
        """Basic ACME configuration."""
        return {
            "email": "test@example.com",
            "domains": ["example.com"],
            "challenge_type": "http-01",
            "directory_url": "https://acme-test.example.com/directory",
        }

    def test_stop_not_running_check(
        self, mock_http_challenge_server: Mock, basic_acme_config: dict
    ) -> None:
        """Test stop method when not running (lines 106-108)."""
        manager = ACMEManager(
            challenge_server=mock_http_challenge_server,
            acme_config=basic_acme_config,
        )

        # Ensure manager is not running (default state)
        assert not manager.is_running

        async def test_stop() -> None:
            await manager.stop()
            # Should complete without error even when not running

        import asyncio

        asyncio.run(test_stop())

    def test_http01_challenge_handler_no_server_error(
        self, basic_acme_config: dict
    ) -> None:
        """Test HTTP-01 challenge handler without server (lines 294-313)."""
        # Create manager without HTTP challenge server for HTTP-01
        with pytest.raises(ValueError, match="HTTP challenge server is required"):
            ACMEManager(
                challenge_server=None,  # No server provided
                acme_config=basic_acme_config,  # HTTP-01 challenge type
            )


class TestACMEClientNeedsRenewalEdgeCases:
    """Test additional edge cases for needs_renewal method."""

    def test_needs_renewal_with_valid_certificate(self) -> None:
        """Test needs_renewal with a valid certificate that doesn't need renewal."""
        client = ACMEClient()

        # Mock expiry date in the future (more than 30 days) - use timezone-aware datetime
        future_date = datetime.now().astimezone() + timedelta(days=60)

        with patch.object(client, "check_certificate_expiry", return_value=future_date):
            result = client.needs_renewal("/fake/cert.pem", days_before_expiry=30)
            assert result is False

    def test_needs_renewal_with_expiring_certificate(self) -> None:
        """Test needs_renewal with a certificate that's expiring soon."""
        client = ACMEClient()

        # Mock expiry date in the near future (less than 30 days) - use timezone-aware datetime
        near_future_date = datetime.now().astimezone() + timedelta(days=15)

        with patch.object(
            client, "check_certificate_expiry", return_value=near_future_date
        ):
            result = client.needs_renewal("/fake/cert.pem", days_before_expiry=30)
            assert result is True
