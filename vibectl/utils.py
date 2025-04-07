"""
Utility functions for vibectl.

Contains reusable helper functions used across the application.
"""

import json
import subprocess
import sys
from typing import NoReturn, Optional

from .console import console_manager


def handle_exception(e: Exception, exit_on_error: bool = True) -> Optional[NoReturn]:
    """Handle common exceptions consistently.
    
    Args:
        e: The exception to handle
        exit_on_error: Whether to exit the program on error
        
    Returns:
        None if exit_on_error is False, otherwise does not return
    """
    error_msg = str(e).lower()
    
    # Handle API key related errors
    if "no key found" in error_msg or "api key" in error_msg or "missing api key" in error_msg:
        console_manager.print_missing_api_key_error()
    
    # Handle kubectl subprocess errors
    elif isinstance(e, subprocess.CalledProcessError):
        if hasattr(e, 'stderr') and e.stderr:
            # kubectl errors will have stderr content
            console_manager.error_console.print(e.stderr, end="")
        else:
            # Generic subprocess error
            console_manager.print_error(f"Command failed with exit code {getattr(e, 'returncode', 'unknown')}")
    
    # Handle file not found errors (typically kubectl not in PATH)
    elif isinstance(e, FileNotFoundError):
        if "kubectl" in error_msg or getattr(e, 'filename', '') == 'kubectl':
            console_manager.print_error("kubectl not found in PATH")
        else:
            console_manager.print_error(f"File not found: {getattr(e, 'filename', None)}")
    
    # Handle JSON parsing errors
    elif isinstance(e, (json.JSONDecodeError, ValueError)) and "json" in error_msg:
        console_manager.print_note("kubectl version information not available")
    
    # Handle 'Missing request after vibe' errors
    elif "missing request after 'vibe'" in error_msg:
        console_manager.print_missing_request_error()
    
    # Handle LLM errors
    elif "llm error" in error_msg:
        console_manager.print_error(str(e))
        console_manager.print_note("Could not get vibe check")
    
    # Handle invalid response format errors
    elif "invalid response format" in error_msg:
        console_manager.print_error(str(e))
    
    # Handle truncation warnings specially
    elif "truncated" in error_msg and "output" in error_msg:
        console_manager.print_truncation_warning()
    
    # Handle empty output cases
    elif "no output" in error_msg or "empty output" in error_msg:
        console_manager.print_empty_output_message()
    
    # Handle general errors
    else:
        console_manager.print_error(str(e))
    
    if exit_on_error:
        sys.exit(1)
    
    # Return None when exit_on_error is False
    return None 