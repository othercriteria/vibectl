"""
Tests for vibectl.server.main module.

This module tests all functionality in the server main entry point,
including configuration management, CLI commands, and utility functions.
"""

import os
import signal
import tempfile
from pathlib import Path
from unittest.mock import Mock, mock_open, patch

from click.testing import CliRunner

from vibectl.server.main import (
    cli,
    create_default_config,
    generate_certs,
    generate_token,
    get_default_server_config,
    get_server_config_path,
    init_config,
    load_server_config,
    main,
    parse_duration,
    serve,
    signal_handler,
    validate_config,
)
from vibectl.types import Error, Success


class TestConfigurationManagement:
    """Test configuration-related functions."""

    @patch("vibectl.server.main.get_config_dir")
    def test_get_server_config_path(self, mock_get_config_dir: Mock) -> None:
        """Test getting server configuration path."""
        mock_config_dir = Path("/mock/config")
        mock_get_config_dir.return_value = mock_config_dir

        result = get_server_config_path()

        mock_get_config_dir.assert_called_once_with("server")
        assert result == mock_config_dir / "config.yaml"

    def test_get_default_server_config(self) -> None:
        """Test get_default_server_config returns correct structure."""
        config = get_default_server_config()

        # Check structure and required keys
        assert isinstance(config, dict)
        assert "server" in config
        assert "tls" in config
        assert "jwt" in config

        # Check server section
        server_config = config["server"]
        assert server_config["host"] == "0.0.0.0"
        assert server_config["port"] == 50051
        assert server_config["default_model"] == "anthropic/claude-3-7-sonnet-latest"
        assert server_config["max_workers"] == 10
        assert server_config["log_level"] == "INFO"

        # Check tls section
        tls_config = config["tls"]
        assert tls_config["enabled"] is False
        assert tls_config["cert_file"] is None
        assert tls_config["key_file"] is None
        assert tls_config["ca_bundle_file"] is None

        # Check jwt section
        jwt_config = config["jwt"]
        assert jwt_config["enabled"] is False
        assert jwt_config["secret_key"] is None
        assert jwt_config["secret_key_file"] is None
        assert jwt_config["algorithm"] == "HS256"
        assert jwt_config["issuer"] == "vibectl-server"
        assert jwt_config["expiration_days"] == 30

    @patch("vibectl.server.main.get_server_config_path")
    @patch("vibectl.server.main.load_yaml_config")
    def test_load_server_config_file_exists(
        self, mock_load_yaml: Mock, mock_get_path: Mock
    ) -> None:
        """Test loading server config from existing file."""
        mock_path = Mock()
        mock_get_path.return_value = mock_path

        # Mock the deep-merged result that load_yaml_config returns
        merged_config = {
            "server": {
                "host": "custom.host",  # From user config
                "port": 8080,  # From user config
                "default_model": "anthropic/claude-3-7-sonnet-latest",  # From defaults
                "max_workers": 10,  # From defaults
                "log_level": "INFO",  # From defaults
            },
            "tls": {
                "enabled": True,  # From user config
                "cert_file": "/path/to/cert.pem",  # From user config
                "key_file": "/path/to/key.pem",  # From user config
                "ca_bundle_file": None,  # From defaults
            },
            "jwt": {
                "enabled": True,  # From user config
                "secret_key": "custom_secret",  # From user config
                "secret_key_file": None,  # From defaults
                "algorithm": "HS256",  # From defaults
                "issuer": "vibectl-server",  # From defaults
                "expiration_days": 30,  # From defaults
            },
        }

        mock_load_yaml.return_value = merged_config
        mock_path.exists.return_value = True

        # Load the configuration
        result = load_server_config()

        # Verify the result is Success and configuration matches
        assert isinstance(result, Success)
        mock_load_yaml.assert_called_once_with(mock_path, get_default_server_config())
        config_data = result.data
        assert isinstance(config_data, dict)
        assert config_data["server"]["host"] == "custom.host"
        assert config_data["server"]["port"] == 8080

    @patch("vibectl.server.main.get_server_config_path")
    @patch("vibectl.server.main.load_yaml_config")
    def test_load_server_config_file_not_exists(
        self, mock_load_yaml: Mock, mock_get_path: Mock
    ) -> None:
        """Test loading server config when file doesn't exist."""
        mock_path = Mock()
        mock_get_path.return_value = mock_path

        # When file doesn't exist, load_yaml_config should return defaults
        expected_config = get_default_server_config()
        mock_load_yaml.return_value = expected_config

        result = load_server_config()

        assert isinstance(result, Success)
        mock_load_yaml.assert_called_once_with(mock_path, get_default_server_config())
        config_data = result.data
        assert isinstance(config_data, dict)
        assert config_data["server"]["host"] == "0.0.0.0"
        assert config_data["server"]["port"] == 50051

    @patch("vibectl.server.main.load_yaml_config")
    def test_load_server_config_with_explicit_path(self, mock_load_yaml: Mock) -> None:
        """Test loading server config with explicit path."""
        explicit_path = Path("/explicit/config.yaml")

        # Set up expected config with explicit host in structured format
        expected_config = get_default_server_config()
        expected_config["server"]["host"] = "explicit.host"
        mock_load_yaml.return_value = expected_config

        result = load_server_config(explicit_path)

        assert isinstance(result, Success)
        mock_load_yaml.assert_called_once_with(
            explicit_path, get_default_server_config()
        )
        config_data = result.data
        assert isinstance(config_data, dict)
        assert config_data["server"]["host"] == "explicit.host"

    @patch("vibectl.server.main.get_server_config_path")
    @patch("pathlib.Path.exists")
    def test_load_server_config_yaml_error(
        self, mock_exists: Mock, mock_get_path: Mock
    ) -> None:
        """Test loading server config with YAML error."""
        config_path = Path("/mock/config.yaml")
        mock_get_path.return_value = config_path
        mock_exists.return_value = True

        with (
            patch("builtins.open", mock_open(read_data="invalid: yaml: content")),
            patch(
                "vibectl.config_utils.load_yaml_config",
                side_effect=ValueError("Invalid YAML"),
            ),
        ):
            result = load_server_config()

        # Should return Success with defaults on error
        assert isinstance(result, Success)
        expected = get_default_server_config()
        assert result.data == expected

    @patch("vibectl.server.main.get_server_config_path")
    @patch("pathlib.Path.exists")
    def test_load_server_config_empty_file(
        self, mock_exists: Mock, mock_get_path: Mock
    ) -> None:
        """Test loading server config with empty file."""
        config_path = Path("/mock/config.yaml")
        mock_get_path.return_value = config_path
        mock_exists.return_value = True

        with (
            patch("builtins.open", mock_open(read_data="")),
            patch(
                "vibectl.config_utils.load_yaml_config",
                return_value=get_default_server_config(),
            ),
        ):
            result = load_server_config()

        # Should return Success with defaults when file is empty
        assert isinstance(result, Success)
        expected = get_default_server_config()
        assert result.data == expected

    @patch("vibectl.server.main.get_server_config_path")
    @patch("pathlib.Path.mkdir")
    @patch("pathlib.Path.open")
    def test_create_default_config(
        self, mock_path_open: Mock, mock_mkdir: Mock, mock_get_path: Mock
    ) -> None:
        """Test creating default configuration file."""
        config_path = Path("/mock/config.yaml")
        mock_get_path.return_value = config_path

        # Mock the file opening and writing
        mock_file = mock_open()
        mock_path_open.return_value = mock_file.return_value

        result = create_default_config()

        assert isinstance(result, Success)
        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
        # Verify open was called with "w" mode
        mock_path_open.assert_called_once_with("w")

    @patch("pathlib.Path.mkdir")
    @patch("pathlib.Path.open")
    def test_create_default_config_with_explicit_path(
        self, mock_path_open: Mock, mock_mkdir: Mock
    ) -> None:
        """Test creating default config with explicit path."""
        explicit_path = Path("/explicit/config.yaml")

        # Mock the file opening and writing
        mock_file = mock_open()
        mock_path_open.return_value = mock_file.return_value

        result = create_default_config(explicit_path)

        assert isinstance(result, Success)
        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
        # Verify open was called with "w" mode
        mock_path_open.assert_called_once_with("w")

    @patch("vibectl.server.main.get_server_config_path")
    @patch("pathlib.Path.mkdir")
    @patch("pathlib.Path.open")
    def test_create_default_config_write_error(
        self, mock_open: Mock, mock_mkdir: Mock, mock_get_path: Mock
    ) -> None:
        """Test creating default config with write error."""
        config_path = Path("/mock/config.yaml")
        mock_get_path.return_value = config_path
        mock_open.side_effect = OSError("Permission denied")

        result = create_default_config()

        assert isinstance(result, Error)
        assert "Permission denied" in result.error


