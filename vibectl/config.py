"""Configuration management for vibectl"""

import os
from pathlib import Path
from typing import Any, Dict, List, Tuple, Type, Union

import yaml

DEFAULT_CONFIG = {
    "kubeconfig": None,  # Will use default kubectl config location if None
    "theme": "default",  # Default theme for console output
}

# Define type for expected types that can be a single type or a tuple of types
ConfigType = Union[Type, Tuple[Type, ...]]

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
CONFIG_VALID_VALUES = {
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
                    self._config = yaml.safe_load(f) or {}
        except (yaml.YAMLError, OSError):
            self._config = {}

    def save(self) -> None:
        """Save current configuration to file"""
        try:
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

    def set(self, key: str, value: str) -> None:
        """Set a configuration value.

        Args:
            key: The configuration key
            value: The value to set

        Raises:
            ValueError: If the key or value is invalid
        """
        # Validate key
        if key not in CONFIG_SCHEMA:
            valid_keys = ", ".join(CONFIG_SCHEMA.keys())
            raise ValueError(f"Invalid config key: {key}. Valid keys are: {valid_keys}")

        # Convert value to correct type
        expected_type = CONFIG_SCHEMA[key]
        typed_value: Any = None

        # Special handling for None type
        if value.lower() == "none":
            # Check if None is an acceptable type
            if isinstance(expected_type, tuple) and type(None) in expected_type:
                typed_value = None
            else:
                # If None is not acceptable, raise an error
                raise ValueError(f"None is not a valid value for {key}")
        else:
            # Try to convert to expected type
            if expected_type == bool or (
                isinstance(expected_type, tuple) and bool in expected_type
            ):
                if value.lower() in ("true", "yes", "1", "on"):
                    typed_value = True
                elif value.lower() in ("false", "no", "0", "off"):
                    typed_value = False
                else:
                    raise ValueError(
                        f"Invalid boolean value: {value}. Use true/false, yes/no, 1/0, or on/off"
                    )
            else:
                # Default conversion
                try:
                    if isinstance(expected_type, tuple):
                        # Use the first non-None type for conversion
                        for t in expected_type:
                            if t is not type(None):  # Using 'is not' instead of '!='
                                typed_value = t(value)
                                break
                        else:
                            # This should be unreachable if we've handled None correctly
                            typed_value = value
                    else:
                        typed_value = expected_type(value)
                except (ValueError, TypeError) as err:
                    raise ValueError(
                        f"Invalid value for {key}: {value}. Expected type: {expected_type}"
                    ) from err

        # Validate against allowed values if applicable
        if key in CONFIG_VALID_VALUES and typed_value is not None:
            valid_values = CONFIG_VALID_VALUES[key]
            if typed_value not in valid_values:
                valid_values_str = ", ".join(str(v) for v in valid_values)
                raise ValueError(
                    f"Invalid value for {key}: {typed_value}. Valid values: {valid_values_str}"
                )

        # Set the typed value
        self._config[key] = typed_value
        self.config_dir.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, "w") as f:
            yaml.dump(self._config, f)

    def get_available_themes(self) -> List[str]:
        """Get a list of available themes.

        Returns:
            List of available theme names
        """
        return CONFIG_VALID_VALUES["theme"]

    def show(self) -> Dict[str, Any]:
        """Show all configuration values.

        Returns:
            Dictionary of all configuration values
        """
        return dict(self._config)
