"""Configuration management for vibectl"""

import os
from pathlib import Path
from typing import Any, TypeVar, cast

import yaml

# Default values
DEFAULT_CONFIG = {
    "kubeconfig": None,  # Will use default kubectl config location if None
    "kubectl_command": "kubectl",
    "theme": "dark",
    "use_emoji": True,
    "show_raw_output": False,
    "show_vibe": True,
    "show_kubectl": False,  # Show kubectl commands when they are executed
    "model": "claude-3.7-sonnet",
    "memory_enabled": True,
    "memory_max_chars": 500,
    "warn_no_output": True,
    "colored_output": True,
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
    "use_emoji": bool,
    "show_raw_output": bool,
    "show_vibe": bool,
    "show_kubectl": bool,
    "warn_no_output": bool,
    "model": str,
    "custom_instructions": (str, type(None)),
    "memory": (str, type(None)),
    "memory_enabled": bool,
    "memory_max_chars": int,
    "colored_output": bool,
    "model_keys": dict,
    "model_key_files": dict,
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
        """Validate that a value is in the allowed values for a key.

        Args:
            key: The configuration key
            value: The value to validate

        Raises:
            ValueError: If the value is not allowed
        """
        if key in CONFIG_VALID_VALUES and value is not None:
            valid_values = CONFIG_VALID_VALUES[key]
            if value not in valid_values:
                valid_values_str = ", ".join(str(v) for v in valid_values)
                raise ValueError(
                    f"Invalid value for {key}: {value}. "
                    f"Valid values: {valid_values_str}"
                )

    def set(self, key: str, value: Any) -> None:
        """Set configuration value.

        Args:
            key: The configuration key to set
            value: The value to set

        Raises:
            ValueError: If the key or value is invalid
        """
        # Validate key exists in schema
        self._validate_key(key)

        # Convert string values to appropriate type
        if isinstance(value, str):
            value = self._convert_to_type(key, value)

        # Validate value is allowed for this key
        self._validate_allowed_values(key, value)

        # Set the value
        self._config[key] = value
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
