"""
Plugin management subcommands for vibectl.

This module provides functionality to manage vibectl plugins including:
- Installing plugins from files
- Listing installed plugins
- Uninstalling plugins
- Updating existing plugins
- Managing plugin precedence configuration
"""

import json

import asyncclick as click
from rich.table import Table

from vibectl.config import Config
from vibectl.console import console_manager
from vibectl.logutil import logger
from vibectl.plugins import PluginStore
from vibectl.types import Error, Result, Success
from vibectl.utils import handle_exception


async def run_plugin_install_command(
    plugin_path: str, force: bool = False, precedence: str | None = None
) -> Result:
    """Install a plugin from a local file path.

    Args:
        plugin_path: Path to the plugin JSON file
        force: Whether to force install even if plugin already exists
        precedence: Where to place in precedence order ('first', 'last', or None)

    Returns:
        Result indicating success or failure
    """
    try:
        store = PluginStore()

        # Check if plugin already exists (unless force is used)
        if not force:
            try:
                # Try to read the plugin file to get its metadata
                with open(plugin_path) as f:
                    plugin_data = json.load(f)
                plugin_id = plugin_data.get("plugin_metadata", {}).get("name")
                if plugin_id and store.get_plugin(plugin_id):
                    return Error(
                        error=f"✗ Plugin '{plugin_id}' already exists. "
                        "Use --force to overwrite."
                    )
            except Exception:
                # If we can't read the plugin file, let install_plugin handle the error
                pass

        plugin = store.install_plugin(plugin_path, force=force)

        # Handle precedence configuration if requested
        config = Config()
        precedence_updated = False
        if precedence:
            current_precedence = config.get("plugins.precedence", [])

            # Remove if already in list (for updates)
            if plugin.metadata.name in current_precedence:
                current_precedence.remove(plugin.metadata.name)

            if precedence == "first":
                current_precedence.insert(0, plugin.metadata.name)
                precedence_updated = True
            elif precedence == "last":
                current_precedence.append(plugin.metadata.name)
                precedence_updated = True

            if precedence_updated:
                config.set("plugins.precedence", current_precedence)

        result_message = (
            f"✓ Installed plugin '{plugin.metadata.name}' "
            f"version {plugin.metadata.version}"
        )

        # Show what prompts this plugin customizes
        if plugin.prompt_mappings:
            result_message += "\n\nCustomizes prompts:"
            for key in plugin.prompt_mappings:
                result_message += f"\n  • {key}"

        # Inform about precedence
        if precedence_updated:
            position = (
                "highest priority" if precedence == "first" else "lowest priority"
            )
            result_message += f"\n\n✓ Added to precedence list at {position}"
        else:
            result_message += (
                "\n\nNote: Plugin not added to precedence list. "
                f"Use 'vibectl plugin precedence add {plugin.metadata.name}' "
                "to configure priority, "
                "or use --precedence first/last during installation."
            )

        return Success(message=result_message)

    except FileNotFoundError:
        return Error(error=f"✗ Plugin file not found: {plugin_path}")
    except Exception as e:
        logger.error(f"Plugin installation failed: {e}")
        return Error(error=f"✗ Failed to install plugin: {e}")


async def run_plugin_list_command() -> Result:
    """List all installed plugins.

    Returns:
        Result with formatted plugin list or error
    """
    try:
        store = PluginStore()
        plugins = store.list_plugins()

        if not plugins:
            return Success(message="No plugins installed.")

        table = Table(title="Installed Plugins")
        table.add_column("ID", style="cyan")
        table.add_column("Version", style="green")
        table.add_column("Description", style="dim")
        table.add_column("Prompts", style="yellow")

        for plugin in plugins:
            prompt_count = len(plugin.prompt_mappings) if plugin.prompt_mappings else 0
            prompt_keys = (
                ", ".join(plugin.prompt_mappings.keys())
                if plugin.prompt_mappings
                else "None"
            )
            if len(prompt_keys) > 40:
                prompt_keys = prompt_keys[:37] + "..."

            table.add_row(
                plugin.metadata.name,
                plugin.metadata.version,
                plugin.metadata.description or "No description",
                f"{prompt_count} ({prompt_keys})",
            )

        # Capture table output as string
        console_manager.console.print(table)
        return Success(message="")  # Table is printed directly

    except Exception as e:
        logger.error(f"Failed to list plugins: {e}")
        return Error(error=f"✗ Failed to list plugins: {e}")


