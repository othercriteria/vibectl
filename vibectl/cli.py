"""
Command-line interface for vibectl.

Provides a vibes-based alternative to kubectl, using AI to generate human-friendly
summaries of Kubernetes resources. Each command aims to make cluster management
more intuitive while preserving access to raw kubectl output when needed.
"""

import json
import subprocess
import sys
from typing import List, NoReturn, Optional

import click
import llm
from rich.console import Console
from rich.table import Table

from .config import Config
from .prompt import (
    CREATE_RESOURCE_PROMPT,
    DESCRIBE_RESOURCE_PROMPT,
    GET_RESOURCE_PROMPT,
    LOGS_PROMPT,
    PLAN_CREATE_PROMPT,
    PLAN_DESCRIBE_PROMPT,
    PLAN_GET_PROMPT,
    PLAN_LOGS_PROMPT,
)

console = Console()
error_console = Console(stderr=True)

# Constants
MAX_TOKEN_LIMIT = 10000
LOGS_TRUNCATION_RATIO = 3
DEFAULT_MODEL = "claude-3.7-sonnet"
DEFAULT_SHOW_RAW_OUTPUT = False
DEFAULT_SHOW_VIBE = True
DEFAULT_SUPPRESS_OUTPUT_WARNING = False

# Prompt for version command
VERSION_PROMPT = """Interpret this Kubernetes version information in a human-friendly way.
Highlight important details like version compatibility, deprecation notices, or update recommendations.

Format your response using rich.Console() markup syntax with matched closing tags:
- [bold]Version numbers and key details[/bold] for emphasis
- [green]Compatible or up-to-date components[/green] for positive states
- [yellow]Warnings or deprecation notices[/yellow] for concerning states
- [red]Critical issues or incompatibilities[/red] for problems
- [blue]Kubernetes components[/blue] for k8s terms
- [italic]Build dates and release info[/italic] for timing information

Here's the version information:
{version_info}"""


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
            console.print(result.stdout, end="", markup=False, highlight=False)
        return None
    except subprocess.CalledProcessError as e:
        error_console.print(f"[bold red]Error:[/] {e.stderr}", end="")
        raise  # Re-raise the original error
    except FileNotFoundError:
        error_console.print("[bold red]Error:[/] kubectl not found in PATH")
        raise


@click.group()
@click.version_option()
def cli() -> None:
    """vibectl - A vibes-based alternative to kubectl"""
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
            error_console.print(
                "[yellow]Warning:[/yellow] Neither raw output nor vibe output is enabled. "
                "Use --show-raw-output or --show-vibe to see output."
            )

        # Get the plan from LLM
        llm_model = llm.get_model(model_name)
        prompt = plan_prompt.format(request=request)
        response = llm_model.prompt(prompt)
        plan = response.text() if hasattr(response, "text") else str(response)

        # Check for error responses from planner
        if isinstance(plan, str) and plan.startswith("ERROR:"):
            error_console.print(f"[bold red]Error:[/bold red] {plan[7:]}")
            sys.exit(1)

        # Extract kubectl command from plan
        kubectl_args = []
        for line in plan.split("\n"):
            if line == "---":
                break
            kubectl_args.append(line)

        # Validate plan format
        if not kubectl_args:
            error_console.print(
                "[bold red]Error:[/bold red] Invalid response format from planner"
            )
            sys.exit(1)

        # Run kubectl command
        try:
            output = run_kubectl([command, *kubectl_args], capture=True)
        except subprocess.CalledProcessError as e:
            # If kubectl fails, error is already shown by run_kubectl
            if show_raw_output:
                console.print(str(e), markup=False, highlight=False)
            sys.exit(1)

        # If no output, nothing to do
        if not output:
            return

        # Show raw output if requested
        if show_raw_output:
            console.print(output, markup=False, highlight=False, end="")

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
                error_console.print(
                    "[yellow]Warning:[/yellow] Output is too large for AI processing. "
                    "Using truncated output for vibe check."
                )

            try:
                prompt = summary_prompt.format(output=llm_output)
                response = llm_model.prompt(prompt)
                summary = (
                    response.text() if hasattr(response, "text") else str(response)
                )
                if show_raw_output:
                    console.print()  # Add newline between raw output and vibe check
                console.print("[bold green]✨ Vibe check:[/bold green]")
                console.print(summary, markup=True, highlight=False)
            except Exception as e:
                error_console.print(
                    f"[yellow]Note:[/yellow] Could not get vibe check: [red]{e}[/red]"
                )

    except Exception as e:
        if "No key found" in str(e):
            error_console.print(
                "[bold red]Error:[/bold red] Missing API key. "
                "Please set the API key using 'export ANTHROPIC_API_KEY=your-api-key' "
                "or configure it using 'llm keys set anthropic'"
            )
            sys.exit(1)
        else:
            error_console.print(f"[bold red]Error:[/bold red] {e}")
            sys.exit(1)


