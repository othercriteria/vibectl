"""
Shared configuration utilities for vibectl client and server.

This module provides common configuration management functionality that can be
used by both the client and server components to reduce code duplication.
"""

import copy
import os
from pathlib import Path
from typing import Any

import yaml


def get_config_dir(component: str, base_dir: Path | None = None) -> Path:
    """Get the configuration directory for a component.

    Args:
        component: Component name ('client' or 'server')
        base_dir: Optional base directory for configuration (used in testing)

    Returns:
        Path to the configuration directory

    Raises:
        ValueError: If component is not 'client' or 'server'
    """
    if component not in ("client", "server"):
        raise ValueError(
            f"Invalid component: {component}. Must be 'client' or 'server'"
        )

    # Use provided base directory first (for testing), then
    # environment variable, then default
    if base_dir is not None:
        return base_dir / ".config" / "vibectl" / component

    # Check for component-specific environment variable first
    env_var = f"VIBECTL_{component.upper()}_CONFIG_DIR"
    env_config_dir = os.environ.get(env_var)
    if env_config_dir:
        return Path(env_config_dir)

    # Check for generic VIBECTL_CONFIG_DIR
    env_config_dir = os.environ.get("VIBECTL_CONFIG_DIR")
    if env_config_dir:
        return Path(env_config_dir) / component

    # Default to XDG configuration directory
    config_home = os.environ.get("XDG_CONFIG_HOME")
    if config_home:
        return Path(config_home) / "vibectl" / component
    else:
        return Path.home() / ".config" / "vibectl" / component


