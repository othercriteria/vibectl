"""
Utility functions for vibectl.

Contains reusable helper functions used across the application.
"""

import json
import subprocess
import sys

from rich.console import Console

from .console import console_manager

error_console = Console(stderr=True)


def handle_exception(e: Exception, exit_on_error: bool = True) -> None:
    """Handle exceptions with nice error messages.

    Args:
        e: Exception to handle
        exit_on_error: Whether to exit the process

    Returns:
        None if exit_on_error is False, otherwise this function never returns
    """
    error_console.print(f"[bold red]Error:[/] {e!s}")

    # Handle API key related errors
    if (
        "no key found" in str(e).lower()
        or "api key" in str(e).lower()
        or "missing api key" in str(e).lower()
    ):
        console_manager.print_missing_api_key_error()

    # Handle kubectl subprocess errors
    elif isinstance(e, subprocess.CalledProcessError):
        if hasattr(e, "stderr") and e.stderr:
            # kubectl errors will have stderr content
            console_manager.error_console.print(e.stderr, end="")
        else:
            # Generic subprocess error
            console_manager.print_error(
                f"Command failed with exit code {getattr(e, 'returncode', 'unknown')}"
            )

    # Handle file not found errors (typically kubectl not in PATH)
    elif isinstance(e, FileNotFoundError):
        if "kubectl" in str(e).lower() or getattr(e, "filename", "") == "kubectl":
            console_manager.print_error("kubectl not found in PATH")
        else:
            console_manager.print_error(
                f"File not found: {getattr(e, 'filename', None)}"
            )

    # Handle JSON parsing errors
    elif isinstance(e, json.JSONDecodeError | ValueError) and "json" in str(e).lower():
        console_manager.print_note("kubectl version information not available")

    # Handle 'Missing request after vibe' errors
    elif "missing request after 'vibe'" in str(e).lower():
        console_manager.print_missing_request_error()

    # Handle LLM errors
    elif "llm error" in str(e).lower():
        console_manager.print_error(str(e))
        console_manager.print_note("Could not get vibe check")

    # Handle invalid response format errors
    elif "invalid response format" in str(e).lower():
        console_manager.print_error(str(e))

    # Handle truncation warnings specially
    elif "truncated" in str(e).lower() and "output" in str(e).lower():
        console_manager.print_truncation_warning()

    # Handle empty output cases
    elif "no output" in str(e).lower() or "empty output" in str(e).lower():
        console_manager.print_empty_output_message()

    # Handle general errors
    else:
        console_manager.print_error(str(e))

    if exit_on_error:
        sys.exit(1)
    return None
