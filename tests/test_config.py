"""Tests for configuration management.

This module tests the configuration management functionality of vibectl.
"""

import os
from collections.abc import Generator
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import Mock, patch

import pytest
import yaml
from asyncclick.testing import CliRunner

from vibectl.cli import cli
from vibectl.config import (
    DEFAULT_CONFIG,
    Config,
    parse_proxy_url,
)
from vibectl.config_utils import ensure_config_dir


class MockConfig(Config):
    """Mock Config class that doesn't rely on file I/O."""

    def __init__(self, base_dir: Path | None = None) -> None:
        """Initialize with default config in memory only."""
        # Use environment variable, provided base directory, or default to user's home
        self.config_dir = ensure_config_dir("client", base_dir)
        self.config_file = self.config_dir / "config.yaml"

        # Initialize with defaults - use deep copy to avoid modifying the original
        import copy

        self._config = copy.deepcopy(DEFAULT_CONFIG)

        # If a config file exists, load it
        if self.config_file.exists() and self.config_file.is_file():
            self._load_config_from_file()

    def _load_config_from_file(self) -> None:
        """Load configuration from file for mock - preserves unsupported keys."""
        try:
            if self.config_file.stat().st_size == 0:
                # Handle empty file as an empty dictionary
                loaded_config: dict[str, Any] = {}
            else:
                with open(self.config_file, encoding="utf-8") as f:
                    loaded_config = yaml.safe_load(f) or {}

            # Update our default config with loaded values
            # This preserves unsupported keys
            self._config.update(loaded_config)

        except (yaml.YAMLError, OSError) as e:
            raise ValueError(f"Failed to load config: {e}") from e

    def _save_config(self) -> None:
        """No-op for mock class."""
        pass

    def get_model_key_file(self, provider: str) -> str | None:
        """Get model key file path for provider from environment or config."""
        # Check environment variable first
        env_var = f"{provider.upper()}_API_KEY_FILE"
        env_file = os.environ.get(env_var)
        if env_file:
            return env_file

        # Check configuration
        result = self.get(f"providers.{provider}.key_file")
        return result if isinstance(result, str | type(None)) else None


@pytest.fixture
def test_config() -> MockConfig:
    """Create a test configuration instance."""
    # Create and return a MockConfig
    return MockConfig()


def test_config_initialization(test_config: MockConfig) -> None:
    """Test Config initialization creates directory and empty config."""
    assert isinstance(test_config.show(), dict)


def test_config_get_with_default(test_config: MockConfig) -> None:
    """Test getting configuration values with defaults."""
    assert test_config.get("nonexistent", "default") == "default"
    assert (
        test_config.get("display.theme", "default") == "default"
    )  # Default from initialization


def test_config_set_boolean_values(test_config: MockConfig) -> None:
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
        test_config.set("display.show_raw_output", input_str)
        assert test_config.get("display.show_raw_output") == expected


def test_config_set_show_kubectl(test_config: MockConfig) -> None:
    """Test setting show_kubectl configuration value."""
    # Set show_kubectl to true
    test_config.set("display.show_kubectl", True)
    assert test_config.get("display.show_kubectl") is True

    # Set show_kubectl to false
    test_config.set("display.show_kubectl", False)
    assert test_config.get("display.show_kubectl") is False

    # Test string conversion to boolean
    test_config.set("display.show_kubectl", "true")
    assert test_config.get("display.show_kubectl") is True

    # Unset should reset to default (False)
    test_config.unset("display.show_kubectl")
    assert test_config.get("display.show_kubectl") is False


def test_config_set_warn_no_proxy(test_config: MockConfig) -> None:
    """Test setting warn_no_proxy configuration value."""
    # Default should be True
    assert test_config.get("warnings.warn_no_proxy", True) is True

    # Set warn_no_proxy to false
    test_config.set("warnings.warn_no_proxy", False)
    assert test_config.get("warnings.warn_no_proxy") is False

    # Set warn_no_proxy to true
    test_config.set("warnings.warn_no_proxy", True)
    assert test_config.get("warnings.warn_no_proxy") is True

    # Test string conversion to boolean
    test_config.set("warnings.warn_no_proxy", "false")
    assert test_config.get("warnings.warn_no_proxy") is False

    # Unset should reset to default (True)
    test_config.unset("warnings.warn_no_proxy")
    assert test_config.get("warnings.warn_no_proxy", True) is True


def test_config_set_invalid_boolean(test_config: MockConfig) -> None:
    """Test setting invalid boolean value."""
    with pytest.raises(ValueError, match="Invalid value for display.show_raw_output"):
        test_config.set("display.show_raw_output", "invalid")


