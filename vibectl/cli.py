"""
Command-line interface for vibectl
"""
from typing import NoReturn

import click
from rich.console import Console

console = Console()

@click.group()
@click.version_option()
def cli() -> None:
    """vibectl - A vibes-based alternative to kubectl"""
    pass

@cli.command()
def vibe() -> None:
    """Check the current vibe of your cluster"""
    console.print("✨ [bold green]Checking cluster vibes...[/]")
    # TODO: Implement cluster vibe checking

def main() -> NoReturn:
    """Entry point for the CLI"""
    cli()

if __name__ == "__main__":
    main() 