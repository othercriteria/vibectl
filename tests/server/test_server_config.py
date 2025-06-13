"""
Tests for vibectl.server.config module.

This module tests all functionality in the ServerConfig class and related functions,
aiming for 100% test coverage with proper error handling and edge case testing.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import yaml

from vibectl.server.config import (
    ServerConfig,
    create_default_server_config,
    get_default_server_config,
    get_server_config_path,
    load_server_config,
    validate_server_config,
)
from vibectl.types import Error, Success


class TestServerConfig:
    """Test ServerConfig class."""

    def test_init_default_path(self) -> None:
        """Test ServerConfig initialization with default path."""
        config = ServerConfig()

        expected_path = Path.home() / ".config" / "vibectl" / "server" / "config.yaml"
        assert config.config_path == expected_path
        assert config._config_cache is None

    def test_init_custom_path(self) -> None:
        """Test ServerConfig initialization with custom path."""
        custom_path = Path("/custom/config.yaml")
        config = ServerConfig(custom_path)

        assert config.config_path == custom_path
        assert config._config_cache is None

    def test_get_config_path(self) -> None:
        """Test get_config_path method."""
        custom_path = Path("/test/config.yaml")
        config = ServerConfig(custom_path)

        assert config.get_config_path() == custom_path

    def test_get_default_config(self) -> None:
        """Test get_default_config method."""
        config = ServerConfig()
        default_config = config.get_default_config()

        # Check all main sections exist
        assert "server" in default_config
        assert "jwt" in default_config
        assert "tls" in default_config
        assert "acme" in default_config

        # Check server section
        server = default_config["server"]
        assert server["host"] == "0.0.0.0"
        assert server["port"] == 50051
        assert server["max_workers"] == 10
        assert server["default_model"] is None

        # Check JWT section
        jwt = default_config["jwt"]
        assert jwt["enabled"] is False
        assert jwt["secret_key"] is None
        assert jwt["algorithm"] == "HS256"
        assert jwt["expiration_hours"] == 24

        # Check TLS section
        tls = default_config["tls"]
        assert tls["enabled"] is False
        assert tls["cert_file"] is None
        assert tls["key_file"] is None

        # Check ACME section
        acme = default_config["acme"]
        assert acme["enabled"] is False
        assert acme["email"] is None
        assert acme["domains"] == []

    def test_load_file_not_exists(self) -> None:
        """Test loading config when file doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "nonexistent.yaml"
            config = ServerConfig(config_path)

            result = config.load()

            assert isinstance(result, Success)
            assert result.data == config.get_default_config()
            assert config._config_cache == result.data

    def test_load_yaml_file_success(self) -> None:
        """Test loading YAML config file successfully."""
        test_config = {
            "server": {"host": "localhost", "port": 8080},
            "jwt": {"enabled": True},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(test_config, f)
            config_path = Path(f.name)

        try:
            config = ServerConfig(config_path)
            result = config.load()

            assert isinstance(result, Success)
            assert result.data is not None
            assert isinstance(result.data, dict)
            # Should be merged with defaults
            assert result.data["server"]["host"] == "localhost"
            assert result.data["server"]["port"] == 8080
            assert result.data["jwt"]["enabled"] is True
            # Defaults should still be present
            assert result.data["server"]["max_workers"] == 10
            assert result.data["acme"]["enabled"] is False
        finally:
            config_path.unlink()

    def test_load_json_file_success(self) -> None:
        """Test loading JSON config file successfully."""
        test_config = {
            "server": {"host": "jsonhost", "port": 9090},
            "tls": {"enabled": True},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(test_config, f)
            config_path = Path(f.name)

        try:
            config = ServerConfig(config_path)
            result = config.load()

            assert isinstance(result, Success)
            assert result.data is not None
            assert isinstance(result.data, dict)
            assert result.data["server"]["host"] == "jsonhost"
            assert result.data["server"]["port"] == 9090
            assert result.data["tls"]["enabled"] is True
        finally:
            config_path.unlink()

    def test_load_empty_yaml_file(self) -> None:
        """Test loading empty YAML file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")  # Empty file
            config_path = Path(f.name)

        try:
            config = ServerConfig(config_path)
            result = config.load()

            assert isinstance(result, Success)
            # Should return defaults since empty YAML loads as None
            assert result.data == config.get_default_config()
        finally:
            config_path.unlink()

    def test_load_with_cache(self) -> None:
        """Test loading config with cache enabled."""
        config = ServerConfig(Path("/nonexistent.yaml"))

        # First load should cache the result
        result1 = config.load()
        assert isinstance(result1, Success)

        # Second load should return cached result
        result2 = config.load()
        assert isinstance(result2, Success)
        assert result1.data is result2.data  # Same object reference

    def test_load_force_reload(self) -> None:
        """Test loading config with force reload."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({"server": {"host": "original"}}, f)
            config_path = Path(f.name)

        try:
            config = ServerConfig(config_path)

            # First load
            result1 = config.load()
            assert isinstance(result1, Success)
            assert result1.data is not None
            assert isinstance(result1.data, dict)
            assert result1.data["server"]["host"] == "original"

            # Modify file
            with open(config_path, "w") as f:
                yaml.dump({"server": {"host": "modified"}}, f)

            # Load without force should return cached
            result2 = config.load(force_reload=False)
            assert isinstance(result2, Success)
            assert result2.data is not None
            assert isinstance(result2.data, dict)
            assert result2.data["server"]["host"] == "original"

            # Load with force should return new data
            result3 = config.load(force_reload=True)
            assert isinstance(result3, Success)
            assert result3.data is not None
            assert isinstance(result3.data, dict)
            assert result3.data["server"]["host"] == "modified"
        finally:
            config_path.unlink()

    def test_load_invalid_yaml(self) -> None:
        """Test loading invalid YAML file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("invalid: yaml: content: [")
            config_path = Path(f.name)

        try:
            config = ServerConfig(config_path)
            result = config.load()

            assert isinstance(result, Error)
            assert "Failed to load server configuration" in result.error
            assert config._config_cache is None
        finally:
            config_path.unlink()

    def test_load_invalid_json(self) -> None:
        """Test loading invalid JSON file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{invalid json}")
            config_path = Path(f.name)

        try:
            config = ServerConfig(config_path)
            result = config.load()

            assert isinstance(result, Error)
            assert "Failed to load server configuration" in result.error
        finally:
            config_path.unlink()

    def test_load_permission_error(self) -> None:
        """Test loading config with permission error."""
        config = ServerConfig(Path("/root/inaccessible.yaml"))

        with patch("builtins.open", side_effect=PermissionError("Access denied")):
            result = config.load()

            assert isinstance(result, Error)
            assert "Failed to load server configuration" in result.error

    def test_save_yaml_success(self) -> None:
        """Test saving config to YAML file successfully."""
        test_config = {"server": {"host": "saved", "port": 8080}}

        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.yaml"
            config = ServerConfig(config_path)

            result = config.save(test_config)

            assert isinstance(result, Success)
            assert config_path.exists()
            assert config._config_cache == test_config

            # Verify file contents
            with open(config_path) as f:
                saved_data = yaml.safe_load(f)
            assert saved_data == test_config

    def test_save_json_success(self) -> None:
        """Test saving config to JSON file successfully."""
        test_config = {"server": {"host": "savedjson", "port": 9090}}

        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config = ServerConfig(config_path)

            result = config.save(test_config)

            assert isinstance(result, Success)
            assert config_path.exists()

            # Verify file contents
            with open(config_path) as f:
                saved_data = json.load(f)
            assert saved_data == test_config

    def test_save_creates_directory(self) -> None:
        """Test saving config creates parent directories."""
        test_config = {"server": {"host": "test"}}

        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "nested" / "dir" / "config.yaml"
            config = ServerConfig(config_path)

            result = config.save(test_config)

            assert isinstance(result, Success)
            assert config_path.exists()
            assert config_path.parent.exists()

    def test_save_permission_error(self) -> None:
        """Test saving config with permission error."""
        config = ServerConfig(Path("/root/inaccessible.yaml"))

        with patch("builtins.open", side_effect=PermissionError("Access denied")):
            result = config.save({"test": "data"})

            assert isinstance(result, Error)
            assert "Failed to save server configuration" in result.error

    def test_get_simple_key(self) -> None:
        """Test getting a simple configuration key."""
        test_config = {"server": {"host": "testhost", "port": 8080}}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(test_config, f)
            config_path = Path(f.name)

        try:
            config = ServerConfig(config_path)

            assert config.get("server.host") == "testhost"
            assert config.get("server.port") == 8080
        finally:
            config_path.unlink()

    def test_get_nested_key(self) -> None:
        """Test getting nested configuration key."""
        config = ServerConfig(Path("/nonexistent.yaml"))

        # Should use defaults
        assert config.get("server.host") == "0.0.0.0"
        assert config.get("jwt.enabled") is False

    def test_get_missing_key_with_default(self) -> None:
        """Test getting missing key returns default."""
        config = ServerConfig(Path("/nonexistent.yaml"))

        assert config.get("nonexistent.key", "default_value") == "default_value"
        assert config.get("server.nonexistent", 42) == 42

    def test_get_with_load_error(self) -> None:
        """Test getting key when load fails."""
        config = ServerConfig(Path("/root/inaccessible.yaml"))

        with patch.object(config, "load", return_value=Error(error="Load failed")):
            result = config.get("server.host", "fallback")

            assert result == "fallback"

    def test_get_with_none_config(self) -> None:
        """Test getting key when config data is None."""
        config = ServerConfig()

        with patch.object(config, "load", return_value=Success(data=None)):
            result = config.get("server.host", "fallback")

            assert result == "fallback"

    def test_get_key_path_with_none_value(self) -> None:
        """Test getting key when intermediate value is None."""
        test_config = {"server": None}
        config = ServerConfig()

        with patch.object(config, "load", return_value=Success(data=test_config)):
            result = config.get("server.host", "fallback")

            assert result == "fallback"

    def test_get_invalid_key_type(self) -> None:
        """Test getting key with type error."""
        test_config = {"server": "not_a_dict"}
        config = ServerConfig()

        with patch.object(config, "load", return_value=Success(data=test_config)):
            result = config.get("server.host", "fallback")

            assert result == "fallback"

    def test_set_simple_key(self) -> None:
        """Test setting a simple configuration key."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.yaml"
            config = ServerConfig(config_path)

            # First create a default config
            config.save(config.get_default_config())

            result = config.set("server.host", "newhost")

            assert isinstance(result, Success)

            # Verify the value was set
            assert config.get("server.host") == "newhost"

    def test_set_nested_key_creates_structure(self) -> None:
        """Test setting nested key creates necessary structure."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.yaml"
            config = ServerConfig(config_path)

            # First create a default config
            config.save(config.get_default_config())

            result = config.set("new.nested.key", "value")

            assert isinstance(result, Success)
            assert config.get("new.nested.key") == "value"

    def test_set_with_load_error(self) -> None:
        """Test setting key when load fails."""
        config = ServerConfig(Path("/root/inaccessible.yaml"))

        with patch.object(config, "load", return_value=Error(error="Load failed")):
            result = config.set("server.host", "newhost")

            assert isinstance(result, Error)
            assert "Load failed" in result.error

    def test_set_with_none_config_data(self) -> None:
        """Test setting key when config data is None."""
        config = ServerConfig()

        with patch.object(config, "load", return_value=Success(data=None)):
            result = config.set("server.host", "newhost")

            assert isinstance(result, Error)
            assert "Configuration data is None" in result.error

    def test_set_with_save_error(self) -> None:
        """Test setting key when save fails."""
        config = ServerConfig(Path("/nonexistent.yaml"))

        with patch.object(config, "save", return_value=Error(error="Save failed")):
            result = config.set("server.host", "newhost")

            assert isinstance(result, Error)
            assert "Save failed" in result.error

    def test_validate_valid_config(self) -> None:
        """Test validating a valid configuration."""
        valid_config = {
            "server": {"host": "localhost", "port": 8080, "max_workers": 5},
            "jwt": {"enabled": False},
            "tls": {"enabled": False},
            "acme": {"enabled": False},
        }

        config = ServerConfig()
        result = config.validate(valid_config)

        assert isinstance(result, Success)
        assert result.data == valid_config

    def test_validate_no_config_loads_from_file(self) -> None:
        """Test validating without config loads from file."""
        config = ServerConfig(Path("/nonexistent.yaml"))

        result = config.validate()

        assert isinstance(result, Success)
        # Should validate the default config

    def test_validate_with_load_error(self) -> None:
        """Test validating when load fails."""
        config = ServerConfig(Path("/root/inaccessible.yaml"))

        with patch.object(config, "load", return_value=Error(error="Load failed")):
            result = config.validate()

            assert isinstance(result, Error)
            assert "Load failed" in result.error

    def test_validate_with_none_config_data(self) -> None:
        """Test validating when config data is None."""
        config = ServerConfig()

        with patch.object(config, "load", return_value=Success(data=None)):
            result = config.validate()

            assert isinstance(result, Error)
            assert "Configuration data is None" in result.error

    def test_validate_invalid_port_string(self) -> None:
        """Test validating config with invalid port as string."""
        invalid_config = {
            "server": {"host": "localhost", "port": "abc", "max_workers": 5}
        }

        config = ServerConfig()
        result = config.validate(invalid_config)

        assert isinstance(result, Error)
        assert "Invalid port value: abc" in result.error

    def test_validate_invalid_max_workers_string(self) -> None:
        """Test validating config with invalid max_workers as string."""
        invalid_config = {
            "server": {"host": "localhost", "port": 8080, "max_workers": "invalid"}
        }

        config = ServerConfig()
        result = config.validate(invalid_config)

        assert isinstance(result, Error)
        assert "Invalid max_workers value: invalid" in result.error

    def test_validate_port_conversion_success(self) -> None:
        """Test validating config with port as convertible string."""
        config_with_string_port = {
            "server": {"host": "localhost", "port": "8080", "max_workers": 5}
        }

        config = ServerConfig()
        result = config.validate(config_with_string_port)

        assert isinstance(result, Success)
        assert result.data is not None
        assert isinstance(result.data, dict)
        assert result.data["server"]["port"] == 8080  # Converted to int

    def test_validate_max_workers_conversion_success(self) -> None:
        """Test validating config with max_workers as convertible string."""
        config_with_string_workers = {
            "server": {"host": "localhost", "port": 8080, "max_workers": "10"}
        }

        config = ServerConfig()
        result = config.validate(config_with_string_workers)

        assert isinstance(result, Success)
        assert result.data is not None
        assert isinstance(result.data, dict)
        assert result.data["server"]["max_workers"] == 10  # Converted to int

    def test_validate_port_out_of_range_low(self) -> None:
        """Test validating config with port too low."""
        invalid_config = {"server": {"host": "localhost", "port": 0, "max_workers": 5}}

        config = ServerConfig()
        result = config.validate(invalid_config)

        assert isinstance(result, Error)
        assert "Port must be between 1 and 65535, got: 0" in result.error

    def test_validate_port_out_of_range_high(self) -> None:
        """Test validating config with port too high."""
        invalid_config = {
            "server": {"host": "localhost", "port": 70000, "max_workers": 5}
        }

        config = ServerConfig()
        result = config.validate(invalid_config)

        assert isinstance(result, Error)
        assert "Port must be between 1 and 65535, got: 70000" in result.error

    def test_validate_max_workers_too_low(self) -> None:
        """Test validating config with max_workers too low."""
        invalid_config = {
            "server": {"host": "localhost", "port": 8080, "max_workers": 0}
        }

        config = ServerConfig()
        result = config.validate(invalid_config)

        assert isinstance(result, Error)
        assert "max_workers must be at least 1, got: 0" in result.error

    def test_validate_invalid_host_empty(self) -> None:
        """Test validating config with empty host."""
        invalid_config = {"server": {"host": "", "port": 8080, "max_workers": 5}}

        config = ServerConfig()
        result = config.validate(invalid_config)

        assert isinstance(result, Error)
        assert "Invalid host value:" in result.error

    def test_validate_invalid_host_non_string(self) -> None:
        """Test validating config with non-string host."""
        invalid_config = {"server": {"host": 123, "port": 8080, "max_workers": 5}}

        config = ServerConfig()
        result = config.validate(invalid_config)

        assert isinstance(result, Error)
        assert "Invalid host value: 123" in result.error

    def test_validate_jwt_enabled_no_secret(self) -> None:
        """Test validating config with JWT enabled but no secret key in config.

        JWT can be enabled without a secret_key in config since the secret
        can be loaded from environment variables, secret_key_file, or
        generated dynamically by the JWT system.
        """
        valid_config = {
            "server": {"host": "localhost", "port": 8080, "max_workers": 5},
            "jwt": {"enabled": True},
        }

        config = ServerConfig()
        result = config.validate(valid_config)

        assert isinstance(result, Success)
        assert result.data is not None
        # Verify the config structure is preserved
        assert result.data["jwt"]["enabled"] is True

    def test_validate_jwt_enabled_with_secret(self) -> None:
        """Test validating config with JWT enabled and secret key."""
        valid_config = {
            "server": {"host": "localhost", "port": 8080, "max_workers": 5},
            "jwt": {"enabled": True, "secret_key": "my-secret"},
        }

        config = ServerConfig()
        result = config.validate(valid_config)

        assert isinstance(result, Success)

    def test_validate_jwt_enabled_no_secret_allows_dynamic_loading(self) -> None:
        """Test that JWT validation allows enabled JWT without secret_key in config.

        This tests the specific behavior that was causing the demo to fail:
        JWT can be enabled in config without a secret_key because the JWT
        authentication system loads secrets from multiple sources:
        - Environment variables (JWT_SECRET_KEY)
        - Secret key files (jwt.secret_key_file)
        - Dynamic generation as fallback

        The validation should not require secret_key in the config file.
        """
        config_with_jwt_no_secret = {
            "server": {"host": "0.0.0.0", "port": 50051, "max_workers": 10},
            "jwt": {"enabled": True},  # No secret_key provided
            "tls": {"enabled": False},
            "acme": {"enabled": False},
        }

        config = ServerConfig()
        result = config.validate(config_with_jwt_no_secret)

        assert isinstance(result, Success)
        assert result.data is not None
        assert result.data["jwt"]["enabled"] is True
        # Verify that secret_key is not required in validation
        assert (
            "secret_key" not in result.data["jwt"]
            or result.data["jwt"]["secret_key"] is None
        )

    def test_validate_tls_enabled_no_cert_file(self) -> None:
        """Test validating config with TLS enabled but no cert file."""
        invalid_config = {
            "server": {"host": "localhost", "port": 8080, "max_workers": 5},
            "tls": {"enabled": True},
            "acme": {"enabled": False},
        }

        config = ServerConfig()
        result = config.validate(invalid_config)

        assert isinstance(result, Error)
        assert "TLS enabled but no cert_file provided" in result.error

    def test_validate_tls_enabled_no_key_file(self) -> None:
        """Test validating config with TLS enabled but no key file."""
        invalid_config = {
            "server": {"host": "localhost", "port": 8080, "max_workers": 5},
            "tls": {"enabled": True, "cert_file": "cert.pem"},
            "acme": {"enabled": False},
        }

        config = ServerConfig()
        result = config.validate(invalid_config)

        assert isinstance(result, Error)
        assert "TLS enabled but no key_file provided" in result.error

    def test_validate_tls_enabled_with_acme(self) -> None:
        """Test validating config with TLS enabled and ACME enabled."""
        valid_config = {
            "server": {"host": "localhost", "port": 8080, "max_workers": 5},
            "tls": {"enabled": True},
            "acme": {
                "enabled": True,
                "email": "test@example.com",
                "domains": ["example.com"],
            },
        }

        config = ServerConfig()
        result = config.validate(valid_config)

        assert isinstance(result, Success)

    def test_validate_acme_enabled_no_email(self) -> None:
        """Test validating config with ACME enabled but no email."""
        invalid_config = {
            "server": {"host": "localhost", "port": 8080, "max_workers": 5},
            "acme": {"enabled": True, "domains": ["example.com"]},
        }

        config = ServerConfig()
        result = config.validate(invalid_config)

        assert isinstance(result, Error)
        assert "ACME enabled but no email provided" in result.error

    def test_validate_acme_enabled_empty_string_email(self) -> None:
        """Test validating config with ACME enabled but empty string email."""
        invalid_config = {
            "server": {"host": "localhost", "port": 8080, "max_workers": 5},
            "acme": {"enabled": True, "email": "", "domains": ["example.com"]},
        }

        config = ServerConfig()
        result = config.validate(invalid_config)

        assert isinstance(result, Error)
        assert "ACME enabled but no email provided" in result.error

    def test_validate_acme_enabled_whitespace_email(self) -> None:
        """Test validating config with ACME enabled but whitespace-only email."""
        invalid_config = {
            "server": {"host": "localhost", "port": 8080, "max_workers": 5},
            "acme": {"enabled": True, "email": "   ", "domains": ["example.com"]},
        }

        config = ServerConfig()
        result = config.validate(invalid_config)

        assert isinstance(result, Error)
        assert "ACME enabled but no email provided" in result.error

    def test_validate_acme_enabled_no_domains(self) -> None:
        """Test validating config with ACME enabled but no domains."""
        invalid_config = {
            "server": {"host": "localhost", "port": 8080, "max_workers": 5},
            "acme": {"enabled": True, "email": "test@example.com"},
        }

        config = ServerConfig()
        result = config.validate(invalid_config)

        assert isinstance(result, Error)
        assert "ACME enabled but no domains provided" in result.error

    def test_validate_exception_during_validation(self) -> None:
        """Test validating config with exception during validation."""
        config = ServerConfig()

        # Create a config that will cause an exception during access
        with (
            patch.dict("os.environ", {}),
            patch("vibectl.server.config.logger"),
        ):
            # Mock config.get to raise an exception
            mock_config = Mock()
            mock_config.get.side_effect = RuntimeError("Unexpected error")

            result = config.validate(mock_config)

            assert isinstance(result, Error)
            assert "Configuration validation failed" in result.error

    def test_apply_overrides_simple(self) -> None:
        """Test applying simple configuration overrides."""
        base_config = {"server": {"host": "localhost", "port": 8080}}
        overrides = {"server": {"port": 9090}}

        config = ServerConfig()
        result = config.apply_overrides(base_config, overrides)

        assert result["server"]["host"] == "localhost"
        assert result["server"]["port"] == 9090

    def test_apply_overrides_nested(self) -> None:
        """Test applying nested configuration overrides."""
        base_config = {
            "server": {"host": "localhost", "port": 8080},
            "jwt": {"enabled": False, "algorithm": "HS256"},
        }
        overrides = {
            "server": {"port": 9090},
            "jwt": {"enabled": True},
            "new_section": {"key": "value"},
        }

        config = ServerConfig()
        result = config.apply_overrides(base_config, overrides)

        assert result["server"]["host"] == "localhost"  # Preserved
        assert result["server"]["port"] == 9090  # Overridden
        assert result["jwt"]["enabled"] is True  # Overridden
        assert result["jwt"]["algorithm"] == "HS256"  # Preserved
        assert result["new_section"]["key"] == "value"  # Added

    def test_apply_overrides_replace_non_dict(self) -> None:
        """Test applying overrides replaces non-dict values."""
        base_config = {"server": {"host": "localhost"}}
        overrides = {"server": "replaced"}

        config = ServerConfig()
        result = config.apply_overrides(base_config, overrides)

        assert result["server"] == "replaced"

    def test_create_default_success(self) -> None:
        """Test creating default configuration successfully."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.yaml"
            config = ServerConfig(config_path)

            result = config.create_default()

            assert isinstance(result, Success)
            assert config_path.exists()

            # Verify content
            with open(config_path) as f:
                saved_config = yaml.safe_load(f)
            assert saved_config == config.get_default_config()

    def test_create_default_file_exists_no_force(self) -> None:
        """Test creating default config when file exists without force."""
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            config_path = Path(f.name)

        try:
            config = ServerConfig(config_path)
            result = config.create_default(force=False)

            assert isinstance(result, Error)
            assert "Configuration file already exists" in result.error
        finally:
            config_path.unlink()

    def test_create_default_file_exists_with_force(self) -> None:
        """Test creating default config when file exists with force."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("existing: content")
            config_path = Path(f.name)

        try:
            config = ServerConfig(config_path)
            result = config.create_default(force=True)

            assert isinstance(result, Success)

            # Verify content was replaced
            with open(config_path) as f:
                saved_config = yaml.safe_load(f)
            assert saved_config == config.get_default_config()
        finally:
            config_path.unlink()

    def test_create_default_save_error(self) -> None:
        """Test creating default config with save error."""
        import tempfile

        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = Path(f.name)

        # Remove the file so it doesn't exist
        temp_path.unlink()

        try:
            config = ServerConfig(temp_path)

            with patch.object(config, "save", return_value=Error(error="Save failed")):
                result = config.create_default()

                assert isinstance(result, Error)
                assert "Save failed" in result.error
        finally:
            # Clean up - remove the temp file if it exists
            if temp_path.exists():
                temp_path.unlink()

    def test_deep_merge_simple(self) -> None:
        """Test deep merge with simple dictionaries."""
        base = {"a": 1, "b": 2}
        updates = {"b": 3, "c": 4}

        result = ServerConfig._deep_merge(base, updates)

        assert result == {"a": 1, "b": 3, "c": 4}
        assert result is not base  # Should be a copy

    def test_deep_merge_nested(self) -> None:
        """Test deep merge with nested dictionaries."""
        base = {"level1": {"level2": {"a": 1, "b": 2}, "other": "value"}}
        updates = {"level1": {"level2": {"b": 3, "c": 4}}}

        result = ServerConfig._deep_merge(base, updates)

        expected = {"level1": {"level2": {"a": 1, "b": 3, "c": 4}, "other": "value"}}
        assert result == expected

    def test_deep_merge_replace_non_dict(self) -> None:
        """Test deep merge replaces non-dict values."""
        base = {"key": {"nested": "value"}}
        updates = {"key": "replaced"}

        result = ServerConfig._deep_merge(base, updates)

        assert result == {"key": "replaced"}


class TestStandaloneFunctions:
    """Test standalone functions in the config module."""

    def test_get_server_config_path(self) -> None:
        """Test get_server_config_path function."""
        result = get_server_config_path()

        expected = Path.home() / ".config" / "vibectl" / "server" / "config.yaml"
        assert result == expected

    def test_load_server_config_default_path(self) -> None:
        """Test load_server_config with default path."""
        with patch("vibectl.server.config.ServerConfig") as mock_config_class:
            mock_instance = Mock()
            mock_instance.load.return_value = Success(data={"test": "data"})
            mock_config_class.return_value = mock_instance

            result = load_server_config()

            assert isinstance(result, Success)
            mock_config_class.assert_called_once_with(None)
            mock_instance.load.assert_called_once()

    def test_load_server_config_custom_path(self) -> None:
        """Test load_server_config with custom path."""
        custom_path = Path("/custom/config.yaml")

        with patch("vibectl.server.config.ServerConfig") as mock_config_class:
            mock_instance = Mock()
            mock_instance.load.return_value = Success(data={"test": "data"})
            mock_config_class.return_value = mock_instance

            result = load_server_config(custom_path)

            assert isinstance(result, Success)
            mock_config_class.assert_called_once_with(custom_path)

    def test_create_default_server_config_default_path(self) -> None:
        """Test create_default_server_config with default path."""
        with patch("vibectl.server.config.ServerConfig") as mock_config_class:
            mock_instance = Mock()
            mock_instance.create_default.return_value = Success()
            mock_config_class.return_value = mock_instance

            result = create_default_server_config()

            assert isinstance(result, Success)
            mock_config_class.assert_called_once_with(None)
            mock_instance.create_default.assert_called_once_with(False)

    def test_create_default_server_config_with_force(self) -> None:
        """Test create_default_server_config with force flag."""
        with patch("vibectl.server.config.ServerConfig") as mock_config_class:
            mock_instance = Mock()
            mock_instance.create_default.return_value = Success()
            mock_config_class.return_value = mock_instance

            result = create_default_server_config(force=True)

            assert isinstance(result, Success)
            mock_instance.create_default.assert_called_once_with(True)

    def test_create_default_server_config_custom_path(self) -> None:
        """Test create_default_server_config with custom path."""
        custom_path = Path("/custom/config.yaml")

        with patch("vibectl.server.config.ServerConfig") as mock_config_class:
            mock_instance = Mock()
            mock_instance.create_default.return_value = Success()
            mock_config_class.return_value = mock_instance

            result = create_default_server_config(custom_path)

            assert isinstance(result, Success)
            mock_config_class.assert_called_once_with(custom_path)

    def test_validate_server_config_with_config(self) -> None:
        """Test validate_server_config with provided config."""
        test_config = {"server": {"host": "localhost"}}

        with patch("vibectl.server.config.ServerConfig") as mock_config_class:
            mock_instance = Mock()
            mock_instance.validate.return_value = Success(data=test_config)
            mock_config_class.return_value = mock_instance

            result = validate_server_config(test_config)

            assert isinstance(result, Success)
            mock_config_class.assert_called_once_with(None)
            mock_instance.validate.assert_called_once_with(test_config)

    def test_validate_server_config_custom_path(self) -> None:
        """Test validate_server_config with custom path."""
        custom_path = Path("/custom/config.yaml")

        with patch("vibectl.server.config.ServerConfig") as mock_config_class:
            mock_instance = Mock()
            mock_instance.validate.return_value = Success(data={})
            mock_config_class.return_value = mock_instance

            result = validate_server_config(config_path=custom_path)

            assert isinstance(result, Success)
            mock_config_class.assert_called_once_with(custom_path)

    def test_get_default_server_config_function(self) -> None:
        """Test get_default_server_config standalone function."""
        result = get_default_server_config()

        assert isinstance(result, dict)
        assert "server" in result
        assert "jwt" in result
        assert "tls" in result
        assert "acme" in result

        # Check that it matches expected structure
        server = result["server"]
        assert server["host"] == "0.0.0.0"
        assert server["port"] == 50051
        assert server["default_model"] == "anthropic/claude-3-7-sonnet-latest"
        assert server["log_level"] == "INFO"

        jwt = result["jwt"]
        assert jwt["enabled"] is False
        assert jwt["issuer"] == "vibectl-server"
        assert jwt["expiration_days"] == 30

        acme = result["acme"]
        assert acme["directory_url"] == "https://acme-v02.api.letsencrypt.org/directory"
        assert acme["auto_renew"] is True
        assert acme["renew_days_before_expiry"] == 30