class TestUtilityFunctions:
    """Test utility functions."""

    def test_parse_duration_days_only(self) -> None:
        """Test parsing duration with just number (days)."""
        result = parse_duration("30")
        assert isinstance(result, Success)
        assert result.data == 30

        result = parse_duration("  30  ")  # Test whitespace
        assert isinstance(result, Success)
        assert result.data == 30

    def test_parse_duration_with_suffixes(self) -> None:
        """Test parsing duration with various suffixes."""
        result = parse_duration("30d")
        assert isinstance(result, Success)
        assert result.data == 30

        result = parse_duration("6m")
        assert isinstance(result, Success)
        assert result.data == 180  # 6 * 30

        result = parse_duration("2y")
        assert isinstance(result, Success)
        assert result.data == 730  # 2 * 365

    def test_parse_duration_case_insensitive(self) -> None:
        """Test parsing duration is case insensitive."""
        result = parse_duration("30D")
        assert isinstance(result, Success)
        assert result.data == 30

        result = parse_duration("6M")
        assert isinstance(result, Success)
        assert result.data == 180

        result = parse_duration("2Y")
        assert isinstance(result, Success)
        assert result.data == 730

    def test_parse_duration_invalid_format(self) -> None:
        """Test parsing duration with invalid formats."""
        result = parse_duration("abc")
        assert isinstance(result, Error)

        result = parse_duration("30x")  # Invalid suffix
        assert isinstance(result, Error)

        result = parse_duration("d")  # No number
        assert isinstance(result, Error)

    def test_parse_duration_invalid_number(self) -> None:
        """Test parsing duration with invalid number."""
        result = parse_duration("abc d")
        assert isinstance(result, Error)

    def test_validate_config_valid(self) -> None:
        """Test config validation with valid parameters."""
        result = validate_config("localhost", 8080, 5)
        assert isinstance(result, Success)

    def test_validate_config_invalid_port(self) -> None:
        """Test config validation with invalid port."""
        result = validate_config("localhost", 0, 5)
        assert isinstance(result, Error)

        result = validate_config("localhost", 65536, 5)
        assert isinstance(result, Error)

    def test_validate_config_invalid_workers(self) -> None:
        """Test config validation with invalid max workers."""
        result = validate_config("localhost", 8080, 0)
        assert isinstance(result, Error)

    def test_signal_handler(self) -> None:
        """Test signal handler sets shutdown event."""
        # Test that signal handler sets global variable
        import vibectl.server.main as main_module

        # Reset shutdown event
        main_module.shutdown_event = False

        # Call signal handler
        signal_handler(signal.SIGTERM, None)

        # Check that shutdown event is set
        assert main_module.shutdown_event is True


