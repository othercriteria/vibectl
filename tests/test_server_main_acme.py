"""
Tests for ACME-related functionality in vibectl.server.main module.

This module tests ACME certificate provisioning, serve-acme command,
and ACME configuration handling.
"""

from pathlib import Path
from unittest.mock import Mock, patch

from click.testing import CliRunner

from vibectl.server.main import (
    _provision_acme_certificates,
    cli,
    determine_serve_mode,
    get_default_server_config,
)
from vibectl.types import Error, ServeMode, Success


class TestACMECertificateProvisioning:
    """Test ACME certificate provisioning functionality."""

    @patch("vibectl.server.main.create_acme_client")
    @patch("pathlib.Path.mkdir")
    @patch("pathlib.Path.home")
    def test_provision_acme_certificates_success(
        self, mock_home: Mock, mock_mkdir: Mock, mock_create_client: Mock
    ) -> None:
        """Test successful ACME certificate provisioning."""
        # Setup mocks
        mock_home.return_value = Path("/home/test")
        mock_acme_client = Mock()
        mock_create_client.return_value = mock_acme_client
        mock_acme_client.needs_renewal.return_value = True
        mock_acme_client.request_certificate.return_value = (b"cert_data", b"key_data")

        server_config = {
            "acme": {
                "email": "test@example.com",
                "domains": ["example.com", "www.example.com"],
                "directory_url": "https://acme-staging.api.letsencrypt.org/directory",
                "staging": True,
                "challenge_type": "http-01",
                "challenge_dir": ".well-known/acme-challenge",
            }
        }

        result = _provision_acme_certificates(server_config)

        assert isinstance(result, Success)
        assert result.data is not None
        cert_file, key_file = result.data
        assert (
            cert_file == "/home/test/.config/vibectl/server/acme-certs/example.com.crt"
        )
        assert (
            key_file == "/home/test/.config/vibectl/server/acme-certs/example.com.key"
        )

        mock_create_client.assert_called_once_with(
            directory_url="https://acme-staging.api.letsencrypt.org/directory",
            email="test@example.com",
        )
        mock_acme_client.needs_renewal.assert_called_once_with(
            cert_file, days_before_expiry=30
        )
        mock_acme_client.request_certificate.assert_called_once_with(
            domains=["example.com", "www.example.com"],
            challenge_type="http-01",
            cert_file=cert_file,
            key_file=key_file,
            challenge_dir=".well-known/acme-challenge",
        )

    @patch("vibectl.server.main.create_acme_client")
    @patch("pathlib.Path.mkdir")
    @patch("pathlib.Path.home")
    def test_provision_acme_certificates_no_renewal_needed(
        self, mock_home: Mock, mock_mkdir: Mock, mock_create_client: Mock
    ) -> None:
        """Test ACME certificate provisioning when no renewal is needed."""
        # Setup mocks
        mock_home.return_value = Path("/home/test")
        mock_acme_client = Mock()
        mock_create_client.return_value = mock_acme_client
        mock_acme_client.needs_renewal.return_value = False

        server_config = {
            "acme": {
                "email": "test@example.com",
                "domains": ["example.com"],
                "staging": False,
            }
        }

        result = _provision_acme_certificates(server_config)

        assert isinstance(result, Success)
        assert result.data is not None
        cert_file, key_file = result.data
        assert (
            cert_file == "/home/test/.config/vibectl/server/acme-certs/example.com.crt"
        )
        assert (
            key_file == "/home/test/.config/vibectl/server/acme-certs/example.com.key"
        )

        mock_acme_client.needs_renewal.assert_called_once()
        # Should not call request_certificate when no renewal needed
        mock_acme_client.request_certificate.assert_not_called()

    @patch("vibectl.server.main.create_acme_client")
    def test_provision_acme_certificates_client_creation_error(
        self, mock_create_client: Mock
    ) -> None:
        """Test ACME certificate provisioning when client creation fails."""
        mock_create_client.side_effect = Exception("Failed to create ACME client")

        server_config = {
            "acme": {"email": "test@example.com", "domains": ["example.com"]}
        }

        result = _provision_acme_certificates(server_config)

        assert isinstance(result, Error)
        assert "ACME certificate provisioning failed" in result.error

    @patch("vibectl.server.main.create_acme_client")
    @patch("pathlib.Path.mkdir")
    @patch("pathlib.Path.home")
    def test_provision_acme_certificates_request_error(
        self, mock_home: Mock, mock_mkdir: Mock, mock_create_client: Mock
    ) -> None:
        """Test ACME certificate provisioning when certificate request fails."""
        # Setup mocks
        mock_home.return_value = Path("/home/test")
        mock_acme_client = Mock()
        mock_create_client.return_value = mock_acme_client
        mock_acme_client.needs_renewal.return_value = True
        mock_acme_client.request_certificate.side_effect = Exception(
            "Challenge validation failed"
        )

        server_config = {
            "acme": {"email": "test@example.com", "domains": ["example.com"]}
        }

        result = _provision_acme_certificates(server_config)

        assert isinstance(result, Error)
        assert "ACME certificate provisioning failed" in result.error

    @patch("vibectl.server.main.create_acme_client")
    @patch("pathlib.Path.mkdir")
    @patch("pathlib.Path.home")
    def test_provision_acme_certificates_with_defaults(
        self, mock_home: Mock, mock_mkdir: Mock, mock_create_client: Mock
    ) -> None:
        """Test ACME certificate provisioning with default values."""
        # Setup mocks
        mock_home.return_value = Path("/home/test")
        mock_acme_client = Mock()
        mock_create_client.return_value = mock_acme_client
        mock_acme_client.needs_renewal.return_value = True
        mock_acme_client.request_certificate.return_value = (b"cert_data", b"key_data")

        # Minimal configuration - will use defaults
        server_config = {
            "acme": {"email": "test@example.com", "domains": ["example.com"]}
        }

        result = _provision_acme_certificates(server_config)

        assert isinstance(result, Success)
        mock_create_client.assert_called_once_with(
            directory_url="https://acme-v02.api.letsencrypt.org/directory",
            email="test@example.com",
        )
        mock_acme_client.request_certificate.assert_called_once_with(
            domains=["example.com"],
            challenge_type="http-01",
            cert_file="/home/test/.config/vibectl/server/acme-certs/example.com.crt",
            key_file="/home/test/.config/vibectl/server/acme-certs/example.com.key",
            challenge_dir=".well-known/acme-challenge",
        )


