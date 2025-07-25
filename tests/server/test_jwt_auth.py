"""
Unit tests for JWT authentication functionality.

Tests the JWT authentication manager, token generation, validation,
and configuration loading for the vibectl LLM proxy server.
"""

import datetime
import os
import uuid
from typing import Any
from unittest.mock import patch

import jwt as pyjwt  # Avoid conflict with class names
import pytest

from vibectl.server.jwt_auth import (
    JWTAuthManager,
    JWTConfig,
    create_jwt_manager,
    generate_secret_key,
    load_config_from_server,
    load_config_with_generation,
)
from vibectl.types import Error, Success


class TestJWTConfig:
    """Test the JWTConfig model."""

    def test_jwt_config_defaults(self) -> None:
        """Test that JWTConfig has sensible defaults."""
        config = JWTConfig(secret_key="test-secret")

        assert config.secret_key == "test-secret"
        assert config.algorithm == "HS256"
        assert config.issuer == "vibectl-server"
        assert config.expiration_days == 30

    def test_jwt_config_custom_values(self) -> None:
        """Test that JWTConfig accepts custom values."""
        config = JWTConfig(
            secret_key="custom-secret",
            algorithm="HS512",
            issuer="custom-issuer",
            expiration_days=7,
        )

        assert config.secret_key == "custom-secret"
        assert config.algorithm == "HS512"
        assert config.issuer == "custom-issuer"
        assert config.expiration_days == 7


class TestSecretKeyGeneration:
    """Test the generate_secret_key function."""

    def test_generate_secret_key_returns_string(self) -> None:
        """Test that generate_secret_key returns a string."""
        key = generate_secret_key()
        assert isinstance(key, str)
        assert len(key) > 0

    def test_generate_secret_key_is_unique(self) -> None:
        """Test that generate_secret_key generates unique keys."""
        key1 = generate_secret_key()
        key2 = generate_secret_key()
        assert key1 != key2

    def test_generate_secret_key_is_url_safe(self) -> None:
        """Test that generated keys are URL safe base64."""
        key = generate_secret_key()
        # URL-safe base64 uses A-Z, a-z, 0-9, -, and _
        allowed_chars = set(
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        )
        assert all(c in allowed_chars for c in key)


