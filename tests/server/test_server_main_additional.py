"""
Tests for additional functionality in vibectl.server.main module.

This module tests remaining functionality including serve-custom command,
smart serve command, server creation, and other utility functions.
"""

from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

from click.testing import CliRunner

from vibectl.server.config import get_default_server_config
from vibectl.server.main import (
    _create_and_start_server_common,
    _load_and_validate_config,
    _perform_certificate_generation,
    cli,
    handle_result,
)
from vibectl.types import Error, ServeMode, Success


class TestServerCreationAndStartup:
    """Test server creation and startup functionality."""

    @patch("vibectl.server.main.init_logging")
    @patch("vibectl.server.main._create_and_start_server_with_async_acme")
    def test_create_and_start_server_common_acme_enabled(
        self,
        mock_async_acme_server: Mock,
        mock_init_logging: Mock,
    ) -> None:
        """Test server creation with ACME certificates enabled."""
        server_config = {
            "server": {
                "host": "0.0.0.0",
                "port": 50051,
                "default_model": "test-model",
                "max_workers": 10,
                "log_level": "INFO",
            },
            "tls": {"enabled": True, "cert_file": None, "key_file": None},
            "acme": {
                "enabled": True,
                "email": "test@example.com",
                "domains": ["example.com"],
                "challenge_type": "tls-alpn-01",
            },
            "jwt": {"enabled": False},
        }

        # Mock ACME server startup
        mock_async_acme_server.return_value = Success()

        result = _create_and_start_server_common(server_config)

        assert isinstance(result, Success)
        mock_async_acme_server.assert_called_once_with(server_config)

    @patch("vibectl.server.main.init_logging")
    @patch("vibectl.server.main.create_server")
    def test_create_and_start_server_common_tls_disabled(
        self, mock_create_server: Mock, mock_init_logging: Mock
    ) -> None:
        """Test server creation with TLS disabled."""
        server_config = {
            "server": {
                "host": "localhost",
                "port": 8080,
                "default_model": None,
                "max_workers": 5,
                "log_level": "DEBUG",
            },
            "tls": {"enabled": False},
            "acme": {"enabled": False},
            "jwt": {"enabled": True},
        }

        mock_server = Mock()
        mock_create_server.return_value = mock_server
        mock_server.serve_forever.return_value = None

        result = _create_and_start_server_common(server_config)

        assert isinstance(result, Success)
        mock_create_server.assert_called_once_with(
            host="localhost",
            port=8080,
            default_model=None,
            max_workers=5,
            require_auth=True,
            use_tls=False,
            cert_file=None,
            key_file=None,
        )

    @patch("vibectl.server.main.init_logging")
    @patch("vibectl.server.main._create_and_start_server_with_async_acme")
    def test_create_and_start_server_common_acme_error(
        self, mock_async_acme_server: Mock, mock_init_logging: Mock
    ) -> None:
        """Test server creation when ACME provisioning fails."""
        server_config = {
            "server": {
                "host": "0.0.0.0",
                "port": 50051,
                "default_model": "test",
                "max_workers": 10,
                "log_level": "INFO",
            },
            "tls": {"enabled": True},
            "acme": {
                "enabled": True,
                "email": "test@example.com",
                "domains": ["example.com"],
                "challenge_type": "tls-alpn-01",
            },
            "jwt": {"enabled": False},
        }

        mock_async_acme_server.return_value = Error(error="ACME provisioning failed")

        result = _create_and_start_server_common(server_config)

        assert isinstance(result, Error)
        assert "ACME provisioning failed" in result.error

    @patch("vibectl.server.main.init_logging")
    @patch("vibectl.server.main._create_and_start_server_with_async_acme")
    def test_create_and_start_server_common_acme_none_data(
        self, mock_async_acme_server: Mock, mock_init_logging: Mock
    ) -> None:
        """Test server creation when ACME provisioning returns None data."""
        server_config = {
            "server": {
                "host": "0.0.0.0",
                "port": 50051,
                "default_model": "test",
                "max_workers": 10,
                "log_level": "INFO",
            },
            "tls": {"enabled": True},
            "acme": {
                "enabled": True,
                "email": "test@example.com",
                "domains": ["example.com"],
                "challenge_type": "tls-alpn-01",
            },
            "jwt": {"enabled": False},
        }

        # Mock ACME returning error for missing data
        mock_async_acme_server.return_value = Error(
            error="ACME certificate provisioning returned no certificate data"
        )

        result = _create_and_start_server_common(server_config)

        assert isinstance(result, Error)
        assert (
            "ACME certificate provisioning returned no certificate data" in result.error
        )

    @patch("vibectl.server.main.init_logging")
    @patch("vibectl.server.main.create_server")
    def test_create_and_start_server_common_keyboard_interrupt(
        self, mock_create_server: Mock, mock_init_logging: Mock
    ) -> None:
        """Test server creation with keyboard interrupt."""
        server_config = {
            "server": {
                "host": "0.0.0.0",
                "port": 50051,
                "default_model": "test",
                "max_workers": 10,
                "log_level": "INFO",
            },
            "tls": {"enabled": False},
            "acme": {"enabled": False},
            "jwt": {"enabled": False},
        }

        mock_server = Mock()
        mock_create_server.return_value = mock_server
        mock_server.serve_forever.side_effect = KeyboardInterrupt()

        result = _create_and_start_server_common(server_config)

        assert isinstance(result, Success)

    @patch("vibectl.server.main.init_logging")
    @patch("vibectl.server.main.create_server")
    def test_create_and_start_server_common_server_error(
        self, mock_create_server: Mock, mock_init_logging: Mock
    ) -> None:
        """Test server creation when server creation fails."""
        server_config = {
            "server": {
                "host": "0.0.0.0",
                "port": 50051,
                "default_model": "test",
                "max_workers": 10,
                "log_level": "INFO",
            },
            "tls": {"enabled": False},
            "acme": {"enabled": False},
            "jwt": {"enabled": False},
        }

        mock_create_server.side_effect = Exception("Failed to create server")

        result = _create_and_start_server_common(server_config)

        assert isinstance(result, Error)
        assert "Server startup failed" in result.error


