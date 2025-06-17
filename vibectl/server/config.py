"""Server configuration management.

This module provides server-specific configuration handling for vibectl server,
following the same patterns as the main CLI configuration.
"""

import json
import logging
from pathlib import Path
from typing import Any

import yaml

from vibectl.types import Error, Result, Success

logger = logging.getLogger(__name__)


class ServerConfig:
    """Server configuration management."""

    def __init__(self, config_path: Path | None = None):
        """Initialize server configuration.

        Args:
            config_path: Optional path to configuration file
        """
        self.config_path = config_path or get_server_config_path()
        self._config_cache: dict[str, Any] | None = None

    def get_config_path(self) -> Path:
        """Get the server configuration file path."""
        return self.config_path

    def get_default_config(self) -> dict[str, Any]:
        """Get default server configuration."""
        return {
            "server": {
                "host": "0.0.0.0",
                "port": 50051,
                "max_workers": 10,
                "default_model": None,
            },
            "jwt": {
                "enabled": False,
                "secret_key": None,
                "algorithm": "HS256",
                "expiration_hours": 24,
            },
            "tls": {
                "enabled": False,
                "cert_file": None,
                "key_file": None,
                "ca_bundle_file": None,
                "hsts": {
                    "enabled": False,
                    "max_age": 31536000,  # 1 year by default
                    "include_subdomains": True,
                    "preload": False,
                },
            },
            "acme": {
                "enabled": False,
                "email": None,
                "domains": [],
                "directory_url": "https://acme-v02.api.letsencrypt.org/directory",
                "challenge": {"type": "http-01"},
                "challenge_dir": ".well-known/acme-challenge",
                "auto_renew": True,
                "renew_days_before_expiry": 30,
            },
        }

    def load(self, force_reload: bool = False) -> Result:
        """Load server configuration from file.

        Args:
            force_reload: Whether to force reload from file

        Returns:
            Result containing the loaded configuration
        """
        if not force_reload and self._config_cache is not None:
            return Success(data=self._config_cache)

        try:
            if not self.config_path.exists():
                logger.debug(
                    f"Configuration file {self.config_path} not found, using defaults"
                )
                config = self.get_default_config()
            else:
                logger.debug(f"Loading server configuration from {self.config_path}")
                with open(self.config_path, encoding="utf-8") as f:
                    if self.config_path.suffix.lower() == ".json":
                        config = json.load(f)
                    else:
                        config = yaml.safe_load(f) or {}

                # Merge with defaults to ensure all required keys exist
                default_config = self.get_default_config()
                config = self._deep_merge(default_config, config)

            self._config_cache = config
            return Success(data=config)

        except Exception as e:
            error_msg = (
                f"Failed to load server configuration from {self.config_path}: {e}"
            )
            logger.error(error_msg)
            return Error(error=error_msg, exception=e)

    def save(self, config: dict[str, Any]) -> Result:
        """Save server configuration to file.

        Args:
            config: Configuration to save

        Returns:
            Result indicating success or failure
        """
        try:
            # Create directory if it doesn't exist
            self.config_path.parent.mkdir(parents=True, exist_ok=True)

            with open(self.config_path, "w", encoding="utf-8") as f:
                if self.config_path.suffix.lower() == ".json":
                    json.dump(config, f, indent=2)
                else:
                    yaml.dump(config, f, default_flow_style=False, indent=2)

            self._config_cache = config
            logger.info(f"Server configuration saved to {self.config_path}")
            return Success()

        except Exception as e:
            error_msg = (
                f"Failed to save server configuration to {self.config_path}: {e}"
            )
            logger.error(error_msg)
            return Error(error=error_msg, exception=e)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value using dot notation.

        Args:
            key: Configuration key (e.g., 'server.host', 'jwt.enabled')
            default: Default value if key is not found

        Returns:
            Configuration value or default
        """
        config_result = self.load()
        if isinstance(config_result, Error):
            logger.warning(
                f"Failed to load config for get({key}): {config_result.error}"
            )
            return default

        config = config_result.data
        if config is None:
            return default

        keys = key.split(".")

        try:
            value = config
            for k in keys:
                if value is None:
                    return default
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default

    def set(self, key: str, value: Any) -> Result:
        """Set a configuration value using dot notation.

        Args:
            key: Configuration key (e.g., 'server.host', 'jwt.enabled')
            value: Value to set

        Returns:
            Result indicating success or failure
        """
        config_result = self.load()
        if isinstance(config_result, Error):
            return config_result

        if config_result.data is None:
            return Error(error="Configuration data is None")

        config = config_result.data.copy()
        keys = key.split(".")

        # Navigate to the parent dictionary
        current = config
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]

        # Set the final value
        current[keys[-1]] = value

        return self.save(config)

    def validate(self, config: dict[str, Any] | None = None) -> Result:
        """Validate server configuration.

        Args:
            config: Configuration to validate (loads from file if None)

        Returns:
            Result containing validated configuration
        """
        if config is None:
            config_result = self.load()
            if isinstance(config_result, Error):
                return config_result
            if config_result.data is None:
                return Error(error="Configuration data is None")
            config = config_result.data

        try:
            # Validate server section
            server_section = config.get("server", {})
            host = server_section.get("host", "0.0.0.0")
            port = server_section.get("port", 50051)
            max_workers = server_section.get("max_workers", 10)

            # Ensure port and max_workers are integers
            if not isinstance(port, int):
                try:
                    port = int(port)
                    server_section["port"] = port
                except (ValueError, TypeError):
                    return Error(error=f"Invalid port value: {port}")

            if not isinstance(max_workers, int):
                try:
                    max_workers = int(max_workers)
                    server_section["max_workers"] = max_workers
                except (ValueError, TypeError):
                    return Error(error=f"Invalid max_workers value: {max_workers}")

            # Validate port range
            if not (1 <= port <= 65535):
                return Error(error=f"Port must be between 1 and 65535, got: {port}")

            # Validate max_workers
            if max_workers < 1:
                return Error(
                    error=f"max_workers must be at least 1, got: {max_workers}"
                )

            # Validate host (basic check)
            if not isinstance(host, str) or not host.strip():
                return Error(error=f"Invalid host value: {host}")

            # Validate JWT section
            jwt_section = config.get("jwt", {})
            if jwt_section.get("enabled", False):
                # JWT can be enabled without a secret_key in config since
                # the secret can be loaded from environment variables,
                # secret_key_file, or generated dynamically by the JWT system
                pass

            # Validate TLS and ACME sections
            tls_section = config.get("tls", {})
            acme_section = config.get("acme", {})

            if tls_section.get("enabled", False):
                cert_file = tls_section.get("cert_file")
                key_file = tls_section.get("key_file")

                # Only validate file existence if not using ACME
                if not acme_section.get("enabled", False):
                    if not cert_file:
                        return Error(error="TLS enabled but no cert_file provided")
                    if not key_file:
                        return Error(error="TLS enabled but no key_file provided")

            # Validate ACME section
            if acme_section.get("enabled", False):
                email = acme_section.get("email")
                if not email or not email.strip():
                    return Error(error="ACME enabled but no email provided")
                if not acme_section.get("domains"):
                    return Error(error="ACME enabled but no domains provided")

            return Success(data=config)

        except Exception as e:
            return Error(error=f"Configuration validation failed: {e}", exception=e)

    def apply_overrides(
        self, config: dict[str, Any], overrides: dict[str, Any]
    ) -> dict[str, Any]:
        """Apply configuration overrides using deep merge.

        Args:
            config: Base configuration
            overrides: Configuration overrides

        Returns:
            Merged configuration
        """
        return self._deep_merge(config, overrides)

    def create_default(self, force: bool = False) -> Result:
        """Create default configuration file.

        Args:
            force: Whether to overwrite existing configuration

        Returns:
            Result indicating success or failure
        """
        if self.config_path.exists() and not force:
            return Error(error=f"Configuration file already exists: {self.config_path}")

        default_config = self.get_default_config()
        return self.save(default_config)

    @staticmethod
    def _deep_merge(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
        """Recursively merge dictionaries.

        Args:
            base: Base dictionary
            updates: Updates to apply

        Returns:
            Merged dictionary
        """
        result = base.copy()
        for key, value in updates.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = ServerConfig._deep_merge(result[key], value)
            else:
                result[key] = value
        return result


def get_server_config_path() -> Path:
    """Get the default server configuration file path.

    Returns:
        Path to server configuration file
    """
    return Path.home() / ".config" / "vibectl" / "server" / "config.yaml"


def load_server_config(config_path: Path | None = None) -> Result:
    """Load server configuration from file.

    Args:
        config_path: Optional path to configuration file

    Returns:
        Result containing the loaded configuration
    """
    server_config = ServerConfig(config_path)
    return server_config.load()


def create_default_server_config(
    config_path: Path | None = None, force: bool = False
) -> Result:
    """Create default server configuration file.

    Args:
        config_path: Optional path to configuration file
        force: Whether to overwrite existing configuration

    Returns:
        Result indicating success or failure
    """
    server_config = ServerConfig(config_path)
    return server_config.create_default(force)


def validate_server_config(
    config: dict[str, Any] | None = None, config_path: Path | None = None
) -> Result:
    """Validate server configuration.

    Args:
        config: Configuration to validate (loads from file if None)
        config_path: Optional path to configuration file

    Returns:
        Result containing validated configuration
    """
    server_config = ServerConfig(config_path)
    return server_config.validate(config)


def get_default_server_config() -> dict[str, Any]:
    """Get default server configuration as a standalone function.

    Returns:
        Default server configuration dictionary
    """
    return {
        "server": {
            "host": "0.0.0.0",
            "port": 50051,
            "max_workers": 10,
            "default_model": "anthropic/claude-3-7-sonnet-latest",
            "log_level": "INFO",
        },
        "jwt": {
            "enabled": False,
            "secret_key": None,
            "secret_key_file": None,
            "algorithm": "HS256",
            "issuer": "vibectl-server",
            "expiration_days": 30,
        },
        "tls": {
            "enabled": False,
            "cert_file": None,
            "key_file": None,
            "ca_bundle_file": None,
            "hsts": {
                "enabled": False,
                "max_age": 31536000,  # 1 year by default
                "include_subdomains": True,
                "preload": False,
            },
        },
        "acme": {
            "enabled": False,
            "email": None,
            "domains": [],
            "directory_url": "https://acme-v02.api.letsencrypt.org/directory",
            "challenge": {"type": "tls-alpn-01"},
            "challenge_dir": ".well-known/acme-challenge",
            "auto_renew": True,
            "renew_days_before_expiry": 30,
        },
    }
