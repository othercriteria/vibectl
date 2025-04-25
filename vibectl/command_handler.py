"""
Command handler module for vibectl.

Provides reusable patterns for command handling and execution
to reduce duplication across CLI commands.

Note: All exceptions should propagate to the CLI entry point for centralized error
handling. Do not print or log user-facing errors here; use logging for diagnostics only.
"""

import asyncio
import random
import re
import subprocess
import time
from collections.abc import Callable
from contextlib import suppress

import click
import yaml
from rich.panel import Panel
from rich.progress import (
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from .config import (
    DEFAULT_CONFIG,
    Config,
)
from .console import console_manager
from .logutil import logger as _logger
from .memory import get_memory, set_memory, update_memory
from .model_adapter import get_model_adapter
from .output_processor import OutputProcessor
from .prompt import (
    memory_fuzzy_update_prompt,
    port_forward_prompt,
    recovery_prompt,
    wait_resource_prompt,
)
from .proxy import (
    StatsProtocol,
    TcpProxy,
    start_proxy_server,
    stop_proxy_server,
)
from .types import Error, OutputFlags, Result, Success

logger = _logger

# Export Table for testing
__all__ = ["Table"]

# Constants for output flags
# (DEFAULT_MODEL, DEFAULT_SHOW_RAW_OUTPUT, DEFAULT_SHOW_VIBE,
#  DEFAULT_WARN_NO_OUTPUT, DEFAULT_SHOW_KUBECTL)
# Use values from config.py's DEFAULT_CONFIG instead

# Initialize output processor
output_processor = OutputProcessor(max_chars=2000, llm_max_chars=2000)


def run_kubectl(
    cmd: list[str], capture: bool = False, config: Config | None = None
) -> Result:
    """Run kubectl command and capture output.

    Args:
        cmd: List of command arguments
        capture: Whether to capture and return output
        config: Optional Config instance to use

    Returns:
        Success with command output if capture=True, or None otherwise
        Error with error message on failure
    """
    try:
        # Get a Config instance if not provided
        cfg = config or Config()

        # Get the kubeconfig path from config
        kubeconfig = cfg.get("kubeconfig")

        # Build the full command
        kubectl_cmd = ["kubectl"]

        # Add the command arguments first, to ensure kubeconfig is AFTER the main
        # command
        kubectl_cmd.extend(cmd)

        # Add kubeconfig AFTER the main command to avoid errors
        if kubeconfig:
            kubectl_cmd.extend(["--kubeconfig", str(kubeconfig)])

        logger.info(f"Running kubectl command: {' '.join(kubectl_cmd)}")

        # Execute the command
        result = subprocess.run(
            kubectl_cmd,
            capture_output=capture,
            check=False,
            text=True,
            encoding="utf-8",
        )

        # Check for errors
        if result.returncode != 0:
            error_message = result.stderr.strip() if capture else "Command failed"
            if not error_message:
                error_message = f"Command failed with exit code {result.returncode}"
            logger.debug(f"kubectl command failed: {error_message}")

            # Create error result, marking kubectl server errors as non-halting
            # for auto loops
            return create_kubectl_error(error_message)

        # Return output if capturing
        if capture:
            output = result.stdout.strip()
            logger.debug(f"kubectl command output: {output}")
            return Success(data=output)
        return Success()
    except FileNotFoundError:
        error_msg = "kubectl not found. Please install it and try again."
        logger.debug(error_msg)
        return Error(error=error_msg)
    except Exception as e:
        logger.debug(f"Exception running kubectl: {e}", exc_info=True)
        return Error(error=str(e), exception=e)


def create_kubectl_error(
    error_message: str, exception: Exception | None = None
) -> Error:
    """
    Create an Error object for kubectl failures, marking certain errors as
    non-halting for auto loops.

    Args:
        error_message: The error message
        exception: Optional exception that caused the error

    Returns:
        Error object with appropriate halt_auto_loop flag set
    """
    # For kubectl server errors (like NotFound, Forbidden, etc.),
    # set halt_auto_loop=False so auto loops can continue
    if "Error from server" in error_message:
        return Error(error=error_message, exception=exception, halt_auto_loop=False)

    # For unknown command errors (usually from malformed LLM output),
    # set halt_auto_loop=False so the auto loop can continue and the LLM can
    # correct itself
    if "unknown command" in error_message.lower():
        return Error(error=error_message, exception=exception, halt_auto_loop=False)

    # For other errors, use the default (halt_auto_loop=True)
    return Error(error=error_message, exception=exception)


def handle_standard_command(
    command: str,
    resource: str,
    args: tuple,
    output_flags: OutputFlags,
    summary_prompt_func: Callable[[], str],
) -> Result:
    """Handle a standard kubectl command with both raw and vibe output.

    Args:
        command: The kubectl command to run
        resource: The resource to act on
        args: Additional command arguments
        output_flags: Output configuration flags
        summary_prompt_func: Function to generate summary prompt

    Returns:
        Result with Success or Error information
    """
    try:
        logger.info(f"Handling standard command: {command} {resource} {' '.join(args)}")

        # Run kubectl and process the result
        result = _run_standard_kubectl_command(command, resource, args)
        if isinstance(result, Error):
            return result

        # Extract output from success result
        output = result.data

        # Handle empty output case
        if not output:
            return _handle_empty_output(command, resource, args)

        # Handle the output display based on the configured flags
        return _handle_standard_command_output(
            output=output,
            output_flags=output_flags,
            summary_prompt_func=summary_prompt_func,
            command=f"{command} {resource} {' '.join(args)}",
        )
    except Exception as e:
        return _handle_standard_command_error(command, resource, args, e)


def _run_standard_kubectl_command(command: str, resource: str, args: tuple) -> Result:
    """Run a standard kubectl command and handle basic error cases.

    Args:
        command: The kubectl command to run
        resource: The resource to act on
        args: Additional command arguments

    Returns:
        Result with Success or Error information
    """
    # Build command list
    cmd_args = [command, resource]
    if args:
        cmd_args.extend(args)

    # Run kubectl and get result
    kubectl_result = run_kubectl(cmd_args, capture=True)

    # Handle errors from kubectl
    if isinstance(kubectl_result, Error):
        logger.error(
            f"Error in standard command: {command} {resource} {' '.join(args)}: "
            f"{kubectl_result.error}"
        )
        # Display error to user
        console_manager.print_error(kubectl_result.error)
        return kubectl_result

    # For Success result, ensure we return it properly
    return kubectl_result


def _handle_empty_output(command: str, resource: str, args: tuple) -> Result:
    """Handle the case when kubectl returns no output.

    Args:
        command: The kubectl command that was run
        resource: The resource that was acted on
        args: Additional command arguments that were used

    Returns:
        Success result indicating no output
    """
    logger.info(f"No output from command: {command} {resource} {' '.join(args)}")
    console_manager.print_processing("Command returned no output")
    return Success(message="Command returned no output")


def _handle_standard_command_output(
    output: str,
    output_flags: OutputFlags,
    summary_prompt_func: Callable[[], str],
    command: str,
) -> Result:
    """Process output from a standard command.

    A wrapper around handle_command_output that handles logging.

    Args:
        output: Command output to process
        output_flags: Output configuration flags
        summary_prompt_func: Function to generate summary prompt
        command: The full command string for logging

    Returns:
        Result of output processing
    """
    output_result = handle_command_output(
        output=output,
        output_flags=output_flags,
        summary_prompt_func=summary_prompt_func,
        command=command,
    )

    logger.info(f"Completed standard command: {command}")

    return output_result


def _handle_standard_command_error(
    command: str, resource: str, args: tuple, exception: Exception
) -> Error:
    """Handle unexpected errors in standard command execution.

    Args:
        command: The kubectl command that was run
        resource: The resource that was acted on
        args: Additional command arguments that were used
        exception: The exception that was raised

    Returns:
        Error result with error information
    """
    logger.error(
        f"Unexpected error handling standard command: {command} {resource} "
        f"{' '.join(args)}: {exception}",
        exc_info=True,
    )
    return Error(error=f"Unexpected error: {exception}", exception=exception)


def create_api_error(error_message: str, exception: Exception | None = None) -> Error:
    """
    Create an Error object for API failures, marking them as non-halting for auto loops.

    These are errors like 'overloaded_error' or other API-related issues that shouldn't
    break the auto loop.

    Args:
        error_message: The error message
        exception: Optional exception that caused the error

    Returns:
        Error object with halt_auto_loop=False
    """
    return Error(error=error_message, exception=exception, halt_auto_loop=False)


def is_api_error(error_message: str) -> bool:
    """
    Check if an error message looks like an API error.

    Args:
        error_message: The error message to check

    Returns:
        True if the error appears to be an API error, False otherwise
    """
    # Check for API error formats
    api_error_patterns = [
        "Error executing prompt",
        "overloaded_error",
        "rate_limit",
        "capacity",
        "busy",
        "throttle",
        "anthropic.API",
        "openai.API",
        "llm error",
        "model unavailable",
    ]

    error_message_lower = error_message.lower()
    return any(pattern.lower() in error_message_lower for pattern in api_error_patterns)


def handle_command_output(
    output: Result | str,
    output_flags: OutputFlags,
    summary_prompt_func: Callable[[], str],
    max_token_limit: int = 10000,
    truncation_ratio: int = 3,
    command: str | None = None,
) -> Result:
    """Handle displaying command output in both raw and vibe formats.

    Args:
        output: The command output to display (can be a string or a Result object)
        output_flags: Configuration for output display
        summary_prompt_func: Function returning the prompt template for summarizing
        max_token_limit: Maximum number of tokens for the prompt
        truncation_ratio: Ratio for truncating the output
        command: Optional command string that generated the output

    Returns:
        Result with Success containing vibe output or Error with error information
    """
    logger.debug(f"Handling command output for: {command}")

    try:
        # Extract data from Result objects if needed
        if isinstance(output, Success):
            output_data = output.data
        elif isinstance(output, Error):
            return output  # Pass through error results
        else:
            output_data = output  # Already a string

        # Ensure we have string data to work with
        if not isinstance(output_data, str):
            logger.warning(
                f"Expected string output but got {type(output_data).__name__}"
            )
            # Convert to string if possible
            output_data = "" if output_data is None else str(output_data)

        # Display command if needed
        _display_kubectl_command(output_flags, command)

        # Check and warn if no output will be displayed
        _check_output_visibility(output_flags)

        # Show raw output if needed
        _display_raw_output(output_flags, output_data)

        # Process vibe output if needed
        if output_flags.show_vibe:
            vibe_result = _process_vibe_output(
                output_data,
                output_flags,
                summary_prompt_func,
                max_token_limit,
                truncation_ratio,
                command,
            )

            # If we got an error from vibe processing, return that
            if isinstance(vibe_result, Error):
                return vibe_result

            # Otherwise, extract the vibe output
            vibe_output = vibe_result.data

            # Display the output if there was any
            if vibe_output and output_flags.show_raw:
                console_manager.console.print()

            if vibe_output:
                _display_vibe_output(vibe_output)
        else:
            vibe_output = ""

        # Return success with whatever vibe output we got
        return Success(message="Command completed successfully", data=vibe_output)

    except Exception as e:
        logger.error(f"Error in vibe output processing: {e}", exc_info=True)
        error_message = f"Error processing output: {e}"

        # Check if this is an API error, which shouldn't halt auto loops
        if is_api_error(str(e)):
            logger.info("API error detected, marking as non-halting for auto loops")
            return create_api_error(error_message, e)

        # For non-API errors, use the default behavior (halt_auto_loop=True)
        return Error(error=error_message, exception=e)


def _display_kubectl_command(output_flags: OutputFlags, command: str | None) -> None:
    """Display the kubectl command if requested.

    Args:
        output_flags: Output configuration flags
        command: Command string to display
    """
    # Skip display if not requested or no command
    if not output_flags.show_kubectl or not command:
        return

    # Handle vibe command with or without a request
    if command.startswith("vibe"):
        # Split to check if there's a request after "vibe"
        parts = command.split(" ", 1)
        if len(parts) == 1 or not parts[1].strip():
            # When there's no specific request, show message about memory context
            console_manager.print_processing(
                "Planning next steps based on memory context..."
            )
        else:
            # When there is a request, show the request
            request = parts[1].strip()
            console_manager.print_processing(f"Planning how to: {request}")
    # Skip other cases as they're now handled in _process_and_execute_kubectl_command


def _check_output_visibility(output_flags: OutputFlags) -> None:
    """Check if no output will be shown and warn if needed.

    Args:
        output_flags: Output configuration flags
    """
    if (
        not output_flags.show_raw
        and not output_flags.show_vibe
        and output_flags.warn_no_output
    ):
        logger.warning("No output will be shown due to output flags.")
        console_manager.print_no_output_warning()


def _display_raw_output(output_flags: OutputFlags, output: str) -> None:
    """Display raw output if requested.

    Args:
        output_flags: Output configuration flags
        output: Command output to display
    """
    if output_flags.show_raw:
        logger.debug("Showing raw output.")
        console_manager.print_raw(output)


def _process_vibe_output(
    output: str,
    output_flags: OutputFlags,
    summary_prompt_func: Callable[[], str],
    max_token_limit: int = 10000,
    truncation_ratio: int = 3,
    command: str | None = None,
) -> Result:
    """Process command output to generate a vibe summary.

    Args:
        output: The command output to process
        output_flags: Output configuration flags
        summary_prompt_func: Function to generate summary prompt
        max_token_limit: Maximum number of tokens for the prompt
        truncation_ratio: Ratio for truncating the output
        command: Optional command string that generated the output

    Returns:
        Result with Success containing vibe output or Error with error information
    """
    logger.debug("Processing output for vibe summary.")

    # Process output to avoid token limits
    truncation_result = output_processor.process_auto(output)
    processed_output = truncation_result.truncated

    # Show truncation warning if needed
    # Simplification: Check if truncated content is different from original
    if truncation_result.original != truncation_result.truncated:
        logger.warning("Output was truncated for processing.")
        console_manager.print_truncation_warning()

    try:
        # Get summary from LLM
        vibe_output = _get_llm_summary(
            processed_output, output_flags.model_name, summary_prompt_func(), command
        )

        # Update memory if we have a command, regardless of vibe output
        if command:
            update_memory(command, output, vibe_output, output_flags.model_name)

        # Check for empty response
        if not vibe_output:
            logger.info("Vibe output is empty.")
            console_manager.print_empty_output_message()
            return Success(
                message="Command completed successfully, but vibe output is empty.",
                data="",
            )

        # Check for error response
        if vibe_output.startswith("ERROR:"):
            error_message = vibe_output[7:].strip()  # Remove "ERROR: " prefix
            logger.error(f"Vibe model returned error: {error_message}")
            console_manager.print_error(error_message)
            return Error(error=error_message)

        # Return the vibe output
        return Success(message="Vibe output processed successfully", data=vibe_output)

    except Exception as e:
        error_message = f"Error getting LLM summary: {e}"

        # Check if this is an API error, which shouldn't halt auto loops
        if is_api_error(str(e)):
            logger.info(
                "API error in LLM summary, marking as non-halting for auto loops"
            )
            return create_api_error(error_message, e)

        # For other errors, use the default behavior
        return Error(error=error_message, exception=e)


def _get_llm_summary(
    processed_output: str,
    model_name: str,
    summary_prompt: str,
    command: str | None = None,
) -> str:
    """Get a summary from the LLM.

    Args:
        processed_output: Processed command output
        model_name: Name of the model to use
        summary_prompt: Prompt template for summarizing
        command: Optional command string to include in the prompt

    Returns:
        Summary text from the LLM
    """
    model_adapter = get_model_adapter()
    model = model_adapter.get_model(model_name)

    # Format the prompt correctly based on available parameters
    prompt = (
        summary_prompt.format(output=processed_output, command=command)
        if command
        else summary_prompt.format(output=processed_output)
    )

    logger.debug(f"Sending prompt to model: {prompt[:100]}...")
    return model_adapter.execute(model, prompt)


def _display_vibe_output(vibe_output: str) -> None:
    """Display the vibe output.

    Args:
        vibe_output: Vibe output to display
    """
    logger.debug("Displaying vibe summary output.")
    console_manager.print_vibe(vibe_output)


def handle_vibe_request(
    request: str,
    command: str,
    plan_prompt: str,
    summary_prompt_func: Callable[[], str],
    output_flags: OutputFlags,
    yes: bool = False,  # Add parameter to control confirmation bypass
    semiauto: bool = False,  # Add parameter for semiauto mode
    live_display: bool = True,  # Add parameter for live display
    memory_context: str = "",  # Add parameter for memory context
    autonomous_mode: bool = False,  # Add parameter for autonomous mode
) -> Result:
    """Handle a request to execute a kubectl command based on a natural language query.

    Args:
        request: Natural language request from the user
        command: Command type (get, describe, etc.)
        plan_prompt: LLM prompt template for planning the kubectl command
        summary_prompt_func: Function that returns the LLM prompt for summarizing
        output_flags: Output configuration flags
        yes: Whether to bypass confirmation prompts
        semiauto: Whether this is operating in semiauto mode
        live_display: Whether to use live display for commands like port-forward
        memory_context: Memory context to include in the prompt (for vibe mode)
        autonomous_mode: Whether this is operating in autonomous mode

    Returns:
        Result with Success or Error information
    """
    try:
        logger.info(
            f"Planning kubectl command for request: '{request}' (command: {command})"
        )
        model_adapter = get_model_adapter()
        model = model_adapter.get_model(output_flags.model_name)

        # Format the prompt for the LLM
        formatted_prompt = _format_vibe_prompt(
            plan_prompt, request, command, memory_context
        )

        # Get the kubectl command from the LLM
        kubectl_cmd = model_adapter.execute(model, formatted_prompt)

        # Check if we got a valid command
        if not kubectl_cmd:
            logger.error(
                "No kubectl command could be generated for request: '%s'", request
            )
            console_manager.print_error("No kubectl command could be generated.")
            return Error(error="No kubectl command could be generated")

        # Handle error output from LLM
        if kubectl_cmd.startswith("ERROR:"):
            return _handle_planning_error(
                kubectl_cmd, command, request, output_flags.model_name
            )

        # Process the command string generated by the LLM
        result = _process_and_execute_kubectl_command(
            kubectl_cmd=kubectl_cmd,
            command=command,
            request=request,
            output_flags=output_flags,
            summary_prompt_func=summary_prompt_func,
            yes=yes,
            semiauto=semiauto,
            live_display=live_display,
            autonomous_mode=autonomous_mode,
        )

        # If there was an error, query the model for recovery suggestions
        if isinstance(result, Error):
            logger.info("Command execution failed, getting recovery suggestions")
            # Get recovery suggestions from model
            try:
                # Format the recovery prompt
                recovery_prompt_text = recovery_prompt(
                    command=f"{command} {kubectl_cmd}",
                    error=result.error,
                )

                # Make a second call to the model for recovery suggestions
                recovery_suggestions = model_adapter.execute(
                    model, recovery_prompt_text
                )
                if recovery_suggestions:
                    console_manager.print_processing("Recovery suggestions:")
                    console_manager.print_note(recovery_suggestions)
                    # Set recovery_suggestions directly on the result
                    result.recovery_suggestions = recovery_suggestions

                    # Update memory with recovery suggestions
                    update_memory(
                        command=f"{command} {kubectl_cmd}",
                        command_output=result.error,
                        vibe_output=f"Recovery suggestions: {recovery_suggestions}",
                        model_name=output_flags.model_name,
                    )

                    # Log that recovery suggestions were added to memory
                    logger.info("Recovery suggestions added to memory context")
            except Exception as recovery_err:
                logger.error(f"Error getting recovery suggestions: {recovery_err}")

        return result
    except Exception as e:
        logger.error(f"Error in vibe request processing: {e}", exc_info=True)
        return Error(error=f"Error processing vibe request: {e}", exception=e)


def _format_vibe_prompt(
    plan_prompt: str, request: str, command: str, memory_context: str = ""
) -> str:
    """Format the plan prompt for vibe requests, handling different format styles.

    Args:
        plan_prompt: The prompt template
        request: The user's natural language request
        command: The command type (get, describe, etc.)
        memory_context: Optional memory context to include

    Returns:
        Formatted prompt ready to send to the LLM
    """
    # Prepare the format parameters
    format_params = {"request": request, "command": command}

    # Always provide memory_context in format_params, even if empty
    # This prevents KeyError when the prompt contains {memory_context}
    format_params["memory_context"] = memory_context or ""

    try:
        # First, check if there are any positional format specifiers in the prompt
        import re

        positional_formats = re.findall(r"{(\d+)}", plan_prompt)

        if positional_formats:
            # If positional formats exist, use string replacement for all parameters
            logger.info(
                "Detected positional format specifiers in prompt, "
                "using string replacement"
            )
            formatted_prompt = plan_prompt

            # Replace all named parameters
            formatted_prompt = formatted_prompt.replace(
                "{memory_context}", memory_context or ""
            )
            formatted_prompt = formatted_prompt.replace("{request}", request)
            formatted_prompt = formatted_prompt.replace("{command}", command)

            # Then handle any remaining positional parameters by replacing
            # them with empty strings
            for pos in positional_formats:
                formatted_prompt = formatted_prompt.replace(f"{{{pos}}}", "")
        else:
            # No positional formats, use normal keyword formatting
            formatted_prompt = plan_prompt.format(**format_params)

    except (KeyError, IndexError) as e:
        # Fallback to string replacement as a last resort
        logger.warning(
            f"Format error ({e}) in prompt. Using fallback formatting method."
        )
        # Use string replacement as a fallback to avoid format conflicts
        formatted_prompt = plan_prompt
        formatted_prompt = formatted_prompt.replace(
            "{memory_context}", memory_context or ""
        )
        formatted_prompt = formatted_prompt.replace("{request}", request).replace(
            "{command}", command
        )

        # Replace any remaining format specifiers with empty strings
        import re

        formatted_prompt = re.sub(r"{(\d+)}", "", formatted_prompt)
        # Also replace any remaining {name} format specifiers
        formatted_prompt = re.sub(r"{[a-zA-Z0-9_]+}", "", formatted_prompt)

    return formatted_prompt


def _handle_planning_error(
    kubectl_cmd: str, command: str, request: str, model_name: str
) -> Result:
    """Handle error responses from the LLM during planning.

    Args:
        kubectl_cmd: The error response from the LLM
        command: The command type
        request: The user's request
        model_name: The model name used

    Returns:
        Error result with the error message
    """
    error_message = kubectl_cmd[7:].strip()  # Remove "ERROR: " prefix
    logger.error("LLM planning error: %s", error_message)

    # Update memory with the error for context
    command_for_output = f"{command} vibe {request}"
    error_output = f"Error: {error_message}"
    update_memory(
        command=command_for_output,
        command_output=error_output,
        vibe_output=kubectl_cmd,
        model_name=model_name,
    )

    console_manager.print_processing("Planning error added to memory context")
    console_manager.print_error(kubectl_cmd)
    return Error(error=error_message)


def _process_and_execute_kubectl_command(
    kubectl_cmd: str,
    command: str,
    request: str,
    output_flags: OutputFlags,
    summary_prompt_func: Callable[[], str],
    yes: bool = False,
    semiauto: bool = False,
    live_display: bool = True,
    autonomous_mode: bool = False,
) -> Result:
    """Process and execute the kubectl command generated by the LLM.

    Args:
        kubectl_cmd: The kubectl command string generated by the LLM
        command: The command type
        request: The user's request
        output_flags: Output configuration flags
        summary_prompt_func: Function to generate summary prompt
        yes: Whether to bypass confirmation prompts
        semiauto: Whether this is operating in semiauto mode
        live_display: Whether to use live display for commands like port-forward
        autonomous_mode: Whether this is operating in autonomous mode

    Returns:
        Result of command execution
    """
    logger.debug(f"Processing planned command string: {kubectl_cmd}")

    # Parse the command string
    try:
        cmd_args, yaml_content = _process_command_string(kubectl_cmd)
        args = _parse_command_args(cmd_args)
        display_cmd = _create_display_command(args, yaml_content)
    except ValueError as ve:
        logger.error("Command parsing error: %s", ve, exc_info=True)
        console_manager.print_error(f"Command parsing error: {ve}")
        return Error(error=f"Command parsing error: {ve}", exception=ve)

    # Determine if confirmation is needed
    needs_confirm = _needs_confirmation(command, semiauto) and not yes

    # Set a flag to prevent duplicate command display in output handling
    show_command_now = output_flags.show_kubectl or needs_confirm
    # Always set show_kubectl to False in the modified flags to avoid
    # duplicate command displays
    modified_output_flags = output_flags.replace(show_kubectl=False)

    # Display the command if needed
    if show_command_now:
        logger.info(f"Planned kubectl command: {display_cmd}")

        # Determine how to display the command
        if command == "vibe" and (autonomous_mode or semiauto):
            # When in autonomous/semiauto mode with vibe command,
            # just show the kubectl part
            # Show the actual kubectl command that will be executed
            cmd_str = f"kubectl {display_cmd}"
            console_manager.print_processing(f"Running: {cmd_str}")
        else:
            # For other cmds: include vibe in cmd string if there is a request
            display_command = (
                f"{command} vibe {request}" if request else f"{command} vibe"
            )
            cmd_str = f"kubectl {display_command}"
            console_manager.print_processing(f"Running: {cmd_str}")

    # Handle confirmation if needed
    if needs_confirm:
        confirm_result = _handle_command_confirmation(
            display_cmd, command, semiauto, output_flags.model_name
        )
        # If the user didn't confirm, return the result from confirmation
        # If they did confirm, confirm_result will be None and we continue
        if confirm_result is not None:
            return confirm_result

    # Execute the command based on its type
    logger.info(f"Executing command: {command} {display_cmd}")

    # Handle live display for specific command types
    if command == "wait" and live_display and len(args) > 0 and args[0] == "wait":
        # Get the resource and args from the parsed command
        resource = args[1] if len(args) > 1 else ""
        wait_args = tuple(args[2:]) if len(args) > 2 else ()
        return handle_wait_with_live_display(resource, wait_args, modified_output_flags)

    # Handle port-forward with live display
    if (
        command == "port-forward"
        and live_display
        and len(args) > 0
        and args[0] == "port-forward"
    ):
        resource = args[1] if len(args) > 1 else ""
        port_args = tuple(args[2:]) if len(args) > 2 else ()
        return handle_port_forward_with_live_display(
            resource, port_args, modified_output_flags
        )

    # Execute the standard kubectl command
    try:
        if yaml_content:
            logger.debug("Executing command with YAML content")
            # Use a consistent logging format
            logger.info(f"Executing kubectl command: {args} (yaml: True)")
            result = _execute_yaml_command(args, yaml_content)
        else:
            logger.debug("Executing standard command")
            logger.info(f"Executing kubectl command: {args} (yaml: False)")
            result = _execute_command(args, None)

        # Log the result
        if isinstance(result, Error):
            logger.error(f"Error executing command: {result.error}")
            console_manager.print_error(result.error)
            return result

        # Process the output
        # Create command string for output processing that appropriately represents
        # what's being executed without duplication
        if command == "vibe":
            # For vibe commands, use "vibe <request>" or just "vibe"
            display_command = f"{command} {request}" if request else command
        else:
            # For other cmds: include vibe in cmd string if there is a request
            display_command = (
                f"{command} vibe {request}" if request else f"{command} vibe"
            )

        return handle_command_output(
            output=result,
            output_flags=modified_output_flags,
            summary_prompt_func=summary_prompt_func,
            command=display_command,
        )
    except Exception as e:
        logger.error(f"Error executing planned command: {e}", exc_info=True)
        console_manager.print_error(f"Error executing command: {e}")
        return Error(error=f"Error executing command: {e}", exception=e)


def _handle_command_confirmation(
    display_cmd: str, cmd_for_display: str, semiauto: bool, model_name: str
) -> Result | None:
    """Handle command confirmation with enhanced options.

    Args:
        display_cmd: The command to display
        cmd_for_display: The command prefix to display
        semiauto: Whether this is operating in semiauto mode
        model_name: The model name used

    Returns:
        Result if the command was cancelled, None if it should proceed
    """
    # Enhanced confirmation dialog with new options: yes, no, and, but, exit, memory
    if semiauto:
        console_manager.print_note(
            "\n[Y]es, [N]o, yes [A]nd, no [B]ut, [M]emory, or [E]xit? (y/n/a/b/m/e)"
        )
    else:
        console_manager.print_note(
            "\n[Y]es, [N]o, yes [A]nd, no [B]ut, or [M]emory? (y/n/a/b/m)"
        )

    while True:
        choice = click.prompt(
            "",
            type=click.Choice(
                ["y", "n", "a", "b", "m", "e"]
                if semiauto
                else ["y", "n", "a", "b", "m"],
                case_sensitive=False,
            ),
            default="n",
        ).lower()

        # Process the choice
        if choice == "m":
            # Show memory and then show the confirmation dialog again
            from vibectl.memory import get_memory

            memory_content = get_memory()
            if memory_content:
                console_manager.safe_print(
                    console_manager.console,
                    Panel(
                        memory_content,
                        title="Memory Content",
                        border_style="blue",
                        expand=False,
                    ),
                )
            else:
                console_manager.print_warning(
                    "Memory is empty. Use 'vibectl memory set' to add content."
                )
            # Don't return, continue the loop to show the confirmation dialog again
            continue

        if choice in ["n", "b"]:
            # No or No But - don't execute the command
            logger.info(
                f"User cancelled execution of planned command: "
                f"kubectl {cmd_for_display} {display_cmd}"
            )
            console_manager.print_cancelled()

            # If "but" is chosen, do a fuzzy memory update
            if choice == "b":
                return _handle_fuzzy_memory_update("no but", model_name)
            return Success(message="Command execution cancelled by user")

        # Handle the Exit option if in semiauto mode
        elif choice == "e" and semiauto:
            logger.info("User chose to exit the semiauto loop")
            console_manager.print_note("Exiting semiauto session")
            # Instead of raising an exception or returning an Exit type,
            # return a Success with continue_execution=False
            return Success(
                message="User requested exit from semiauto loop",
                continue_execution=False,
            )

        elif choice in ["y", "a"]:
            # Yes or Yes And - execute the command
            logger.info("User approved execution of planned command")

            # If "and" is chosen, do a fuzzy memory update
            if choice == "a":
                memory_result = _handle_fuzzy_memory_update("yes and", model_name)
                if isinstance(memory_result, Error):
                    return memory_result

            # Proceed with command execution
            return None


def _handle_fuzzy_memory_update(option: str, model_name: str) -> Result:
    """Handle fuzzy memory updates.

    Args:
        option: The option chosen ("yes and" or "no but")
        model_name: The model name to use

    Returns:
        Result if an error occurred, Success otherwise
    """
    logger.info(f"User requested fuzzy memory update with '{option}' option")
    console_manager.print_note("Enter additional information for memory:")
    update_text = click.prompt("Memory update")

    # Update memory with the provided text
    from vibectl.config import Config

    try:
        # Get the model name from config if not specified
        cfg = Config()
        current_memory = get_memory()

        # Get the model
        model_adapter = get_model_adapter()
        model = model_adapter.get_model(model_name)

        # Create a prompt for the fuzzy memory update
        prompt = memory_fuzzy_update_prompt(current_memory, update_text, cfg)

        # Get the response
        console_manager.print_processing("Updating memory...")
        updated_memory = model_adapter.execute(model, prompt)

        # Set the updated memory
        set_memory(updated_memory, cfg)
        console_manager.print_success("Memory updated")

        # Display the updated memory
        console_manager.safe_print(
            console_manager.console,
            Panel(
                updated_memory,
                title="Updated Memory Content",
                border_style="blue",
                expand=False,
            ),
        )

        return Success(message="Memory updated successfully")
    except Exception as e:
        logger.error(f"Error updating memory: {e}")
        console_manager.print_error(f"Error updating memory: {e}")
        return Error(error=f"Error updating memory: {e}", exception=e)


def _process_command_string(kubectl_cmd: str) -> tuple[str, str | None]:
    """Process the command string to extract YAML content and command arguments.

    Args:
        kubectl_cmd: The command string from the model

    Returns:
        Tuple of (command arguments, YAML content or None)
    """
    # Check for heredoc syntax (create -f - << EOF)
    if " << EOF" in kubectl_cmd or " <<EOF" in kubectl_cmd:
        # Find the start of the heredoc
        if " << EOF" in kubectl_cmd:
            cmd_parts = kubectl_cmd.split(" << EOF", 1)
        else:
            cmd_parts = kubectl_cmd.split(" <<EOF", 1)

        cmd_args = cmd_parts[0].strip()
        yaml_content = None

        # If there's content after the heredoc marker, treat it as YAML
        if len(cmd_parts) > 1:
            yaml_content = cmd_parts[1].strip()
            # Remove trailing EOF if present
            if yaml_content.endswith("EOF"):
                yaml_content = yaml_content[:-3].strip()

        return cmd_args, yaml_content

    # Check for YAML content separated by --- (common in kubectl manifests)
    cmd_parts = kubectl_cmd.split("---", 1)
    cmd_args = cmd_parts[0].strip()
    yaml_content = None
    if len(cmd_parts) > 1:
        yaml_content = "---" + cmd_parts[1]

    return cmd_args, yaml_content


def _parse_command_args(cmd_args: str) -> list[str]:
    """Parse command arguments into a list.

    Args:
        cmd_args: The command arguments string

    Returns:
        List of command arguments
    """
    import shlex

    # Use shlex to properly handle quoted arguments
    try:
        # This preserves quotes and handles spaces in arguments properly
        args = shlex.split(cmd_args)
    except ValueError:
        # Fall back to simple splitting if shlex fails (e.g., unbalanced quotes)
        args = cmd_args.split()

    return args


def _filter_kubeconfig_flags(args: list[str]) -> list[str]:
    """Filter out kubeconfig flags from the command arguments.

    This is a stub function left for backward compatibility.

    Args:
        args: List of command arguments

    Returns:
        The same list of arguments unchanged
    """
    return args


def _create_display_command(args: list[str], yaml_content: str | None) -> str:
    """Create a display-friendly command string.

    Args:
        args: List of command arguments
        yaml_content: YAML content if present

    Returns:
        Display-friendly command string
    """
    import shlex

    # Reconstruct the command for display
    if yaml_content:
        # For commands with YAML, show a simplified version
        if args and args[0] == "create":
            # For create, we show that it's using a YAML file
            return f"{' '.join(args)} (with YAML content)"
        else:
            # For other commands, standard format with YAML note
            return f"{' '.join(args)} -f (YAML content)"
    else:
        # For standard commands without YAML, quote arguments with spaces/chars
        display_args = []
        for arg in args:
            # Check if the argument needs quoting
            chars = "\"'<>|&;()"
            has_space = " " in arg
            has_special = any(c in arg for c in chars)
            if has_space or has_special:
                # Use shlex.quote to properly quote the argument
                display_args.append(shlex.quote(arg))
            else:
                display_args.append(arg)
        return " ".join(display_args)


def _needs_confirmation(command: str, semiauto: bool) -> bool:
    """Check if a command needs confirmation.

    Args:
        command: Command type
        semiauto: Whether the command is running in semiauto mode
            (always requires confirmation)

    Returns:
        Whether the command needs confirmation
    """
    # Always confirm in semiauto mode
    if semiauto:
        return True

    # These commands need confirmation due to their potentially dangerous nature
    dangerous_commands = [
        "delete",
        "scale",
        "rollout",
        "patch",
        "apply",
        "replace",
        "create",
    ]
    return command in dangerous_commands


def _execute_command(args: list[str], yaml_content: str | None) -> Result:
    """Execute the kubectl command with the given arguments.

    Args:
        args: List of command arguments
        yaml_content: YAML content if present

    Returns:
        Result with Success containing command output or Error with error information
    """
    try:
        if yaml_content:
            return _execute_yaml_command(args, yaml_content)
        else:
            # Check if any arguments contain spaces or special characters
            has_complex_args = any(
                " " in arg or "<" in arg or ">" in arg for arg in args
            )

            if has_complex_args:
                # Use direct subprocess execution with preserved argument structure
                return _execute_command_with_complex_args(args)
            else:
                # Regular command without complex arguments
                # Ensure we directly call run_kubectl - this is important for tests
                return run_kubectl(args, capture=True)
    except Exception as e:
        logger.error("Error executing command: %s", e, exc_info=True)
        return create_kubectl_error(f"Error executing command: {e}", exception=e)


def _execute_command_with_complex_args(args: list[str]) -> Result:
    """Execute a kubectl command with complex arguments that need special handling.

    Args:
        args: List of command arguments

    Returns:
        Result with Success containing command output or Error with error information
    """
    import subprocess

    try:
        # Build the full command to preserve argument structure
        cmd = ["kubectl"]

        # Add each argument, preserving structure that might have
        # spaces or special chars
        for arg in args:
            cmd.append(arg)

        # Run the command, preserving the argument structure
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return Success(data=result.stdout)
    except subprocess.CalledProcessError as e:
        if e.stderr:
            console_manager.print_error(e.stderr)
            # Use create_kubectl_error to properly set halt_auto_loop
            return create_kubectl_error(f"Command failed: {e.stderr}", exception=e)
        # Use create_kubectl_error for exit code errors too
        return create_kubectl_error(
            f"Command failed with exit code {e.returncode}", exception=e
        )
    except Exception as e:
        logger.error("Error executing command with complex args: %s", e, exc_info=True)
        return Error(error=f"Error executing command: {e}", exception=e)


def _execute_yaml_command(args: list[str], yaml_content: str) -> Result:
    """Execute a kubectl command with YAML content.

    Args:
        args: List of command arguments
        yaml_content: YAML content to use

    Returns:
        Result with Success containing command output or Error with error information
    """
    import re
    import subprocess
    import tempfile
    from subprocess import TimeoutExpired

    try:
        # Fix multi-document YAML formatting issues
        # Ensure document separators are at the beginning of lines with no indentation
        # This addresses "mapping values are not allowed in this context" errors
        yaml_content = re.sub(r"^(\s+)---\s*$", "---", yaml_content, flags=re.MULTILINE)

        # Ensure each document starts with --- including the first
        # one if it doesn't already
        if not yaml_content.lstrip().startswith("---"):
            yaml_content = "---\n" + yaml_content

        # Check if this is a stdin pipe command (kubectl ... -f -)
        is_stdin_command = False
        for i, arg in enumerate(args):
            if arg == "-f" and i + 1 < len(args) and args[i + 1] == "-":
                is_stdin_command = True
                break

        if is_stdin_command:
            # For commands like kubectl create -f -, use Popen with stdin
            cmd = ["kubectl", *args]

            # Use bytes mode for Popen to avoid encoding issues
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,  # Use bytes mode
            )

            # Encode the YAML content to bytes
            yaml_bytes = yaml_content.encode("utf-8")
            try:
                stdout_bytes, stderr_bytes = process.communicate(
                    input=yaml_bytes, timeout=30
                )  # Add 30-second timeout
            except TimeoutExpired:
                # Try to terminate the process if it's still running
                process.kill()
                # Attempt to collect any output that might be available
                stdout_bytes, stderr_bytes = process.communicate()
                # Return an error with a clear message
                return Error(
                    error="Command timed out after 30 seconds",
                    exception=Exception("Subprocess timeout"),
                )

            # Decode the output back to strings
            stdout = stdout_bytes.decode("utf-8")
            stderr = stderr_bytes.decode("utf-8")

            if process.returncode != 0:
                error_msg = (
                    stderr or f"Command failed with exit code {process.returncode}"
                )
                return create_kubectl_error(error_msg)

            return Success(data=stdout)
        else:
            # For the command, use a temporary file
            temp_path = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".yaml", delete=False
                ) as temp:
                    temp.write(yaml_content)
                    temp_path = temp.name

                # For create commands that might be using --from-literal
                # or similar flags
                # just pass the arguments as is and add the -f flag
                cmd = ["kubectl", *args]

                # Only add -f if we have YAML content and it's not already in the args
                if yaml_content and not any(
                    arg == "-f" or arg.startswith("-f=") for arg in args
                ):
                    cmd.extend(["-f", temp_path])

                proc = subprocess.run(cmd, capture_output=True, text=True, check=False)

                if proc.returncode != 0:
                    error_msg = (
                        proc.stderr
                        or f"Command failed with exit code {proc.returncode}"
                    )
                    return create_kubectl_error(error_msg)

                return Success(data=proc.stdout)
            finally:
                # Clean up the temporary file
                if temp_path:
                    import os

                    try:
                        os.unlink(temp_path)
                    except Exception as cleanup_error:
                        logger.warning(
                            f"Failed to clean up temporary file: {cleanup_error}"
                        )
    except Exception as e:
        logger.error("Error executing YAML command: %s", e, exc_info=True)
        return Error(error=f"Error executing YAML command: {e}", exception=e)


