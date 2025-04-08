"""Tests for the configuration module."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import pytest
import yaml
from click.testing import CliRunner

from vibectl.cli import cli
from vibectl.config import Config


@pytest.fixture
def test_config(tmp_path: Path) -> Config:
    """Create a test configuration instance."""
    return Config(base_dir=tmp_path)


def test_config_initialization(test_config: Config) -> None:
    """Test Config initialization creates directory and empty config."""
    assert test_config.config_dir.exists()
    assert test_config.config_file.exists()
    assert isinstance(test_config.show(), dict)


def test_config_load_existing(test_config: Config) -> None:
    """Test loading existing configuration."""
    test_config.set("theme", "dark")

    # Create new instance pointing to same directory
    new_config = Config(base_dir=test_config.config_dir.parent)
    assert new_config.get("theme") == "dark"


def test_config_save(test_config: Config) -> None:
    """Test saving configuration."""
    test_config.set("theme", "light")

    # Read file directly to verify
    with open(test_config.config_file, encoding="utf-8") as f:
        saved_config = yaml.safe_load(f)
    assert saved_config["theme"] == "light"


def test_config_get_with_default(test_config: Config) -> None:
    """Test getting configuration values with defaults."""
    assert test_config.get("nonexistent", "default") == "default"
    assert test_config.get("theme", "default") == "dark"  # Default from initialization


def test_config_set_boolean_values(test_config: Config) -> None:
    """Test setting boolean configuration values."""
    # Test various boolean string representations
    test_cases = [
        ("true", True),
        ("yes", True),
        ("1", True),
        ("on", True),
        ("false", False),
        ("no", False),
        ("0", False),
        ("off", False),
    ]

    for input_str, expected in test_cases:
        test_config.set("show_raw_output", input_str)
        assert test_config.get("show_raw_output") == expected


def test_config_set_invalid_boolean(test_config: Config) -> None:
    """Test setting invalid boolean value."""
    with pytest.raises(ValueError, match="Invalid boolean value"):
        test_config.set("show_raw_output", "invalid")


def test_config_get_typed(test_config: Config) -> None:
    """Test getting typed configuration values."""
    test_config.set("show_raw_output", True)
    assert test_config.get_typed("show_raw_output", False) is True


def test_config_get_available_themes(test_config: Config) -> None:
    """Test getting available themes."""
    themes = test_config.get_available_themes()
    assert isinstance(themes, list)
    assert "light" in themes
    assert "dark" in themes


def test_config_show() -> None:
    """Test showing configuration."""
    with TemporaryDirectory() as temp_dir:
        cfg = Config(Path(temp_dir))
        cfg.set("theme", "dark")
        config_data = cfg.show()
        assert "theme" in config_data
        assert config_data["theme"] == "dark"


def test_config_none_values(test_config: Config) -> None:
    """Test handling of None values."""
    test_config.set("kubeconfig", None)
    assert test_config.get("kubeconfig") is None


def test_config_unset_default_key() -> None:
    """Test unsetting a configuration key that has a default value."""
    with TemporaryDirectory() as temp_dir:
        cfg = Config(Path(temp_dir))
        # Set a non-default value
        cfg.set("theme", "light")
        assert cfg.get("theme") == "light"
        # Unset should reset to default
        cfg.unset("theme")
        assert cfg.get("theme") == "dark"  # dark is the default theme


def test_config_unset_custom_key() -> None:
    """Test unsetting a configuration key that has no default value."""
    with TemporaryDirectory() as temp_dir:
        cfg = Config(Path(temp_dir))
        # Set a custom value
        cfg.set("custom_instructions", "test instructions")
        assert cfg.get("custom_instructions") == "test instructions"
        # Unset should remove the key
        cfg.unset("custom_instructions")
        assert cfg.get("custom_instructions") is None


def test_config_unset_invalid_key() -> None:
    """Test unsetting an invalid configuration key."""
    with TemporaryDirectory() as temp_dir:
        cfg = Config(Path(temp_dir))
        with pytest.raises(ValueError, match="Key not found in configuration"):
            cfg.unset("invalid_key")  # Key that doesn't exist in config at all


def test_config_unset_nonexistent_key() -> None:
    """Test unsetting a key that doesn't exist in the configuration."""
    with TemporaryDirectory() as temp_dir:
        cfg = Config(Path(temp_dir))
        with pytest.raises(ValueError, match="Key not found in configuration"):
            cfg.unset("nonexistent_key")


def test_config_load_invalid_yaml(test_config: Config) -> None:
    """Test loading invalid YAML configuration."""
    # Write invalid YAML to config file
    with open(test_config.config_file, "w", encoding="utf-8") as f:
        f.write("invalid: yaml: :")

    # Loading should raise ValueError
    with pytest.raises(ValueError, match="Failed to load config"):
        test_config._load_config()


