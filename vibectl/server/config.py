"""Server configuration management.

This module provides server-specific configuration handling for vibectl server,
following the same patterns as the main CLI configuration.
"""

import json
import logging
import os
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

from vibectl.types import Error, Result, Success

# Runtime ContextVar overrides (set via CLI flags or tests)
from . import overrides as server_overrides

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rate-limit model
# ---------------------------------------------------------------------------


@dataclass
class Limits:
    """Typed container for effective rate-limit values.

    A ``None`` value means *unlimited* for that particular dimension.
    """

    max_requests_per_minute: int | None = None
    max_concurrent_requests: int | None = None
    max_input_length: int | None = None
    request_timeout_seconds: int | None = None

    def as_dict(self) -> dict[str, int | None]:
        return {
            "max_requests_per_minute": self.max_requests_per_minute,
            "max_concurrent_requests": self.max_concurrent_requests,
            "max_input_length": self.max_input_length,
            "request_timeout_seconds": self.request_timeout_seconds,
        }


class ServerConfig:
    """Server configuration management."""

    def __init__(self, config_path: Path | None = None):
        """Initialize server configuration.

        Args:
            config_path: Optional path to configuration file
        """
        self.config_path = config_path or get_server_config_path()
        self._config_cache: dict[str, Any] | None = None

        # Hot-reload support
        self._callbacks: list[Callable[[dict[str, Any]], None]] = []
        self._watch_thread: threading.Thread | None = None
        self._stop_event: threading.Event | None = None

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
                "limits": {
                    "global": {
                        "max_requests_per_minute": None,
                        "max_concurrent_requests": None,
                        "max_input_length": None,
                        "request_timeout_seconds": None,
                    },
                    "per_token": {},
                },
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

            # Write to a temporary file in the same directory first, then atomically
            # replace the target path. This guarantees that any watcher thread will
            # either see the *previous* complete file or the *new* complete file,
            # but never a partially-written one, eliminating race conditions that
            # caused CI flakes.
            with tempfile.NamedTemporaryFile(
                "w",
                dir=self.config_path.parent,
                suffix=self.config_path.suffix or "",
                delete=False,
                encoding="utf-8",
            ) as tmp_file:
                if self.config_path.suffix.lower() == ".json":
                    json.dump(config, tmp_file, indent=2)
                else:
                    yaml.dump(config, tmp_file, default_flow_style=False, indent=2)

                # Flush buffers and fsync to ensure data is on disk before rename.
                tmp_file.flush()
                os.fsync(tmp_file.fileno())

            os.replace(tmp_file.name, self.config_path)

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
        # 1. Check for runtime overrides first - these have highest precedence.
        is_overridden, override_val = server_overrides.get_override(key)
        if is_overridden:
            return override_val

        # 2. Fallback to persisted configuration.
        config_result = self.load()

        if isinstance(config_result, Error):
            # Fail-open: fall back to last known good cache if present.
            if self._config_cache is not None:
                config: dict[str, Any] = self._config_cache
            else:
                logger.warning(
                    "Failed to load config for get(%s): %s", key, config_result.error
                )
                return default
        else:
            # Success branch - mypy can now see `data` is present.
            config = cast(dict[str, Any], config_result.data)

        if config is None:
            return default

        keys = key.split(".")

        try:
            value = config
            for k in keys:
                if value is None:
                    return default
                value = value[k]

            # If the value we found equals the *default* config value but we have a
            # previously cached config (and we are *not* already using that
            # cache), try again against the cache.  This guards against the case
            # where a hot-reload attempt failed (e.g. invalid YAML) and we fell
            # back to defaults on the most recent load, but the caller still
            # expects the last known-good value.

            if self._config_cache is not None and config is not self._config_cache:
                try:
                    cached_val: Any = self._config_cache
                    for k in keys:
                        cached_val = cached_val[k]
                    return cached_val
                except Exception:  # pragma: no cover
                    pass  # Fall through to original value

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

            # Validate limits section
            limits_section = server_section.get("limits", {})

            # Ensure required sub-sections exist even if empty.
            if "global" not in limits_section:
                limits_section["global"] = {}
            if "per_token" not in limits_section:
                limits_section["per_token"] = {}

            # Validate & sanitise global limits
            result_global = self._sanitize_limits_dict(limits_section["global"])
            if isinstance(result_global, Error):
                return result_global
            limits_section["global"] = result_global.data

            # Validate each per-token block
            for token_key, token_limits in list(
                limits_section.get("per_token", {}).items()
            ):
                if not isinstance(token_limits, dict):
                    return Error(
                        error=f"per_token entry for {token_key} must be a mapping"
                    )

                result_token = self._sanitize_limits_dict(token_limits)
                if isinstance(result_token, Error):
                    return result_token
                limits_section["per_token"][token_key] = result_token.data

            # Persist sanitized limits back to config
            server_section["limits"] = limits_section

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

    def _sanitize_limits_dict(self, limits_dict: dict[str, object]) -> Result:
        """Validate & sanitise a limits dictionary in-place.

        The input is expected to be a mapping of *limit keys* to raw values. Strings are
        coerced to ints. On success, returns a new dict with sanitised values which can
        be safely merged back into the config structure.
        """

        cleaned: dict[str, int | None] = {}

        for attr in (
            "max_requests_per_minute",
            "max_concurrent_requests",
            "max_input_length",
            "request_timeout_seconds",
        ):
            value = limits_dict.get(attr)
            validated = self._validate_limit_value(value, attr)
            if isinstance(validated, Error):
                return validated
            cleaned[attr] = validated

        return Success(data=cleaned)

    def _validate_limit_value(self, raw: Any, key: str) -> int | None | Error:
        """Validate a single numeric limit value.

        Args:
            raw: Raw value from configuration (may be ``None`` or string).
            key: Friendly name for error messages.

        Returns:
            ``int`` or ``None`` on success, or an ``Error`` instance when invalid.
        """

        if raw is None:
            return None

        # Convert strings to int where possible.
        try:
            value_int = int(raw)
        except (ValueError, TypeError):
            return Error(error=f"Invalid {key} value: {raw!r} (must be integer)")

        if value_int < 1:
            return Error(error=f"{key} must be >= 1, got: {value_int}")

        return value_int

    def get_limits(self, token_sub: str | None = None) -> "Limits":
        """Return the *effective* limits for a JWT subject (or global defaults).

        Args:
            token_sub: The JWT ``sub`` (subject) or ``kid`` identifying the caller.
                       If ``None``, only the global limits are considered.

        Returns:
            A :class:`Limits` instance with any unspecified dimensions set to
            ``None`` (meaning *unlimited*).
        """

        config_result = self.load()
        if isinstance(config_result, Error) or config_result.data is None:
            # Fail-open (no limits) if configuration cannot be loaded.
            return Limits()

        cfg = config_result.data
        limits_cfg = cfg.get("server", {}).get("limits", {})

        global_cfg = (
            limits_cfg.get("global", {}) if isinstance(limits_cfg, dict) else {}
        )

        # Extract per-token overrides if present
        per_token_cfg: dict[str, Any] = {}
        if token_sub is not None and isinstance(limits_cfg, dict):
            per_token_cfg = (
                limits_cfg.get("per_token", {}).get(token_sub, {})
                if isinstance(limits_cfg.get("per_token", {}), dict)
                else {}
            )

        # Merge per-token over global (token-specific keys override globals)
        merged: dict[str, int | None] = {**global_cfg, **per_token_cfg}

        # Apply ContextVar overrides for global limit keys (token-specific overrides
        # are not supported yet but can be added following the same pattern).
        override_paths: dict[str, str] = {
            "max_requests_per_minute": "server.limits.global.max_requests_per_minute",
            "max_concurrent_requests": "server.limits.global.max_concurrent_requests",
            "max_input_length": "server.limits.global.max_input_length",
            "request_timeout_seconds": "server.limits.global.request_timeout_seconds",
        }
        for attr, path in override_paths.items():
            is_overridden, value = server_overrides.get_override(path)
            if is_overridden:
                merged[attr] = value

        # Sanitize (re-use helper)
        sanitised_result = self._sanitize_limits_dict(cast(dict[str, object], merged))
        if isinstance(sanitised_result, Error):
            # Config invalid - treat as unlimited, but log for diagnostics.
            logger.warning(
                "Invalid limits configuration detected for token %s: %s",
                token_sub,
                sanitised_result.error,
            )
            return Limits()

        clean_dict: dict[str, int | None] = sanitised_result.data or {}

        return Limits(
            max_requests_per_minute=clean_dict.get("max_requests_per_minute"),
            max_concurrent_requests=clean_dict.get("max_concurrent_requests"),
            max_input_length=clean_dict.get("max_input_length"),
            request_timeout_seconds=clean_dict.get("request_timeout_seconds"),
        )

    # ---------------------------------------------------------------------
    # Hot-reload / subscription API
    # ---------------------------------------------------------------------

    def subscribe(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Register *callback* invoked with new config after each successful reload."""

        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def unsubscribe(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Remove previously registered callback."""

        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def start_auto_reload(self, poll_interval: float = 1.0) -> None:
        """Begin background polling of the config file for changes."""

        if self._watch_thread and self._watch_thread.is_alive():
            return  # Already running

        self._stop_event = threading.Event()

        # Capture the file's current modification time *before* starting the
        # watcher thread.  Doing this in the caller thread eliminates a race
        # condition in which the file is modified between the time the caller
        # invokes ``start_auto_reload`` and the background thread computes the
        # initial ``last_mtime`` value, resulting in missed change events in
        # very fast test scenarios.
        last_mtime: int | None = (
            self.config_path.stat().st_mtime_ns if self.config_path.exists() else None
        )

        def _watch() -> None:
            nonlocal last_mtime
            # The loop will compare the current mtime against ``last_mtime`` and
            # invoke callbacks when they differ.
            while self._stop_event and not self._stop_event.is_set():
                try:
                    current_mtime: int | None = (
                        self.config_path.stat().st_mtime_ns
                        if self.config_path.exists()
                        else None
                    )
                    if current_mtime != last_mtime:
                        # Attempt to reload the config (always forced to bypass any
                        # cached version).
                        result = self.load(force_reload=True)
                        if isinstance(result, Success) and result.data is not None:
                            last_mtime = current_mtime

                            for cb in list(self._callbacks):
                                try:
                                    cb(result.data)
                                except Exception:  # pragma: no cover
                                    # User callbacks should never break the watcher
                                    logger.exception("Config reload callback raised")
                    # Sleep for the configured poll interval before checking again.
                    time.sleep(poll_interval)
                except Exception:  # pragma: no cover
                    logger.exception("Exception in config auto-reload watcher")
                    time.sleep(poll_interval)

        self._watch_thread = threading.Thread(
            target=_watch, name="ServerConfigAutoReload", daemon=True
        )
        self._watch_thread.start()

    def stop_auto_reload(self) -> None:
        """Stop background config polling."""

        if self._stop_event:
            self._stop_event.set()
        if self._watch_thread and self._watch_thread.is_alive():
            self._watch_thread.join(timeout=2)
        self._watch_thread = None
        self._stop_event = None


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
            "limits": {
                "global": {
                    "max_requests_per_minute": None,
                    "max_concurrent_requests": None,
                    "max_input_length": None,
                    "request_timeout_seconds": None,
                },
                "per_token": {},
            },
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
