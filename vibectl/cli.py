"""
Command-line interface for vibectl.

Provides a vibes-based alternative to kubectl, using AI to generate human-friendly
summaries of Kubernetes resources. Each command aims to make cluster management
more intuitive while preserving access to raw kubectl output when needed.
"""

import datetime
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
from vibectl.subcommands.check_cmd import run_check_command as run_check_subcommand
from vibectl.subcommands.cluster_info_cmd import run_cluster_info_command
from vibectl.subcommands.create_cmd import run_create_command
from vibectl.subcommands.delete_cmd import run_delete_command
from vibectl.subcommands.describe_cmd import run_describe_command
from vibectl.subcommands.diff_cmd import run_diff_command
from vibectl.subcommands.events_cmd import run_events_command
from vibectl.subcommands.get_cmd import run_get_command
from vibectl.subcommands.just_cmd import run_just_command
from vibectl.subcommands.logs_cmd import run_logs_command
from vibectl.subcommands.port_forward_cmd import run_port_forward_command
from vibectl.subcommands.rollout_cmd import run_rollout_command
from vibectl.subcommands.scale_cmd import run_scale_command
from vibectl.subcommands.version_cmd import run_version_command
from vibectl.subcommands.vibe_cmd import run_vibe_command
from vibectl.subcommands.wait_cmd import run_wait_command

from . import __version__
from .config import DEFAULT_CONFIG, Config
from .console import console_manager
from .logutil import init_logging, logger
from .model_adapter import get_model_adapter, validate_model_key_on_startup
from .prompt import memory_fuzzy_update_prompt
from .types import (
    Error,
    Fragment,
    Result,
    Success,
    UserFragments,
)
from .utils import handle_exception

# Current datetime for version command
CURRENT_DATETIME = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# --- Common Option Decorator ---
def common_command_options(
    include_show_kubectl: bool = False,
    include_live_display: bool = False,
    include_yes: bool = False,
    include_show_metrics: bool = True,
) -> Callable:
    """Decorator to DRY out common CLI options for subcommands."""

    def decorator(f: Callable) -> Callable:
        options = [
            click.option(
                "--show-raw-output/--no-show-raw-output", is_flag=True, default=None
            ),
            click.option("--show-vibe/--no-show-vibe", is_flag=True, default=None),
            click.option("--model", default=None, help="The LLM model to use"),
            click.option(
                "--freeze-memory",
                is_flag=True,
                help="Prevent memory updates for this command",
            ),
            click.option(
                "--unfreeze-memory",
                is_flag=True,
                help="Enable memory updates for this command",
            ),
        ]
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
                    "--show-metrics/--no-show-metrics",
                    is_flag=True,
                    default=None,
                    help="Show LLM latency and token usage metrics",
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
    import os

    if verbose:
        os.environ["VIBECTL_LOG_LEVEL"] = "DEBUG"
    elif log_level:
        os.environ["VIBECTL_LOG_LEVEL"] = log_level.upper()
    init_logging()
    logger.info("vibectl CLI started")
    # Initialize the console manager with the configured theme
    try:
        cfg = Config()
        theme_name = cfg.get("theme", "default")
        console_manager.set_theme(theme_name)
    except Exception as e:
        logger.warning(f"Failed to set theme: {e}")
        # Fallback to default in case of any issues (helpful for tests)
        pass

    # Validate model configuration on startup - outside try/except for testing
    cfg = Config()  # Get a fresh config instance
    model_name = cfg.get("model", DEFAULT_CONFIG["model"])
    validation_warning = validate_model_key_on_startup(model_name)
    if validation_warning and ctx.invoked_subcommand not in ["config", "help"]:
        console_manager.print_warning(validation_warning)
        logger.warning(f"Model validation warning: {validation_warning}")

    # Show welcome message if no subcommand is invoked
    show_welcome_if_no_subcommand(ctx)


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
    show_metrics: bool | None = None,
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
    show_metrics: bool | None = None,
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
    show_metrics: bool | None = None,
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
    )
    handle_result(result)


