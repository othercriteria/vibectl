"""
Console UI for vibectl.

This module provides console UI functionality for vibectl.
"""

from typing import Any

from rich.console import Console
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
        self.console.print(message, style=style)

    def print_raw(self, message: str) -> None:
        """Print raw output."""
        self.console.print(message)

    def print_error(self, message: str) -> None:
        """Print an error message."""
        self.error_console.print(f"Error: {message}", style="error")

    def print_warning(self, message: str) -> None:
        """Print a warning message."""
        self.error_console.print(f"Warning: {message}", style="warning")

    def print_note(self, message: str, error: Exception | None = None) -> None:
        """Print a note message with optional error."""
        if error:
            self.error_console.print(f"Note: {message} ({error!s})", style="info")
        else:
            self.error_console.print(f"Note: {message}", style="info")

    def print_success(self, message: str) -> None:
        """Print a success message."""
        self.console.print(message, style="success")

    def print_vibe(self, message: str) -> None:
        """Print a vibe message."""
        self.console.print("✨ Vibe check:", style="vibe")
        self.console.print(message)

    def print_vibe_header(self) -> None:
        """Print vibe header."""
        self.console.print("✨ Vibe check:", style="vibe")

    def print_no_output_warning(self) -> None:
        """Print warning about no output."""
        self.print_warning(
            "No output will be displayed. "
            "Use --show-raw-output to see raw kubectl output or "
            "--show-vibe to see the vibe check summary."
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
        self.console.print(f"🔄 {message}", style="info")

    def print_vibe_welcome(self) -> None:
        """Print vibe welcome message."""
        self.console.print("🔮 Welcome to vibectl - vibes-based kubectl", style="vibe")
        self.console.print(
            "Use 'vibe' commands to get AI-powered insights about your cluster"
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

        self.console.print(table)

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

    def process_output_for_vibe(self, output: str) -> tuple[str, bool]:
        """Process output for vibe, truncating if necessary."""
        if len(output) <= 1000:
            return output, False

        # Keep first 500 and last 500 characters
        first_part = output[:500]
        last_part = output[-500:]
        truncated_output = f"{first_part}\n... (truncated) ...\n{last_part}"
        return truncated_output, True


# Create global instance for easy import
console_manager = ConsoleManager()