class TestLoadConfigFromServer:
    """Test the load_config_from_server function."""

    def test_load_config_from_env_variable_highest_precedence(self) -> None:
        """Test that environment variable takes highest precedence."""

        env_vars = {
            "VIBECTL_JWT_SECRET": "env-secret",
            "VIBECTL_JWT_ALGORITHM": "HS512",
            "VIBECTL_JWT_ISSUER": "env-issuer",
            "VIBECTL_JWT_EXPIRATION_DAYS": "7",
        }

        # Create a server config with different values
        server_config = {
            "server": {"host": "localhost", "port": 8080},
            "jwt": {
                "secret_key": "config-secret",
                "algorithm": "HS384",
                "issuer": "config-issuer",
                "expiration_days": 14,
            },
        }

        with patch.dict(os.environ, env_vars, clear=False):
            config = load_config_from_server(server_config)

        assert config.secret_key == "env-secret"  # Env wins
        assert config.algorithm == "HS512"  # Env wins
        assert config.issuer == "env-issuer"  # Env wins
        assert config.expiration_days == 7  # Env wins

    def test_load_config_from_env_key_file_second_precedence(self) -> None:
        """Test that environment key file takes second precedence."""
        import tempfile

        # Create secret key file
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as secret_file:
            secret_file.write("file-secret")
            secret_file.flush()

            env_vars = {
                "VIBECTL_JWT_SECRET_FILE": secret_file.name,
                "VIBECTL_JWT_ALGORITHM": "HS512",
            }

            # Create server config with different values
            server_config = {
                "jwt": {"secret_key": "config-secret", "algorithm": "HS384"}
            }

            with patch.dict(os.environ, env_vars, clear=False):
                config = load_config_from_server(server_config)

            assert config.secret_key == "file-secret"  # Env file wins over config
            assert config.algorithm == "HS512"  # Env wins

        os.unlink(secret_file.name)

    def test_load_config_env_key_file_read_error_fallback(self) -> None:
        """Env key file read errors fall back to server config key."""
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as secret_file:
            secret_file.write("file-secret")
            secret_file.flush()

            env_vars = {"VIBECTL_JWT_SECRET_FILE": secret_file.name}
            server_config = {"jwt": {"secret_key": "config-secret"}}

            with (
                patch.dict(os.environ, env_vars, clear=False),
                patch("pathlib.Path.read_text", side_effect=OSError("boom")),
                patch("vibectl.server.jwt_auth.logger") as mock_logger,
            ):
                config = load_config_from_server(server_config)

                assert config.secret_key == "config-secret"
                warnings = [c.args[0] for c in mock_logger.warning.call_args_list]
                assert any(
                    "Failed to read JWT secret from environment key file" in msg
                    for msg in warnings
                )

        os.unlink(secret_file.name)

    def test_load_config_from_server_config_third_precedence(self) -> None:
        """Test that server config values take third precedence."""

        # Clear any JWT env vars
        env_keys_to_remove = [
            "VIBECTL_JWT_SECRET",
            "VIBECTL_JWT_SECRET_FILE",
            "VIBECTL_JWT_ALGORITHM",
            "VIBECTL_JWT_ISSUER",
            "VIBECTL_JWT_EXPIRATION_DAYS",
        ]

        removed_values = {}
        for key in env_keys_to_remove:
            if key in os.environ:
                removed_values[key] = os.environ[key]
                del os.environ[key]

        try:
            server_config = {
                "server": {"host": "localhost", "port": 8080},
                "jwt": {
                    "secret_key": "config-secret",
                    "algorithm": "HS384",
                    "issuer": "config-issuer",
                    "expiration_days": 14,
                },
            }

            config = load_config_from_server(server_config)

            assert config.secret_key == "config-secret"
            assert config.algorithm == "HS384"
            assert config.issuer == "config-issuer"
            assert config.expiration_days == 14
        finally:
            # Restore removed env vars
            for key, value in removed_values.items():
                os.environ[key] = value

    def test_load_config_from_config_key_file_fourth_precedence(self) -> None:
        """Test that config key file takes fourth precedence."""
        import tempfile

        # Clear JWT env vars
        env_keys_to_remove = [
            "VIBECTL_JWT_SECRET",
            "VIBECTL_JWT_SECRET_FILE",
            "VIBECTL_JWT_ALGORITHM",
            "VIBECTL_JWT_ISSUER",
            "VIBECTL_JWT_EXPIRATION_DAYS",
        ]

        removed_values = {}
        for key in env_keys_to_remove:
            if key in os.environ:
                removed_values[key] = os.environ[key]
                del os.environ[key]

        try:
            # Create secret key file
            with tempfile.NamedTemporaryFile(mode="w", delete=False) as secret_file:
                secret_file.write("config-file-secret")
                secret_file.flush()

                server_config = {
                    "jwt": {
                        "secret_key_file": secret_file.name,
                        "algorithm": "HS384",
                        "issuer": "config-issuer",
                    }
                }

                config = load_config_from_server(server_config)

                assert config.secret_key == "config-file-secret"
                assert config.algorithm == "HS384"
                assert config.issuer == "config-issuer"

            os.unlink(secret_file.name)
        finally:
            # Restore removed env vars
            for key, value in removed_values.items():
                os.environ[key] = value

    def test_load_config_config_key_file_read_error(self) -> None:
        """Read errors on config key file trigger generation."""
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as secret_file:
            secret_file.write("config-file-secret")
            secret_file.flush()

            server_config = {"jwt": {"secret_key_file": secret_file.name}}

            with (
                patch("pathlib.Path.read_text", side_effect=OSError("boom")),
                patch("vibectl.server.jwt_auth.generate_secret_key") as mock_gen,
                patch("vibectl.server.jwt_auth.logger") as mock_logger,
            ):
                mock_gen.return_value = "generated-secret"
                config = load_config_from_server(server_config)

                assert config.secret_key == "generated-secret"
                mock_gen.assert_called_once()
                warnings = [c.args[0] for c in mock_logger.warning.call_args_list]
                assert any(
                    "Failed to read JWT secret from config key file" in msg
                    for msg in warnings
                )

        os.unlink(secret_file.name)

    def test_load_config_generates_key_as_fallback(self) -> None:
        """Test that a new key is generated as final fallback."""

        # Clear JWT env vars
        env_keys_to_remove = [
            "VIBECTL_JWT_SECRET",
            "VIBECTL_JWT_SECRET_FILE",
            "VIBECTL_JWT_ALGORITHM",
            "VIBECTL_JWT_ISSUER",
            "VIBECTL_JWT_EXPIRATION_DAYS",
        ]

        removed_values = {}
        for key in env_keys_to_remove:
            if key in os.environ:
                removed_values[key] = os.environ[key]
                del os.environ[key]

        try:
            # Create minimal config without JWT section
            server_config = {"server": {"host": "localhost", "port": 8080}}

            with (
                patch("vibectl.server.jwt_auth.generate_secret_key") as mock_gen,
                patch("vibectl.server.jwt_auth.logger") as _mock_logger,
            ):
                mock_gen.return_value = "generated-secret"
                config = load_config_from_server(server_config)

                assert config.secret_key == "generated-secret"
                assert config.algorithm == "HS256"  # Default
                assert config.issuer == "vibectl-server"  # Default
                assert config.expiration_days == 30  # Default

                mock_gen.assert_called_once()
                _mock_logger.warning.assert_called_once()

                warning_call = _mock_logger.warning.call_args[0][0]
                assert "No JWT secret key found" in warning_call
        finally:
            # Restore removed env vars
            for key, value in removed_values.items():
                os.environ[key] = value

    def test_load_config_nonexistent_config_file(self) -> None:
        """Test loading config when server config is None (uses load_server_config)."""
        with (
            patch("vibectl.server.jwt_auth.generate_secret_key") as mock_gen,
            patch("vibectl.server.jwt_auth.logger") as _mock_logger,
            patch("vibectl.server.config.load_server_config") as mock_load_config,
        ):
            mock_gen.return_value = "generated-secret"
            mock_load_config.return_value = Success(
                data={"server": {"host": "localhost"}}
            )

            config = load_config_from_server(None)

            assert config.secret_key == "generated-secret"
            mock_gen.assert_called_once()
            _mock_logger.warning.assert_called_once()
            mock_load_config.assert_called_once()

    def test_load_config_invalid_config_file(self) -> None:
        """Test loading config with invalid/empty config."""

        with (
            patch("vibectl.server.jwt_auth.generate_secret_key") as mock_gen,
            patch("vibectl.server.jwt_auth.logger") as _mock_logger,
        ):
            mock_gen.return_value = "generated-secret"
            # Pass empty config
            config = load_config_from_server({})

            assert config.secret_key == "generated-secret"
            mock_gen.assert_called_once()
            _mock_logger.warning.assert_called()

    def test_load_config_missing_secret_key_file(self) -> None:
        """Test when config references a missing secret key file."""

        server_config = {
            "jwt": {"secret_key_file": "/nonexistent/secret.key", "algorithm": "HS256"}
        }

        with (
            patch("vibectl.server.jwt_auth.generate_secret_key") as mock_gen,
            patch("vibectl.server.jwt_auth.logger") as _mock_logger,
        ):
            mock_gen.return_value = "generated-secret"
            config = load_config_from_server(server_config)

            assert config.secret_key == "generated-secret"
            mock_gen.assert_called_once()
            _mock_logger.warning.assert_called()