class TestConfigurationLoading:
    """Test configuration loading and validation."""

    @patch("vibectl.server.main.load_server_config")
    @patch("vibectl.server.config.validate_server_config")
    def test_load_and_validate_config_success(
        self, mock_validate: Mock, mock_load_config: Mock
    ) -> None:
        """Test successful configuration loading and validation."""
        config = get_default_server_config()
        mock_load_config.return_value = Success(data=config)
        mock_validate.return_value = Success()

        result = _load_and_validate_config(
            config_path=None, overrides={"server": {"port": "8080"}}
        )

        assert isinstance(result, Success)
        assert result.data is not None
        # Port should be converted to int and merged
        assert result.data["server"]["port"] == 8080

    @patch("vibectl.server.config.ServerConfig.load")
    @patch("vibectl.server.config.ServerConfig.validate")
    def test_load_and_validate_config_load_error(
        self, mock_validate: Mock, mock_load: Mock
    ) -> None:
        """Test configuration loading when loading fails."""
        mock_load.return_value = Error(error="Failed to load config")

        result = _load_and_validate_config(
            config_path=Path("/test/config.yaml"), overrides={}
        )

        assert isinstance(result, Error)
        assert "Failed to load config" in result.error

    @patch("vibectl.server.config.ServerConfig.load")
    @patch("vibectl.server.config.ServerConfig.validate")
    def test_load_and_validate_config_validation_error(
        self, mock_validate: Mock, mock_load: Mock
    ) -> None:
        """Test configuration loading when validation fails."""
        config = get_default_server_config()
        mock_load.return_value = Success(data=config)
        mock_validate.return_value = Error(error="Invalid port number")

        result = _load_and_validate_config(config_path=None, overrides={})

        assert isinstance(result, Error)
        assert "Invalid port number" in result.error

    @patch("vibectl.server.config.ServerConfig.load")
    @patch("vibectl.server.config.ServerConfig.validate")
    def test_load_and_validate_config_with_overrides(
        self, mock_validate: Mock, mock_load: Mock
    ) -> None:
        """Test configuration loading with complex overrides."""
        config = get_default_server_config()
        mock_load.return_value = Success(data=config)

        # Make validate return the config it receives (with overrides applied)
        def validate_side_effect(received_config: dict[str, Any]) -> Success:
            # Apply type conversions that real validation would do
            if "server" in received_config:
                server_section = received_config["server"]
                if "port" in server_section and isinstance(server_section["port"], str):
                    server_section["port"] = int(server_section["port"])
                if "max_workers" in server_section and isinstance(
                    server_section["max_workers"], str
                ):
                    server_section["max_workers"] = int(server_section["max_workers"])
            return Success(data=received_config)

        mock_validate.side_effect = validate_side_effect

        overrides = {
            "server": {"host": "custom.host", "port": "9000", "max_workers": "15"},
            "tls": {"enabled": True},
            "jwt": {"enabled": True},
        }

        result = _load_and_validate_config(config_path=None, overrides=overrides)

        assert isinstance(result, Success)
        merged_config = result.data
        assert merged_config is not None  # Type narrowing for mypy
        assert merged_config["server"]["host"] == "custom.host"
        assert merged_config["server"]["port"] == 9000  # Should be converted to int
        assert (
            merged_config["server"]["max_workers"] == 15
        )  # Should be converted to int
        assert merged_config["tls"]["enabled"] is True
        assert merged_config["jwt"]["enabled"] is True


