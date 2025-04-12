"""
Command-line interface for vibectl.

Provides a vibes-based alternative to kubectl, using AI to generate human-friendly
summaries of Kubernetes resources. Each command aims to make cluster management
more intuitive while preserving access to raw kubectl output when needed.
"""

import datetime
import subprocess
import sys

import click
import llm
from rich.panel import Panel
from rich.table import Table

from vibectl.memory import include_memory_in_prompt

from . import __version__
from .command_handler import (
    configure_output_flags,
    handle_command_output,
    handle_standard_command,
    handle_vibe_request,
    run_kubectl,
)
from .config import Config
from .console import console_manager
from .memory import clear_memory, disable_memory, enable_memory, get_memory, set_memory
from .model_adapter import validate_model_key_on_startup
from .prompt import (
    PLAN_CLUSTER_INFO_PROMPT,
    PLAN_CREATE_PROMPT,
    PLAN_DELETE_PROMPT,
    PLAN_DESCRIBE_PROMPT,
    PLAN_EVENTS_PROMPT,
    PLAN_GET_PROMPT,
    PLAN_LOGS_PROMPT,
    PLAN_ROLLOUT_PROMPT,
    PLAN_SCALE_PROMPT,
    PLAN_VIBE_PROMPT,
    cluster_info_prompt,
    create_resource_prompt,
    delete_resource_prompt,
    describe_resource_prompt,
    events_prompt,
    get_resource_prompt,
    logs_prompt,
    memory_fuzzy_update_prompt,
    rollout_general_prompt,
    rollout_history_prompt,
    rollout_status_prompt,
    scale_resource_prompt,
    version_prompt,
    vibe_autonomous_prompt,
)
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


@click.group(invoke_without_command=True)
@click.version_option(version=__version__)
@click.pass_context
def cli(ctx: click.Context) -> None:
    """vibectl - A vibes-based alternative to kubectl"""
    # Initialize the console manager with the configured theme
    try:
        cfg = Config()
        theme_name = cfg.get("theme", "default")
        console_manager.set_theme(theme_name)
    except Exception:
        # Fallback to default in case of any issues (helpful for tests)
        pass

    # Validate model configuration on startup - outside try/except for testing
    cfg = Config()  # Get a fresh config instance
    model_name = cfg.get("model", DEFAULT_MODEL)
    validation_warning = validate_model_key_on_startup(model_name)
    if validation_warning and ctx.invoked_subcommand not in ["config", "help"]:
        console_manager.print_warning(validation_warning)

    # Show welcome message if no subcommand is invoked
    if ctx.invoked_subcommand is None:
        console_manager.print("Checking cluster vibes...")
        console_manager.print_vibe_welcome()


@cli.command(context_settings={"ignore_unknown_options": True})
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.option("--show-raw-output/--no-show-raw-output", is_flag=True, default=None)
@click.option("--show-vibe/--no-show-vibe", is_flag=True, default=None)
@click.option(
    "--show-kubectl/--no-show-kubectl",
    is_flag=True,
    default=None,
    help="Show the kubectl command being executed",
)
@click.option("--model", default=None, help="The LLM model to use")
@click.option(
    "--freeze-memory", is_flag=True, help="Prevent memory updates for this command"
)
@click.option(
    "--unfreeze-memory", is_flag=True, help="Enable memory updates for this command"
)
def get(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    show_kubectl: bool | None,
    model: str | None,
    freeze_memory: bool,
    unfreeze_memory: bool,
) -> None:
    """Get resources in a concise format."""
    try:
        # Configure output flags
        output_flags = configure_output_flags(
            show_raw_output=show_raw_output,
            show_vibe=show_vibe,
            model=model,
            show_kubectl=show_kubectl,
        )

        # Configure memory flags
        configure_memory_flags(freeze_memory, unfreeze_memory)

        # Special case for vibe command
        if resource == "vibe":
            if len(args) < 1:
                console_manager.print_error("Missing request after 'vibe'")
                sys.exit(1)

            request = " ".join(args)
            try:
                handle_vibe_request(
                    request=request,
                    command="get",
                    plan_prompt=include_memory_in_prompt(PLAN_GET_PROMPT),
                    summary_prompt_func=get_resource_prompt,
                    output_flags=output_flags,
                )
            except Exception as e:
                handle_exception(e)
            return

        # Handle standard command
        handle_standard_command(
            command="get",
            resource=resource,
            args=args,
            output_flags=output_flags,
            summary_prompt_func=get_resource_prompt,
        )
    except Exception as e:
        handle_exception(e)


