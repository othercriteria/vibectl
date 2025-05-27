"""
Tests for plugin management functionality.

This module tests the plugin installation, listing, uninstallation, and precedence
management commands, with a focus on providing a foundation for version compatibility
testing.
"""

import json
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest

from vibectl.plugins import Plugin, PluginMetadata, PluginStore, PromptMapping
from vibectl.subcommands.plugin_cmd import (
    run_plugin_install_command,
    run_plugin_list_command,
    run_plugin_precedence_add_command,
    run_plugin_precedence_list_command,
    run_plugin_precedence_remove_command,
    run_plugin_precedence_set_command,
    run_plugin_uninstall_command,
    run_plugin_update_command,
)
from vibectl.types import Error, Success


@pytest.fixture
def test_plugin_data() -> dict[str, Any]:
    """Standard plugin data for testing."""
    return {
        "plugin_metadata": {
            "name": "test-plugin",
            "version": "1.0.0",
            "description": "A test plugin for unit testing",
            "author": "Test Author",
            "compatible_vibectl_versions": ">=0.8.0,<1.0.0",
            "created_at": "2024-01-15T10:00:00Z",
        },
        "prompt_mappings": {
            "test_prompt": {
                "description": "Test prompt description",
                "focus_points": ["Focus point 1", "Focus point 2"],
                "example_format": ["Example line 1", "Example line 2"],
            }
        },
    }


@pytest.fixture
def incompatible_plugin_data() -> dict[str, Any]:
    """Plugin data for testing version compatibility issues."""
    return {
        "plugin_metadata": {
            "name": "incompatible-plugin",
            "version": "2.0.0",
            "description": "A plugin with incompatible version requirements",
            "author": "Test Author",
            "compatible_vibectl_versions": ">=2.0.0,<3.0.0",  # Future version
            "created_at": "2024-01-15T10:00:00Z",
        },
        "prompt_mappings": {
            "test_prompt": {
                "description": "Test prompt description",
                "focus_points": ["Focus point 1"],
                "example_format": ["Example line 1"],
            }
        },
    }


@pytest.fixture
def test_plugin_file(tmp_path: Path, test_plugin_data: dict[str, Any]) -> str:
    """Create a temporary plugin file for testing."""
    plugin_file = tmp_path / "test-plugin.json"
    with open(plugin_file, "w") as f:
        json.dump(test_plugin_data, f, indent=2)
    return str(plugin_file)


@pytest.fixture
def incompatible_plugin_file(
    tmp_path: Path,
    incompatible_plugin_data: dict[str, Any],
) -> str:
    """Create a temporary incompatible plugin file for testing."""
    plugin_file = tmp_path / "incompatible-plugin.json"
    with open(plugin_file, "w") as f:
        json.dump(incompatible_plugin_data, f, indent=2)
    return str(plugin_file)


@pytest.fixture
def mock_plugin_store(tmp_path: Path) -> Generator[PluginStore, None, None]:
    """Create a PluginStore with a temporary plugins directory."""
    with patch("vibectl.plugins.PluginStore._get_plugins_directory") as mock_get_dir:
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        mock_get_dir.return_value = plugins_dir
        store = PluginStore()
        yield store