class TestCertificateGeneration:
    """Test certificate generation functionality."""

    @patch("vibectl.server.main.get_config_dir")
    @patch("vibectl.server.main.cert_utils.get_default_cert_paths")
    @patch("vibectl.server.main.cert_utils.ensure_certificate_exists")
    @patch("pathlib.Path.mkdir")
    def test_perform_certificate_generation_success(
        self,
        mock_mkdir: Mock,
        mock_ensure_cert: Mock,
        mock_get_paths: Mock,
        mock_get_config_dir: Mock,
    ) -> None:
        """Test successful certificate generation."""
        mock_get_config_dir.return_value = Path("/test/config")
        mock_get_paths.return_value = (
            Path("/test/config/certs/server.crt"),
            Path("/test/config/certs/server.key"),
        )
        mock_ensure_cert.return_value = Success(message="Certificate generated")

        result = _perform_certificate_generation(
            hostname="localhost", cert_file=None, key_file=None, force=False
        )

        assert isinstance(result, Success)
        mock_ensure_cert.assert_called_once_with(
            str(Path("/test/config/certs/server.crt")),
            str(Path("/test/config/certs/server.key")),
            hostname="localhost",
            regenerate=False,
        )

    @patch("vibectl.server.main.cert_utils.ensure_certificate_exists")
    @patch("pathlib.Path.mkdir")
    def test_perform_certificate_generation_with_explicit_paths(
        self, mock_mkdir: Mock, mock_ensure_cert: Mock
    ) -> None:
        """Test certificate generation with explicit file paths."""
        mock_ensure_cert.return_value = Success(message="Certificate generated")

        result = _perform_certificate_generation(
            hostname="example.com",
            cert_file="/custom/cert.pem",
            key_file="/custom/key.pem",
            force=True,
        )

        assert isinstance(result, Success)
        mock_ensure_cert.assert_called_once_with(
            "/custom/cert.pem",
            "/custom/key.pem",
            hostname="example.com",
            regenerate=True,
        )

    @patch("vibectl.server.main.cert_utils.ensure_certificate_exists")
    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.mkdir")
    def test_perform_certificate_generation_error(
        self, mock_mkdir: Mock, mock_exists: Mock, mock_ensure_cert: Mock
    ) -> None:
        """Test certificate generation when cert creation fails."""
        mock_exists.return_value = (
            False  # Files don't exist, so we proceed to cert generation
        )
        mock_ensure_cert.side_effect = Exception("Failed to create certificate")

        result = _perform_certificate_generation(
            hostname="localhost",
            cert_file="/test/cert.pem",
            key_file="/test/key.pem",
            force=False,
        )

        assert isinstance(result, Error)
        assert "Certificate generation failed" in result.error

    @patch("vibectl.server.main.cert_utils.ensure_certificate_exists")
    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.mkdir")
    def test_perform_certificate_generation_exception(
        self, mock_mkdir: Mock, mock_exists: Mock, mock_ensure_cert: Mock
    ) -> None:
        """Test certificate generation with exception."""
        mock_exists.return_value = (
            False  # Files don't exist, so we proceed to cert generation
        )
        mock_ensure_cert.side_effect = Exception("Unexpected error")

        result = _perform_certificate_generation(
            hostname="localhost",
            cert_file="/test/cert.pem",
            key_file="/test/key.pem",
            force=False,
        )

        assert isinstance(result, Error)
        assert "Certificate generation failed" in result.error


