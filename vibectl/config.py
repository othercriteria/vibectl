"""Configuration management for vibectl"""

import copy
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar, cast
from urllib.parse import urlparse

# Import shared configuration utilities
from .config_utils import (
    convert_string_to_type,
    ensure_config_dir,
    get_nested_value,
    load_yaml_config,
    save_yaml_config,
    set_nested_value,
    validate_config_key_path,
    validate_numeric_range,
)

# Import the adapter function to use for validation
from .llm_interface import is_valid_llm_model_name

# Default values - Hierarchical structure
DEFAULT_CONFIG: dict[str, Any] = {
    "core": {
        "kubeconfig": None,  # Will use default kubectl config location if None
        "kubectl_command": "kubectl",
    },
    "display": {
        "theme": "default",
        "show_raw_output": False,
        "show_vibe": True,
        "show_kubectl": False,  # Show kubectl commands when they are executed
        "show_memory": True,  # Show memory content before each auto/semiauto iteration
        "show_iterations": True,  # Show iteration count in auto/semiauto mode
        "show_metrics": "none",  # Show LLM metrics (none/total/sub/all)
        "colored_output": True,
        "show_streaming": True,  # Show intermediate streaming Vibe output
    },
    "llm": {
        "model": "claude-3.7-sonnet",  # Default LLM model to use
        "max_retries": 2,  # Max retries for LLM calls
        "retry_delay_seconds": 1.0,  # Delay between retries
    },
    "providers": {
        "openai": {
            "key": None,  # OpenAI API key
            "key_file": None,  # Path to file containing OpenAI API key
        },
        "anthropic": {
            "key": None,  # Anthropic API key
            "key_file": None,  # Path to file containing Anthropic API key
        },
        "ollama": {
            "key": None,  # Ollama API key (if needed)
            "key_file": None,  # Path to file containing Ollama API key (if needed)
        },
    },
    "memory": {
        "enabled": True,
        "max_chars": 500,
    },
    "warnings": {
        "warn_no_output": True,
        "warn_no_proxy": True,  # Show warning when intermediate_port_range is not set
        "warn_sanitization": True,  # Show warning when request sanitization occurs
    },
    "live_display": {
        "max_lines": 20,  # Default number of lines for live display
        "wrap_text": True,  # Default to wrapping text in live display
        "stream_buffer_max_lines": 100000,  # Max lines for in-memory stream
        "default_filter_regex": None,  # Default regex filter (string or None)
        "save_dir": ".",  # Default directory to save watch output logs
    },
    "features": {
        "intelligent_apply": True,  # Enable intelligent apply features
        "intelligent_edit": True,  # Enable intelligent edit features
        "max_correction_retries": 1,
        "check_max_iterations": 10,  # Default max iterations for 'vibectl check'
    },
    "networking": {
        "intermediate_port_range": None,  # Port range for intermediary port-forwarding
    },
    "plugins": {
        "precedence": [],  # Plugin precedence order; empty list = no explicit order
    },
    "proxy": {
        # Global proxy defaults (can be overridden by individual profiles)
        "timeout_seconds": 30,  # Request timeout for proxy calls
        "retry_attempts": 3,  # Number of retry attempts for failed proxy calls
        # Named proxy profile structure
        "active": None,  # Active profile name (None = proxy disabled)
        "profiles": {},  # Named proxy profiles with individual settings
    },
    "system": {
        "log_level": "WARNING",  # Default log level for logging
        "custom_instructions": None,
    },
    # Auto-managed by vibectl memory commands - keep at top level for now
    "memory_content": None,
}

# Define type for expected types that can be a single type or a tuple of types
ConfigType = type | tuple[type, ...]

# T is a generic type variable for return type annotation
T = TypeVar("T")