class TestPluginInstallation:
    """Tests for plugin installation functionality."""

    async def test_install_valid_plugin(
        self, mock_plugin_store: PluginStore, test_plugin_file: str
    ) -> None:
        """Test installing a valid plugin."""
        result = await run_plugin_install_command(test_plugin_file, force=False)

        assert isinstance(result, Success)
        assert "Installed plugin 'test-plugin' version 1.0.0" in result.message
        assert "Customizes prompts:" in result.message
        assert "• test_prompt" in result.message

        # Verify plugin was actually stored
        plugin = mock_plugin_store.get_plugin("test-plugin")
        assert plugin is not None
        assert plugin.metadata.name == "test-plugin"
        assert plugin.metadata.version == "1.0.0"

    async def test_install_nonexistent_file(
        self, mock_plugin_store: PluginStore
    ) -> None:
        """Test installing a nonexistent plugin file."""
        result = await run_plugin_install_command(
            "/nonexistent/plugin.json", force=False
        )

        assert isinstance(result, Error)
        assert "Plugin file not found" in result.error

    async def test_install_duplicate_plugin_without_force(
        self, mock_plugin_store: PluginStore, test_plugin_file: str
    ) -> None:
        """Test installing a plugin that already exists without force flag."""
        # Install once
        result1 = await run_plugin_install_command(test_plugin_file, force=False)
        assert isinstance(result1, Success)

        # Try to install again without force
        result2 = await run_plugin_install_command(test_plugin_file, force=False)
        assert isinstance(result2, Error)
        assert "already exists" in result2.error
        assert "Use --force to overwrite" in result2.error

    async def test_install_duplicate_plugin_with_force(
        self, mock_plugin_store: PluginStore, test_plugin_file: str
    ) -> None:
        """Test installing a plugin that already exists with force flag."""
        # Install once
        result1 = await run_plugin_install_command(test_plugin_file, force=False)
        assert isinstance(result1, Success)

        # Install again with force
        result2 = await run_plugin_install_command(test_plugin_file, force=True)
        assert isinstance(result2, Success)
        assert "Installed plugin 'test-plugin' version 1.0.0" in result2.message

    async def test_install_invalid_json(
        self, mock_plugin_store: PluginStore, tmp_path: Path
    ) -> None:
        """Test installing a plugin with invalid JSON."""
        invalid_file = tmp_path / "invalid.json"
        with open(invalid_file, "w") as f:
            f.write("{ invalid json }")

        result = await run_plugin_install_command(str(invalid_file), force=False)
        assert isinstance(result, Error)
        assert "Failed to install plugin" in result.error

    async def test_install_plugin_missing_required_fields(
        self, mock_plugin_store: PluginStore, tmp_path: Path
    ) -> None:
        """Test installing a plugin with missing required fields."""
        incomplete_data = {
            "plugin_metadata": {"name": "test"}
        }  # Missing required fields
        incomplete_file = tmp_path / "incomplete.json"
        with open(incomplete_file, "w") as f:
            json.dump(incomplete_data, f)

        result = await run_plugin_install_command(str(incomplete_file), force=False)
        assert isinstance(result, Error)
        assert "Failed to install plugin" in result.error


class TestPluginListing:
    """Tests for plugin listing functionality."""

    async def test_list_no_plugins(self, mock_plugin_store: PluginStore) -> None:
        """Test listing when no plugins are installed."""
        result = await run_plugin_list_command()

        assert isinstance(result, Success)
        assert result.message == "No plugins installed."

    async def test_list_installed_plugins(
        self, mock_plugin_store: PluginStore, test_plugin_file: str
    ) -> None:
        """Test listing installed plugins."""
        # Install a plugin first
        await run_plugin_install_command(test_plugin_file, force=False)

        # Mock console output to capture table
        with patch("vibectl.subcommands.plugin_cmd.console_manager") as mock_console:
            result = await run_plugin_list_command()

            assert isinstance(result, Success)
            # Table is printed directly, so result.message should be empty
            assert result.message == ""
            # Verify console.print was called with a table
            mock_console.console.print.assert_called_once()


class TestPluginUninstallation:
    """Tests for plugin uninstallation functionality."""

    async def test_uninstall_existing_plugin(
        self, mock_plugin_store: PluginStore, test_plugin_file: str
    ) -> None:
        """Test uninstalling an existing plugin."""
        # Install plugin first
        await run_plugin_install_command(test_plugin_file, force=False)

        # Verify it's installed
        plugin = mock_plugin_store.get_plugin("test-plugin")
        assert plugin is not None

        # Uninstall it
        result = await run_plugin_uninstall_command("test-plugin")
        assert isinstance(result, Success)
        assert "Uninstalled plugin 'test-plugin'" in result.message

        # Verify it's removed
        plugin = mock_plugin_store.get_plugin("test-plugin")
        assert plugin is None

    async def test_uninstall_nonexistent_plugin(
        self, mock_plugin_store: PluginStore
    ) -> None:
        """Test uninstalling a plugin that doesn't exist."""
        result = await run_plugin_uninstall_command("nonexistent-plugin")

        assert isinstance(result, Error)
        assert "Plugin 'nonexistent-plugin' not found" in result.error


