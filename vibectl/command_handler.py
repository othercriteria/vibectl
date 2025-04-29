"""
Command handler module for vibectl.

Provides reusable patterns for command handling and execution
to reduce duplication across CLI commands.

Note: All exceptions should propagate to the CLI entry point for centralized error
handling. Do not print or log user-facing errors here; use logging for diagnostics only.
"""

import json
import time
from collections.abc import Callable
from json import JSONDecodeError

import click
from pydantic import ValidationError
from rich.panel import Panel
from rich.table import Table

from .config import (
    DEFAULT_CONFIG,
    Config,
)
from .k8s_utils import (
    create_kubectl_error,
    run_kubectl,
    run_kubectl_with_complex_args,
    run_kubectl_with_yaml,
)
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
    recovery_prompt,
)
from .schema import LLMCommandResponse, ActionType
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

    original_error_object: Error | None = None
    output_str: str | None = None

    if isinstance(output, Error):
        original_error_object = output
        console_manager.print_error(original_error_object.error)
        # Even if it's an error, we might get recovery suggestions if show_vibe is true
        # Extract the error string for potential Vibe processing
        output_str = original_error_object.error
    elif isinstance(output, Success):
        output_str = output.data
    else: # Plain string input
        output_str = output

    _display_kubectl_command(output_flags, command)

    # Display raw output (if available and requested)
    # For errors, display the error string itself if raw is requested.
    if output_str is not None:
        _display_raw_output(output_flags, output_str)

    # Determine if Vibe processing (summary or recovery) is needed
    if output_flags.show_vibe:
        if output_str is not None:
            try:
                # If we started with an error, generate a recovery prompt
                if original_error_object:
                    prompt_str = recovery_prompt(
                        command=command or "Unknown Command",
                        error=output_str # Use the error message as input
                    )
                    logger.info(f"Generated recovery prompt: {prompt_str}")
                    vibe_output = _get_llm_summary(
                        output_str, # Pass error string as context
                        output_flags.model_name,
                        prompt_str,
                    )
                    logger.info(f"LLM recovery suggestion: {vibe_output}")
                    console_manager.print_vibe(vibe_output)
                    # Update the original error object with the suggestion
                    original_error_object.recovery_suggestions = vibe_output
                    # Update memory with error and recovery suggestion
                    update_memory(
                        command=command or "Unknown",
                        command_output=original_error_object.error,
                        vibe_output=vibe_output,
                        model_name=output_flags.model_name,
                    )
                    return original_error_object # Return the modified error
                else:
                    # If we started with success, generate a summary prompt
                    summary_prompt_str = summary_prompt_func()
                    vibe_result = _process_vibe_output(
                        output_str, # Use success output string
                        output_flags,
                        summary_prompt_str=summary_prompt_str,
                        command=command,
                    )
                    return vibe_result

            except Exception as e:
                logger.error(f"Error during Vibe processing: {e}", exc_info=True)
                console_manager.print_error(f"Error processing Vibe output: {e}")
                error_str = str(e)
                final_error = create_api_error(error_str, exception=e) if is_api_error(error_str) else Error(error=error_str, exception=e)
                # If we started with an error, merge the vibe processing error
                if original_error_object:
                    original_error_object.error += f"\nAdditionally, failed to get recovery suggestions: {final_error.error}"
                    original_error_object.recovery_suggestions = f"Error getting suggestions: {final_error.error}"
                    return original_error_object
                else:
                    return final_error
        else:
            # Handle case where output was None but Vibe was requested
            logger.warning("Cannot process Vibe output because input was None.")
            # If we started with an Error object that had no .error string, return that
            if original_error_object:
                original_error_object.error = original_error_object.error or "Input error was None"
                original_error_object.recovery_suggestions = "Could not process None error for suggestions."
                return original_error_object
            else:
                return Error(error="Input command output was None, cannot generate Vibe summary.")

    else: # No Vibe processing requested
        # If we started with an error, return it directly
        if original_error_object:
            return original_error_object
        # Otherwise, return Success with the output string
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
    """Handle a request that requires LLM interaction for command planning.

    Args:
        request: The user's natural language request.
        command: The base kubectl command (e.g., 'get', 'describe').
        plan_prompt: The prompt template used for planning the command.
        summary_prompt_func: Function to generate the summary prompt.
        output_flags: Flags controlling output format and verbosity.
        yes: Bypass confirmation prompts.
        semiauto: Enable semi-autonomous mode (confirm once).
        live_display: Show live output for background tasks.
        memory_context: Context from fuzzy memory.
        autonomous_mode: Enable fully autonomous mode (no confirmations).

    Returns:
        Result object with the outcome of the operation.
    """
    model_name = output_flags.model_name
    model_adapter = get_model_adapter()
    # Get the model instance
    model = model_adapter.get_model(model_name)

    # Generate the schema dict for the LLM response
    # This schema dict is passed to the execute method
    schema = LLMCommandResponse.model_json_schema()

    console_manager.print_processing(f"Consulting {model_name} for a plan...")

    # including any necessary schema instructions if the caller used create_planning_prompt
    logger.debug(f"Using planning prompt template:\n{plan_prompt}")

    # Replace placeholders in the prompt template
    final_plan_prompt = plan_prompt.replace("__MEMORY_CONTEXT_PLACEHOLDER__", memory_context or "")
    final_plan_prompt = final_plan_prompt.replace("__REQUEST_PLACEHOLDER__", request or "")
    logger.debug(f"Final planning prompt:\n{final_plan_prompt}")

    try:
        # Execute the prompt with the model adapter, passing the schema dict
        # Pass model instance as first argument
        llm_response = model_adapter.execute(
            model,
            final_plan_prompt, # Pass the interpolated prompt string
            schema=schema,  # Pass the schema dict here
        )
        logger.info(f"Raw LLM response:\n{llm_response}") # Log raw response

        # === STEP 2: PARSE AND VALIDATE JSON RESPONSE ===
        # If the response is empty or whitespace, return an error
        if not llm_response or llm_response.strip() == "":
            logger.error("LLM returned an empty response.")
            return Error("LLM returned an empty response.")

        try:
            # Use model_validate_json for Pydantic V2
            response = LLMCommandResponse.model_validate_json(llm_response)
            logger.debug(f"Parsed LLM response object: {response}")
            # Explicitly convert string to ActionType enum after validation
            validated_action_type = ActionType(response.action_type)
            logger.info(f"Validated ActionType: {validated_action_type}")

            if isinstance(response.action_type, str):
                response.action_type = ActionType(response.action_type)

        except (JSONDecodeError, ValidationError) as e: # Catches parsing/schema errors
            logger.error(f"Caught inner JSONDecodeError/ValidationError: {type(e).__name__}", exc_info=True)
            # This is where the AttributeError likely occurs
            error_msg = f"Failed to parse or validate LLM response: {e}"
            # Use \\n for newline in f-string, not \\\\n
            logger.error(f"{error_msg}\\nLLM Output:\\n{llm_response}")
            # Replace the call to the non-existent function _handle_planning_error
            # with direct error handling. We treat parsing/validation errors as API errors
            # so they don't halt autonomous loops unnecessarily.
            # Use normal quotes for string literals, not escaped quotes
            update_memory("system", f"Planning Error: {error_msg}", memory_context)
            return create_api_error(error_msg, e)

        except ValueError as e: # Catches ActionType conversion errors? Unlikely.
            # Catch ValueErrors specifically (e.g., from unknown model name)
            error_msg = f"Error during LLM request execution: {e}"
            logger.error(f"Caught inner ValueError: {type(e).__name__}", exc_info=True)
            logger.error(f"{error_msg}", exc_info=True) # Log with traceback
            # Treat as an API error to avoid halting loops
            update_memory("system", f"LLM Execution Error: {error_msg}", memory_context)
            return create_api_error(error_msg, e)

        # === STEP 3: Implement ActionType Dispatch (ERROR, WAIT, FEEDBACK) ===
        match validated_action_type:
            case ActionType.ERROR:
                if not response.error:
                    logger.error("ActionType is ERROR but no error message provided.")
                    return Error(
                        error="Internal error: LLM returned ERROR action without message."
                    )
                # Handle planning errors (updates memory)
                error_message = response.error
                logger.info(f"LLM returned planning error: {error_message}")
                # Display explanation first if provided
                if response.explanation:
                    console_manager.print_note(f"AI Explanation: {response.explanation}")
                try:
                    update_memory(
                        command=command,
                        command_output=f"Planning error: {error_message}",
                        vibe_output=f"Failed to plan command for request: {request}. Error: {error_message}",
                        model_name=output_flags.model_name,
                    )
                    logger.info("Planning error added to memory context")
                except Exception as mem_e:
                    logger.error("Failed to update memory after planning error: %s", mem_e)
                console_manager.print_error(f"LLM Planning Error: {error_message}")
                return Error(
                    error=f"LLM planning error: {error_message}",
                    recovery_suggestions=response.explanation or "Check the request or try rephrasing."
                )

            case ActionType.WAIT:
                if response.wait_duration_seconds is None:
                    logger.error("ActionType is WAIT but no duration provided.")
                    return Error(
                        error="Internal error: LLM returned WAIT action without duration."
                    )
                duration = response.wait_duration_seconds
                logger.info(f"LLM requested WAIT for {duration} seconds.")
                # Display explanation first if provided
                if response.explanation:
                    console_manager.print_note(f"AI Explanation: {response.explanation}")
                console_manager.print_processing(
                    f"Waiting for {duration} seconds as requested by AI..."
                )
                time.sleep(duration)
                return Success(message=f"Waited for {duration} seconds.")

            case ActionType.FEEDBACK:
                logger.info("LLM provided FEEDBACK without command.")
                # Display explanation first if provided
                if response.explanation:
                    console_manager.print_note(f"AI Explanation: {response.explanation}")
                else:
                    # If no explanation, provide a default message
                    console_manager.print_note("Received feedback from AI.")
                return Success(message="Received feedback from AI.")

            case ActionType.COMMAND:
                # === STEP 4: Implement COMMAND branch logic ===
                if not response.commands:
                    logger.error(
                        "ActionType is COMMAND but 'commands' list is missing or empty."
                    )
                    # TODO: Update memory context on validation errors?
                    return Error(
                        error="Internal error: LLM returned COMMAND action without arguments."
                    )

                # The LLM response.commands should ONLY contain arguments, not the verb.
                # The verb comes from the original 'command' parameter passed to handle_vibe_request.
                kubectl_verb = command # Use the original command verb
                kubectl_args = response.commands # Use the list directly as arguments

                # Construct the string representation of the planned command args for logging
                planned_args_str = ' '.join(kubectl_args)
                logger.info(
                    f"LLM planned command arguments: '{planned_args_str}' for original verb: {kubectl_verb}"
                )

                # Display explanation if provided
                if response.explanation:
                    console_manager.print_note(f"AI Explanation: {response.explanation}")

                # Rebuild the command for display purposes including the correct verb
                # Pass the extracted arguments (kubectl_args) to the display helper
                cmd_for_display = _create_display_command(kubectl_args)
                display_cmd = f"kubectl {kubectl_verb} {cmd_for_display}" # Display uses original verb

                # <<< ADDED: Print the command before execution if show_kubectl is True >>>
                if output_flags.show_kubectl:
                    console_manager.print_processing(f"Running: {display_cmd}")
                # Note: YAML content is not handled in this MVP schema version

                # Handle command confirmation using the original verb
                confirmation_needed = _needs_confirmation(kubectl_verb, semiauto)
                should_confirm = confirmation_needed and not (yes or autonomous_mode)

                if should_confirm:
                    confirmation_result = _handle_command_confirmation(
                        display_cmd,
                        cmd_for_display, # Pass args part for display context
                        semiauto, # Pass semiauto flag directly
                        model_name
                    )
                    if confirmation_result is not None:
                        # Check if it's a Success indicating exit, otherwise return the Result
                        if isinstance(confirmation_result, Success) and not confirmation_result.continue_execution:
                            logger.info("Exiting due to user choice in confirmation.")
                            # Ensure we return something indicating non-continuation if needed upstream
                            return confirmation_result # Propagate the Success(continue=False)
                        elif isinstance(confirmation_result, Error):
                             return confirmation_result # Propagate Error
                        # If it's just Success(message=...), it means cancelled, return it
                        elif isinstance(confirmation_result, Success):
                             return confirmation_result

                # <<< Corrected Dispatch Logic: Check live_display *before* verb >>>
                if live_display and kubectl_verb == "wait": # Combine checks
                    logger.info(f"Dispatching 'wait' command to live display handler.")
                    # Pass the full kubectl_args list
                    return handle_wait_with_live_display(
                        resource=kubectl_args[0] if kubectl_args else "", # Best guess for resource
                        args=tuple(kubectl_args[1:]), # Rest are args
                        output_flags=output_flags,
                        summary_prompt_func=summary_prompt_func,
                    )
                elif live_display and kubectl_verb == "port-forward": # Combine checks
                    logger.info(f"Dispatching 'port-forward' command to live display handler.")
                    # Pass the full kubectl_args list
                    return handle_port_forward_with_live_display(
                        resource=kubectl_args[0] if kubectl_args else "", # Best guess for resource
                        args=tuple(kubectl_args[1:]), # Rest are args
                        output_flags=output_flags,
                        summary_prompt_func=summary_prompt_func,
                    )
                # <<< END ADDED SECTION >>>

                # Execute the command using the original verb and the LLM-provided args list
                # If not wait/port-forward or live_display is False, use standard execution
                logger.info(f"Dispatching '{kubectl_verb}' command to standard execution handler.")
                result = _execute_command(kubectl_verb, kubectl_args, None) # Pass original verb and args list

                # Handle output display based on flags, passing the original verb
                return handle_command_output(
                    result,
                    output_flags,
                    summary_prompt_func,
                    command=kubectl_verb, # Pass the original kubectl verb
                )

            case _:
                # Handle unknown action types
                logger.error(f"Internal error: Unknown ActionType: {validated_action_type}")
                return Error(error=f"Internal error: Unknown ActionType received from LLM: {validated_action_type}")

    except Exception as e:
        # Catch potential errors during LLM interaction OR parsing/validation OR dispatch
        logger.error(f"Error during LLM interaction: {e}", exc_info=True)
        error_str = str(e)
        if is_api_error(error_str):
            console_manager.print_error(f"API Error: {error_str}")
            return create_api_error(error_str, exception=e)
        else:
            console_manager.print_error(f"Error executing vibe request: {error_str}")
            return Error(error=error_str, exception=e)


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