def configure_output_flags(
    show_raw_output: bool | None = None,
    yaml: bool | None = None,
    json: bool | None = None,
    vibe: bool | None = None,
    show_vibe: bool | None = None,
    model: str | None = None,
    show_kubectl: bool | None = None,
) -> OutputFlags:
    """Configure output flags based on config.

    Args:
        show_raw_output: Optional override for showing raw output
        yaml: Optional override for showing YAML output
        json: Optional override for showing JSON output
        vibe: Optional override for showing vibe output
        show_vibe: Optional override for showing vibe output
        model: Optional override for LLM model
        show_kubectl: Optional override for showing kubectl commands

    Returns:
        OutputFlags instance containing the configured flags
    """
    config = Config()

    # Use provided values or get from config with defaults
    show_raw = (
        show_raw_output
        if show_raw_output is not None
        else config.get("show_raw_output", DEFAULT_CONFIG["show_raw_output"])
    )

    show_vibe_output = (
        show_vibe
        if show_vibe is not None
        else vibe
        if vibe is not None
        else config.get("show_vibe", DEFAULT_CONFIG["show_vibe"])
    )

    # Get warn_no_output setting - default to True (do warn when no output)
    warn_no_output = config.get("warn_no_output", DEFAULT_CONFIG["warn_no_output"])

    # Get warn_no_proxy setting - default to True (do warn when proxy not configured)
    warn_no_proxy = config.get("warn_no_proxy", True)

    model_name = (
        model if model is not None else config.get("model", DEFAULT_CONFIG["model"])
    )

    # Get show_kubectl setting - default to False
    show_kubectl_commands = (
        show_kubectl
        if show_kubectl is not None
        else config.get("show_kubectl", DEFAULT_CONFIG["show_kubectl"])
    )

    return OutputFlags(
        show_raw=show_raw,
        show_vibe=show_vibe_output,
        warn_no_output=warn_no_output,
        model_name=model_name,
        show_kubectl=show_kubectl_commands,
        warn_no_proxy=warn_no_proxy,
    )