def test_config_get_typed(test_config: MockConfig) -> None:
    """Test getting typed configuration values."""
    test_config.set("display.show_raw_output", True)
    assert test_config.get_typed("display.show_raw_output", False) is True


def test_config_get_available_themes(test_config: MockConfig) -> None:
    """Test getting available themes."""
    themes = test_config.get_available_themes()
    assert isinstance(themes, list)
    assert "light" in themes
    assert "dark" in themes


def test_config_show(test_config: MockConfig) -> None:
    """Test showing configuration."""
    test_config.set("display.theme", "dark")
    config_data = test_config.show()
    assert "display" in config_data
    assert config_data["display"]["theme"] == "dark"


def test_config_none_values(test_config: MockConfig) -> None:
    """Test handling of None values."""
    test_config.set("core.kubeconfig", None)
    assert test_config.get("core.kubeconfig") is None


def test_config_unset_default_key(test_config: MockConfig) -> None:
    """Test unsetting a configuration key that has a default value."""
    # Set a non-default value
    test_config.set("display.theme", "light")
    assert test_config.get("display.theme") == "light"
    # Unset should reset to default
    test_config.unset("display.theme")
    assert test_config.get("display.theme") == "default"  # default is the default theme


def test_config_unset_custom_key(test_config: MockConfig) -> None:
    """Test unsetting a configuration key that has no default value."""
    # Set a custom value
    test_config.set("system.custom_instructions", "test instructions")
    assert test_config.get("system.custom_instructions") == "test instructions"
    # Unset should remove the key
    test_config.unset("system.custom_instructions")
    assert test_config.get("system.custom_instructions") is None


def test_config_unset_invalid_key(test_config: MockConfig) -> None:
    """Test unsetting an invalid configuration key."""
    with pytest.raises(ValueError, match="Unknown configuration key"):
        test_config.unset("invalid_key")  # Key that doesn't exist in config at all


def test_config_unset_nonexistent_key(test_config: MockConfig) -> None:
    """Test unsetting a key that doesn't exist in the configuration."""
    with pytest.raises(ValueError, match="Unknown configuration key"):
        test_config.unset("nonexistent_key")


def test_config_invalid_key(test_config: MockConfig) -> None:
    """Test setting invalid configuration key."""
    with pytest.raises(ValueError, match="Unknown configuration key"):
        test_config.set("invalid_key", "value")


def test_config_invalid_type_conversion(test_config: MockConfig) -> None:
    """Test invalid type conversion."""
    # Test invalid boolean
    with pytest.raises(ValueError, match="Invalid value for display.show_raw_output"):
        test_config.set("display.show_raw_output", "not_a_bool")

    # Test invalid integer conversion
    with pytest.raises(ValueError, match="Invalid value for proxy.timeout_seconds"):
        test_config.set("proxy.timeout_seconds", "not_a_number")


def test_config_invalid_allowed_values(test_config: MockConfig) -> None:
    """Test that invalid values for config keys raise ValueError."""
    # theme: invalid value
    with pytest.raises(ValueError):
        test_config.set("display.theme", "not-a-theme")
    # log_level: invalid value
    with pytest.raises(ValueError):
        test_config.set("system.log_level", "not-a-level")

    # Patch is_valid_llm_model_name for the model tests
    # The slow part is the model validation, so we mock it here.
    with patch("vibectl.config.is_valid_llm_model_name") as mock_is_valid_llm:
        # Configure mock to simulate an invalid model name
        mock_is_valid_llm.return_value = (False, "Mocked: Model not recognized")
        with pytest.raises(ValueError, match="Mocked: Model not recognized"):
            test_config.set("llm.model", "invalid-model-name-123")
        # Ensure our mock was called with the correct model name
        mock_is_valid_llm.assert_called_once_with("invalid-model-name-123")

        # Reset mock for the next test case within this patched context
        mock_is_valid_llm.reset_mock()
        mock_is_valid_llm.return_value = (False, "Mocked: Alias not registered")
        with pytest.raises(ValueError, match="Mocked: Alias not registered"):
            test_config.set("llm.model", "unregistered-alias")
        mock_is_valid_llm.assert_called_once_with("unregistered-alias")

        # Example of testing a case that should pass if the mock allows it
        mock_is_valid_llm.reset_mock()
        mock_is_valid_llm.return_value = (True, None)  # Simulate a valid model
        test_config.set("llm.model", "valid-mocked-model")
        assert test_config.get("llm.model") == "valid-mocked-model"
        mock_is_valid_llm.assert_called_once_with("valid-mocked-model")


