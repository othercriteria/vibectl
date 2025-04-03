"""
Command-line interface for vibectl.

Provides a vibes-based alternative to kubectl, using AI to generate human-friendly
summaries of Kubernetes resources. Each command aims to make cluster management
more intuitive while preserving access to raw kubectl output when needed.
"""

import subprocess
import sys
from typing import List, NoReturn, Optional

import click
import llm
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from . import __version__
from .config import Config
from .prompt import DESCRIBE_RESOURCE_PROMPT, GET_RESOURCE_PROMPT, LOGS_PROMPT

console = Console()
error_console = Console(stderr=True)

# Arbitrary token limit to prevent OOM issues with LLM processing
# Using a conservative estimate of 4 chars per token
MAX_TOKEN_LIMIT = 10000

# For logs, we'll show first and last third when output is too large
LOGS_TRUNCATION_RATIO = 3


def run_kubectl(args: List[str], capture: bool = False) -> Optional[str]:
    """Run kubectl with the given arguments.

    Args:
        args: List of arguments to pass to kubectl
        capture: Whether to capture and return the output (True) or print it (False)

    Returns:
        The command output if capture=True, None otherwise

    Raises:
        SystemExit: If kubectl is not found or returns an error
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
        error_console.print(f"[bold red]Error:[/] {e.stderr}")
        sys.exit(1)
    except FileNotFoundError:
        error_console.print("[bold red]Error:[/] kubectl not found in PATH")
        sys.exit(1)


@click.group()
@click.version_option()
def cli() -> None:
    """vibectl - A vibes-based alternative to kubectl"""
    pass


@cli.command(context_settings={"ignore_unknown_options": True})
@click.argument("resource")
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.option("--raw", is_flag=True, help="Show raw kubectl output")
def get(resource: str, args: tuple, raw: bool) -> None:
    """Get Kubernetes resources with a vibe-based summary.

    Runs 'kubectl get' and uses AI to generate a human-friendly summary of the
    resources. Supports all standard kubectl get arguments and options.

    Examples:
        vibectl get pods
        vibectl get deployments -n kube-system
        vibectl get pods --raw
    """
    # Get the configured model
    cfg = Config()
    model_name = cfg.get("llm_model") or "claude-3.7-sonnet"
    show_raw = raw or cfg.get("show_raw_output")

    # Run kubectl get and capture the output
    cmd = ["get", resource]
    if args:
        # Convert tuple to list and ensure all items are strings
        args_list = [str(arg) for arg in args]
        cmd.extend(args_list)
    output = run_kubectl(cmd, capture=True)
    if not output:
        return

    # Print the raw output if requested
    if show_raw:
        console.print(output, markup=False, highlight=False)
        console.print()  # Add a blank line for readability

    # Use LLM to summarize
    try:
        model = llm.get_model(model_name)
        prompt = GET_RESOURCE_PROMPT.format(output=output)
        response = model.prompt(prompt)
        summary = response.text() if hasattr(response, "text") else str(response)
        if show_raw:
            console.print("[bold green]✨ Vibe check:[/bold green]")
        console.print(summary, markup=True, highlight=False)
    except Exception as e:
        # Always show raw output when LLM fails
        if not show_raw:
            console.print(output, markup=False, highlight=False)
            console.print()  # Add a blank line for readability
        error_console.print(
            f"[yellow]Note:[/yellow] Could not get vibe check: [red]{e}[/red]"
        )


@cli.command()
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def proxy(args: tuple) -> None:
    """Proxy commands directly to kubectl.

    Passes all arguments directly to kubectl without any processing.
    Useful for commands not yet supported by vibectl.
    """
    if not args:
        console.print("Usage: vibectl proxy <kubectl commands>")
        sys.exit(1)
    run_kubectl(list(args))


@cli.group()
def config() -> None:
    """Manage vibectl configuration"""
    pass


@config.command(name="set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str) -> None:
    """Set a configuration value.

    Available keys:
        kubeconfig: Path to kubeconfig file
        llm_model: Name of the LLM model to use
        show_raw_output: Whether to always show raw kubectl output
    """
    cfg = Config()
    cfg.set(key, value)
    console.print(f"[green]✓[/] Set {key} to {value}")


@config.command(name="show")
def config_show() -> None:
    """Show current configuration.

    Displays all configured values in a table format.
    """
    cfg = Config()

    table = Table(title="vibectl Configuration")
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="green")

    for key, value in cfg.show().items():
        table.add_row(key, str(value))

    console.print(table)


@cli.command()
def vibe() -> None:
    """Check the current vibe of your cluster"""
    console.print("✨ [bold green]Checking cluster vibes...[/]")
    # TODO: Implement cluster vibe checking


@cli.command()
def version() -> None:
    """Display vibectl version information.

    Shows both vibectl version and kubectl client version for reference.
    """
    console.print(f"vibectl version [bold green]{__version__}[/]")

    # Show kubectl version for reference
    try:
        result = subprocess.run(
            ["kubectl", "version", "--client", "--output=json"],
            check=True,
            text=True,
            capture_output=True,
        )
        console.print("\nkubectl client version:")
        console.print_json(result.stdout)
    except (subprocess.CalledProcessError, FileNotFoundError):
        console.print("\n[yellow]Note:[/] kubectl version information not available")


@cli.command(context_settings={"ignore_unknown_options": True})
@click.argument("resource")
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.option("--raw", is_flag=True, help="Show raw kubectl output")
def describe(resource: str, args: tuple, raw: bool) -> None:
    """Describe Kubernetes resources with a vibe-based summary.

    Runs 'kubectl describe' and uses AI to generate a concise, human-friendly
    summary focusing on the most important details and any issues that need
    attention. Supports all standard kubectl describe arguments and options.

    The output is limited to prevent memory issues with very large resources.
    If the output is too large, you'll be prompted to describe a more specific
    resource.

    Examples:
        vibectl describe pod my-pod
        vibectl describe deployment my-deployment -n kube-system
        vibectl describe pod my-pod --raw
    """
    # Get the configured model
    cfg = Config()
    model_name = cfg.get("llm_model") or "claude-3.7-sonnet"
    show_raw = raw or cfg.get("show_raw_output")

    # Run kubectl describe and capture the output
    cmd = ["describe", resource]
    if args:
        # Convert tuple to list and ensure all items are strings
        args_list = [str(arg) for arg in args]
        cmd.extend(args_list)
    output = run_kubectl(cmd, capture=True)
    if not output:
        return

    # Check token count (rough estimate: 4 chars per token)
    if len(output) / 4 > MAX_TOKEN_LIMIT:
        error_console.print(
            "[yellow]Warning:[/] Output is too large for AI processing. "
            "Please try describing a more specific resource."
        )
        if show_raw:
            # Write raw output without any processing
            console.file.write(output)
        return

    # Print the raw output if requested
    if show_raw:
        # Write raw output without any processing
        console.file.write(output)
        console.print()  # Add a blank line for readability

    # Use LLM to summarize with progress indicator
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]Getting the vibe...[/bold blue]"),
            console=console,
            transient=True,
        ) as progress:
            progress.add_task("summarize", total=None)
            model = llm.get_model(model_name)
            prompt = DESCRIBE_RESOURCE_PROMPT.format(output=output)
            response = model.prompt(prompt)
            summary = response.text() if hasattr(response, "text") else str(response)

        if show_raw:
            console.print("[bold green]✨ Vibe check:[/bold green]")
        console.print(summary, markup=True, highlight=False)
    except Exception as e:
        # Always show raw output when LLM fails
        if not show_raw:
            # Write raw output without any processing
            console.file.write(output)
            console.print()  # Add a blank line for readability
        error_console.print(
            f"[yellow]Note:[/yellow] Could not get vibe check: [red]{e}[/red]"
        )


@cli.command(context_settings={"ignore_unknown_options": True})
@click.argument("resource")
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.option("--raw", is_flag=True, help="Show raw kubectl output")
def logs(resource: str, args: tuple, raw: bool) -> None:
    """Get container logs with a vibe-based summary.

    Runs 'kubectl logs' and uses AI to generate a concise, human-friendly summary
    focusing on key events, patterns, errors, and notable state changes. Supports
    all standard kubectl logs arguments and options.

    For large log outputs, shows a summary of the first and last portions to
    maintain context while staying within memory limits.

    Examples:
        vibectl logs pod/my-pod
        vibectl logs deployment/my-deployment -n kube-system
        vibectl logs pod/my-pod -c my-container --raw
    """
    # Get the configured model
    cfg = Config()
    model_name = cfg.get("llm_model") or "claude-3.7-sonnet"
    show_raw = raw or cfg.get("show_raw_output")

    # Run kubectl logs and capture the output
    cmd = ["logs", resource]
    if args:
        # Convert tuple to list and ensure all items are strings
        args_list = [str(arg) for arg in args]
        cmd.extend(args_list)
    output = run_kubectl(cmd, capture=True)
    if not output:
        return

    # Print the raw output if requested
    if show_raw:
        # Write raw output without any processing
        console.file.write(output)
        console.print()  # Add a blank line for readability

    # Check token count and handle large outputs
    output_len = len(output)
    token_estimate = output_len / 4
    if token_estimate > MAX_TOKEN_LIMIT:
        # For large outputs, take first and last third
        chunk_size = int(
            MAX_TOKEN_LIMIT / LOGS_TRUNCATION_RATIO * 4
        )  # Convert back to chars
        truncated_output = (
            f"{output[:chunk_size]}\n"
            f"[...truncated {output_len - 2*chunk_size} characters...]\n"
            f"{output[-chunk_size:]}"
        )
        output = truncated_output

    # Use LLM to summarize with progress indicator
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]Getting the vibe...[/bold blue]"),
            console=console,
            transient=True,
        ) as progress:
            progress.add_task("summarize", total=None)
            model = llm.get_model(model_name)
            prompt = LOGS_PROMPT.format(output=output)
            response = model.prompt(prompt)
            summary = response.text() if hasattr(response, "text") else str(response)

        if show_raw:
            console.print("[bold green]✨ Vibe check:[/bold green]")
        console.print(summary, markup=True, highlight=False)
    except Exception as e:
        # Always show raw output when LLM fails
        if not show_raw:
            # Write raw output without any processing
            console.file.write(output)
            console.print()  # Add a blank line for readability
        error_console.print(
            f"[yellow]Note:[/yellow] Could not get vibe check: [red]{e}[/red]"
        )


def main() -> NoReturn:
    """Entry point for the CLI"""
    sys.exit(cli())


if __name__ == "__main__":
    main()