def _create_display_command(args: list[str]) -> str:
    """Create a display-friendly command string.

    Args:
        args: List of command arguments

    Returns:
        Display-friendly command string
    """
    # Check if YAML content is likely present in the arguments
    # (e.g., 'apply -f -' followed by a string starting with 'apiVersion:')
    has_yaml = False
    yaml_content = None
    processed_args = []
    skip_next = False
    for i, arg in enumerate(args):
        if skip_next:
            skip_next = False
            continue

        if arg == "-f" and i + 1 < len(args) and args[i+1] == "-":
            if i + 2 < len(args) and args[i+2].strip().startswith(("apiVersion:", "kind:")):
                has_yaml = True
                yaml_content = args[i+2]
                processed_args.extend(["-f", "-"]) # Keep -f -
                skip_next = True # Skip the actual YAML content in the next iteration
                break # Assume YAML is the last part for display purposes
            else:
                processed_args.append(arg) # Keep -f if not followed by -
        else:
            processed_args.append(arg)

    # Reconstruct the command for display
    if has_yaml:
        # For commands with YAML, show a simplified version
        cmd_prefix = ' '.join(processed_args)
        return f"{cmd_prefix} (with YAML content)"
    else:
        # For standard commands, quote arguments with spaces/chars
        display_args = []
        for arg in args:
            if " " in arg or "<" in arg or ">" in arg or "|" in arg:
                display_args.append(f'"{arg}"') # Quote complex args
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