def test_config_convert_type_first_non_none(test_config: MockConfig) -> None:
    """Test type conversion uses first non-None type."""
    test_config.set("core.kubeconfig", "some/path")
    assert isinstance(test_config.get("core.kubeconfig"), str)


def test_config_convert_type_fallback(test_config: MockConfig) -> None:
    """Test type conversion fallback for tuples."""
    # This is a bit of a contrived test since we don't have a field with multiple
    # non-None types, but it exercises the code path
    test_config.set("core.kubeconfig", "fallback")
    assert test_config.get("core.kubeconfig") == "fallback"


def test_config_convert_type_exception_handling(test_config: MockConfig) -> None:
    """Test exception handling in type conversion."""
    # The convert_to_type method should handle conversion errors
    with pytest.raises(ValueError, match="Invalid value for memory.max_chars"):
        test_config.set("memory.max_chars", "not_an_int")


def test_config_get_all(test_config: MockConfig) -> None:
    """Test getting all configuration values."""
    all_config = test_config.get_all()
    assert isinstance(all_config, dict)
    assert "display" in all_config
    assert all_config["display"]["theme"] == "default"  # Default


def test_config_handle_none_value(test_config: MockConfig) -> None:
    """Test handling None values in allowed fields."""
    # kubeconfig can be None
    test_config.set("core.kubeconfig", None)
    assert test_config.get("core.kubeconfig") is None


def test_config_save_explicit(test_config: MockConfig) -> None:
    """Test explicitly saving configuration."""
    test_config.set("display.theme", "light")
    assert test_config.get("display.theme") == "light"

    # This would normally save to file, but our mock version is a no-op
    test_config.save()

    # Value should still be in memory
    assert test_config.get("display.theme") == "light"


def test_config_empty_file() -> None:
    """Test handling of empty configuration file."""
    with TemporaryDirectory() as temp_dir:
        config_dir = Path(temp_dir) / ".config" / "vibectl" / "client"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "config.yaml"
        # Create an empty file
        with open(config_file, "w"):
            pass

        # Initialize config with the empty file
        config = Config(Path(temp_dir))

        # Config should be initialized with defaults
        assert config.get("display.theme") == "default"  # Default theme


def test_config_load_error() -> None:
    """Test error handling when loading config with invalid YAML."""
    with TemporaryDirectory() as temp_dir:
        config_dir = Path(temp_dir) / ".config" / "vibectl" / "client"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "config.yaml"

        # Create a non-empty file so that yaml.safe_load gets called
        with open(config_file, "w") as f:
            f.write("display:\n  theme: dark\n")

        # Mock yaml.safe_load to raise a YAMLError
        error_msg = "Simulated YAML error"
        error = yaml.YAMLError(error_msg)
        with (
            patch("yaml.safe_load", side_effect=error),
            pytest.raises(ValueError, match="Failed to load config"),
        ):
            # Should raise ValueError when trying to load
            Config(Path(temp_dir))


def test_config_save_error() -> None:
    """Test error handling when saving config fails."""
    with TemporaryDirectory() as temp_dir:
        config_dir = Path(temp_dir) / ".config" / "vibectl" / "client"
        config_dir.mkdir(parents=True, exist_ok=True)

        # Initialize config first (this should work)
        config = Config(Path(temp_dir))

        # Set up a mock that allows reads but fails on writes
        original_open = open

        def mock_open(*args: Any, **kwargs: Any) -> Any:
            # Check if this is a write operation
            if len(args) > 1 and "w" in str(args[1]):
                raise OSError("File write error")
            # Otherwise, use the original open
            return original_open(*args, **kwargs)

        with (
            patch("builtins.open", side_effect=mock_open),
            pytest.raises(ValueError, match="Failed to save config"),
        ):
            config.set("display.theme", "dark")


def test_config_unset_special_case() -> None:
    """Test the special case handling in unset for test compatibility."""
    with pytest.raises(ValueError, match="Unknown configuration key"):
        config = Config()  # Use real config to test the actual implementation
        config.unset("invalid_key")  # This should match the special case


def test_config_unsupported_keys() -> None:
    """Test handling of unsupported keys in configuration file."""
    # Directly check the DEFAULT_CONFIG at the start
    print(f"DEFAULT_CONFIG at test start: {DEFAULT_CONFIG}")

    with TemporaryDirectory() as temp_dir:
        config_dir = Path(temp_dir) / ".config" / "vibectl" / "client"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "config.yaml"

        # Create a config file with some supported and unsupported keys
        config_data = {
            "display": {"theme": "dark"},  # Supported
            "unsupported_key": "some_value",  # Not supported
            "another_unsupported": {"nested": "value"},  # Not supported
        }

        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        # Initialize config
        config = Config(Path(temp_dir))

        # Should be able to access supported keys
        assert config.get("display.theme") == "dark"

        # Should be able to access unsupported keys that were loaded from file
        assert config.get("unsupported_key") == "some_value"
        assert config.get("another_unsupported") == {"nested": "value"}

        # Should not be able to set unsupported keys via the API
        with pytest.raises(ValueError, match="Unknown configuration key"):
            config.set("new_unsupported_key", "value")