class TestPluginUpdating:
    """Tests for plugin update functionality."""

    async def test_update_existing_plugin(
        self, mock_plugin_store: PluginStore, test_plugin_file: str, tmp_path: Path
    ) -> None:
        """Test updating an existing plugin."""
        # Install original plugin
        await run_plugin_install_command(test_plugin_file, force=False)

        # Create updated plugin with new version
        updated_data = {
            "plugin_metadata": {
                "name": "test-plugin",
                "version": "1.1.0",  # Updated version
                "description": "Updated test plugin",
                "author": "Test Author",
                "compatible_vibectl_versions": ">=0.8.0,<1.0.0",
                "created_at": "2024-01-16T10:00:00Z",
            },
            "prompt_mappings": {
                "test_prompt": {
                    "description": "Updated test prompt description",
                    "focus_points": ["Updated focus point"],
                    "example_format": ["Updated example"],
                }
            },
        }
        updated_file = tmp_path / "updated-plugin.json"
        with open(updated_file, "w") as f:
            json.dump(updated_data, f, indent=2)

        # Update the plugin
        result = await run_plugin_update_command("test-plugin", str(updated_file))

        assert isinstance(result, Success)
        assert (
            "Updated plugin 'test-plugin' from version 1.0.0 to 1.1.0" in result.message
        )

        # Verify the plugin was updated
        plugin = mock_plugin_store.get_plugin("test-plugin")
        assert plugin is not None
        assert plugin.metadata.version == "1.1.0"
        assert plugin.metadata.description == "Updated test plugin"

    async def test_update_nonexistent_plugin(
        self, mock_plugin_store: PluginStore, test_plugin_file: str
    ) -> None:
        """Test updating a plugin that doesn't exist."""
        result = await run_plugin_update_command("nonexistent-plugin", test_plugin_file)

        assert isinstance(result, Error)
        assert "Plugin 'nonexistent-plugin' not found" in result.error
        assert "Use 'install' instead" in result.error

    async def test_update_plugin_id_mismatch(
        self, mock_plugin_store: PluginStore, test_plugin_file: str, tmp_path: Path
    ) -> None:
        """Test updating with a plugin file that has a different name."""
        # Install original plugin
        await run_plugin_install_command(test_plugin_file, force=False)

        # Create plugin with different name
        different_data = {
            "plugin_metadata": {
                "name": "different-plugin",  # Different name
                "version": "1.1.0",
                "description": "Different plugin",
                "author": "Test Author",
                "compatible_vibectl_versions": ">=0.8.0,<1.0.0",
                "created_at": "2024-01-16T10:00:00Z",
            },
            "prompt_mappings": {
                "test_prompt": {
                    "description": "Test prompt",
                    "focus_points": ["Focus point"],
                    "example_format": ["Example"],
                }
            },
        }
        different_file = tmp_path / "different-plugin.json"
        with open(different_file, "w") as f:
            json.dump(different_data, f, indent=2)

        # Try to update with mismatched ID
        result = await run_plugin_update_command("test-plugin", str(different_file))

        assert isinstance(result, Error)
        assert "Plugin ID mismatch" in result.error
        assert "expected 'test-plugin', got 'different-plugin'" in result.error


