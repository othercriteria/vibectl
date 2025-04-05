"""
Console management for vibectl.

Provides utility functions and classes for managing console output,
error handling, and formatting for vibectl commands.
"""

from typing import Any, Dict, Optional, Tuple

from rich.console import Console
from rich.table import Table


class ConsoleManager:
    """Manages console output and error handling for vibectl."""

    def __init__(self) -> None:
        """Initialize the console manager with stdout and stderr consoles."""
        self.console = Console()
        self.error_console = Console(stderr=True)

    def print(
        self,
        message: str,
        markup: bool = True,
        highlight: bool = False,
        end: str = "\n",
    ) -> None:
        """Print a message to the standard console."""
        self.console.print(message, markup=markup, highlight=highlight, end=end)

    def print_raw(self, message: str, end: str = "") -> None:
        """Print raw output without markup or highlighting."""
        self.console.print(message, markup=False, highlight=False, end=end)

    def print_error(self, message: str, end: str = "\n") -> None:
        """Print an error message to the error console."""
        self.error_console.print(f"[bold red]Error:[/bold red] {message}", end=end)

    def print_warning(self, message: str, end: str = "\n") -> None:
        """Print a warning message to the error console."""
        self.error_console.print(f"[yellow]Warning:[/yellow] {message}", end=end)

    def print_note(
        self, message: str, error: Optional[Exception] = None, end: str = "\n"
    ) -> None:
        """Print a note message to the error console, optionally with an error."""
        if error:
            self.error_console.print(
                f"[yellow]Note:[/yellow] {message}: [red]{error}[/red]", end=end
            )
        else:
            self.error_console.print(f"[yellow]Note:[/yellow] {message}", end=end)

    def print_vibe_header(self) -> None:
        """Print the vibe check header."""
        self.console.print("[bold green]✨ Vibe check:[/bold green]")

    def print_vibe(self, summary: str) -> None:
        """Print a vibe check summary."""
        self.print_vibe_header()
        self.console.print(summary, markup=True, highlight=False)

    def print_no_output_warning(self) -> None:
        """Print a warning about no output being enabled."""
        self.print_warning(
            "Neither raw output nor vibe output is enabled. "
            "Use --show-raw-output or --show-vibe to see output."
        )

    def print_truncation_warning(self) -> None:
        """Print a warning about output being truncated for AI processing."""
        self.print_warning(
            "Output is too large for AI processing. "
            "Using truncated output for vibe check."
        )

    def print_missing_api_key_error(self) -> None:
        """Print an error message about missing API key."""
        self.print_error(
            "Missing API key. "
            "Please set the API key using 'export ANTHROPIC_API_KEY=your-api-key' "
            "or configure it using 'llm keys set anthropic'"
        )

    def print_missing_request_error(self) -> None:
        """Print an error message about missing request after 'vibe'."""
        self.print_error("Missing request after 'vibe'")

    def print_config_table(self, config_data: Dict[str, Any]) -> None:
        """Print a table showing configuration data."""
        # Create table with title
        table = Table(
            title="vibectl Configuration", show_header=True, title_justify="center"
        )
        table.add_column("Key", style="bold")
        table.add_column("Value")

        # Add rows for each config item
        for key, value in config_data.items():
            table.add_row(str(key), str(value))

        self.console.print(table)

    def print_success(self, message: str) -> None:
        """Print a success message."""
        self.console.print(f"[green]✓[/] {message}")

    def handle_vibe_output(
        self,
        output: str,
        show_raw_output: bool,
        show_vibe: bool,
        summary: Optional[str] = None,
    ) -> None:
        """Handle displaying vibe output based on configuration."""
        if show_raw_output:
            self.print_raw(output)
            # Add a newline if we're going to show the vibe check too
            if show_vibe:
                self.console.print()

        if show_vibe and summary:
            self.print_vibe(summary)

    def process_output_for_vibe(
        self, output: str, max_token_limit: int, truncation_ratio: int
    ) -> Tuple[str, bool]:
        """Process output to ensure it stays within token limits for LLM.

        Args:
            output: The raw output to process
            max_token_limit: Maximum token limit
            truncation_ratio: Ratio for chunking the truncated output

        Returns:
            Tuple containing (processed_output, was_truncated)
        """
        # Check token count for LLM
        output_len = len(output)
        token_estimate = output_len / 4
        was_truncated = False

        if token_estimate > max_token_limit:
            # Take first and last portions, omitting middle
            chunk_size = int(
                max_token_limit / truncation_ratio * 4
            )  # Convert back to chars
            truncated_output = (
                f"{output[:chunk_size]}\n"
                f"[...truncated {output_len - 2 * chunk_size} characters...]\n"
                f"{output[-chunk_size:]}"
            )
            self.print_truncation_warning()
            was_truncated = True
            return truncated_output, was_truncated

        return output, was_truncated


# Create global instance for easy import
console_manager = ConsoleManager()
