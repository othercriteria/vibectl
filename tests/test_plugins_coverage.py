"""
Additional tests for vibectl/plugins.py to improve test coverage.

This module focuses on testing edge cases and error conditions that are not
covered by the main plugin management tests.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from vibectl.config import Config
from vibectl.plugins import (
    Plugin,
    PluginMetadata,
    PluginStore,
    PromptMapping,
    PromptResolver,
)


class TestPromptMappingEdgeCases:
    """Test edge cases and error conditions for PromptMapping."""

    def test_prompt_mapping_getitem_key_error(self) -> None:
        """Test that PromptMapping raises KeyError for missing keys."""
        mapping = PromptMapping({"existing_key": "value"})

        # Should work for existing key
        assert mapping["existing_key"] == "value"

        # Should raise KeyError for missing key
        with pytest.raises(KeyError):
            _ = mapping["missing_key"]

    def test_prompt_mapping_contains(self) -> None:
        """Test the __contains__ method."""
        mapping = PromptMapping({"key1": "value1", "key2": None})

        assert "key1" in mapping
        assert "key2" in mapping  # None values should still be "in" the mapping
        assert "missing_key" not in mapping

    def test_prompt_mapping_keys_and_items(self) -> None:
        """Test keys() and items() methods."""
        data = {"key1": "value1", "key2": "value2"}
        mapping = PromptMapping(data)

        # Test keys()
        keys = list(mapping.keys())
        assert set(keys) == {"key1", "key2"}

        # Test items()
        items = list(mapping.items())
        assert set(items) == {("key1", "value1"), ("key2", "value2")}

    def test_prompt_metadata_with_non_dict_value(self) -> None:
        """Test prompt_metadata property with non-dict metadata."""
        # Test with None metadata
        mapping = PromptMapping({"prompt_metadata": None})
        assert mapping.prompt_metadata == {}

        # Test with string metadata - this will cause ValueError in
        # actual implementation
        # So we test that the ValueError is raised rather than expecting empty dict
        mapping = PromptMapping({"prompt_metadata": "not_a_dict"})
        with pytest.raises(ValueError):
            _ = mapping.prompt_metadata

        # Test with missing metadata
        mapping = PromptMapping({})
        assert mapping.prompt_metadata == {}

    def test_legacy_detection_edge_cases(self) -> None:
        """Test legacy prompt type detection edge cases."""
        # Planning prompt with empty string examples (should be False)
        mapping = PromptMapping({"examples": ""})
        assert not mapping.is_planning_prompt()

        # Summary prompt with empty string focus_points and example_format
        mapping = PromptMapping({"focus_points": "", "example_format": ""})
        assert not mapping.is_summary_prompt()

        # Summary prompt with None values
        mapping = PromptMapping({"focus_points": None, "example_format": None})
        assert not mapping.is_summary_prompt()


class TestPluginStoreErrorHandling:
    """Test error handling in PluginStore."""

    @patch("vibectl.plugins.Path.mkdir")
    def test_plugin_directory_creation_failure(self, mock_mkdir: Mock) -> None:
        """Test handling of plugin directory creation failure."""
        mock_mkdir.side_effect = OSError("Permission denied")

        with pytest.raises(OSError, match="Permission denied"):
            PluginStore()

    def test_uninstall_nonexistent_plugin(self) -> None:
        """Test uninstalling a plugin that doesn't exist."""
        with (
            tempfile.TemporaryDirectory() as tmp_dir,
            patch("vibectl.plugins.PluginStore._get_plugins_directory") as mock_get_dir,
        ):
            plugins_dir = Path(tmp_dir) / "plugins"
            plugins_dir.mkdir()
            mock_get_dir.return_value = plugins_dir

            store = PluginStore()

            with pytest.raises(ValueError, match="Plugin 'nonexistent' not found"):
                store.uninstall_plugin("nonexistent")

    def test_list_installed_plugins_with_corrupt_file(self) -> None:
        """Test listing plugins when there's a corrupted plugin file."""
        with (
            tempfile.TemporaryDirectory() as tmp_dir,
            patch("vibectl.plugins.PluginStore._get_plugins_directory") as mock_get_dir,
        ):
            plugins_dir = Path(tmp_dir) / "plugins"
            plugins_dir.mkdir()
            mock_get_dir.return_value = plugins_dir

            store = PluginStore()

            # Create a corrupted JSON file
            corrupt_file = plugins_dir / "corrupt-plugin.json"
            with open(corrupt_file, "w") as f:
                f.write("{ invalid json content")

            # Should handle the corrupt file gracefully and return empty list
            with patch("vibectl.plugins.logger") as mock_logger:
                plugins = store.list_installed_plugins()
                assert len(plugins) == 0
                mock_logger.warning.assert_called_once()
                assert "Failed to load plugin" in str(mock_logger.warning.call_args)

    def test_get_plugin_by_name_no_plugins(self) -> None:
        """Test get_plugin_by_name when no plugins exist."""
        with (
            tempfile.TemporaryDirectory() as tmp_dir,
            patch("vibectl.plugins.PluginStore._get_plugins_directory") as mock_get_dir,
        ):
            plugins_dir = Path(tmp_dir) / "plugins"
            plugins_dir.mkdir()
            mock_get_dir.return_value = plugins_dir

            store = PluginStore()
            result = store.get_plugin_by_name("nonexistent")
            assert result is None