def ensure_config_dir(component: str, base_dir: Path | None = None) -> Path:
    """Ensure the configuration directory exists for a component.

    Args:
        component: Component name ('client' or 'server')
        base_dir: Optional base directory for configuration (used in testing)

    Returns:
        Path to the configuration directory (created if it didn't exist)
    """
    config_dir = get_config_dir(component, base_dir)
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def load_yaml_config(
    config_file: Path, defaults: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Load YAML configuration from file with optional defaults.

    Args:
        config_file: Path to the configuration file
        defaults: Optional default configuration to merge with

    Returns:
        dict: Loaded configuration merged with defaults

    Raises:
        ValueError: If configuration file cannot be loaded
    """
    try:
        # Handle empty or non-existent files
        if not config_file.exists() or config_file.stat().st_size == 0:
            loaded_config: dict[str, Any] = {}
        else:
            with open(config_file, encoding="utf-8") as f:
                loaded_config = yaml.safe_load(f) or {}

        # Start with defaults if provided
        if defaults is not None:
            config = copy.deepcopy(defaults)
            deep_merge(config, loaded_config)
            return config
        else:
            return loaded_config

    except (yaml.YAMLError, OSError) as e:
        raise ValueError(f"Failed to load config from {config_file}: {e}") from e


def save_yaml_config(
    config: dict[str, Any], config_file: Path, comment: str | None = None
) -> None:
    """Save configuration to YAML file.

    Args:
        config: Configuration dictionary to save
        config_file: Path to save the configuration file
        comment: Optional comment to add at the top of the file

    Raises:
        ValueError: If configuration file cannot be saved
    """
    try:
        # Ensure parent directory exists
        config_file.parent.mkdir(parents=True, exist_ok=True)

        with open(config_file, "w", encoding="utf-8") as f:
            if comment:
                # Handle multi-line comments properly
                for line in comment.splitlines():
                    f.write(f"# {line}\n")
                f.write("\n")  # Single newline after comment block
            yaml.dump(config, f, default_flow_style=False)

    except (yaml.YAMLError, OSError) as e:
        raise ValueError(f"Failed to save config to {config_file}: {e}") from e


def deep_merge(base: dict[str, Any], updates: dict[str, Any]) -> None:
    """Deep merge updates into base dictionary in-place.

    Args:
        base: Base dictionary to merge into (modified in-place)
        updates: Updates to merge into base
    """
    for key, value in updates.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            deep_merge(base[key], value)
        else:
            base[key] = value


def get_nested_value(config: dict[str, Any], path: str) -> Any:
    """Get a value from nested config using dotted path notation.

    Args:
        config: The config dictionary
        path: Dotted path like 'display.theme' or 'llm.model'

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


def set_nested_value(config: dict[str, Any], path: str, value: Any) -> None:
    """Set a value in nested config using dotted path notation.

    Args:
        config: The config dictionary to modify
        path: Dotted path like 'display.theme' or 'llm.model'
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


def validate_config_key_path(path: str, schema: dict[str, Any]) -> None:
    """Validate that a hierarchical path exists in the schema.

    Args:
        path: Dotted path like 'display.theme'
        schema: Configuration schema to validate against

    Raises:
        ValueError: If the path is invalid
    """
    parts = path.split(".")
    current_schema = schema

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
                available_sections = list(schema.keys())
                raise ValueError(
                    f"Invalid config section: {part}. "
                    f"Available sections: {available_sections}"
                )
        current_schema = current_schema[part]


def convert_string_to_type(
    value: str, expected_type: type | tuple[type, ...], field_name: str = ""
) -> Any:
    """Convert a string value to the expected type.

    Args:
        value: String value to convert
        expected_type: Expected type or tuple of allowed types
        field_name: Optional field name for better error messages

    Returns:
        Converted value

    Raises:
        ValueError: If conversion fails
    """
    # Always convert string "none" to Python None first
    if value.lower() == "none":
        return None

    try:
        # Convert string to appropriate type
        if expected_type is bool:
            return convert_string_to_bool(value)
        elif expected_type is int:
            return int(value)
        elif expected_type is float:
            return float(value)
        elif expected_type is list:
            return convert_string_to_list(value)
        elif isinstance(expected_type, tuple):
            # Convert to the first non-None type in the tuple
            for t in expected_type:
                if t is not type(None):
                    if t is bool:
                        return convert_string_to_bool(value)
                    elif t is int:
                        return int(value)
                    elif t is float:
                        return float(value)
                    elif t is str:
                        return value
                    elif t is list:
                        return convert_string_to_list(value)
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
        # Wrap conversion errors with field context if available
        if field_name:
            raise ValueError(f"Invalid value for {field_name}: {value}") from e
        else:
            raise


def convert_string_to_bool(value: str) -> bool:
    """Convert a string value to a boolean.

    Args:
        value: String value to convert

    Returns:
        Boolean value

    Raises:
        ValueError: If string cannot be converted to boolean
    """
    if value.lower() in ("true", "yes", "1", "on"):
        return True
    if value.lower() in ("false", "no", "0", "off"):
        return False
    raise ValueError(
        f"Invalid boolean value: {value}. Use true/false, yes/no, 1/0, or on/off"
    )


def convert_string_to_list(value: str) -> list[Any]:
    """Convert a string value to a list.

    Args:
        value: String value to convert

    Returns:
        List value
    """
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


def get_env_with_fallbacks(
    primary_var: str, fallback_vars: list[str] | None = None, default: str | None = None
) -> str | None:
    """Get environment variable value with fallback options.

    Args:
        primary_var: Primary environment variable name
        fallback_vars: List of fallback environment variable names
        default: Default value if no environment variables are set

    Returns:
        Environment variable value or default
    """
    # Try primary variable first
    value = os.environ.get(primary_var)
    if value:
        return value

    # Try fallback variables
    if fallback_vars:
        for var in fallback_vars:
            value = os.environ.get(var)
            if value:
                return value

    return default


def read_key_from_file(file_path: str | Path) -> str | None:
    """Read API key or secret from a file.

    Args:
        file_path: Path to the file containing the key

    Returns:
        Key content or None if file cannot be read
    """
    try:
        key_path = Path(file_path).expanduser()
        if key_path.exists():
            return key_path.read_text().strip()
    except OSError:
        # Silently handle file read errors
        pass

    return None


def validate_numeric_range(
    value: Any, min_value: int | float, max_value: int | float, field_name: str
) -> None:
    """Validate that a numeric value is within the specified range.

    Args:
        value: Value to validate
        min_value: Minimum allowed value
        max_value: Maximum allowed value
        field_name: Name of the field being validated (for error messages)

    Raises:
        ValueError: If value is not numeric or outside the valid range
    """
    if not isinstance(value, int | float):
        raise ValueError(
            f"Invalid type for {field_name}: expected number, "
            f"got {type(value).__name__}"
        )

    if value < min_value or value > max_value:
        raise ValueError(
            f"Invalid value for {field_name}: {value}. "
            f"Must be between {min_value} and {max_value}"
        )