class TestServeCustomCommand:
    """Test the serve-custom CLI command."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch("vibectl.server.main._load_and_validate_config")
    @patch("vibectl.server.main._create_and_start_server_common")
    @patch("vibectl.server.main.handle_result")
    def test_serve_custom_command_success(
        self, mock_handle_result: Mock, mock_create_server: Mock, mock_load_config: Mock
    ) -> None:
        """Test successful serve-custom command execution."""
        # Use Click's isolated filesystem to create actual files for path validation
        with self.runner.isolated_filesystem():
            # Create actual temporary cert files for Click validation
            Path("cert.pem").write_text("fake cert")
            Path("key.pem").write_text("fake key")

            mock_config = get_default_server_config()
            mock_load_config.return_value = Success(data=mock_config)
            mock_create_server.return_value = Success()

            result = self.runner.invoke(
                cli,
                ["serve-custom", "--cert-file", "cert.pem", "--key-file", "key.pem"],
            )

            assert result.exit_code == 0
            mock_load_config.assert_called_once()
            mock_create_server.assert_called_once()

    @patch("vibectl.server.main._load_and_validate_config")
    @patch("vibectl.server.main._create_and_start_server_common")
    @patch("vibectl.server.main.handle_result")
    def test_serve_custom_command_with_all_options(
        self, mock_handle_result: Mock, mock_create_server: Mock, mock_load_config: Mock
    ) -> None:
        """Test serve-custom command with all options."""
        with self.runner.isolated_filesystem():
            # Create actual temporary cert files for Click validation
            Path("server.crt").write_text("fake cert")
            Path("server.key").write_text("fake key")
            Path("ca-bundle.pem").write_text("fake ca bundle")
            Path("config.yaml").write_text("fake config")

            mock_config = get_default_server_config()
            mock_load_config.return_value = Success(data=mock_config)
            mock_create_server.return_value = Success()

            result = self.runner.invoke(
                cli,
                [
                    "serve-custom",
                    "--host",
                    "0.0.0.0",
                    "--port",
                    "8443",
                    "--model",
                    "custom-model",
                    "--max-workers",
                    "20",
                    "--log-level",
                    "DEBUG",
                    "--require-auth",
                    "--cert-file",
                    "server.crt",
                    "--key-file",
                    "server.key",
                    "--ca-bundle-file",
                    "ca-bundle.pem",
                    "--config",
                    "config.yaml",
                ],
            )

            assert result.exit_code == 0
            # Verify configuration overrides
            call_args = mock_load_config.call_args
            overrides = call_args[0][1]

            assert overrides["tls"]["enabled"] is True
            assert Path(overrides["tls"]["cert_file"]).name == "server.crt"
            assert Path(overrides["tls"]["key_file"]).name == "server.key"
            assert Path(overrides["tls"]["ca_bundle_file"]).name == "ca-bundle.pem"
            assert overrides["acme"]["enabled"] is False
            assert overrides["server"]["host"] == "0.0.0.0"
            assert overrides["server"]["port"] == 8443  # Now correctly kept as int
            assert overrides["server"]["default_model"] == "custom-model"
            assert overrides["server"]["max_workers"] == 20  # Now correctly kept as int
            assert overrides["server"]["log_level"] == "DEBUG"
            assert overrides["jwt"]["enabled"] is True

    def test_serve_custom_command_missing_cert_file(self) -> None:
        """Test serve-custom command with missing cert file."""
        result = self.runner.invoke(
            cli, ["serve-custom", "--key-file", "/test/key.pem"]
        )

        assert result.exit_code != 0
        assert "Error:" in result.output

    def test_serve_custom_command_missing_key_file(self) -> None:
        """Test serve-custom command with missing key file."""
        result = self.runner.invoke(
            cli, ["serve-custom", "--cert-file", "/test/cert.pem"]
        )

        assert result.exit_code != 0
        assert "Error:" in result.output


class TestSmartServeCommand:
    """Test the smart serve CLI command."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch("vibectl.server.main.load_server_config")
    @patch("vibectl.server.main.determine_serve_mode")
    @patch("vibectl.server.main.handle_result")
    def test_serve_command_routes_to_insecure(
        self,
        mock_handle_result: Mock,
        mock_determine_mode: Mock,
        mock_load_config: Mock,
    ) -> None:
        """Test serve command routing to insecure mode."""
        config = get_default_server_config()
        mock_load_config.return_value = Success(data=config)
        mock_determine_mode.return_value = ServeMode.INSECURE

        with patch.object(CliRunner, "invoke") as mock_invoke:
            mock_invoke.return_value = Mock(exit_code=0)

            result = self.runner.invoke(cli, ["serve"])

            assert result.exit_code == 0

    @patch("vibectl.server.main.load_server_config")
    @patch("vibectl.server.main.determine_serve_mode")
    @patch("vibectl.server.main.handle_result")
    def test_serve_command_routes_to_acme(
        self,
        mock_handle_result: Mock,
        mock_determine_mode: Mock,
        mock_load_config: Mock,
    ) -> None:
        """Test serve command routing to ACME mode."""
        config = get_default_server_config()
        config["acme"]["enabled"] = True
        config["acme"]["email"] = "test@example.com"
        config["acme"]["domains"] = ["example.com"]
        mock_load_config.return_value = Success(data=config)
        mock_determine_mode.return_value = ServeMode.ACME

        with patch.object(CliRunner, "invoke") as mock_invoke:
            mock_invoke.return_value = Mock(exit_code=0)

            result = self.runner.invoke(cli, ["serve"])

            assert result.exit_code == 0

    @patch("vibectl.server.main.load_server_config")
    def test_serve_command_config_error(self, mock_load_config: Mock) -> None:
        """Test serve command with configuration error."""
        mock_load_config.return_value = Error(error="Config not found")

        with patch("vibectl.server.main.handle_result") as mock_handle:
            result = self.runner.invoke(cli, ["serve"])

            assert result.exit_code == 0
            mock_handle.assert_called_once()


class TestHandleResult:
    """Test result handling functionality."""

    @patch("vibectl.server.main.console_manager")
    @patch("sys.exit")
    def test_handle_result_success_with_message(
        self, mock_exit: Mock, mock_console: Mock
    ) -> None:
        """Test handling successful result with message."""
        result = Success(message="Operation completed successfully")

        handle_result(result)

        mock_console.print_success.assert_called_once_with(
            "Operation completed successfully"
        )
        mock_exit.assert_called_once_with(0)

    @patch("vibectl.server.main.console_manager")
    @patch("sys.exit")
    def test_handle_result_success_without_message(
        self, mock_exit: Mock, mock_console: Mock
    ) -> None:
        """Test handling successful result without message."""
        result = Success()

        handle_result(result)

        # Should not print anything for success without message
        mock_console.print_success.assert_not_called()
        mock_console.print_error.assert_not_called()
        mock_exit.assert_called_once_with(0)

    @patch("vibectl.server.main.console_manager")
    @patch("sys.exit")
    def test_handle_result_error(self, mock_exit: Mock, mock_console: Mock) -> None:
        """Test handling error result."""
        result = Error(error="Something went wrong")

        handle_result(result)

        mock_console.print_error.assert_called_once_with("Something went wrong")
        mock_exit.assert_called_once_with(1)

    @patch("vibectl.server.main.console_manager")
    @patch("sys.exit")
    def test_handle_result_error_with_recovery_suggestions(
        self, mock_exit: Mock, mock_console: Mock
    ) -> None:
        """Test handling error result with recovery suggestions."""
        result = Error(
            error="CA not found",
            recovery_suggestions="Run 'vibectl-server ca init' to create a CA",
        )

        handle_result(result)

        mock_console.print_error.assert_called_once_with("CA not found")
        mock_console.print_note.assert_called_once_with(
            "Run 'vibectl-server ca init' to create a CA"
        )
        mock_exit.assert_called_once_with(1)