class TestPluginValidationErrorCases:
    """Test plugin validation error conditions."""

    def test_validate_plugin_empty_name(self) -> None:
        """Test validation fails for plugin with empty name."""
        plugin = Plugin(
            metadata=PluginMetadata(
                name="",  # Empty name
                version="1.0.0",
                description="Test plugin",
                author="Test Author",
                compatible_vibectl_versions=">=0.8.0,<1.0.0",
                created_at="2024-01-15T10:00:00Z",
            ),
            prompt_mappings={"test": PromptMapping({"description": "test"})},
        )

        with (
            tempfile.TemporaryDirectory() as tmp_dir,
            patch("vibectl.plugins.PluginStore._get_plugins_directory") as mock_get_dir,
        ):
            plugins_dir = Path(tmp_dir) / "plugins"
            plugins_dir.mkdir()
            mock_get_dir.return_value = plugins_dir

            store = PluginStore()

            with patch("vibectl.plugins.logger") as mock_logger:
                result = store._validate_plugin(plugin)
                assert result is False
                mock_logger.error.assert_called_with("Plugin metadata missing name")

    def test_validate_plugin_empty_version(self) -> None:
        """Test validation fails for plugin with empty version."""
        plugin = Plugin(
            metadata=PluginMetadata(
                name="test-plugin",
                version="",  # Empty version
                description="Test plugin",
                author="Test Author",
                compatible_vibectl_versions=">=0.8.0,<1.0.0",
                created_at="2024-01-15T10:00:00Z",
            ),
            prompt_mappings={"test": PromptMapping({"description": "test"})},
        )

        with (
            tempfile.TemporaryDirectory() as tmp_dir,
            patch("vibectl.plugins.PluginStore._get_plugins_directory") as mock_get_dir,
        ):
            plugins_dir = Path(tmp_dir) / "plugins"
            plugins_dir.mkdir()
            mock_get_dir.return_value = plugins_dir

            store = PluginStore()

            with patch("vibectl.plugins.logger") as mock_logger:
                result = store._validate_plugin(plugin)
                assert result is False
                mock_logger.error.assert_called_with("Plugin metadata missing version")

    def test_validate_planning_prompt_missing_examples(self) -> None:
        """Test validation fails for planning prompt missing examples."""
        plugin = Plugin(
            metadata=PluginMetadata(
                name="test-plugin",
                version="1.0.0",
                description="Test plugin",
                author="Test Author",
                compatible_vibectl_versions=">=0.8.0,<1.0.0",
                created_at="2024-01-15T10:00:00Z",
            ),
            prompt_mappings={
                "test": PromptMapping(
                    {
                        "prompt_metadata": {"is_planning_prompt": True},
                        "command": "kubectl get pods",
                        # Missing "examples" field
                    }
                )
            },
        )

        with (
            tempfile.TemporaryDirectory() as tmp_dir,
            patch("vibectl.plugins.PluginStore._get_plugins_directory") as mock_get_dir,
        ):
            plugins_dir = Path(tmp_dir) / "plugins"
            plugins_dir.mkdir()
            mock_get_dir.return_value = plugins_dir

            store = PluginStore()

            with patch("vibectl.plugins.logger") as mock_logger:
                result = store._validate_plugin(plugin)
                assert result is False
                mock_logger.error.assert_called_with(
                    "Planning prompt mapping 'test' missing examples"
                )

    def test_validate_planning_prompt_missing_command(self) -> None:
        """Test validation fails for planning prompt missing command."""
        plugin = Plugin(
            metadata=PluginMetadata(
                name="test-plugin",
                version="1.0.0",
                description="Test plugin",
                author="Test Author",
                compatible_vibectl_versions=">=0.8.0,<1.0.0",
                created_at="2024-01-15T10:00:00Z",
            ),
            prompt_mappings={
                "test": PromptMapping(
                    {
                        "prompt_metadata": {"is_planning_prompt": True},
                        "examples": "kubectl get pods",
                        # Missing "command" field
                    }
                )
            },
        )

        with (
            tempfile.TemporaryDirectory() as tmp_dir,
            patch("vibectl.plugins.PluginStore._get_plugins_directory") as mock_get_dir,
        ):
            plugins_dir = Path(tmp_dir) / "plugins"
            plugins_dir.mkdir()
            mock_get_dir.return_value = plugins_dir

            store = PluginStore()

            with patch("vibectl.plugins.logger") as mock_logger:
                result = store._validate_plugin(plugin)
                assert result is False
                mock_logger.error.assert_called_with(
                    "Planning prompt mapping 'test' missing command field"
                )

    def test_validate_summary_prompt_missing_required_fields(self) -> None:
        """Test validation fails for summary prompt missing required fields."""
        plugin = Plugin(
            metadata=PluginMetadata(
                name="test-plugin",
                version="1.0.0",
                description="Test plugin",
                author="Test Author",
                compatible_vibectl_versions=">=0.8.0,<1.0.0",
                created_at="2024-01-15T10:00:00Z",
            ),
            prompt_mappings={
                "test": PromptMapping(
                    {
                        "prompt_metadata": {"is_summary_prompt": True},
                        # Missing both "focus_points" and "example_format"
                    }
                )
            },
        )

        with (
            tempfile.TemporaryDirectory() as tmp_dir,
            patch("vibectl.plugins.PluginStore._get_plugins_directory") as mock_get_dir,
        ):
            plugins_dir = Path(tmp_dir) / "plugins"
            plugins_dir.mkdir()
            mock_get_dir.return_value = plugins_dir

            store = PluginStore()

            with patch("vibectl.plugins.logger") as mock_logger:
                result = store._validate_plugin(plugin)
                assert result is False
                mock_logger.error.assert_called_with(
                    "Summary prompt mapping 'test' missing focus_points or "
                    "example_format"
                )