class TestServeModeDetection:
    """Test serve mode detection logic."""

    def test_determine_serve_mode_insecure(self) -> None:
        """Test determining insecure serve mode."""
        config = {"tls": {"enabled": False}}
        result = determine_serve_mode(config)
        assert result == ServeMode.INSECURE

    def test_determine_serve_mode_acme(self) -> None:
        """Test determining ACME serve mode."""
        config = {"tls": {"enabled": True}, "acme": {"enabled": True}}
        result = determine_serve_mode(config)
        assert result == ServeMode.ACME

    def test_determine_serve_mode_custom(self) -> None:
        """Test determining custom serve mode."""
        config = {
            "tls": {
                "enabled": True,
                "cert_file": "/path/to/cert.pem",
                "key_file": "/path/to/key.pem",
            },
            "acme": {"enabled": False},
        }
        result = determine_serve_mode(config)
        assert result == ServeMode.CUSTOM

    def test_determine_serve_mode_ca(self) -> None:
        """Test determining CA serve mode."""
        config = {"tls": {"enabled": True}, "acme": {"enabled": False}}
        result = determine_serve_mode(config)
        assert result == ServeMode.CA

    def test_determine_serve_mode_missing_sections(self) -> None:
        """Test serve mode detection with missing configuration sections."""
        config: dict[str, dict] = {}
        result = determine_serve_mode(config)
        assert result == ServeMode.INSECURE