# --- Helper for standard create logic ---
def _create_command_logic(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    show_kubectl: bool | None = None,
    show_metrics: bool | None = None,
) -> Result:
    """Handles the logic for standard (non-vibe) create commands."""
    # Call the synchronous runner function from the subcommand module
    return run_create_command(
        resource=resource,
        args=args,
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        show_kubectl=show_kubectl,
        model=model,
        freeze_memory=freeze_memory,
        unfreeze_memory=unfreeze_memory,
        show_metrics=show_metrics,
    )


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
    show_metrics: bool | None = None,
) -> None:
    """Create resources from a file or stdin."""
    if resource == "vibe":
        if not args:
            msg = "Missing request after 'vibe'. Usage: vibectl create vibe <request>"
            console_manager.print_error(msg)
            sys.exit(1)
            return
        vibe_request = " ".join(args)
        result = await run_vibe_command(
            request=vibe_request,
            show_raw_output=show_raw_output,
            show_vibe=show_vibe,
            show_kubectl=show_kubectl,
            model=model,
            freeze_memory=freeze_memory,
            unfreeze_memory=unfreeze_memory,
            show_metrics=show_metrics,
        )
    else:
        result = _create_command_logic(
            resource=resource,
            args=args,
            show_raw_output=show_raw_output,
            show_vibe=show_vibe,
            show_kubectl=show_kubectl,
            model=model,
            freeze_memory=freeze_memory,
            unfreeze_memory=unfreeze_memory,
            show_metrics=show_metrics,
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
    show_metrics: bool | None = None,
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

    Examples:
        vibectl config set theme dark
        vibectl config set kubeconfig ~/.kube/my-config
        vibectl config set show_raw_output true
    """
    try:
        cfg = Config()
        cfg.set(key, value)
        cfg.save()
        console_manager.print_success(f"Configuration {key} set to {value}")
    except ValueError as e:
        handle_exception(e)


@config.command()
def show() -> None:
    """Show all configuration values.

    Examples:
        vibectl config show
    """
    try:
        cfg = Config()
        config_data = cfg.get_all()

        table = Table(title="Configuration")
        table.add_column("Key")
        table.add_column("Value", style="green")

        for key, value in config_data.items():
            table.add_row(key, str(value))

        console_manager.safe_print(console_manager.console, table)
    except Exception as e:
        handle_exception(e)


@config.command()
@click.argument("key")
def unset(key: str) -> None:
    """Unset a configuration value, resetting it to default.

    Examples:
        vibectl config unset theme  # Reset theme to default
        vibectl config unset kubeconfig  # Reset kubeconfig to default
    """
    try:
        cfg = Config()
        cfg.unset(key)
        console_manager.print_success(f"Configuration {key} reset to default")
    except ValueError as e:
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
    current_instructions = cfg.get("custom_instructions", "")

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
                console_manager.print_error(
                    "Error: No instructions provided via stdin."
                )
                # Use handle_exception for consistency, though it exits
                handle_exception(ValueError("No instructions provided via stdin"))
                return
            logger.info("Instructions received from stdin")
        else:
            console_manager.print_error("Error: No instructions text provided.")
            console_manager.print_note("Use --edit to open an editor or pipe input.")
            # Use handle_exception for consistency
            handle_exception(ValueError("No instructions text provided."))
            return

    try:
        cfg.set("custom_instructions", instructions_text)
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
        instructions_text = cfg.get("custom_instructions", "")
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
        cfg.set("custom_instructions", "")
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
    cfg.set("theme", theme_name)
    cfg.save()  # Save the config after setting
    console_manager.print_success(f"Theme set to '{theme_name}'.")


@cli.group()
def theme() -> None:
    """Manage console theme settings."""
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
    """
    Set the theme for the console output.

    Examples:
        vibectl theme set dark
        vibectl theme set light
    """
    try:
        # Call the separated logic function
        _set_theme_logic(theme_name)
    except Exception as e:
        # Catch potential ValueError from helper or save errors
        handle_exception(e)


@cli.command()
@click.argument("request", required=False)
@common_command_options(include_show_kubectl=True, include_yes=True)
@click.option(
    "--interval", "-i", type=int, default=5, help="Seconds between loop iterations"
)
@click.option(
    "--limit", "-l", type=int, default=None, help="Maximum number of iterations to run"
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
    show_metrics: bool | None = None,
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
            yes=yes,
            interval=interval,
            semiauto=False,
            limit=limit,
            show_metrics=show_metrics,
        )
        handle_result(result)
    except Exception as e:
        # Always print the error message to console if available
        if hasattr(e, "error") and e.error:
            console_manager.print_error(e.error)
        # Otherwise, print the standard exception string representation
        elif str(e):
            console_manager.print_error(str(e))

        # Use Click's abort mechanism to exit with non-zero status
        raise click.Abort() from e


@cli.command()
@click.argument("request", required=False)
@common_command_options(include_show_kubectl=True)
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
    show_metrics: bool | None = None,
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
            # No exit_on_error parameter needed - defaults to False
        )

        # Check for error result (should only happen with programmatic API)
        if not isinstance(result, Success):
            # Always print the error message to console if available
            if hasattr(result, "error") and result.error:
                console_manager.print_error(result.error)
            else:
                console_manager.print_error(f"Unknown error occurred: {result!s}")

            # Use Click's abort mechanism to exit with non-zero status
            # This is only reached if there's a catastrophic error that couldn't be
            # handled gracefully within the semiauto command itself
            raise click.Abort() from None
    except Exception as e:
        # Always print the error message to console if available
        if hasattr(e, "error") and e.error:
            console_manager.print_error(e.error)
        else:
            console_manager.print_error(f"Unknown error occurred: {e!s}")

        # Use Click's abort mechanism to exit with non-zero status
        # This is only reached if there's a catastrophic error that couldn't be
        # handled gracefully within the semiauto command itself
        raise click.Abort() from e


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
    show_metrics: bool | None = None,
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
    )
    handle_result(result)


@cli.command()
@click.argument("request", required=False)
@common_command_options(include_show_kubectl=True, include_yes=True)
@click.option(
    "--show-metrics/--no-show-metrics",
    is_flag=True,
    default=None,
    help="Show LLM latency and token usage metrics",
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
    show_metrics: bool | None = None,
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
        show_metrics=show_metrics,  # Pass show_metrics
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
    show_metrics: bool | None = None,
    yes: bool = False,
) -> None:
    """Show Kubernetes version information."""
    result = await run_version_command(
        args=args,
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        model=model,
        freeze_memory=freeze_memory,
        unfreeze_memory=unfreeze_memory,
        show_kubectl=show_kubectl,
        show_metrics=show_metrics,
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
    show_metrics: bool | None = None,
    yes: bool = False,
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
def memory_update(update_text: tuple, model: str | None = None) -> None:
    """Update memory with additional information or context.

    Uses LLM to intelligently update memory with new information
    while preserving important existing context.
    """
    try:
        cfg = Config()

        # Get the current memory
        current_memory = get_memory(cfg)

        # Join the text parts to handle multi-word input
        update_text_str = " ".join(update_text)

        # Get the model name from config if not specified
        # Use .get() for model, falling back to DEFAULT_CONFIG
        model_name_to_use = model or cfg.get("model", DEFAULT_CONFIG["model"])

        # Get the model adapter and model instance
        model_adapter = get_model_adapter(cfg)
        model_instance = model_adapter.get_model(model_name_to_use)

        # Create fragments for the fuzzy memory update
        system_fragments, user_fragments_template = memory_fuzzy_update_prompt(
            current_memory=current_memory, update_text=update_text_str, config=cfg
        )

        # ormat the user_fragments_template here.
        filled_user_fragments = []
        for template_str in user_fragments_template:
            try:
                # Try to format with update_text
                filled_user_fragments.append(
                    Fragment(template_str.format(update_text=update_text_str))
                )
            except KeyError:
                # If {update_text} isn't in a particular template piece, use it as is.
                filled_user_fragments.append(Fragment(template_str))

        console_manager.print_processing(
            f"Updating memory using {model_name_to_use}..."
        )

        # Execute using the model adapter
        updated_memory, _ = model_adapter.execute_and_log_metrics(
            model=model_instance,
            system_fragments=system_fragments,
            user_fragments=UserFragments(filled_user_fragments),
        )

        # Set the updated memory
        set_memory(updated_memory, cfg)
        console_manager.print_success("Memory updated")

        # Display the updated memory
        console_manager.safe_print(
            console_manager.console,
            Panel(
                updated_memory,
                title="Updated Memory Content",
                border_style="blue",
                expand=False,
            ),
        )
    except Exception as e:
        handle_exception(e)


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
    show_metrics: bool | None = None,
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
    show_metrics: bool | None = None,
) -> None:
    """Manage rollouts of deployments, statefulsets, and daemonsets."""
    if ctx.invoked_subcommand is not None:
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
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool,
    unfreeze_memory: bool,
    show_kubectl: bool | None,
    yes: bool = False,
    show_metrics: bool | None = None,
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
    show_metrics: bool | None = None,
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
    show_metrics: bool | None = None,
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
    show_metrics: bool | None = None,
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
    show_metrics: bool | None = None,
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
    show_metrics: bool | None = None,
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
    show_metrics: bool | None = None,
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


# Explicitly add commands if decorator registration is failing in tests
# This is a workaround and might indicate a deeper issue
if hasattr(rollout, "add_command"):
    rollout.add_command(undo)  # type: ignore[attr-defined]
    rollout.add_command(restart)  # type: ignore[attr-defined]
    rollout.add_command(pause)  # type: ignore[attr-defined]
    rollout.add_command(resume)  # type: ignore[attr-defined]


@cli.command(context_settings={"ignore_unknown_options": True})
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@common_command_options(include_show_kubectl=True)
@click.option(
    "--live-display/--no-live-display",
    is_flag=True,
    default=True,
    help="Show a live spinner with elapsed time during waiting",
)
@click.option(
    "--show-metrics/--no-show-metrics",
    is_flag=True,
    default=None,
    help="Show LLM latency and token usage metrics",
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
    show_metrics: bool | None = None,
) -> None:
    """Wait for a specific condition on one or more resources.

    Shows a live spinner with elapsed time while waiting for resources
    to meet their specified conditions.
    """
    # Await the call to the async runner function
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
    )
    # Pass the awaited result to handle_result
    handle_result(cmd_result)


@cli.command(context_settings={"ignore_unknown_options": True})
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@common_command_options(include_show_kubectl=True)
@click.option(
    "--live-display/--no-live-display",
    is_flag=True,
    default=True,
    help="Show a live display with connection status during port forwarding",
)
@click.option(
    "--show-metrics/--no-show-metrics",
    is_flag=True,
    default=None,
    help="Show LLM latency and token usage metrics",
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
    show_metrics: bool | None = None,
) -> None:
    """Forward one or more local ports to a pod, service, or deployment.

    Shows a live display with connection status and elapsed time while
    forwarding ports between your local system and Kubernetes resources.
    """
    # Await the call to the async runner function
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
    )
    # Pass the awaited result to handle_result
    handle_result(cmd_result)


@cli.command(context_settings={"ignore_unknown_options": True})
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@common_command_options(include_show_kubectl=True)
async def diff(
    resource: str,
    args: tuple[str, ...],
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool,
    unfreeze_memory: bool,
    show_kubectl: bool | None = None,
    show_metrics: bool | None = None,
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
    )
    handle_result(result)


@cli.command(
    "apply",
    help="Apply a configuration to a resource by filename or stdin",
    context_settings={
        "ignore_unknown_options": True
    },  # Allow arbitrary args for kubectl
)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.option("--show-raw-output", is_flag=True, help="Show raw kubectl output")
@click.option("--show-vibe", is_flag=True, help="Show vibe output")
@click.option("--show-kubectl", is_flag=True, help="Show kubectl command executed")
@click.option("--model", help="Specify the LLM model to use")
@click.option("--freeze-memory", is_flag=True, help="Freeze memory (no new updates)")
@click.option(
    "--unfreeze-memory", is_flag=True, help="Unfreeze memory (allow new updates)"
)
@click.option("--show-metrics", is_flag=True, help="Show LLM metrics")
@click.pass_context
async def apply_command_wrapper(
    ctx: click.Context,
    args: tuple[str, ...],
    show_raw_output: bool | None,
    show_vibe: bool | None,
    show_kubectl: bool | None,
    model: str | None,
    freeze_memory: bool,
    unfreeze_memory: bool,
    show_metrics: bool | None,
) -> None:
    """Wrapper for the apply command."""
    result = await run_apply_command(
        args=args,
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        show_kubectl=show_kubectl,
        model=model,
        freeze_memory=freeze_memory,
        unfreeze_memory=unfreeze_memory,
        show_metrics=show_metrics,
    )
    handle_result(result)


# Check command
@cli.command(
    "check",
    help="Evaluate a predicate about the cluster state using LLM.",
    context_settings={
        "ignore_unknown_options": False
    },  # No passthrough for check args yet
)
@click.argument("predicate", nargs=1, type=click.STRING)
@click.option(
    "--show-raw-output", is_flag=True, help="Show raw LLM plan/output (if any)"
)
@click.option(
    "--show-vibe",
    is_flag=True,
    default=True,
    help="Show LLM reasoning/decision (default: True)",
)
@click.option(
    "--show-kubectl", is_flag=True, help="Show kubectl command if LLM plans one"
)
@click.option("--model", help="Specify the LLM model to use")
@click.option("--freeze-memory", is_flag=True, help="Freeze memory (no new updates)")
@click.option(
    "--unfreeze-memory", is_flag=True, help="Unfreeze memory (allow new updates)"
)
@click.option("--show-metrics", is_flag=True, help="Show LLM metrics")
# TODO: Add --max-iterations, --timeout, --token-budget for Phase 2
@click.pass_context
async def check_command_wrapper(
    ctx: click.Context,
    predicate: str,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    show_kubectl: bool | None,
    model: str | None,
    freeze_memory: bool,
    unfreeze_memory: bool,
    show_metrics: bool | None,
) -> None:
    """Wrapper for the check command."""
    result = await run_check_subcommand(
        predicate=predicate,
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        show_kubectl=show_kubectl,
        model=model,
        freeze_memory=freeze_memory,
        unfreeze_memory=unfreeze_memory,
        show_metrics=show_metrics,
    )
    handle_result(result)


def handle_result(result: Result) -> None:
    """Handle the Result of a subcommand, exiting if requested."""
    logger.info(f"handle_result received: {result!r}")
    if isinstance(result, Success):
        if result.continue_execution:
            logger.info(
                f"Continuing execution as requested by Success: {result.message}"
            )
            return

        exit_code = result.original_exit_code or 0
        # Ensure consistent single period at the end of result.message
        formatted_message = result.message.rstrip().rstrip(".")
        logger.info(
            f"Normal termination requested: {formatted_message}. "
            f"Using original_exit_code: {result.original_exit_code}, "
            f"effective_exit_code: {exit_code}."
        )
        raise click.exceptions.Exit(exit_code)

    elif isinstance(result, Error):
        # Always print the error message to the console if available
        if result.error:
            console_manager.print_error(result.error)
        elif str(result):
            console_manager.print_error(str(result))

        # Use original_exit_code if present and non-zero, otherwise default to 1
        exit_code_val = 1
        if result.original_exit_code is not None and result.original_exit_code != 0:
            exit_code_val = result.original_exit_code

        logger.info(
            f"Encountered an error. Error details: {result!r}. "
            f"Using exit_code_val: {exit_code_val}"
        )
        raise click.exceptions.Exit(exit_code_val)