@cli.command()
@click.argument("resource")
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.option("--show-raw-output/--no-show-raw-output", is_flag=True, default=None)
@click.option("--show-vibe/--no-show-vibe", is_flag=True, default=None)
@click.option("--model", help="The LLM model to use")
@click.option(
    "--freeze-memory", is_flag=True, help="Prevent memory updates for this command"
)
@click.option(
    "--unfreeze-memory", is_flag=True, help="Enable memory updates for this command"
)
def describe(
    resource: str,
    args: tuple,
    show_raw_output: bool | None = None,
    show_vibe: bool | None = None,
    model: str | None = None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
) -> None:
    """Show details of a specific resource or group of resources."""
    try:
        # Configure output flags
        output_flags = configure_output_flags(
            show_raw_output=show_raw_output, show_vibe=show_vibe, model=model
        )

        # Configure memory flags
        configure_memory_flags(freeze_memory, unfreeze_memory)

        # Handle vibe case
        if resource == "vibe":
            if not args:
                console_manager.print_error("Missing request after 'vibe'")
                sys.exit(1)

            request = " ".join(args)
            handle_vibe_request(
                request=request,
                command="describe",
                plan_prompt=include_memory_in_prompt(PLAN_DESCRIBE_PROMPT),
                summary_prompt_func=describe_resource_prompt,
                output_flags=output_flags,
            )
            return

        # Handle standard command
        handle_standard_command(
            command="describe",
            resource=resource,
            args=args,
            output_flags=output_flags,
            summary_prompt_func=describe_resource_prompt,
        )
    except Exception as e:
        handle_exception(e)


@cli.command()
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.option("--show-raw-output/--no-show-raw-output", is_flag=True, default=None)
@click.option("--show-vibe/--no-show-vibe", is_flag=True, default=None)
@click.option("--model", default=None, help="The LLM model to use")
@click.option(
    "--freeze-memory", is_flag=True, help="Prevent memory updates for this command"
)
@click.option(
    "--unfreeze-memory", is_flag=True, help="Enable memory updates for this command"
)
def logs(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
) -> None:
    """Show logs for a container in a pod."""
    try:
        # Configure output flags
        output_flags = configure_output_flags(
            show_raw_output=show_raw_output, show_vibe=show_vibe, model=model
        )

        # Configure memory flags
        configure_memory_flags(freeze_memory, unfreeze_memory)

        # Special case for vibe command
        if resource == "vibe":
            if not args:
                console_manager.print_error("Missing request after 'vibe'")
                sys.exit(1)

            request = " ".join(args)
            handle_vibe_request(
                request=request,
                command="logs",
                plan_prompt=include_memory_in_prompt(PLAN_LOGS_PROMPT),
                summary_prompt_func=logs_prompt,
                output_flags=output_flags,
            )
            return

        # Regular logs command
        cmd = ["logs", resource, *args]
        output = run_kubectl(cmd, capture=True)

        if not output:
            return

        # Check if output is too large and might need truncation
        output_length = len(output)
        if output_length > MAX_TOKEN_LIMIT * LOGS_TRUNCATION_RATIO:
            console_manager.print_truncation_warning()

        # Handle the output display based on the configured flags
        handle_command_output(
            output=output,
            output_flags=output_flags,
            summary_prompt_func=logs_prompt,
            max_token_limit=MAX_TOKEN_LIMIT,
            truncation_ratio=LOGS_TRUNCATION_RATIO,
        )
    except Exception as e:
        handle_exception(e)


