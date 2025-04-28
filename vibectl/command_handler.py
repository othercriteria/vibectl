"""
Command handler module for vibectl.

Provides reusable patterns for command handling and execution
to reduce duplication across CLI commands.

Note: All exceptions should propagate to the CLI entry point for centralized error
handling. Do not print or log user-facing errors here; use logging for diagnostics only.
"""

import subprocess
from collections.abc import Callable

import click
from rich.panel import Panel
from rich.table import Table

from .config import (
    DEFAULT_CONFIG,
    Config,
)
from .k8s_utils import create_kubectl_error, run_kubectl
from .live_display import (
    _execute_port_forward_with_live_display,
    _execute_wait_with_live_display,
)
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
from .types import Error, OutputFlags, Result, Success
from .utils import console_manager

logger = _logger

# Export Table for testing
__all__ = ["Table"]


# Initialize output processor
output_processor = OutputProcessor(max_chars=2000, llm_max_chars=2000)


def handle_standard_command(
    command: str,
    resource: str,
    args: tuple,
    output_flags: OutputFlags,
    summary_prompt_func: Callable[[], str],
) -> Result:
    """Handle standard kubectl commands like get, describe, logs.

    Args:
        command: The kubectl command (get, describe, logs, etc.)
        resource: The resource type (e.g., pods, deployments)
        args: Additional arguments for the command
        output_flags: Flags controlling output format

    Returns:
        Result object containing output or error
    """
    result = _run_standard_kubectl_command(command, resource, args)

    if isinstance(result, Error):
        # Handle API errors specifically if needed
        if is_api_error(result.error):
            return create_api_error(result.error, result.exception)
        # Ensure exception exists before passing
        if result.exception:
            return _handle_standard_command_error(
                command,
                resource,
                args,
                result.exception,
            )
        else:
            # Handle case where Error has no exception (should not happen often)
            logger.error(
                f"Command {command} {resource} failed with error but "
                f"no exception: {result.error}"
            )
            return result  # Return the original error

    output = result.data

    # Handle empty output
    # Ensure output is not None before checking/stripping
    if output is None or not output.strip():
        return _handle_empty_output(command, resource, args)

    # Process and display output based on flags
    # Pass command type to handle_command_output
    # Output is guaranteed to be a string here
    return handle_command_output(
        output,
        output_flags,
        summary_prompt_func,
        command=command,
    )


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
    command: str | None = None,
) -> Result:
    """Processes and displays command output based on flags.

    Args:
        output: The command output string or a Result object.
        output_flags: Flags controlling the output format.
        max_token_limit: Max token limit for LLM input.
        truncation_ratio: Ratio for truncating long output.
        command: The original kubectl command type (e.g., get, describe).

    Returns:
        Result object containing the processed output or original error.
    """
    _check_output_visibility(output_flags)

    if isinstance(output, Error):
        # If input is an Error, display it and return
        console_manager.print_error(output.error)
        return output

    # Extract string output from Success object if needed
    output_str = output.data if isinstance(output, Success) else output

    _display_kubectl_command(output_flags, command)
    # Ensure output_str is not None before displaying
    if output_str is not None:
        _display_raw_output(output_flags, output_str)

    # Determine if Vibe processing is needed
    if output_flags.show_vibe:
        summary_prompt_str = summary_prompt_func()

        # Pass the formatted string to _process_vibe_output
        # Ensure output_str is not None before processing
        if output_str is not None:
            try:
                vibe_result = _process_vibe_output(
                    output_str,
                    output_flags,
                    summary_prompt_str=summary_prompt_str,  # Pass formatted string
                    command=command,
                )
                # Directly return the result from vibe processing
                return vibe_result
            except Exception as e:
                logger.error(f"Error during Vibe processing: {e}", exc_info=True)
                console_manager.print_error(f"Error processing Vibe output: {e}")
                # Return an Error object after handling the exception
                error_str = str(e)
                if is_api_error(error_str):
                    return create_api_error(error_str, exception=e)
                else:
                    return Error(error=error_str, exception=e)
        else:
            # Handle case where output_str is None but Vibe was requested
            logger.warning("Cannot process Vibe output because input output was None.")
            return Error(
                error="Input command output was None, cannot generate Vibe summary."
            )

    else:
        # If only raw output is requested, return it as Success
        # Ensure output_str is not None before returning
        return Success(message=output_str if output_str is not None else "")


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
    summary_prompt_str: str,
    command: str | None = None,
) -> Result:
    """Processes output using Vibe LLM for summary.

    Args:
        output: The raw command output string.
        output_flags: Flags controlling output format.
        summary_prompt_str: The formatted prompt string for the LLM.

        command: The original kubectl command type.

    Returns:
        Result object with Vibe summary or an Error.
    """
    # Truncate output if necessary
    processed_output = output_processor.process_auto(output).truncated

    # Get LLM summary
    try:
        vibe_output = _get_llm_summary(
            processed_output,
            output_flags.model_name,
            summary_prompt_str,  # Pass formatted string
        )

        # Check if the LLM returned an error string
        if vibe_output.startswith("ERROR:"):
            error_message = vibe_output[7:].strip()
            logger.error(f"LLM summary error: {error_message}")
            console_manager.print_error(vibe_output)  # Display the full ERROR: string
            # Check if it's an API error to set halt_auto_loop correctly
            if is_api_error(error_message):
                # Pass the error message without the ERROR: prefix
                return create_api_error(error_message)
            else:
                return Error(error=error_message)

        _display_vibe_output(vibe_output)

        # Update memory only if Vibe summary succeeded (and wasn't an error string)
        update_memory(
            command=command or "Unknown",
            command_output=output,  # Store original full output in memory
            vibe_output=vibe_output,
            model_name=output_flags.model_name,
        )
        return Success(message=vibe_output)
    except Exception as e:
        logger.error(f"Error getting Vibe summary: {e}", exc_info=True)
        console_manager.print_error(f"Error processing Vibe output: {e}")
        return Error(error=str(e), exception=e)