class TestLoadConfigWithGeneration:
    """Test the load_config_with_generation function."""

    def test_load_config_without_persistence_behaves_like_normal(self) -> None:
        """Test that with persist_generated_key=False, behaves like normal function."""

        env_vars = {"VIBECTL_JWT_SECRET": "env-secret"}
        server_config = {"server": {"host": "localhost"}}

        with patch.dict(os.environ, env_vars, clear=False):
            config = load_config_with_generation(
                server_config, persist_generated_key=False
            )

            assert config.secret_key == "env-secret"

    def test_load_config_persists_generated_key_to_config_file(self) -> None:
        """Test that generated key is persisted to config file when enabled."""
        import tempfile

        import yaml

        # Clear JWT env vars to force generation
        env_keys_to_remove = [
            "VIBECTL_JWT_SECRET",
            "VIBECTL_JWT_SECRET_FILE",
            "VIBECTL_JWT_ALGORITHM",
            "VIBECTL_JWT_ISSUER",
            "VIBECTL_JWT_EXPIRATION_DAYS",
        ]

        removed_values = {}
        for key in env_keys_to_remove:
            if key in os.environ:
                removed_values[key] = os.environ[key]
                del os.environ[key]

        try:
            # Create initial config without JWT section
            initial_config = {
                "server": {"host": "localhost", "port": 8080},
                "model": {"provider": "openai"},
            }

            with (
                tempfile.NamedTemporaryFile(
                    mode="w", suffix=".yaml", delete=False
                ) as config_file,
            ):
                yaml.dump(initial_config, config_file)
                config_file.flush()

                with (
                    patch("vibectl.server.jwt_auth.generate_secret_key") as mock_gen,
                    patch("vibectl.server.jwt_auth.logger") as mock_logger,
                    patch(
                        "vibectl.server.config.load_server_config"
                    ) as mock_load_config,
                    patch("vibectl.server.config.get_server_config_path") as mock_path,
                ):
                    mock_gen.return_value = "generated-secret-key"
                    mock_load_config.return_value = Success(data=initial_config.copy())
                    mock_path.return_value = config_file.name

                    config = load_config_with_generation(
                        None, persist_generated_key=True
                    )

                    # Verify returned config
                    assert config.secret_key == "generated-secret-key"
                    assert config.algorithm == "HS256"  # Default
                    assert config.issuer == "vibectl-server"  # Default
                    assert config.expiration_days == 30  # Default

                    mock_gen.assert_called_once()
                    mock_logger.info.assert_called_once()

                    info_call = mock_logger.info.call_args[0][0]
                    assert "Generated and saved new JWT secret key" in info_call

                # Verify config file was updated
                with open(config_file.name) as f:
                    updated_config = yaml.safe_load(f)

                assert "jwt" in updated_config
                assert updated_config["jwt"]["secret_key"] == "generated-secret-key"
                # Verify original config preserved
                assert updated_config["server"]["host"] == "localhost"
                assert updated_config["model"]["provider"] == "openai"

            os.unlink(config_file.name)
        finally:
            # Restore removed env vars
            for key, value in removed_values.items():
                os.environ[key] = value

    def test_load_config_persists_to_nonexistent_config_file(self) -> None:
        """Test that config file is created when it doesn't exist."""
        import yaml

        # Clear JWT env vars to force generation
        env_keys_to_remove = [
            "VIBECTL_JWT_SECRET",
            "VIBECTL_JWT_SECRET_FILE",
            "VIBECTL_JWT_ALGORITHM",
            "VIBECTL_JWT_ISSUER",
            "VIBECTL_JWT_EXPIRATION_DAYS",
        ]

        removed_values = {}
        for key in env_keys_to_remove:
            if key in os.environ:
                removed_values[key] = os.environ[key]
                del os.environ[key]

        try:
            nonexistent_file = "/tmp/nonexistent_config.yaml"

            # Ensure file doesn't exist
            if os.path.exists(nonexistent_file):
                os.unlink(nonexistent_file)

            with (
                patch("vibectl.server.jwt_auth.generate_secret_key") as mock_gen,
                patch("vibectl.server.jwt_auth.logger") as mock_logger,
                patch("vibectl.server.config.load_server_config") as mock_load_config,
                patch("vibectl.server.config.get_server_config_path") as mock_get_path,
            ):
                mock_gen.return_value = "generated-secret-key"
                mock_load_config.return_value = Success(data={})
                mock_get_path.return_value = nonexistent_file

                config = load_config_with_generation(None, persist_generated_key=True)

                # Verify returned config
                assert config.secret_key == "generated-secret-key"

                mock_gen.assert_called_once()
                mock_logger.info.assert_called_once()

                info_call = mock_logger.info.call_args[0][0]
                assert "Generated and saved new JWT secret key" in info_call

            # Verify config file was created
            assert os.path.exists(nonexistent_file)

            with open(nonexistent_file) as f:
                created_config = yaml.safe_load(f)

            assert "jwt" in created_config
            assert created_config["jwt"]["secret_key"] == "generated-secret-key"

            # Clean up
            os.unlink(nonexistent_file)
        finally:
            # Restore removed env vars
            for key, value in removed_values.items():
                os.environ[key] = value

    def test_load_config_uses_existing_key_when_available(self) -> None:
        """Test that existing keys are reused, not overwritten."""

        # Create config with existing JWT key
        server_config = {
            "jwt": {"secret_key": "existing-secret-key", "algorithm": "HS384"}
        }

        with (
            patch("vibectl.server.jwt_auth.generate_secret_key") as mock_gen,
            patch("vibectl.server.jwt_auth.logger") as mock_logger,
        ):
            config = load_config_with_generation(
                server_config, persist_generated_key=True
            )

            # Should use existing key, not generate new one
            assert config.secret_key == "existing-secret-key"
            assert config.algorithm == "HS384"

            # Should not generate new key
            mock_gen.assert_not_called()

            # Should log reuse message
            mock_logger.info.assert_called_once()
            info_call = mock_logger.info.call_args[0][0]
            assert "Using JWT secret from server configuration" in info_call

    @pytest.mark.skipif(os.geteuid() == 0, reason="Root can write read-only files")
    def test_load_config_handles_config_file_write_errors(self) -> None:
        """Test handling of config file write errors during persistence."""
        import tempfile

        # Clear JWT env vars to force generation
        env_keys_to_remove = [
            "VIBECTL_JWT_SECRET",
            "VIBECTL_JWT_SECRET_FILE",
            "VIBECTL_JWT_ALGORITHM",
            "VIBECTL_JWT_ISSUER",
            "VIBECTL_JWT_EXPIRATION_DAYS",
        ]

        removed_values = {}
        for key in env_keys_to_remove:
            if key in os.environ:
                removed_values[key] = os.environ[key]
                del os.environ[key]

        try:
            with (
                tempfile.NamedTemporaryFile(
                    mode="w", suffix=".yaml", delete=False
                ) as config_file,
            ):
                config_file.write("server:\n  host: localhost")
                config_file.flush()

                # Make file read-only to simulate write error
                os.chmod(config_file.name, 0o444)

                with (
                    patch("vibectl.server.jwt_auth.generate_secret_key") as mock_gen,
                    patch("vibectl.server.jwt_auth.logger") as mock_logger,
                    patch(
                        "vibectl.server.config.load_server_config"
                    ) as mock_load_config,
                    patch("vibectl.server.config.get_server_config_path") as mock_path,
                ):
                    mock_gen.return_value = "generated-secret-key"
                    mock_load_config.return_value = Success(
                        data={"server": {"host": "localhost"}}
                    )
                    mock_path.return_value = config_file.name

                    config = load_config_with_generation(
                        None, persist_generated_key=True
                    )

                    # Should still return valid config
                    assert config.secret_key == "generated-secret-key"

                    # Should log error about write failure
                    mock_logger.error.assert_called_once()
                    error_call = mock_logger.error.call_args[0][0]
                    assert (
                        "Failed to save generated JWT secret to config file"
                        in error_call
                    )

                # Restore permissions for cleanup
                os.chmod(config_file.name, 0o644)

            os.unlink(config_file.name)
        finally:
            # Restore removed env vars
            for key, value in removed_values.items():
                os.environ[key] = value