# Valid configuration keys and their types - Hierarchical structure
CONFIG_SCHEMA: dict[str, Any] = {
    "core": {
        "kubeconfig": (str, type(None)),
        "kubectl_command": str,
    },
    "display": {
        "theme": str,
        "show_raw_output": bool,
        "show_vibe": bool,
        "show_kubectl": bool,
        "show_memory": bool,
        "show_iterations": bool,
        "show_metrics": str,  # Show LLM metrics
        "colored_output": bool,
        "show_streaming": bool,
    },
    "llm": {
        "model": str,
        "max_retries": int,
        "retry_delay_seconds": float,
    },
    "providers": {
        "openai": {
            "key": (str, type(None)),
            "key_file": (str, type(None)),
        },
        "anthropic": {
            "key": (str, type(None)),
            "key_file": (str, type(None)),
        },
        "ollama": {
            "key": (str, type(None)),
            "key_file": (str, type(None)),
        },
    },
    "memory": {
        "enabled": bool,
        "max_chars": int,
    },
    "warnings": {
        "warn_no_output": bool,
        "warn_no_proxy": bool,
        "warn_sanitization": bool,
    },
    "live_display": {
        "max_lines": int,
        "wrap_text": bool,
        "stream_buffer_max_lines": int,
        "default_filter_regex": (str, type(None)),
        "save_dir": str,
    },
    "features": {
        "intelligent_apply": bool,
        "intelligent_edit": bool,
        "max_correction_retries": int,
        "check_max_iterations": int,
    },
    "networking": {
        "intermediate_port_range": (str, type(None)),
    },
    "plugins": {
        "precedence": list,
    },
    "proxy": {
        # Global proxy defaults
        "timeout_seconds": int,
        "retry_attempts": int,
        # Named proxy profile structure
        "active": (str, type(None)),  # Active profile name
        "profiles": dict,  # Named proxy profiles
    },
    "system": {
        "log_level": str,
        "custom_instructions": (str, type(None)),
    },
    # Top-level items that remain
    "memory_content": (str, type(None)),
}

# Valid values for specific keys
CONFIG_VALID_VALUES: dict[str, list[Any]] = {
    "theme": ["default", "dark", "light", "accessible"],
    "model": [
        "gpt-4",
        "gpt-3.5-turbo",
        "claude-3.7-sonnet",
        "claude-3.7-opus",
        "ollama:llama3",
    ],
    "log_level": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    "show_metrics": ["none", "total", "sub", "all"],  # Only support enum string values
}

# Range constraints for numeric proxy settings
PROXY_CONSTRAINTS = {
    "timeout_seconds": {"min": 1, "max": 300},  # 1 second to 5 minutes
    "retry_attempts": {"min": 0, "max": 10},  # 0 to 10 retries
}

# Environment variable mappings for API keys
ENV_KEY_MAPPINGS = {
    "openai": {
        "key": "VIBECTL_OPENAI_API_KEY",
        "key_file": "VIBECTL_OPENAI_API_KEY_FILE",
    },
    "anthropic": {
        "key": "VIBECTL_ANTHROPIC_API_KEY",
        "key_file": "VIBECTL_ANTHROPIC_API_KEY_FILE",
    },
    "ollama": {
        "key": "VIBECTL_OLLAMA_API_KEY",
        "key_file": "VIBECTL_OLLAMA_API_KEY_FILE",
    },
}