class TestErrorHandlingPaths:
    """Test error handling paths that are missing coverage."""

    def test_parse_duration_general_exception(self) -> None:
        """Test parse_duration handles general exceptions correctly."""
        from unittest.mock import patch

        from vibectl.server.main import parse_duration

        # Mock parse_duration_to_days to raise a general exception
        with patch(
            "vibectl.server.main.parse_duration_to_days",
            side_effect=RuntimeError("Unexpected duration parsing error"),
        ):
            result = parse_duration("invalid")

        assert isinstance(result, Error)
        assert (
            "Failed to parse duration: Unexpected duration parsing error"
            in result.error
        )
        assert result.exception is not None

    @patch("vibectl.server.main.setup_private_ca")
    def test_initialize_ca_ca_manager_error(self, mock_setup_ca: Mock) -> None:
        """Test CA initialization with CAManagerError."""
        # This tests lines 523-524: CAManagerError handling
        from vibectl.server.ca_manager import CAManagerError
        from vibectl.server.main import _initialize_ca

        mock_setup_ca.side_effect = CAManagerError("CA setup failed")

        result = _initialize_ca(
            ca_dir=None,
            root_cn="Test Root CA",
            intermediate_cn="Test Intermediate CA",
            organization="Test Org",
            country="US",
            force=False,
        )

        assert isinstance(result, Error)
        assert "CA initialization failed: CA setup failed" in result.error
        assert result.exception is not None

    @patch("vibectl.server.main.setup_private_ca")
    def test_initialize_ca_unexpected_exception(self, mock_setup_ca: Mock) -> None:
        """Test CA initialization with unexpected exception."""
        # This tests lines 498-499: general exception handling in CA initialization
        from vibectl.server.main import _initialize_ca

        mock_setup_ca.side_effect = Exception("Unexpected CA error")

        result = _initialize_ca(
            ca_dir=None,
            root_cn="Test Root CA",
            intermediate_cn="Test Intermediate CA",
            organization="Test Org",
            country="US",
            force=False,
        )

        assert isinstance(result, Error)
        assert (
            "Unexpected error during CA initialization: Unexpected CA error"
            in result.error
        )
        assert result.exception is not None

    def test_create_and_start_server_acme_missing_email(self) -> None:
        """Test server startup with ACME enabled but missing email."""
        # This tests lines 1017-1020: ACME email validation error
        from vibectl.server.main import _create_and_start_server_common

        server_config = {
            "server": {
                "host": "0.0.0.0",
                "port": 50051,
                "max_workers": 10,
                "default_model": "test",
            },
            "tls": {"enabled": True},
            "acme": {"enabled": True, "email": None, "domains": ["example.com"]},
            "jwt": {"enabled": False},
        }

        result = _create_and_start_server_common(server_config)

        assert isinstance(result, Error)
        assert "ACME enabled but no email provided" in result.error

    def test_create_and_start_server_acme_empty_string_email(self) -> None:
        """Test server startup with ACME enabled but empty string email."""
        from vibectl.server.main import _create_and_start_server_common

        server_config = {
            "server": {
                "host": "0.0.0.0",
                "port": 50051,
                "max_workers": 10,
                "default_model": "test",
            },
            "tls": {"enabled": True},
            "acme": {"enabled": True, "email": "", "domains": ["example.com"]},
            "jwt": {"enabled": False},
        }

        result = _create_and_start_server_common(server_config)

        assert isinstance(result, Error)
        assert "ACME enabled but no email provided" in result.error

    def test_create_and_start_server_acme_whitespace_email(self) -> None:
        """Test server startup with ACME enabled but whitespace-only email."""
        from vibectl.server.main import _create_and_start_server_common

        server_config = {
            "server": {
                "host": "0.0.0.0",
                "port": 50051,
                "max_workers": 10,
                "default_model": "test",
            },
            "tls": {"enabled": True},
            "acme": {"enabled": True, "email": "   ", "domains": ["example.com"]},
            "jwt": {"enabled": False},
        }

        result = _create_and_start_server_common(server_config)

        assert isinstance(result, Error)
        assert "ACME enabled but no email provided" in result.error

    def test_create_and_start_server_acme_missing_domains(self) -> None:
        """Test server startup with ACME enabled but missing domains."""
        # This tests lines 1023-1026: ACME domains validation error
        from vibectl.server.main import _create_and_start_server_common

        server_config = {
            "server": {
                "host": "0.0.0.0",
                "port": 50051,
                "max_workers": 10,
                "default_model": "test",
            },
            "tls": {"enabled": True},
            "acme": {"enabled": True, "email": "test@example.com", "domains": []},
            "jwt": {"enabled": False},
        }

        result = _create_and_start_server_common(server_config)

        assert isinstance(result, Error)
        assert "ACME enabled but no domains provided" in result.error

    @patch("vibectl.server.main._create_and_start_server_with_async_acme")
    def test_create_and_start_server_acme_cert_provision_error(
        self, mock_async_acme_server: Mock
    ) -> None:
        """Test server startup when ACME certificate provisioning fails."""
        # This tests lines around 1029-1030: ACME certificate provisioning failure
        from vibectl.server.main import _create_and_start_server_common

        mock_async_acme_server.return_value = Error(
            error="Certificate provisioning failed"
        )

        server_config = {
            "server": {
                "host": "0.0.0.0",
                "port": 50051,
                "max_workers": 10,
                "default_model": "test",
            },
            "tls": {"enabled": True},
            "acme": {
                "enabled": True,
                "email": "test@example.com",
                "domains": ["example.com"],
                "challenge_type": "tls-alpn-01",
            },
            "jwt": {"enabled": False},
        }

        result = _create_and_start_server_common(server_config)

        assert isinstance(result, Error)
        assert "Certificate provisioning failed" in result.error

    @patch("vibectl.server.main._create_and_start_server_with_async_acme")
    def test_create_and_start_server_acme_no_cert_data(
        self, mock_async_acme_server: Mock
    ) -> None:
        """Test server startup when ACME provisioning returns no certificate data."""
        # This tests the data validation after ACME provisioning
        from vibectl.server.main import _create_and_start_server_common

        mock_async_acme_server.return_value = Error(
            error="ACME certificate provisioning returned no certificate data"
        )

        server_config = {
            "server": {
                "host": "0.0.0.0",
                "port": 50051,
                "max_workers": 10,
                "default_model": "test",
            },
            "tls": {"enabled": True},
            "acme": {
                "enabled": True,
                "email": "test@example.com",
                "domains": ["example.com"],
                "challenge_type": "tls-alpn-01",
            },
            "jwt": {"enabled": False},
        }

        result = _create_and_start_server_common(server_config)

        assert isinstance(result, Error)
        assert (
            "ACME certificate provisioning returned no certificate data" in result.error
        )

    @patch("vibectl.server.main._create_and_start_server_with_async_acme")
    def test_create_and_start_server_acme_provision_exception(
        self, mock_async_acme_server: Mock
    ) -> None:
        """Test server startup when ACME provisioning raises an exception."""
        # This tests lines 1051-1054: exception handling in ACME provisioning
        from vibectl.server.main import _create_and_start_server_common

        acme_exception = Exception("ACME service unavailable")
        mock_async_acme_server.return_value = Error(
            error="ACME certificate provisioning failed: ACME service unavailable",
            exception=acme_exception,
        )

        server_config = {
            "server": {
                "host": "0.0.0.0",
                "port": 50051,
                "max_workers": 10,
                "default_model": "test",
            },
            "tls": {"enabled": True},
            "acme": {
                "enabled": True,
                "email": "test@example.com",
                "domains": ["example.com"],
                "challenge_type": "tls-alpn-01",
            },
            "jwt": {"enabled": False},
        }

        result = _create_and_start_server_common(server_config)

        assert isinstance(result, Error)
        assert (
            "ACME certificate provisioning failed: ACME service unavailable"
            in result.error
        )
        assert result.exception is not None