class TestPromptResolverEdgeCases:
    """Test edge cases in PromptResolver."""

    def test_prompt_resolver_empty_precedence_list(self) -> None:
        """Test PromptResolver with empty precedence list."""
        with (
            tempfile.TemporaryDirectory() as tmp_dir,
            patch("vibectl.plugins.PluginStore._get_plugins_directory") as mock_get_dir,
        ):
            plugins_dir = Path(tmp_dir) / "plugins"
            plugins_dir.mkdir()
            mock_get_dir.return_value = plugins_dir

            store = PluginStore()
            config = Config()
            config.set("plugins.precedence", [])  # Empty list

            resolver = PromptResolver(store, config)

            # Should return None when no plugins are installed
            result = resolver.get_prompt_mapping("nonexistent_prompt")
            assert result is None

    def test_prompt_resolver_no_precedence_config(self) -> None:
        """Test PromptResolver when no precedence is configured."""
        with (
            tempfile.TemporaryDirectory() as tmp_dir,
            patch("vibectl.plugins.PluginStore._get_plugins_directory") as mock_get_dir,
        ):
            plugins_dir = Path(tmp_dir) / "plugins"
            plugins_dir.mkdir()
            mock_get_dir.return_value = plugins_dir

            store = PluginStore()
            config = Config()
            # Don't set any precedence config

            resolver = PromptResolver(store, config)

            with patch("vibectl.plugins.logger") as mock_logger:
                result = resolver.get_prompt_mapping("nonexistent_prompt")
                assert result is None

                # Should log debug message about no precedence configured
                assert any(
                    "No plugin precedence configured" in str(call)
                    for call in mock_logger.debug.call_args_list
                )

    def test_prompt_resolver_with_plugin_not_in_precedence(self) -> None:
        """Test PromptResolver finding plugin not in precedence list."""
        plugin_data = {
            "plugin_metadata": {
                "name": "unlisted-plugin",
                "version": "1.0.0",
                "description": "Plugin not in precedence",
                "author": "Test Author",
                "compatible_vibectl_versions": ">=0.8.0,<1.0.0",
                "created_at": "2024-01-15T10:00:00Z",
            },
            "prompt_mappings": {
                "test_prompt": {
                    "description": "Test prompt",
                    "focus_points": ["Focus point"],
                    "example_format": ["Example"],
                }
            },
        }

        with (
            tempfile.TemporaryDirectory() as tmp_dir,
            patch("vibectl.plugins.PluginStore._get_plugins_directory") as mock_get_dir,
        ):
            plugins_dir = Path(tmp_dir) / "plugins"
            plugins_dir.mkdir()
            mock_get_dir.return_value = plugins_dir

            # Create plugin file
            plugin_file = plugins_dir / "unlisted-plugin-1.0.0.json"
            with open(plugin_file, "w") as f:
                json.dump(plugin_data, f)

            store = PluginStore()
            config = Config()
            config.set("plugins.precedence", ["some-other-plugin"])  # Different plugin

            resolver = PromptResolver(store, config)

            with patch("vibectl.plugins.logger") as mock_logger:
                result = resolver.get_prompt_mapping("test_prompt")
                assert result is not None
                assert result.get("description") == "Test prompt"

                # Should log debug message about using plugin not in precedence
                debug_calls = [str(call) for call in mock_logger.debug.call_args_list]
                assert any("not in precedence list" in call for call in debug_calls)

    def test_prompt_resolver_filesystem_order_fallback(self) -> None:
        """Test PromptResolver falling back to filesystem order."""
        plugin_data = {
            "plugin_metadata": {
                "name": "filesystem-plugin",
                "version": "1.0.0",
                "description": "Plugin for filesystem order test",
                "author": "Test Author",
                "compatible_vibectl_versions": ">=0.8.0,<1.0.0",
                "created_at": "2024-01-15T10:00:00Z",
            },
            "prompt_mappings": {
                "filesystem_prompt": {
                    "description": "Filesystem order prompt",
                    "focus_points": ["Focus"],
                    "example_format": ["Example"],
                }
            },
        }

        with (
            tempfile.TemporaryDirectory() as tmp_dir,
            patch("vibectl.plugins.PluginStore._get_plugins_directory") as mock_get_dir,
        ):
            plugins_dir = Path(tmp_dir) / "plugins"
            plugins_dir.mkdir()
            mock_get_dir.return_value = plugins_dir

            # Create plugin file
            plugin_file = plugins_dir / "filesystem-plugin-1.0.0.json"
            with open(plugin_file, "w") as f:
                json.dump(plugin_data, f)

            store = PluginStore()
            config = Config()
            # No precedence configured at all

            resolver = PromptResolver(store, config)

            with patch("vibectl.plugins.logger") as mock_logger:
                result = resolver.get_prompt_mapping("filesystem_prompt")
                assert result is not None
                assert result.get("description") == "Filesystem order prompt"

                # Should log about using filesystem order
                debug_calls = [str(call) for call in mock_logger.debug.call_args_list]
                assert any("filesystem order" in call for call in debug_calls)


