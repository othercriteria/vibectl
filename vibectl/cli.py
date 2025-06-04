"""
Command-line interface for vibectl.

Provides a vibes-based alternative to kubectl, using AI to generate human-friendly
summaries of Kubernetes resources. Each command aims to make cluster management
more intuitive while preserving access to raw kubectl output when needed.
"""

import os
import sys
from collections.abc import Callable

import asyncclick as click
from rich.panel import Panel
from rich.table import Table

from vibectl.memory import (
    clear_memory,
    disable_memory,
    enable_memory,
    get_memory,
    set_memory,
)
from vibectl.subcommands.apply_cmd import run_apply_command
from vibectl.subcommands.auto_cmd import run_auto_command, run_semiauto_command
from vibectl.subcommands.check_cmd import run_check_command
from vibectl.subcommands.cluster_info_cmd import run_cluster_info_command
from vibectl.subcommands.create_cmd import run_create_command
from vibectl.subcommands.delete_cmd import run_delete_command
from vibectl.subcommands.describe_cmd import run_describe_command
from vibectl.subcommands.diff_cmd import run_diff_command
from vibectl.subcommands.edit_cmd import run_edit_command
from vibectl.subcommands.events_cmd import run_events_command
from vibectl.subcommands.get_cmd import run_get_command
from vibectl.subcommands.just_cmd import run_just_command
from vibectl.subcommands.logs_cmd import run_logs_command
from vibectl.subcommands.memory_update_cmd import run_memory_update_logic
from vibectl.subcommands.patch_cmd import run_patch_command
from vibectl.subcommands.plugin_cmd import plugin_group
from vibectl.subcommands.port_forward_cmd import run_port_forward_command
from vibectl.subcommands.rollout_cmd import run_rollout_command
from vibectl.subcommands.scale_cmd import run_scale_command
from vibectl.subcommands.setup_proxy_cmd import setup_proxy_group
from vibectl.subcommands.version_cmd import run_version_command
from vibectl.subcommands.vibe_cmd import run_vibe_command
from vibectl.subcommands.wait_cmd import run_wait_command

from . import __version__
from .config import DEFAULT_CONFIG, Config
from .console import console_manager
from .logutil import init_logging, logger
from .model_adapter import validate_model_key_on_startup
from .types import (
    Error,
    MetricsDisplayMode,
    Result,
    Success,
)
from .utils import handle_exception


# --- Common Option Decorator ---
def common_command_options(
    include_show_kubectl: bool = False,
    include_live_display: bool = False,
    include_yes: bool = False,
    include_show_metrics: bool = True,
    include_show_streaming: bool = True,
    include_freeze_memory: bool = True,
) -> Callable:
    """Decorator to DRY out common CLI options for subcommands."""

    def decorator(f: Callable) -> Callable:
        options = [
            click.option(
                "--show-raw-output/--no-show-raw-output", is_flag=True, default=None
            ),
            click.option("--show-vibe/--no-show-vibe", is_flag=True, default=None),
            click.option("--model", default=None, help="The LLM model to use"),
        ]
        if include_freeze_memory:
            options.append(
                click.option(
                    "--freeze-memory",
                    is_flag=True,
                    default=None,
                    help="Prevent memory updates for this command",
                )
            )
            options.append(
                click.option(
                    "--unfreeze-memory",
                    is_flag=True,
                    default=None,
                    help="Enable memory updates for this command",
                )
            )
        if include_show_kubectl:
            options.append(
                click.option(
                    "--show-kubectl/--no-show-kubectl",
                    is_flag=True,
                    default=None,
                    help="Show the kubectl command being executed",
                )
            )
        if include_live_display:
            options.append(
                click.option(
                    "--live-display/--no-live-display",
                    is_flag=True,
                    default=True,
                    help="Show a live spinner with elapsed time during waiting",
                )
            )
        if include_yes:
            options.append(
                click.option(
                    "--yes", "-y", is_flag=True, help="Skip confirmation prompt"
                )
            )
        if include_show_metrics:
            options.append(
                click.option(
                    "--show-metrics",
                    type=click.Choice(
                        ["none", "total", "sub", "all"], case_sensitive=False
                    ),
                    default=None,
                    help="Show LLM latency and token usage metrics "
                    "(none, total, sub, all)",
                )
            )
        if include_show_streaming:
            options.append(
                click.option(
                    "--show-streaming/--no-show-streaming",
                    is_flag=True,
                    default=None,
                    help="Show intermediate streaming output for LLM summary",
                )
            )
        for option in reversed(options):
            f = option(f)
        return f

    return decorator


def show_welcome_if_no_subcommand(ctx: click.Context) -> None:
    """Show the welcome message if no subcommand is invoked.

    Args:
        ctx: The Click context
    """
    if ctx.invoked_subcommand is None:
        logger.info("No subcommand invoked; showing welcome message.")
        console_manager.print("Checking cluster vibes...")
        console_manager.print_vibe_welcome()


