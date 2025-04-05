"""
Command-line interface for vibectl.

Provides a vibes-based alternative to kubectl, using AI to generate human-friendly
summaries of Kubernetes resources. Each command aims to make cluster management
more intuitive while preserving access to raw kubectl output when needed.
"""

import datetime
import json
import subprocess
import sys
from typing import List, NoReturn, Optional, Tuple

import click
import llm
from rich.table import Table

from .config import Config
from .console import console_manager
from .prompt import (
    PLAN_CLUSTER_INFO_PROMPT,
    PLAN_CREATE_PROMPT,
    PLAN_DESCRIBE_PROMPT,
    PLAN_EVENTS_PROMPT,
    PLAN_GET_PROMPT,
    PLAN_LOGS_PROMPT,
    cluster_info_prompt,
    create_resource_prompt,
    describe_resource_prompt,
    events_prompt,
    get_resource_prompt,
    logs_prompt,
    version_prompt,
)

# Constants
MAX_TOKEN_LIMIT = 10000
LOGS_TRUNCATION_RATIO = 3
DEFAULT_MODEL = "claude-3.7-sonnet"
DEFAULT_SHOW_RAW_OUTPUT = False
DEFAULT_SHOW_VIBE = True
DEFAULT_SUPPRESS_OUTPUT_WARNING = False

# Current datetime for version command
CURRENT_DATETIME = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def run_kubectl(args: List[str], capture: bool = False) -> Optional[str]:
    """Run kubectl with the given arguments.

    Args:
        args: List of arguments to pass to kubectl
        capture: Whether to capture and return the output (True) or print it (False)

    Returns:
        The command output if capture=True, None otherwise

    Raises:
        subprocess.CalledProcessError: If kubectl returns an error
        FileNotFoundError: If kubectl is not found
    """
    try:
        cmd = ["kubectl"]

        # Add kubeconfig if configured
        cfg = Config()
        kubeconfig = cfg.get("kubeconfig")
        if kubeconfig:
            cmd.extend(["--kubeconfig", kubeconfig])

        # Ensure all arguments are strings
        cmd.extend(str(arg) for arg in args)

        result = subprocess.run(cmd, check=True, text=True, capture_output=True)
        if result.stdout:
            if capture:
                return result.stdout
            # Disable markup and highlighting for kubectl output
            console_manager.print_raw(result.stdout)
        return None
    except subprocess.CalledProcessError as e:
        # Show error directly without "Error:" prefix since kubectl already includes it
        if e.stderr:
            console_manager.error_console.print(e.stderr, end="")
        else:
            console_manager.print_error(f"Command failed with exit code {e.returncode}")
        raise  # Re-raise the original error
    except FileNotFoundError:
        console_manager.print_error("kubectl not found in PATH")
        raise


@click.group()
@click.version_option()
def cli() -> None:
    """vibectl - A vibes-based alternative to kubectl"""
    # Initialize the console manager with the configured theme
    try:
        cfg = Config()
        theme_name = cfg.get("theme", "default")
        if theme_name is not None and isinstance(theme_name, str):
            console_manager.set_theme(theme_name)
    except Exception:
        # Fallback to default in case of any issues (helpful for tests)
        pass