async def run_plugin_uninstall_command(plugin_id: str) -> Result:
    """Uninstall a plugin by ID.

    Args:
        plugin_id: The plugin name/ID to uninstall

    Returns:
        Result indicating success or failure
    """
    try:
        store = PluginStore()

        # Check if plugin exists
        plugin = store.get_plugin(plugin_id)
        if not plugin:
            return Error(error=f"✗ Plugin '{plugin_id}' not found.")

        # Check if plugin is in precedence list before uninstalling
        config = Config()
        precedence = config.get("plugins.precedence", [])
        was_in_precedence = plugin_id in precedence

        # Remove from precedence list if present
        if was_in_precedence:
            precedence.remove(plugin_id)
            config.set("plugins.precedence", precedence)

        store.uninstall_plugin(plugin_id)

        result_message = f"✓ Uninstalled plugin '{plugin_id}'"
        if was_in_precedence:
            result_message += "\n✓ Removed from precedence list"

        return Success(message=result_message)

    except Exception as e:
        logger.error(f"Plugin uninstallation failed: {e}")
        return Error(error=f"✗ Failed to uninstall plugin: {e}")


async def run_plugin_update_command(plugin_id: str, plugin_path: str) -> Result:
    """Update an existing plugin with a new version.

    Args:
        plugin_id: The plugin name/ID to update
        plugin_path: Path to the new plugin file

    Returns:
        Result indicating success or failure
    """
    try:
        store = PluginStore()

        # Check if plugin exists
        existing_plugin = store.get_plugin(plugin_id)
        if not existing_plugin:
            return Error(
                error=f"✗ Plugin '{plugin_id}' not found. Use 'install' instead."
            )

        # Install with force=True to update
        new_plugin = store.install_plugin(plugin_path, force=True)

        if new_plugin.metadata.name != plugin_id:
            return Error(
                error=f"✗ Plugin ID mismatch: expected '{plugin_id}', "
                f"got '{new_plugin.metadata.name}'"
            )

        result_message = (
            f"✓ Updated plugin '{plugin_id}' from version "
            f"{existing_plugin.metadata.version} to {new_plugin.metadata.version}"
        )

        # Show what prompts this plugin customizes
        if new_plugin.prompt_mappings:
            result_message += "\n\nCustomizes prompts:"
            for key in new_plugin.prompt_mappings:
                result_message += f"\n  • {key}"

        return Success(message=result_message)

    except FileNotFoundError:
        return Error(error=f"✗ Plugin file not found: {plugin_path}")
    except Exception as e:
        logger.error(f"Plugin update failed: {e}")
        return Error(error=f"✗ Failed to update plugin: {e}")


async def run_plugin_precedence_list_command() -> Result:
    """List the current plugin precedence order.

    Returns:
        Result with current precedence configuration
    """
    try:
        config = Config()
        precedence = config.get("plugins.precedence", [])

        if not precedence:
            return Success(
                message="No plugin precedence configured. Using default order."
            )

        result_message = "Plugin precedence order (highest to lowest priority):"
        for i, plugin_name in enumerate(precedence, 1):
            result_message += f"\n  {i}. {plugin_name}"

        return Success(message=result_message)

    except Exception as e:
        logger.error(f"Failed to get plugin precedence: {e}")
        return Error(error=f"✗ Failed to get plugin precedence: {e}")


async def run_plugin_precedence_set_command(precedence_list: list[str]) -> Result:
    """Set the plugin precedence order.

    Args:
        precedence_list: List of plugin names in priority order

    Returns:
        Result indicating success or failure
    """
    try:
        config = Config()
        store = PluginStore()

        # Validate that all plugins in the precedence list exist
        installed_plugins = [p.metadata.name for p in store.list_plugins()]
        missing_plugins = [p for p in precedence_list if p not in installed_plugins]

        if missing_plugins:
            return Error(
                error="✗ Unknown plugins in precedence list: "
                f"{', '.join(missing_plugins)}. "
                f"Installed plugins: {', '.join(installed_plugins)}"
            )

        # Set the precedence configuration
        config.set("plugins.precedence", precedence_list)

        result_message = "✓ Plugin precedence updated:"
        for i, plugin_name in enumerate(precedence_list, 1):
            result_message += f"\n  {i}. {plugin_name}"

        return Success(message=result_message)

    except Exception as e:
        logger.error(f"Failed to set plugin precedence: {e}")
        return Error(error=f"✗ Failed to set plugin precedence: {e}")


async def run_plugin_precedence_add_command(
    plugin_name: str, position: int | None = None
) -> Result:
    """Add a plugin to the precedence list.

    Args:
        plugin_name: Name of the plugin to add
        position: Position to insert at (1-based), or None to append

    Returns:
        Result indicating success or failure
    """
    try:
        config = Config()
        store = PluginStore()

        # Validate plugin exists
        if not store.get_plugin(plugin_name):
            return Error(error=f"✗ Plugin '{plugin_name}' not found.")

        precedence = config.get("plugins.precedence", [])

        # Remove if already in list
        if plugin_name in precedence:
            precedence.remove(plugin_name)

        # Add at specified position or append
        if position is not None:
            # Convert to 0-based index and clamp to valid range
            insert_index = max(0, min(position - 1, len(precedence)))
            precedence.insert(insert_index, plugin_name)
        else:
            precedence.append(plugin_name)

        config.set("plugins.precedence", precedence)

        result_message = f"✓ Added '{plugin_name}' to precedence list:"
        for i, p in enumerate(precedence, 1):
            marker = " ← new" if p == plugin_name else ""
            result_message += f"\n  {i}. {p}{marker}"

        return Success(message=result_message)

    except Exception as e:
        logger.error(f"Failed to add plugin to precedence: {e}")
        return Error(error=f"✗ Failed to add plugin to precedence: {e}")


