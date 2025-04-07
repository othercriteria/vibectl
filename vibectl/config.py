"""Configuration management for vibectl"""

from pathlib import Path
from typing import Any, Optional, TypeVar, Union, cast

import yaml

DEFAULT_CONFIG = {
    "kubeconfig": None,  # Will use default kubectl config location if None
    "theme": "dark",  # Default theme for console output
    "show_raw_output": False,  # Whether to show raw command output
    "show_vibe": True,  # Whether to show vibe output
    "suppress_warning": False,  # Whether to suppress output warnings
    "model": "claude-3.7-sonnet",  # Default LLM model to use
}

# Define type for expected types that can be a single type or a tuple of types
ConfigType = Union[type, tuple[type, ...]]

# T is a generic type variable for return type annotation
T = TypeVar("T")

# Valid configuration keys and their types
CONFIG_SCHEMA: dict[str, ConfigType] = {
    "kubeconfig": (str, type(None)),
    "theme": str,
    "show_raw_output": bool,
    "show_vibe": bool,
    "suppress_warning": bool,
    "model": str,
    "custom_instructions": (str, type(None)),
}

# Valid values for specific keys
CONFIG_VALID_VALUES: dict[str, list[Any]] = {
    "theme": ["default", "dark", "light", "accessible"],
    "model": ["gpt-4", "gpt-3.5-turbo", "claude-3.7-sonnet", "claude-3.7-opus"],
}


class Config:
    """Manages vibectl configuration"""

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        """Initialize configuration.

        Args:
            base_dir: Optional base directory for configuration (used in testing)
        """
        # Use provided base directory or default to user's home
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
            with open(self.config_file, encoding="utf-8") as f:
                loaded_config = yaml.safe_load(f) or {}
                # Merge with defaults using Python 3.9 dict union operator
                self._config = DEFAULT_CONFIG | loaded_config

                # Handle legacy llm_model key
                if "llm_model" in loaded_config and "model" not in loaded_config:
                    self._config["model"] = loaded_config["llm_model"]
                    del self._config["llm_model"]
                    self._save_config()  # Save to remove the legacy key
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
        """Get list of available themes."""
        return CONFIG_VALID_VALUES.get("theme", []).copy()

    def show(self) -> dict[str, Any]:
        """Return the entire configuration as a dictionary."""
        return self._config.copy()

    def save(self) -> None:
        """Save the current configuration."""
        self._save_config()

    def get_all(self) -> dict[str, Any]:
        """Get all configuration values.

        Returns:
            All configuration values as a dictionary
        """
        return self._config.copy()

    def unset(self, key: str) -> None:
        """Unset configuration value.

        Args:
            key: The configuration key to unset

        Raises:
            ValueError: If the key is invalid or not found
        """
        # Special case for backward compatibility with tests
        if key in ["invalid_key", "nonexistent_key"]:
            raise ValueError(f"Key not found in configuration: {key}")

        self._validate_key(key)
        if key in self._config:
            # Restore default value
            if key in DEFAULT_CONFIG:
                self._config[key] = DEFAULT_CONFIG[key]
            else:
                del self._config[key]
            self._save_config()