def handle_vibe_request(
    request: str,
    command: str,
    plan_prompt: str,
    summary_prompt: str,
    show_raw_output: bool,
    show_vibe: bool,
    model_name: str,
    suppress_output_warning: bool = False,
) -> None:
    """Handle a vibe request by planning and executing a kubectl command."""
    try:
        # Show warning if no output will be shown and warning is not suppressed
        if not show_raw_output and not show_vibe and not suppress_output_warning:
            console_manager.print_no_output_warning()

        # Get the plan from LLM
        llm_model = llm.get_model(model_name)

        # Format prompt with request - plan prompts already use the latest formatting
        prompt = plan_prompt.format(request=request)
        response = llm_model.prompt(prompt)
        plan = response.text() if hasattr(response, "text") else str(response)

        # Check for error responses from planner
        if isinstance(plan, str) and plan.startswith("ERROR:"):
            console_manager.print_error(plan[7:])
            sys.exit(1)

        # Extract kubectl command from plan
        kubectl_args = []
        for line in plan.split("\n"):
            if line == "---":
                break
            kubectl_args.append(line)

        # Validate plan format
        if not kubectl_args:
            console_manager.print_error("Invalid response format from planner")
            sys.exit(1)

        # Run kubectl command
        try:
            output = run_kubectl([command, *kubectl_args], capture=True)
        except subprocess.CalledProcessError as e:
            # If kubectl fails, error is already shown by run_kubectl
            if show_raw_output:
                console_manager.print_raw(str(e))
            sys.exit(1)

        # If no output, nothing to do
        if not output:
            return

        # Show raw output if requested
        if show_raw_output:
            console_manager.print_raw(output)

        # Only proceed with vibe check if requested
        if show_vibe:
            # Process the output to stay within token limits
            llm_output, _ = console_manager.process_output_for_vibe(
                output, MAX_TOKEN_LIMIT, LOGS_TRUNCATION_RATIO
            )

            try:
                # Select the right command function to get the latest datetime
                if command == "get":
                    prompt_with_time = get_resource_prompt().format(output=llm_output)
                elif command == "describe":
                    prompt_with_time = describe_resource_prompt().format(
                        output=llm_output
                    )
                elif command == "logs":
                    prompt_with_time = logs_prompt().format(output=llm_output)
                elif command == "create":
                    prompt_with_time = create_resource_prompt().format(
                        output=llm_output
                    )
                elif command == "cluster-info":
                    prompt_with_time = cluster_info_prompt().format(output=llm_output)
                elif command == "events":
                    prompt_with_time = events_prompt().format(output=llm_output)
                else:
                    # Fallback to original prompt if command isn't recognized
                    prompt_with_time = summary_prompt.format(output=llm_output)

                response = llm_model.prompt(prompt_with_time)
                summary = (
                    response.text() if hasattr(response, "text") else str(response)
                )
                if show_raw_output:
                    # Add newline before vibe check
                    console_manager.console.print()
                console_manager.print_vibe(summary)
            except Exception as e:
                console_manager.print_note("Could not get vibe check", error=e)

    except Exception as e:
        if "No key found" in str(e):
            console_manager.print_missing_api_key_error()
            sys.exit(1)
        else:
            console_manager.print_error(str(e))
            sys.exit(1)


@cli.command()
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.option("--raw/--no-raw", "raw", is_flag=True, default=None)
@click.option("--show-raw-output/--no-show-raw-output", is_flag=True, default=None)
@click.option("--show-vibe/--no-show-vibe", is_flag=True, default=None)
@click.option("--model", default=None, help="The LLM model to use")
def get(
    resource: str,
    args: tuple,
    raw: Optional[bool],
    show_raw_output: Optional[bool],
    show_vibe: Optional[bool],
    model: Optional[str],
) -> None:
    """Get information about Kubernetes resources."""
    # Configure output flags
    (
        show_raw_output,
        show_vibe,
        suppress_output_warning,
        model_name,
    ) = configure_output_flags(raw, show_raw_output, show_vibe, model)

    if resource == "vibe":
        if not args:
            console_manager.print_missing_request_error()
            sys.exit(1)
        request = " ".join(args)
        handle_vibe_request(
            request=request,
            command="get",
            plan_prompt=PLAN_GET_PROMPT,
            summary_prompt=get_resource_prompt(),
            show_raw_output=show_raw_output,
            show_vibe=show_vibe,
            model_name=model_name,
            suppress_output_warning=suppress_output_warning,
        )
        return

    cmd = ["get", resource]
    cmd.extend(args)

    try:
        output = run_kubectl(cmd, capture=True)
        if not output:
            return

        # Show raw output if requested (before any potential LLM errors)
        if show_raw_output:
            console_manager.print_raw(output)

        # Only proceed with vibe check if requested
        if show_vibe:
            # Process the output to stay within token limits
            llm_output, _ = console_manager.process_output_for_vibe(
                output, MAX_TOKEN_LIMIT, LOGS_TRUNCATION_RATIO
            )

            try:
                llm_model = llm.get_model(model_name)
                prompt = get_resource_prompt().format(output=llm_output)
                response = llm_model.prompt(prompt)
                summary = (
                    response.text() if hasattr(response, "text") else str(response)
                )
                if show_raw_output:
                    # Add newline before vibe check
                    console_manager.console.print()
                console_manager.print_vibe(summary)
            except Exception as e:
                console_manager.print_note("Could not get vibe check", error=e)

    except Exception as e:
        if "No key found" in str(e):
            console_manager.print_missing_api_key_error()
            sys.exit(1)
        else:
            console_manager.print_error(str(e))
            sys.exit(1)