class TestJWTAuthManager:
    """Test the JWTAuthManager class."""

    @pytest.fixture
    def jwt_config(self) -> JWTConfig:
        """Create a test JWT configuration."""
        return JWTConfig(
            secret_key="test-secret-key",
            algorithm="HS256",
            issuer="test-issuer",
            expiration_days=1,  # Short expiration for testing
        )

    @pytest.fixture
    def jwt_manager(self, jwt_config: JWTConfig) -> JWTAuthManager:
        """Create a test JWT auth manager."""
        return JWTAuthManager(jwt_config)

    def test_jwt_manager_initialization(self, jwt_config: JWTConfig) -> None:
        """Test JWT manager initialization."""
        with patch("vibectl.server.jwt_auth.logger") as _mock_logger:
            manager = JWTAuthManager(jwt_config)

            assert manager.config == jwt_config
            _mock_logger.info.assert_called_once()
            log_call = _mock_logger.info.call_args[0][0]
            assert "JWT Auth Manager initialized" in log_call
            assert "test-issuer" in log_call

    def test_generate_token_basic(self, jwt_manager: JWTAuthManager) -> None:
        """Test basic token generation."""
        with patch("vibectl.server.jwt_auth.logger") as _mock_logger:
            token = jwt_manager.generate_token("test-subject")

            assert isinstance(token, str)
            assert len(token) > 0

            # Verify logging
            _mock_logger.info.assert_called_once()
            log_call = _mock_logger.info.call_args[0][0]
            assert "Generated JWT token for subject 'test-subject'" in log_call

    def test_generate_token_with_custom_expiration(
        self, jwt_manager: JWTAuthManager
    ) -> None:
        """Test token generation with custom expiration."""
        token = jwt_manager.generate_token("test-subject", expiration_days=7)

        # Decode token to verify expiration
        payload = pyjwt.decode(token, "test-secret-key", algorithms=["HS256"])
        exp_time = datetime.datetime.fromtimestamp(payload["exp"], tz=datetime.UTC)
        iat_time = datetime.datetime.fromtimestamp(payload["iat"], tz=datetime.UTC)

        # Should be approximately 7 days
        duration = exp_time - iat_time
        assert 6.9 <= duration.days <= 7.1  # Allow for small timing differences

    def test_generate_token_payload_structure(
        self, jwt_manager: JWTAuthManager
    ) -> None:
        """Test that generated token has correct payload structure."""
        token = jwt_manager.generate_token("test-subject")

        # Decode without verification to check structure
        payload = pyjwt.decode(token, options={"verify_signature": False})

        assert payload["sub"] == "test-subject"
        assert payload["iss"] == "test-issuer"
        assert "iat" in payload
        assert "exp" in payload
        assert "jti" in payload

        # Verify jti is a valid UUID
        assert uuid.UUID(payload["jti"])

    def test_validate_token_valid(self, jwt_manager: JWTAuthManager) -> None:
        """Test validation of a valid token."""
        token = jwt_manager.generate_token("test-subject")

        with patch("vibectl.server.jwt_auth.logger") as _mock_logger:
            payload = jwt_manager.validate_token(token)

            assert payload["sub"] == "test-subject"
            assert payload["iss"] == "test-issuer"

            _mock_logger.debug.assert_called_once()
            log_call = _mock_logger.debug.call_args[0][0]
            assert (
                "Successfully validated JWT token for subject: test-subject" in log_call
            )

    def test_validate_token_expired(self, jwt_config: JWTConfig) -> None:
        """Test validation of an expired token."""
        # Create token that's already expired
        now = datetime.datetime.now(datetime.UTC)
        expired_time = now - datetime.timedelta(days=1)

        payload = {
            "sub": "test-subject",
            "iss": jwt_config.issuer,
            "iat": expired_time,
            "exp": expired_time,  # Already expired
            "jti": str(uuid.uuid4()),
        }

        token = pyjwt.encode(
            payload, jwt_config.secret_key, algorithm=jwt_config.algorithm
        )
        manager = JWTAuthManager(jwt_config)

        with patch("vibectl.server.jwt_auth.logger") as _mock_logger:
            with pytest.raises(pyjwt.InvalidTokenError, match="Token has expired"):
                manager.validate_token(token)

            _mock_logger.warning.assert_called_once()
            log_call = _mock_logger.warning.call_args[0][0]
            assert "JWT token has expired" in log_call

    def test_validate_token_invalid_signature(
        self, jwt_manager: JWTAuthManager
    ) -> None:
        """Test validation of token with invalid signature."""
        # Create token with wrong secret
        payload = {
            "sub": "test-subject",
            "iss": "test-issuer",
            "iat": datetime.datetime.now(datetime.UTC),
            "exp": datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1),
            "jti": str(uuid.uuid4()),
        }

        token = pyjwt.encode(payload, "wrong-secret", algorithm="HS256")

        with patch("vibectl.server.jwt_auth.logger") as _mock_logger:
            with pytest.raises(
                pyjwt.InvalidTokenError, match="Invalid token signature"
            ):
                jwt_manager.validate_token(token)

            _mock_logger.warning.assert_called_once()
            log_call = _mock_logger.warning.call_args[0][0]
            assert "JWT token has invalid signature" in log_call

    def test_validate_token_invalid_issuer(self, jwt_config: JWTConfig) -> None:
        """Test validation of token with invalid issuer."""
        # Create token with wrong issuer
        payload = {
            "sub": "test-subject",
            "iss": "wrong-issuer",
            "iat": datetime.datetime.now(datetime.UTC),
            "exp": datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1),
            "jti": str(uuid.uuid4()),
        }

        token = pyjwt.encode(
            payload, jwt_config.secret_key, algorithm=jwt_config.algorithm
        )
        manager = JWTAuthManager(jwt_config)

        with patch("vibectl.server.jwt_auth.logger") as _mock_logger:
            with pytest.raises(pyjwt.InvalidTokenError, match="Invalid token issuer"):
                manager.validate_token(token)

            _mock_logger.warning.assert_called_once()
            log_call = _mock_logger.warning.call_args[0][0]
            assert "JWT token has invalid issuer" in log_call

    def test_validate_token_malformed(self, jwt_manager: JWTAuthManager) -> None:
        """Test validation of malformed token."""
        malformed_token = "not.a.valid.jwt.token"

        with patch("vibectl.server.jwt_auth.logger") as _mock_logger:
            with pytest.raises(pyjwt.InvalidTokenError):
                jwt_manager.validate_token(malformed_token)

            _mock_logger.warning.assert_called_once()
            log_call = _mock_logger.warning.call_args[0][0]
            assert "Invalid JWT token" in log_call

    def test_validate_token_unexpected_error(self, jwt_manager: JWTAuthManager) -> None:
        """Test handling of unexpected errors during token validation."""
        with patch("jwt.decode") as mock_decode:
            mock_decode.side_effect = Exception("Unexpected error")

            with patch("vibectl.server.jwt_auth.logger") as _mock_logger:
                with pytest.raises(
                    pyjwt.InvalidTokenError, match="Token validation failed"
                ):
                    jwt_manager.validate_token("test-token")

                _mock_logger.error.assert_called_once()
                log_call = _mock_logger.error.call_args[0][0]
                assert "Unexpected error validating JWT token" in log_call

    def test_get_token_subject_valid_token(self, jwt_manager: JWTAuthManager) -> None:
        """Test extracting subject from valid token without verification."""
        token = jwt_manager.generate_token("test-subject")

        subject = jwt_manager.get_token_subject(token)
        assert subject == "test-subject"

    def test_get_token_subject_invalid_token(self, jwt_manager: JWTAuthManager) -> None:
        """Test extracting subject from invalid token returns None."""
        invalid_token = "not.a.valid.jwt"

        with patch("vibectl.server.jwt_auth.logger") as _mock_logger:
            subject = jwt_manager.get_token_subject(invalid_token)

            assert subject is None
            _mock_logger.debug.assert_called_once()
            log_call = _mock_logger.debug.call_args[0][0]
            assert "Failed to extract subject from token" in log_call

    def test_get_token_subject_token_without_subject(
        self, jwt_config: JWTConfig
    ) -> None:
        """Test extracting subject from token that doesn't have sub claim."""
        # Create token without subject
        payload = {
            "iss": jwt_config.issuer,
            "iat": datetime.datetime.now(datetime.UTC),
            "exp": datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1),
        }

        token = pyjwt.encode(
            payload, jwt_config.secret_key, algorithm=jwt_config.algorithm
        )
        manager = JWTAuthManager(jwt_config)

        subject = manager.get_token_subject(token)
        assert subject is None