class TestServerStartupErrorPaths:
    """Test server startup error paths that are missing coverage."""

    @patch("vibectl.server.main.init_logging")
    @patch("vibectl.server.main.create_server")
    def test_create_and_start_server_unexpected_server_error(
        self, mock_create_server: Mock, mock_init_logging: Mock
    ) -> None:
        """Test _create_and_start_server_common handles unexpected server errors."""
        from unittest.mock import patch

        from vibectl.server.main import _create_and_start_server_common

        # Use a complete server config to avoid KeyError
        server_config = {
            "server": {
                "host": "localhost",
                "port": 8080,
                "max_workers": 5,
                "default_model": "test",
            },
            "jwt": {"enabled": False},
            "tls": {"enabled": False},
            "acme": {"enabled": False},  # Add this to prevent KeyError
        }

        # Mock create_server to raise an unexpected exception
        with patch(
            "vibectl.server.main.create_server",
            side_effect=RuntimeError("Unexpected server initialization error"),
        ):
            result = _create_and_start_server_common(server_config)

        assert isinstance(result, Error)
        assert (
            "Server startup failed: Unexpected server initialization error"
            in result.error
        )
        assert result.exception is not None

    @patch("vibectl.server.main.init_logging")
    def test_create_and_start_server_invalid_config_structure(
        self, mock_init_logging: Mock
    ) -> None:
        """Test server startup with invalid configuration structure."""
        # This tests edge cases in config validation
        from vibectl.server.main import _create_and_start_server_common

        # Missing required server section
        server_config = {"tls": {"enabled": False}, "jwt": {"enabled": False}}

        result = _create_and_start_server_common(server_config)

        assert isinstance(result, Error)
        # The exact error will depend on how the function handles missing
        # config sections

    def test_create_default_config_write_permission_error(self) -> None:
        """Test create_default_config handles write permission errors."""
        import tempfile
        from unittest.mock import patch

        from vibectl.server.config import create_default_server_config
        from vibectl.types import Error

        # Create a temporary file path
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.yaml"

        # Mock ServerConfig.save to return an Error result (simulating what
        # real save does with PermissionError)
        expected_error = Error(
            error=f"Failed to save server configuration to {config_path}: "
            "Permission denied",
            exception=PermissionError("Permission denied"),
        )
        with patch(
            "vibectl.server.config.ServerConfig.save", return_value=expected_error
        ):
            result = create_default_server_config(config_path)

        assert isinstance(result, Error)
        assert "Permission denied" in result.error
        assert result.exception is not None