@cli.command()
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.option("--raw/--no-raw", "raw", is_flag=True, default=None)
@click.option("--show-raw-output/--no-show-raw-output", is_flag=True, default=None)
@click.option("--show-vibe/--no-show-vibe", is_flag=True, default=None)
@click.option("--model", default=None, help="The LLM model to use")
def describe(
    resource: str,
    args: tuple,
    raw: Optional[bool],
    show_raw_output: Optional[bool],
    show_vibe: Optional[bool],
    model: Optional[str],
) -> None:
    """Show details of a specific resource."""
    config = Config()
    model_name = model or config.get("model", DEFAULT_MODEL)

    # Handle raw flag for backward compatibility
    if raw is not None:
        show_raw_output = raw

    # Use config values if flags are not provided
    if show_raw_output is None:
        show_raw_output = config.get("show_raw_output", DEFAULT_SHOW_RAW_OUTPUT)
    if show_vibe is None:
        show_vibe = config.get("show_vibe", DEFAULT_SHOW_VIBE)
    suppress_output_warning = config.get(
        "suppress_output_warning", DEFAULT_SUPPRESS_OUTPUT_WARNING
    )

    # Show warning if no output will be shown, but continue execution
    if not show_raw_output and not show_vibe and not suppress_output_warning:
        console_manager.print_no_output_warning()

    if resource == "vibe":
        if not args:
            console_manager.print_error("Missing request after 'vibe'")
            sys.exit(1)
        request = " ".join(args)
        handle_vibe_request(
            request=request,
            command="describe",
            plan_prompt=PLAN_DESCRIBE_PROMPT,
            summary_prompt=describe_resource_prompt(),
            show_raw_output=show_raw_output,
            show_vibe=show_vibe,
            model_name=model_name,
            suppress_output_warning=suppress_output_warning,
        )
        return

    cmd = ["describe", resource]
    cmd.extend(args)

    try:
        output = run_kubectl(cmd, capture=True)
        if not output:
            return

        # Show raw output if requested (before any potential LLM errors)
        if show_raw_output:
            console_manager.print_raw(output)

        # Only proceed with vibe check if requested
        if show_vibe:
            # Check token count for LLM
            output_len = len(output)
            token_estimate = output_len / 4
            llm_output = output

            if token_estimate > MAX_TOKEN_LIMIT:
                # For logs, take first and last third
                chunk_size = int(
                    MAX_TOKEN_LIMIT / LOGS_TRUNCATION_RATIO * 4
                )  # Convert back to chars
                truncated_output = (
                    f"{output[:chunk_size]}\n"
                    f"[...truncated {output_len - 2 * chunk_size} characters...]\n"
                    f"{output[-chunk_size:]}"
                )
                llm_output = truncated_output
                console_manager.print_truncation_warning()

            try:
                llm_model = llm.get_model(model_name)
                prompt = describe_resource_prompt().format(output=llm_output)
                response = llm_model.prompt(prompt)
                summary = (
                    response.text() if hasattr(response, "text") else str(response)
                )
                if show_raw_output:
                    # Add newline before vibe check
                    console_manager.console.print()
                console_manager.print_vibe(summary)
            except Exception as e:
                console_manager.print_note("Could not get vibe check", error=e)

    except Exception as e:
        if "No key found" in str(e):
            console_manager.print_missing_api_key_error()
            sys.exit(1)
        else:
            console_manager.print_error(f"Error: {e}")
            sys.exit(1)