def handle_wait_with_live_display(
    resource: str,
    args: tuple[str, ...],
    output_flags: OutputFlags,
) -> Result:
    """Handle wait command with a live spinner and elapsed time display.

    Args:
        resource: Resource to wait for
        args: Command line arguments
        output_flags: Output configuration flags

    Returns:
        Result with Success containing wait output or Error with error information
    """
    # Extract the condition from args for display
    condition = "condition"
    for arg in args:
        if arg.startswith("--for="):
            condition = arg[6:]
            break

    # Create the command for display
    display_text = f"Waiting for {resource} to meet {condition}"

    # Track start time to calculate total duration
    start_time = time.time()

    # This is our async function to run the kubectl wait command
    async def async_run_wait_command() -> Result:
        """Run kubectl wait command asynchronously."""
        # Build command list
        cmd_args = ["wait", resource]
        if args:
            cmd_args.extend(args)

        # Execute the command in a separate thread to avoid blocking the event loop
        # We use asyncio.to_thread to run the blocking kubectl call in a thread pool
        return await asyncio.to_thread(run_kubectl, cmd_args, capture=True)

    # Create a coroutine to update the progress display continuously
    async def update_progress(task_id: TaskID, progress: Progress) -> None:
        """Update the progress display regularly."""
        try:
            # Keep updating at a frequent interval until cancelled
            while True:
                progress.update(task_id)
                # Very small sleep interval for smoother animation
                # (20-30 updates per second)
                await asyncio.sleep(0.03)
        except asyncio.CancelledError:
            # Handle cancellation gracefully by doing a final update
            progress.update(task_id)
            return

    # Create a more visually appealing progress display
    with Progress(
        SpinnerColumn(),
        TimeElapsedColumn(),
        TextColumn("[bold blue]{task.description}"),
        console=console_manager.console,
        transient=True,
        refresh_per_second=30,  # Higher refresh rate for smoother animation
    ) as progress:
        # Add a wait task
        task_id = progress.add_task(description=display_text, total=None)

        # Define the async main routine that coordinates the wait operation
        async def main() -> Result:
            """Main async routine that runs the wait command and updates progress."""
            # Start updating the progress display in a separate task
            progress_task = asyncio.create_task(update_progress(task_id, progress))

            # Force at least one update to ensure spinner visibility
            await asyncio.sleep(0.1)

            try:
                # Run the wait command
                result = await async_run_wait_command()

                # Give the progress display time to show completion
                # (avoids abrupt disappearance)
                await asyncio.sleep(0.5)

                # Cancel the progress update task
                if not progress_task.done():
                    progress_task.cancel()
                    # Wait for the task to actually cancel
                    with suppress(asyncio.TimeoutError, asyncio.CancelledError):
                        await asyncio.wait_for(progress_task, timeout=0.5)

                return result
            except Exception as e:
                # Ensure we cancel the progress task on errors
                if not progress_task.done():
                    progress_task.cancel()
                    with suppress(asyncio.TimeoutError, asyncio.CancelledError):
                        await asyncio.wait_for(progress_task, timeout=0.5)

                # Return an error result
                return Error(error=str(e), exception=e)

        # Set up loop and run the async code
        result = None
        created_new_loop = False
        loop = None
        wait_success = False  # Track if wait completed successfully

        try:
            # Get or create an event loop in a resilient way
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If we're in a running loop context, create a new one
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    created_new_loop = True
            except RuntimeError:
                # If we can't get a loop, create a new one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                created_new_loop = True

            # Run our main coroutine in the event loop
            result = loop.run_until_complete(main())
            wait_success = isinstance(
                result, Success
            )  # Success if we got a Success result

        except asyncio.CancelledError:
            # Handle user interrupts (like Ctrl+C)
            console_manager.print_note("Wait operation cancelled")
            return Error(error="Wait operation cancelled by user")

        finally:
            # Clean up the progress display
            progress.stop()

            # If we created a new loop, close it to prevent asyncio warnings
            if created_new_loop and loop is not None:
                loop.close()

    # Calculate elapsed time regardless of output
    elapsed_time = time.time() - start_time

    # Handle the command output if any
    if wait_success and isinstance(result, Success):
        # Display success message with duration
        console_manager.console.print(
            f"[bold green]✓[/] Wait completed in [bold]{elapsed_time:.2f}s[/]"
        )

        # Add a small visual separator before the output
        if output_flags.show_raw or output_flags.show_vibe:
            console_manager.console.print()

        output_result = handle_command_output(
            output=result.data or "",
            output_flags=output_flags,
            summary_prompt_func=wait_resource_prompt,
            command=f"wait {resource} {' '.join(args)}",
        )
        return output_result
    elif wait_success:
        # If wait completed successfully but there's no output to display
        success_message = (
            f"[bold green]✓[/] {resource} now meets condition '[bold]{condition}[/]' "
            f"(completed in [bold]{elapsed_time:.2f}s[/])"
        )
        console_manager.safe_print(console_manager.console, success_message)

        # Add a small note if no output will be shown
        if not output_flags.show_raw and not output_flags.show_vibe:
            message = (
                "\nNo output display enabled. Use --show-raw-output or "
                "--show-vibe to see details."
            )
            console_manager.console.print(message)

        return Success(
            message=(
                f"{resource} now meets condition '{condition}' "
                f"(completed in {elapsed_time:.2f}s)"
            ),
        )
    else:
        # If there was an issue but we didn't raise an exception
        if isinstance(result, Error):
            message = (
                f"[bold red]✗[/] Wait operation failed after "
                f"[bold]{elapsed_time:.2f}s[/]: {result.error}"
            )
            console_manager.safe_print(console_manager.console, message)
            return result
        else:
            message = (
                f"[bold yellow]![/] Wait operation completed with no result "
                f"after [bold]{elapsed_time:.2f}s[/]"
            )
            console_manager.console.print(message)
            return Error(
                error=(
                    f"Wait operation completed with no result after {elapsed_time:.2f}s"
                )
            )


