"""
Command-line interface for vibectl.

Provides a vibes-based alternative to kubectl, using AI to generate human-friendly
summaries of Kubernetes resources. Each command aims to make cluster management
more intuitive while preserving access to raw kubectl output when needed.
"""

import datetime
import sys
from collections.abc import Callable

import click
import llm
from rich.panel import Panel
from rich.table import Table

from vibectl.memory import (
    clear_memory,
    disable_memory,
    enable_memory,
    get_memory,
    set_memory,
)
from vibectl.subcommands.auto_cmd import run_auto_command, run_semiauto_command
from vibectl.subcommands.cluster_info_cmd import run_cluster_info_command
from vibectl.subcommands.create_cmd import run_create_command
from vibectl.subcommands.delete_cmd import run_delete_command
from vibectl.subcommands.describe_cmd import run_describe_command
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
from .config import Config
from .console import console_manager
from .logutil import init_logging, logger
from .model_adapter import validate_model_key_on_startup
from .prompt import memory_fuzzy_update_prompt
from .types import Error, Result, Success
from .utils import handle_exception

# Constants
MAX_TOKEN_LIMIT = 10000
LOGS_TRUNCATION_RATIO = 3
DEFAULT_MODEL = "claude-3.7-sonnet"
DEFAULT_SHOW_RAW_OUTPUT = False
DEFAULT_SHOW_VIBE = True
DEFAULT_SUPPRESS_OUTPUT_WARNING = False