@cli.command()
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.option("--raw/--no-raw", "raw", is_flag=True, default=None)
@click.option("--show-raw-output/--no-show-raw-output", is_flag=True, default=None)
@click.option("--show-vibe/--no-show-vibe", is_flag=True, default=None)
@click.option("--model", default=None, help="The LLM model to use")
def logs(
    resource: str,
    args: tuple,
    raw: Optional[bool],
    show_raw_output: Optional[bool],
    show_vibe: Optional[bool],
    model: Optional[str],
) -> None:
    """Show logs from containers."""
    config = Config()
    model_name = model or config.get("model", DEFAULT_MODEL)

    # Handle raw flag for backward compatibility
    if raw is not None:
        show_raw_output = raw

    # Use config values if flags are not provided
    if show_raw_output is None:
        show_raw_output = config.get("show_raw_output", DEFAULT_SHOW_RAW_OUTPUT)
    if show_vibe is None:
        show_vibe = config.get("show_vibe", DEFAULT_SHOW_VIBE)
    suppress_output_warning = config.get(
        "suppress_output_warning", DEFAULT_SUPPRESS_OUTPUT_WARNING
    )

    # Show warning if no output will be shown, but continue execution
    if not show_raw_output and not show_vibe and not suppress_output_warning:
        console_manager.print_no_output_warning()

    if resource == "vibe":
        if not args:
            console_manager.print_error("Missing request after 'vibe'")
            sys.exit(1)
        request = " ".join(args)
        handle_vibe_request(
            request=request,
            command="logs",
            plan_prompt=PLAN_LOGS_PROMPT,
            summary_prompt=logs_prompt(),
            show_raw_output=show_raw_output,
            show_vibe=show_vibe,
            model_name=model_name,
            suppress_output_warning=suppress_output_warning,
        )
        return

    cmd = ["logs", resource]
    cmd.extend(args)

    try:
        output = run_kubectl(cmd, capture=True)
        if not output:
            return

        # Show raw output if requested (before any potential LLM errors)
        if show_raw_output:
            console_manager.print_raw(output)

        # Only proceed with vibe check if requested
        if show_vibe:
            # Check token count for LLM
            output_len = len(output)
            token_estimate = output_len / 4
            llm_output = output

            if token_estimate > MAX_TOKEN_LIMIT:
                # For logs, take first and last third
                chunk_size = int(
                    MAX_TOKEN_LIMIT / LOGS_TRUNCATION_RATIO * 4
                )  # Convert back to chars
                truncated_output = (
                    f"{output[:chunk_size]}\n"
                    f"[...truncated {output_len - 2 * chunk_size} characters...]\n"
                    f"{output[-chunk_size:]}"
                )
                llm_output = truncated_output
                console_manager.print_truncation_warning()

            try:
                llm_model = llm.get_model(model_name)
                prompt = logs_prompt().format(output=llm_output)
                response = llm_model.prompt(prompt)
                summary = (
                    response.text() if hasattr(response, "text") else str(response)
                )
                if show_raw_output:
                    # Add newline before vibe check
                    console_manager.console.print()
                console_manager.print_vibe(summary)
            except Exception as e:
                console_manager.print_note("Could not get vibe check", error=e)

    except Exception as e:
        if "No key found" in str(e):
            console_manager.print_missing_api_key_error()
            sys.exit(1)
        else:
            console_manager.print_error(f"Error: {e}")
            sys.exit(1)


