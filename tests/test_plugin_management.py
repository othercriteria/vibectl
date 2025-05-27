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

from vibectl.config import Config
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
from vibectl.types import (
    Error,
    Fragment,
    PromptFragments,
    Success,
    SystemFragments,
    UserFragments,
)


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


@pytest.fixture
def temp_plugin_store(
    tmp_path: Path,
) -> Generator[tuple[PluginStore, Mock, Path], None, None]:
    """Create a temporary plugin store with config for testing precedence automation."""
    with (
        patch("vibectl.plugins.PluginStore._get_plugins_directory") as mock_get_dir,
        patch("vibectl.subcommands.plugin_cmd.Config") as mock_config_class,
        patch("vibectl.subcommands.plugin_cmd.PluginStore") as mock_store_class,
    ):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        mock_get_dir.return_value = plugins_dir

        # Create real store instance
        store = PluginStore()

        # Mock config instance with shared state
        config_data: dict[str, Any] = {}
        config_instance = Mock()

        def mock_get(key: str, default: Any = None) -> Any:
            return config_data.get(key, default)

        def mock_set(key: str, value: Any) -> None:
            config_data[key] = value

        config_instance.get.side_effect = mock_get
        config_instance.set.side_effect = mock_set
        mock_config_class.return_value = config_instance

        # Make the patched PluginStore return our real store
        mock_store_class.return_value = store

        yield store, config_instance, tmp_path