class TestCreateJWTManager:
    """Test the create_jwt_manager convenience function."""

    def test_create_jwt_manager_with_env_config(self) -> None:
        """Test that create_jwt_manager uses environment configuration."""
        env_vars = {
            "VIBECTL_JWT_SECRET": "test-secret",
            "VIBECTL_JWT_ISSUER": "test-issuer",
        }

        with patch.dict(os.environ, env_vars, clear=False):
            manager = create_jwt_manager()

            assert isinstance(manager, JWTAuthManager)
            assert manager.config.secret_key == "test-secret"
            assert manager.config.issuer == "test-issuer"

    def test_create_jwt_manager_generates_secret_when_missing(self) -> None:
        """Test that create_jwt_manager generates secret when not in environment."""
        # Remove the secret key temporarily
        removed_secret = None
        if "VIBECTL_JWT_SECRET" in os.environ:
            removed_secret = os.environ["VIBECTL_JWT_SECRET"]
            del os.environ["VIBECTL_JWT_SECRET"]

        try:
            with (
                patch("vibectl.server.jwt_auth.generate_secret_key") as mock_gen,
                patch("vibectl.server.jwt_auth.logger") as _mock_logger,
            ):
                mock_gen.return_value = "generated-secret"
                manager = create_jwt_manager()

                assert manager.config.secret_key == "generated-secret"
                mock_gen.assert_called_once()
        finally:
            # Restore the secret key if it existed
            if removed_secret is not None:
                os.environ["VIBECTL_JWT_SECRET"] = removed_secret