class TestPluginVersionValidation:
    """Test plugin version compatibility validation edge cases."""

    def test_plugin_without_version_requirement_validation(self) -> None:
        """Test that plugins without version requirements pass validation."""
        plugin = Plugin(
            metadata=PluginMetadata(
                name="no-version-plugin",
                version="1.0.0",
                description="Plugin without version requirement",
                author="Test Author",
                compatible_vibectl_versions="",  # Empty version requirement
                created_at="2024-01-15T10:00:00Z",
            ),
            prompt_mappings={"test": PromptMapping({"description": "test"})},
        )

        with (
            tempfile.TemporaryDirectory() as tmp_dir,
            patch("vibectl.plugins.PluginStore._get_plugins_directory") as mock_get_dir,
        ):
            plugins_dir = Path(tmp_dir) / "plugins"
            plugins_dir.mkdir()
            mock_get_dir.return_value = plugins_dir

            store = PluginStore()

            # Should pass validation (empty version requirement is allowed)
            result = store._validate_plugin(plugin)
            assert result is True

    @patch("vibectl.plugins.check_plugin_compatibility")
    def test_plugin_version_compatibility_failure(self, mock_check: Mock) -> None:
        """Test plugin validation when version compatibility check fails."""
        mock_check.return_value = (False, "Version mismatch error")

        plugin = Plugin(
            metadata=PluginMetadata(
                name="incompatible-plugin",
                version="1.0.0",
                description="Incompatible plugin",
                author="Test Author",
                compatible_vibectl_versions=">=2.0.0,<3.0.0",  # Future version
                created_at="2024-01-15T10:00:00Z",
            ),
            prompt_mappings={"test": PromptMapping({"description": "test"})},
        )

        with (
            tempfile.TemporaryDirectory() as tmp_dir,
            patch("vibectl.plugins.PluginStore._get_plugins_directory") as mock_get_dir,
        ):
            plugins_dir = Path(tmp_dir) / "plugins"
            plugins_dir.mkdir()
            mock_get_dir.return_value = plugins_dir

            store = PluginStore()

            with patch("vibectl.plugins.logger") as mock_logger:
                result = store._validate_plugin(plugin)
                assert result is False
                mock_logger.error.assert_called_with(
                    "Plugin version compatibility check failed: Version mismatch error"
                )


if __name__ == "__main__":
    pytest.main([__file__])