class ConnectionStats(StatsProtocol):
    """Track connection statistics for port-forward sessions."""

    def __init__(self) -> None:
        """Initialize connection statistics."""
        self.current_status = "Connecting"  # Current connection status
        self.connections_attempted = 0  # Number of connection attempts
        self.successful_connections = 0  # Number of successful connections
        self.bytes_sent = 0  # Bytes sent through connection
        self.bytes_received = 0  # Bytes received through connection
        self.elapsed_connected_time = 0.0  # Time in seconds connection was active
        self.traffic_monitoring_enabled = False  # Whether traffic stats are available
        self.using_proxy = False  # Whether connection is going through proxy
        self.error_messages: list[str] = []  # List of error messages encountered
        self._last_activity_time = time.time()  # Timestamp of last activity

    @property
    def last_activity(self) -> float:
        """Get the timestamp of the last activity."""
        return self._last_activity_time

    @last_activity.setter
    def last_activity(self, value: float) -> None:
        """Set the timestamp of the last activity."""
        self._last_activity_time = value


def has_port_mapping(port_mapping: str) -> bool:
    """Check if a valid port mapping is provided.

    Args:
        port_mapping: The port mapping string to check

    Returns:
        True if a valid port mapping with format "local:remote" is provided
    """
    return ":" in port_mapping and all(
        part.isdigit() for part in port_mapping.split(":")
    )