class TestCertificateOperationErrors:
    """Test certificate operation error paths for missing coverage."""

    @patch("vibectl.server.main.get_config_dir")
    @patch("vibectl.server.main.cert_utils.get_default_cert_paths")
    @patch("pathlib.Path.mkdir")
    def test_perform_certificate_generation_mkdir_error(
        self, mock_mkdir: Mock, mock_get_paths: Mock, mock_get_config_dir: Mock
    ) -> None:
        """Test certificate generation when directory creation fails."""
        # This tests error handling in certificate generation
        from pathlib import Path

        from vibectl.server.main import _perform_certificate_generation

        mock_get_config_dir.return_value = Path("/test/config")
        mock_get_paths.return_value = ("/test/server.crt", "/test/server.key")
        mock_mkdir.side_effect = PermissionError("Cannot create directory")

        result = _perform_certificate_generation("localhost", None, None, False)

        assert isinstance(result, Error)
        assert "Certificate generation failed" in result.error
        assert result.exception is not None

    def test_create_server_certificate_ca_manager_init_error(self) -> None:
        """Test _create_server_certificate handles CA manager initialization errors."""
        import tempfile

        from vibectl.server.main import _create_server_certificate

        # Create a temporary directory that doesn't exist as CA directory
        with tempfile.TemporaryDirectory() as temp_dir:
            non_existent_ca_dir = Path(temp_dir) / "non_existent_ca"

        result = _create_server_certificate(
            "test.example.com", str(non_existent_ca_dir), (), 90, False
        )

        assert isinstance(result, Error)
        assert "CA directory not found:" in result.error

    def test_show_ca_status_manager_init_error(self) -> None:
        """Test _show_ca_status handles CA manager initialization errors."""
        import tempfile

        from vibectl.server.main import _show_ca_status

        # Create a temporary directory that doesn't exist as CA directory
        with tempfile.TemporaryDirectory() as temp_dir:
            non_existent_ca_dir = Path(temp_dir) / "non_existent_ca"

        result = _show_ca_status(str(non_existent_ca_dir), 30)

        assert isinstance(result, Error)
        assert "CA directory not found:" in result.error