class TestServeACMECommand:
    """Test the serve-acme CLI command."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch("vibectl.server.main._load_and_validate_config")
    @patch("vibectl.server.main._create_and_start_server_common")
    @patch("vibectl.server.main.handle_result")
    def test_serve_acme_command_success(
        self,
        mock_handle_result: Mock,
        mock_create_server: Mock,
        mock_load_config: Mock,
    ) -> None:
        """Test successful serve-acme command execution."""
        # Mock configuration loading
        mock_config = get_default_server_config()
        mock_config["acme"]["enabled"] = True
        mock_config["acme"]["email"] = "test@example.com"
        mock_config["acme"]["domains"] = ["example.com"]
        mock_load_config.return_value = Success(data=mock_config)

        # Mock server creation
        mock_create_server.return_value = Success()

        result = self.runner.invoke(
            cli,
            ["serve-acme", "--email", "test@example.com", "--domain", "example.com"],
        )

        assert result.exit_code == 0
        mock_load_config.assert_called_once()
        mock_create_server.assert_called_once_with(mock_config)
        mock_handle_result.assert_called_once()

    @patch("vibectl.server.main._load_and_validate_config")
    @patch("vibectl.server.main.handle_result")
    def test_serve_acme_command_config_error(
        self,
        mock_handle_result: Mock,
        mock_load_config: Mock,
    ) -> None:
        """Test serve-acme command with configuration error."""
        mock_load_config.return_value = Error(error="Invalid configuration")

        result = self.runner.invoke(
            cli,
            ["serve-acme", "--email", "test@example.com", "--domain", "example.com"],
        )

        assert result.exit_code == 0  # CLI doesn't set exit code, handle_result does
        mock_load_config.assert_called_once()
        mock_handle_result.assert_called_once()

    @patch("vibectl.server.main._load_and_validate_config")
    @patch("vibectl.server.main._create_and_start_server_common")
    @patch("vibectl.server.main.handle_result")
    def test_serve_acme_command_with_all_options(
        self,
        mock_handle_result: Mock,
        mock_create_server: Mock,
        mock_load_config: Mock,
    ) -> None:
        """Test serve-acme command with all options specified."""
        mock_config = get_default_server_config()
        mock_load_config.return_value = Success(data=mock_config)
        mock_create_server.return_value = Success()

        result = self.runner.invoke(
            cli,
            [
                "serve-acme",
                "--host",
                "0.0.0.0",
                "--port",
                "8443",
                "--model",
                "test-model",
                "--max-workers",
                "5",
                "--log-level",
                "DEBUG",
                "--require-auth",
                "--email",
                "test@example.com",
                "--domain",
                "example.com",
                "--domain",
                "www.example.com",
                "--staging",
                "--challenge-type",
                "dns-01",
                "--config",
                "/path/to/config.yaml",
            ],
        )

        assert result.exit_code == 0
        # Verify that configuration was called with proper overrides
        call_args = mock_load_config.call_args
        assert call_args[0][0] == Path("/path/to/config.yaml")
        overrides = call_args[0][1]

        assert overrides["tls"]["enabled"] is True
        assert overrides["acme"]["enabled"] is True
        assert overrides["acme"]["email"] == "test@example.com"
        assert overrides["acme"]["domains"] == ["example.com", "www.example.com"]
        assert overrides["acme"]["staging"] is True
        assert overrides["acme"]["challenge_type"] == "dns-01"
        assert overrides["server"]["host"] == "0.0.0.0"
        assert overrides["server"]["port"] == 8443
        assert overrides["server"]["default_model"] == "test-model"
        assert overrides["server"]["max_workers"] == 5
        assert overrides["server"]["log_level"] == "DEBUG"
        assert overrides["jwt"]["enabled"] is True

    @patch("vibectl.server.main._load_and_validate_config")
    @patch("vibectl.server.main._create_and_start_server_common")
    @patch("vibectl.server.main.handle_result")
    def test_serve_acme_command_default_port_443(
        self,
        mock_handle_result: Mock,
        mock_create_server: Mock,
        mock_load_config: Mock,
    ) -> None:
        """Test serve-acme command defaults to port 443 when no port specified."""
        mock_config = get_default_server_config()
        mock_load_config.return_value = Success(data=mock_config)
        mock_create_server.return_value = Success()

        result = self.runner.invoke(
            cli,
            [
                "serve-acme",
                "--host",
                "localhost",  # Specify host but not port
                "--email",
                "test@example.com",
                "--domain",
                "example.com",
            ],
        )

        assert result.exit_code == 0
        call_args = mock_load_config.call_args
        overrides = call_args[0][1]

        # Should default to port 443 for ACME/TLS
        assert overrides["server"]["port"] == 443

    def test_serve_acme_command_missing_required_options(self) -> None:
        """Test serve-acme command with missing required options."""
        result = self.runner.invoke(cli, ["serve-acme"])

        assert result.exit_code != 0
        assert "Missing option" in result.output

    def test_serve_acme_command_missing_email(self) -> None:
        """Test serve-acme command with missing email."""
        result = self.runner.invoke(cli, ["serve-acme", "--domain", "example.com"])

        assert result.exit_code != 0
        assert "Missing option" in result.output

    def test_serve_acme_command_missing_domain(self) -> None:
        """Test serve-acme command with missing domain."""
        result = self.runner.invoke(cli, ["serve-acme", "--email", "test@example.com"])

        assert result.exit_code != 0
        assert "Missing option" in result.output


class TestACMEConfiguration:
    """Test ACME configuration handling."""

    def test_default_server_config_includes_acme(self) -> None:
        """Test that default server config includes ACME section."""
        config: dict = get_default_server_config()

        assert "acme" in config
        acme_config = config["acme"]
        assert acme_config["enabled"] is False
        assert acme_config["email"] is None
        assert acme_config["domains"] == []
        assert (
            acme_config["directory_url"]
            == "https://acme-v02.api.letsencrypt.org/directory"
        )
        assert acme_config["staging"] is False
        assert acme_config["challenge_type"] == "http-01"
        assert acme_config["challenge_dir"] == ".well-known/acme-challenge"
        assert acme_config["auto_renew"] is True
        assert acme_config["renew_days_before_expiry"] == 30