class TestJWTIntegration:
    """Integration tests for JWT authentication."""

    def test_full_token_lifecycle(self) -> None:
        """Test complete token generation and validation lifecycle."""
        # Clear environment
        with patch.dict(os.environ, {}, clear=True):
            # Test with temporary config
            server_config = {
                "jwt": {
                    "secret_key": "test-integration-secret",
                    "algorithm": "HS256",
                    "issuer": "integration-test",
                    "expiration_days": 1,
                }
            }

            config = load_config_from_server(server_config)
            manager = JWTAuthManager(config)

            # Generate token
            subject = "test-user"
            token = manager.generate_token(subject)

            # Validate token
            payload = manager.validate_token(token)
            assert payload["sub"] == subject
            assert payload["iss"] == "integration-test"

    def test_cross_manager_validation_fails(self) -> None:
        """Test that tokens from one manager fail validation in another."""
        config1 = JWTConfig(secret_key="secret1", issuer="issuer1")
        config2 = JWTConfig(
            secret_key="secret2", issuer="issuer1"
        )  # Same issuer, different secret

        manager1 = JWTAuthManager(config1)
        manager2 = JWTAuthManager(config2)

        token = manager1.generate_token("test-user")

        with pytest.raises(pyjwt.InvalidTokenError):
            manager2.validate_token(token)

    def test_algorithm_compatibility(self) -> None:
        """Test JWT token generation and validation with different algorithms."""
        for algorithm in ["HS256", "HS384", "HS512"]:
            config = JWTConfig(
                secret_key="test-secret", algorithm=algorithm, issuer="test-issuer"
            )
            manager = JWTAuthManager(config)

            token = manager.generate_token("test-subject")
            payload = manager.validate_token(token)

            assert payload["sub"] == "test-subject"
            assert payload["iss"] == "test-issuer"