@patch("builtins.open")
def test_config_load_file_error(mock_open: Mock, test_config: Config) -> None:
    """Test loading configuration with file error."""
    mock_open.side_effect = OSError("File error")

    with pytest.raises(ValueError, match="Failed to load config"):
        test_config._load_config()


@patch("builtins.open")
def test_config_save_file_error(mock_open: Mock, test_config: Config) -> None:
    """Test saving configuration with file error."""
    mock_open.side_effect = OSError("File error")

    with pytest.raises(ValueError, match="Failed to save config"):
        test_config._save_config()


def test_config_invalid_key(test_config: Config) -> None:
    """Test setting invalid configuration key."""
    with pytest.raises(ValueError, match="Unknown configuration key"):
        test_config.set("invalid_key", "value")


def test_config_invalid_type_conversion(test_config: Config) -> None:
    """Test invalid type conversion."""
    # Test invalid boolean
    with pytest.raises(ValueError, match="Invalid boolean value"):
        test_config.set("show_raw_output", "not_a_bool")

    # Test invalid string for None-allowed field
    with pytest.raises(ValueError, match="None is not a valid value"):
        test_config.set("theme", "none")

    # Test invalid type for string field
    with pytest.raises(ValueError, match="Invalid value for"):
        test_config.set("theme", "123")  # Theme must be a valid theme name


def test_config_invalid_allowed_values(test_config: Config) -> None:
    """Test invalid allowed values."""
    # Test invalid theme
    with pytest.raises(ValueError, match="Invalid value for theme"):
        test_config.set("theme", "invalid_theme")

    # Test invalid model
    with pytest.raises(ValueError, match="Invalid value for model"):
        test_config.set("model", "invalid_model")


def test_config_legacy_model_key(test_config: Config) -> None:
    """Test handling of legacy llm_model key."""
    # Write config with legacy key
    config_data = {"llm_model": "claude-3.7-sonnet"}
    with open(test_config.config_file, "w", encoding="utf-8") as f:
        yaml.dump(config_data, f)

    # Load config and verify migration
    test_config._load_config()
    assert test_config.get("model") == "claude-3.7-sonnet"
    assert "llm_model" not in test_config._config

    # Verify file was updated
    with open(test_config.config_file, encoding="utf-8") as f:
        saved_config = yaml.safe_load(f)
        assert "model" in saved_config
        assert "llm_model" not in saved_config


def test_config_empty_file(test_config: Config) -> None:
    """Test loading empty configuration file."""
    # Write empty file
    with open(test_config.config_file, "w", encoding="utf-8") as f:
        f.write("")

    # Load config and verify defaults
    test_config._load_config()
    assert test_config.get("theme") == "dark"  # Default value
    assert test_config.get("model") == "claude-3.7-sonnet"  # Default value


def test_config_get_all(test_config: Config) -> None:
    """Test getting all configuration values."""
    # Set some values
    test_config.set("theme", "light")
    test_config.set("model", "claude-3.7-sonnet")

    # Get all values
    config = test_config.get_all()
    assert isinstance(config, dict)
    assert config["theme"] == "light"
    assert config["model"] == "claude-3.7-sonnet"


def test_config_save_explicit(test_config: Config) -> None:
    """Test explicit save call."""
    # Set a value
    test_config.set("theme", "light")

    # Save explicitly
    test_config.save()

    # Verify file
    with open(test_config.config_file, encoding="utf-8") as f:
        saved_config = yaml.safe_load(f)
        assert saved_config["theme"] == "light"


# CLI Config Command Tests

# The cli_runner fixture is now provided by conftest.py


@patch("vibectl.cli.Config")
def test_cli_config_set_save_error(
    mock_config_class: Mock, cli_runner: CliRunner
) -> None:
    """Test config set command handles save error."""
    mock_config = Mock()
    mock_config_class.return_value = mock_config
    mock_config.save.side_effect = ValueError("Failed to save config")

    result = cli_runner.invoke(cli, ["config", "set", "theme", "dark"])
    assert result.exit_code == 1
    assert "Failed to save config" in result.output


@patch("vibectl.cli.Config")
def test_cli_config_show_get_all_error(
    mock_config_class: Mock, cli_runner: CliRunner
) -> None:
    """Test config show command handles get_all error."""
    mock_config = Mock()
    mock_config_class.return_value = mock_config
    mock_config.get_all.side_effect = Exception("Failed to get config")

    result = cli_runner.invoke(cli, ["config", "show"])
    assert result.exit_code == 1
    assert "Failed to get config" in result.output