def test_config_unset_unsupported_key() -> None:
    """Test unsetting an unsupported configuration key."""
    with TemporaryDirectory() as temp_dir:
        config_dir = Path(temp_dir) / ".config" / "vibectl" / "client"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "config.yaml"

        # Create a config file with unsupported key
        config_data = {"unsupported_key": "some_value"}

        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        # Initialize config
        config = Config(Path(temp_dir))

        # Should not be able to unset unsupported keys
        with pytest.raises(ValueError, match="Unknown configuration key"):
            config.unset("unsupported_key")


def test_config_load_file_ioerror() -> None:
    """Test error handling when loading config file fails with IOError."""
    with TemporaryDirectory() as temp_dir:
        config_dir = Path(temp_dir) / ".config" / "vibectl" / "client"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "config.yaml"

        # Create a valid config file
        with open(config_file, "w") as f:
            f.write("display:\n  theme: dark\n")

        # Patch open to raise IOError
        error_msg = "File read error"
        error = OSError(error_msg)
        with (
            patch("builtins.open", side_effect=error),
            pytest.raises(ValueError, match="Failed to load config"),
        ):
            Config(Path(temp_dir))


# CLI Config Command Tests


# Common fixtures for CLI tests (move to conftest.py?)
@pytest.fixture
def mock_handle_exception() -> Generator[Mock, None, None]:
    with patch("vibectl.cli.handle_exception") as mock:
        mock.side_effect = SystemExit(1)  # Simulate exit with error code
        yield mock


@pytest.fixture
def mock_config_class() -> Generator[Mock, None, None]:
    with patch("vibectl.cli.Config") as mock:
        # Return a mock instance when Config() is called
        mock_instance = Mock()
        mock.return_value = mock_instance
        yield mock  # Yield the class mock itself


@pytest.mark.asyncio
async def test_cli_config_set_save_error(
    mock_config_class: Mock, mock_handle_exception: Mock
) -> None:
    """Test CLI config set with save error."""
    # Simulate save error
    mock_config_instance = mock_config_class.return_value
    mock_config_instance.save.side_effect = ValueError("Save failed")

    # Get the command object
    config_cmd = cli.commands["config"]
    set_cmd = config_cmd.commands["set"]  # type: ignore[attr-defined]

    # Expect SystemExit(1) because mock_handle_exception raises it
    with pytest.raises(SystemExit) as exc_info:
        await set_cmd.main(["display.theme", "test"], standalone_mode=False)

    # Assertions
    assert exc_info.value.code == 1
    mock_handle_exception.assert_called_once_with(mock_config_instance.save.side_effect)


@pytest.mark.asyncio
async def test_cli_config_show_get_all_error(
    mock_config_class: Mock, mock_handle_exception: Mock
) -> None:
    """Test CLI config show with get_all error."""
    # Simulate get_all error
    mock_config_instance = mock_config_class.return_value
    get_all_error = ValueError("Get all failed")
    mock_config_instance.get_all.side_effect = get_all_error

    # Get the command object
    config_cmd = cli.commands["config"]
    show_cmd = config_cmd.commands["show"]  # type: ignore[attr-defined]

    # Expect SystemExit(1)
    with pytest.raises(SystemExit) as exc_info:
        await show_cmd.main([], standalone_mode=False)

    # Assertions
    assert exc_info.value.code == 1
    mock_handle_exception.assert_called_once_with(get_all_error)


@pytest.mark.asyncio
async def test_cli_config_unset_invalid_key_error(
    mock_config_class: Mock, mock_handle_exception: Mock
) -> None:
    """Test CLI config unset with invalid key error."""
    # Simulate unset error
    mock_config_instance = mock_config_class.return_value
    unset_error = ValueError("Unset failed")
    mock_config_instance.unset.side_effect = unset_error

    # Get the command object
    config_cmd = cli.commands["config"]
    unset_cmd = config_cmd.commands["unset"]  # type: ignore[attr-defined]

    # Expect SystemExit(1)
    with pytest.raises(SystemExit) as exc_info:
        await unset_cmd.main(["invalidkey"], standalone_mode=False)

    # Assertions
    assert exc_info.value.code == 1
    mock_handle_exception.assert_called_once_with(unset_error)


