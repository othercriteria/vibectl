"""
Plugin system for vibectl.

This module provides functionality to install, manage, and use custom prompt plugins
that allow users to override default prompts with customized versions.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vibectl.config import Config
from vibectl.logutil import logger
from vibectl.version_compat import check_plugin_compatibility


@dataclass
class PluginMetadata:
    """Metadata for a vibectl plugin."""

    name: str
    version: str
    description: str
    author: str
    compatible_vibectl_versions: str
    created_at: str


@dataclass
class PromptMapping:
    """A custom prompt mapping from a plugin."""

    description: str
    focus_points: list[str]
    example_format: list[str]


@dataclass
class Plugin:
    """A complete plugin with metadata and prompt mappings."""

    metadata: PluginMetadata
    prompt_mappings: dict[str, PromptMapping]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Plugin":
        """Create a Plugin from a dictionary (parsed from JSON)."""
        metadata = PluginMetadata(**data["plugin_metadata"])

        prompt_mappings = {}
        for key, mapping_data in data["prompt_mappings"].items():
            prompt_mappings[key] = PromptMapping(**mapping_data)

        return cls(metadata=metadata, prompt_mappings=prompt_mappings)


class PluginStore:
    """Manages plugin storage and retrieval."""

    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self.plugins_dir = self._get_plugins_directory()
        self.plugins_dir.mkdir(parents=True, exist_ok=True)

    def _get_plugins_directory(self) -> Path:
        """Get the plugins storage directory."""
        # Use ~/.config/vibectl/plugins/ as discussed
        config_dir = Path.home() / ".config" / "vibectl" / "plugins"
        return config_dir

    def install_plugin(self, plugin_file_path: str, force: bool = False) -> Plugin:
        """
        Install a plugin from a file.

        Args:
            plugin_file_path: Path to the plugin JSON file
            force: Whether to overwrite existing plugins

        Returns:
            Plugin: The installed plugin object

        Raises:
            FileNotFoundError: If the plugin file doesn't exist
            ValueError: If plugin validation fails or plugin exists and force=False
        """
        plugin_path = Path(plugin_file_path)
        if not plugin_path.exists():
            raise FileNotFoundError(f"Plugin file not found: {plugin_file_path}")

        # Load and validate plugin
        with open(plugin_path) as f:
            plugin_data = json.load(f)

        plugin = Plugin.from_dict(plugin_data)

        # Check if plugin already exists
        existing_plugin = self.get_plugin(plugin.metadata.name)
        if existing_plugin and not force:
            raise ValueError(
                f"Plugin '{plugin.metadata.name}' already exists. "
                "Use force=True to overwrite."
            )

        # Validate plugin before storing
        if not self._validate_plugin(plugin):
            raise ValueError(f"Plugin validation failed: {plugin_file_path}")

        # Copy plugin file to plugins directory
        dest_filename = f"{plugin.metadata.name}-{plugin.metadata.version}.json"
        dest_path = self.plugins_dir / dest_filename

        with open(dest_path, "w") as f:
            json.dump(plugin_data, f, indent=2)

        logger.info(
            "Plugin installed successfully: "
            f"{plugin.metadata.name} v{plugin.metadata.version}"
        )
        return plugin

    def uninstall_plugin(self, plugin_id: str) -> None:
        """
        Uninstall a plugin by ID/name.

        Args:
            plugin_id: The plugin name/ID to uninstall

        Raises:
            ValueError: If plugin is not found
        """
        # Find all files for this plugin (different versions)
        plugin_files = list(self.plugins_dir.glob(f"{plugin_id}-*.json"))

        if not plugin_files:
            raise ValueError(f"Plugin '{plugin_id}' not found")

        # Remove all versions of the plugin
        for plugin_file in plugin_files:
            plugin_file.unlink()
            logger.info(f"Removed plugin file: {plugin_file}")

        logger.info(f"Plugin uninstalled successfully: {plugin_id}")

    def get_plugin(self, plugin_id: str) -> Plugin | None:
        """
        Get a plugin by ID/name (returns latest version if multiple exist).

        Args:
            plugin_id: The plugin name/ID to get

        Returns:
            Plugin if found, None otherwise
        """
        return self.get_plugin_by_name(plugin_id)

    def list_plugins(self) -> list[Plugin]:
        """Get list of all installed plugins (alias for list_installed_plugins)."""
        return self.list_installed_plugins()

    def _validate_plugin(self, plugin: Plugin) -> bool:
        """
        Validate a plugin before installation.

        Args:
            plugin: Plugin to validate

        Returns:
            bool: True if valid, False otherwise
        """
        # Basic validation - could be extended
        if not plugin.metadata.name:
            logger.error("Plugin metadata missing name")
            return False

        if not plugin.metadata.version:
            logger.error("Plugin metadata missing version")
            return False

        if not plugin.prompt_mappings:
            logger.error("Plugin has no prompt mappings")
            return False

        # Validate each prompt mapping
        for key, mapping in plugin.prompt_mappings.items():
            if not mapping.description:
                logger.error(f"Prompt mapping '{key}' missing description")
                return False

            if not mapping.focus_points:
                logger.error(f"Prompt mapping '{key}' missing focus_points")
                return False

        # Version compatibility check
        if plugin.metadata.compatible_vibectl_versions:
            is_compatible, error_msg = check_plugin_compatibility(
                plugin.metadata.compatible_vibectl_versions
            )
            if not is_compatible:
                logger.error(f"Plugin version compatibility check failed: {error_msg}")
                return False

        return True

    def list_installed_plugins(self) -> list[Plugin]:
        """Get list of all installed plugins."""
        plugins = []

        for plugin_file in self.plugins_dir.glob("*.json"):
            try:
                with open(plugin_file) as f:
                    plugin_data = json.load(f)
                plugin = Plugin.from_dict(plugin_data)
                plugins.append(plugin)
            except Exception as e:
                logger.warning(f"Failed to load plugin {plugin_file}: {e}")

        return plugins

    def get_plugin_by_name(self, name: str) -> Plugin | None:
        """Get a plugin by name (returns latest version if multiple exist)."""
        plugins = [p for p in self.list_installed_plugins() if p.metadata.name == name]
        if not plugins:
            return None

        # Return latest version (simple string comparison for now)
        return max(plugins, key=lambda p: p.metadata.version)


class PromptResolver:
    """Resolves prompts using plugin precedence and fallbacks."""

    def __init__(self, plugin_store: PluginStore, config: Config | None = None):
        self.plugin_store = plugin_store
        self.config = config or Config()

    def _is_plugin_compatible_at_runtime(self, plugin: Plugin, prompt_key: str) -> bool:
        """
        Check if a plugin is compatible with the current vibectl version at runtime.

        Args:
            plugin: The plugin to check
            prompt_key: The prompt key being requested (for logging)

        Returns:
            bool: True if compatible or no version requirement, False if incompatible
        """
        if not plugin.metadata.compatible_vibectl_versions:
            # No version requirement specified - allow it
            return True

        is_compatible, error_msg = check_plugin_compatibility(
            plugin.metadata.compatible_vibectl_versions
        )

        if not is_compatible:
            logger.warning(
                f"Skipping plugin '{plugin.metadata.name}' for prompt "
                f"'{prompt_key}': {error_msg}. Consider updating the plugin."
            )
            return False

        return True

    def get_prompt_mapping(self, prompt_key: str) -> PromptMapping | None:
        """
        Get the prompt mapping for a given key, respecting plugin precedence.

        Args:
            prompt_key: The prompt key to look up (e.g., "patch_resource_summary")

        Returns:
            PromptMapping if found in any active plugin, None otherwise
        """
        # Get plugin precedence from config
        precedence_order = self.config.get("plugin_precedence", [])

        if precedence_order:
            # Use configured precedence order
            logger.debug(f"Using configured plugin precedence: {precedence_order}")

            # Check plugins in precedence order
            for plugin_name in precedence_order:
                plugin = self.plugin_store.get_plugin(plugin_name)
                if (
                    plugin
                    and prompt_key in plugin.prompt_mappings
                    and self._is_plugin_compatible_at_runtime(plugin, prompt_key)
                ):
                    logger.debug(
                        f"Using prompt '{prompt_key}' from plugin "
                        f"'{plugin.metadata.name}' (precedence priority)"
                    )
                    return plugin.prompt_mappings[prompt_key]

            # If not found in precedence list, check remaining plugins
            installed_plugins = self.plugin_store.list_installed_plugins()
            remaining_plugins = [
                p for p in installed_plugins if p.metadata.name not in precedence_order
            ]

            for plugin in remaining_plugins:
                if (
                    prompt_key in plugin.prompt_mappings
                    and self._is_plugin_compatible_at_runtime(plugin, prompt_key)
                ):
                    logger.debug(
                        f"Using prompt '{prompt_key}' from plugin "
                        f"'{plugin.metadata.name}' (not in precedence list)"
                    )
                    return plugin.prompt_mappings[prompt_key]
        else:
            # No precedence configured - use filesystem order (original behavior)
            logger.debug("No plugin precedence configured, using filesystem order")

            for plugin in self.plugin_store.list_installed_plugins():
                if (
                    prompt_key in plugin.prompt_mappings
                    and self._is_plugin_compatible_at_runtime(plugin, prompt_key)
                ):
                    logger.debug(
                        f"Using prompt '{prompt_key}' from plugin "
                        f"'{plugin.metadata.name}'"
                    )
                    return plugin.prompt_mappings[prompt_key]

        logger.debug(
            f"No plugin override found for prompt '{prompt_key}', using default"
        )
        return None