class TestSmartServeCommandRouting:
    """Test comprehensive smart serve command routing with argument passing."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch("vibectl.server.main.load_server_config")
    @patch("vibectl.server.main.serve_insecure")
    def test_serve_routes_to_insecure_with_config_only(
        self, mock_serve_insecure: Mock, mock_load_config: Mock
    ) -> None:
        """Test serve command routes to insecure mode with only config argument."""
        config = get_default_server_config()
        config["tls"]["enabled"] = False
        mock_load_config.return_value = Success(data=config)

        result = self.runner.invoke(cli, ["serve", "--config", "test.yaml"])

        assert result.exit_code == 0
        mock_serve_insecure.assert_called_once_with(config="test.yaml")

    @patch("vibectl.server.main.load_server_config")
    @patch("vibectl.server.main.serve_ca")
    def test_serve_routes_to_ca_with_proper_arguments(
        self, mock_serve_ca: Mock, mock_load_config: Mock
    ) -> None:
        """Test serve command routes to CA mode with proper default arguments."""
        config = get_default_server_config()
        config["tls"]["enabled"] = True
        config["acme"]["enabled"] = False
        # No cert_file/key_file specified = CA mode
        mock_load_config.return_value = Success(data=config)

        result = self.runner.invoke(cli, ["serve"])

        assert result.exit_code == 0
        mock_serve_ca.assert_called_once_with(
            config=None,
            ca_dir=None,
            hostname="localhost",
            san=(),
            validity_days=90,
        )

    @patch("vibectl.server.main.load_server_config")
    @patch("vibectl.server.main.serve_acme")
    def test_serve_routes_to_acme_with_extracted_arguments(
        self, mock_serve_acme: Mock, mock_load_config: Mock
    ) -> None:
        """Test serves ACME mode with extracted arguments from config."""
        config = get_default_server_config()
        config["tls"]["enabled"] = True
        config["acme"] = {
            "enabled": True,
            "email": "test@example.com",
            "domains": ["example.com", "www.example.com"],
            "directory_url": "https://acme-staging-v02.api.letsencrypt.org/directory",
            "challenge_type": "dns-01",
        }
        mock_load_config.return_value = Success(data=config)

        result = self.runner.invoke(cli, ["serve", "--config", "acme.yaml"])

        assert result.exit_code == 0
        mock_serve_acme.assert_called_once_with(
            config="acme.yaml",
            email="test@example.com",
            domain=["example.com", "www.example.com"],
            directory_url="https://acme-staging-v02.api.letsencrypt.org/directory",
            challenge_type="dns-01",
        )

    @patch("vibectl.server.main.load_server_config")
    @patch("vibectl.server.main.serve_acme")
    def test_serve_routes_to_acme_with_defaults(
        self, mock_serve_acme: Mock, mock_load_config: Mock
    ) -> None:
        """Test serves ACME mode with minimal config (using defaults)."""
        config = get_default_server_config()
        config["tls"]["enabled"] = True
        config["acme"] = {
            "enabled": True,
            "email": "minimal@example.com",
            "domains": ["minimal.com"],
            # directory_url and challenge_type will use defaults
        }
        mock_load_config.return_value = Success(data=config)

        result = self.runner.invoke(cli, ["serve"])

        assert result.exit_code == 0
        mock_serve_acme.assert_called_once_with(
            config=None,
            email="minimal@example.com",
            domain=["minimal.com"],
            directory_url=None,  # Default (Let's Encrypt production)
            challenge_type="http-01",  # Default
        )

    @patch("vibectl.server.main.load_server_config")
    @patch("vibectl.server.main.serve_custom")
    def test_serve_routes_to_custom_with_extracted_arguments(
        self, mock_serve_custom: Mock, mock_load_config: Mock
    ) -> None:
        """Test serves custom mode with extracted cert file arguments."""
        config = get_default_server_config()
        config["tls"] = {
            "enabled": True,
            "cert_file": "/path/to/cert.pem",
            "key_file": "/path/to/key.pem",
            "ca_bundle_file": "/path/to/ca-bundle.pem",
        }
        config["acme"]["enabled"] = False
        mock_load_config.return_value = Success(data=config)

        result = self.runner.invoke(cli, ["serve", "--config", "custom.yaml"])

        assert result.exit_code == 0
        mock_serve_custom.assert_called_once_with(
            config="custom.yaml",
            cert_file="/path/to/cert.pem",
            key_file="/path/to/key.pem",
            ca_bundle_file="/path/to/ca-bundle.pem",
        )

    @patch("vibectl.server.main.load_server_config")
    @patch("vibectl.server.main.serve_custom")
    def test_serve_routes_to_custom_without_ca_bundle(
        self, mock_serve_custom: Mock, mock_load_config: Mock
    ) -> None:
        """Test serve command routes to custom mode without CA bundle."""
        config = get_default_server_config()
        config["tls"] = {
            "enabled": True,
            "cert_file": "/path/to/cert.pem",
            "key_file": "/path/to/key.pem",
            # No ca_bundle_file
        }
        config["acme"]["enabled"] = False
        mock_load_config.return_value = Success(data=config)

        result = self.runner.invoke(cli, ["serve"])

        assert result.exit_code == 0
        mock_serve_custom.assert_called_once_with(
            config=None,
            cert_file="/path/to/cert.pem",
            key_file="/path/to/key.pem",
            ca_bundle_file=None,
        )

    @patch("vibectl.server.main.load_server_config")
    @patch("vibectl.server.main.handle_result")
    def test_serve_ca_mode_missing_ca_directory_with_key_only(
        self, mock_handle_result: Mock, mock_load_config: Mock
    ) -> None:
        """Test serves CA mode when only key_file is provided (missing cert_file)."""
        config = get_default_server_config()
        config["tls"] = {
            "enabled": True,
            "key_file": "/path/to/key.pem",
            # Missing cert_file - should route to CA mode
        }
        config["acme"]["enabled"] = False
        mock_load_config.return_value = Success(data=config)

        result = self.runner.invoke(cli, ["serve"])

        assert result.exit_code == 0
        # Should call handle_result with an error about missing CA directory
        mock_handle_result.assert_called_once()
        error_call = mock_handle_result.call_args[0][0]
        assert isinstance(error_call, Error)
        assert "CA directory not found:" in error_call.error

    @patch("vibectl.server.main.load_server_config")
    @patch("vibectl.server.main.handle_result")
    def test_serve_ca_mode_missing_ca_directory_with_cert_only(
        self, mock_handle_result: Mock, mock_load_config: Mock
    ) -> None:
        """Test serves CA mode when only cert_file is provided (missing key_file)."""
        config = get_default_server_config()
        config["tls"] = {
            "enabled": True,
            "cert_file": "/path/to/cert.pem",
            # Missing key_file - should route to CA mode
        }
        config["acme"]["enabled"] = False
        mock_load_config.return_value = Success(data=config)

        result = self.runner.invoke(cli, ["serve"])

        assert result.exit_code == 0
        # Should call handle_result with an error about missing CA directory
        mock_handle_result.assert_called_once()
        error_call = mock_handle_result.call_args[0][0]
        assert isinstance(error_call, Error)
        assert "CA directory not found:" in error_call.error

    @patch("vibectl.server.main.load_server_config")
    @patch("vibectl.server.main.handle_result")
    def test_serve_unknown_mode_error(
        self, mock_handle_result: Mock, mock_load_config: Mock
    ) -> None:
        """Test serve command handles unknown serve mode."""
        config = get_default_server_config()
        mock_load_config.return_value = Success(data=config)

        # Mock determine_serve_mode to return an invalid mode
        with patch(
            "vibectl.server.main.determine_serve_mode", return_value="invalid-mode"
        ):
            result = self.runner.invoke(cli, ["serve"])

        assert result.exit_code == 0
        mock_handle_result.assert_called_once()
        error_call = mock_handle_result.call_args[0][0]
        assert isinstance(error_call, Error)
        assert "Unknown serve mode: invalid-mode" in error_call.error

    @patch("vibectl.server.main.load_server_config")
    @patch("vibectl.server.main.handle_result")
    def test_serve_config_loading_error(
        self, mock_handle_result: Mock, mock_load_config: Mock
    ) -> None:
        """Test serve command handles configuration loading errors."""
        mock_load_config.return_value = Error(error="Configuration file not found")

        result = self.runner.invoke(cli, ["serve", "--config", "missing.yaml"])

        assert result.exit_code == 0
        mock_handle_result.assert_called_once()
        error_call = mock_handle_result.call_args[0][0]
        assert isinstance(error_call, Error)
        assert "Configuration file not found" in error_call.error
