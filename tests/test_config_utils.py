"""Tests for config_utils module.

This module provides comprehensive tests for the configuration utility functions
used by both client and server components.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import yaml

from vibectl.config_utils import (
    convert_string_to_bool,
    convert_string_to_list,
    convert_string_to_type,
    deep_merge,
    ensure_config_dir,
    get_config_dir,
    get_env_with_fallbacks,
    get_nested_value,
    load_yaml_config,
    read_key_from_file,
    save_yaml_config,
    set_nested_value,
    validate_config_key_path,
    validate_numeric_range,
)


class TestGetConfigDir:
    """Test get_config_dir function."""

    def test_get_config_dir_client(self) -> None:
        """Test getting client config directory."""
        result = get_config_dir("client")
        # The path should end with "client" component
        assert result.name == "client"

    def test_get_config_dir_server(self) -> None:
        """Test getting server config directory."""
        result = get_config_dir("server")
        # The path should end with "server" component
        assert result.name == "server"

    def test_get_config_dir_invalid_component(self) -> None:
        """Test getting config directory with invalid component."""
        with pytest.raises(ValueError, match="Invalid component"):
            get_config_dir("invalid")

    def test_get_config_dir_with_base_dir(self) -> None:
        """Test getting config directory with custom base directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            result = get_config_dir("client", base_dir)
            expected = base_dir / ".config" / "vibectl" / "client"
            assert result == expected

    @patch.dict(os.environ, {"VIBECTL_CLIENT_CONFIG_DIR": "/custom/client"})
    def test_get_config_dir_component_specific_env(self) -> None:
        """Test getting config directory with component-specific env variable."""
        result = get_config_dir("client")
        assert result == Path("/custom/client")

    @patch.dict(os.environ, {"VIBECTL_CONFIG_DIR": "/custom/base"})
    def test_get_config_dir_generic_env(self) -> None:
        """Test getting config directory with generic environment variable."""
        result = get_config_dir("client")
        assert result == Path("/custom/base/client")

    @patch.dict(os.environ, {}, clear=True)
    @patch("vibectl.config_utils.Path.home", return_value=Path("/mock/home"))
    def test_get_config_dir_default_behavior(self, mock_home: Mock) -> None:
        """Test getting config directory with default behavior."""
        result = get_config_dir("client")
        assert result.name == "client"
        assert "vibectl" in str(result)