@cli.command()
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.option("--show-raw-output/--no-show-raw-output", is_flag=True, default=None)
@click.option("--show-vibe/--no-show-vibe", is_flag=True, default=None)
@click.option("--model", default=None, help="The LLM model to use")
@click.option(
    "--freeze-memory", is_flag=True, help="Prevent memory updates for this command"
)
@click.option(
    "--unfreeze-memory", is_flag=True, help="Enable memory updates for this command"
)
def create(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
) -> None:
    """Create a resource."""
    try:
        # Configure output flags
        output_flags = configure_output_flags(
            show_raw_output=show_raw_output, show_vibe=show_vibe, model=model
        )

        # Configure memory flags
        configure_memory_flags(freeze_memory, unfreeze_memory)

        # Handle vibe command
        if resource == "vibe":
            if not args:
                console_manager.print_error("Missing request after 'vibe'")
                sys.exit(1)
            request = " ".join(args)
            handle_vibe_request(
                request=request,
                command="create",
                plan_prompt=include_memory_in_prompt(PLAN_CREATE_PROMPT),
                summary_prompt_func=create_resource_prompt,
                output_flags=output_flags,
            )
            return

        # Regular create command
        cmd = ["create", resource, *args]
        output = run_kubectl(cmd, capture=True)

        if not output:
            return

        # Handle the output display based on the configured flags
        handle_command_output(
            output=output,
            output_flags=output_flags,
            summary_prompt_func=create_resource_prompt,
        )
    except Exception as e:
        handle_exception(e)


@cli.command()
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.option("--show-raw-output/--no-show-raw-output", is_flag=True, default=None)
@click.option("--show-vibe/--no-show-vibe", is_flag=True, default=None)
@click.option("--model", default=None, help="The LLM model to use")
@click.option(
    "--freeze-memory", is_flag=True, help="Prevent memory updates for this command"
)
@click.option(
    "--unfreeze-memory", is_flag=True, help="Enable memory updates for this command"
)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def delete(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    yes: bool = False,
) -> None:
    """Delete a resource.

    Removes resources from the cluster.
    Use --yes or -y to skip confirmation prompt for non-interactive usage.
    """
    try:
        # Configure output flags
        output_flags = configure_output_flags(
            show_raw_output=show_raw_output, show_vibe=show_vibe, model=model
        )

        # Configure memory flags
        configure_memory_flags(freeze_memory, unfreeze_memory)

        # Handle vibe command
        if resource == "vibe":
            if not args:
                console_manager.print_error("Missing request after 'vibe'")
                sys.exit(1)
            request = " ".join(args)
            handle_vibe_request(
                request=request,
                command="delete",
                plan_prompt=include_memory_in_prompt(PLAN_DELETE_PROMPT),
                summary_prompt_func=delete_resource_prompt,
                output_flags=output_flags,
                yes=yes,
            )
            return

        # Handle standard command without confirmation
        handle_standard_command(
            command="delete",
            resource=resource,
            args=args,
            output_flags=output_flags,
            summary_prompt_func=delete_resource_prompt,
        )
    except Exception as e:
        handle_exception(e)


@cli.command()
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def just(args: tuple) -> None:
    """Pass commands directly to kubectl.

    Passes all arguments directly to kubectl without any processing.
    Useful for commands not yet supported by vibectl or when you want
    to use kubectl directly.

    Example:
        vibectl just get pods  # equivalent to: kubectl get pods
    """
    try:
        if not args:
            console_manager.print_error("Usage: vibectl just <kubectl commands>")
            sys.exit(1)

        # Build kubectl command with args
        cmd = ["kubectl"]

        # Add kubeconfig if configured
        cfg = Config()
        kubeconfig = cfg.get("kubeconfig")
        if kubeconfig:
            cmd.extend(["--kubeconfig", str(kubeconfig)])

        # Add the user's arguments
        cmd.extend(args)

        # Run the command
        result = subprocess.run(cmd, check=True, text=True, capture_output=True)
        if result.stdout:
            # Print standard output
            console_manager.print_raw(result.stdout)
        if result.stderr:
            # Print error output if any
            console_manager.print_error(result.stderr)
    except (
        FileNotFoundError
    ):  # pragma: no cover - kubectl not found is difficult to test reliably
        console_manager.print_error("kubectl not found in PATH")
        sys.exit(1)
    except (
        subprocess.CalledProcessError
    ) as e:  # pragma: no cover - specific exit codes are difficult to test
        if e.stderr:
            console_manager.print_error(f"Error: {e.stderr}")
        else:
            console_manager.print_error(
                f"Error: Command failed with exit code {e.returncode}"
            )
        sys.exit(1)
    except Exception as e:  # pragma: no cover - general exception catch for robustness
        console_manager.print_error(f"Error: {e!s}")
        sys.exit(1)


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
    """Show current configuration."""
    try:
        cfg = Config()
        config_data = cfg.get_all()
        if not config_data:
            console_manager.print_note("No configuration set")
            return

        table = Table(title="vibectl Configuration")
        table.add_column("Key", style="cyan")
        table.add_column("Value", style="green")

        for key, value in config_data.items():
            table.add_row(key, str(value))

        console_manager.console.print(table)
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

        # No text provided and no editor flag
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
        sys.exit(1)