class TestJWTAuthCoverageGaps:
    """Tests to fill specific coverage gaps in JWT auth module."""

    def test_load_config_with_invalid_server_config_data_type(self) -> None:
        """Test handling of invalid server config data type."""
        with (
            patch("vibectl.server.config.load_server_config") as mock_load,
            patch("vibectl.server.config.get_default_server_config") as mock_default,
        ):
            mock_load.return_value = Error("config error")
            mock_default.return_value = {"jwt": {"secret_key": "fallback-key"}}

            config = load_config_from_server()

            mock_load.assert_called_once()
            mock_default.assert_called_once()
            assert config.secret_key == "fallback-key"
            assert config.algorithm == "HS256"

    def test_load_config_env_key_file_missing(self) -> None:
        """Test handling of missing environment key file."""

        # Use a non-existent file path
        nonexistent_file = "/tmp/does_not_exist_jwt_secret.txt"
        env_vars = {"VIBECTL_JWT_SECRET_FILE": nonexistent_file}
        server_config = {"jwt": {"secret_key": "config-fallback-key"}}

        with patch.dict(os.environ, env_vars, clear=False):
            config = load_config_from_server(server_config)
            assert config.secret_key == "config-fallback-key"

    def test_load_config_config_key_file_missing(self) -> None:
        """Test handling of missing config key file."""
        nonexistent_file = "/tmp/does_not_exist_config_jwt_secret.txt"
        server_config = {"jwt": {"secret_key_file": nonexistent_file}}

        with patch.dict(os.environ, {}, clear=True):
            config = load_config_from_server(server_config)
            # Should fall back to generating a new key
            assert len(config.secret_key) > 0
            assert config.secret_key.replace("-", "").replace("_", "").isalnum()

    def test_load_config_with_generation_config_path_none(self) -> None:
        """Test load_config_with_generation when config_path is None."""
        server_config: dict[str, Any] = {"jwt": {}}  # No secret configured

        # Test without persist_generated_key - should behave normally
        config = load_config_with_generation(
            server_config=server_config, persist_generated_key=False
        )
        assert len(config.secret_key) > 0

        # Test with persist_generated_key but no config_path - should not persist
        config = load_config_with_generation(
            server_config=server_config, persist_generated_key=True
        )
        assert len(config.secret_key) > 0

    def test_load_config_with_generation_yaml_dump_error(self) -> None:
        """Test handling of YAML dump errors during key persistence."""
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as config_file:
            config_file.write("jwt: {}\n")
            config_file.flush()
            config_path = config_file.name

        server_config: dict[str, Any] = {"jwt": {}}  # No secret configured

        with (
            patch(
                "vibectl.server.config.get_server_config_path", return_value=config_path
            ),
            patch("vibectl.server.config.load_server_config") as mock_load,
            patch("yaml.dump", side_effect=Exception("YAML dump failed")),
            patch("vibectl.server.jwt_auth.logger") as mock_logger,
        ):
            mock_load.return_value = Success(data=server_config)

            # This should still work despite the YAML dump error
            config = load_config_with_generation(
                server_config=None, persist_generated_key=True
            )

            # Should generate a key but fail to persist
            assert config.secret_key  # Generated key
            mock_logger.error.assert_called_once()  # Should log the persistence error

        os.unlink(config_path)

    def test_jwt_manager_get_token_subject_decode_error(self) -> None:
        """Test get_token_subject handling of token decode errors."""
        config = JWTConfig(secret_key="test-secret")
        manager = JWTAuthManager(config)

        # Test with completely invalid token
        invalid_token = "not.a.valid.jwt.token"
        subject = manager.get_token_subject(invalid_token)
        assert subject is None

        # Test with malformed token structure
        malformed_token = "header.payload"  # Missing signature
        subject = manager.get_token_subject(malformed_token)
        assert subject is None

    def test_jwt_manager_validate_token_generic_exception(self) -> None:
        """Test validate_token handling of unexpected exceptions."""
        config = JWTConfig(secret_key="test-secret")
        manager = JWTAuthManager(config)

        # Mock jwt.decode to raise an unexpected exception
        with (
            patch("jwt.decode", side_effect=ValueError("Unexpected error")),
            pytest.raises(pyjwt.InvalidTokenError, match="Token validation failed"),
        ):
            manager.validate_token("any-token")
