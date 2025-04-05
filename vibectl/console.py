"""
Console management for vibectl.

Provides utility functions and classes for managing console output,
error handling, and formatting for vibectl commands.
"""

from typing import Any, Dict, Optional, Tuple

from rich.console import Console
from rich.table import Table
from rich.theme import Theme

from .output_processor import output_processor

# Default themes
DEFAULT_THEME = {
    "success": "green",
    "error": "bold red",
    "warning": "yellow",
    "note": "yellow",
    "info": "blue",
    "title": "bold green",
    "highlight": "bold",
    "timestamp": "italic",
    "table_title": "bold",
    "key": "bold",
    "value": "",
}

DARK_THEME = {
    "success": "green",
    "error": "bold red",
    "warning": "yellow",
    "note": "yellow",
    "info": "blue",
    "title": "bold green",
    "highlight": "bold white",
    "timestamp": "italic grey70",
    "table_title": "bold cyan",
    "key": "bold white",
    "value": "white",
}

LIGHT_THEME = {
    "success": "green",
    "error": "bold red",
    "warning": "yellow",
    "note": "blue",
    "info": "dark_blue",
    "title": "bold green",
    "highlight": "bold black",
    "timestamp": "italic grey50",
    "table_title": "bold blue",
    "key": "bold black",
    "value": "black",
}

ACCESSIBLE_THEME = {
    "success": "bold blue",
    "error": "bold red",
    "warning": "bold magenta",
    "note": "bold cyan",
    "info": "bold green",
    "title": "bold blue",
    "highlight": "bold",
    "timestamp": "italic",
    "table_title": "bold blue",
    "key": "bold",
    "value": "",
}


class ConsoleManager:
    """Manages console output and error handling for vibectl."""

    def __init__(self, theme_name: str = "default") -> None:
        """Initialize the console manager with stdout and stderr consoles.

        Args:
            theme_name: The name of the theme to use (default, dark, light, accessible)
        """
        # Set up theme
        self.theme_name = theme_name
        self.themes = {
            "default": DEFAULT_THEME,
            "dark": DARK_THEME,
            "light": LIGHT_THEME,
            "accessible": ACCESSIBLE_THEME,
        }
        self._theme = self._create_theme(theme_name)

        # Set up consoles with theme
        self.console = Console(theme=self._theme)
        self.error_console = Console(stderr=True, theme=self._theme)

    def _create_theme(self, theme_name: str) -> Theme:
        """Create a rich Theme object from theme dictionary.

        Args:
            theme_name: The name of the theme to use

        Returns:
            A rich Theme object
        """
        theme_dict = self.themes.get(theme_name, DEFAULT_THEME)
        return Theme(theme_dict)

    def set_theme(self, theme_name: str) -> None:
        """Change the current theme.

        Args:
            theme_name: The name of the theme to use

        Raises:
            ValueError: If the theme name is not valid
        """
        if theme_name not in self.themes:
            raise ValueError(
                f"Invalid theme name: {theme_name}. "
                f"Valid themes are: {', '.join(self.themes.keys())}"
            )

        self.theme_name = theme_name
        self._theme = self._create_theme(theme_name)

        # Recreate consoles with new theme
        self.console = Console(theme=self._theme)
        self.error_console = Console(stderr=True, theme=self._theme)

    def get_available_themes(self) -> Dict[str, Dict[str, str]]:
        """Get a dictionary of available themes.

        Returns:
            Dictionary of theme names and their color mappings
        """
        return self.themes

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
        self.error_console.print(f"[error]Error:[/error] {message}", end=end)

    def print_warning(self, message: str, end: str = "\n") -> None:
        """Print a warning message to the error console."""
        self.error_console.print(f"[warning]Warning:[/warning] {message}", end=end)

    def print_note(
        self, message: str, error: Optional[Exception] = None, end: str = "\n"
    ) -> None:
        """Print a note message to the error console, optionally with an error."""
        if error:
            self.error_console.print(
                f"[note]Note:[/note] {message}: [error]{error}[/error]", end=end
            )
        else:
            self.error_console.print(f"[note]Note:[/note] {message}", end=end)

    def print_info(self, message: str, end: str = "\n") -> None:
        """Print an informational message to the console."""
        self.console.print(f"[info]Info:[/info] {message}", end=end)

    def print_success(self, message: str, end: str = "\n") -> None:
        """Print a success message."""
        self.console.print(f"[success]✓[/success] {message}", end=end)

    def print_vibe_header(self) -> None:
        """Print the vibe check header."""
        self.console.print("[title]✨ Vibe check:[/title]")

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
            title="vibectl Configuration",
            show_header=True,
            title_justify="center",
            title_style="table_title",
        )
        table.add_column("Key", style="key")
        table.add_column("Value", style="value")

        # Add rows for each config item
        for key, value in config_data.items():
            table.add_row(str(key), str(value))

        self.console.print(table)

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

        This is a convenience method that delegates to the output_processor.

        Args:
            output: The raw output to process
            max_token_limit: Maximum number of tokens for LLM input
            truncation_ratio: Ratio for truncating output

        Returns:
            Tuple containing (processed_output, was_truncated)
        """
        # Configure the output processor with our token limits
        output_processor.max_token_limit = max_token_limit
        output_processor.truncation_ratio = truncation_ratio

        # Use automatic processing for best results
        result = output_processor.process_auto(output)

        # Print truncation warning if needed
        if result[1]:  # If was_truncated is True
            self.print_truncation_warning()

        return result


# Create global instance for easy import
console_manager = ConsoleManager()
