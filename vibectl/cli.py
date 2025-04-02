"""
Command-line interface for vibectl
"""

import subprocess
import sys
from typing import List, NoReturn

import click
from rich.console import Console
from rich.table import Table

from . import __version__
from .config import Config

console = Console()
error_console = Console(stderr=True)


def run_kubectl(args: List[str]) -> None:
    """Run kubectl with the given arguments"""
    try:
        cmd = ["kubectl"]

        # Add kubeconfig if configured
        cfg = Config()
        kubeconfig = cfg.get("kubeconfig")
        if kubeconfig:
            cmd.extend(["--kubeconfig", kubeconfig])

        cmd.extend(args)

        result = subprocess.run(cmd, check=True, text=True, capture_output=True)
        if result.stdout:
            # Disable markup and highlighting for kubectl output
            console.print(result.stdout, end="", markup=False, highlight=False)
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


@cli.command()
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def proxy(args: tuple) -> None:
    """Proxy commands directly to kubectl"""
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
    """Set a configuration value"""
    cfg = Config()
    cfg.set(key, value)
    console.print(f"[green]✓[/] Set {key} to {value}")


@config.command(name="show")
def config_show() -> None:
    """Show current configuration"""
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
    """Display vibectl version information"""
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


def main() -> NoReturn:
    """Entry point for the CLI"""
    sys.exit(cli())


if __name__ == "__main__":
    main()
