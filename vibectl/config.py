"""Configuration management for vibectl"""

import copy
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar, cast
from urllib.parse import urlparse

import yaml

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
        "enabled": False,  # Enable proxy mode for LLM calls
        "server_url": None,  # Server URL, e.g., vibectl-server://secret@llm-server.company.com:443
        "timeout_seconds": 30,  # Request timeout for proxy calls
        "retry_attempts": 3,  # Number of retry attempts for failed proxy calls
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
        "enabled": bool,
        "server_url": (str, type(None)),
        "timeout_seconds": int,
        "retry_attempts": int,
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


def _get_nested_value(config: dict[str, Any], path: str) -> Any:
    """Get a value from nested config using dotted path notation.

    Args:
        config: The config dictionary
        path: Dotted path like 'display.theme' or 'llm.model_keys'

    Returns:
        The value at the specified path

    Raises:
        KeyError: If the path doesn't exist
    """
    parts = path.split(".")
    current = config

    for part in parts:
        if not isinstance(current, dict) or part not in current:
            raise KeyError(f"Config path not found: {path}")
        current = current[part]

    return current


def _set_nested_value(config: dict[str, Any], path: str, value: Any) -> None:
    """Set a value in nested config using dotted path notation.

    Args:
        config: The config dictionary to modify
        path: Dotted path like 'display.theme' or 'llm.model_keys'
        value: The value to set
    """
    parts = path.split(".")
    current = config

    # Navigate to the parent of the final key
    for part in parts[:-1]:
        if part not in current:
            current[part] = {}
        elif not isinstance(current[part], dict):
            raise ValueError(f"Cannot set nested value: {part} is not a dictionary")
        current = current[part]

    # Set the final key
    current[parts[-1]] = value


def _validate_hierarchical_key(path: str) -> None:
    """Validate that a hierarchical path exists in the schema.

    Args:
        path: Dotted path like 'display.theme'

    Raises:
        ValueError: If the path is invalid
    """
    parts = path.split(".")
    current_schema = CONFIG_SCHEMA

    for i, part in enumerate(parts):
        if not isinstance(current_schema, dict) or part not in current_schema:
            # Generate helpful error message
            current_path = ".".join(parts[:i])
            if current_path:
                available_keys = (
                    list(current_schema.keys())
                    if isinstance(current_schema, dict)
                    else []
                )
                raise ValueError(
                    f"Invalid config path: {path}. "
                    f"'{part}' not found in section '{current_path}'. "
                    f"Available keys: {available_keys}"
                )
            else:
                available_sections = list(CONFIG_SCHEMA.keys())
                raise ValueError(
                    f"Invalid config section: {part}. "
                    f"Available sections: {available_sections}"
                )
        current_schema = current_schema[part]