@pytest.mark.asyncio
async def test_cli_config_show_basic(mock_config_class: Mock) -> None:
    """Test basic CLI config show."""
    # Ensure get_all returns a dictionary
    mock_config_instance = mock_config_class.return_value
    mock_config_instance.get_all.return_value = {
        "display": {"theme": "test"},
        "llm": {"model": "test"},
    }

    runner = CliRunner()
    result = await runner.invoke(cli.commands["config"], ["show"])  # type: ignore[arg-type]

    # Assertions
    assert result.exit_code == 0


def test_config_handle_none_value_full(test_config: MockConfig) -> None:
    """Test that 'none' string is treated as a regular string value."""
    # "none" should be treated as a string, not converted to None
    test_config.set("core.kubeconfig", "none")
    assert test_config.get("core.kubeconfig") == "none"

    # Setting 'none' should fail validation if it's not a valid value for the field
    # Now expect the more detailed error message without the unset suggestion
    # (since display.theme doesn't allow None values)
    with pytest.raises(
        ValueError, match="Invalid value for display.theme: none.*Valid values are"
    ):
        test_config.set("display.theme", "none")


def test_config_helpful_unset_message_for_nullable_fields(
    test_config: MockConfig,
) -> None:
    """Test unset message is shown for nullable fields with enumerated values."""
    import vibectl.config

    # Temporarily add a test field that is nullable and has enumerated values
    original_schema = vibectl.config.CONFIG_SCHEMA.copy()
    original_valid_values = vibectl.config.CONFIG_VALID_VALUES.copy()

    try:
        # Add test field to schema and valid values
        vibectl.config.CONFIG_SCHEMA = {
            **original_schema,
            "test_section": {"nullable_enum": (str, type(None))},
        }
        vibectl.config.CONFIG_VALID_VALUES = {
            **original_valid_values,
            "nullable_enum": ["option1", "option2", "option3"],
        }

        # Create a new config instance to pick up the modified schema
        with TemporaryDirectory() as temp_dir:
            test_cfg = Config(Path(temp_dir))

            # Test that invalid value shows helpful message with unset suggestion
            # Use re.DOTALL flag to match newlines in the error message
            expected_pattern = (
                r"(?s)Invalid value for test_section\.nullable_enum: invalid.*"
                r"Valid values are.*To clear this setting, use: vibectl config "
                r"unset test_section\.nullable_enum"
            )
            with pytest.raises(ValueError, match=expected_pattern):
                test_cfg.set("test_section.nullable_enum", "invalid")

    finally:
        # Restore original schema and valid values
        vibectl.config.CONFIG_SCHEMA = original_schema
        vibectl.config.CONFIG_VALID_VALUES = original_valid_values


def test_config_convert_type_first_non_none_full(test_config: MockConfig) -> None:
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


def test_config_convert_type_fallback_full(test_config: MockConfig) -> None:
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
            # Test through the public API - the type conversion is now internal
            test_cfg.set("test_bad_schema", "test_value")
            result = test_cfg.get("test_bad_schema")
            assert result == "test_value"
    finally:
        # Restore the original schema
        vibectl.config.CONFIG_SCHEMA = original_schema


def test_config_convert_type_exception_handling_full(test_config: MockConfig) -> None:
    """Test convert_type exception handling with full mock schema injection."""
    import vibectl.config

    # Create a test schema with a type that will fail conversion
    class FailingType:
        def __init__(self, value: str) -> None:
            raise ValueError("Conversion always fails")

    original_schema = vibectl.config.CONFIG_SCHEMA.copy()
    try:
        # Apply our test schema - add to system section to be hierarchical
        vibectl.config.CONFIG_SCHEMA = {
            **original_schema,
            "system": {**original_schema["system"], "failing_type": FailingType},
        }

        # Add our test key to valid values
        if "system.failing_type" not in vibectl.config.CONFIG_VALID_VALUES:
            vibectl.config.CONFIG_VALID_VALUES["system.failing_type"] = ["any_value"]

        # Attempt to convert a value that will trigger the exception
        with TemporaryDirectory() as temp_dir:
            test_cfg = Config(Path(temp_dir))
            # Test through the public API - should get a proper error message
            with pytest.raises(
                ValueError, match="Invalid value for system.failing_type"
            ):
                test_cfg.set("system.failing_type", "any_value")
    finally:
        # Restore the original schema
        vibectl.config.CONFIG_SCHEMA = original_schema