@cli.command()
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.option("--raw/--no-raw", "raw", is_flag=True, default=None)
@click.option("--show-raw-output/--no-show-raw-output", is_flag=True, default=None)
@click.option("--show-vibe/--no-show-vibe", is_flag=True, default=None)
@click.option("--model", default=None, help="The LLM model to use")
@click.option("--namespace", "-n", default=None, help="Namespace")
def get(
    resource: str,
    args: tuple,
    raw: Optional[bool],
    show_raw_output: Optional[bool],
    show_vibe: Optional[bool],
    model: Optional[str],
    namespace: Optional[str],
) -> None:
    """Get information about Kubernetes resources."""
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
        error_console.print(
            "[yellow]Warning:[/yellow] Neither raw output nor vibe output is enabled. "
            "Use --show-raw-output or --show-vibe to see output."
        )

    if resource == "vibe":
        if not args:
            error_console.print(
                "[bold red]Error:[/bold red] Missing request after 'vibe'"
            )
            sys.exit(1)
        request = " ".join(args)
        handle_vibe_request(
            request=request,
            command="get",
            plan_prompt=PLAN_GET_PROMPT,
            summary_prompt=GET_RESOURCE_PROMPT,
            show_raw_output=show_raw_output,
            show_vibe=show_vibe,
            model_name=model_name,
            suppress_output_warning=suppress_output_warning,
        )
        return

    cmd = ["get", resource]
    if namespace:
        cmd.extend(["-n", namespace])
    cmd.extend(args)

    try:
        output = run_kubectl(cmd, capture=True)
        if not output:
            return

        # Show raw output if requested (before any potential LLM errors)
        if show_raw_output:
            console.print(output, markup=False, highlight=False, end="")

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
                error_console.print(
                    "[yellow]Warning:[/yellow] Output is too large for AI processing. "
                    "Using truncated output for vibe check."
                )

            try:
                llm_model = llm.get_model(model_name)
                prompt = GET_RESOURCE_PROMPT.format(output=llm_output)
                response = llm_model.prompt(prompt)
                summary = (
                    response.text() if hasattr(response, "text") else str(response)
                )
                if show_raw_output:
                    console.print()  # Add newline between raw output and vibe check
                console.print("[bold green]✨ Vibe check:[/bold green]")
                console.print(summary, markup=True, highlight=False)
            except Exception as e:
                error_console.print(
                    f"[yellow]Note:[/yellow] Could not get vibe check: [red]{e}[/red]"
                )

    except Exception as e:
        if "No key found" in str(e):
            error_console.print(
                "[bold red]Error:[/bold red] Missing API key. "
                "Please set the API key using 'export ANTHROPIC_API_KEY=your-api-key' "
                "or configure it using 'llm keys set anthropic'"
            )
            sys.exit(1)
        else:
            error_console.print(f"[bold red]Error:[/bold red] {e}")
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
        error_console.print(
            "[yellow]Warning:[/yellow] Neither raw output nor vibe output is enabled. "
            "Use --show-raw-output or --show-vibe to see output."
        )

    if resource == "vibe":
        if not args:
            error_console.print(
                "[bold red]Error:[/bold red] Missing request after 'vibe'"
            )
            sys.exit(1)
        request = " ".join(args)
        handle_vibe_request(
            request=request,
            command="describe",
            plan_prompt=PLAN_DESCRIBE_PROMPT,
            summary_prompt=DESCRIBE_RESOURCE_PROMPT,
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
            console.print(output, markup=False, highlight=False, end="")

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
                error_console.print(
                    "[yellow]Warning:[/yellow] Output is too large for AI processing. "
                    "Using truncated output for vibe check."
                )

            try:
                llm_model = llm.get_model(model_name)
                prompt = DESCRIBE_RESOURCE_PROMPT.format(output=llm_output)
                response = llm_model.prompt(prompt)
                summary = (
                    response.text() if hasattr(response, "text") else str(response)
                )
                if show_raw_output:
                    console.print()  # Add newline between raw output and vibe check
                console.print("[bold green]✨ Vibe check:[/bold green]")
                console.print(summary, markup=True, highlight=False)
            except Exception as e:
                error_console.print(
                    f"[yellow]Note:[/yellow] Could not get vibe check: [red]{e}[/red]"
                )

    except Exception as e:
        if "No key found" in str(e):
            error_console.print(
                "[bold red]Error:[/bold red] Missing API key. "
                "Please set the API key using 'export ANTHROPIC_API_KEY=your-api-key' "
                "or configure it using 'llm keys set anthropic'"
            )
            sys.exit(1)
        else:
            error_console.print(f"[bold red]Error:[/bold red] {e}")
            sys.exit(1)


@cli.command()
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.option("--raw/--no-raw", "raw", is_flag=True, default=None)
@click.option("--show-raw-output/--no-show-raw-output", is_flag=True, default=None)
@click.option("--show-vibe/--no-show-vibe", is_flag=True, default=None)
@click.option("--model", default=None, help="The LLM model to use")
@click.option("--container", "-c", default=None, help="Container name")
def logs(
    resource: str,
    args: tuple,
    raw: Optional[bool],
    show_raw_output: Optional[bool],
    show_vibe: Optional[bool],
    model: Optional[str],
    container: Optional[str],
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
        error_console.print(
            "[yellow]Warning:[/yellow] Neither raw output nor vibe output is enabled. "
            "Use --show-raw-output or --show-vibe to see output."
        )

    if resource == "vibe":
        if not args:
            error_console.print(
                "[bold red]Error:[/bold red] Missing request after 'vibe'"
            )
            sys.exit(1)
        request = " ".join(args)
        handle_vibe_request(
            request=request,
            command="logs",
            plan_prompt=PLAN_LOGS_PROMPT,
            summary_prompt=LOGS_PROMPT,
            show_raw_output=show_raw_output,
            show_vibe=show_vibe,
            model_name=model_name,
            suppress_output_warning=suppress_output_warning,
        )
        return

    cmd = ["logs", resource]
    if container:
        cmd.extend(["-c", container])
    cmd.extend(args)

    try:
        output = run_kubectl(cmd, capture=True)
        if not output:
            return

        # Show raw output if requested (before any potential LLM errors)
        if show_raw_output:
            console.print(output, markup=False, highlight=False, end="")

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
                error_console.print(
                    "[yellow]Warning:[/yellow] Output is too large for AI processing. "
                    "Using truncated output for vibe check."
                )

            try:
                llm_model = llm.get_model(model_name)
                prompt = LOGS_PROMPT.format(output=llm_output)
                response = llm_model.prompt(prompt)
                summary = (
                    response.text() if hasattr(response, "text") else str(response)
                )
                if show_raw_output:
                    console.print()  # Add newline between raw output and vibe check
                console.print("[bold green]✨ Vibe check:[/bold green]")
                console.print(summary, markup=True, highlight=False)
            except Exception as e:
                error_console.print(
                    f"[yellow]Note:[/yellow] Could not get vibe check: [red]{e}[/red]"
                )

    except Exception as e:
        if "No key found" in str(e):
            error_console.print(
                "[bold red]Error:[/bold red] Missing API key. "
                "Please set the API key using 'export ANTHROPIC_API_KEY=your-api-key' "
                "or configure it using 'llm keys set anthropic'"
            )
            sys.exit(1)
        else:
            error_console.print(f"[bold red]Error:[/bold red] {e}")
            sys.exit(1)


@cli.command()
@click.argument("resource", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.option("--raw/--no-raw", "raw", is_flag=True, default=None)
@click.option("--show-raw-output/--no-show-raw-output", is_flag=True, default=None)
@click.option("--show-vibe/--no-show-vibe", is_flag=True, default=None)
@click.option("--model", default=None, help="The LLM model to use")
@click.option("--image", default=None, help="Container image")
@click.option("--namespace", "-n", default=None, help="Namespace")
def create(
    resource: str,
    args: tuple,
    raw: Optional[bool],
    show_raw_output: Optional[bool],
    show_vibe: Optional[bool],
    model: Optional[str],
    image: Optional[str],
    namespace: Optional[str],
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
        error_console.print(
            "[yellow]Warning:[/yellow] Neither raw output nor vibe output is enabled. "
            "Use --show-raw-output or --show-vibe to see output."
        )

    if resource == "vibe":
        if not args:
            error_console.print(
                "[bold red]Error:[/bold red] Missing request after 'vibe'"
            )
            sys.exit(1)
        request = " ".join(args)
        handle_vibe_request(
            request=request,
            command="create",
            plan_prompt=PLAN_CREATE_PROMPT,
            summary_prompt=CREATE_RESOURCE_PROMPT,
            show_raw_output=show_raw_output,
            show_vibe=show_vibe,
            model_name=model_name,
            suppress_output_warning=suppress_output_warning,
        )
        return

    cmd = ["create", resource]
    if image:
        cmd.extend(["--image", image])
    if namespace:
        cmd.extend(["-n", namespace])
    cmd.extend(args)

    try:
        output = run_kubectl(cmd, capture=True)
        if not output:
            return

        # Show raw output if requested (before any potential LLM errors)
        if show_raw_output:
            console.print(output, markup=False, highlight=False, end="")

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
                error_console.print(
                    "[yellow]Warning:[/yellow] Output is too large for AI processing. "
                    "Using truncated output for vibe check."
                )

            try:
                llm_model = llm.get_model(model_name)
                prompt = CREATE_RESOURCE_PROMPT.format(output=llm_output)
                response = llm_model.prompt(prompt)
                summary = (
                    response.text() if hasattr(response, "text") else str(response)
                )
                if show_raw_output:
                    console.print()  # Add newline between raw output and vibe check
                console.print("[bold green]✨ Vibe check:[/bold green]")
                console.print(summary, markup=True, highlight=False)
            except Exception as e:
                error_console.print(
                    f"[yellow]Note:[/yellow] Could not get vibe check: [red]{e}[/red]"
                )

    except Exception as e:
        if "No key found" in str(e):
            error_console.print(
                "[bold red]Error:[/bold red] Missing API key. "
                "Please set the API key using 'export ANTHROPIC_API_KEY=your-api-key' "
                "or configure it using 'llm keys set anthropic'"
            )
            sys.exit(1)
        else:
            error_console.print(f"[bold red]Error:[/bold red] {e}")
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
        console.print("Usage: vibectl just <kubectl commands>")
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
        show_vibe: Whether to show vibe summaries by default (default: true)
        suppress_output_warning: Whether to suppress warning when no output is shown (default: false)
    """
    cfg = Config()

    # Convert string boolean values
    if key in ["show_raw_output", "show_vibe", "suppress_output_warning"]:
        value = str(value.lower() == "true").lower()

    # Validate model name
    if key == "llm_model" and value not in ["claude-3.7-sonnet"]:
        error_console.print(
            "[bold red]Error:[/bold red] Invalid model name. "
            "Currently supported models: claude-3.7-sonnet"
        )
        sys.exit(1)

    cfg.set(key, value)
    console.print(f"[green]✓[/] Set {key} to {value}")


@config.command()
def show() -> None:
    """Show current configuration."""
    cfg = Config()
    config_data = cfg.show()

    # Create table with title
    table = Table(
        title="vibectl Configuration", show_header=True, title_justify="center"
    )
    table.add_column("Key", style="bold")
    table.add_column("Value")

    # Add rows for each config item
    for key, value in config_data.items():
        table.add_row(str(key), str(value))

    console.print(table)


@cli.command()
def vibe() -> None:
    """Check the current vibe of your cluster."""
    console.print("✨ [bold green]Checking cluster vibes...[/]")
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
        prompt = VERSION_PROMPT.format(version_info=version_info)
        response = llm_model.prompt(prompt)
        interpretation = response.text() if hasattr(response, "text") else str(response)
        console.print(interpretation, markup=True, highlight=False)

    except (subprocess.CalledProcessError, FileNotFoundError):
        msg = "\n[yellow]Note:[/yellow] kubectl version information not available"
        error_console.print(msg)
    except Exception as e:
        msg = (
            f"\n[yellow]Note:[/yellow] Error getting version information: "
            f"[red]{e}[/red]"
        )
        error_console.print(msg)


def main() -> NoReturn:
    """Entry point for the CLI"""
    sys.exit(cli())


if __name__ == "__main__":
    main()