class Config:
    """Manages vibectl configuration"""

    def __init__(self, base_dir: Path | None = None) -> None:
        """Initialize configuration.

        Args:
            base_dir: Optional base directory for configuration (used in testing)
        """
        # Use provided base directory first (for testing), then
        # environment variable, then default
        if base_dir is not None:
            self.config_dir = base_dir / ".config" / "vibectl" / "client"
        else:
            env_config_dir = os.environ.get("VIBECTL_CONFIG_DIR")
            if env_config_dir:
                self.config_dir = Path(env_config_dir)
            else:
                self.config_dir = Path.home() / ".config" / "vibectl" / "client"

        self.config_file = self.config_dir / "config.yaml"
        self._config: dict[str, Any] = {}

        # Create config directory if it doesn't exist
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # Load or create default config
        if self.config_file.exists():
            self._load_config()
        else:
            self._config = copy.deepcopy(DEFAULT_CONFIG)
            self._save_config()

    def _load_config(self) -> None:
        """Load configuration from file."""
        try:
            # First check if the file is empty
            if self.config_file.stat().st_size == 0:
                # Handle empty file as an empty dictionary
                loaded_config: dict[str, Any] = {}
            else:
                with open(self.config_file, encoding="utf-8") as f:
                    loaded_config = yaml.safe_load(f) or {}

            # Start with a copy of the default config
            self._config = copy.deepcopy(DEFAULT_CONFIG)
            # Deep merge the loaded config into defaults
            self._deep_merge(self._config, loaded_config)
        except (yaml.YAMLError, OSError) as e:
            raise ValueError(f"Failed to load config: {e}") from e

    def _deep_merge(self, base: dict[str, Any], updates: dict[str, Any]) -> None:
        """Deep merge updates into base dictionary."""
        for key, value in updates.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def _save_config(self) -> None:
        """Save configuration to file."""
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                yaml.dump(self._config, f, default_flow_style=False)
        except (yaml.YAMLError, OSError) as e:
            raise ValueError(f"Failed to save config: {e}") from e

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value using either flat key or dotted path."""
        if "." in key:
            # Hierarchical path like 'display.theme'
            try:
                return _get_nested_value(self._config, key)
            except KeyError:
                return default
        else:
            # Top-level key
            return self._config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set configuration value using either flat key or dotted path."""
        if "." in key:
            # Hierarchical path like 'display.theme'
            _validate_hierarchical_key(key)
            # Convert string values to appropriate types
            converted_value = self._convert_hierarchical_value(key, value)
            # Validate the converted value
            self._validate_hierarchical_value(key, converted_value)
            _set_nested_value(self._config, key, converted_value)
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
                raise ValueError(f"None is not a valid value for {path}")

        # Extract the key name for validation lookup
        key_name = parts[-1]  # Last part is the actual key name

        # Check against CONFIG_VALID_VALUES if it exists for this key
        if key_name in CONFIG_VALID_VALUES:
            valid_values = CONFIG_VALID_VALUES[key_name]

            # Special handling for model validation with LLM interface
            if key_name == "model":
                is_valid, error_msg = is_valid_llm_model_name(str(value))
                if not is_valid:
                    raise ValueError(error_msg or f"Invalid model: {value}")
            else:
                # Standard validation against allowed values
                if value not in valid_values:
                    raise ValueError(
                        f"Invalid value for {path}: {value}. "
                        f"Valid values are: {valid_values}"
                    )

    def _convert_hierarchical_value(self, path: str, value: Any) -> Any:
        """Convert string value to appropriate type for hierarchical path."""
        try:
            # Get the expected type from schema
            parts = path.split(".")
            current_schema = CONFIG_SCHEMA

            for part in parts:
                current_schema = current_schema[part]

            expected_type = current_schema

            # If value is already the right type, return it
            if not isinstance(value, str):
                return value

            # Always convert string "none" to Python None first
            if value.lower() == "none":
                return None

            # Convert string to appropriate type
            if expected_type is bool:
                return self._convert_to_bool(path, value)
            elif expected_type is int:
                return int(value)
            elif expected_type is float:
                return float(value)
            elif expected_type is list:
                return self._convert_to_list(path, value)
            elif isinstance(expected_type, tuple):
                # Convert to the first non-None type in the tuple
                for t in expected_type:
                    if t is not type(None):
                        if t is bool:
                            return self._convert_to_bool(path, value)
                        elif t is int:
                            return int(value)
                        elif t is float:
                            return float(value)
                        elif t is str:
                            return value
                        elif t is list:
                            return self._convert_to_list(path, value)
                        else:
                            # Handle custom class types in tuple
                            return t(value)
                        break
            elif isinstance(expected_type, type):
                # Handle custom class types - attempt to instantiate
                return expected_type(value)

            # Default to string
            return value
        except (ValueError, TypeError) as e:
            # Re-raise with better error message that includes the path
            if "Invalid value for" in str(e):
                raise  # Don't double-wrap our custom errors
            raise ValueError(f"Invalid value for {path}: {e}") from e

    def _convert_to_bool(self, key: str, value: str) -> bool:
        """Convert a string value to a boolean."""
        if value.lower() in ("true", "yes", "1", "on"):
            return True
        if value.lower() in ("false", "no", "0", "off"):
            return False
        raise ValueError(
            f"Invalid boolean value for {key}: {value}. "
            f"Use true/false, yes/no, 1/0, or on/off"
        )

    def _convert_to_list(self, key: str, value: str) -> list[Any]:
        """Convert a string value to a list."""
        # Handle string representation of lists (e.g., "['item1', 'item2']")
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            try:
                import ast

                parsed = ast.literal_eval(value)
                if isinstance(parsed, list):
                    return parsed
            except (ValueError, SyntaxError):
                pass  # Fall through to comma-separated parsing

        # Handle comma-separated values
        if "," in value:
            items = [item.strip().strip("\"'") for item in value.split(",")]
            return [item for item in items if item]  # Filter out empty strings

        # Handle single value
        if value:
            return [value.strip().strip("\"'")]

        # Empty string means empty list
        return []

    def unset(self, key: str) -> None:
        """Unset a configuration key, resetting it to default."""
        if "." in key:
            # Hierarchical path - validate first, then reset to default
            # value from DEFAULT_CONFIG
            _validate_hierarchical_key(key)
            try:
                default_value = _get_nested_value(DEFAULT_CONFIG, key)
                _set_nested_value(self._config, key, default_value)
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


# Proxy URL parsing utilities


@dataclass
class ProxyConfig:
    """Parsed proxy configuration from URL."""

    host: str
    port: int
    secret: str | None = None
    use_tls: bool = True


def parse_proxy_url(url: str | None) -> ProxyConfig | None:
    """Parse a proxy URL into connection details.

    Expected formats:
    - vibectl-server://secret@host:port (secure, TLS enabled)
    - vibectl-server://host:port (secure, no auth)
    - vibectl-server-insecure://secret@host:port (insecure, TLS disabled)
    - vibectl-server-insecure://host:port (insecure, no auth)

    Args:
        url: The proxy server URL

    Returns:
        ProxyConfig object with parsed details, or None if url is None/empty

    Raises:
        ValueError: If URL format is invalid
    """
    if not url:
        return None

    try:
        parsed = urlparse(url)

        # Validate scheme and determine TLS setting
        if parsed.scheme == "vibectl-server":
            use_tls = True
        elif parsed.scheme == "vibectl-server-insecure":
            use_tls = False
        else:
            raise ValueError(
                f"Invalid proxy URL scheme: {parsed.scheme}. "
                f"Expected 'vibectl-server' or 'vibectl-server-insecure'"
            )

        # Extract host and port
        if not parsed.hostname:
            raise ValueError("Proxy URL must include hostname")

        host = parsed.hostname
        port = parsed.port or 50051  # Default gRPC port

        # Extract secret from username part
        secret = parsed.username if parsed.username else None

        return ProxyConfig(host=host, port=port, secret=secret, use_tls=use_tls)
    except Exception as e:
        raise ValueError(f"Invalid proxy URL format: {e}") from e


def build_proxy_url(host: str, port: int, secret: str | None = None) -> str:
    """Build a proxy URL from components.

    Args:
        host: Server hostname
        port: Server port
        secret: Optional authentication secret

    Returns:
        Formatted proxy URL
    """
    if secret:
        return f"vibectl-server://{secret}@{host}:{port}"
    else:
        return f"vibectl-server://{host}:{port}"