@cli.command()
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.option("--raw/--no-raw", "raw", is_flag=True, default=None)
@click.option("--show-raw-output/--no-show-raw-output", is_flag=True, default=None)
@click.option("--show-vibe/--no-show-vibe", is_flag=True, default=None)
@click.option("--model", default=None, help="The LLM model to use")
def create(
    resource: str,
    args: tuple,
    raw: Optional[bool],
    show_raw_output: Optional[bool],
    show_vibe: Optional[bool],
    model: Optional[str],
) -> None:
    """Create a resource."""
    config = Config()
    model_name = model or config.get("model", DEFAULT_MODEL)

    # Handle raw flag for backward compatibility
    if raw is not None:
        show_raw_output = raw

    # Use config values if flags are not provided
    if show_raw_output is None:
        show_raw_output = config.get("show_raw_output", DEFAULT_SHOW_RAW_OUTPUT)
    if show_vibe is None:
        show_vibe = config.get("show_vibe", DEFAULT_SHOW_VIBE)
    suppress_output_warning = config.get(
        "suppress_output_warning", DEFAULT_SUPPRESS_OUTPUT_WARNING
    )

    # Show warning if no output will be shown, but continue execution
    if not show_raw_output and not show_vibe and not suppress_output_warning:
        console_manager.print_no_output_warning()

    if resource == "vibe":
        if not args:
            console_manager.print_error("Missing request after 'vibe'")
            sys.exit(1)
        request = " ".join(args)
        handle_vibe_request(
            request=request,
            command="create",
            plan_prompt=PLAN_CREATE_PROMPT,
            summary_prompt=create_resource_prompt(),
            show_raw_output=show_raw_output,
            show_vibe=show_vibe,
            model_name=model_name,
            suppress_output_warning=suppress_output_warning,
        )
        return

    cmd = ["create", resource]
    cmd.extend(args)

    try:
        output = run_kubectl(cmd, capture=True)
        if not output:
            return

        # Show raw output if requested (before any potential LLM errors)
        if show_raw_output:
            console_manager.print_raw(output)

        # Only proceed with vibe check if requested
        if show_vibe:
            # Check token count for LLM
            output_len = len(output)
            token_estimate = output_len / 4
            llm_output = output

            if token_estimate > MAX_TOKEN_LIMIT:
                # For logs, take first and last third
                chunk_size = int(
                    MAX_TOKEN_LIMIT / LOGS_TRUNCATION_RATIO * 4
                )  # Convert back to chars
                truncated_output = (
                    f"{output[:chunk_size]}\n"
                    f"[...truncated {output_len - 2 * chunk_size} characters...]\n"
                    f"{output[-chunk_size:]}"
                )
                llm_output = truncated_output
                console_manager.print_truncation_warning()

            try:
                llm_model = llm.get_model(model_name)
                prompt = create_resource_prompt().format(output=llm_output)
                response = llm_model.prompt(prompt)
                summary = (
                    response.text() if hasattr(response, "text") else str(response)
                )
                if show_raw_output:
                    # Add newline before vibe check
                    console_manager.console.print()
                console_manager.print_vibe(summary)
            except Exception as e:
                console_manager.print_note("Could not get vibe check", error=e)

    except Exception as e:
        if "No key found" in str(e):
            console_manager.print_missing_api_key_error()
            sys.exit(1)
        else:
            console_manager.print_error(f"Error: {e}")
            sys.exit(1)


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
    if not args:
        console_manager.print("Usage: vibectl just <kubectl commands>")
        sys.exit(1)
    run_kubectl(list(args))


@cli.group()
def config() -> None:
    """Manage vibectl configuration."""
    pass