def _get_llm_summary(
    processed_output: str,
    model_name: str,
    summary_prompt_str: str,
) -> str:
    """Gets the LLM summary for the processed output.

    Args:
        processed_output: The processed (potentially truncated) output.
        model_name: Name of the LLM model to use.
        summary_prompt_str: The formatted prompt string for the LLM.
        command: The original kubectl command type.

    Returns:
        The summary generated by the LLM.
    """
    model_adapter = get_model_adapter()
    model = model_adapter.get_model(model_name)
    # Format the prompt string with the output
    final_prompt = summary_prompt_str.format(output=processed_output)
    return model_adapter.execute(model, final_prompt)


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

        # Format the prompt for the LLM - Directly format plan_prompt
        # Remove call to _format_vibe_prompt
        try:
            # Pass both request and memory_context
            formatted_prompt = plan_prompt.format(
                request=request,
                memory_context=memory_context,
            )
        except KeyError as e:
            logger.warning(
                f"Prompt formatting failed for request '{request}' "
                f"(Format error: {e}). Using fallback formatting method."
            )
            # Fallback if prompt doesn't use {request} key
            formatted_prompt = plan_prompt

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
                # Format the recovery prompt (only needs command and error)
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

        # TODO: refactor for cleaner control and explicit passing of prompt...
        return handle_wait_with_live_display(
            resource,
            wait_args,
            modified_output_flags,
            summary_prompt_func=wait_resource_prompt,
        )

    # Handle port-forward with live display
    if (
        command == "port-forward"
        and live_display
        and len(args) > 0
        and args[0] == "port-forward"
    ):
        resource = args[1] if len(args) > 1 else ""
        port_args = tuple(args[2:]) if len(args) > 2 else ()

        # TODO: refactor for cleaner control and explicit passing of prompt...
        return handle_port_forward_with_live_display(
            resource,
            port_args,
            modified_output_flags,
            summary_prompt_func=port_forward_prompt,
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
    try:
        # Get the model name from config if not specified
        cfg = Config()
        current_memory = get_memory(cfg)  # Pass cfg

        # Get the model
        model_adapter = get_model_adapter(cfg)  # Pass cfg
        model = model_adapter.get_model(model_name)

        # Create a prompt for the fuzzy memory update
        # Pass context arguments explicitly to memory_fuzzy_update_prompt if required
        # Assuming memory_fuzzy_update_prompt handles context internally via config
        prompt = memory_fuzzy_update_prompt(
            current_memory=current_memory,
            update_text=update_text,
        )

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


def parse_kubectl_command(command_string: str) -> tuple[str, list[str]]:
    """Parses a kubectl command string into command and arguments."""
    # Split the command string into command and arguments
    parts = command_string.split(maxsplit=1)
    if len(parts) > 1:
        command = parts[0]
        args = parts[1].split()
    else:
        command = parts[0]
        args = []
    return command, args


# Wrapper for wait command live display
def handle_wait_with_live_display(
    resource: str,
    args: tuple[str, ...],
    output_flags: OutputFlags,
    summary_prompt_func: Callable[[], str],
) -> Result:
    """Handles `kubectl wait` by preparing args and calling the live display worker.

    Args:
        resource: The resource type (e.g., pod, deployment).
        args: Command arguments including resource name and conditions.
        output_flags: Flags controlling output format.

    Returns:
        Result from the live display worker function.
    """
    # Extract the condition from args for display
    condition = "condition"
    for arg in args:
        if arg.startswith("--for="):
            condition = arg[6:]
            break

    # Create the command for display
    display_text = f"Waiting for {resource} to meet {condition}"

    # Call the worker function in live_display.py
    wait_result = _execute_wait_with_live_display(
        resource=resource,
        args=args,
        output_flags=output_flags,
        condition=condition,
        display_text=display_text,
    )

    # Process the result from the worker using handle_command_output
    # Create the command string for context
    command_str = f"wait {resource} {' '.join(args)}"
    return handle_command_output(
        output=wait_result,  # Pass the Result object directly
        output_flags=output_flags,
        summary_prompt_func=summary_prompt_func,
        command=command_str,
    )


# Wrapper for port-forward command live display
def handle_port_forward_with_live_display(
    resource: str,
    args: tuple[str, ...],
    output_flags: OutputFlags,
    summary_prompt_func: Callable[[], str],
) -> Result:
    """Handles `kubectl port-forward` by preparing args and invoking live display.

    Args:
        resource: The resource type (e.g., pod, service).
        args: Command arguments including resource name and port mappings.
        output_flags: Flags controlling output format.

    Returns:
        Result from the live display worker function.
    """
    # Extract port mapping from args for display
    port_mapping = "port"
    for arg in args:
        # Simple check for port mapping format (e.g., 8080:80)
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

    # Call the worker function in live_display.py
    return _execute_port_forward_with_live_display(
        resource=resource,
        args=args,
        output_flags=output_flags,
        port_mapping=port_mapping,
        local_port=local_port,
        remote_port=remote_port,
        display_text=display_text,
        summary_prompt_func=summary_prompt_func,
    )
