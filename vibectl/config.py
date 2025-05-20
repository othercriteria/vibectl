"""Configuration management for vibectl"""

import os
import re
from pathlib import Path
from typing import Any, TypeVar, cast

import yaml

# Import the adapter function to use for validation
# Remove this import as we'll use the llm_interface directly
# from .model_adapter import get_model_adapter
from .llm_interface import is_valid_llm_model_name

# Default values
DEFAULT_CONFIG = {
    "kubeconfig": None,  # Will use default kubectl config location if None
    "kubectl_command": "kubectl",
    "theme": "dark",
    "show_raw_output": False,
    "show_vibe": True,
    "show_kubectl": False,  # Show kubectl commands when they are executed
    "show_memory": False,  # Show memory content before each auto/semiauto iteration
    "show_iterations": False,  # Show iteration count in auto/semiauto mode
    "show_metrics": False,  # Show LLM metrics (latency, tokens)
    "model": "claude-3.7-sonnet",
    "memory_enabled": True,
    "memory_max_chars": 500,
    "warn_no_output": True,
    "warn_no_proxy": True,  # Show warning when intermediate_port_range is not set
    "colored_output": True,
    "intermediate_port_range": None,  # Port range for intermediary port-forwarding
    # Model Key Configuration Section
    "model_keys": {
        "openai": None,  # API key for OpenAI models
        "anthropic": None,  # API key for Anthropic models
        "ollama": None,  # Not usually needed, but for custom Ollama setups
    },
    "model_key_files": {
        "openai": None,  # Path to file containing OpenAI API key
        "anthropic": None,  # Path to file containing Anthropic API key
        "ollama": None,  # Path to file containing Ollama API key (if needed)
    },
    "log_level": "WARNING",  # Default log level for logging
    "live_display_max_lines": 20,  # Default number of lines for live display
    "live_display_wrap_text": True,  # Default to wrapping text in live display
    "live_display_stream_buffer_max_lines": 100000,  # Max lines for in-memory stream
    "live_display_default_filter_regex": None,  # Default regex filter (string or None)
    "live_display_save_dir": ".",  # Default directory to save watch output logs
    "intelligent_apply": True,  # Enable intelligent apply features
    "max_correction_retries": 1,
    "check_max_iterations": 10,  # Default max iterations for 'vibectl check'
}

# Define type for expected types that can be a single type or a tuple of types
ConfigType = type | tuple[type, ...]

# T is a generic type variable for return type annotation
T = TypeVar("T")

# Valid configuration keys and their types
CONFIG_SCHEMA: dict[str, ConfigType] = {
    "kubeconfig": (str, type(None)),
    "kubectl_command": str,
    "theme": str,
    "show_raw_output": bool,
    "show_vibe": bool,
    "show_kubectl": bool,
    "show_memory": bool,  # Show memory before each iteration in auto/semiauto mode
    "show_iterations": bool,  # Show iteration count and limit in auto/semiauto mode
    "show_metrics": bool,  # Show LLM metrics
    "warn_no_output": bool,
    "warn_no_proxy": bool,
    "model": str,
    "custom_instructions": (str, type(None)),
    "memory": (str, type(None)),
    "memory_enabled": bool,
    "memory_max_chars": int,
    "colored_output": bool,
    "intermediate_port_range": (
        str,
        type(None),
    ),  # Format: "min-max" (e.g., "10000-20000") or None to disable
    "model_keys": dict,
    "model_key_files": dict,
    "log_level": str,  # Log level for logging
    "live_display_max_lines": int,
    "live_display_wrap_text": bool,
    "live_display_stream_buffer_max_lines": int,
    "live_display_default_filter_regex": (str, type(None)),  # Allow str or None
    "live_display_save_dir": str,
    "intelligent_apply": bool,
    "max_correction_retries": int,
    "check_max_iterations": int,
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
}

# Environment variable mappings for API keys
ENV_KEY_MAPPINGS = {
    "openai": {
        "key": "VIBECTL_OPENAI_API_KEY",
        "key_file": "VIBECTL_OPENAI_API_KEY_FILE",
        "legacy_key": "OPENAI_API_KEY",
    },
    "anthropic": {
        "key": "VIBECTL_ANTHROPIC_API_KEY",
        "key_file": "VIBECTL_ANTHROPIC_API_KEY_FILE",
        "legacy_key": "ANTHROPIC_API_KEY",
    },
    "ollama": {
        "key": "VIBECTL_OLLAMA_API_KEY",
        "key_file": "VIBECTL_OLLAMA_API_KEY_FILE",
        "legacy_key": "OLLAMA_API_KEY",
    },
}