def test_config_load_process() -> None:
    """Test the config loading process to understand behavior with unsupported keys."""
    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        config_dir = temp_path / ".config" / "vibectl" / "client"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "config.yaml"

        # Test 1: Create config file with valid and invalid keys
        config_data = {
            "display": {"theme": "dark"},
            "unsupported_key": "some_value",
        }
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        config = Config(temp_path)

        # Test that both supported and unsupported keys are available
        assert config.get("display.theme") == "dark"
        assert config.get("unsupported_key") == "some_value"

        # Test 2: Modify supported key
        config.set("display.theme", "light")
        assert config.get("display.theme") == "light"

        # Test 3: Try to modify unsupported key
        with pytest.raises(ValueError, match="Unknown configuration key"):
            config.set("unsupported_key", "new_value")


def test_valid_key_in_file_invalid_key_in_memory() -> None:
    """Test valid keys from file load but unsupported keys can't be set via API."""
    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        config_dir = temp_path / ".config" / "vibectl" / "client"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "config.yaml"

        # Create a config file with only valid keys
        config_data = {"display": {"theme": "dark"}}
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        config = Config(temp_path)

        # Valid key should work
        assert config.get("display.theme") == "dark"

        # Try to set an invalid key - should fail
        with pytest.raises(ValueError, match="Unknown configuration key"):
            config.set("invalid_key", "value")


def test_theme_validation() -> None:
    """Test validation of theme values."""
    config = Config()

    # Valid theme
    config.set("display.theme", "light")
    assert config.get("display.theme") == "light"

    # Invalid theme
    with pytest.raises(ValueError, match="Invalid value for display.theme"):
        config.set("display.theme", "invalid_theme")


def test_load_behavior_with_mock() -> None:
    """Test the config loading behavior by mocking yaml.safe_load."""
    with TemporaryDirectory() as temp_dir:
        # Setup
        temp_path = Path(temp_dir)
        config_dir = temp_path / ".config" / "vibectl" / "client"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "config.yaml"

        # Create a config file
        config_data = {"display": {"theme": "light"}}
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        # Mock yaml.safe_load to return a different value
        mock_data = {"display": {"theme": "dark"}}

        with patch("yaml.safe_load", return_value=mock_data):
            config = Config(temp_path)
            # Should use the mocked value
            assert config.get("display.theme") == "dark"


def test_config_debug_initialization() -> None:
    """Directly monkey-patch the Config initialization to understand the issue."""
    with TemporaryDirectory() as temp_dir:
        # Setup
        temp_path = Path(temp_dir)
        config_dir = temp_path / ".config" / "vibectl" / "client"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "config.yaml"

        # Create the actual config file
        config_data = {"display": {"theme": "light"}}
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        # Confirm file exists
        assert config_file.exists()

        # Initialize config and check
        config = Config(temp_path)
        assert config.get("display.theme") == "light"


def test_config_direct_patch() -> None:
    """Test default configuration behavior when no config file exists."""
    with TemporaryDirectory() as temp_dir:
        # Setup
        temp_path = Path(temp_dir)
        config_dir = temp_path / ".config" / "vibectl" / "client"
        config_dir.mkdir(parents=True, exist_ok=True)

        # Create config without any existing file
        config = Config(temp_path)
        # Should use default config since no file exists
        assert config.get("display.theme") == "default"


def test_load_file_in_temp() -> None:
    """Test loading a temporary file with no mocking to see default behavior."""
    # Create a temporary file
    with TemporaryDirectory() as temp_dir:
        # Setup manually
        temp_path = Path(temp_dir) / ".config" / "vibectl" / "client"
        temp_path.mkdir(parents=True, exist_ok=True)
        config_file = temp_path / "config.yaml"

        # Create a minimal config file
        with open(config_file, "w") as f:
            f.write("display:\n  theme: dark\n")

        # Make sure it exists
        assert config_file.exists()

        # Load config
        config = Config(Path(temp_dir))
        assert config.get("display.theme") == "dark"


def test_mockconfig_get_model_key_none_behavior() -> None:
    config = MockConfig()
    config._config["llm"]["model_keys"] = {"openai": None}
    assert config.get_model_key("openai") is None


def test_config_ollama_model_pattern_allowed(test_config: MockConfig) -> None:
    """Test that any ollama:<model> value is accepted for model config key.

    We mock the underlying llm validation to isolate the config logic.
    """
    # Should not raise because we mock the validation check
    with patch("vibectl.config.is_valid_llm_model_name", return_value=(True, None)):
        test_config.set("llm.model", "ollama:some-ollama-model")
        assert test_config.get("llm.model") == "ollama:some-ollama-model"

    # Test that an ollama model that ISN'T valid according to llm *does* raise
    # when the mock is removed (or returns False)
    with (
        patch(
            "vibectl.config.is_valid_llm_model_name",
            return_value=(False, "LLM says no"),
        ),
        pytest.raises(ValueError, match="LLM says no"),
    ):
        test_config.set("llm.model", "ollama:invalid-model-for-test")