@patch("vibectl.cli.Config")
def test_cli_config_unset_invalid_key_error(
    mock_config_class: Mock, cli_runner: CliRunner
) -> None:
    """Test config unset command handles invalid key error."""
    mock_config = Mock()
    mock_config_class.return_value = mock_config
    mock_config.unset.side_effect = ValueError("Invalid key")

    result = cli_runner.invoke(cli, ["config", "unset", "invalid_key"])
    assert result.exit_code == 1
    assert "Invalid key" in result.output


@patch("vibectl.cli.Config")
def test_cli_config_show_basic(mock_config_class: Mock, cli_runner: CliRunner) -> None:
    """Test basic config show command."""
    mock_config = Mock()
    mock_config_class.return_value = mock_config
    mock_config.get_all.return_value = {"key": "value"}

    result = cli_runner.invoke(cli, ["config", "show"])

    assert result.exit_code == 0
    mock_config.get_all.assert_called_once()


def test_config_handle_none_value(test_config: Config) -> None:
    """Test handling of 'none' string as None value when it's allowed."""
    # The kubeconfig config field allows None values
    test_config.set("kubeconfig", "none")
    assert test_config.get("kubeconfig") is None

    # Setting 'none' value for a field that doesn't allow None should raise ValueError
    with pytest.raises(ValueError, match="None is not a valid value for theme"):
        test_config.set("theme", "none")


def test_config_convert_type_first_non_none(test_config: Config) -> None:
    """Test type conversion using first non-None type in a tuple of expected types."""
    # This is a bit of an implementation detail, but we need to test the branch
    # for multiple types where we choose the first non-None type

    # Temporary schema modification for testing
    import vibectl.config

    original_schema = vibectl.config.CONFIG_SCHEMA.copy()
    try:
        # Monkey patch the schema temporarily to test this case
        vibectl.config.CONFIG_SCHEMA = {
            **vibectl.config.CONFIG_SCHEMA,
            "test_multi_type": (type(None), str, int),  # Use a tuple with None first
        }

        # Now try to convert a value using this schema
        # This should use str as the first non-None type
        test_config.set("test_multi_type", "test_value")
        assert test_config.get("test_multi_type") == "test_value"
    finally:
        # Restore the original schema
        vibectl.config.CONFIG_SCHEMA = original_schema


def test_config_convert_type_fallback(test_config: Config) -> None:
    """Test type conversion fallback for unusual cases."""
    # This tests the fallback code path where none of the types in a tuple work
    # or where there's only None types (which should never happen in practice)

    # Mock the schema and create a controlled test environment
    import vibectl.config

    # Create a mock schema with only None type
    test_schema = {**vibectl.config.CONFIG_SCHEMA, "test_bad_schema": (type(None),)}
    original_schema = vibectl.config.CONFIG_SCHEMA

    try:
        # Apply the test schema
        vibectl.config.CONFIG_SCHEMA = test_schema

        # Add our test key to valid values
        if "test_bad_schema" not in vibectl.config.CONFIG_VALID_VALUES:
            vibectl.config.CONFIG_VALID_VALUES["test_bad_schema"] = ["test_value"]

        # This should reach the fallback code path and return the string as-is
        # We need to use a new Config instance to ensure it gets our patched schema
        with TemporaryDirectory() as temp_dir:
            test_cfg = Config(Path(temp_dir))
            # Use internal method directly since it's not expected to be called normally
            # when all types in a tuple are None
            result = test_cfg._convert_to_type("test_bad_schema", "test_value")
            assert result == "test_value"
    finally:
        # Restore the original schema
        vibectl.config.CONFIG_SCHEMA = original_schema


def test_config_convert_type_exception_handling(test_config: Config) -> None:
    """Test exception handling in the _convert_to_type method."""
    import vibectl.config

    # Create a test schema with a type that will fail conversion
    class FailingType:
        def __init__(self, value: str) -> None:
            raise ValueError("Conversion always fails")

    original_schema = vibectl.config.CONFIG_SCHEMA.copy()
    try:
        # Apply our test schema
        vibectl.config.CONFIG_SCHEMA = {**original_schema, "failing_type": FailingType}

        # Add our test key to valid values
        if "failing_type" not in vibectl.config.CONFIG_VALID_VALUES:
            vibectl.config.CONFIG_VALID_VALUES["failing_type"] = ["any_value"]

        # Attempt to convert a value that will trigger the exception
        with TemporaryDirectory() as temp_dir:
            test_cfg = Config(Path(temp_dir))
            with pytest.raises(ValueError, match="Invalid value for failing_type"):
                test_cfg._convert_to_type("failing_type", "any_value")
    finally:
        # Restore the original schema
        vibectl.config.CONFIG_SCHEMA = original_schema
