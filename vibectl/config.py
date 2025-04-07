"""Configuration management for vibectl"""

import os
from pathlib import Path
from typing import Any, Dict, List, Tuple, Type, TypeVar, Union, cast, Optional

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
ConfigType = Union[Type, Tuple[Type, ...]]

# T is a generic type variable for return type annotation
T = TypeVar("T")

# Valid configuration keys and their types
CONFIG_SCHEMA: Dict[str, ConfigType] = {
    "kubeconfig": (str, type(None)),
    "theme": str,
    "show_raw_output": bool,
    "show_vibe": bool,
    "suppress_warning": bool,
    "model": str,
    "custom_instructions": (str, type(None)),
}

# Valid values for specific keys
CONFIG_VALID_VALUES: Dict[str, List[Any]] = {
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
        self._config: Dict[str, Any] = {}
        
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
            with open(self.config_file, "r", encoding="utf-8") as f:
                loaded_config = yaml.safe_load(f) or {}
                # Merge with defaults to ensure all keys exist
                self._config = DEFAULT_CONFIG.copy()
                self._config.update(loaded_config)
                
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
            raise ValueError(f"Unknown configuration key: {key}. Valid keys are: {valid_keys}")

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
        if expected_type == bool or (isinstance(expected_type, tuple) and bool in expected_type):
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
                    f"Invalid value for {key}: {value}. Valid values: {valid_values_str}"
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
        """Get configuration value with type safety.

        Args:
            key: The configuration key
            default: Default value if key is not found (also determines return type)

        Returns:
            The configuration value with the same type as the default value
        """
        value = self.get(key, default)
        # Cast to the same type as the default to help type checking
        return cast(T, value)

    def get_available_themes(self) -> List[str]:
        """Return list of available themes."""
        return CONFIG_VALID_VALUES["theme"]

    def show(self) -> Dict[str, Any]:
        """Return current configuration."""
        return dict(self._config)

    def save(self) -> None:
        """Save configuration to file."""
        self._save_config()

    def get_all(self) -> Dict[str, Any]:
        """Get all configuration values.

        Returns:
            Dict[str, Any]: Dictionary of all configuration values
        """
        return self._config.copy()

    def unset(self, key: str) -> None:
        """Unset a configuration value, resetting it to the default.

        If the key is in DEFAULT_CONFIG, it will be reset to its default value.
        If not, it will be removed from the configuration.
        If the key is not in CONFIG_SCHEMA, a warning will be printed.

        Args:
            key: The configuration key to unset

        Raises:
            ValueError: If the key does not exist in the configuration
        """
        # Check if key exists in configuration
        if key not in self._config:
            valid_keys = ", ".join(self._config.keys())
            raise ValueError(f"Key not found in configuration: {key}. Existing keys are: {valid_keys}")

        # Warn if key is not in schema (likely deprecated)
        if key not in CONFIG_SCHEMA:
            from .console import console_manager
            console_manager.print_warning(f"Note: '{key}' is not in the current configuration schema (may be deprecated)")

        # Reset to default value if one exists
        if key in DEFAULT_CONFIG:
            self._config[key] = DEFAULT_CONFIG[key]
        else:
            # For keys not in DEFAULT_CONFIG, remove them
            self._config.pop(key, None)
        
        self._save_config()
