"""
Tests for additional functionality in vibectl.server.main module.

This module tests remaining functionality including serve-custom command,
smart serve command, server creation, and other utility functions.
"""

from pathlib import Path
from unittest.mock import Mock, patch

from click.testing import CliRunner

from vibectl.server.main import (
    _create_and_start_server_common,
    _load_and_validate_config,
    _perform_certificate_generation,
    cli,
    get_default_server_config,
    handle_result,
)
from vibectl.types import Error, ServeMode, Success


class TestServerCreationAndStartup:
    """Test server creation and startup functionality."""

    @patch("vibectl.server.main.init_logging")
    @patch("vibectl.server.main._provision_acme_certificates")
    @patch("vibectl.server.main.create_server")
    def test_create_and_start_server_common_acme_enabled(
        self,
        mock_create_server: Mock,
        mock_provision_acme: Mock,
        mock_init_logging: Mock,
    ) -> None:
        """Test server creation with ACME certificates enabled."""
        server_config = {
            "server": {
                "host": "0.0.0.0",
                "port": 443,
                "default_model": "test-model",
                "max_workers": 10,
                "log_level": "INFO",
            },
            "tls": {"enabled": True, "cert_file": None, "key_file": None},
            "acme": {
                "enabled": True,
                "email": "test@example.com",
                "domains": ["example.com"],
            },
            "jwt": {"enabled": False},
        }

        # Mock ACME certificate provisioning
        mock_provision_acme.return_value = Success(
            data=("/path/to/cert.pem", "/path/to/key.pem")
        )

        # Mock server creation and startup
        mock_server = Mock()
        mock_create_server.return_value = mock_server
        mock_server.serve_forever.return_value = None

        result = _create_and_start_server_common(server_config)

        assert isinstance(result, Success)
        mock_provision_acme.assert_called_once_with(server_config)
        mock_create_server.assert_called_once_with(
            host="0.0.0.0",
            port=443,
            default_model="test-model",
            max_workers=10,
            require_auth=False,
            use_tls=True,
            cert_file="/path/to/cert.pem",
            key_file="/path/to/key.pem",
        )
        mock_server.serve_forever.assert_called_once()

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
    @patch("vibectl.server.main._provision_acme_certificates")
    def test_create_and_start_server_common_acme_error(
        self, mock_provision_acme: Mock, mock_init_logging: Mock
    ) -> None:
        """Test server creation when ACME provisioning fails."""
        server_config = {
            "server": {
                "host": "0.0.0.0",
                "port": 443,
                "default_model": "test",
                "max_workers": 10,
                "log_level": "INFO",
            },
            "tls": {"enabled": True},
            "acme": {
                "enabled": True,
                "email": "test@example.com",
                "domains": ["example.com"],
            },
            "jwt": {"enabled": False},
        }

        mock_provision_acme.return_value = Error(error="ACME provisioning failed")

        result = _create_and_start_server_common(server_config)

        assert isinstance(result, Error)
        assert "ACME provisioning failed" in result.error

    @patch("vibectl.server.main.init_logging")
    @patch("vibectl.server.main._provision_acme_certificates")
    def test_create_and_start_server_common_acme_none_data(
        self, mock_provision_acme: Mock, mock_init_logging: Mock
    ) -> None:
        """Test server creation when ACME provisioning returns None data."""
        server_config = {
            "server": {
                "host": "0.0.0.0",
                "port": 443,
                "default_model": "test",
                "max_workers": 10,
                "log_level": "INFO",
            },
            "tls": {"enabled": True},
            "acme": {
                "enabled": True,
                "email": "test@example.com",
                "domains": ["example.com"],
            },
            "jwt": {"enabled": False},
        }

        # Mock ACME returning success but with None data
        mock_provision_acme.return_value = Success(data=None)

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
    @patch("vibectl.server.main.validate_config")
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

    @patch("vibectl.server.main.load_server_config")
    def test_load_and_validate_config_load_error(self, mock_load_config: Mock) -> None:
        """Test configuration loading when loading fails."""
        mock_load_config.return_value = Error(error="Failed to load config")

        result = _load_and_validate_config(
            config_path=Path("/test/config.yaml"), overrides={}
        )

        assert isinstance(result, Error)
        assert "Failed to load config" in result.error

    @patch("vibectl.server.main.load_server_config")
    @patch("vibectl.server.main.validate_config")
    def test_load_and_validate_config_validation_error(
        self, mock_validate: Mock, mock_load_config: Mock
    ) -> None:
        """Test configuration loading when validation fails."""
        config = get_default_server_config()
        mock_load_config.return_value = Success(data=config)
        mock_validate.return_value = Error(error="Invalid port number")

        result = _load_and_validate_config(config_path=None, overrides={})

        assert isinstance(result, Error)
        assert "Invalid port number" in result.error

    @patch("vibectl.server.main.load_server_config")
    @patch("vibectl.server.main.validate_config")
    def test_load_and_validate_config_with_overrides(
        self, mock_validate: Mock, mock_load_config: Mock
    ) -> None:
        """Test configuration loading with complex overrides."""
        config = get_default_server_config()
        mock_load_config.return_value = Success(data=config)
        mock_validate.return_value = Success()

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
    def test_perform_certificate_generation_error(self, mock_ensure_cert: Mock) -> None:
        """Test certificate generation when cert creation fails."""
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
    def test_perform_certificate_generation_exception(
        self, mock_ensure_cert: Mock
    ) -> None:
        """Test certificate generation with exception."""
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