# Proxy Configuration Validation Tests


def test_proxy_server_url_validation_valid_urls(test_config: MockConfig) -> None:
    """Test that valid proxy server URLs are accepted."""
    valid_urls = [
        "vibectl-server://localhost:50051",
        "vibectl-server-insecure://localhost:8080",
    ]

    for url in valid_urls:
        test_config.set("proxy.server_url", url)
        assert test_config.get("proxy.server_url") == url


def test_proxy_server_url_validation_invalid_urls(test_config: MockConfig) -> None:
    """Test that invalid proxy server URLs are rejected."""
    invalid_urls = [
        "http://localhost:50051",  # Wrong scheme
        "https://localhost:50051",  # Wrong scheme
        "ftp://localhost:50051",  # Wrong scheme
        "vibectl-server://",  # Missing host
        "vibectl-server://:50051",  # Missing host
        "invalid-url",  # Not a URL at all
        "vibectl-server://host:abc",  # Invalid port
    ]

    for url in invalid_urls:
        with pytest.raises(ValueError, match="Invalid proxy URL"):
            test_config.set("proxy.server_url", url)


def test_proxy_server_url_jwt_token_format_validation(test_config: MockConfig) -> None:
    """Test JWT token handling in proxy server URLs."""
    # Valid URLs with tokens (tokens are treated as opaque strings)
    valid_urls_with_tokens = [
        "vibectl-server://eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJzdWIifQ.sig@host:443",
        "vibectl-server-insecure://a.b.c@localhost:50051",
        "vibectl-server://simple-token@example.com:443",
        "vibectl-server://abc123@example.com:443",
    ]

    # These should all work (tokens are treated as opaque)
    for url in valid_urls_with_tokens:
        test_config.set("proxy.server_url", url)
        assert test_config.get("proxy.server_url") == url

    # URLs without tokens should also work
    token_optional_urls = [
        "vibectl-server://host:443",
        "vibectl-server-insecure://localhost:50051",
    ]

    for url in token_optional_urls:
        test_config.set("proxy.server_url", url)
        assert test_config.get("proxy.server_url") == url


def test_proxy_server_url_none_allowed(test_config: MockConfig) -> None:
    """Test that proxy.server_url can be set to None."""
    test_config.set("proxy.server_url", None)
    assert test_config.get("proxy.server_url") is None

    # Test string "none" is treated as a string but fails validation since
    # it's not a valid proxy URL
    with pytest.raises(ValueError, match="Invalid proxy URL for proxy.server_url"):
        test_config.set("proxy.server_url", "none")


def test_proxy_timeout_seconds_validation_valid_values(test_config: MockConfig) -> None:
    """Test that valid timeout values are accepted."""
    valid_timeouts = [1, 30, 60, 120, 300]  # 1 second to 5 minutes

    for timeout in valid_timeouts:
        test_config.set("proxy.timeout_seconds", timeout)
        assert test_config.get("proxy.timeout_seconds") == timeout


def test_proxy_timeout_seconds_validation_invalid_values(
    test_config: MockConfig,
) -> None:
    """Test that invalid timeout values are rejected."""
    invalid_timeouts = [0, -1, 301, 1000]  # Below min, above max

    for timeout in invalid_timeouts:
        with pytest.raises(ValueError, match="Must be between 1 and 300"):
            test_config.set("proxy.timeout_seconds", timeout)


def test_proxy_retry_attempts_validation_valid_values(
    test_config: MockConfig,
) -> None:
    """Test that valid retry attempt values are accepted."""
    valid_retries = [0, 1, 3, 5, 10]  # 0 to 10 retries

    for retries in valid_retries:
        test_config.set("proxy.retry_attempts", retries)
        assert test_config.get("proxy.retry_attempts") == retries


def test_proxy_retry_attempts_validation_invalid_values(
    test_config: MockConfig,
) -> None:
    """Test that invalid retry attempt values are rejected."""
    invalid_retries = [-1, 11, 20, 100]  # Below min, above max

    for retries in invalid_retries:
        with pytest.raises(ValueError, match="Must be between 0 and 10"):
            test_config.set("proxy.retry_attempts", retries)


def test_proxy_enabled_boolean_validation(test_config: MockConfig) -> None:
    """Test that proxy.enabled only accepts boolean values."""
    # Valid boolean values
    test_config.set("proxy.enabled", True)
    assert test_config.get("proxy.enabled") is True

    test_config.set("proxy.enabled", False)
    assert test_config.get("proxy.enabled") is False

    # String boolean representations
    test_config.set("proxy.enabled", "true")
    assert test_config.get("proxy.enabled") is True

    test_config.set("proxy.enabled", "false")
    assert test_config.get("proxy.enabled") is False