class TestEnsureConfigDir:
    """Test ensure_config_dir function."""

    def test_ensure_config_dir_creates_directory(self) -> None:
        """Test that ensure_config_dir creates the directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            result = ensure_config_dir("client", base_dir)
            assert result.exists()
            assert result.is_dir()


class TestLoadYamlConfig:
    """Test load_yaml_config function."""

    def test_load_yaml_config_existing_file(self) -> None:
        """Test loading YAML config from existing file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({"key": "value"}, f)
            f.flush()

            result = load_yaml_config(Path(f.name))
            assert result == {"key": "value"}

            # Clean up
            Path(f.name).unlink()

    def test_load_yaml_config_nonexistent_file(self) -> None:
        """Test loading YAML config from non-existent file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "nonexistent.yaml"
            result = load_yaml_config(config_file)
            assert result == {}

    def test_load_yaml_config_empty_file(self) -> None:
        """Test loading YAML config from empty file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            # Write nothing to create empty file
            f.flush()

            result = load_yaml_config(Path(f.name))
            assert result == {}

            # Clean up
            Path(f.name).unlink()

    def test_load_yaml_config_with_defaults(self) -> None:
        """Test loading YAML config with defaults."""
        defaults = {"default_key": "default_value", "shared_key": "default"}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({"shared_key": "loaded", "loaded_key": "loaded_value"}, f)
            f.flush()

            result = load_yaml_config(Path(f.name), defaults)
            assert result["default_key"] == "default_value"
            assert result["shared_key"] == "loaded"  # Loaded value overrides default
            assert result["loaded_key"] == "loaded_value"

            # Clean up
            Path(f.name).unlink()

    def test_load_yaml_config_yaml_error(self) -> None:
        """Test loading YAML config with YAML error."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("invalid: yaml: content:")  # Invalid YAML
            f.flush()

            with pytest.raises(ValueError, match="Failed to load config"):
                load_yaml_config(Path(f.name))

            # Clean up
            Path(f.name).unlink()

    @patch("vibectl.config_utils.Path.exists", return_value=False)
    def test_load_yaml_config_os_error(self, mock_exists: Mock) -> None:
        """Test loading YAML config with OS error (file doesn't exist)."""
        config_file = Path("/fake/path.yaml")
        # When file doesn't exist, it should return empty dict, not raise
        result = load_yaml_config(config_file)
        assert result == {}


class TestSaveYamlConfig:
    """Test save_yaml_config function."""

    def test_save_yaml_config_basic(self) -> None:
        """Test saving YAML config."""
        config = {"key": "value", "number": 42}

        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "test.yaml"
            save_yaml_config(config, config_file)

            # Verify file was created and contains correct data
            assert config_file.exists()
            with open(config_file) as f:
                loaded = yaml.safe_load(f)
            assert loaded == config

    def test_save_yaml_config_with_comment(self) -> None:
        """Test saving YAML config with comment."""
        config = {"key": "value"}
        comment = "This is a test config file"

        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "test.yaml"
            save_yaml_config(config, config_file, comment)

            # Verify file contains comment
            content = config_file.read_text()
            assert "# This is a test config file" in content

    def test_save_yaml_config_multiline_comment(self) -> None:
        """Test saving YAML config with multiline comment."""
        config = {"key": "value"}
        comment = "Line 1\nLine 2\nLine 3"

        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "test.yaml"
            save_yaml_config(config, config_file, comment)

            # Verify file contains all comment lines
            content = config_file.read_text()
            assert "# Line 1" in content
            assert "# Line 2" in content
            assert "# Line 3" in content

    def test_save_yaml_config_creates_directory(self) -> None:
        """Test that save_yaml_config creates parent directories."""
        config = {"key": "value"}

        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "subdir" / "test.yaml"
            save_yaml_config(config, config_file)

            # Verify parent directory was created
            assert config_file.parent.exists()
            assert config_file.exists()

    @patch("builtins.open", side_effect=OSError("Permission denied"))
    def test_save_yaml_config_os_error(self, mock_open: Mock) -> None:
        """Test saving YAML config with OS error."""
        config = {"key": "value"}
        config_file = Path("/fake/path.yaml")

        with pytest.raises(ValueError, match="Failed to save config"):
            save_yaml_config(config, config_file)


class TestDeepMerge:
    """Test deep_merge function."""

    def test_deep_merge_simple(self) -> None:
        """Test deep merge with simple dictionaries."""
        base = {"a": 1, "b": 2}
        updates = {"b": 3, "c": 4}

        deep_merge(base, updates)

        assert base == {"a": 1, "b": 3, "c": 4}

    def test_deep_merge_nested(self) -> None:
        """Test deep merge with nested dictionaries."""
        base = {"level1": {"a": 1, "b": 2}, "other": "value"}
        updates = {"level1": {"b": 3, "c": 4}}

        deep_merge(base, updates)

        assert base == {"level1": {"a": 1, "b": 3, "c": 4}, "other": "value"}

    def test_deep_merge_overwrite_non_dict(self) -> None:
        """Test deep merge overwrites non-dict values."""
        base = {"key": "string_value"}
        updates = {"key": {"nested": "value"}}

        deep_merge(base, updates)

        assert base == {"key": {"nested": "value"}}


class TestGetNestedValue:
    """Test get_nested_value function."""

    def test_get_nested_value_simple(self) -> None:
        """Test getting simple nested value."""
        config = {"a": {"b": {"c": "value"}}}
        result = get_nested_value(config, "a.b.c")
        assert result == "value"

    def test_get_nested_value_top_level(self) -> None:
        """Test getting top-level value."""
        config = {"key": "value"}
        result = get_nested_value(config, "key")
        assert result == "value"

    def test_get_nested_value_missing_key(self) -> None:
        """Test getting missing nested value."""
        config = {"a": {"b": "value"}}
        with pytest.raises(KeyError, match="Config path not found: a.c"):
            get_nested_value(config, "a.c")

    def test_get_nested_value_non_dict_intermediate(self) -> None:
        """Test getting nested value with non-dict intermediate."""
        config = {"a": "not_a_dict"}
        with pytest.raises(KeyError, match="Config path not found: a.b"):
            get_nested_value(config, "a.b")


class TestSetNestedValue:
    """Test set_nested_value function."""

    def test_set_nested_value_new_path(self) -> None:
        """Test setting nested value with new path."""
        config: dict = {}
        set_nested_value(config, "a.b.c", "value")
        assert config == {"a": {"b": {"c": "value"}}}

    def test_set_nested_value_existing_path(self) -> None:
        """Test setting nested value in existing path."""
        config = {"a": {"b": {"c": "old"}}}
        set_nested_value(config, "a.b.c", "new")
        assert config["a"]["b"]["c"] == "new"

    def test_set_nested_value_top_level(self) -> None:
        """Test setting top-level value."""
        config: dict = {}
        set_nested_value(config, "key", "value")
        assert config == {"key": "value"}

    def test_set_nested_value_non_dict_intermediate(self) -> None:
        """Test setting nested value with non-dict intermediate."""
        config = {"a": "not_a_dict"}
        with pytest.raises(
            ValueError, match="Cannot set nested value: a is not a dictionary"
        ):
            set_nested_value(config, "a.b", "value")


class TestValidateConfigKeyPath:
    """Test validate_config_key_path function."""

    def test_validate_config_key_path_valid(self) -> None:
        """Test validating valid config key path."""
        schema = {"a": {"b": {"c": "type"}}}
        # Should not raise
        validate_config_key_path("a.b.c", schema)

    def test_validate_config_key_path_invalid_section(self) -> None:
        """Test validating invalid config section."""
        schema = {"a": {"b": "type"}}
        with pytest.raises(ValueError, match="Invalid config section: invalid"):
            validate_config_key_path("invalid.b", schema)

    def test_validate_config_key_path_invalid_nested(self) -> None:
        """Test validating invalid nested config path."""
        schema = {"a": {"b": "type"}}
        with pytest.raises(ValueError, match="'invalid' not found in section 'a'"):
            validate_config_key_path("a.invalid", schema)


class TestConvertStringToBool:
    """Test convert_string_to_bool function."""

    def test_convert_string_to_bool_true_values(self) -> None:
        """Test converting true string values to bool."""
        true_values = ["true", "yes", "1", "on", "TRUE", "YES", "ON"]
        for value in true_values:
            assert convert_string_to_bool(value) is True

    def test_convert_string_to_bool_false_values(self) -> None:
        """Test converting false string values to bool."""
        false_values = ["false", "no", "0", "off", "FALSE", "NO", "OFF"]
        for value in false_values:
            assert convert_string_to_bool(value) is False

    def test_convert_string_to_bool_invalid(self) -> None:
        """Test converting invalid string to bool."""
        with pytest.raises(ValueError, match="Invalid boolean value: invalid"):
            convert_string_to_bool("invalid")


class TestConvertStringToList:
    """Test convert_string_to_list function."""

    def test_convert_string_to_list_bracket_format(self) -> None:
        """Test converting bracket format string to list."""
        result = convert_string_to_list("['item1', 'item2', 'item3']")
        assert result == ["item1", "item2", "item3"]

    def test_convert_string_to_list_comma_separated(self) -> None:
        """Test converting comma-separated string to list."""
        result = convert_string_to_list("item1, item2, item3")
        assert result == ["item1", "item2", "item3"]

    def test_convert_string_to_list_single_value(self) -> None:
        """Test converting single value string to list."""
        result = convert_string_to_list("single_item")
        assert result == ["single_item"]

    def test_convert_string_to_list_empty_string(self) -> None:
        """Test converting empty string to list."""
        result = convert_string_to_list("")
        assert result == []

    def test_convert_string_to_list_quoted_items(self) -> None:
        """Test converting quoted items to list."""
        result = convert_string_to_list('"item1", "item2", "item3"')
        assert result == ["item1", "item2", "item3"]

    def test_convert_string_to_list_invalid_bracket_format(self) -> None:
        """Test converting invalid bracket format falls back to comma parsing."""
        result = convert_string_to_list("[invalid, bracket, format")
        assert result == ["[invalid", "bracket", "format"]


class TestConvertStringToType:
    """Test convert_string_to_type function."""

    def test_convert_string_to_type_none(self) -> None:
        """Test that 'none' string is treated as a regular string value."""
        # "none" should always be treated as a string, not converted to None
        result = convert_string_to_type("none", str)
        assert result == "none"

        # Even when None is allowed, "none" should remain a string
        result = convert_string_to_type("none", (str, type(None)))
        assert result == "none"

    def test_convert_string_to_type_bool(self) -> None:
        """Test converting string to bool."""
        assert convert_string_to_type("true", bool) is True
        assert convert_string_to_type("false", bool) is False

    def test_convert_string_to_type_int(self) -> None:
        """Test converting string to int."""
        result = convert_string_to_type("42", int)
        assert result == 42

    def test_convert_string_to_type_float(self) -> None:
        """Test converting string to float."""
        result = convert_string_to_type("3.14", float)
        assert result == 3.14

    def test_convert_string_to_type_list(self) -> None:
        """Test converting string to list."""
        result = convert_string_to_type("item1,item2", list)
        assert result == ["item1", "item2"]

    def test_convert_string_to_type_tuple_with_bool(self) -> None:
        """Test converting string with tuple type containing bool."""
        result = convert_string_to_type("true", (bool, str))
        assert result is True

    def test_convert_string_to_type_tuple_with_int(self) -> None:
        """Test converting string with tuple type containing int."""
        result = convert_string_to_type("42", (int, str))
        assert result == 42

    def test_convert_string_to_type_tuple_with_none(self) -> None:
        """Test converting string with tuple type containing None."""
        result = convert_string_to_type("test", (type(None), str))
        assert result == "test"

    def test_convert_string_to_type_custom_class(self) -> None:
        """Test converting string with custom class type."""

        class CustomType:
            def __init__(self, value: str) -> None:
                self.value = value

        result = convert_string_to_type("test", CustomType)
        assert isinstance(result, CustomType)
        assert result.value == "test"

    def test_convert_string_to_type_invalid_conversion(self) -> None:
        """Test converting string with invalid conversion."""
        with pytest.raises(ValueError, match="Invalid value for field"):
            convert_string_to_type("invalid", int, "field")

    def test_convert_string_to_type_custom_class_in_tuple(self) -> None:
        """Test converting string with custom class in tuple."""

        class CustomType:
            def __init__(self, value: str) -> None:
                self.value = value

        result = convert_string_to_type("test", (CustomType, str))
        assert isinstance(result, CustomType)
        assert result.value == "test"


class TestGetEnvWithFallbacks:
    """Test get_env_with_fallbacks function."""

    @patch.dict(os.environ, {"PRIMARY": "primary_value"})
    def test_get_env_with_fallbacks_primary(self) -> None:
        """Test getting environment variable with primary value."""
        result = get_env_with_fallbacks(
            "PRIMARY", ["FALLBACK1", "FALLBACK2"], "default"
        )
        assert result == "primary_value"

    @patch.dict(os.environ, {"FALLBACK1": "fallback_value"}, clear=True)
    def test_get_env_with_fallbacks_fallback(self) -> None:
        """Test getting environment variable with fallback value."""
        result = get_env_with_fallbacks(
            "PRIMARY", ["FALLBACK1", "FALLBACK2"], "default"
        )
        assert result == "fallback_value"

    @patch.dict(os.environ, {}, clear=True)
    def test_get_env_with_fallbacks_default(self) -> None:
        """Test getting environment variable with default value."""
        result = get_env_with_fallbacks(
            "PRIMARY", ["FALLBACK1", "FALLBACK2"], "default"
        )
        assert result == "default"

    @patch.dict(os.environ, {}, clear=True)
    def test_get_env_with_fallbacks_none(self) -> None:
        """Test getting environment variable with no fallbacks."""
        result = get_env_with_fallbacks("PRIMARY")
        assert result is None


class TestReadKeyFromFile:
    """Test read_key_from_file function."""

    def test_read_key_from_file_existing(self) -> None:
        """Test reading key from existing file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("secret_key_content\n")
            f.flush()

            result = read_key_from_file(f.name)
            assert result == "secret_key_content"

            # Clean up
            Path(f.name).unlink()

    def test_read_key_from_file_nonexistent(self) -> None:
        """Test reading key from non-existent file."""
        result = read_key_from_file("/nonexistent/file.key")
        assert result is None

    def test_read_key_from_file_with_path_object(self) -> None:
        """Test reading key from file using Path object."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("secret_key_content")
            f.flush()

            result = read_key_from_file(Path(f.name))
            assert result == "secret_key_content"

            # Clean up
            Path(f.name).unlink()

    @patch("pathlib.Path.read_text", side_effect=OSError("Permission denied"))
    def test_read_key_from_file_os_error(self, mock_read_text: Mock) -> None:
        """Test reading key from file with OS error."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.flush()

            result = read_key_from_file(f.name)
            assert result is None

            # Clean up
            Path(f.name).unlink()


class TestValidateNumericRange:
    """Test validate_numeric_range function."""

    def test_validate_numeric_range_valid_int(self) -> None:
        """Test validating valid integer range."""
        # Should not raise
        validate_numeric_range(5, 1, 10, "test_field")

    def test_validate_numeric_range_valid_float(self) -> None:
        """Test validating valid float range."""
        # Should not raise
        validate_numeric_range(5.5, 1.0, 10.0, "test_field")

    def test_validate_numeric_range_invalid_type(self) -> None:
        """Test validating invalid type."""
        with pytest.raises(ValueError, match="Invalid type for test_field"):
            validate_numeric_range("not_a_number", 1, 10, "test_field")

    def test_validate_numeric_range_below_min(self) -> None:
        """Test validating value below minimum."""
        with pytest.raises(ValueError, match="Invalid value for test_field: 0"):
            validate_numeric_range(0, 1, 10, "test_field")

    def test_validate_numeric_range_above_max(self) -> None:
        """Test validating value above maximum."""
        with pytest.raises(ValueError, match="Invalid value for test_field: 15"):
            validate_numeric_range(15, 1, 10, "test_field")

    def test_validate_numeric_range_at_boundaries(self) -> None:
        """Test validating values at boundaries."""
        # Should not raise
        validate_numeric_range(1, 1, 10, "test_field")
        validate_numeric_range(10, 1, 10, "test_field")