@theme.command(name="set")
@click.argument("theme_name")
def theme_set(theme_name: str) -> None:
    """Set the console theme.

    Examples:
        vibectl theme set dark
        vibectl theme set light
    """
    try:
        # Verify theme exists
        available_themes = console_manager.get_available_themes()
        if theme_name not in available_themes:  # pragma: no cover - tested separately
            console_manager.print_error(
                f"Invalid theme '{theme_name}'. Available themes: "
                f"{', '.join(available_themes)}"
            )
            sys.exit(1)

        # Save theme in config
        cfg = Config()
        cfg.set("theme", theme_name)
        cfg.save()

        # Apply theme
        console_manager.set_theme(theme_name)
        console_manager.print_success(f"Theme set to {theme_name}")
    except Exception as e:  # pragma: no cover - general exception catch for robustness
        handle_exception(e)
        sys.exit(1)


@cli.command()
@click.argument("request", required=False)
@click.option("--show-raw-output/--no-show-raw-output", is_flag=True, default=None)
@click.option("--show-vibe/--no-show-vibe", is_flag=True, default=None)
@click.option(
    "--show-kubectl/--no-show-kubectl",
    is_flag=True,
    default=None,
    help="Show the kubectl command being executed",
)
@click.option("--model", default=None, help="The LLM model to use")
@click.option(
    "--freeze-memory", is_flag=True, help="Prevent memory updates for this command"
)
@click.option(
    "--unfreeze-memory", is_flag=True, help="Enable memory updates for this command"
)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
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
    """Execute autonomous Kubernetes operations guided by memory and planning.

    Analyzes cluster state, memory context, and user request to determine and
    execute appropriate kubectl commands. With no arguments, it will use memory
    and general Kubernetes knowledge to guide operations.

    Examples:
        vibectl vibe "create a deployment for nginx with 3 replicas"
        vibectl vibe "check if all pods are running"
        vibectl vibe "fix the issues with the frontend service"
        vibectl vibe
    """
    try:
        # Configure output flags
        output_flags = configure_output_flags(
            show_raw_output=show_raw_output,
            show_vibe=show_vibe,
            model=model,
            show_kubectl=show_kubectl,
        )

        # Configure memory flags
        configure_memory_flags(freeze_memory, unfreeze_memory)

        # Get memory
        memory_context = get_memory() or ""

        # Handle empty request case
        if not request:
            request = ""
            console_manager.print_processing(
                "Planning next steps based on memory context..."
            )
        else:
            console_manager.print_processing(f"Planning how to: {request}")

        # Autonomous vibe command - plan_prompt already includes memory directly
        handle_vibe_request(
            request=request,
            command="vibe",
            plan_prompt=PLAN_VIBE_PROMPT.format(
                memory_context=memory_context, request=request
            ),
            summary_prompt_func=vibe_autonomous_prompt,
            output_flags=output_flags,
            yes=yes,
            autonomous_mode=True,
        )
    except Exception as e:
        handle_exception(e)


