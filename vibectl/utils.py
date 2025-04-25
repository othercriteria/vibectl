"""
Utility functions for vibectl.

Contains reusable helper functions used across the application.
"""

import json
import logging
import os
import subprocess
import sys
import traceback
import types

from rich.console import Console

from .console import console_manager

error_console = Console(stderr=True)


def handle_exception(
    e: Exception, exit_on_error: bool = True, tb: types.TracebackType | None = None
) -> None:
    """
    Handle exceptions with nice error messages.
    Optionally print tracebacks if VIBECTL_TRACEBACK=1 or log level is DEBUG.
    Accepts an optional traceback object for robust traceback printing.
    """
    # Handle 'Missing request after vibe' errors first to avoid duplicate output
    if "missing request after 'vibe'" in str(e).lower():
        console_manager.print_missing_request_error()
        if exit_on_error:
            sys.exit(1)
        return None

    # Optionally print traceback if VIBECTL_TRACEBACK=1 or log level is DEBUG
    show_traceback = (
        os.environ.get("VIBECTL_TRACEBACK") == "1"
        or logging.getLogger().getEffectiveLevel() <= logging.DEBUG
    )

    if show_traceback and tb is not None:
        console_manager.safe_print(
            console_manager.error_console, "[red]Traceback (most recent call last):[/]"
        )
        traceback.print_exception(type(e), e, tb)

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
            console_manager.safe_print(console_manager.error_console, e.stderr, end="")
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

    else:
        # Handle general errors (fallback)
        error_message = str(e)
        if not error_message or error_message == "None":
            error_message = "Unknown error occurred"
        console_manager.print_error(error_message)

    if exit_on_error:
        sys.exit(1)
    return None
