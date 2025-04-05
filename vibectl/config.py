"""Configuration management for vibectl"""

import os
from pathlib import Path
from typing import Any, Dict, List, Tuple, Type, TypeVar, Union, cast

import yaml

DEFAULT_CONFIG = {
    "kubeconfig": None,  # Will use default kubectl config location if None
    "theme": "default",  # Default theme for console output
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
    "suppress_output_warning": bool,
    "model": str,
}

# Valid values for specific keys
CONFIG_VALID_VALUES: Dict[str, List[Any]] = {
    "theme": ["default", "dark", "light", "accessible"],
}


class Config:
    """Manages vibectl configuration"""

    def __init__(self) -> None:
        """Initialize configuration."""
        self.config_dir = (
            Path(os.getenv("XDG_CONFIG_HOME", "~/.config")).expanduser() / "vibectl"
        )
        self.config_file = self.config_dir / "config.yaml"
        self._config: Dict[str, Any] = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from file."""
        try:
            if not self.config_dir.exists():
                self.config_dir.mkdir(parents=True)
            if self.config_file.exists():
                with open(self.config_file) as f:
                    loaded_config = yaml.safe_load(f)
                    self._config = loaded_config if loaded_config else {}
        except (yaml.YAMLError, OSError):
            self._config = {}

    def save(self) -> None:
        """Save current configuration to file"""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, "w") as f:
                yaml.dump(self._config, f)
        except OSError:
            # Log error or handle it appropriately
            # For now, we'll just let it propagate since this is a write operation
            raise

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value.

        Args:
            key: The configuration key
            default: Default value if key is not found

        Returns:
            The configuration value or default if not found
        """
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
            raise ValueError(f"Invalid config key: {key}. Valid keys are: {valid_keys}")

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
        if isinstance(expected_type, bool) or (
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
                err_msg = f"Invalid value for {key}: {value}. "
                err_msg += f"Valid values: {valid_values_str}"
                raise ValueError(err_msg)

    def set(self, key: str, value: str) -> None:
        """Set a configuration value.

        Args:
            key: The configuration key
            value: The value to set

        Raises:
            ValueError: If the key or value is invalid
        """
        # Validate key
        self._validate_key(key)

        # Convert value to correct type
        typed_value = self._convert_to_type(key, value)

        # Validate against allowed values if applicable
        self._validate_allowed_values(key, typed_value)

        # Set the typed value
        self._config[key] = typed_value
        # Save to file
        self.save()

    def get_typed(self, key: str, default: T) -> T:
        """Get a configuration value with type safety.

        Args:
            key: The configuration key
            default: Default value if key is not found (also determines return type)

        Returns:
            The configuration value with the same type as the default value
        """
        value = self._config.get(key, default)
        # Cast to the same type as the default to help type checking
        return cast("T", value)

    def get_available_themes(self) -> List[str]:
        """Get a list of available themes.

        Returns:
            List of available theme names
        """
        return CONFIG_VALID_VALUES.get("theme", [])

    def show(self) -> Dict[str, Any]:
        """Show all configuration values.

        Returns:
            Dictionary of all configuration values
        """
        return dict(self._config)