def test_proxy_type_validation(test_config: MockConfig) -> None:
    """Test that proxy configuration values require correct types."""
    # timeout_seconds must be numeric
    with pytest.raises(ValueError, match="Invalid value for proxy.timeout_seconds"):
        test_config.set("proxy.timeout_seconds", "not-a-number")

    # retry_attempts must be numeric
    with pytest.raises(ValueError, match="Invalid value for proxy.retry_attempts"):
        test_config.set("proxy.retry_attempts", "not-a-number")


def test_proxy_edge_cases(test_config: MockConfig) -> None:
    """Test edge cases for proxy configuration validation."""
    # Boundary values should work
    test_config.set("proxy.timeout_seconds", 1)  # Minimum
    assert test_config.get("proxy.timeout_seconds") == 1

    test_config.set("proxy.timeout_seconds", 300)  # Maximum
    assert test_config.get("proxy.timeout_seconds") == 300

    test_config.set("proxy.retry_attempts", 0)  # Minimum (no retries)
    assert test_config.get("proxy.retry_attempts") == 0

    test_config.set("proxy.retry_attempts", 10)  # Maximum
    assert test_config.get("proxy.retry_attempts") == 10


def test_proxy_unset_behavior(test_config: MockConfig) -> None:
    """Test that unsetting proxy configuration resets to defaults."""
    # Set non-default values
    test_config.set("proxy.enabled", True)
    test_config.set("proxy.timeout_seconds", 60)
    test_config.set("proxy.retry_attempts", 5)

    # Unset should restore defaults
    test_config.unset("proxy.enabled")
    assert test_config.get("proxy.enabled") is False  # Default

    test_config.unset("proxy.timeout_seconds")
    assert test_config.get("proxy.timeout_seconds") == 30  # Default

    test_config.unset("proxy.retry_attempts")
    assert test_config.get("proxy.retry_attempts") == 3  # Default


def test_jwt_token_validation_helper() -> None:
    """Test the JWT token format validation helper function."""
    # This test is no longer relevant since we simplified token handling
    # Tokens are now treated as opaque strings, no validation needed
    pass


def test_proxy_url_parsing_with_jwt_validation() -> None:
    """Test proxy URL parsing with token handling."""

    # Any token format should work
    simple_token = "simple_token_123"

    # Valid URL with token
    config = parse_proxy_url(f"vibectl-server://{simple_token}@example.com:443")
    assert config is not None
    assert config.host == "example.com"
    assert config.port == 443
    assert config.jwt_token == simple_token
    assert config.use_tls is True


def test_get_model_key_file_from_env_var(test_config: MockConfig) -> None:
    """Test getting model key file from environment variable."""
    env_var = "ANTHROPIC_API_KEY_FILE"
    test_file = "/env/path/anthropic_key"

    with patch.dict("os.environ", {env_var: test_file}):
        result = test_config.get_model_key_file("anthropic")
        assert result == test_file


def test_get_ca_bundle_path_from_config(test_config: MockConfig) -> None:
    """Test getting CA bundle path from configuration."""
    ca_bundle_path = "/config/path/to/ca.pem"
    test_config.set("proxy.ca_bundle_path", ca_bundle_path)

    result = test_config.get_ca_bundle_path()
    assert result == ca_bundle_path


def test_get_ca_bundle_path_from_env_var(test_config: MockConfig) -> None:
    """Test getting CA bundle path from environment variable."""
    ca_bundle_path = "/env/path/to/ca.pem"

    with patch.dict("os.environ", {"VIBECTL_CA_BUNDLE": ca_bundle_path}):
        result = test_config.get_ca_bundle_path()
        assert result == ca_bundle_path


def test_get_ca_bundle_path_env_overrides_config(test_config: MockConfig) -> None:
    """Test that environment variable overrides config for CA bundle path."""
    config_path = "/config/path/to/ca.pem"
    env_path = "/env/path/to/ca.pem"

    test_config.set("proxy.ca_bundle_path", config_path)

    with patch.dict("os.environ", {"VIBECTL_CA_BUNDLE": env_path}):
        result = test_config.get_ca_bundle_path()
        assert result == env_path


def test_get_ca_bundle_path_returns_none_when_not_configured(
    test_config: MockConfig,
) -> None:
    """Test getting CA bundle path returns None when not configured."""
    result = test_config.get_ca_bundle_path()
    assert result is None