class TestPluginPrecedence:
    """Tests for plugin precedence management."""

    async def test_precedence_list_empty(self) -> None:
        """Test listing precedence when none is configured."""
        with patch("vibectl.subcommands.plugin_cmd.Config") as mock_config:
            mock_config.return_value.get.return_value = []

            result = await run_plugin_precedence_list_command()

            assert isinstance(result, Success)
            assert "No plugin precedence configured" in result.message

    async def test_precedence_list_configured(self) -> None:
        """Test listing configured precedence."""
        with patch("vibectl.subcommands.plugin_cmd.Config") as mock_config:
            mock_config.return_value.get.return_value = ["plugin-a", "plugin-b"]

            result = await run_plugin_precedence_list_command()

            assert isinstance(result, Success)
            assert "Plugin precedence order" in result.message
            assert "1. plugin-a" in result.message
            assert "2. plugin-b" in result.message

    async def test_precedence_set_valid_plugins(
        self, mock_plugin_store: PluginStore, test_plugin_file: str
    ) -> None:
        """Test setting precedence with valid plugins."""
        # Install a plugin first
        await run_plugin_install_command(test_plugin_file, force=False)

        with (
            patch("vibectl.subcommands.plugin_cmd.Config") as mock_config,
            patch("vibectl.subcommands.plugin_cmd.PluginStore") as mock_store_class,
        ):
            mock_config_instance = Mock()
            mock_config.return_value = mock_config_instance
            mock_store_class.return_value = mock_plugin_store

            result = await run_plugin_precedence_set_command(["test-plugin"])

            assert isinstance(result, Success)
            assert "Plugin precedence updated" in result.message
            assert "1. test-plugin" in result.message
            mock_config_instance.set.assert_called_once_with(
                "plugin_precedence", ["test-plugin"]
            )

    async def test_precedence_set_unknown_plugins(
        self, mock_plugin_store: PluginStore
    ) -> None:
        """Test setting precedence with unknown plugins."""
        with (
            patch("vibectl.subcommands.plugin_cmd.Config") as _mock_config,
            patch("vibectl.subcommands.plugin_cmd.PluginStore") as mock_store_class,
        ):
            mock_store_class.return_value = mock_plugin_store

            result = await run_plugin_precedence_set_command(["unknown-plugin"])

            assert isinstance(result, Error)
            assert "Unknown plugins in precedence list" in result.error
            assert "unknown-plugin" in result.error

    async def test_precedence_add_plugin(
        self, mock_plugin_store: PluginStore, test_plugin_file: str
    ) -> None:
        """Test adding a plugin to precedence list."""
        # Install a plugin first
        await run_plugin_install_command(test_plugin_file, force=False)

        with (
            patch("vibectl.subcommands.plugin_cmd.Config") as mock_config,
            patch("vibectl.subcommands.plugin_cmd.PluginStore") as mock_store_class,
        ):
            mock_config_instance = Mock()
            mock_config_instance.get.return_value = []
            mock_config.return_value = mock_config_instance
            mock_store_class.return_value = mock_plugin_store

            result = await run_plugin_precedence_add_command("test-plugin")

            assert isinstance(result, Success)
            assert "Added 'test-plugin' to precedence list" in result.message
            assert "1. test-plugin ← new" in result.message
            mock_config_instance.set.assert_called_once_with(
                "plugin_precedence", ["test-plugin"]
            )

    async def test_precedence_add_plugin_with_position(
        self, mock_plugin_store: PluginStore, test_plugin_file: str
    ) -> None:
        """Test adding a plugin to precedence list at specific position."""
        # Install a plugin first
        await run_plugin_install_command(test_plugin_file, force=False)

        with (
            patch("vibectl.subcommands.plugin_cmd.Config") as mock_config,
            patch("vibectl.subcommands.plugin_cmd.PluginStore") as mock_store_class,
        ):
            mock_config_instance = Mock()
            mock_config_instance.get.return_value = ["existing-plugin"]
            mock_config.return_value = mock_config_instance
            mock_store_class.return_value = mock_plugin_store

            result = await run_plugin_precedence_add_command("test-plugin", position=1)

            assert isinstance(result, Success)
            assert "Added 'test-plugin' to precedence list" in result.message
            mock_config_instance.set.assert_called_once_with(
                "plugin_precedence", ["test-plugin", "existing-plugin"]
            )

    async def test_precedence_remove_plugin(self) -> None:
        """Test removing a plugin from precedence list."""
        with patch("vibectl.subcommands.plugin_cmd.Config") as mock_config:
            mock_config_instance = Mock()
            mock_config_instance.get.return_value = ["plugin-a", "plugin-b"]
            mock_config.return_value = mock_config_instance

            result = await run_plugin_precedence_remove_command("plugin-a")

            assert isinstance(result, Success)
            assert "Removed 'plugin-a' from precedence list" in result.message
            assert "1. plugin-b" in result.message
            mock_config_instance.set.assert_called_once_with(
                "plugin_precedence", ["plugin-b"]
            )

    async def test_precedence_remove_plugin_not_in_list(self) -> None:
        """Test removing a plugin that's not in the precedence list."""
        with patch("vibectl.subcommands.plugin_cmd.Config") as mock_config:
            mock_config_instance = Mock()
            mock_config_instance.get.return_value = ["plugin-a"]
            mock_config.return_value = mock_config_instance

            result = await run_plugin_precedence_remove_command("plugin-b")

            assert isinstance(result, Error)
            assert "Plugin 'plugin-b' not in precedence list" in result.error