def handle_port_forward_with_live_display(
    resource: str,
    args: tuple[str, ...],
    output_flags: OutputFlags,
) -> Result:
    """Handle port-forward command with a live display showing connection status
    and ports.

    Args:
        resource: Resource to forward ports for
        args: Command line arguments including port specifications
        output_flags: Output configuration flags

    Returns:
        Result with Success containing port-forward information or Error on failure
    """
    # Extract port mapping from args for display
    port_mapping = "port"
    for arg in args:
        if ":" in arg and all(part.isdigit() for part in arg.split(":")):
            port_mapping = arg
            break

    # Format local and remote ports for display
    local_port, remote_port = (
        port_mapping.split(":") if ":" in port_mapping else (port_mapping, port_mapping)
    )

    # Create the command for display
    display_text = (
        f"Forwarding {resource} port [bold]{remote_port}[/] "
        f"to localhost:[bold]{local_port}[/]"
    )

    # Track start time for elapsed time display
    start_time = time.time()

    # Create a stats object to track connection information
    stats = ConnectionStats()

    # Check if traffic monitoring is enabled via intermediate port range
    cfg = Config()
    intermediate_port_range = cfg.get("intermediate_port_range")
    use_proxy = False
    proxy_port = None

    # Check if a port mapping was provided (required for proxy)
    has_valid_port_mapping = has_port_mapping(port_mapping)

    if intermediate_port_range and has_valid_port_mapping:
        try:
            # Parse the port range
            min_port, max_port = map(int, intermediate_port_range.split("-"))

            # Get a random port in the range
            proxy_port = random.randint(min_port, max_port)

            # Enable proxy mode
            use_proxy = True
            stats.using_proxy = True
            stats.traffic_monitoring_enabled = True

            console_manager.print_note(
                f"Traffic monitoring enabled via proxy on port {proxy_port}"
            )
        except (ValueError, AttributeError) as e:
            console_manager.print_error(
                f"Invalid intermediate_port_range format: {intermediate_port_range}. "
                f"Expected format: 'min-max'. Error: {e}"
            )
            use_proxy = False
            return Error(
                error=(
                    f"Invalid intermediate_port_range format: "
                    f"{intermediate_port_range}. Expected format: 'min-max'."
                ),
                exception=e,
            )
    elif (
        not intermediate_port_range
        and has_valid_port_mapping
        and output_flags.warn_no_proxy
    ):
        # Show warning about missing proxy configuration when port mapping is provided
        console_manager.print_no_proxy_warning()

    # Create a subprocess to run kubectl port-forward
    # We'll use asyncio to manage this process and update the display
    async def run_port_forward() -> asyncio.subprocess.Process:
        """Run the port-forward command and capture output."""
        # Build command list
        cmd_args = ["port-forward", resource]

        # Make sure we have valid args - check for resource pattern first
        args_list = list(args)

        # If using proxy, modify the port mapping argument to use proxy_port
        if use_proxy and proxy_port is not None:
            # Find and replace the port mapping argument
            for i, arg in enumerate(args_list):
                if ":" in arg and all(part.isdigit() for part in arg.split(":")):
                    # Replace with proxy port:remote port
                    args_list[i] = f"{proxy_port}:{remote_port}"
                    break

        # Add remaining arguments
        if args_list:
            cmd_args.extend(args_list)

        # Full kubectl command
        kubectl_cmd = ["kubectl"]

        # Add kubeconfig if set
        kubeconfig = cfg.get("kubeconfig")
        if kubeconfig:
            kubectl_cmd.extend(["--kubeconfig", str(kubeconfig)])

        # Add the port-forward command args
        kubectl_cmd.extend(cmd_args)

        # Create a process to run kubectl port-forward
        # This process will keep running until cancelled
        process = await asyncio.create_subprocess_exec(
            *kubectl_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Increment connection attempts counter
        stats.connections_attempted += 1

        # Return reference to the process
        return process

    # Update the progress display with connection status
    async def update_progress(
        task_id: TaskID,
        progress: Progress,
        process: asyncio.subprocess.Process,
        proxy: TcpProxy | None = None,
    ) -> None:
        """Update the progress display with connection status and data."""
        connected = False
        connection_start_time = None

        try:
            # Keep updating until cancelled
            while True:
                # Check if process has output ready
                if process.stdout:
                    line = await process.stdout.readline()
                    if line:
                        # Got output, update connection status
                        line_str = line.decode("utf-8").strip()
                        if "Forwarding from" in line_str:
                            connected = True
                            stats.current_status = "Connected"
                            stats.successful_connections += 1
                            if connection_start_time is None:
                                connection_start_time = time.time()

                            # Attempt to parse traffic information if available
                            if "traffic" in line_str.lower():
                                stats.traffic_monitoring_enabled = True
                                # Extract bytes sent/received if available
                                # Parsing depends on the output format
                                if "sent" in line_str.lower():
                                    sent_match = re.search(
                                        r"sent (\d+)", line_str.lower()
                                    )
                                    if sent_match:
                                        stats.bytes_sent += int(sent_match.group(1))
                                if "received" in line_str.lower():
                                    received_match = re.search(
                                        r"received (\d+)", line_str.lower()
                                    )
                                    if received_match:
                                        stats.bytes_received += int(
                                            received_match.group(1)
                                        )

                # Update stats from proxy if enabled
                if proxy and connected:
                    # Update stats from the proxy server
                    stats.bytes_sent = proxy.stats.bytes_sent
                    stats.bytes_received = proxy.stats.bytes_received
                    stats.traffic_monitoring_enabled = True

                # Update connection time if connected
                if connected and connection_start_time is not None:
                    stats.elapsed_connected_time = time.time() - connection_start_time

                # Update the description based on connection status
                if connected:
                    if proxy:
                        # Show traffic stats in the description when using proxy
                        bytes_sent = stats.bytes_sent
                        bytes_received = stats.bytes_received
                        progress.update(
                            task_id,
                            description=(
                                f"{display_text} - [green]Connected[/green] "
                                f"([cyan]↑{bytes_sent}B[/] "
                                f"[magenta]↓{bytes_received}B[/])"
                            ),
                        )
                    else:
                        progress.update(
                            task_id,
                            description=f"{display_text} - [green]Connected[/green]",
                        )
                else:
                    # Check if the process is still running
                    if process.returncode is not None:
                        stats.current_status = "Disconnected"
                        progress.update(
                            task_id,
                            description=f"{display_text} - [red]Disconnected[/red]",
                        )
                        break

                    # Still establishing connection
                    progress.update(
                        task_id,
                        description=f"{display_text} - Connecting...",
                    )

                # Small sleep for smooth updates
                await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            # Final update before cancellation
            stats.current_status = "Cancelled"
            progress.update(
                task_id,
                description=f"{display_text} - [yellow]Cancelled[/yellow]",
            )

    # Create progress display
    with Progress(
        SpinnerColumn(),
        TimeElapsedColumn(),
        TextColumn("{task.description}"),
        console=console_manager.console,
        transient=False,  # We want to keep this visible
        refresh_per_second=10,
    ) as progress:
        # Add port-forward task
        task_id = progress.add_task(
            description=f"{display_text} - Starting...", total=None
        )

        # Define the main async routine
        async def main() -> None:
            """Main async routine that runs port-forward and updates progress."""
            proxy = None

            try:
                # Start proxy server if traffic monitoring is enabled
                if use_proxy and proxy_port is not None:
                    proxy = await start_proxy_server(
                        local_port=int(local_port), target_port=proxy_port, stats=stats
                    )

                # Start the port-forward process
                process = await run_port_forward()

                # Start updating the progress display
                progress_task = asyncio.create_task(
                    update_progress(task_id, progress, process, proxy)
                )

                try:
                    # Keep running until user interrupts with Ctrl+C
                    await process.wait()

                    # If we get here, the process completed or errored
                    if process.returncode != 0:
                        # Read error output
                        stderr = await process.stderr.read() if process.stderr else b""
                        error_msg = stderr.decode("utf-8").strip()
                        stats.error_messages.append(error_msg)
                        console_manager.print_error(f"Port-forward error: {error_msg}")

                except asyncio.CancelledError:
                    # User cancelled, terminate the process
                    process.terminate()
                    await process.wait()
                    raise

                finally:
                    # Cancel the progress task
                    if not progress_task.done():
                        progress_task.cancel()
                        with suppress(asyncio.CancelledError):
                            await asyncio.wait_for(progress_task, timeout=0.5)

            finally:
                # Clean up proxy server if it was started
                if proxy:
                    await stop_proxy_server(proxy)

        # Set up event loop and run the async code
        created_new_loop = False
        loop = None

        try:
            # Get or create an event loop
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    created_new_loop = True
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                created_new_loop = True

            # Run the main coroutine
            loop.run_until_complete(main())

        except KeyboardInterrupt:
            # Handle Ctrl+C gracefully
            stats.current_status = "Cancelled (User)"
            console_manager.print_note("\nPort-forward cancelled by user")
            return Error(error="Port-forward cancelled by user")

        except asyncio.CancelledError:
            # Handle cancellation
            stats.current_status = "Cancelled"
            console_manager.print_note("\nPort-forward cancelled")
            return Error(error="Port-forward cancelled")

        except Exception as e:
            # Handle other errors
            stats.current_status = "Error"
            stats.error_messages.append(str(e))
            console_manager.print_error(f"\nPort-forward error: {e!s}")
            return Error(error=f"Port-forward error: {e}", exception=e)

        finally:
            # Clean up
            if created_new_loop and loop is not None:
                loop.close()

    # Calculate elapsed time
    elapsed_time = time.time() - start_time

    # Show final message with elapsed time
    console_manager.print_note(
        f"\n[bold]Port-forward session ended after "
        f"[italic]{elapsed_time:.1f}s[/italic][/bold]"
    )

    # Create and display a table with connection statistics
    table = Table(title=f"Port-forward {resource} Connection Summary")

    # Add columns
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    # Add rows with connection statistics
    table.add_row("Status", stats.current_status)
    table.add_row("Resource", resource)
    table.add_row("Port Mapping", f"localhost:{local_port} → {remote_port}")
    table.add_row("Duration", f"{elapsed_time:.1f}s")
    table.add_row("Connected Time", f"{stats.elapsed_connected_time:.1f}s")
    table.add_row("Connection Attempts", str(stats.connections_attempted))
    table.add_row("Successful Connections", str(stats.successful_connections))

    # Add proxy information if enabled
    if stats.using_proxy:
        table.add_row("Traffic Monitoring", "Enabled")
        table.add_row("Proxy Mode", "Active")

    # Add traffic information if available
    if stats.traffic_monitoring_enabled:
        table.add_row("Data Sent", f"{stats.bytes_sent} bytes")
        table.add_row("Data Received", f"{stats.bytes_received} bytes")

    # Add any error messages
    if stats.error_messages:
        table.add_row("Errors", "\n".join(stats.error_messages))

    # Display the table
    console_manager.console.print(table)

    # Prepare forward info for memory
    forward_info = f"Port-forward {resource} {port_mapping} ran for {elapsed_time:.1f}s"

    # Create command string for memory
    command_str = f"port-forward {resource} {' '.join(args)}"

    # If vibe output is enabled, generate a summary using the LLM
    vibe_output = ""
    has_error = bool(stats.error_messages)

    if output_flags.show_vibe:
        try:
            # Get the prompt function
            summary_prompt_func = port_forward_prompt

            # Get LLM summary of the port-forward session
            model_adapter = get_model_adapter()
            model = model_adapter.get_model(output_flags.model_name)

            # Create detailed info for the prompt
            detailed_info = {
                "resource": resource,
                "port_mapping": port_mapping,
                "local_port": local_port,
                "remote_port": remote_port,
                "duration": f"{elapsed_time:.1f}s",
                "command": command_str,
                "status": stats.current_status,
                "connected_time": f"{stats.elapsed_connected_time:.1f}s",
                "connection_attempts": stats.connections_attempted,
                "successful_connections": stats.successful_connections,
                "traffic_monitoring_enabled": stats.traffic_monitoring_enabled,
                "using_proxy": stats.using_proxy,
                "bytes_sent": stats.bytes_sent,
                "bytes_received": stats.bytes_received,
                "errors": stats.error_messages,
            }

            # Format as YAML for the prompt
            detailed_yaml = yaml.safe_dump(detailed_info, default_flow_style=False)

            # Get the prompt template and format it
            summary_prompt = summary_prompt_func()
            prompt = summary_prompt.format(output=detailed_yaml, command=command_str)

            # Execute the prompt to get a summary
            vibe_output = model_adapter.execute(model, prompt)

            # Display the vibe output
            if vibe_output:
                console_manager.print_vibe(vibe_output)

        except Exception as e:
            # Don't let errors in vibe generation break the command
            console_manager.print_error(f"Error generating summary: {e}")
            logger.error(f"Error generating port-forward summary: {e}", exc_info=True)

    # Update memory with the port-forward information
    update_memory(
        command_str,
        forward_info,
        vibe_output,  # Now using the generated vibe output
        output_flags.model_name,
    )

    # Return appropriate result
    if has_error:
        return Error(
            error="\n".join(stats.error_messages)
            or "Port-forward completed with errors",
        )
    else:
        return Success(
            message=(
                f"Port-forward {resource} {port_mapping} completed "
                f"successfully ({elapsed_time:.1f}s)"
            ),
            data=vibe_output,
        )