# --- CLI Group with Global Options ---
@click.group(invoke_without_command=True)
@click.version_option(version=__version__)
@click.option(
    "--log-level",
    type=click.Choice(
        ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], case_sensitive=False
    ),
    default=None,
    help="Set the logging level for all commands.",
)
@click.option(
    "--verbose",
    is_flag=True,
    default=False,
    help="Shortcut for --log-level=DEBUG.",
)
@click.pass_context
async def cli(ctx: click.Context, log_level: str | None, verbose: bool) -> None:
    """vibectl - A vibes-based alternative to kubectl"""
    # Set logging level from CLI flags

    if verbose:
        os.environ["VIBECTL_LOG_LEVEL"] = "DEBUG"
    elif log_level:
        os.environ["VIBECTL_LOG_LEVEL"] = log_level.upper()
    init_logging()
    logger.info("vibectl CLI started")
    # Initialize the console manager with the configured theme
    try:
        cfg = Config()
        theme_name = cfg.get("display.theme", "default")
        console_manager.set_theme(theme_name)
    except Exception as e:
        logger.warning(f"Failed to set theme: {e}")
        # Fallback to default in case of any issues (helpful for tests)
        pass

    # Validate model configuration on startup - outside try/except for testing
    cfg = Config()  # Get a fresh config instance
    model_name = cfg.get("llm.model", DEFAULT_CONFIG["llm"]["model"])
    validation_warning = validate_model_key_on_startup(model_name)
    if validation_warning and ctx.invoked_subcommand not in ["config", "help"]:
        console_manager.print_warning(validation_warning)
        logger.warning(f"Model validation warning: {validation_warning}")

    # Show welcome message if no subcommand is invoked
    show_welcome_if_no_subcommand(ctx)


cli.add_command(plugin_group)
cli.add_command(setup_proxy_group)


@cli.command(context_settings={"ignore_unknown_options": True})
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@common_command_options(include_show_kubectl=True)
async def get(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool,
    unfreeze_memory: bool,
    show_kubectl: bool | None = None,
    show_metrics: MetricsDisplayMode | None = None,
    show_streaming: bool | None = None,
) -> None:
    """Get resources in a concise format."""
    # Await the call to the now-async runner function
    result = await run_get_command(
        resource=resource,
        args=args,
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        show_kubectl=show_kubectl,
        model=model,
        freeze_memory=freeze_memory,
        unfreeze_memory=unfreeze_memory,
        show_metrics=show_metrics,
        show_streaming=show_streaming,
    )
    handle_result(result)


@cli.command(context_settings={"ignore_unknown_options": True})
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@common_command_options(include_show_kubectl=True)
async def describe(
    resource: str,
    args: tuple,
    show_raw_output: bool | None = None,
    show_vibe: bool | None = None,
    model: str | None = None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    show_kubectl: bool | None = None,
    show_metrics: MetricsDisplayMode | None = None,
    show_streaming: bool | None = None,
) -> None:
    """Show details of a specific resource or group of resources."""
    result = await run_describe_command(
        resource=resource,
        args=args,
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        show_kubectl=show_kubectl,
        model=model,
        freeze_memory=freeze_memory,
        unfreeze_memory=unfreeze_memory,
        show_metrics=show_metrics,
        show_streaming=show_streaming,
    )
    handle_result(result)


@cli.command(context_settings={"ignore_unknown_options": True})
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@common_command_options(include_show_kubectl=True)
async def logs(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    show_kubectl: bool | None = None,
    show_metrics: MetricsDisplayMode | None = None,
    show_streaming: bool | None = None,
) -> None:
    """Show logs for a container in a pod."""
    result = await run_logs_command(
        resource=resource,
        args=args,
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        show_kubectl=show_kubectl,
        model=model,
        freeze_memory=freeze_memory,
        unfreeze_memory=unfreeze_memory,
        show_metrics=show_metrics,
        show_streaming=show_streaming,
    )
    handle_result(result)


@cli.command(context_settings={"ignore_unknown_options": True})
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@common_command_options(include_show_kubectl=True)
async def create(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    show_kubectl: bool | None = None,
    show_metrics: MetricsDisplayMode | None = None,
    show_streaming: bool | None = None,
) -> None:
    """Create resources from a file or stdin."""
    result = await run_create_command(
        resource=resource,
        args=args,
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        show_kubectl=show_kubectl,
        model=model,
        freeze_memory=freeze_memory,
        unfreeze_memory=unfreeze_memory,
        show_metrics=show_metrics,
        show_streaming=show_streaming,
    )
    handle_result(result)


@cli.command(context_settings={"ignore_unknown_options": True})
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@common_command_options(include_show_kubectl=True, include_yes=True)
async def delete(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    show_kubectl: bool | None = None,
    yes: bool = False,
    show_metrics: MetricsDisplayMode | None = None,
    show_streaming: bool | None = None,
) -> None:
    """Delete a resource."""

    # Await the call to the now-async runner function
    result = await run_delete_command(
        resource=resource,
        args=args,
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        model=model,
        freeze_memory=freeze_memory,
        unfreeze_memory=unfreeze_memory,
        show_kubectl=show_kubectl,
        yes=yes,
        show_metrics=show_metrics,
        show_streaming=show_streaming,
    )
    handle_result(result)


