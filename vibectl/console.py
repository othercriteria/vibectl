"""
Console UI for vibectl.

This module provides console UI functionality for vibectl.
"""

from typing import Any

from rich.console import Console
from rich.errors import MarkupError
from rich.table import Table
from rich.theme import Theme


class ConsoleManager:
    """Manage console output for vibectl."""

    def __init__(self) -> None:
        """Initialize the console manager."""
        self.theme_name = "default"
        self._theme = Theme(
            {
                "error": "red",
                "warning": "yellow",
                "info": "blue",
                "success": "green",
                "vibe": "magenta",
                "key": "cyan",
                "value": "white",
            }
        )
        self.themes = {
            "default": Theme(
                {
                    "error": "red",
                    "warning": "yellow",
                    "info": "blue",
                    "success": "green",
                    "vibe": "magenta",
                    "key": "cyan",
                    "value": "white",
                }
            ),
            "dark": Theme(
                {
                    "error": "red",
                    "warning": "yellow",
                    "info": "blue",
                    "success": "green",
                    "vibe": "magenta",
                    "key": "cyan",
                    "value": "white",
                }
            ),
            "light": Theme(
                {
                    "error": "red",
                    "warning": "yellow",
                    "info": "blue",
                    "success": "green",
                    "vibe": "magenta",
                    "key": "cyan",
                    "value": "black",
                }
            ),
            "accessible": Theme(
                {
                    "error": "red",
                    "warning": "blue",
                    "info": "cyan",
                    "success": "green",
                    "vibe": "magenta",
                    "key": "yellow",
                    "value": "white",
                }
            ),
        }
        self.console = Console(theme=self._theme)
        self.error_console = Console(stderr=True, theme=self._theme)

    def get_available_themes(self) -> list[str]:
        """Get list of available theme names.

        Returns:
            List[str]: List of available theme names
        """
        return list(self.themes.keys())

    def set_theme(self, theme_name: str) -> None:
        """Set the console theme."""
        if theme_name not in self.themes:
            raise ValueError("Invalid theme name")

        self.theme_name = theme_name
        self._theme = self.themes[theme_name]
        self.console = Console(theme=self._theme)
        self.error_console = Console(stderr=True, theme=self._theme)

    def print(self, message: str, style: str | None = None) -> None:
        """Print a message with optional style."""
        self.safe_print(self.console, message, style=style)

    def print_raw(self, message: str) -> None:
        """Print raw output."""
        self.safe_print(self.console, message, markup=False)

    def safe_print(
        self,
        console: Console,
        message: str | Table | Any,
        style: str | None = None,
        markup: bool = True,
        **kwargs: Any,
    ) -> None:
        """Print a message safely, handling malformed markup gracefully.

        If Rich markup parsing fails, fall back to printing without markup.

        Args:
            console: The console to print to
            message: The message to print
            style: Optional style to apply
            markup: Whether to enable markup parsing (default: True)
            **kwargs: Additional keyword arguments to pass to console.print
        """
        try:
            console.print(message, style=style, markup=markup, **kwargs)
        except MarkupError:
            # If markup parsing fails, try again with markup disabled
            console.print(message, style=style, markup=False, **kwargs)

    def print_error(self, message: str) -> None:
        """Print an error message."""
        self.safe_print(self.error_console, f"Error: {message}", style="error")

    def print_warning(self, message: str) -> None:
        """Print a warning message."""
        self.safe_print(self.error_console, f"Warning: {message}", style="warning")

    def print_note(self, message: str, error: Exception | None = None) -> None:
        """Print a note message with optional error."""
        if error:
            self.safe_print(
                self.error_console, f"Note: {message} ({error!s})", style="info"
            )
        else:
            self.safe_print(self.error_console, f"Note: {message}", style="info")

    def print_success(self, message: str) -> None:
        """Print a success message."""
        self.safe_print(self.console, message, style="success")

    def print_vibe(self, message: str) -> None:
        """Print a vibe message."""
        self.safe_print(self.console, "✨ Vibe check:", style="vibe")
        self.safe_print(self.console, message)

    def print_vibe_header(self) -> None:
        """Print vibe header."""
        self.safe_print(self.console, "✨ Vibe check:", style="vibe")

    def print_no_output_warning(self) -> None:
        """Print warning about no output."""
        self.print_warning(
            "No output will be displayed. "
            "Use --show-raw-output to see raw kubectl output or "
            "--show-vibe to see the vibe check summary."
        )

    def print_no_proxy_warning(self) -> None:
        """Print information about missing proxy configuration."""
        self.print_warning(
            "Traffic monitoring disabled. To enable statistics and monitoring:\n"
            "1. Set intermediate_port_range in your config:\n"
            "   vibectl config set intermediate_port_range 10000-11000\n"
            "2. Use port-forward with a port mapping (e.g., 8080:80)\n"
            "\nTo suppress this message: vibectl config set warn_no_proxy false"
        )

    def print_truncation_warning(self) -> None:
        """Print warning about output truncation."""
        self.print_warning("Output was truncated for processing")

    def print_missing_api_key_error(self) -> None:
        """Print error about missing API key."""
        self.print_error(
            "Missing API key. Please set OPENAI_API_KEY environment variable."
        )

    def print_missing_request_error(self) -> None:
        """Print error about missing request."""
        self.print_error("Missing request after 'vibe' command")

    def print_empty_output_message(self) -> None:
        """Print message about empty output."""
        self.print_note("No output to display")

    def print_keyboard_interrupt(self) -> None:
        """Print keyboard interrupt message."""
        self.print_error("Keyboard interrupt")

    def print_cancelled(self) -> None:
        """Print command cancellation message."""
        self.print_warning("Command cancelled")

    def print_processing(self, message: str) -> None:
        """Print a processing message.

        Args:
            message: The message to display indicating processing status.
        """
        self.safe_print(self.console, f"🔄 {message}", style="info")

    def print_proposal(self, message: str) -> None:
        """Print a proposal message."""
        self.safe_print(self.console, f"💡 {message}", style="vibe")

    def print_vibe_welcome(self) -> None:
        """Print vibe welcome message."""
        self.safe_print(
            self.console, "🔮 Welcome to vibectl - vibes-based kubectl", style="vibe"
        )
        self.safe_print(
            self.console,
            "Use 'vibe' commands to get AI-powered insights about your cluster",
        )

    def print_config_table(self, config_data: dict[str, Any]) -> None:
        """Print configuration data in a table.

        Args:
            config_data: Configuration data to display.
        """
        table = Table(title="Configuration")
        table.add_column("Setting", style="key")
        table.add_column("Value", style="value")

        for key, value in sorted(config_data.items()):
            table.add_row(str(key), str(value))

        self.safe_print(self.console, table)

    def handle_vibe_output(
        self,
        output: str,
        show_raw_output: bool,
        show_vibe: bool,
        vibe_output: str | None = None,
    ) -> None:
        """Handle displaying command output in both raw and vibe formats.

        Args:
            output: Raw command output.
            show_raw_output: Whether to show raw output.
            show_vibe: Whether to show vibe output.
            vibe_output: Optional vibe output to display.
        """
        if show_raw_output:
            self.print_raw(output)

        if show_vibe and vibe_output:
            self.print_vibe(vibe_output)

    def print_metrics(
        self,
        latency_ms: float | None = None,
        tokens_in: int | None = None,
        tokens_out: int | None = None,
        source: str | None = None,
        total_duration: float | None = None,
    ) -> None:
        """Display LLM metrics in a formatted way."""
        items = []
        if source:
            items.append(f"[dim]Source:[/] {source}")
        if latency_ms is not None:
            items.append(f"[dim]Latency:[/] {latency_ms:.2f} ms")
        if total_duration is not None:
            items.append(f"[dim]Total Duration:[/] {total_duration:.2f} ms")
        if tokens_in is not None and tokens_out is not None:
            items.append(f"[dim]Tokens:[/] {tokens_in} in, {tokens_out} out")

        if items:
            self.safe_print(
                self.console, f"📊 [bold cyan]Metrics:[/bold cyan] {' | '.join(items)}"
            )

    def print_waiting(self, message: str = "Waiting...") -> None:
        """Display a waiting message."""
        self.safe_print(self.console, message, style="info")


# Create global instance for easy import
console_manager = ConsoleManager()