class TestCLICommands:
    """Test CLI command functionality."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch("vibectl.server.main.load_server_config")
    @patch("vibectl.server.main.validate_config")
    @patch("vibectl.server.main.create_server")
    def test_serve_command_default(
        self,
        mock_create_server: Mock,
        mock_validate: Mock,
        mock_load_config: Mock,
    ) -> None:
        """Test serve command with default configuration."""
        mock_config = {
            "server": {
                "host": "0.0.0.0",
                "port": 50051,
                "default_model": "test-model",
                "max_workers": 10,
                "log_level": "INFO",
            },
            "tls": {
                "enabled": False,
                "cert_file": None,
                "key_file": None,
                "ca_bundle_file": None,
            },
            "jwt": {
                "enabled": False,
                "secret_key": None,
                "secret_key_file": None,
                "algorithm": "HS256",
                "issuer": "vibectl-server",
                "expiration_days": 30,
            },
        }

        mock_load_config.return_value = Success(data=mock_config)
        mock_validate.return_value = Success()
        mock_server = Mock()
        mock_create_server.return_value = mock_server

        # Execute the command
        result = self.runner.invoke(serve)

        # Verify the command succeeded
        assert result.exit_code == 0

        # Verify configuration validation
        mock_validate.assert_called_once_with("0.0.0.0", 50051, 10)

        # Verify server creation
        mock_create_server.assert_called_once_with(
            host="0.0.0.0",
            port=50051,
            default_model="test-model",
            max_workers=10,
            require_auth=False,
            use_tls=False,
            cert_file=None,
            key_file=None,
        )

        # Verify server.serve_forever was called
        mock_server.serve_forever.assert_called_once()

    @patch("vibectl.server.main.load_server_config")
    @patch("vibectl.server.main.validate_config")
    @patch("vibectl.server.main.create_server")
    def test_serve_command_with_overrides(
        self,
        mock_create_server: Mock,
        mock_validate: Mock,
        mock_load_config: Mock,
    ) -> None:
        """Test serve command with CLI option overrides."""
        mock_config = {
            "server": {
                "host": "0.0.0.0",
                "port": 50051,
                "default_model": "test-model",
                "max_workers": 10,
                "log_level": "INFO",
            },
            "tls": {
                "enabled": False,
                "cert_file": None,
                "key_file": None,
                "ca_bundle_file": None,
            },
            "jwt": {
                "enabled": False,
                "secret_key": None,
                "secret_key_file": None,
                "algorithm": "HS256",
                "issuer": "vibectl-server",
                "expiration_days": 30,
            },
        }

        mock_load_config.return_value = Success(data=mock_config)
        mock_validate.return_value = Success()
        mock_server = Mock()
        mock_create_server.return_value = mock_server

        # Execute the command with overrides
        runner = CliRunner()
        result = runner.invoke(
            serve, ["--host", "127.0.0.1", "--port", "8080", "--require-auth", "--tls"]
        )

        # Verify the command succeeded
        assert result.exit_code == 0

        # Verify server creation with overridden values
        mock_create_server.assert_called_once_with(
            host="127.0.0.1",  # Overridden
            port=8080,  # Overridden
            default_model="test-model",
            max_workers=10,
            require_auth=True,  # Overridden
            use_tls=True,  # Overridden
            cert_file=None,
            key_file=None,
        )

    @patch("vibectl.server.main.load_server_config")
    @patch("vibectl.server.main.validate_config")
    @patch("vibectl.server.main.create_server")
    def test_serve_command_validation_error(
        self,
        mock_create_server: Mock,
        mock_validate: Mock,
        mock_load_config: Mock,
    ) -> None:
        """Test serve command with validation error."""
        mock_config = get_default_server_config()
        mock_load_config.return_value = Success(data=mock_config)
        mock_validate.return_value = Error("Invalid port")

        result = self.runner.invoke(serve)

        assert result.exit_code == 1
        # Error is printed to output in CLI
        assert "Error: Invalid port" in result.output

    @patch("vibectl.server.main.load_server_config")
    @patch("vibectl.server.main.validate_config")
    @patch("vibectl.server.main.create_server")
    def test_serve_command_keyboard_interrupt(
        self,
        mock_create_server: Mock,
        mock_validate: Mock,
        mock_load_config: Mock,
    ) -> None:
        """Test serve command with keyboard interrupt."""
        mock_config = get_default_server_config()
        mock_load_config.return_value = Success(data=mock_config)
        mock_validate.return_value = Success()

        mock_server = Mock()
        mock_server.serve_forever.side_effect = KeyboardInterrupt()
        mock_create_server.return_value = mock_server

        result = self.runner.invoke(serve)

        assert result.exit_code == 0  # Should handle gracefully

    @patch("vibectl.server.main.parse_duration")
    @patch("vibectl.server.main.load_config_with_generation")
    @patch("vibectl.server.main.JWTAuthManager")
    def test_generate_token_command(
        self,
        mock_jwt_manager_class: Mock,
        mock_load_config: Mock,
        mock_parse_duration: Mock,
    ) -> None:
        """Test generate-token command with default options."""
        # Setup mocks
        mock_parse_duration.return_value = Success(data=30)
        mock_config = Mock()
        mock_load_config.return_value = mock_config
        mock_jwt_manager = Mock()
        mock_jwt_manager_class.return_value = mock_jwt_manager
        mock_jwt_manager.generate_token.return_value = "mock-jwt-token"

        # Run command
        result = self.runner.invoke(generate_token, ["test-subject"])

        # Verify output
        assert result.exit_code == 0
        assert "mock-jwt-token" in result.output

        # Verify function calls
        mock_parse_duration.assert_called_once_with("1y")
        mock_load_config.assert_called_once_with(persist_generated_key=True)
        mock_jwt_manager_class.assert_called_once_with(mock_config)
        mock_jwt_manager.generate_token.assert_called_once_with(
            subject="test-subject", expiration_days=30
        )

    @patch("vibectl.server.main.parse_duration")
    @patch("vibectl.server.main.load_config_with_generation")
    @patch("vibectl.server.main.JWTAuthManager")
    def test_generate_token_with_output_file(
        self,
        mock_jwt_manager_class: Mock,
        mock_load_config: Mock,
        mock_parse_duration: Mock,
    ) -> None:
        """Test generate-token command with output file."""
        # Setup mocks
        mock_parse_duration.return_value = Success(data=90)
        mock_config = Mock()
        mock_load_config.return_value = mock_config
        mock_jwt_manager = Mock()
        mock_jwt_manager_class.return_value = mock_jwt_manager
        mock_jwt_manager.generate_token.return_value = "mock-jwt-token"

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as temp_file:
            temp_path = temp_file.name

        try:
            # Run command with output file
            result = self.runner.invoke(
                generate_token,
                ["prod-client", "--expires-in", "3m", "--output", temp_path],
            )

            # Verify exit code
            assert result.exit_code == 0

            # Verify function calls
            mock_parse_duration.assert_called_once_with("3m")
            mock_jwt_manager.generate_token.assert_called_once_with(
                subject="prod-client", expiration_days=90
            )

            # Verify token was written to file
            with open(temp_path) as f:
                content = f.read().strip()
                assert content == "mock-jwt-token"

        finally:
            # Cleanup
            os.unlink(temp_path)

    @patch("vibectl.server.main.parse_duration")
    def test_generate_token_error(self, mock_parse_duration: Mock) -> None:
        """Test generate token command with error."""
        mock_parse_duration.return_value = Error("Invalid duration")

        result = self.runner.invoke(generate_token, ["test-subject"])

        assert result.exit_code == 1

    @patch("vibectl.server.main.ensure_config_dir")
    @patch("vibectl.server.main.create_default_config")
    @patch("pathlib.Path.exists")
    def test_init_config_command(
        self, mock_exists: Mock, mock_create_config: Mock, mock_ensure_dir: Mock
    ) -> None:
        """Test init config command."""
        config_dir = Path("/mock/config")
        _config_file = config_dir / "config.yaml"
        mock_ensure_dir.return_value = config_dir
        mock_exists.return_value = False
        mock_create_config.return_value = Success()

        result = self.runner.invoke(init_config)

        assert result.exit_code == 0
        mock_ensure_dir.assert_called_once_with("server")
        mock_create_config.assert_called_once()

    @patch("vibectl.server.main.ensure_config_dir")
    @patch("pathlib.Path.exists")
    def test_init_config_file_exists_no_force(
        self, mock_exists: Mock, mock_ensure_dir: Mock
    ) -> None:
        """Test init config command when file exists without force."""
        config_dir = Path("/mock/config")
        _config_file = config_dir / "config.yaml"
        mock_ensure_dir.return_value = config_dir
        mock_exists.return_value = True

        result = self.runner.invoke(init_config)

        assert result.exit_code == 1

    @patch("vibectl.server.main.ensure_config_dir")
    @patch("vibectl.server.main.create_default_config")
    @patch("pathlib.Path.exists")
    def test_init_config_with_force(
        self, mock_exists: Mock, mock_create_config: Mock, mock_ensure_dir: Mock
    ) -> None:
        """Test init config command with force flag."""
        config_dir = Path("/mock/config")
        _config_file = config_dir / "config.yaml"
        mock_ensure_dir.return_value = config_dir
        mock_exists.return_value = True
        mock_create_config.return_value = Success()

        result = self.runner.invoke(init_config, ["--force"])

        assert result.exit_code == 0
        mock_create_config.assert_called_once()

    @patch("vibectl.server.main.ensure_config_dir")
    def test_init_config_error(self, mock_ensure_dir: Mock) -> None:
        """Test init config command with error."""
        mock_ensure_dir.side_effect = OSError("Permission denied")

        result = self.runner.invoke(init_config)

        assert result.exit_code == 1

    @patch("vibectl.server.main.load_server_config")
    @patch("vibectl.server.main.validate_config")
    @patch("vibectl.server.main.create_server")
    def test_cli_default_command(
        self,
        mock_create_server: Mock,
        mock_validate: Mock,
        mock_load_config: Mock,
    ) -> None:
        """Test CLI group defaults to serve command."""
        mock_config = get_default_server_config()
        mock_load_config.return_value = Success(data=mock_config)
        mock_validate.return_value = Success()

        mock_server = Mock()
        mock_create_server.return_value = mock_server

        result = self.runner.invoke(cli)

        assert result.exit_code == 0
        mock_server.serve_forever.assert_called_once()

    @patch("vibectl.server.main.load_server_config")
    @patch("vibectl.server.main.validate_config")
    @patch("vibectl.server.main.create_server")
    def test_serve_command_with_tls_options(
        self,
        mock_create_server: Mock,
        mock_validate: Mock,
        mock_load_config: Mock,
    ) -> None:
        """Test serve command with TLS options."""
        mock_config = get_default_server_config()
        mock_load_config.return_value = Success(data=mock_config)
        mock_validate.return_value = Success()

        mock_server = Mock()
        mock_create_server.return_value = mock_server

        result = self.runner.invoke(
            serve,
            [
                "--tls",
                "--cert-file",
                "/path/to/cert.pem",
                "--key-file",
                "/path/to/key.pem",
            ],
        )

        assert result.exit_code == 0
        mock_create_server.assert_called_once_with(
            host="0.0.0.0",
            port=50051,
            default_model="anthropic/claude-3-7-sonnet-latest",
            max_workers=10,
            require_auth=False,
            use_tls=True,
            cert_file="/path/to/cert.pem",
            key_file="/path/to/key.pem",
        )

    @patch("vibectl.server.main.load_server_config")
    @patch("vibectl.server.main.validate_config")
    @patch("vibectl.server.main.create_server")
    @patch("vibectl.server.main.get_config_dir")
    @patch("vibectl.server.cert_utils.ensure_certificate_exists")
    @patch("vibectl.server.cert_utils.get_default_cert_paths")
    def test_serve_command_with_generate_certs(
        self,
        mock_get_default_paths: Mock,
        mock_ensure_certs: Mock,
        mock_get_config_dir: Mock,
        mock_create_server: Mock,
        mock_validate: Mock,
        mock_load_config: Mock,
    ) -> None:
        """Test serve command with certificate generation."""
        mock_config = get_default_server_config()
        mock_config["tls"]["enabled"] = True  # Enable TLS in the tls section
        mock_load_config.return_value = Success(data=mock_config)
        mock_validate.return_value = Success()

        mock_get_config_dir.return_value = Path("/test/config")
        mock_get_default_paths.return_value = ("/test/cert.pem", "/test/key.pem")

        mock_server = Mock()
        mock_create_server.return_value = mock_server

        result = self.runner.invoke(serve, ["--generate-certs"])

        assert result.exit_code == 0
        # Note: The exact ensure_certs call parameters depend on implementation
        mock_ensure_certs.assert_called_once_with(
            "/test/cert.pem",
            "/test/key.pem",
            hostname="localhost",
            regenerate=True,
        )

    @patch("vibectl.server.main.load_server_config")
    @patch("vibectl.server.main.validate_config")
    @patch("vibectl.server.main.create_server")
    def test_serve_command_with_no_tls(
        self,
        mock_create_server: Mock,
        mock_validate: Mock,
        mock_load_config: Mock,
    ) -> None:
        """Test serve command with TLS disabled explicitly."""
        mock_config = get_default_server_config()
        mock_load_config.return_value = Success(data=mock_config)
        mock_validate.return_value = Success()

        mock_server = Mock()
        mock_create_server.return_value = mock_server

        result = self.runner.invoke(serve, ["--no-tls"])

        assert result.exit_code == 0
        mock_create_server.assert_called_once_with(
            host="0.0.0.0",
            port=50051,
            default_model="anthropic/claude-3-7-sonnet-latest",
            max_workers=10,
            require_auth=False,
            use_tls=False,
            cert_file=None,
            key_file=None,
        )

    @patch("vibectl.server.cert_utils.ensure_certificate_exists")
    @patch("vibectl.server.cert_utils.get_default_cert_paths")
    @patch("vibectl.server.main.get_config_dir")
    def test_generate_certs_command_default(
        self,
        mock_get_config_dir: Mock,
        mock_get_default_paths: Mock,
        mock_ensure_certs: Mock,
    ) -> None:
        """Test generate-certs command with default options."""
        mock_get_config_dir.return_value = Path("/mock/config")
        mock_get_default_paths.return_value = ("/mock/cert.pem", "/mock/key.pem")

        result = self.runner.invoke(generate_certs)

        assert result.exit_code == 0
        mock_ensure_certs.assert_called_once_with(
            "/mock/cert.pem",
            "/mock/key.pem",
            hostname="localhost",
            regenerate=False,
        )

    @patch("vibectl.server.cert_utils.ensure_certificate_exists")
    @patch("vibectl.server.main.get_config_dir")
    def test_generate_certs_command_with_options(
        self, mock_get_config_dir: Mock, mock_ensure_certs: Mock
    ) -> None:
        """Test generate-certs command with custom options."""
        mock_get_config_dir.return_value = Path("/mock/config")

        result = self.runner.invoke(
            generate_certs,
            [
                "--cert-file",
                "/custom/cert.pem",
                "--key-file",
                "/custom/key.pem",
                "--hostname",
                "custom.example.com",
                "--force",
            ],
        )

        assert result.exit_code == 0
        mock_ensure_certs.assert_called_once_with(
            "/custom/cert.pem",
            "/custom/key.pem",
            hostname="custom.example.com",
            regenerate=True,
        )

    @patch("vibectl.server.cert_utils.ensure_certificate_exists")
    def test_generate_certs_command_error(self, mock_ensure_certs: Mock) -> None:
        """Test generate-certs command with certificate generation error."""
        mock_ensure_certs.side_effect = Exception("Certificate generation failed")

        result = self.runner.invoke(generate_certs)

        assert result.exit_code == 1


class TestMainEntryPoint:
    """Test main entry point function."""

    @patch("vibectl.server.main.cli")
    def test_main_success(self, mock_cli: Mock) -> None:
        """Test main function with successful execution."""
        mock_cli.return_value = None

        result = main()

        assert result == 0
        mock_cli.assert_called_once()

    @patch("vibectl.server.main.cli")
    def test_main_exception(self, mock_cli: Mock) -> None:
        """Test main function with exception."""
        mock_cli.side_effect = Exception("Test error")

        result = main()

        assert result == 1
        mock_cli.assert_called_once()

    def test_main_server_stopped_by_signal(self) -> None:
        """Test main function when server is stopped by signal."""
        with (
            patch("vibectl.server.main.cli") as mock_cli,
        ):
            # CLI execution succeeds
            mock_cli.return_value = None

            result = main()

            assert result == 0
            mock_cli.assert_called_once()

    def test_main_server_creation_error(self) -> None:
        """Test main function when CLI execution fails."""
        with (
            patch("vibectl.server.main.cli") as mock_cli,
        ):
            # CLI execution raises an exception
            mock_cli.side_effect = Exception("CLI execution failed")

            result = main()

            assert result == 1
            mock_cli.assert_called_once()