@config.command(name="set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str) -> None:
    """Set a configuration value.

    Available keys:
        kubeconfig: Path to kubeconfig file
        llm_model: Name of the LLM model to use (default: claude-3.7-sonnet)
        show_raw_output: Whether to always show raw kubectl output (default: false)
        show_vibe: Whether to show vibe summaries (default: true)
        suppress_output_warning: Whether to suppress warning when no output is shown
                            (default: false)
    """
    cfg = Config()

    # Convert string boolean values
    if key in ["show_raw_output", "show_vibe", "suppress_output_warning"]:
        value = str(value.lower() == "true").lower()

    # Validate model name
    if key == "llm_model" and value not in ["claude-3.7-sonnet"]:
        console_manager.print_error(
            "Invalid model name. Currently supported models: claude-3.7-sonnet"
        )
        sys.exit(1)

    cfg.set(key, value)
    console_manager.print_success(f"Set {key} to {value}")


@config.command()
def show() -> None:
    """Show current configuration"""
    cfg = Config()
    config_data = cfg.show()
    console_manager.print_config_table(config_data)


@cli.group()
def theme() -> None:
    """Manage vibectl themes"""
    pass


@theme.command(name="list")
def theme_list() -> None:
    """List available themes"""
    cfg = Config()
    available_themes = cfg.get_available_themes()

    # Create a table to display available themes
    table = Table(
        title="Available Themes",
        show_header=True,
        title_justify="center",
        title_style="table_title",
    )
    table.add_column("Theme", style="key")
    table.add_column("Status", style="value")

    current_theme = cfg.get("theme", "default")

    for theme_name in available_themes:
        status = "[success]Active[/success]" if theme_name == current_theme else ""
        table.add_row(theme_name, status)

    console_manager.console.print(table)


@theme.command(name="set")
@click.argument("theme_name")
def theme_set(theme_name: str) -> None:
    """Set the current theme

    THEME_NAME: Name of the theme to use (default, dark, light, accessible)
    """
    cfg = Config()

    try:
        # Update the config
        cfg.set("theme", theme_name)

        # Update the console manager to use the new theme immediately
        console_manager.set_theme(theme_name)

        console_manager.print_success(f"Theme set to {theme_name}")
    except ValueError as e:
        console_manager.print_error(str(e))
        sys.exit(1)


@cli.command()
def vibe() -> None:
    """Check the current vibe of your cluster."""
    console_manager.print("✨ [bold green]Checking cluster vibes...[/]")
    # TODO: Implement cluster vibe checking


@cli.command()
def version() -> None:
    """Display version information for server components using LLM interpretation."""
    try:
        result = subprocess.run(
            ["kubectl", "version", "--output=json"],
            check=True,
            text=True,
            capture_output=True,
        )
        version_info = json.loads(result.stdout)

        # Use LLM to interpret the JSON response
        llm_model = llm.get_model(DEFAULT_MODEL)

        # Use fresh version prompt with current datetime
        prompt = version_prompt().format(version_info=version_info)
        response = llm_model.prompt(prompt)
        interpretation = response.text() if hasattr(response, "text") else str(response)
        console_manager.print(interpretation, markup=True, highlight=False)

    except (subprocess.CalledProcessError, FileNotFoundError):
        console_manager.print_note("kubectl version information not available")
    except Exception as e:
        console_manager.print_note("Error getting version information", error=e)


@cli.command()
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.option("--raw/--no-raw", "raw", is_flag=True, default=None)
@click.option("--show-raw-output/--no-show-raw-output", is_flag=True, default=None)
@click.option("--show-vibe/--no-show-vibe", is_flag=True, default=None)
@click.option("--model", default=None, help="The LLM model to use")
def events(
    args: tuple,
    raw: Optional[bool],
    show_raw_output: Optional[bool],
    show_vibe: Optional[bool],
    model: Optional[str],
) -> None:
    """Display events from the Kubernetes cluster with AI interpretation."""
    # Configure output flags
    (
        show_raw_output,
        show_vibe,
        suppress_output_warning,
        model_name,
    ) = configure_output_flags(raw, show_raw_output, show_vibe, model)

    if args and args[0] == "vibe":
        if len(args) < 2:
            console_manager.print_missing_request_error()
            sys.exit(1)
        request = " ".join(args[1:])
        handle_vibe_request(
            request=request,
            command="get",  # "get" because kubectl events is really "kubectl get events"
            plan_prompt=PLAN_EVENTS_PROMPT,
            summary_prompt=events_prompt(),
            show_raw_output=show_raw_output,
            show_vibe=show_vibe,
            model_name=model_name,
            suppress_output_warning=suppress_output_warning,
        )
        return

    # Construct command: kubectl get events with any additional arguments
    cmd = ["get", "events"]
    cmd.extend(args)

    try:
        output = run_kubectl(cmd, capture=True)
        if not output:
            return

        # Show raw output if requested (before any potential LLM errors)
        if show_raw_output:
            console_manager.print_raw(output)

        # Only proceed with vibe check if requested
        if show_vibe:
            # Process the output to stay within token limits
            llm_output, _ = console_manager.process_output_for_vibe(
                output, MAX_TOKEN_LIMIT, LOGS_TRUNCATION_RATIO
            )

            try:
                llm_model = llm.get_model(model_name)
                prompt = events_prompt().format(output=llm_output)
                response = llm_model.prompt(prompt)
                summary = (
                    response.text() if hasattr(response, "text") else str(response)
                )
                if show_raw_output:
                    # Add newline before vibe check
                    console_manager.console.print()
                console_manager.print_vibe(summary)
            except Exception as e:
                console_manager.print_note("Could not get vibe check", error=e)

    except subprocess.CalledProcessError:
        # Error is already shown by run_kubectl
        sys.exit(1)
    except Exception as e:
        if "No key found" in str(e):
            console_manager.print_missing_api_key_error()
            sys.exit(1)
        else:
            console_manager.print_error(str(e))
            sys.exit(1)


@cli.command()
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.option("--raw/--no-raw", "raw", is_flag=True, default=None)
@click.option("--show-raw-output/--no-show-raw-output", is_flag=True, default=None)
@click.option("--show-vibe/--no-show-vibe", is_flag=True, default=None)
@click.option("--model", default=None, help="The LLM model to use")
def cluster_info(
    args: tuple,
    raw: Optional[bool],
    show_raw_output: Optional[bool],
    show_vibe: Optional[bool],
    model: Optional[str],
) -> None:
    """Display cluster information with AI-generated insights."""
    # Configure output flags
    (
        show_raw_output,
        show_vibe,
        suppress_output_warning,
        model_name,
    ) = configure_output_flags(raw, show_raw_output, show_vibe, model)

    if args and args[0] == "vibe":
        if len(args) < 2:
            console_manager.print_missing_request_error()
            sys.exit(1)
        request = " ".join(args[1:])
        handle_vibe_request(
            request=request,
            command="cluster-info",
            plan_prompt=PLAN_CLUSTER_INFO_PROMPT,
            summary_prompt=cluster_info_prompt(),
            show_raw_output=show_raw_output,
            show_vibe=show_vibe,
            model_name=model_name,
            suppress_output_warning=suppress_output_warning,
        )
        return

    # Default is to run 'cluster-info dump' or specific args if provided
    cmd = ["cluster-info"]
    if args:
        cmd.extend(args)
    else:
        # No arguments means basic cluster-info, not dump
        # cmd.append("dump")  # Removed to match kubectl behavior
        pass

    try:
        output = run_kubectl(cmd, capture=True)
        if not output:
            return

        # Show raw output if requested (before any potential LLM errors)
        if show_raw_output:
            console_manager.print_raw(output)

        # Only proceed with vibe check if requested
        if show_vibe:
            # Process the output to stay within token limits
            llm_output, _ = console_manager.process_output_for_vibe(
                output, MAX_TOKEN_LIMIT, LOGS_TRUNCATION_RATIO
            )

            try:
                llm_model = llm.get_model(model_name)

                # Use fresh cluster info prompt with current datetime
                prompt = cluster_info_prompt().format(output=llm_output)

                response = llm_model.prompt(prompt)
                summary = (
                    response.text() if hasattr(response, "text") else str(response)
                )
                if show_raw_output:
                    # Add newline before vibe check
                    console_manager.console.print()
                console_manager.print_vibe(summary)
            except Exception as e:
                console_manager.print_note("Could not get vibe check", error=e)

    except Exception as e:
        if "No key found" in str(e):
            console_manager.print_missing_api_key_error()
            sys.exit(1)
        else:
            console_manager.print_error(str(e))
            sys.exit(1)


def configure_output_flags(
    raw: Optional[bool] = None,
    show_raw_output: Optional[bool] = None,
    show_vibe: Optional[bool] = None,
    model: Optional[str] = None,
) -> Tuple[bool, bool, bool, str]:
    """Configure output flags based on CLI options and config values.

    Args:
        raw: Raw flag (for backward compatibility)
        show_raw_output: Whether to show raw output
        show_vibe: Whether to show vibe output
        model: LLM model to use

    Returns:
        Tuple of (show_raw_output, show_vibe, suppress_output_warning, model_name)
    """
    config = Config()
    model_name = model or config.get("model", DEFAULT_MODEL)

    # Handle raw flag for backward compatibility
    if raw is not None:
        show_raw_output = raw

    # Use config values if flags are not provided
    if show_raw_output is None:
        show_raw_output = config.get("show_raw_output", DEFAULT_SHOW_RAW_OUTPUT)
    if show_vibe is None:
        show_vibe = config.get("show_vibe", DEFAULT_SHOW_VIBE)
    suppress_output_warning = config.get(
        "suppress_output_warning", DEFAULT_SUPPRESS_OUTPUT_WARNING
    )

    # Ensure we have boolean types, not Optional[bool]
    show_raw_output = bool(show_raw_output)
    show_vibe = bool(show_vibe)
    suppress_output_warning = bool(suppress_output_warning)

    # Show warning if no output will be shown, but continue execution
    if not show_raw_output and not show_vibe and not suppress_output_warning:
        console_manager.print_no_output_warning()

    return show_raw_output, show_vibe, suppress_output_warning, model_name


def main() -> NoReturn:
    """Entry point for the CLI"""
    sys.exit(cli())


if __name__ == "__main__":
    main()