def create_test_plugin(tmp_path: Path, name: str, version: str) -> str:
    """Helper function to create a test plugin file."""
    plugin_data = {
        "plugin_metadata": {
            "name": name,
            "version": version,
            "description": f"A test plugin for {name}",
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

    plugin_file = tmp_path / f"{name}.json"
    with open(plugin_file, "w") as f:
        json.dump(plugin_data, f, indent=2)
    return str(plugin_file)


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


class TestPluginPrecedenceAutomation:
    """Test automatic precedence management during install and uninstall operations."""

    async def test_install_with_precedence_first(
        self, temp_plugin_store: tuple[PluginStore, Mock, Path]
    ) -> None:
        """Test installing a plugin with precedence=first."""
        store, config, temp_dir = temp_plugin_store

        # Create initial precedence list with another plugin
        store.install_plugin(create_test_plugin(temp_dir, "existing-plugin", "1.0.0"))
        await run_plugin_precedence_set_command(["existing-plugin"])

        # Install new plugin with precedence=first
        result = await run_plugin_install_command(
            create_test_plugin(temp_dir, "new-plugin", "1.0.0"), precedence="first"
        )

        assert isinstance(result, Success)
        assert "new-plugin" in result.message
        assert "highest priority" in result.message

        # Check precedence order
        precedence_result = await run_plugin_precedence_list_command()
        assert isinstance(precedence_result, Success)
        assert "1. new-plugin" in precedence_result.message
        assert "2. existing-plugin" in precedence_result.message

    async def test_install_with_precedence_last(
        self, temp_plugin_store: tuple[PluginStore, Mock, Path]
    ) -> None:
        """Test installing a plugin with precedence=last."""
        store, config, temp_dir = temp_plugin_store

        # Create initial precedence list with another plugin
        store.install_plugin(create_test_plugin(temp_dir, "existing-plugin", "1.0.0"))
        await run_plugin_precedence_set_command(["existing-plugin"])

        # Install new plugin with precedence=last
        result = await run_plugin_install_command(
            create_test_plugin(temp_dir, "new-plugin", "1.0.0"), precedence="last"
        )

        assert isinstance(result, Success)
        assert "new-plugin" in result.message
        assert "lowest priority" in result.message

        # Check precedence order
        precedence_result = await run_plugin_precedence_list_command()
        assert isinstance(precedence_result, Success)
        assert "1. existing-plugin" in precedence_result.message
        assert "2. new-plugin" in precedence_result.message

    async def test_install_without_precedence_option(
        self, temp_plugin_store: tuple[PluginStore, Mock, Path]
    ) -> None:
        """Test installing a plugin without precedence option shows info message."""
        store, config, temp_dir = temp_plugin_store

        result = await run_plugin_install_command(
            create_test_plugin(temp_dir, "test-plugin", "1.0.0")
        )

        assert isinstance(result, Success)
        assert "test-plugin" in result.message
        assert "not added to precedence list" in result.message
        assert "precedence add test-plugin" in result.message
        assert "--precedence first/last" in result.message

    async def test_install_update_existing_plugin_precedence(
        self, temp_plugin_store: tuple[PluginStore, Mock, Path]
    ) -> None:
        """Test that updating a plugin in precedence list maintains its position."""
        store, config, temp_dir = temp_plugin_store

        # Install and add to precedence
        store.install_plugin(create_test_plugin(temp_dir, "test-plugin", "1.0.0"))
        await run_plugin_precedence_set_command(["test-plugin"])

        # Install new version with precedence=first (should update position)
        result = await run_plugin_install_command(
            create_test_plugin(temp_dir, "test-plugin", "2.0.0"),
            force=True,
            precedence="first",
        )

        assert isinstance(result, Success)
        assert "test-plugin" in result.message
        assert "highest priority" in result.message

        # Check only appears once in precedence
        precedence_result = await run_plugin_precedence_list_command()
        assert isinstance(precedence_result, Success)
        precedence_lines = precedence_result.message.split("\n")
        plugin_lines = [line for line in precedence_lines if "test-plugin" in line]
        assert len(plugin_lines) == 1

    async def test_uninstall_removes_from_precedence(
        self, temp_plugin_store: tuple[PluginStore, Mock, Path]
    ) -> None:
        """Test that uninstalling a plugin removes it from precedence list."""
        store, config, temp_dir = temp_plugin_store

        # Install plugins and set precedence
        store.install_plugin(create_test_plugin(temp_dir, "plugin-a", "1.0.0"))
        store.install_plugin(create_test_plugin(temp_dir, "plugin-b", "1.0.0"))
        await run_plugin_precedence_set_command(["plugin-a", "plugin-b"])

        # Uninstall plugin-a
        result = await run_plugin_uninstall_command("plugin-a")

        assert isinstance(result, Success)
        assert "plugin-a" in result.message
        assert "Removed from precedence list" in result.message

        # Check precedence only contains plugin-b
        precedence_result = await run_plugin_precedence_list_command()
        assert isinstance(precedence_result, Success)
        assert "plugin-b" in precedence_result.message
        assert "plugin-a" not in precedence_result.message

    async def test_uninstall_not_in_precedence(
        self, temp_plugin_store: tuple[PluginStore, Mock, Path]
    ) -> None:
        """Test uninstalling plugin not in precedence doesn't mention precedence."""
        store, config, temp_dir = temp_plugin_store

        # Install plugin but don't add to precedence
        store.install_plugin(create_test_plugin(temp_dir, "test-plugin", "1.0.0"))

        # Uninstall plugin
        result = await run_plugin_uninstall_command("test-plugin")

        assert isinstance(result, Success)
        assert "test-plugin" in result.message
        assert "Removed from precedence list" not in result.message


class TestRuntimeVersionCompatibility:
    """Tests for runtime version compatibility validation."""

    @patch("vibectl.plugins.logger")
    def test_runtime_version_check_skips_incompatible_plugin(
        self, mock_logger: Mock, mock_plugin_store: PluginStore
    ) -> None:
        """Test that incompatible plugins are skipped at runtime with warning."""
        # Create an incompatible plugin (requires future version)
        incompatible_plugin = Plugin(
            metadata=PluginMetadata(
                name="future-plugin",
                version="1.0.0",
                description="Plugin requiring future vibectl version",
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

        # Mock the plugin store to return the incompatible plugin
        with patch.object(
            mock_plugin_store,
            "list_installed_plugins",
            return_value=[incompatible_plugin],
        ):
            from vibectl.plugins import PromptResolver

            resolver = PromptResolver(mock_plugin_store)
            result = resolver.get_prompt_mapping("test_prompt")

            # Should return None (no compatible plugin found)
            assert result is None

            # Should log a warning about skipping the incompatible plugin
            mock_logger.warning.assert_called_once()
            warning_call = mock_logger.warning.call_args[0][0]
            assert "Skipping plugin 'future-plugin'" in warning_call
            assert "Requires version >= 2.0.0, got 0.8.7" in warning_call
            assert "Consider updating the plugin" in warning_call

    @patch("vibectl.plugins.logger")
    def test_runtime_version_check_uses_compatible_plugin(
        self, mock_logger: Mock, mock_plugin_store: PluginStore
    ) -> None:
        """Test that compatible plugins are used at runtime."""
        # Create a compatible plugin
        compatible_plugin = Plugin(
            metadata=PluginMetadata(
                name="compatible-plugin",
                version="1.0.0",
                description="Plugin compatible with current vibectl version",
                author="Test Author",
                compatible_vibectl_versions=">=0.8.0,<1.0.0",  # Compatible
                created_at="2024-01-15T10:00:00Z",
            ),
            prompt_mappings={
                "test_prompt": PromptMapping(
                    description="Test prompt description",
                    focus_points=["Focus point 1"],
                    example_format=["Example line 1"],
                )
            },
        )

        # Mock the plugin store to return the compatible plugin
        with patch.object(
            mock_plugin_store,
            "list_installed_plugins",
            return_value=[compatible_plugin],
        ):
            from vibectl.plugins import PromptResolver

            resolver = PromptResolver(mock_plugin_store)
            result = resolver.get_prompt_mapping("test_prompt")

            # Should return the plugin mapping
            assert result is not None
            assert result.description == "Test prompt description"
            assert result.focus_points == ["Focus point 1"]
            assert result.example_format == ["Example line 1"]

            # Should not log any warnings about version compatibility
            mock_logger.warning.assert_not_called()

    @patch("vibectl.plugins.logger")
    def test_runtime_version_check_precedence_order(
        self, mock_logger: Mock, mock_plugin_store: PluginStore
    ) -> None:
        """Test that version compatibility is checked in precedence order."""
        # Create two plugins: first is incompatible, second is compatible
        incompatible_plugin = Plugin(
            metadata=PluginMetadata(
                name="incompatible-plugin",
                version="1.0.0",
                description="Incompatible plugin",
                author="Test Author",
                compatible_vibectl_versions=">=2.0.0,<3.0.0",  # Future version
                created_at="2024-01-15T10:00:00Z",
            ),
            prompt_mappings={
                "test_prompt": PromptMapping(
                    description="Incompatible prompt",
                    focus_points=["Focus point"],
                    example_format=["Example"],
                )
            },
        )

        compatible_plugin = Plugin(
            metadata=PluginMetadata(
                name="compatible-plugin",
                version="1.0.0",
                description="Compatible plugin",
                author="Test Author",
                compatible_vibectl_versions=">=0.8.0,<1.0.0",  # Compatible
                created_at="2024-01-15T10:00:00Z",
            ),
            prompt_mappings={
                "test_prompt": PromptMapping(
                    description="Compatible prompt",
                    focus_points=["Focus point"],
                    example_format=["Example"],
                )
            },
        )

        # Mock config to return precedence order
        config = Config()
        config.set("plugin_precedence", ["incompatible-plugin", "compatible-plugin"])

        # Mock plugin store methods
        def mock_get_plugin(name: str) -> Plugin | None:
            if name == "incompatible-plugin":
                return incompatible_plugin
            elif name == "compatible-plugin":
                return compatible_plugin
            return None

        with patch.object(mock_plugin_store, "get_plugin", side_effect=mock_get_plugin):
            from vibectl.plugins import PromptResolver

            resolver = PromptResolver(mock_plugin_store, config)
            result = resolver.get_prompt_mapping("test_prompt")

            # Should return the compatible plugin (second in precedence)
            assert result is not None
            assert result.description == "Compatible prompt"

            # Should log a warning about skipping the incompatible plugin
            mock_logger.warning.assert_called_once()
            warning_call = mock_logger.warning.call_args[0][0]
            assert "Skipping plugin 'incompatible-plugin'" in warning_call

    def test_runtime_version_check_with_plugin_override_decorator(
        self, mock_plugin_store: PluginStore
    ) -> None:
        """Test version compatibility works through with_plugin_override decorator."""
        # Create an incompatible plugin
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
                "patch_resource_summary": PromptMapping(
                    description="Test patch summary from plugin",
                    focus_points=["Plugin focus point"],
                    example_format=["Plugin example"],
                )
            },
        )

        # Mock the plugin store to return the incompatible plugin
        with patch.object(
            mock_plugin_store,
            "list_installed_plugins",
            return_value=[incompatible_plugin],
        ):
            # Import and test the actual patch_resource_prompt function
            from vibectl.prompts.patch import patch_resource_prompt

            # This should fall back to default prompt due to version incompatibility
            result = patch_resource_prompt()

            # Should return the default prompt fragments
            assert result is not None
            assert len(result) == 2  # (system_fragments, user_fragments)

            # Verify it's the default prompt by checking it doesn't contain
            # plugin content
            system_fragments, user_fragments = result
            system_text = " ".join(system_fragments + user_fragments)

            # Should not contain plugin-specific content
            assert "Test patch summary from plugin" not in system_text
            assert "Plugin focus point" not in system_text
            assert "Plugin example" not in system_text

            # Should contain default prompt content
            assert (
                "kubectl patch results" in system_text.lower()
                or "patch" in system_text.lower()
            )

    def test_runtime_version_check_plugin_without_version_requirement(
        self, mock_plugin_store: PluginStore
    ) -> None:
        """Test that plugins without version requirements are allowed."""
        # Create a plugin without version compatibility requirement
        plugin_without_version = Plugin(
            metadata=PluginMetadata(
                name="no-version-plugin",
                version="1.0.0",
                description="Plugin without version requirement",
                author="Test Author",
                compatible_vibectl_versions="",  # Empty version requirement
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

        # Mock the plugin store to return the plugin
        with patch.object(
            mock_plugin_store,
            "list_installed_plugins",
            return_value=[plugin_without_version],
        ):
            from vibectl.plugins import PromptResolver

            resolver = PromptResolver(mock_plugin_store)
            result = resolver.get_prompt_mapping("test_prompt")

            # Should return the plugin mapping (no version check performed)
            assert result is not None
            assert result.description == "Test prompt"


class TestDualPromptTypePlugins:
    """Tests for plugins that support both planning and summary prompts."""

    @pytest.fixture
    def dual_prompt_plugin_data(self) -> dict[str, Any]:
        """Plugin data with planning and summary prompts (like annotating-patch-v1)."""
        return {
            "plugin_metadata": {
                "name": "dual-prompt-plugin",
                "version": "1.0.0",
                "description": "Plugin with both planning and summary prompts",
                "author": "Test Author",
                "compatible_vibectl_versions": ">=0.8.0,<1.0.0",
                "created_at": "2024-01-15T10:00:00Z",
            },
            "prompt_mappings": {
                "patch_plan": {
                    "description": "Planning patch commands with custom logic",
                    "examples": [
                        [
                            "scale nginx deployment to 5 replicas",
                            {
                                "action_type": "COMMAND",
                                "commands": [
                                    "deployment",
                                    "nginx",
                                    "-p",
                                    '{"spec":{"replicas":5}}',
                                ],
                                "explanation": "User asked to scale...",
                            },
                        ],
                        [
                            "add label environment=prod to service web-service...",
                            {
                                "action_type": "COMMAND",
                                "commands": [
                                    "service",
                                    "web-service",
                                    "-p",
                                    '{"metadata":{"labels":{"environment":"prod"},'
                                    '"annotations":{"note":"korqtvcpv"}}}',
                                ],
                                "explanation": "User asked to add labels...",
                            },
                        ],
                    ],
                },
                "patch_resource_summary": {
                    "description": "Summarize patch results with custom decoding",
                    "focus_points": [
                        "decode any 'note' annotation values...",
                        "explain the decoded note in a friendly way",
                        "show standard patch result information",
                    ],
                    "example_format": [
                        "[bold]deployment.apps/nginx[/bold] [green]patched[/green]",
                        "[italic]Decoded from annotation:[/italic] ...",
                    ],
                },
            },
        }

    @pytest.fixture
    def planning_only_plugin_data(self) -> dict[str, Any]:
        """Plugin data with only planning prompts."""
        return {
            "plugin_metadata": {
                "name": "planning-only-plugin",
                "version": "1.0.0",
                "description": "Plugin with only planning prompts",
                "author": "Test Author",
                "compatible_vibectl_versions": ">=0.8.0,<1.0.0",
                "created_at": "2024-01-15T10:00:00Z",
            },
            "prompt_mappings": {
                "patch_plan": {
                    "description": "Custom planning for patch commands",
                    "examples": [
                        [
                            "scale nginx deployment to 3 replicas",
                            {
                                "action_type": "COMMAND",
                                "commands": [
                                    "deployment",
                                    "nginx",
                                    "-p",
                                    '{"spec":{"replicas":3}}',
                                ],
                                "explanation": "Custom planning logic applied.",
                            },
                        ],
                    ],
                },
            },
        }

    @pytest.fixture
    def summary_only_plugin_data(self) -> dict[str, Any]:
        """Plugin data with only summary prompts."""
        return {
            "plugin_metadata": {
                "name": "summary-only-plugin",
                "version": "1.0.0",
                "description": "Plugin with only summary prompts",
                "author": "Test Author",
                "compatible_vibectl_versions": ">=0.8.0,<1.0.0",
                "created_at": "2024-01-15T10:00:00Z",
            },
            "prompt_mappings": {
                "patch_resource_summary": {
                    "description": "Custom summary for patch results",
                    "focus_points": [
                        "resource type and name",
                        "changes applied",
                        "custom formatting",
                    ],
                    "example_format": [
                        "[bold]resource[/bold] [green]patched[/green]",
                        "Custom summary format",
                    ],
                },
            },
        }

    def test_dual_prompt_plugin_validation(
        self, mock_plugin_store: PluginStore, dual_prompt_plugin_data: dict[str, Any]
    ) -> None:
        """Test plugins with both planning and summary prompts validate correctly."""
        plugin = Plugin.from_dict(dual_prompt_plugin_data)

        # Verify the plugin structure
        assert len(plugin.prompt_mappings) == 2

        # Check planning prompt
        patch_plan = plugin.prompt_mappings["patch_plan"]
        assert patch_plan.is_planning_prompt()
        assert not patch_plan.is_summary_prompt()
        assert patch_plan.examples is not None
        assert len(patch_plan.examples) == 2
        assert patch_plan.focus_points is None
        assert patch_plan.example_format is None

        # Check summary prompt
        patch_summary = plugin.prompt_mappings["patch_resource_summary"]
        assert patch_summary.is_summary_prompt()
        assert not patch_summary.is_planning_prompt()
        assert patch_summary.focus_points is not None
        assert patch_summary.example_format is not None
        assert patch_summary.examples is None

        # Validate plugin passes validation
        assert mock_plugin_store._validate_plugin(plugin)

    def test_planning_only_plugin_validation(
        self, mock_plugin_store: PluginStore, planning_only_plugin_data: dict[str, Any]
    ) -> None:
        """Test that planning-only plugins validate correctly."""
        plugin = Plugin.from_dict(planning_only_plugin_data)

        patch_plan = plugin.prompt_mappings["patch_plan"]
        assert patch_plan.is_planning_prompt()
        assert not patch_plan.is_summary_prompt()
        assert patch_plan.examples is not None
        assert patch_plan.focus_points is None

        assert mock_plugin_store._validate_plugin(plugin)

    def test_summary_only_plugin_validation(
        self, mock_plugin_store: PluginStore, summary_only_plugin_data: dict[str, Any]
    ) -> None:
        """Test that summary-only plugins validate correctly."""
        plugin = Plugin.from_dict(summary_only_plugin_data)

        patch_summary = plugin.prompt_mappings["patch_resource_summary"]
        assert patch_summary.is_summary_prompt()
        assert not patch_summary.is_planning_prompt()
        assert patch_summary.focus_points is not None
        assert patch_summary.examples is None

        assert mock_plugin_store._validate_plugin(plugin)

    def test_invalid_prompt_mapping_validation(
        self, mock_plugin_store: PluginStore
    ) -> None:
        """Test that invalid prompt mappings fail validation."""
        # Plugin with prompt mapping that has neither examples nor focus_points
        invalid_plugin_data = {
            "plugin_metadata": {
                "name": "invalid-plugin",
                "version": "1.0.0",
                "description": "Invalid plugin",
                "author": "Test Author",
                "compatible_vibectl_versions": ">=0.8.0,<1.0.0",
                "created_at": "2024-01-15T10:00:00Z",
            },
            "prompt_mappings": {
                "invalid_prompt": {
                    "description": "Invalid prompt with no examples or focus_points",
                    # Missing both examples and focus_points/example_format
                },
            },
        }

        plugin = Plugin.from_dict(invalid_plugin_data)

        # Should fail validation
        assert not mock_plugin_store._validate_plugin(plugin)

    def test_planning_prompt_missing_examples_validation(
        self, mock_plugin_store: PluginStore
    ) -> None:
        """Test that planning prompts without examples fail validation."""
        invalid_planning_data = {
            "plugin_metadata": {
                "name": "invalid-planning",
                "version": "1.0.0",
                "description": "Invalid planning plugin",
                "author": "Test Author",
                "compatible_vibectl_versions": ">=0.8.0,<1.0.0",
                "created_at": "2024-01-15T10:00:00Z",
            },
            "prompt_mappings": {
                "patch_plan": {
                    "description": "Planning prompt without examples",
                    "examples": [],  # Empty examples
                },
            },
        }

        plugin = Plugin.from_dict(invalid_planning_data)

        # Should fail validation
        assert not mock_plugin_store._validate_plugin(plugin)

    def test_summary_prompt_missing_focus_points_validation(
        self, mock_plugin_store: PluginStore
    ) -> None:
        """Test summary prompts sans focus_points or example_format fail validation."""
        invalid_summary_data = {
            "plugin_metadata": {
                "name": "invalid-summary",
                "version": "1.0.0",
                "description": "Invalid summary plugin",
                "author": "Test Author",
                "compatible_vibectl_versions": ">=0.8.0,<1.0.0",
                "created_at": "2024-01-15T10:00:00Z",
            },
            "prompt_mappings": {
                "patch_resource_summary": {
                    "description": "Summary prompt...",
                    # Missing both focus_points and example_format
                },
            },
        }

        plugin = Plugin.from_dict(invalid_summary_data)

        # Should fail validation
        assert not mock_plugin_store._validate_plugin(plugin)

    @patch("vibectl.plugins.PluginStore")
    @patch("vibectl.plugins.PromptResolver")
    def test_plugin_override_decorator_planning_prompt(
        self,
        mock_resolver_class: Mock,
        mock_store_class: Mock,
        dual_prompt_plugin_data: dict[str, Any],
    ) -> None:
        """Test that the plugin override decorator works for planning prompts."""
        from vibectl.prompts.shared import with_plugin_override

        # Create plugin with planning prompt
        plugin = Plugin.from_dict(dual_prompt_plugin_data)
        patch_plan_mapping = plugin.prompt_mappings["patch_plan"]

        # Mock the resolver to return our planning prompt mapping
        mock_resolver = Mock()
        mock_resolver.get_prompt_mapping.return_value = patch_plan_mapping
        mock_resolver_class.return_value = mock_resolver

        # Create a mock function to decorate
        @with_plugin_override("patch_plan")
        def mock_planning_function(
            config: Config | None = None, current_memory: str | None = None
        ) -> PromptFragments:
            # This is the default behavior - should not be called
            return PromptFragments(
                (
                    SystemFragments([Fragment("default planning")]),
                    UserFragments([Fragment("default request")]),
                )
            )

        # Call the decorated function
        result = mock_planning_function()

        # Verify the result is from create_planning_prompt
        assert isinstance(result, tuple)
        assert len(result) == 2
        system_fragments, user_fragments = result
        assert isinstance(system_fragments, list)
        assert isinstance(user_fragments, list)

        # Should contain planning-specific content
        combined_text = " ".join(system_fragments + user_fragments)
        assert "kubectl patch" in combined_text
        assert "COMMAND" in combined_text
        assert "Planning patch commands with custom logic" in combined_text

    @patch("vibectl.plugins.PluginStore")
    @patch("vibectl.plugins.PromptResolver")
    def test_plugin_override_decorator_summary_prompt(
        self,
        mock_resolver_class: Mock,
        mock_store_class: Mock,
        dual_prompt_plugin_data: dict[str, Any],
    ) -> None:
        """Test that the plugin override decorator works for summary prompts."""
        from vibectl.prompts.shared import with_plugin_override

        # Create plugin with summary prompt
        plugin = Plugin.from_dict(dual_prompt_plugin_data)
        patch_summary_mapping = plugin.prompt_mappings["patch_resource_summary"]

        # Mock the resolver to return our summary prompt mapping
        mock_resolver = Mock()
        mock_resolver.get_prompt_mapping.return_value = patch_summary_mapping
        mock_resolver_class.return_value = mock_resolver

        # Create a mock function to decorate
        @with_plugin_override("patch_resource_summary")
        def mock_summary_function(
            config: Config | None = None, current_memory: str | None = None
        ) -> PromptFragments:
            # This is the default behavior - should not be called
            return PromptFragments(
                (
                    SystemFragments([Fragment("default summary")]),
                    UserFragments([Fragment("default output")]),
                )
            )

        # Call the decorated function
        result = mock_summary_function()

        # Verify the result is from create_summary_prompt
        assert isinstance(result, tuple)
        assert len(result) == 2
        system_fragments, user_fragments = result
        assert isinstance(system_fragments, list)
        assert isinstance(user_fragments, list)

        # Should contain summary-specific content
        combined_text = " ".join(system_fragments + user_fragments)
        assert "decode any 'note' annotation values" in combined_text
        assert "Summarize patch results with custom decoding" in combined_text
        assert "{output}" in combined_text

    @patch("vibectl.plugins.PluginStore")
    @patch("vibectl.plugins.PromptResolver")
    def test_plugin_override_decorator_fallback_on_error(
        self, mock_resolver_class: Mock, mock_store_class: Mock
    ) -> None:
        """Test that the plugin override decorator falls back to default on errors."""
        from vibectl.prompts.shared import with_plugin_override

        # Mock the resolver to raise an exception
        mock_resolver = Mock()
        mock_resolver.get_prompt_mapping.side_effect = Exception("Plugin error")
        mock_resolver_class.return_value = mock_resolver

        # Track if default function was called
        default_called = False

        @with_plugin_override("patch_plan")
        def mock_function_with_fallback(
            config: Config | None = None, current_memory: str | None = None
        ) -> PromptFragments:
            nonlocal default_called
            default_called = True
            return PromptFragments(
                (
                    SystemFragments([Fragment("default")]),
                    UserFragments([Fragment("fallback")]),
                )
            )

        # Call the decorated function
        result = mock_function_with_fallback()

        # Should fall back to default function
        assert default_called
        assert result == PromptFragments(
            (
                SystemFragments([Fragment("default")]),
                UserFragments([Fragment("fallback")]),
            )
        )

    async def test_install_dual_prompt_plugin_success(
        self,
        mock_plugin_store: PluginStore,
        tmp_path: Path,
        dual_prompt_plugin_data: dict[str, Any],
    ) -> None:
        """Test installing a plugin with both planning and summary prompts."""
        plugin_file = tmp_path / "dual-prompt-plugin.json"
        with open(plugin_file, "w") as f:
            json.dump(dual_prompt_plugin_data, f, indent=2)

        result = await run_plugin_install_command(str(plugin_file), force=False)

        assert isinstance(result, Success)
        assert "Installed plugin 'dual-prompt-plugin' version 1.0.0" in result.message
        assert "Customizes prompts:" in result.message
        assert "• patch_plan" in result.message
        assert "• patch_resource_summary" in result.message

        # Verify plugin was actually stored
        plugin = mock_plugin_store.get_plugin("dual-prompt-plugin")
        assert plugin is not None
        assert len(plugin.prompt_mappings) == 2
