"""
Command-line interface for vibectl
"""

import sys
import subprocess
from typing import NoReturn, Optional, List

import click
from rich.console import Console

console = Console()
error_console = Console(stderr=True)


def run_kubectl(args: List[str]) -> None:
    """Run kubectl with the given arguments"""
    try:
        result = subprocess.run(
            ["kubectl"] + args,
            check=True,
            text=True,
            capture_output=True
        )
        if result.stdout:
            # Disable markup and highlighting for kubectl output
            console.print(result.stdout, end="", markup=False, highlight=False)
    except subprocess.CalledProcessError as e:
        error_console.print(f"[bold red]Error:[/] {e.stderr}")
        sys.exit(1)
    except FileNotFoundError:
        error_console.print("[bold red]Error:[/] kubectl not found in PATH")
        sys.exit(1)


@click.group(invoke_without_command=True, context_settings={"ignore_unknown_options": True})
@click.version_option()
@click.option("--no-vibes", is_flag=True, help="Disable vibes and proxy directly to kubectl")
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def cli(ctx: click.Context, no_vibes: bool, args: tuple) -> None:
    """vibectl - A vibes-based alternative to kubectl"""
    ctx.ensure_object(dict)
    ctx.obj["NO_VIBES"] = no_vibes

    if no_vibes:
        if args:
            run_kubectl(list(args))
        else:
            console.print("Usage: vibectl --no-vibes <kubectl commands>")
            sys.exit(1)
    elif ctx.invoked_subcommand is None:
        ctx.invoke(vibe)


@cli.command()
def vibe() -> None:
    """Check the current vibe of your cluster"""
    console.print("✨ [bold green]Checking cluster vibes...[/]")
    # TODO: Implement cluster vibe checking


def main() -> NoReturn:
    """Entry point for the CLI"""
    sys.exit(cli())


if __name__ == "__main__":
    main()