class TestVersionCompatibilityFoundation:
    """Tests that will guide the implementation of version compatibility checks."""

    async def test_install_future_version_requirement(
        self, mock_plugin_store: PluginStore, incompatible_plugin_file: str
    ) -> None:
        """Test installing a plugin with future version requirements.

        This test should now fail since version compatibility is implemented.
        """
        # This should now fail due to version compatibility checking
        result = await run_plugin_install_command(incompatible_plugin_file, force=False)

        # Now that version compatibility is implemented, this should fail
        assert isinstance(result, Error)
        assert (
            "version compatibility" in result.error.lower()
            or "requires version" in result.error.lower()
            or "failed to install plugin" in result.error.lower()
        )

    def test_plugin_metadata_includes_version_info(
        self, test_plugin_data: dict[str, Any]
    ) -> None:
        """Test that plugin metadata includes version compatibility information."""
        plugin = Plugin.from_dict(test_plugin_data)

        assert hasattr(plugin.metadata, "compatible_vibectl_versions")
        assert plugin.metadata.compatible_vibectl_versions == ">=0.8.0,<1.0.0"

    def test_version_compatibility_field_validation(self, tmp_path: Path) -> None:
        """Test plugin validation includes version compatibility field."""
        # Plugin without version compatibility field
        invalid_data = {
            "plugin_metadata": {
                "name": "test-plugin",
                "version": "1.0.0",
                "description": "Test plugin",
                "author": "Test Author",
                # Missing compatible_vibectl_versions
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

        with pytest.raises(TypeError):
            # This should fail due to missing required field
            Plugin.from_dict(invalid_data)

    async def test_install_compatible_version_requirement(
        self, mock_plugin_store: PluginStore, test_plugin_file: str
    ) -> None:
        """Test installing a plugin with compatible version requirements."""
        # The test plugin has ">=0.8.0,<1.0.0" which should be compatible with 0.8.7
        result = await run_plugin_install_command(test_plugin_file, force=False)

        assert isinstance(result, Success)
        assert "Installed plugin 'test-plugin' version 1.0.0" in result.message

    async def test_install_old_version_requirement(
        self, mock_plugin_store: PluginStore, tmp_path: Path
    ) -> None:
        """Test installing a plugin that requires an older vibectl version."""
        old_version_data = {
            "plugin_metadata": {
                "name": "old-plugin",
                "version": "1.0.0",
                "description": "A plugin requiring old vibectl version",
                "author": "Test Author",
                "compatible_vibectl_versions": "<0.8.0",  # Too old
                "created_at": "2024-01-15T10:00:00Z",
            },
            "prompt_mappings": {
                "test_prompt": {
                    "description": "Test prompt description",
                    "focus_points": ["Focus point 1"],
                    "example_format": ["Example line 1"],
                }
            },
        }
        old_plugin_file = tmp_path / "old-plugin.json"
        with open(old_plugin_file, "w") as f:
            json.dump(old_version_data, f, indent=2)

        result = await run_plugin_install_command(str(old_plugin_file), force=False)

        assert isinstance(result, Error)
        assert (
            "version compatibility" in result.error.lower()
            or "requires version" in result.error.lower()
            or "failed to install plugin" in result.error.lower()
        )

    async def test_install_invalid_version_format(
        self, mock_plugin_store: PluginStore, tmp_path: Path
    ) -> None:
        """Test installing a plugin with invalid version requirement format."""
        invalid_version_data = {
            "plugin_metadata": {
                "name": "invalid-version-plugin",
                "version": "1.0.0",
                "description": "A plugin with invalid version format",
                "author": "Test Author",
                "compatible_vibectl_versions": "~1.0.0",  # Invalid format
                "created_at": "2024-01-15T10:00:00Z",
            },
            "prompt_mappings": {
                "test_prompt": {
                    "description": "Test prompt description",
                    "focus_points": ["Focus point 1"],
                    "example_format": ["Example line 1"],
                }
            },
        }
        invalid_file = tmp_path / "invalid-version-plugin.json"
        with open(invalid_file, "w") as f:
            json.dump(invalid_version_data, f, indent=2)

        result = await run_plugin_install_command(str(invalid_file), force=False)

        assert isinstance(result, Error)
        assert (
            "version compatibility" in result.error.lower()
            or "invalid version requirement" in result.error.lower()
            or "failed to install plugin" in result.error.lower()
        )

    def test_version_compatibility_validation_in_plugin_store(
        self, mock_plugin_store: PluginStore
    ) -> None:
        """Test that PluginStore validation includes version compatibility checking."""
        # Create a plugin with incompatible version requirements
        incompatible_plugin = Plugin(
            metadata=PluginMetadata(
                name="test-plugin",
                version="1.0.0",
                description="Test plugin",
                author="Test Author",
                compatible_vibectl_versions=">=2.0.0,<3.0.0",  # Future version
                created_at="2024-01-15T10:00:00Z",
            ),
            prompt_mappings={
                "test_prompt": PromptMapping(
                    description="Test prompt",
                    focus_points=["Focus point"],
                    example_format=["Example"],
                )
            },
        )

        # This should fail validation due to version incompatibility
        assert mock_plugin_store._validate_plugin(incompatible_plugin) is False

        # Create a plugin with compatible version requirements
        compatible_plugin = Plugin(
            metadata=PluginMetadata(
                name="test-plugin",
                version="1.0.0",
                description="Test plugin",
                author="Test Author",
                compatible_vibectl_versions=">=0.8.0,<1.0.0",  # Compatible
                created_at="2024-01-15T10:00:00Z",
            ),
            prompt_mappings={
                "test_prompt": PromptMapping(
                    description="Test prompt",
                    focus_points=["Focus point"],
                    example_format=["Example"],
                )
            },
        )

        # This should pass validation due to version compatibility
        assert mock_plugin_store._validate_plugin(compatible_plugin) is True


class TestPluginValidation:
    """Tests for plugin validation logic."""

    def test_validate_plugin_structure(self, mock_plugin_store: PluginStore) -> None:
        """Test plugin validation with complete valid structure."""
        valid_plugin = Plugin(
            metadata=PluginMetadata(
                name="test-plugin",
                version="1.0.0",
                description="Test plugin",
                author="Test Author",
                compatible_vibectl_versions=">=0.8.0,<1.0.0",
                created_at="2024-01-15T10:00:00Z",
            ),
            prompt_mappings={
                "test_prompt": PromptMapping(
                    description="Test prompt",
                    focus_points=["Focus point"],
                    example_format=["Example"],
                )
            },
        )

        assert mock_plugin_store._validate_plugin(valid_plugin) is True

    def test_validate_plugin_missing_name(self, mock_plugin_store: PluginStore) -> None:
        """Test plugin validation fails when name is missing."""
        invalid_plugin = Plugin(
            metadata=PluginMetadata(
                name="",  # Empty name
                version="1.0.0",
                description="Test plugin",
                author="Test Author",
                compatible_vibectl_versions=">=0.8.0,<1.0.0",
                created_at="2024-01-15T10:00:00Z",
            ),
            prompt_mappings={
                "test_prompt": PromptMapping(
                    description="Test prompt",
                    focus_points=["Focus point"],
                    example_format=["Example"],
                )
            },
        )

        assert mock_plugin_store._validate_plugin(invalid_plugin) is False

    def test_validate_plugin_missing_prompt_mappings(
        self, mock_plugin_store: PluginStore
    ) -> None:
        """Test plugin validation fails when prompt mappings are empty."""
        invalid_plugin = Plugin(
            metadata=PluginMetadata(
                name="test-plugin",
                version="1.0.0",
                description="Test plugin",
                author="Test Author",
                compatible_vibectl_versions=">=0.8.0,<1.0.0",
                created_at="2024-01-15T10:00:00Z",
            ),
            prompt_mappings={},  # Empty mappings
        )

        assert mock_plugin_store._validate_plugin(invalid_plugin) is False