def _execute_command(command: str, args: list[str], yaml_content: str | None) -> Result:
    """Execute the kubectl command by dispatching to the appropriate utility function.

    Args:
        command: The kubectl command verb (e.g., 'get', 'delete')
        args: List of command arguments (e.g., ['pods', '-n', 'default'])
        yaml_content: YAML content if present

    Returns:
        Result with Success containing command output or Error with error information
    """
    try:
        # Prepend the command verb to the arguments list for execution
        # Ensure command is not empty before prepending
        full_args = ([command] + args) if command else args

        if yaml_content:
            # Dispatch to the YAML handling function in k8s_utils
            # Pass the combined args (command + original args)
            return run_kubectl_with_yaml(full_args, yaml_content)
        else:
            # Check if any arguments contain spaces or special characters
            # Note: Check the original args, not the combined full_args
            has_complex_args = any(
                " " in arg or "<" in arg or ">" in arg for arg in args
            )

            if has_complex_args:
                # Dispatch to the complex args handling function in k8s_utils
                # Pass the combined args (command + original args)
                return run_kubectl_with_complex_args(full_args)
            else:
                # Regular command without complex arguments, use standard run_kubectl
                # Pass the combined args (command + original args)
                return run_kubectl(full_args, capture=True)
    except Exception as e:
        logger.error("Error dispatching command execution: %s", e, exc_info=True)
        # Use create_kubectl_error for consistency if possible, otherwise generic Error
        return create_kubectl_error(f"Error executing command: {e}", exception=e)


def configure_output_flags(
    show_raw_output: bool | None = None,
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