@cli.command(context_settings={"ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
async def just(args: tuple) -> None:
    """Pass commands directly to kubectl.

    Passes all arguments directly to kubectl without any processing.
    Useful for commands not yet supported by vibectl or when you want
    to use kubectl directly.

    Example:
        vibectl just get pods  # equivalent to: kubectl get pods
    """
    result = await run_just_command(args)
    handle_result(result)


@cli.group()
def config() -> None:
    """Manage vibectl configuration."""
    pass


@config.command(name="set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str) -> None:
    """Set a configuration value.

    Supports hierarchical keys using dot notation.

    Examples:
        vibectl config set display.theme dark
        vibectl config set core.kubeconfig ~/.kube/my-config
        vibectl config set llm.model claude-4-sonnet
        vibectl config set display.show_raw_output true
    """
    try:
        cfg = Config()
        cfg.set(key, value)
        cfg.save()
        console_manager.print_success(f"Configuration {key} set to {value}")
    except ValueError as e:
        handle_exception(e)


@config.command()
@click.argument("section", required=False)
def show(section: str | None = None) -> None:
    """Show configuration values.

    Can show all config or just a specific section.

    Examples:
        vibectl config show           # Show all configuration
        vibectl config show llm       # Show only LLM section
        vibectl config show display   # Show only display section
        vibectl config show core.kubeconfig  # Show single value
    """
    try:
        cfg = Config()
        config_data = cfg.get_all()

        # Handle specific path or section
        if section:
            if "." in section:
                # Single value (e.g., llm.model)
                try:
                    value = cfg.get(section)
                    console_manager.print(f"{section}: {value}")
                    return
                except Exception:
                    console_manager.print_error(f"Config path not found: {section}")
                    return
            else:
                # Section filter (e.g., llm, display)
                if section not in config_data:
                    available_sections = list(config_data.keys())
                    console_manager.print_error(
                        f"Section '{section}' not found. Available sections: "
                        f"{', '.join(available_sections)}"
                    )
                    return

                # Show only the specified section
                section_data = config_data[section]
                if isinstance(section_data, dict):
                    table = Table(title=f"Configuration - {section.title()} Section")
                    table.add_column("Key")
                    table.add_column("Value", style="green")

                    for key, value in section_data.items():
                        table.add_row(f"{section}.{key}", str(value))

                    console_manager.safe_print(console_manager.console, table)
                else:
                    console_manager.print(f"{section}: {section_data}")
                return

        # Show all configuration with section headers
        table = Table(title="Configuration")
        table.add_column("Key")
        table.add_column("Value", style="green")

        # Group top-level items first
        for key, value in config_data.items():
            if not isinstance(value, dict):
                table.add_row(key, str(value))

        # Then show each section
        for section_name, section_data in config_data.items():
            if isinstance(section_data, dict):
                # Add a separator row for the section
                table.add_row(f"[bold blue]{section_name.upper()}[/bold blue]", "")
                for key, value in section_data.items():
                    table.add_row(f"  {section_name}.{key}", str(value))

        console_manager.safe_print(console_manager.console, table)
    except Exception as e:
        handle_exception(e)


@config.command()
@click.argument("key")
def unset(key: str) -> None:
    """Unset a configuration value, resetting it to default.

    Supports hierarchical keys using dot notation.

    Examples:
        vibectl config unset display.theme  # Reset theme to default
        vibectl config unset core.kubeconfig  # Reset kubeconfig to default
        vibectl config unset llm.model_keys.openai  # Reset openai key to default
    """
    try:
        cfg = Config()
        cfg.unset(key)
        console_manager.print_success(f"Configuration {key} reset to default")
    except ValueError as e:
        handle_exception(e)


@config.command()
def info() -> None:
    """Show configuration file information.

    Examples:
        vibectl config info
    """
    try:
        cfg = Config()

        # Get file info
        config_file = cfg.config_file
        file_exists = config_file.exists()

        table = Table(title="Configuration Information")
        table.add_column("Property")
        table.add_column("Value", style="green")

        table.add_row("Configuration file", str(config_file))
        table.add_row("File exists", "Yes" if file_exists else "No")

        if file_exists:
            import time

            stat = config_file.stat()
            last_modified = time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)
            )
            table.add_row("Last modified", last_modified)
            table.add_row("File size", f"{stat.st_size} bytes")

        table.add_row("Config directory", str(cfg.config_dir))

        console_manager.safe_print(console_manager.console, table)

    except Exception as e:
        handle_exception(e)


@cli.group()
def instructions() -> None:
    """Manage custom instructions for vibe prompts."""
    pass


@instructions.command(name="set")
@click.argument("instructions_text", required=False)
@click.option("--edit", is_flag=True, help="Open an editor to write instructions")
async def instructions_set(
    instructions_text: str | None = None, edit: bool = False
) -> None:
    """Set custom instructions for the LLM."""
    cfg = Config()
    current_instructions = cfg.get("system.custom_instructions", "")

    if edit:
        logger.info("Opening editor for custom instructions")
        edited_instructions = click.edit(current_instructions)
        if edited_instructions is not None:
            instructions_text = edited_instructions
            logger.info("Instructions updated via editor")
        else:
            logger.info("Editor closed without saving instructions")
            console_manager.print_note("Instructions not changed.")
            return

    if not instructions_text:
        # Check if input is being piped
        if not sys.stdin.isatty():
            instructions_text = sys.stdin.read().strip()
            if not instructions_text:
                raise ValueError("No instructions provided via stdin")
            logger.info("Instructions received from stdin")
        else:
            raise ValueError("No instructions text provided.")

    try:
        cfg.set("system.custom_instructions", instructions_text)
        cfg.save()
        logger.info("Custom instructions saved successfully")
        console_manager.print_success("Custom instructions set successfully.")
    except Exception as e:
        logger.error("Error saving custom instructions: %s", e, exc_info=True)
        handle_exception(e)


@instructions.command(name="show")
async def instructions_show() -> None:
    """Show the current custom instructions."""
    cfg = Config()
    try:
        instructions_text = cfg.get("system.custom_instructions", "")
        if instructions_text:
            console_manager.print_note("Custom instructions:")
            console_manager.print(instructions_text)
        else:
            console_manager.print_note("No custom instructions set")
    except Exception as e:
        logger.error("Error getting custom instructions: %s", e, exc_info=True)
        handle_exception(e)


@instructions.command()
async def clear() -> None:
    """Clear the custom instructions."""
    cfg = Config()
    try:
        cfg.set("system.custom_instructions", "")
        cfg.save()
        logger.info("Custom instructions cleared successfully")
        console_manager.print_success("Custom instructions cleared.")
    except Exception as e:
        logger.error("Error clearing custom instructions: %s", e, exc_info=True)
        handle_exception(e)


# --- Helper function for theme setting logic ---
def _set_theme_logic(theme_name: str) -> None:
    """Handles the core logic of validating and setting the theme."""
    # Verify theme exists
    available_themes = console_manager.get_available_themes()
    if theme_name not in available_themes:
        msg = (
            f"Invalid theme '{theme_name}'. Available themes: "
            f"{', '.join(available_themes)}"
        )
        # Raise ValueError instead of exiting
        raise ValueError(msg)

    # Save theme in config
    cfg = Config()
    cfg.set("display.theme", theme_name)
    cfg.save()  # Save the config after setting
    console_manager.print_success(f"Theme set to '{theme_name}'.")


@cli.group()
def theme() -> None:
    """Manage vibectl themes."""
    pass


@theme.command()
def list() -> None:
    """List available themes."""
    try:
        available_themes = console_manager.get_available_themes()
        console_manager.print_note("Available themes:")
        for theme in available_themes:
            console_manager.print(f"  - {theme}")
    except Exception as e:
        handle_exception(e)


@theme.command(name="set")
@click.argument("theme_name")
def theme_set(theme_name: str) -> None:
    """Set the vibectl theme."""
    try:
        _set_theme_logic(theme_name)
        console_manager.print(f"✓ Theme set to '{theme_name}'")
    except Exception as e:
        logger.error(f"Failed to set theme: {e}")
        console_manager.print_error(f"✗ Failed to set theme: {e}")
        handle_exception(e)


@cli.command()
@click.argument("request", required=False)
@common_command_options(
    include_show_kubectl=True,
    include_yes=True,
    include_show_metrics=True,
    include_show_streaming=True,
)
@click.option(
    "--limit", "-l", type=int, default=None, help="Maximum number of iterations to run"
)
@click.option(
    "--interval",
    "-i",
    type=int,
    default=5,
    help="Seconds to wait between iterations (default: 5)",
)
async def auto(
    request: str | None,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    show_kubectl: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    interval: int = 5,
    limit: int | None = None,
    yes: bool = False,
    show_metrics: MetricsDisplayMode | None = None,
    show_streaming: bool | None = None,
) -> None:
    """Loop vibectl vibe commands automatically."""
    try:
        # Await run_auto_command
        result = await run_auto_command(
            request=request,
            show_raw_output=show_raw_output,
            show_vibe=show_vibe,
            show_kubectl=show_kubectl,
            model=model,
            freeze_memory=freeze_memory,
            unfreeze_memory=unfreeze_memory,
            interval=interval,
            limit=limit,
            yes=yes,
            show_metrics=show_metrics,
            show_streaming=show_streaming,
            semiauto=False,  # Auto command is not in semiauto mode
            exit_on_error=True,  # Auto command should exit on error by default
        )
        handle_result(result)
    except Exception as e:
        handle_exception(e)


@cli.command()
@click.argument("request", required=False)
@common_command_options(
    include_show_kubectl=True,
    include_show_metrics=True,
    include_show_streaming=True,
)
@click.option(
    "--limit", "-l", type=int, default=None, help="Maximum number of iterations to run"
)
async def semiauto(
    request: str | None,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    show_kubectl: bool | None,
    model: str | None,
    freeze_memory: bool,
    unfreeze_memory: bool,
    limit: int | None = None,
    show_metrics: MetricsDisplayMode | None = None,
    show_streaming: bool | None = None,
) -> None:
    """Run vibe command in semiauto mode with manual confirmation.

    This is a convenience wrapper around 'vibectl auto --semiauto'.
    In semiauto mode, you will need to confirm each step before it executes.
    This can be useful for learning or when working with complex requests.
    """
    try:
        result = await run_semiauto_command(
            request=request,
            show_raw_output=show_raw_output,
            show_vibe=show_vibe,
            show_kubectl=show_kubectl,
            model=model,
            freeze_memory=freeze_memory,
            unfreeze_memory=unfreeze_memory,
            limit=limit,
            show_metrics=show_metrics,
            show_streaming=show_streaming,
        )
        handle_result(result)
    except Exception:
        # Let exceptions propagate to main() for centralized handling
        raise


@cli.command(context_settings={"ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@common_command_options(include_show_kubectl=True)
async def events(
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    show_kubectl: bool | None = None,
    show_metrics: MetricsDisplayMode | None = None,
    show_streaming: bool | None = None,
) -> None:
    """List events in the cluster."""
    result = await run_events_command(
        args=args,
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        show_kubectl=show_kubectl,
        model=model,
        freeze_memory=freeze_memory,
        unfreeze_memory=unfreeze_memory,
        show_metrics=show_metrics,
        show_streaming=show_streaming,
    )
    handle_result(result)


@cli.command(context_settings={"ignore_unknown_options": True})
@click.argument("predicate", nargs=-1, type=click.UNPROCESSED, required=True)
@common_command_options(include_show_kubectl=True, include_yes=True)
async def check(
    predicate: tuple[str, ...],
    show_raw_output: bool | None,
    show_vibe: bool | None,
    show_kubectl: bool | None,
    model: str | None,
    freeze_memory: bool,
    unfreeze_memory: bool,
    yes: bool,
    show_metrics: MetricsDisplayMode | None,
    show_streaming: bool | None,
) -> None:
    """Determine if a predicate about the cluster is true."""
    result = await run_check_command(
        predicate=" ".join(predicate),
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        show_kubectl=show_kubectl,
        model=model,
        freeze_memory=freeze_memory,
        unfreeze_memory=unfreeze_memory,
        yes=yes,
        show_metrics=show_metrics,
        show_streaming=show_streaming,
    )
    handle_result(result)


@cli.command()
@click.argument("request", required=False)
@common_command_options(include_show_kubectl=True, include_yes=True)
@click.option(
    "--show-metrics",
    type=click.Choice(["none", "total", "sub", "all"], case_sensitive=False),
    default=None,
    help="Show LLM latency and token usage metrics (none, total, sub, all)",
)
async def vibe(
    request: str | None,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    show_kubectl: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    yes: bool = False,
    show_metrics: MetricsDisplayMode | None = None,
    show_streaming: bool | None = None,
) -> None:
    """LLM interprets natural language request and runs fitting kubectl command."""
    # Call run_vibe_command instead of handle_vibe_request directly
    result = await run_vibe_command(
        request=request,
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        show_kubectl=show_kubectl,
        model=model,
        freeze_memory=freeze_memory,
        unfreeze_memory=unfreeze_memory,
        yes=yes,
        semiauto=False,  # Vibe command is never called in semiauto loop directly
        exit_on_error=False,  # Let handle_result manage exit
        show_metrics=show_metrics,
        show_streaming=show_streaming,
    )
    handle_result(result)


@cli.command()
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@common_command_options(include_show_kubectl=True, include_yes=True)
async def version(
    args: tuple,
    show_raw_output: bool | None = None,
    show_vibe: bool | None = None,
    model: str | None = None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    show_kubectl: bool | None = None,
    show_metrics: MetricsDisplayMode | None = None,
    yes: bool = False,
    show_streaming: bool | None = None,
) -> None:
    """Show client and server versions."""
    result = await run_version_command(
        args=args,
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        model=model,
        freeze_memory=freeze_memory,
        unfreeze_memory=unfreeze_memory,
        show_kubectl=show_kubectl,
        show_metrics=show_metrics,
        show_streaming=show_streaming,
    )
    handle_result(result)


@cli.command()
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@common_command_options(include_show_kubectl=True, include_yes=True)
async def cluster_info(
    args: tuple,
    show_raw_output: bool | None = None,
    show_vibe: bool | None = None,
    model: str | None = None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    show_kubectl: bool | None = None,
    show_metrics: MetricsDisplayMode | None = None,
    yes: bool = False,
    show_streaming: bool | None = None,
) -> None:
    """Get cluster information."""
    result = await run_cluster_info_command(
        args=args,
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        model=model,
        freeze_memory=freeze_memory,
        unfreeze_memory=unfreeze_memory,
        show_kubectl=show_kubectl,
        show_metrics=show_metrics,
        show_streaming=show_streaming,
    )
    handle_result(result)


@cli.group(name="memory", help="Memory management commands")
def memory_group() -> None:
    """Group for memory-related commands."""
    pass


@memory_group.command(name="show", help="Show current memory content")
def memory_show() -> None:
    """Display the current memory content."""
    try:
        memory_content = get_memory()
        if memory_content:
            console_manager.safe_print(
                console_manager.console,
                Panel(
                    memory_content,
                    title="Memory Content",
                    border_style="blue",
                    expand=False,
                ),
            )
        else:
            console_manager.print_warning(
                "Memory is empty. Use 'vibectl memory set' to add content."
            )
    except Exception as e:
        handle_exception(e)


@memory_group.command(name="set", help="Set memory content")
@click.argument("text", nargs=-1, required=False)
@click.option(
    "--edit",
    "-e",
    is_flag=True,
    help="Open editor to write memory content",
)
def memory_set(text: tuple | None = None, edit: bool = False) -> None:
    """Set memory content.

    TEXT argument is optional and can be used to directly set content.
    Use --edit flag to open an editor instead.
    """
    if edit:
        try:
            initial_text = get_memory() or "# Enter memory content here\n"
            edited_text = click.edit(initial_text)
            if edited_text is not None:
                set_memory(edited_text)
                console_manager.print_success("Memory updated from editor")
            else:
                console_manager.print_warning("Memory update cancelled")
        except Exception as e:
            console_manager.print_error(str(e))
            raise click.Abort() from e
    elif text and len(text) > 0:
        try:
            # Join the text parts to handle multi-word input
            memory_text = " ".join(text)
            set_memory(memory_text)
            console_manager.print_success("Memory set")
        except Exception as e:
            console_manager.print_error(str(e))
            raise click.Abort() from e
    else:
        import sys

        if not sys.stdin.isatty():
            stdin_content = sys.stdin.read()
            if stdin_content.strip():
                set_memory(stdin_content)
                console_manager.print_success("Memory set from stdin")
                return
        console_manager.print_error(
            "No text provided. Use TEXT argument, --edit flag, or pipe input via stdin."
        )
        raise click.Abort()


@memory_group.command()
def freeze() -> None:
    """Disable automatic memory updates."""
    try:
        disable_memory()
        console_manager.print_success("Memory updates frozen (disabled)")
    except Exception as e:
        handle_exception(e)


@memory_group.command()
def unfreeze() -> None:
    """Enable automatic memory updates."""
    try:
        enable_memory()
        console_manager.print_success("Memory updates unfrozen (enabled)")
    except Exception as e:
        handle_exception(e)


@memory_group.command(name="clear")
def memory_clear() -> None:
    """Clear memory content."""
    try:
        clear_memory()
        console_manager.print_success("Memory content cleared")
    except Exception as e:
        handle_exception(e)


@memory_group.command(name="update")
@click.argument("update_text", nargs=-1, required=True)
@click.option("--model", default=None, help="The LLM model to use")
@click.option(
    "--show-streaming/--no-show-streaming",
    is_flag=True,
    default=None,
    help="Show streaming output for LLM responses.",
)
@click.pass_context
async def memory_update(
    ctx: click.Context,
    update_text: tuple,
    model: str | None = None,
    show_streaming: bool | None = None,
) -> None:
    """Update memory with new content using LLM summarization."""
    update_text_str = " ".join(update_text)
    result = await run_memory_update_logic(
        update_text_str=update_text_str,
        model_name=model,
    )
    handle_result(result)


@cli.command(context_settings={"ignore_unknown_options": True})
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@common_command_options(include_show_kubectl=True)
async def scale(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    show_kubectl: bool | None = None,
    show_metrics: MetricsDisplayMode | None = None,
    show_streaming: bool | None = None,
) -> None:
    """Scale resources.

    Scales Kubernetes resources like deployments, statefulsets, or replicasets to
    the specified number of replicas.

    Examples:
        vibectl scale deployment/nginx --replicas=3
        vibectl scale statefulset/redis -n cache --replicas=5
        vibectl scale deployment frontend --replicas=0
        vibectl scale vibe "scale the frontend deployment to 3 replicas"
    """
    # Await the call to the async runner function
    result = await run_scale_command(
        resource=resource,
        args=args,
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        show_kubectl=show_kubectl,
        model=model,
        freeze_memory=freeze_memory,
        unfreeze_memory=unfreeze_memory,
        show_metrics=show_metrics,
        show_streaming=show_streaming,
    )
    handle_result(result)


@cli.command(context_settings={"ignore_unknown_options": True})
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@common_command_options(include_show_kubectl=True)
async def patch(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    show_kubectl: bool | None = None,
    show_metrics: MetricsDisplayMode | None = None,
    show_streaming: bool | None = None,
) -> None:
    """Apply patches to Kubernetes resources in place.

    Supports strategic merge patches, JSON merge patches, and JSON patches.
    Can patch resources by file or by type/name.

    Supports vibe mode for natural language patch descriptions:

    Examples:
        # Strategic merge patch with inline patch
        vibectl patch deployment frontend -p '{"spec":{"replicas":3}}'

        # Apply patch from file
        vibectl patch deployment frontend --patch-file patch.yaml

        # Vibe mode for natural language patches
        vibectl patch vibe "scale the frontend deployment to 3 replicas"
        vibectl patch vibe "update nginx image to version 1.21"
        vibectl patch vibe "add label environment=prod to the frontend service"
    """
    # Await the call to the async runner function
    result = await run_patch_command(
        resource=resource,
        args=args,
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        show_kubectl=show_kubectl,
        model=model,
        freeze_memory=freeze_memory,
        unfreeze_memory=unfreeze_memory,
        show_metrics=show_metrics,
        show_streaming=show_streaming,
    )
    handle_result(result)


@cli.command(context_settings={"ignore_unknown_options": True})
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@common_command_options(include_show_kubectl=True)
async def edit(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    show_kubectl: bool | None = None,
    show_metrics: MetricsDisplayMode | None = None,
    show_streaming: bool | None = None,
) -> None:
    """Edit Kubernetes resources in place.

    Opens resources in an editor for interactive modification.
    Supports both traditional kubectl edit and intelligent vibe mode editing.

    Supports vibe mode for AI-assisted editing:

    Examples:
        # Traditional kubectl edit
        vibectl edit deployment frontend

        # Edit with specific editor
        vibectl edit service api-server --editor=vim

        # Vibe mode for AI-assisted editing
        vibectl edit vibe "nginx deployment liveness and readiness config"
        vibectl edit vibe "add resource limits to the frontend deployment"
        vibectl edit vibe "configure ingress for the api service"
    """
    # Await the call to the async runner function
    result = await run_edit_command(
        resource=resource,
        args=args,
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        show_kubectl=show_kubectl,
        model=model,
        freeze_memory=freeze_memory,
        unfreeze_memory=unfreeze_memory,
        show_metrics=show_metrics,
        show_streaming=show_streaming,
    )
    handle_result(result)


@cli.group(
    invoke_without_command=True, context_settings={"ignore_unknown_options": True}
)
@common_command_options(include_show_kubectl=True)
@click.pass_context
def rollout(
    ctx: click.Context,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    show_kubectl: bool | None = None,
    show_metrics: MetricsDisplayMode | None = None,
    show_streaming: bool | None = None,
) -> None:
    """Manage rollouts of deployments, statefulsets, and daemonsets."""
    if ctx.invoked_subcommand is not None:
        # Store common flags in context to pass to subcommands
        ctx.obj = {
            "show_raw_output": show_raw_output,
            "show_vibe": show_vibe,
            "model": model,
            "freeze_memory": freeze_memory,
            "unfreeze_memory": unfreeze_memory,
            "show_kubectl": show_kubectl,
            "show_metrics": show_metrics,
            "show_streaming": show_streaming,
        }
        return

    console_manager.print_error(
        "Missing subcommand for rollout. "
        "Use one of: status, history, undo, restart, pause, resume"
    )
    sys.exit(1)


async def _rollout_common(
    subcommand: str,
    resource: str,
    args: tuple,
    # These will now come from ctx.obj
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool,
    unfreeze_memory: bool,
    show_kubectl: bool | None,
    yes: bool = False,
    show_metrics: MetricsDisplayMode | None = None,
    show_streaming: bool | None = None,
) -> None:
    # Await run_rollout_command
    result = await run_rollout_command(
        subcommand=subcommand,
        resource=resource,
        args=args,
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        show_kubectl=show_kubectl,
        model=model,
        freeze_memory=freeze_memory,
        unfreeze_memory=unfreeze_memory,
        yes=yes,
        show_metrics=show_metrics,
    )
    handle_result(result)


@rollout.command(context_settings={"ignore_unknown_options": True})
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@common_command_options(include_show_kubectl=True)
async def status(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    show_kubectl: bool | None = None,
    show_metrics: MetricsDisplayMode | None = None,
) -> None:
    await _rollout_common(
        subcommand="status",
        resource=resource,
        args=args,
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        model=model,
        freeze_memory=freeze_memory,
        unfreeze_memory=unfreeze_memory,
        show_kubectl=show_kubectl,
        yes=False,
        show_metrics=show_metrics,
    )


@rollout.command(context_settings={"ignore_unknown_options": True})
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@common_command_options(include_show_kubectl=True)
async def history(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    show_kubectl: bool | None = None,
    show_metrics: MetricsDisplayMode | None = None,
) -> None:
    await _rollout_common(
        subcommand="history",
        resource=resource,
        args=args,
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        model=model,
        freeze_memory=freeze_memory,
        unfreeze_memory=unfreeze_memory,
        show_kubectl=show_kubectl,
        yes=False,
        show_metrics=show_metrics,
    )


@rollout.command(context_settings={"ignore_unknown_options": True})
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@common_command_options(include_show_kubectl=True)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
async def undo(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    show_kubectl: bool | None = None,
    yes: bool = False,
    show_metrics: MetricsDisplayMode | None = None,
) -> None:
    await _rollout_common(
        subcommand="undo",
        resource=resource,
        args=args,
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        model=model,
        freeze_memory=freeze_memory,
        unfreeze_memory=unfreeze_memory,
        show_kubectl=show_kubectl,
        yes=yes,
        show_metrics=show_metrics,
    )


@rollout.command(context_settings={"ignore_unknown_options": True})
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@common_command_options(include_show_kubectl=True)
async def restart(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    show_kubectl: bool | None = None,
    show_metrics: MetricsDisplayMode | None = None,
) -> None:
    await _rollout_common(
        subcommand="restart",
        resource=resource,
        args=args,
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        model=model,
        freeze_memory=freeze_memory,
        unfreeze_memory=unfreeze_memory,
        show_kubectl=show_kubectl,
        yes=False,
        show_metrics=show_metrics,
    )


@rollout.command(context_settings={"ignore_unknown_options": True})
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@common_command_options(include_show_kubectl=True)
async def pause(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    show_kubectl: bool | None = None,
    show_metrics: MetricsDisplayMode | None = None,
) -> None:
    await _rollout_common(
        subcommand="pause",
        resource=resource,
        args=args,
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        model=model,
        freeze_memory=freeze_memory,
        unfreeze_memory=unfreeze_memory,
        show_kubectl=show_kubectl,
        yes=False,
        show_metrics=show_metrics,
    )


@rollout.command(context_settings={"ignore_unknown_options": True})
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@common_command_options(include_show_kubectl=True)
async def resume(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    show_kubectl: bool | None = None,
    show_metrics: MetricsDisplayMode | None = None,
) -> None:
    await _rollout_common(
        subcommand="resume",
        resource=resource,
        args=args,
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        model=model,
        freeze_memory=freeze_memory,
        unfreeze_memory=unfreeze_memory,
        show_kubectl=show_kubectl,
        yes=False,
        show_metrics=show_metrics,
    )


@cli.command(context_settings={"ignore_unknown_options": True})
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@common_command_options(
    include_show_kubectl=True,
    include_live_display=True,
    include_show_metrics=True,
    include_show_streaming=True,
)
async def wait(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    show_kubectl: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    live_display: bool = True,
    show_metrics: MetricsDisplayMode | None = None,
    show_streaming: bool | None = None,
) -> None:
    """Wait for a specific condition on one or more resources."""
    cmd_result = await run_wait_command(
        resource=resource,
        args=args,
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        show_kubectl=show_kubectl,
        model=model,
        freeze_memory=freeze_memory,
        unfreeze_memory=unfreeze_memory,
        live_display=live_display,
        show_metrics=show_metrics,
        show_streaming=show_streaming,
    )
    handle_result(cmd_result)


@cli.command(context_settings={"ignore_unknown_options": True})
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@common_command_options(
    include_show_kubectl=True,
    include_live_display=True,
    include_show_metrics=True,
    include_show_streaming=True,
)
async def port_forward(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    show_kubectl: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    live_display: bool = True,
    show_metrics: MetricsDisplayMode | None = None,
    show_streaming: bool | None = None,
) -> None:
    """Forward one or more local ports to a pod, service, or deployment."""
    cmd_result = await run_port_forward_command(
        resource=resource,
        args=args,
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        show_kubectl=show_kubectl,
        model=model,
        freeze_memory=freeze_memory,
        unfreeze_memory=unfreeze_memory,
        live_display=live_display,
        show_metrics=show_metrics,
        show_streaming=show_streaming,
    )
    handle_result(cmd_result)


@cli.command(context_settings={"ignore_unknown_options": True})
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@common_command_options(
    include_show_kubectl=True, include_show_metrics=True, include_show_streaming=True
)
async def diff(
    resource: str,
    args: tuple[str, ...],
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool,
    unfreeze_memory: bool,
    show_kubectl: bool | None = None,
    show_metrics: MetricsDisplayMode | None = None,
    show_streaming: bool | None = None,
) -> None:
    """Diff configurations between local files/stdin and the live cluster state."""
    result = await run_diff_command(
        resource=resource,
        args=args,
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        show_kubectl=show_kubectl,
        model=model,
        freeze_memory=freeze_memory,
        unfreeze_memory=unfreeze_memory,
        show_metrics=show_metrics,
        show_streaming=show_streaming,
    )
    handle_result(result)


@cli.command(context_settings={"ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED, required=True)
@common_command_options(include_show_kubectl=True)
async def apply(
    args: tuple[str, ...],
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool,
    unfreeze_memory: bool,
    show_kubectl: bool | None = None,
    show_metrics: MetricsDisplayMode | None = None,
    show_streaming: bool | None = None,
) -> None:
    """Apply a configuration to a resource by filename or stdin."""
    result = await run_apply_command(
        args=args,
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        show_kubectl=show_kubectl,
        model=model,
        freeze_memory=freeze_memory,
        unfreeze_memory=unfreeze_memory,
        show_metrics=show_metrics,
        show_streaming=show_streaming,
    )
    handle_result(result)


def handle_result(result: Result) -> None:
    """Handle the result of a command, print output, and exit."""
    exit_code: int = 0
    if isinstance(result, Success):
        if result.data:
            # Ensure data is a string before printing
            data_to_print = result.data
            if not isinstance(data_to_print, str):
                # Attempt to convert to string, or use a placeholder
                try:
                    data_to_print = str(data_to_print)
                except Exception:
                    data_to_print = "[unprintable data]"
            console_manager.print(data_to_print)

        # Prioritize original_exit_code if it exists and is an int
        if hasattr(result, "original_exit_code") and isinstance(
            result.original_exit_code, int
        ):
            exit_code = result.original_exit_code
        else:
            exit_code = 0  # Default for Success
        logger.debug(f"Success result, final exit_code: {exit_code}")

    elif isinstance(result, Error):
        console_manager.print_error(result.error)
        # if result.details: # result.details is not a valid attribute of Error
        #     # Assuming details is already formatted for printing
        #     console_manager.print_error_details(str(result.details))

        # Prioritize original_exit_code if it exists and is an int
        if hasattr(result, "original_exit_code") and isinstance(
            result.original_exit_code, int
        ):
            exit_code = result.original_exit_code
        else:
            exit_code = 1  # Default for Error
        logger.debug(f"Error result, final exit_code: {exit_code}")

    sys.exit(exit_code)


def main() -> None:
    """Main entry point that wraps the CLI and handles all exceptions centrally."""
    import click as regular_click  # Import regular click for Exit exceptions

    try:
        # Initialize logging first
        init_logging()
        # Run the CLI with standalone_mode=False to handle exceptions ourselves
        cli(standalone_mode=False)
    except (click.exceptions.Exit, regular_click.exceptions.Exit) as e:
        # Both asyncclick.Exit and click.Exit can be raised by --help, --version, etc.
        # Exit normally with the code from the exception
        sys.exit(e.exit_code)
    except Exception as e:
        # Centralized exception handling - print user-friendly errors only
        handle_exception(e)
        sys.exit(1)


if __name__ == "__main__":
    main()