@cli.command(context_settings={"ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.option("--show-raw-output/--no-show-raw-output", is_flag=True, default=None)
@click.option("--show-vibe/--no-show-vibe", is_flag=True, default=None)
@click.option("--model", default=None, help="The LLM model to use")
@click.option(
    "--freeze-memory", is_flag=True, help="Prevent memory updates for this command"
)
@click.option(
    "--unfreeze-memory", is_flag=True, help="Enable memory updates for this command"
)
def events(
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
) -> int | None:
    """List events in the cluster."""
    try:
        # Configure output flags
        output_flags = configure_output_flags(
            show_raw_output=show_raw_output, show_vibe=show_vibe, model=model
        )

        # Configure memory flags
        configure_memory_flags(freeze_memory, unfreeze_memory)

        # Special case for vibe command
        if args and args[0] == "vibe":
            if len(args) < 2:
                console_manager.print_error("Missing request after 'vibe'")
                return 1
            request = " ".join(args[1:])
            handle_vibe_request(
                request=request,
                command="events",
                plan_prompt=include_memory_in_prompt(PLAN_EVENTS_PROMPT),
                summary_prompt_func=events_prompt,
                output_flags=output_flags,
            )
            return 1

        # For standard commands, run kubectl events
        try:
            cmd = ["events"]
            cmd.extend(args)
            output = run_kubectl(cmd, capture=True)

            if not output:
                console_manager.print_empty_output_message()
                return 0

            # Handle output display based on flags
            try:
                handle_command_output(
                    output=output,
                    output_flags=output_flags,
                    summary_prompt_func=events_prompt,
                )
                return 0
            except Exception as e:
                handle_exception(e)
                return 1
        except Exception as e:
            handle_exception(e)
            return 1
    except Exception as e:
        handle_exception(e)
        return 1


@cli.command()
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.option("--show-raw-output/--no-show-raw-output", is_flag=True, default=None)
@click.option("--show-vibe/--no-show-vibe", is_flag=True, default=None)
@click.option("--model", default=None, help="The LLM model to use")
def version(
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
) -> None:
    """Show Kubernetes version information.

    Provides human-friendly interpretation of kubectl version details, highlighting
    compatibility status, potential upgrade recommendations, and significant version
    differences.
    """
    try:
        # Configure output flags
        output_flags = configure_output_flags(
            show_raw_output=show_raw_output, show_vibe=show_vibe, model=model
        )

        # Special case for vibe command
        if args and args[0] == "vibe":
            if len(args) < 2:
                console_manager.print_error("Missing request after 'vibe'")
                sys.exit(1)

            request = " ".join(args[1:])
            try:
                handle_vibe_request(
                    request=request,
                    command="version",
                    plan_prompt=PLAN_CLUSTER_INFO_PROMPT,
                    summary_prompt_func=version_prompt,
                    output_flags=output_flags,
                )
            except Exception as e:
                handle_exception(e)
            return

        # For standard version command with no args, run kubectl version
        try:
            output = run_kubectl(["version", "--output=json"], capture=True)

            if not output:
                console_manager.print_note("kubectl version information not available")
                return

            # Handle output display based on flags
            handle_command_output(
                output=output,
                output_flags=output_flags,
                summary_prompt_func=version_prompt,
            )
        except Exception as e:
            handle_exception(e)
    except Exception as e:
        handle_exception(e)
        # This is unreachable due to sys.exit in handle_exception, but makes the type
        # checker happy
        return None


@cli.command()
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.option("--show-raw-output/--no-show-raw-output", is_flag=True, default=None)
@click.option("--show-vibe/--no-show-vibe", is_flag=True, default=None)
@click.option("--model", default=None, help="The LLM model to use")
def cluster_info(
    args: tuple,
    show_raw_output: bool | None = None,
    show_vibe: bool | None = None,
    model: str | None = None,
) -> int | None:
    """Display cluster info."""
    try:
        # Configure output flags
        output_flags = configure_output_flags(
            show_raw_output=show_raw_output, show_vibe=show_vibe, model=model
        )

        # Handle vibe command
        if args and args[0] == "vibe":
            if len(args) < 2:
                console_manager.print_error("Missing request after 'vibe'")
                return 1
            request = " ".join(args[1:])
            handle_vibe_request(
                request=request,
                command="cluster-info",
                plan_prompt=PLAN_CLUSTER_INFO_PROMPT,
                summary_prompt_func=cluster_info_prompt,
                output_flags=output_flags,
            )
            return 0

        # Run the command
        output = run_kubectl(["cluster-info", *args], capture=True)

        if not output:
            return 0

        # Handle output display based on flags
        handle_command_output(
            output=output,
            output_flags=output_flags,
            summary_prompt_func=cluster_info_prompt,
        )
        return 0
    except Exception as e:
        handle_exception(e)
        return 1


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
            console_manager.console.print(
                Panel(
                    memory_content,
                    title="Memory Content",
                    border_style="blue",
                    expand=False,
                )
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
    elif text:
        try:
            # Join the text parts to handle multi-word input
            memory_text = " ".join(text)
            set_memory(memory_text)
            console_manager.print_success("Memory set")
        except Exception as e:
            console_manager.print_error(str(e))
            raise click.Abort() from e
    else:
        console_manager.print_error(
            "No text provided. Use TEXT argument or --edit flag"
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
        console_manager.console.print(
            Panel(
                updated_memory,
                title="Updated Memory Content",
                border_style="blue",
                expand=False,
            )
        )
    except Exception as e:
        handle_exception(e)


@cli.command(context_settings={"ignore_unknown_options": True})
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.option("--show-raw-output/--no-show-raw-output", is_flag=True, default=None)
@click.option("--show-vibe/--no-show-vibe", is_flag=True, default=None)
@click.option("--model", default=None, help="The LLM model to use")
@click.option(
    "--freeze-memory", is_flag=True, help="Prevent memory updates for this command"
)
@click.option(
    "--unfreeze-memory", is_flag=True, help="Enable memory updates for this command"
)
def scale(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
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
    try:
        # Configure output flags
        output_flags = configure_output_flags(
            show_raw_output=show_raw_output, show_vibe=show_vibe, model=model
        )

        # Configure memory flags
        configure_memory_flags(freeze_memory, unfreeze_memory)

        # Handle vibe command
        if resource == "vibe":
            if not args:
                console_manager.print_error("Missing request after 'vibe'")
                sys.exit(1)
            request = " ".join(args)
            handle_vibe_request(
                request=request,
                command="scale",
                plan_prompt=include_memory_in_prompt(PLAN_SCALE_PROMPT),
                summary_prompt_func=scale_resource_prompt,
                output_flags=output_flags,
            )
            return

        # Regular scale command
        cmd = ["scale", resource, *args]
        output = run_kubectl(cmd, capture=True)

        if not output:
            return

        # Handle the output display based on the configured flags
        handle_command_output(
            output=output,
            output_flags=output_flags,
            summary_prompt_func=scale_resource_prompt,
        )
    except Exception as e:
        handle_exception(e)


def configure_memory_flags(freeze: bool, unfreeze: bool) -> None:
    """Configure memory behavior based on flags.

    Args:
        freeze: Whether to disable memory updates for this command
        unfreeze: Whether to enable memory updates for this command

    Raises:
        ValueError: If both freeze and unfreeze are specified
    """
    if freeze and unfreeze:
        raise ValueError("Cannot specify both --freeze-memory and --unfreeze-memory")

    cfg = Config()

    if freeze:
        disable_memory(cfg)
    elif unfreeze:
        enable_memory(cfg)


@cli.group(
    invoke_without_command=True, context_settings={"ignore_unknown_options": True}
)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.option("--show-raw-output/--no-show-raw-output", is_flag=True, default=None)
@click.option("--show-vibe/--no-show-vibe", is_flag=True, default=None)
@click.option("--model", default=None, help="The LLM model to use")
@click.option(
    "--freeze-memory", is_flag=True, help="Prevent memory updates for this command"
)
@click.option(
    "--unfreeze-memory", is_flag=True, help="Enable memory updates for this command"
)
@click.pass_context
def rollout(
    ctx: click.Context,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
) -> None:
    """Manage rollouts of deployments, statefulsets, and daemonsets.

    Includes subcommands for checking status, viewing history, undoing rollouts,
    restarting, or pausing/resuming rollouts.

    Examples:
        vibectl rollout status deployment/nginx
        vibectl rollout history deployment/frontend
        vibectl rollout undo deployment/api --to-revision=2
        vibectl rollout restart deployment/backend
        vibectl rollout pause deployment/website
        vibectl rollout resume deployment/website
        vibectl rollout vibe "check status of the frontend deployment"
    """
    if ctx.invoked_subcommand is not None:
        # If a subcommand is used, we don't need to do anything here
        return

    try:
        # Configure output flags
        output_flags = configure_output_flags(
            show_raw_output=show_raw_output, show_vibe=show_vibe, model=model
        )

        # Configure memory flags
        configure_memory_flags(freeze_memory, unfreeze_memory)

        # Handle vibe command
        if args and args[0] == "vibe":
            if len(args) < 2:
                console_manager.print_error("Missing request after 'vibe'")
                sys.exit(1)
            request = " ".join(args[1:])
            handle_vibe_request(
                request=request,
                command="rollout",
                plan_prompt=include_memory_in_prompt(PLAN_ROLLOUT_PROMPT),
                summary_prompt_func=rollout_general_prompt,
                output_flags=output_flags,
            )
            return

        # For direct 'rollout' command with no recognized subcommand
        console_manager.print_error(
            "Missing subcommand for rollout. "
            "Use one of: status, history, undo, restart, pause, resume"
        )
        sys.exit(1)
    except Exception as e:
        handle_exception(e)


@rollout.command(context_settings={"ignore_unknown_options": True})
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.option("--show-raw-output/--no-show-raw-output", is_flag=True, default=None)
@click.option("--show-vibe/--no-show-vibe", is_flag=True, default=None)
@click.option("--model", default=None, help="The LLM model to use")
@click.option(
    "--freeze-memory", is_flag=True, help="Prevent memory updates for this command"
)
@click.option(
    "--unfreeze-memory", is_flag=True, help="Enable memory updates for this command"
)
def status(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
) -> None:
    """Show the status of a rollout.

    Examples:
        vibectl rollout status deployment/nginx
        vibectl rollout status deployment frontend -n app
    """
    try:
        # Configure output flags
        output_flags = configure_output_flags(
            show_raw_output=show_raw_output, show_vibe=show_vibe, model=model
        )

        # Configure memory flags
        configure_memory_flags(freeze_memory, unfreeze_memory)

        # Run the command
        cmd = ["rollout", "status", resource, *args]
        output = run_kubectl(cmd, capture=True)

        if not output:
            return

        # Handle the output display based on the configured flags
        handle_command_output(
            output=output,
            output_flags=output_flags,
            summary_prompt_func=rollout_status_prompt,
        )
    except Exception as e:
        handle_exception(e)


@rollout.command(context_settings={"ignore_unknown_options": True})
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.option("--show-raw-output/--no-show-raw-output", is_flag=True, default=None)
@click.option("--show-vibe/--no-show-vibe", is_flag=True, default=None)
@click.option("--model", default=None, help="The LLM model to use")
@click.option(
    "--freeze-memory", is_flag=True, help="Prevent memory updates for this command"
)
@click.option(
    "--unfreeze-memory", is_flag=True, help="Enable memory updates for this command"
)
def history(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
) -> None:
    """Show the rollout history.

    Examples:
        vibectl rollout history deployment/nginx
        vibectl rollout history deployment frontend -n app
        vibectl rollout history deployment/frontend --revision=2
    """
    try:
        # Configure output flags
        output_flags = configure_output_flags(
            show_raw_output=show_raw_output, show_vibe=show_vibe, model=model
        )

        # Configure memory flags
        configure_memory_flags(freeze_memory, unfreeze_memory)

        # Run the command
        cmd = ["rollout", "history", resource, *args]
        output = run_kubectl(cmd, capture=True)

        if not output:
            return

        # Handle the output display based on the configured flags
        handle_command_output(
            output=output,
            output_flags=output_flags,
            summary_prompt_func=rollout_history_prompt,
        )
    except Exception as e:
        handle_exception(e)


@rollout.command(context_settings={"ignore_unknown_options": True})
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.option("--show-raw-output/--no-show-raw-output", is_flag=True, default=None)
@click.option("--show-vibe/--no-show-vibe", is_flag=True, default=None)
@click.option("--model", default=None, help="The LLM model to use")
@click.option(
    "--freeze-memory", is_flag=True, help="Prevent memory updates for this command"
)
@click.option(
    "--unfreeze-memory", is_flag=True, help="Enable memory updates for this command"
)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def undo(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    yes: bool = False,
) -> None:
    """Undo a rollout.

    Examples:
        vibectl rollout undo deployment/nginx
        vibectl rollout undo deployment frontend -n app
        vibectl rollout undo deployment/frontend --to-revision=2
    """
    try:
        # Configure output flags
        output_flags = configure_output_flags(
            show_raw_output=show_raw_output, show_vibe=show_vibe, model=model
        )

        # Configure memory flags
        configure_memory_flags(freeze_memory, unfreeze_memory)

        # Handle confirmation for undo operation
        if not yes:
            confirmation_message = (
                f"Are you sure you want to undo the rollout for {resource}?"
            )
            if not click.confirm(confirmation_message):
                console_manager.print_note("Operation cancelled")
                return

        # Run the command
        cmd = ["rollout", "undo", resource, *args]
        output = run_kubectl(cmd, capture=True)

        if not output:
            return

        # Handle the output display based on the configured flags
        handle_command_output(
            output=output,
            output_flags=output_flags,
            summary_prompt_func=rollout_general_prompt,
        )
    except Exception as e:
        handle_exception(e)


@rollout.command(context_settings={"ignore_unknown_options": True})
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.option("--show-raw-output/--no-show-raw-output", is_flag=True, default=None)
@click.option("--show-vibe/--no-show-vibe", is_flag=True, default=None)
@click.option("--model", default=None, help="The LLM model to use")
@click.option(
    "--freeze-memory", is_flag=True, help="Prevent memory updates for this command"
)
@click.option(
    "--unfreeze-memory", is_flag=True, help="Enable memory updates for this command"
)
def restart(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
) -> None:
    """Restart a resource.

    Examples:
        vibectl rollout restart deployment/nginx
        vibectl rollout restart deployment frontend -n app
        vibectl rollout restart deployment,statefulset -l app=frontend
    """
    try:
        # Configure output flags
        output_flags = configure_output_flags(
            show_raw_output=show_raw_output, show_vibe=show_vibe, model=model
        )

        # Configure memory flags
        configure_memory_flags(freeze_memory, unfreeze_memory)

        # Run the command
        cmd = ["rollout", "restart", resource, *args]
        output = run_kubectl(cmd, capture=True)

        if not output:
            return

        # Handle the output display based on the configured flags
        handle_command_output(
            output=output,
            output_flags=output_flags,
            summary_prompt_func=rollout_general_prompt,
        )
    except Exception as e:
        handle_exception(e)


@rollout.command(context_settings={"ignore_unknown_options": True})
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.option("--show-raw-output/--no-show-raw-output", is_flag=True, default=None)
@click.option("--show-vibe/--no-show-vibe", is_flag=True, default=None)
@click.option("--model", default=None, help="The LLM model to use")
@click.option(
    "--freeze-memory", is_flag=True, help="Prevent memory updates for this command"
)
@click.option(
    "--unfreeze-memory", is_flag=True, help="Enable memory updates for this command"
)
def pause(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
) -> None:
    """Pause a rollout.

    Examples:
        vibectl rollout pause deployment/nginx
        vibectl rollout pause deployment frontend -n app
    """
    try:
        # Configure output flags
        output_flags = configure_output_flags(
            show_raw_output=show_raw_output, show_vibe=show_vibe, model=model
        )

        # Configure memory flags
        configure_memory_flags(freeze_memory, unfreeze_memory)

        # Run the command
        cmd = ["rollout", "pause", resource, *args]
        output = run_kubectl(cmd, capture=True)

        if not output:
            return

        # Handle the output display based on the configured flags
        handle_command_output(
            output=output,
            output_flags=output_flags,
            summary_prompt_func=rollout_general_prompt,
        )
    except Exception as e:
        handle_exception(e)


@rollout.command(context_settings={"ignore_unknown_options": True})
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.option("--show-raw-output/--no-show-raw-output", is_flag=True, default=None)
@click.option("--show-vibe/--no-show-vibe", is_flag=True, default=None)
@click.option("--model", default=None, help="The LLM model to use")
@click.option(
    "--freeze-memory", is_flag=True, help="Prevent memory updates for this command"
)
@click.option(
    "--unfreeze-memory", is_flag=True, help="Enable memory updates for this command"
)
def resume(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
) -> None:
    """Resume a paused rollout.

    Examples:
        vibectl rollout resume deployment/nginx
        vibectl rollout resume deployment frontend -n app
    """
    try:
        # Configure output flags
        output_flags = configure_output_flags(
            show_raw_output=show_raw_output, show_vibe=show_vibe, model=model
        )

        # Configure memory flags
        configure_memory_flags(freeze_memory, unfreeze_memory)

        # Run the command
        cmd = ["rollout", "resume", resource, *args]
        output = run_kubectl(cmd, capture=True)

        if not output:
            return

        # Handle the output display based on the configured flags
        handle_command_output(
            output=output,
            output_flags=output_flags,
            summary_prompt_func=rollout_general_prompt,
        )
    except Exception as e:
        handle_exception(e)


def main() -> None:
    """Run the CLI application."""
    try:
        exit_code = cli()
        sys.exit(exit_code or 0)
    except KeyboardInterrupt:
        console_manager.print_keyboard_interrupt()
        sys.exit(1)
    except Exception as e:
        handle_exception(e)
        # This is unreachable due to sys.exit in handle_exception, but makes the type
        # checker happy
        return None


if __name__ == "__main__":
    main()