# Current datetime for version command
CURRENT_DATETIME = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# --- Common Option Decorator ---
def common_command_options(
    include_show_kubectl: bool = False,
    include_live_display: bool = False,
    include_yes: bool = False,
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
        for option in reversed(options):
            f = option(f)
        return f

    return decorator


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
def cli(ctx: click.Context, log_level: str | None, verbose: bool) -> None:
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
    model_name = cfg.get("model", DEFAULT_MODEL)
    validation_warning = validate_model_key_on_startup(model_name)
    if validation_warning and ctx.invoked_subcommand not in ["config", "help"]:
        console_manager.print_warning(validation_warning)
        logger.warning(f"Model validation warning: {validation_warning}")

    # Show welcome message if no subcommand is invoked
    if ctx.invoked_subcommand is None:
        logger.info("No subcommand invoked; showing welcome message.")
        console_manager.print("Checking cluster vibes...")
        console_manager.print_vibe_welcome()


@cli.command(context_settings={"ignore_unknown_options": True})
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@common_command_options(include_show_kubectl=True)
def get(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool,
    unfreeze_memory: bool,
    show_kubectl: bool | None = None,
) -> None:
    """Get resources in a concise format."""
    result = run_get_command(
        resource,
        args,
        show_raw_output,
        show_vibe,
        show_kubectl,
        model,
        freeze_memory,
        unfreeze_memory,
    )
    handle_result(result)


@cli.command()
@click.argument("resource")
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@common_command_options(include_show_kubectl=True)
def describe(
    resource: str,
    args: tuple,
    show_raw_output: bool | None = None,
    show_vibe: bool | None = None,
    model: str | None = None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    show_kubectl: bool | None = None,
) -> None:
    """Show details of a specific resource or group of resources."""
    result = run_describe_command(
        resource,
        args,
        show_raw_output,
        show_vibe,
        show_kubectl,
        model,
        freeze_memory,
        unfreeze_memory,
    )
    handle_result(result)


@cli.command()
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@common_command_options(include_show_kubectl=True)
def logs(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    show_kubectl: bool | None = None,
) -> None:
    """Show logs for a container in a pod."""
    result = run_logs_command(
        resource,
        args,
        show_raw_output,
        show_vibe,
        show_kubectl,
        model,
        freeze_memory,
        unfreeze_memory,
    )
    handle_result(result)


@cli.command()
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@common_command_options(include_show_kubectl=True)
def create(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    show_kubectl: bool | None = None,
) -> None:
    """Create a resource."""
    result = run_create_command(
        resource,
        args,
        show_raw_output,
        show_vibe,
        show_kubectl,
        model,
        freeze_memory,
        unfreeze_memory,
    )
    handle_result(result)


@cli.command()
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@common_command_options(include_show_kubectl=True, include_yes=True)
def delete(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    show_kubectl: bool | None = None,
    yes: bool = False,
) -> None:
    """Delete a resource.

    Removes resources from the cluster.
    Use --yes or -y to skip confirmation prompt for non-interactive usage.
    """
    result = run_delete_command(
        resource=resource,
        args=args,
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        model=model,
        freeze_memory=freeze_memory,
        unfreeze_memory=unfreeze_memory,
        show_kubectl=show_kubectl,
        yes=yes,
    )
    handle_result(result)


@cli.command(context_settings={"ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def just(args: tuple) -> None:
    """Pass commands directly to kubectl.

    Passes all arguments directly to kubectl without any processing.
    Useful for commands not yet supported by vibectl or when you want
    to use kubectl directly.

    Example:
        vibectl just get pods  # equivalent to: kubectl get pods
    """
    result = run_just_command(args)
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
def instructions_set(instructions_text: str | None = None, edit: bool = False) -> None:
    """Set custom instructions for LLM responses."""
    try:
        cfg = Config()

        # If --edit flag is used, open an editor
        if edit:
            instructions_text = click.edit(cfg.get("custom_instructions", ""))
            if instructions_text is None:
                console_manager.print_warning(
                    "Editor was closed without saving. Instructions not updated."
                )
                return

        # If no text provided and not editing, try to read from stdin
        if instructions_text is None:
            import sys

            if not sys.stdin.isatty():
                stdin_content = sys.stdin.read()
                if stdin_content.strip():
                    instructions_text = stdin_content

        # No text provided and no editor flag and nothing from stdin
        if not instructions_text:
            console_manager.print_error(
                "Instructions cannot be empty. Use --edit or provide instructions text."
            )
            sys.exit(1)

        # Save the instructions
        cfg.set("custom_instructions", instructions_text)
        cfg.save()
        console_manager.print_success("Custom instructions saved")
    except Exception as e:
        handle_exception(e)


@instructions.command(name="show")
def instructions_show() -> None:
    """Show currently set custom instructions."""
    cfg = Config()
    instructions_text = cfg.get("custom_instructions", "")

    if instructions_text:
        console_manager.print_note("Custom instructions:")
        console_manager.print(instructions_text)
    else:
        console_manager.print_note("No custom instructions set")


@instructions.command()
def clear() -> None:
    """Clear custom instructions."""
    try:
        cfg = Config()
        cfg.set("custom_instructions", "")
        cfg.save()
        console_manager.print_success("Custom instructions cleared")
    except Exception as e:
        handle_exception(e)


@cli.group()
def theme() -> None:
    """Manage console theme."""
    pass


@theme.command()
def list() -> None:
    """List available themes."""
    try:
        themes = console_manager.get_available_themes()
        console_manager.print_note("Available themes:")
        for theme_name in themes:
            console_manager.print(f"  - {theme_name}")
    except Exception as e:
        handle_exception(e)
        return


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
        # Verify theme exists
        available_themes = console_manager.get_available_themes()
        if theme_name not in available_themes:
            msg = (
                f"Invalid theme '{theme_name}'. Available themes: "
                f"{', '.join(available_themes)}"
            )
            console_manager.print_error(msg)
            sys.exit(1)

        # Save theme in config
        cfg = Config()
        cfg.set("theme", theme_name)
        cfg.save()

        # Apply theme
        console_manager.set_theme(theme_name)
        console_manager.print_success(f"Theme set to {theme_name}")
    except Exception as e:
        handle_exception(e)
        return


@cli.command()
@click.argument("request", required=False)
@common_command_options(include_show_kubectl=True, include_yes=True)
def vibe(
    request: str | None,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    show_kubectl: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    yes: bool = False,
) -> None:
    """Run a command based on your natural language request."""
    try:
        result = run_vibe_command(
            request=request,
            show_raw_output=show_raw_output,
            show_vibe=show_vibe,
            show_kubectl=show_kubectl,
            model=model,
            freeze_memory=freeze_memory,
            unfreeze_memory=unfreeze_memory,
            yes=yes,
        )
        handle_result(result)
    except Exception as e:
        # Always print the error message to console if available
        if hasattr(e, "error") and e.error:
            console_manager.print_error(e.error)
        # Otherwise, print the standard exception string representation if non-empty
        elif str(e):
            console_manager.print_error(str(e))
        # As a last resort if str(e) is empty
        else:
            console_manager.print_error("An unexpected error occurred.")

        # Use Click's abort mechanism to exit with non-zero status
        raise click.Abort() from e


@cli.command()
@click.argument("request", required=False)
@common_command_options(include_show_kubectl=True)
@click.option(
    "--interval", "-i", type=int, default=5, help="Seconds between loop iterations"
)
@click.option(
    "--limit", "-l", type=int, default=None, help="Maximum number of iterations to run"
)
def auto(
    request: str | None,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    show_kubectl: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    interval: int = 5,
    limit: int | None = None,
) -> None:
    """Loop vibectl vibe commands automatically."""
    try:
        result = run_auto_command(
            request=request,
            show_raw_output=show_raw_output,
            show_vibe=show_vibe,
            show_kubectl=show_kubectl,
            model=model,
            freeze_memory=freeze_memory,
            unfreeze_memory=unfreeze_memory,
            yes=True,
            interval=interval,
            semiauto=False,
            limit=limit,
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
def semiauto(
    request: str | None,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    show_kubectl: bool | None,
    model: str | None,
    freeze_memory: bool,
    unfreeze_memory: bool,
    limit: int | None = None,
) -> None:
    """Run vibe command in semiauto mode with manual confirmation.

    This is a convenience wrapper around 'vibectl auto --semiauto'.
    In semiauto mode, you will need to confirm each step before it executes.
    This can be useful for learning or when working with complex requests.
    """
    try:
        result = run_semiauto_command(
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
def events(
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    show_kubectl: bool | None = None,
) -> None:
    """List events in the cluster."""
    result = run_events_command(
        args=args,
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        show_kubectl=show_kubectl,
        model=model,
        freeze_memory=freeze_memory,
        unfreeze_memory=unfreeze_memory,
    )
    handle_result(result)


@cli.command()
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@common_command_options(include_show_kubectl=True)
def version(
    args: tuple,
    show_raw_output: bool | None = None,
    show_vibe: bool | None = None,
    model: str | None = None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    show_kubectl: bool | None = None,
) -> None:
    """Show Kubernetes version information."""
    result = run_version_command(
        args,
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        model=model,
        freeze_memory=freeze_memory,
        unfreeze_memory=unfreeze_memory,
        show_kubectl=show_kubectl,
    )
    handle_result(result)


@cli.command()
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@common_command_options(include_show_kubectl=True)
def cluster_info(
    args: tuple,
    show_raw_output: bool | None = None,
    show_vibe: bool | None = None,
    model: str | None = None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    show_kubectl: bool | None = None,
) -> int | None:
    """Display cluster info."""
    result = run_cluster_info_command(
        args=args,
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        model=model,
        freeze_memory=freeze_memory,
        unfreeze_memory=unfreeze_memory,
        show_kubectl=show_kubectl,
    )
    handle_result(result)
    return 0


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
        # Get the current memory
        current_memory = get_memory()

        # Join the text parts to handle multi-word input
        update_text_str = " ".join(update_text)

        # Get the model name from config if not specified
        cfg = Config()
        model_name = model or cfg.get("model", DEFAULT_MODEL)

        # Get the model
        model_instance = llm.get_model(model_name)

        # Create a prompt for the fuzzy memory update
        prompt = memory_fuzzy_update_prompt(current_memory, update_text_str, cfg)

        # Get the response
        console_manager.print_processing(f"Updating memory using {model_name}...")
        response = model_instance.prompt(prompt)
        updated_memory = response.text()

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
def scale(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    show_kubectl: bool | None = None,
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
    result = run_scale_command(
        resource=resource,
        args=args,
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        show_kubectl=show_kubectl,
        model=model,
        freeze_memory=freeze_memory,
        unfreeze_memory=unfreeze_memory,
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
) -> None:
    """Manage rollouts of deployments, statefulsets, and daemonsets."""
    if ctx.invoked_subcommand is not None:
        return
    console_manager.print_error(
        "Missing subcommand for rollout. "
        "Use one of: status, history, undo, restart, pause, resume"
    )
    sys.exit(1)


def _rollout_common(
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
) -> None:
    result = run_rollout_command(
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
    )
    handle_result(result)


@rollout.command(context_settings={"ignore_unknown_options": True})
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@common_command_options(include_show_kubectl=True)
def status(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    show_kubectl: bool | None = None,
) -> None:
    _rollout_common(
        subcommand="status",
        resource=resource,
        args=args,
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        model=model,
        freeze_memory=freeze_memory,
        unfreeze_memory=unfreeze_memory,
        show_kubectl=show_kubectl,
    )


@rollout.command(context_settings={"ignore_unknown_options": True})
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@common_command_options(include_show_kubectl=True)
def history(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    show_kubectl: bool | None = None,
) -> None:
    _rollout_common(
        subcommand="history",
        resource=resource,
        args=args,
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        model=model,
        freeze_memory=freeze_memory,
        unfreeze_memory=unfreeze_memory,
        show_kubectl=show_kubectl,
    )


@rollout.command(context_settings={"ignore_unknown_options": True})
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@common_command_options(include_show_kubectl=True)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def undo(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    show_kubectl: bool | None = None,
    yes: bool = False,
) -> None:
    _rollout_common(
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
    )


@rollout.command(context_settings={"ignore_unknown_options": True})
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@common_command_options(include_show_kubectl=True)
def restart(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    show_kubectl: bool | None = None,
) -> None:
    _rollout_common(
        subcommand="restart",
        resource=resource,
        args=args,
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        model=model,
        freeze_memory=freeze_memory,
        unfreeze_memory=unfreeze_memory,
        show_kubectl=show_kubectl,
    )


@rollout.command(context_settings={"ignore_unknown_options": True})
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@common_command_options(include_show_kubectl=True)
def pause(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    show_kubectl: bool | None = None,
) -> None:
    _rollout_common(
        subcommand="pause",
        resource=resource,
        args=args,
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        model=model,
        freeze_memory=freeze_memory,
        unfreeze_memory=unfreeze_memory,
        show_kubectl=show_kubectl,
    )


@rollout.command(context_settings={"ignore_unknown_options": True})
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@common_command_options(include_show_kubectl=True)
def resume(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    show_kubectl: bool | None = None,
) -> None:
    _rollout_common(
        subcommand="resume",
        resource=resource,
        args=args,
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        model=model,
        freeze_memory=freeze_memory,
        unfreeze_memory=unfreeze_memory,
        show_kubectl=show_kubectl,
    )


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
def wait(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    show_kubectl: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    live_display: bool = True,
) -> None:
    """Wait for a specific condition on one or more resources.

    Shows a live spinner with elapsed time while waiting for resources
    to meet their specified conditions.
    """
    result = run_wait_command(
        resource=resource,
        args=args,
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        show_kubectl=show_kubectl,
        model=model,
        freeze_memory=freeze_memory,
        unfreeze_memory=unfreeze_memory,
        live_display=live_display,
    )
    handle_result(result)


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
def port_forward(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    show_kubectl: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    live_display: bool = True,
) -> None:
    """Forward one or more local ports to a pod, service, or deployment.

    Shows a live display with connection status and elapsed time while
    forwarding ports between your local system and Kubernetes resources.
    """
    result = run_port_forward_command(
        resource=resource,
        args=args,
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        show_kubectl=show_kubectl,
        model=model,
        freeze_memory=freeze_memory,
        unfreeze_memory=unfreeze_memory,
        live_display=live_display,
    )
    handle_result(result)


def handle_result(result: Result) -> None:
    """
    Handle a Result (Success or Error): print errors and exit with the correct code.
    Use in CLI handlers to reduce boilerplate.
    """
    if isinstance(result, Success):
        # Check if we should terminate execution
        if not result.continue_execution:
            # This is a normal exit (like the user choosing "Exit" in semiauto mode)
            logger.info(f"Normal termination requested: {result.message}")
            sys.exit(0)
        return  # Normal exit, continue
    elif isinstance(result, Error):
        # Always print the error message to console if available
        if hasattr(result, "error") and result.error:
            console_manager.print_error(result.error)
        # Otherwise, print the standard exception string representation
        elif str(result):
            console_manager.print_error(str(result))

        # Use Click's abort mechanism to exit with non-zero status
        raise click.Abort()


def main() -> None:
    """
    Run the CLI application.
    Unhandled exceptions are shown as user-friendly errors.
    Tracebacks are only shown if VIBECTL_TRACEBACK=1 or log level is DEBUG.
    """
    try:
        exit_code = cli(standalone_mode=False)
        sys.exit(exit_code or 0)
    except KeyboardInterrupt:
        console_manager.print_keyboard_interrupt()
        sys.exit(1)
    except Exception as e:
        handle_exception(e)


if __name__ == "__main__":
    main()