class Config:
    """Manages vibectl configuration"""

    def __init__(self, base_dir: Path | None = None) -> None:
        """Initialize configuration.

        Args:
            base_dir: Optional base directory for configuration (used in testing)
        """
        # Use shared utility to get config directory
        self.config_dir = ensure_config_dir("client", base_dir)
        self.config_file = self.config_dir / "config.yaml"
        self._config: dict[str, Any] = {}

        # Load or create default config using shared utilities
        self._config = load_yaml_config(self.config_file, DEFAULT_CONFIG)
        if not self.config_file.exists():
            self._save_config()

    def _save_config(self) -> None:
        """Save configuration to file."""
        save_yaml_config(self._config, self.config_file)

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value.

        The lookup order is:
        1. **CLI override** set via :pymod:`vibectl.overrides` (ContextVar)
        2. Persisted configuration file (self._config)
        3. Explicit *default* parameter
        """

        # ------------------------------------------------------------------
        # Deprecation shim for legacy keys
        # ------------------------------------------------------------------
        # Historically the key for user-supplied custom instructions lived at
        # the *top level* of the config as ``custom_instructions``.  The new
        # canonical location is ``system.custom_instructions``.  To avoid
        # breaking existing user configs and in-flight migrations we still
        # honour the legacy key *read-only* while emitting an explicit
        # deprecation warning.  Write operations **must** target the new key.
        #
        # NOTE:  The shim is intentionally placed *before* override handling
        # so that overrides continue to work transparently when callers still
        # reference the old key.
        if key == "custom_instructions":
            import warnings

            warnings.warn(
                "Config key 'custom_instructions' is deprecated; use "
                "'system.custom_instructions' instead.",
                DeprecationWarning,
                stacklevel=2,
            )

            # Redirect lookup to the new namespaced key while preserving the
            # original precedence rules (CLI overrides > persisted config >
            # supplied default).
            redirected_key = "system.custom_instructions"

            # 1. CLI override check for the *new* key
            try:
                from .overrides import get_override  # type: ignore

                overridden, value = get_override(redirected_key)
                if overridden:
                    return value
            except Exception:
                # If overrides module is unavailable (e.g., during certain
                # test setups) fall through to persisted config lookup.
                pass

            # 2. Persisted configuration lookup for the new key
            try:
                return get_nested_value(self._config, redirected_key)
            except KeyError:
                # 3. Fallback to the caller-supplied default
                return default

        # 1. Check for runtime override first
        try:
            from .overrides import (
                get_override,  # Local import to avoid cycles during tests
            )

            overridden, value = get_override(key)
            if overridden:
                return value
        except Exception:
            # If overrides module is not available for some reason, fall through.
            pass

        # 2. Fall back to persisted configuration
        if "." in key:
            # Hierarchical path like 'display.theme'
            try:
                return get_nested_value(self._config, key)
            except KeyError:
                return default
        else:
            # Top-level key
            return self._config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a configuration value."""
        if "." in key:
            # Hierarchical key - validate it exists in schema
            validate_config_key_path(key, CONFIG_SCHEMA)

            # Convert value based on expected type
            if isinstance(value, str):
                # Get the expected type from schema
                parts = key.split(".")
                current_schema: Any = CONFIG_SCHEMA
                for part in parts:
                    current_schema = current_schema[part]
                # current_schema should now be the type annotation
                # (str, bool, tuple, etc.)
                expected_type: type | tuple[type, ...] = current_schema
                converted_value = convert_string_to_type(value, expected_type, key)
            else:
                converted_value = value
            # Validate the converted value
            self._validate_hierarchical_value(key, converted_value)
            set_nested_value(self._config, key, converted_value)
        else:
            # Top-level key
            if key not in CONFIG_SCHEMA:
                valid_keys = list(CONFIG_SCHEMA.keys())
                raise ValueError(
                    f"Unknown configuration key: {key}. Valid sections: {valid_keys}"
                )
            # For top-level keys, just set directly
            self._config[key] = value

        self._save_config()

    def _validate_hierarchical_value(self, path: str, value: Any) -> None:
        """Validate a hierarchical value against constraints."""
        # Get the schema for this path to check if None is allowed
        parts = path.split(".")
        current_schema = CONFIG_SCHEMA

        for part in parts:
            current_schema = current_schema[part]

        expected_type = current_schema

        # Check if None is allowed for this field
        if value is None:
            if isinstance(expected_type, tuple) and type(None) in expected_type:
                return  # None is allowed
            else:
                # This field doesn't allow None - suggest unset which resets to default
                error_msg = f"None is not a valid value for {path}"
                error_msg += "\n\nTo reset this setting to its default, use: "
                error_msg += f"vibectl config unset {path}"
                raise ValueError(error_msg)

        # Extract the key name for validation lookup
        key_name = parts[-1]  # Last part is the actual key name

        # Special validation for proxy configuration
        if len(parts) >= 2 and parts[0] == "proxy":
            self._validate_proxy_value(path, key_name, value)

        # Check against CONFIG_VALID_VALUES if it exists for this key
        if key_name in CONFIG_VALID_VALUES:
            valid_values = CONFIG_VALID_VALUES[key_name]

            # Special handling for model validation with LLM interface
            if key_name == "model":
                is_valid, validation_error = is_valid_llm_model_name(str(value))
                if not is_valid:
                    error_msg = validation_error or f"Invalid model: {value}"
                    raise ValueError(error_msg)
            else:
                # Standard validation against allowed values
                if value not in valid_values:
                    # Check if this field allows None values to suggest using unset
                    allows_none = (
                        isinstance(expected_type, tuple) and type(None) in expected_type
                    )
                    error_msg = (
                        f"Invalid value for {path}: {value}. "
                        f"Valid values are: {valid_values}"
                    )
                    if allows_none:
                        error_msg += "\n\nTo clear this setting, use: "
                        error_msg += f"vibectl config unset {path}"
                    raise ValueError(error_msg)

    def _validate_proxy_value(self, path: str, key_name: str, value: Any) -> None:
        """Validate proxy-specific configuration values."""
        if key_name == "server_url" and value is not None:
            # Validate proxy URL format
            try:
                proxy_config = parse_proxy_url(str(value))
                if proxy_config is None:
                    raise ValueError("Invalid proxy URL format")
            except ValueError as e:
                raise ValueError(f"Invalid proxy URL for {path}: {e}") from e

        elif key_name in PROXY_CONSTRAINTS:
            # Validate numeric ranges for proxy settings
            constraint = PROXY_CONSTRAINTS[key_name]
            min_val = constraint["min"]
            max_val = constraint["max"]
            validate_numeric_range(value, min_val, max_val, path)

    def _validate_proxy_security_config(self, security_config: dict[str, Any]) -> None:
        """Validate security configuration for proxy profiles.

        Args:
            security_config: Security configuration dictionary

        Raises:
            ValueError: If security configuration is invalid
        """
        # Define valid security configuration keys and types
        valid_security_keys: dict[str, type | tuple[type, ...]] = {
            "sanitize_requests": bool,
            "audit_logging": bool,
            "confirmation_mode": str,
            "audit_log_path": (str, type(None)),
            "warn_sanitization": bool,
        }

        # Valid values for confirmation_mode
        valid_confirmation_modes = ["none", "per-session", "per-command"]

        for key, value in security_config.items():
            if key not in valid_security_keys:
                valid_keys = list(valid_security_keys.keys())
                raise ValueError(
                    f"Unknown security configuration key: {key}. "
                    f"Valid keys: {valid_keys}"
                )

            expected_type = valid_security_keys[key]

            # Check type
            if not isinstance(value, expected_type):
                if isinstance(expected_type, tuple):
                    type_names = [getattr(t, "__name__", str(t)) for t in expected_type]
                    type_desc = " or ".join(type_names)
                else:
                    type_desc = getattr(expected_type, "__name__", str(expected_type))
                raise ValueError(
                    f"Invalid type for security.{key}: expected {type_desc}, "
                    f"got {type(value).__name__}"
                )

            # Special validation for confirmation_mode
            if key == "confirmation_mode" and value not in valid_confirmation_modes:
                raise ValueError(
                    f"Invalid confirmation_mode: {value}. "
                    f"Valid values: {valid_confirmation_modes}"
                )

    def unset(self, key: str) -> None:
        """Unset a configuration key, resetting it to default."""
        if "." in key:
            # Hierarchical path - validate first, then reset to default
            # value from DEFAULT_CONFIG
            validate_config_key_path(key, CONFIG_SCHEMA)
            try:
                default_value = get_nested_value(DEFAULT_CONFIG, key)
                set_nested_value(self._config, key, default_value)
            except KeyError as err:
                raise ValueError(f"Config path not found: {key}") from err
        else:
            # Top-level key - validate first
            if key not in CONFIG_SCHEMA:
                valid_keys = list(CONFIG_SCHEMA.keys())
                raise ValueError(
                    f"Unknown configuration key: {key}. Valid sections: {valid_keys}"
                )

            if key not in self._config:
                raise ValueError(f"Key not found in configuration: {key}")

            if key in DEFAULT_CONFIG:
                self._config[key] = copy.deepcopy(DEFAULT_CONFIG[key])
            else:
                del self._config[key]

        self._save_config()

    def get_all(self) -> dict[str, Any]:
        """Get all configuration values."""
        return copy.deepcopy(self._config)

    def show(self) -> dict[str, Any]:
        """Show the current configuration."""
        return self.get_all()

    def save(self) -> None:
        """Save the current configuration to disk."""
        self._save_config()

    def get_typed(self, key: str, default: T) -> T:
        """Get a typed configuration value with a default."""
        value = self.get(key, default)
        return cast("T", value)

    def get_available_themes(self) -> list[str]:
        """Get list of available themes."""
        return CONFIG_VALID_VALUES["theme"]

    def get_model_key(self, provider: str) -> str | None:
        """Get API key for a specific model provider."""
        # Check if we have mappings for this provider
        if provider not in ENV_KEY_MAPPINGS:
            return None

        # Get mapping for specific provider
        mapping = ENV_KEY_MAPPINGS[provider]

        # 1. Check environment variable override
        env_key = os.environ.get(mapping["key"])
        if env_key:
            return env_key

        # 2. Check environment variable key file
        env_key_file = os.environ.get(mapping["key_file"])
        if env_key_file:
            try:
                key_path = Path(env_key_file).expanduser()
                if key_path.exists():
                    return key_path.read_text().strip()
            except OSError:
                pass

        # 3. Check configured key
        provider_key = self.get(f"providers.{provider}.key")
        if provider_key:
            return str(provider_key)

        # 4. Check configured key file
        provider_key_file = self.get(f"providers.{provider}.key_file")
        if provider_key_file:
            try:
                key_path = Path(provider_key_file).expanduser()
                if key_path.exists():
                    return key_path.read_text().strip()
            except OSError:
                pass

        return None

    def set_model_key(self, provider: str, key: str) -> None:
        """Set API key for a specific model provider in the config."""
        if provider not in ENV_KEY_MAPPINGS:
            valid_providers = ", ".join(ENV_KEY_MAPPINGS.keys())
            raise ValueError(
                f"Invalid model provider: {provider}. "
                f"Valid providers are: {valid_providers}"
            )

        # Set the key in the new provider structure
        self.set(f"providers.{provider}.key", key)

    def set_model_key_file(self, provider: str, file_path: str) -> None:
        """Set path to key file for a specific model provider."""
        if provider not in ENV_KEY_MAPPINGS:
            valid_providers = ", ".join(ENV_KEY_MAPPINGS.keys())
            raise ValueError(
                f"Invalid model provider: {provider}. "
                f"Valid providers are: {valid_providers}"
            )

        # Verify the file exists
        path = Path(file_path).expanduser()
        if not path.exists():
            raise ValueError(f"Key file does not exist: {file_path}")

        # Set the file path in the new provider structure
        self.set(f"providers.{provider}.key_file", str(path))

    # Proxy Profile Management

    def get_active_proxy_profile(self) -> str | None:
        """Get the currently active proxy profile name.

        Returns:
            Active profile name, or None if no profile is active
        """
        active = self.get("proxy.active")
        return str(active) if active is not None else None

    def set_active_proxy_profile(self, profile_name: str | None) -> None:
        """Set the active proxy profile.

        Args:
            profile_name: Profile name to activate, or None to disable proxy
        """
        self.set("proxy.active", profile_name)

    def get_proxy_profile(self, profile_name: str) -> dict[str, Any] | None:
        """Get configuration for a specific proxy profile.

        Args:
            profile_name: Name of the profile to retrieve

        Returns:
            Profile configuration dict, or None if profile doesn't exist
        """
        profiles = self.get("proxy.profiles", {})
        if isinstance(profiles, dict):
            return profiles.get(profile_name)
        return None

    def set_proxy_profile(
        self, profile_name: str, profile_config: dict[str, Any]
    ) -> None:
        """Set configuration for a proxy profile.

        Args:
            profile_name: Name of the profile
            profile_config: Profile configuration dictionary
        """
        # Validate security configuration if present
        if "security" in profile_config:
            self._validate_proxy_security_config(profile_config["security"])

        profiles = self.get("proxy.profiles", {})
        profiles[profile_name] = profile_config
        self.set("proxy.profiles", profiles)

    def remove_proxy_profile(self, profile_name: str) -> bool:
        """Remove a proxy profile.

        Args:
            profile_name: Name of the profile to remove

        Returns:
            True if profile was removed, False if it didn't exist
        """
        profiles = self.get("proxy.profiles", {})
        if profile_name in profiles:
            del profiles[profile_name]
            self.set("proxy.profiles", profiles)

            # If we removed the active profile, deactivate proxy
            if self.get("proxy.active") == profile_name:
                self.set("proxy.active", None)

            return True
        return False

    def list_proxy_profiles(self) -> list[str]:
        """List all configured proxy profile names.

        Returns:
            List of profile names
        """
        profiles = self.get("proxy.profiles", {})
        return list(profiles.keys())

    def is_proxy_enabled(self) -> bool:
        """Check if proxy mode is enabled (has an active profile).

        Returns:
            True if proxy is enabled
        """
        return self.get("proxy.active") is not None

    def get_effective_proxy_config(self) -> dict[str, Any] | None:
        """Get the effective proxy configuration by merging global and profile settings.

        Returns:
            Merged proxy configuration, or None if no active profile
        """
        active_profile = self.get_active_proxy_profile()
        if not active_profile:
            return None

        profile_config = self.get_proxy_profile(active_profile)
        if not profile_config:
            return None

        # Start with global proxy defaults
        effective_config = {
            "timeout_seconds": self.get("proxy.timeout_seconds", 30),
            "retry_attempts": self.get("proxy.retry_attempts", 3),
        }

        # Override with profile-specific settings
        effective_config.update(profile_config)

        return effective_config

    def get_ca_bundle_path(self) -> str | None:
        """Get CA bundle path for proxy connections.

        Checks environment variable first, then active proxy profile.

        Returns:
            Path to CA bundle file, or None if not configured
        """
        import os

        # Check environment variable first (takes precedence)
        env_ca_bundle = os.environ.get("VIBECTL_CA_BUNDLE")
        if env_ca_bundle:
            return env_ca_bundle

        # Check active proxy profile for CA bundle
        effective_config = self.get_effective_proxy_config()
        if effective_config:
            return effective_config.get("ca_bundle_path")

        return None