class Config:
    """Manages vibectl configuration"""

    def __init__(self, base_dir: Path | None = None) -> None:
        """Initialize configuration.

        Args:
            base_dir: Optional base directory for configuration (used in testing)
        """
        # Use environment variable, provided base directory, or default to user's home
        env_config_dir = os.environ.get("VIBECTL_CONFIG_DIR")
        if env_config_dir:
            self.config_dir = Path(env_config_dir)
        else:
            self.config_dir = (base_dir or Path.home()) / ".vibectl"

        self.config_file = self.config_dir / "config.yaml"
        self._config: dict[str, Any] = {}

        # Create config directory if it doesn't exist
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # Load or create default config
        if self.config_file.exists():
            self._load_config()
        else:
            self._config = DEFAULT_CONFIG.copy()
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
            self._config = DEFAULT_CONFIG.copy()
            # Update with all loaded values to ensure they take precedence
            # This preserves unsupported keys
            self._config.update(loaded_config)
        except (yaml.YAMLError, OSError) as e:
            raise ValueError(f"Failed to load config: {e}") from e

    def _save_config(self) -> None:
        """Save configuration to file."""
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                yaml.dump(self._config, f)
        except (yaml.YAMLError, OSError) as e:
            raise ValueError(f"Failed to save config: {e}") from e

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        return self._config.get(key, default)

    def _validate_key(self, key: str) -> None:
        """Validate that a key exists in the configuration schema.

        Args:
            key: The configuration key to validate

        Raises:
            ValueError: If the key is invalid
        """
        if key not in CONFIG_SCHEMA:
            valid_keys = ", ".join(CONFIG_SCHEMA.keys())
            raise ValueError(
                f"Unknown configuration key: {key}. Valid keys are: {valid_keys}"
            )

    def _convert_to_type(self, key: str, value: str) -> Any:
        """Convert a string value to the correct type based on the schema.

        Args:
            key: The configuration key
            value: The string value to convert

        Returns:
            The value converted to the correct type

        Raises:
            ValueError: If the value can't be converted to the expected type
        """
        expected_type = CONFIG_SCHEMA[key]

        # Handle None special case
        if value.lower() == "none":
            if isinstance(expected_type, tuple) and type(None) in expected_type:
                return None
            raise ValueError(f"None is not a valid value for {key}")

        # Handle boolean conversion
        if (isinstance(expected_type, type) and expected_type is bool) or (
            isinstance(expected_type, tuple) and bool in expected_type
        ):
            return self._convert_to_bool(key, value)

        # Handle other types
        try:
            if isinstance(expected_type, tuple):
                # Use the first non-None type for conversion
                for t in expected_type:
                    if t is not type(None):
                        return t(value)
                # Fallback
                return value
            return expected_type(value)
        except (ValueError, TypeError) as err:
            raise ValueError(
                f"Invalid value for {key}: {value}. Expected type: {expected_type}"
            ) from err

    def _convert_to_bool(self, key: str, value: str) -> bool:
        """Convert a string value to a boolean.

        Args:
            key: The configuration key (for error messages)
            value: The string value to convert

        Returns:
            The boolean value

        Raises:
            ValueError: If the value can't be converted to a boolean
        """
        if value.lower() in ("true", "yes", "1", "on"):
            return True
        if value.lower() in ("false", "no", "0", "off"):
            return False
        raise ValueError(
            f"Invalid boolean value for {key}: {value}. "
            f"Use true/false, yes/no, 1/0, or on/off"
        )

    def _validate_allowed_values(self, key: str, value: Any) -> None:
        """Validate that a value is allowed for a given key, if applicable."""
        if key in CONFIG_VALID_VALUES:
            valid_values = CONFIG_VALID_VALUES[key]
            # Allow any ollama:<model> value
            if key == "model" and isinstance(value, str):
                if value.startswith("ollama:"):
                    return
                # Allow providerless alias (e.g., 'llama3.2:1b-text-q2_K') if
                # it looks like a valid alias
                if re.match(r"^[a-zA-Z0-9_\-:./]+$", value) and not (
                    value.startswith("gpt-") or value.startswith("claude-")
                ):
                    return
            # Remove the strict check against the hardcoded list for 'model'
            # if value not in valid_values:
            if key != "model" and value not in valid_values:
                # For model, show pattern in error message
                # This part is now unreachable for 'model', but kept for other keys
                if key == "model":
                    valid_str = (
                        ", ".join(str(v) for v in valid_values)
                        + ", ollama:<model>, or a registered alias (see 'llm models')"
                    )
                else:
                    valid_str = ", ".join(str(v) for v in valid_values)
                raise ValueError(
                    f"Invalid value for {key}: {value}. Valid values are: {valid_str}"
                )

    def set(self, key: str, value: Any) -> None:
        """Set a configuration value, with type and allowed value validation."""
        self._validate_key(key)
        # Convert to correct type
        converted_value = self._convert_to_type(key, str(value))

        # Perform model name validation if setting the 'model' key
        if key == "model":
            # Call the config-independent validation function directly
            is_valid, error_msg = is_valid_llm_model_name(converted_value)
            if not is_valid:
                raise ValueError(error_msg)

        # Validate allowed values (if any) - this no longer checks model name existence
        self._validate_allowed_values(key, converted_value)
        self._config[key] = converted_value
        self._save_config()

    def get_typed(self, key: str, default: T) -> T:
        """Get a typed configuration value with a default.

        Args:
            key: The key to get
            default: The default value (used for type information)

        Returns:
            The configuration value with the same type as the default
        """
        value = self.get(key, default)
        # Safe since we're providing the same type as the default
        return cast("T", value)

    def get_available_themes(self) -> list[str]:
        """Get list of available themes.

        Returns:
            List of theme names
        """
        return CONFIG_VALID_VALUES["theme"]

    def show(self) -> dict[str, Any]:
        """Show the current configuration.

        Returns:
            The current configuration dictionary
        """
        return self._config.copy()

    def save(self) -> None:
        """Save the current configuration to disk."""
        self._save_config()

    def get_all(self) -> dict[str, Any]:
        """Get all configuration values.

        Returns:
            The full configuration dictionary
        """
        return self._config.copy()

    def unset(self, key: str) -> None:
        """Unset a configuration key, resetting it to default if applicable.

        Args:
            key: The key to unset

        Raises:
            ValueError: If the key is not found
        """
        if key not in self._config:
            raise ValueError(f"Key not found in configuration: {key}")

        if key in DEFAULT_CONFIG:
            # Reset to default value
            self._config[key] = DEFAULT_CONFIG[key]
        else:
            # Remove entirely if no default
            del self._config[key]

        self._save_config()

    def get_model_key(self, provider: str) -> str | None:
        """Get API key for a specific model provider.

        This method checks multiple sources in this order:
        1. Environment variable override (VIBECTL_*_API_KEY)
        2. Key file path from environment variable (VIBECTL_*_API_KEY_FILE)
        3. Configured key in model_keys dictionary
        4. Configured key file in model_key_files dictionary
        5. Legacy environment variable (*_API_KEY)

        Args:
            provider: The model provider (openai, anthropic, ollama)

        Returns:
            The API key if found, None otherwise
        """
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
                # Log warning but continue with other methods
                pass

        # 3. Check configured key
        model_keys = self._config.get("model_keys", {})
        if (
            isinstance(model_keys, dict)
            and provider in model_keys
            and model_keys[provider]
        ):
            return str(model_keys[provider])

        # 4. Check configured key file
        model_key_files = self._config.get("model_key_files", {})
        if (
            isinstance(model_key_files, dict)
            and provider in model_key_files
            and model_key_files[provider]
        ):
            try:
                key_path = Path(model_key_files[provider]).expanduser()
                if key_path.exists():
                    return key_path.read_text().strip()
            except OSError:
                # Continue with legacy environment variable
                pass

        # 5. Check legacy environment variable
        legacy_key = os.environ.get(mapping["legacy_key"])
        if legacy_key:
            return legacy_key

        return None

    def set_model_key(self, provider: str, key: str) -> None:
        """Set API key for a specific model provider in the config.

        Args:
            provider: The model provider (openai, anthropic, ollama)
            key: The API key to set

        Raises:
            ValueError: If the provider is invalid
        """
        if provider not in ENV_KEY_MAPPINGS:
            valid_providers = ", ".join(ENV_KEY_MAPPINGS.keys())
            raise ValueError(
                f"Invalid model provider: {provider}. "
                f"Valid providers are: {valid_providers}"
            )

        # Initialize the model_keys dict if it doesn't exist
        if "model_keys" not in self._config:
            self._config["model_keys"] = {}

        # Set the key
        self._config["model_keys"][provider] = key
        self._save_config()

    def set_model_key_file(self, provider: str, file_path: str) -> None:
        """Set path to key file for a specific model provider.

        Args:
            provider: The model provider (openai, anthropic, ollama)
            file_path: Path to file containing the API key

        Raises:
            ValueError: If the provider is invalid or the file doesn't exist
        """
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

        # Initialize the model_key_files dict if it doesn't exist
        if "model_key_files" not in self._config:
            self._config["model_key_files"] = {}

        # Set the file path
        self._config["model_key_files"][provider] = str(path)
        self._save_config()