async def run_plugin_precedence_remove_command(plugin_name: str) -> Result:
    """Remove a plugin from the precedence list.

    Args:
        plugin_name: Name of the plugin to remove

    Returns:
        Result indicating success or failure
    """
    try:
        config = Config()
        precedence = config.get("plugins.precedence", [])

        if plugin_name not in precedence:
            return Error(error=f"✗ Plugin '{plugin_name}' not in precedence list.")

        precedence.remove(plugin_name)
        config.set("plugins.precedence", precedence)

        if precedence:
            result_message = f"✓ Removed '{plugin_name}' from precedence list:"
            for i, p in enumerate(precedence, 1):
                result_message += f"\n  {i}. {p}"
        else:
            result_message = (
                f"✓ Removed '{plugin_name}' from precedence list. List is now empty."
            )

        return Success(message=result_message)

    except Exception as e:
        logger.error(f"Failed to remove plugin from precedence: {e}")
        return Error(error=f"✗ Failed to remove plugin from precedence: {e}")


@click.group(name="plugin")
def plugin_group() -> None:
    """Manage vibectl plugins and precedence configuration."""
    pass


@plugin_group.command("install")
@click.argument("plugin_path", type=click.Path(exists=True))
@click.option("--force", is_flag=True, help="Overwrite existing plugin")
@click.option(
    "--precedence",
    type=click.Choice(["first", "last"]),
    help="Where to place in precedence order",
)
async def plugin_install(plugin_path: str, force: bool, precedence: str | None) -> None:
    """Install a plugin from a local file path."""
    result = await run_plugin_install_command(plugin_path, force, precedence)
    if isinstance(result, Error):
        handle_exception(Exception(result.error), exit_on_error=True)
    else:
        console_manager.print(result.message)


@plugin_group.command("list")
async def plugin_list() -> None:
    """List all installed plugins."""
    result = await run_plugin_list_command()
    if isinstance(result, Error):
        handle_exception(Exception(result.error), exit_on_error=True)
    elif result.message:  # Only print if there's a message (not empty for table output)
        console_manager.print(result.message)


@plugin_group.command("uninstall")
@click.argument("plugin_id")
async def plugin_uninstall(plugin_id: str) -> None:
    """Uninstall a plugin by ID."""
    result = await run_plugin_uninstall_command(plugin_id)
    if isinstance(result, Error):
        handle_exception(Exception(result.error), exit_on_error=True)
    else:
        console_manager.print(result.message)


@plugin_group.command("update")
@click.argument("plugin_id")
@click.argument("plugin_path", type=click.Path(exists=True))
async def plugin_update(plugin_id: str, plugin_path: str) -> None:
    """Update an existing plugin with a new version."""
    result = await run_plugin_update_command(plugin_id, plugin_path)
    if isinstance(result, Error):
        handle_exception(Exception(result.error), exit_on_error=True)
    else:
        console_manager.print(result.message)


@plugin_group.group("precedence")
def precedence_group() -> None:
    """Manage plugin precedence order."""
    pass


@precedence_group.command("list")
async def precedence_list() -> None:
    """List the current plugin precedence order."""
    result = await run_plugin_precedence_list_command()
    if isinstance(result, Error):
        handle_exception(Exception(result.error), exit_on_error=True)
    else:
        console_manager.print(result.message)


@precedence_group.command("set")
@click.argument("plugins", nargs=-1, required=True)
async def precedence_set(plugins: tuple[str, ...]) -> None:
    """Set the plugin precedence order.

    PLUGINS: List of plugin names in priority order (highest to lowest)

    Example: vibectl plugin precedence set plugin-a plugin-b plugin-c
    """
    result = await run_plugin_precedence_set_command(list(plugins))
    if isinstance(result, Error):
        handle_exception(Exception(result.error), exit_on_error=True)
    else:
        console_manager.print(result.message)


@precedence_group.command("add")
@click.argument("plugin_name")
@click.option("--position", type=int, help="Position to insert at (1-based)")
async def precedence_add(plugin_name: str, position: int | None) -> None:
    """Add a plugin to the precedence list."""
    result = await run_plugin_precedence_add_command(plugin_name, position)
    if isinstance(result, Error):
        handle_exception(Exception(result.error), exit_on_error=True)
    else:
        console_manager.print(result.message)


@precedence_group.command("remove")
@click.argument("plugin_name")
async def precedence_remove(plugin_name: str) -> None:
    """Remove a plugin from the precedence list."""
    result = await run_plugin_precedence_remove_command(plugin_name)
    if isinstance(result, Error):
        handle_exception(Exception(result.error), exit_on_error=True)
    else:
        console_manager.print(result.message)