# Proxy URL parsing utilities


@dataclass
class ProxyConfig:
    """Configuration for LLM proxy connection."""

    host: str
    port: int
    jwt_token: str | None = None
    use_tls: bool = True
    ca_bundle_path: str | None = None


def parse_proxy_url(url: str) -> ProxyConfig:
    """Parse a proxy URL into a ProxyConfig.

    Supports these URL schemes:
    - vibectl-server://jwt-token@host:port (TLS with certificate verification)
    - vibectl-server://host:port (TLS with certificate verification, no auth)
    - vibectl-server-insecure://jwt-token@host:port (no TLS)
    - vibectl-server-insecure://host:port (no TLS, no auth)

    CA bundle configuration is handled separately via:
    - VIBECTL_CA_BUNDLE environment variable
    - proxy.ca_bundle_path configuration value

    Args:
        url: The proxy URL to parse

    Returns:
        ProxyConfig: Parsed configuration

    Raises:
        ValueError: If the URL is invalid or unsupported
    """
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise ValueError(f"Invalid URL format: {e}") from e

    # Parse scheme and determine TLS settings
    if parsed.scheme == "vibectl-server":
        use_tls = True
    elif parsed.scheme == "vibectl-server-insecure":
        use_tls = False
    else:
        raise ValueError(
            f"Unsupported scheme '{parsed.scheme}'. "
            f"Expected 'vibectl-server' or 'vibectl-server-insecure'"
        )

    # Parse host and port
    if not parsed.hostname:
        raise ValueError(f"Host is required in URL: {url}")

    host = parsed.hostname
    port = parsed.port if parsed.port is not None else 50051

    # Parse JWT token from username part
    jwt_token = parsed.username if parsed.username else None

    return ProxyConfig(
        host=host,
        port=port,
        jwt_token=jwt_token,
        use_tls=use_tls,
        ca_bundle_path=None,  # CA bundle will be resolved separately
    )


def build_proxy_url(host: str, port: int, jwt_token: str | None = None) -> str:
    """Build a proxy URL from components.

    Args:
        host: Server hostname
        port: Server port
        jwt_token: Optional JWT authentication token

    Returns:
        Formatted proxy URL
    """
    if jwt_token:
        return f"vibectl-server://{jwt_token}@{host}:{port}"
    else:
        return f"vibectl-server://{host}:{port}"
