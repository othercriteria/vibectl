"""
Command handler module for vibectl.

Provides reusable patterns for command handling and execution
to reduce duplication across CLI commands.

Note: All exceptions should propagate to the CLI entry point for centralized error
handling. Do not print or log user-facing errors here; use logging for diagnostics only.
"""

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
    run_kubectl_with_yaml,
)
from .live_display import (
    _execute_port_forward_with_live_display,
    _execute_wait_with_live_display,
)
from .live_display_watch import _execute_watch_with_live_display
from .logutil import logger as _logger
from .memory import get_memory, set_memory, update_memory
from .model_adapter import RecoverableApiError, get_model_adapter
from .output_processor import OutputProcessor
from .prompt import (
    memory_fuzzy_update_prompt,
    recovery_prompt,
)
from .schema import ActionType, LLMCommandResponse
from .types import (
    Error,
    Fragment,
    LLMMetrics,
    OutputFlags,
    PromptFragments,
    Result,
    Success,
    SummaryPromptFragmentFunc,
    SystemFragments,
    UserFragments,
)
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
    summary_prompt_func: SummaryPromptFragmentFunc,
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
        # API errors are now handled by the RecoverableApiError exception type
        # if they originate from the model adapter. Other kubectl errors
        # are generally treated as halting.
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
    try:
        return handle_command_output(
            output,
            output_flags,
            summary_prompt_func,
            command=command,
        )
    except Exception as e:
        # If handle_command_output raises an unexpected error, handle it
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


def create_api_error(
    error_message: str,
    exception: Exception | None = None,
    metrics: LLMMetrics | None = None,
) -> Error:
    """
    Create an Error object for API failures, marking them as non-halting for auto loops.

    These are errors like 'overloaded_error' or other API-related issues that shouldn't
    break the auto loop.

    Args:
        error_message: The error message
        exception: Optional exception that caused the error
        metrics: Optional metrics associated with the error

    Returns:
        Error object with halt_auto_loop=False and optional metrics
    """
    return Error(
        error=error_message,
        exception=exception,
        halt_auto_loop=False,
        metrics=metrics,
    )


def handle_command_output(
    output: Result | str,
    output_flags: OutputFlags,
    summary_prompt_func: SummaryPromptFragmentFunc,
    command: str | None = None,
) -> Result:
    """Processes and displays command output based on flags.

    Args:
        output: The command output string or a Result object.
        output_flags: Flags controlling the output format.
        command: The original kubectl command type (e.g., get, describe).

    Returns:
        Result object containing the processed output or original error.
    """
    _check_output_visibility(output_flags)

    original_error_object: Error | None = None
    output_str: str | None = None
    result_metrics: LLMMetrics | None = (
        None  # Metrics from this result (summary/recovery)
    )

    if isinstance(output, Error):
        original_error_object = output
        console_manager.print_error(original_error_object.error)
        output_str = original_error_object.error
        result_metrics = original_error_object.metrics  # Get metrics from Error
    elif isinstance(output, Success):
        output_str = output.data
        result_metrics = output.metrics  # Get metrics from Success
    else:  # Plain string input
        output_str = output

    _display_kubectl_command(output_flags, command)

    if output_str is not None:
        _display_raw_output(output_flags, output_str)

    # --- Vibe Processing --- #
    vibe_result: Result | None = None
    if output_flags.show_vibe:
        if output_str is not None:
            try:
                if original_error_object:
                    # If we started with an error, generate a recovery prompt
                    # recovery_prompt now returns fragments
                    recovery_system_fragments, recovery_user_fragments = (
                        recovery_prompt(
                            failed_command=command or "Unknown Command",
                            error_output=output_str,
                            original_explanation=None,
                            current_memory=get_memory(),
                            # Add config if needed by recovery_prompt
                            config=Config(),
                        )
                    )
                    logger.info(
                        "Generated recovery fragments: "
                        f"System={len(recovery_system_fragments)}, "
                        f"User={len(recovery_user_fragments)}"
                    )

                    # Call LLM adapter directly for recovery, bypassing _get_llm_summary
                    try:
                        model_adapter = get_model_adapter()
                        model = model_adapter.get_model(output_flags.model_name)
                        # Get text and metrics from the recovery call using fragments
                        vibe_output_text, recovery_metrics = (
                            model_adapter.execute_and_log_metrics(
                                model,
                                system_fragments=SystemFragments(
                                    recovery_system_fragments
                                ),
                                user_fragments=UserFragments(recovery_user_fragments),
                            )
                        )
                        suggestions_generated = True
                    except Exception as llm_exc:
                        # Handle LLM execution errors during recovery appropriately
                        logger.error(
                            f"Error getting recovery suggestions from LLM: {llm_exc}",
                            exc_info=True,
                        )
                        # If suggestions fail, we don't mark as recoverable
                        suggestions_generated = False
                        # Store the error message as the text output
                        vibe_output_text = (
                            f"Failed to get recovery suggestions: {llm_exc}"
                        )
                        recovery_metrics = None  # No metrics if call failed
                        # Don't raise here, let the function return the original error

                    logger.info(f"LLM recovery suggestion: {vibe_output_text}")
                    # Display only the text part of the suggestion/error
                    console_manager.print_vibe(vibe_output_text)
                    # Update the original error object with suggestion/failure text
                    # If there was an original error, update its recovery suggestions
                    # The recovery suggestion is plain text, not JSON.
                    original_error_object.recovery_suggestions = vibe_output_text

                    # Attach metrics (if any) from the recovery call
                    original_error_object.metrics = recovery_metrics

                    # If suggestions were generated, mark as non-halting for auto mode
                    if suggestions_generated:
                        logger.info(
                            "Marking error as non-halting due to successful "
                            "recovery suggestion."
                        )
                        original_error_object.halt_auto_loop = False

                    # Update memory with error and recovery suggestion (or
                    # failure message)
                    # Wrap memory update in try-except as it's non-critical path
                    try:
                        memory_update_metrics = update_memory(
                            command=command or "Unknown",
                            command_output=original_error_object.error,
                            vibe_output=vibe_output_text,
                            model_name=output_flags.model_name,
                        )
                        if memory_update_metrics and output_flags.show_vibe:
                            console_manager.print_metrics(
                                latency_ms=memory_update_metrics.latency_ms,
                                tokens_in=memory_update_metrics.token_input,
                                tokens_out=memory_update_metrics.token_output,
                                source="LLM Memory Update (Recovery)",
                                total_duration=memory_update_metrics.total_processing_duration_ms,
                            )

                    except Exception as mem_err:
                        logger.error(
                            f"Failed to update memory during error recovery: {mem_err}"
                        )

                    # The recovery path returns the modified original_error_object
                    # which now contains recovery_metrics in its .metrics field.
                    # We use result_metrics extracted earlier.
                    pass  # No change needed here, metrics handled above
                else:
                    # If we started with success, generate a summary prompt
                    # Call with config
                    cfg = Config()  # Instantiate config
                    # Call WITH config argument as required by the type hint
                    summary_system_fragments, summary_user_fragments = (
                        summary_prompt_func(cfg)
                    )
                    # _process_vibe_output returns Success with summary_metrics
                    vibe_result = _process_vibe_output(
                        output_str,
                        output_flags,
                        summary_system_fragments=summary_system_fragments,
                        summary_user_fragments=summary_user_fragments,
                        command=command,
                        original_error_object=original_error_object,
                    )
                    if isinstance(vibe_result, Success):
                        result_metrics = vibe_result.metrics  # Get metrics from summary
                    elif isinstance(vibe_result, Error):
                        result_metrics = (
                            vibe_result.metrics
                        )  # Get metrics from API error
            except RecoverableApiError as api_err:
                # Catch specific recoverable errors from _get_llm_summary
                logger.warning(
                    f"Recoverable API error during Vibe processing: {api_err}",
                    exc_info=True,
                )
                console_manager.print_error(f"API Error: {api_err}")
                # Create a non-halting error using the more detailed log message
                return create_api_error(
                    f"Recoverable API error during Vibe processing: {api_err}", api_err
                )
            except Exception as e:
                logger.error(f"Error during Vibe processing: {e}", exc_info=True)
                error_str = str(e)
                formatted_error_msg = f"Error getting Vibe summary: {error_str}"
                console_manager.print_error(formatted_error_msg)
                # Create a standard halting error for Vibe summary failures
                # using the formatted message
                vibe_error = Error(error=formatted_error_msg, exception=e)

                if original_error_object:
                    # Combine the original error with the Vibe failure
                    # Use the formatted vibe_error message here too
                    combined_error_msg = (
                        f"Original Error: {original_error_object.error}\n"
                        f"Vibe Failure: {vibe_error.error}"
                    )
                    exc = original_error_object.exception or vibe_error.exception
                    # Return combined error, keeping original exception if possible
                    combined_error = Error(error=combined_error_msg, exception=exc)

                    return combined_error or vibe_error  # Return combined/vibe error
        else:
            # Handle case where output was None but Vibe was requested
            logger.warning("Cannot process Vibe output because input was None.")
            # If we started with an Error object that had no .error string, return that
            if original_error_object:
                original_error_object.error = (
                    original_error_object.error or "Input error was None"
                )
                original_error_object.recovery_suggestions = (
                    "Could not process None error for suggestions."
                )
                return original_error_object
            else:
                return Error(
                    error="Input command output was None, cannot generate Vibe summary."
                )

    if output_flags.show_vibe:
        # Display only the metrics from the current result (summary/recovery)
        current_metrics = result_metrics  # Already extracted from output

        if current_metrics and output_flags.show_metrics:
            console_manager.print_metrics(
                latency_ms=current_metrics.latency_ms,
                tokens_in=current_metrics.token_input,
                tokens_out=current_metrics.token_output,
                source="LLM Output Processing",
                total_duration=current_metrics.total_processing_duration_ms,
            )

    # If vibe processing occurred and resulted in a Success/Error, return that.
    # Otherwise, return the original result (or Success if only raw was shown).
    if vibe_result:
        return vibe_result
    elif original_error_object:
        # Return original error if vibe wasn't shown or only recovery happened
        return original_error_object
    else:
        # Return Success with the original output string if no vibe processing
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
    summary_system_fragments: SystemFragments,
    summary_user_fragments: UserFragments,
    command: str | None = None,
    original_error_object: Error | None = None,
) -> Result:
    """Processes output using Vibe LLM for summary.

    Args:
        output: The raw command output string.
        output_flags: Flags controlling output format.
        summary_system_fragments: System prompt fragments for the summary.
        summary_user_fragments: User prompt fragments for the summary.
        command: The original kubectl command type.
        original_error_object: The original error object if available

    Returns:
        Result object with Vibe summary or an Error.
    """
    # Truncate output if necessary
    processed_output = output_processor.process_auto(output).truncated

    # Get LLM summary
    try:
        # Format the {output} placeholder in user fragments
        formatted_user_fragments: UserFragments = UserFragments([])
        for frag_template in summary_user_fragments:
            try:
                # Ensure formatted string is cast to Fragment
                formatted_user_fragments.append(
                    Fragment(frag_template.format(output=processed_output))
                )
            except KeyError:
                # Keep fragments without the placeholder as they are (already Fragment)
                formatted_user_fragments.append(frag_template)

        # Get response text and metrics using fragments directly
        model_adapter = get_model_adapter()
        model = model_adapter.get_model(output_flags.model_name)
        # Get text and metrics
        vibe_output_text, metrics = model_adapter.execute_and_log_metrics(
            model=model,
            system_fragments=summary_system_fragments,
            user_fragments=UserFragments(formatted_user_fragments),
        )

        # Check if the LLM returned an error string in the text part
        if vibe_output_text.startswith("ERROR:"):
            error_message = vibe_output_text[7:].strip()
            logger.error(f"LLM summary error: {error_message}")
            # Display the full ERROR: text string
            console_manager.print_error(vibe_output_text)
            # Treat LLM-reported errors as potentially recoverable API errors
            # Pass the error message without the ERROR: prefix
            # Attach metrics from the failed call to the Error object
            return create_api_error(error_message, metrics=metrics)

        _display_vibe_output(vibe_output_text)  # Display only the text

        # Update memory only if Vibe summary succeeded
        memory_update_metrics = update_memory(
            command=command or "Unknown",
            command_output=output,  # Store original full output in memory
            vibe_output=vibe_output_text,  # Store summary text
            model_name=output_flags.model_name,
        )
        if memory_update_metrics and output_flags.show_metrics:
            console_manager.print_metrics(
                latency_ms=memory_update_metrics.latency_ms,
                tokens_in=memory_update_metrics.token_input,
                tokens_out=memory_update_metrics.token_output,
                source="LLM Memory Update (Summary)",
                total_duration=memory_update_metrics.total_processing_duration_ms,
            )

        # Return Success with the summary text and its metrics
        return Success(message=vibe_output_text, metrics=metrics)
    except RecoverableApiError as api_err:
        # Catch specific recoverable errors from _get_llm_summary
        logger.warning(
            f"Recoverable API error during Vibe processing: {api_err}", exc_info=True
        )
        console_manager.print_error(f"API Error: {api_err}")
        # Create a non-halting error using the more detailed log message
        return create_api_error(
            f"Recoverable API error during Vibe processing: {api_err}", api_err
        )
    except Exception as e:
        logger.error(f"Error getting Vibe summary: {e}", exc_info=True)
        error_str = str(e)
        formatted_error_msg = f"Error getting Vibe summary: {error_str}"
        console_manager.print_error(formatted_error_msg)
        # Create a standard halting error for Vibe summary failures
        # using the formatted message
        vibe_error = Error(error=formatted_error_msg, exception=e)

        if original_error_object:
            # Combine the original error with the Vibe failure
            # Use the formatted vibe_error message here too
            combined_error_msg = (
                f"Original Error: {original_error_object.error}\n"
                f"Vibe Failure: {vibe_error.error}"
            )
            exc = original_error_object.exception or vibe_error.exception
            # Return combined error, keeping original exception if possible
            return Error(error=combined_error_msg, exception=exc)
        else:
            # If there was no original error, just return the Vibe error
            return vibe_error


def _display_vibe_output(vibe_output: str) -> None:
    """Display the vibe output.

    Args:
        vibe_output: Vibe output to display
    """
    logger.debug("Displaying vibe summary output.")
    console_manager.print_vibe(vibe_output)


async def handle_vibe_request(
    request: str,
    command: str,
    plan_prompt_func: Callable[..., PromptFragments],
    summary_prompt_func: SummaryPromptFragmentFunc,
    output_flags: OutputFlags,
    yes: bool = False,  # Add parameter to control confirmation bypass
    semiauto: bool = False,  # Add parameter for semiauto mode
    live_display: bool = True,  # Add parameter for live display
    autonomous_mode: bool = False,  # Add parameter for autonomous mode
    config: Config | None = None,  # Added config
) -> Result:
    """Handle a request that requires LLM interaction for command planning.

    Args:
        request: The user's natural language request.
        command: The base kubectl command (e.g., 'get', 'describe').
        plan_prompt_func: Function returning system/user fragments for planning.
        summary_prompt_func: Function returning system/user fragments for summary.
        output_flags: Flags controlling output format and verbosity.
        yes: Bypass confirmation prompts.
        semiauto: Enable semi-autonomous mode (confirm once).
        live_display: Show live output for background tasks.
        autonomous_mode: Enable fully autonomous mode (no confirmations).
        config: Optional Config instance.

    Returns:
        Result object with the outcome of the operation.
    """
    cfg = config or Config()
    model_name = output_flags.model_name

    # --- Get Planning Fragments and Prepare Prompt --- #
    # Get fresh memory context
    memory_context_str = get_memory(cfg)

    # Call the provided function to get base system/user fragments
    plan_system_fragments, plan_user_fragments_base = plan_prompt_func()

    # Prepare the final list of user fragments
    # Start with the base fragments from the prompt function
    final_user_fragments = list(
        plan_user_fragments_base
    )  # Use list() to ensure mutable copy

    # Prepend memory context if it exists
    if memory_context_str:
        final_user_fragments.insert(
            0,
            Fragment(f"Memory Context:\n{memory_context_str}"),
        )

    # Append the actual request if provided
    if request:
        final_user_fragments.append(Fragment(request))

    # Get and validate the LLM plan using the fragments
    plan_result = _get_llm_plan(
        model_name,
        plan_system_fragments,  # Pass system fragments
        UserFragments(final_user_fragments),  # Pass final user fragments
        LLMCommandResponse,
    )

    if isinstance(plan_result, Error):
        # Error handling (logging, console printing) is now done within _get_llm_plan
        # or handled by the caller based on halt_auto_loop.
        return plan_result

    # --- Display LLM Planning Metrics --- #
    plan_metrics: LLMMetrics | None = None
    if (
        isinstance(plan_result, Success)
        and plan_result.metrics
        and output_flags.show_metrics
    ):
        plan_metrics = plan_result.metrics
        console_manager.print_metrics(
            source="LLM Planner",
            tokens_in=plan_metrics.token_input,
            tokens_out=plan_metrics.token_output,
            latency_ms=plan_metrics.latency_ms,
            total_duration=plan_metrics.total_processing_duration_ms,
        )
    # --- End Planning Metrics Display --- #

    # Plan succeeded, get the validated response object
    response = plan_result.data
    # Add check to satisfy linter and handle potential (though unlikely) None case
    if response is None:
        logger.error("Internal Error: _get_llm_plan returned Success with None data.")
        return Error("Internal error: Failed to get valid plan data from LLM.")

    # Dispatch based on the validated plan's ActionType
    logger.debug(
        f"Matching action_type: {response.action_type} "
        f"(Type: {type(response.action_type)})"
    )
    logger.info(
        f"[DEBUG] Type of response.action_type IS: {type(response.action_type)}"
    )
    # Replace match with if/elif/else
    action = response.action_type
    if action == ActionType.ERROR.value:
        if not response.error:
            logger.error("ActionType is ERROR but no error message provided.")
            return Error(error="Internal error: LLM sent ERROR action without message.")
        # Handle planning errors (updates memory)
        error_message = response.error
        logger.info(f"LLM returned planning error: {error_message}")
        # Display explanation first if provided
        console_manager.print_note(f"AI Explanation: {response.explanation}")
        update_memory(
            command=command,
            command_output=error_message,  # Store raw error from LLM
            vibe_output=f"LLM Planning Error: {request} -> {error_message}",
            model_name=output_flags.model_name,
        )
        logger.info("Planning error added to memory context")
        console_manager.print_error(f"LLM Planning Error: {error_message}")
        return Error(
            error=f"LLM planning error: {error_message}",
            recovery_suggestions=response.explanation
            or "Check the request or try rephrasing.",
        )

    elif action == ActionType.WAIT.value:
        if response.wait_duration_seconds is None:
            logger.error("ActionType is WAIT but no duration provided.")
            return Error(error="Internal error: LLM sent WAIT action without duration.")
        duration = response.wait_duration_seconds
        logger.info(f"LLM requested WAIT for {duration} seconds.")
        # Display explanation first if provided
        console_manager.print_note(f"AI Explanation: {response.explanation}")
        console_manager.print_processing(
            f"Waiting for {duration} seconds as requested by AI..."
        )
        time.sleep(duration)
        return Success(message=f"Waited for {duration} seconds.")

    elif action == ActionType.FEEDBACK.value:
        logger.info("LLM issued FEEDBACK without command.")
        if response.explanation:
            console_manager.print_note(f"AI Explanation: {response.explanation}")
        else:
            # If no explanation, provide a default message
            console_manager.print_note("Received feedback from AI.")
        return Success(message="Received feedback from AI.")

    elif action == ActionType.COMMAND.value:
        if not response.commands and not response.yaml_manifest:
            logger.error(
                "LLM returned COMMAND action but no commands or YAML provided."
            )
            update_memory(
                command=command or "system",
                command_output="LLM Error: COMMAND action with no args.",
                vibe_output="LLM Error: COMMAND action with no args.",
                model_name=output_flags.model_name,
            )
            return Error(error="Internal error: LLM sent COMMAND action with no args.")

        # Extract verb and args using helper
        raw_llm_commands = response.commands or []
        kubectl_verb, kubectl_args = _extract_verb_args(command, raw_llm_commands)

        # Handle error from extraction helper
        if kubectl_verb is None:
            return Error(error="LLM planning failed: Could not determine command verb.")

        if kubectl_verb == "port-forward" and live_display:
            logger.info("Dispatching 'port-forward' command to live display handler.")
            # Extract resource and args for the live handler
            # kubectl_args includes the resource as the first element
            resource = kubectl_args[0] if kubectl_args else ""
            pf_args = tuple(kubectl_args[1:]) if len(kubectl_args) > 1 else ()

            # Validate resource is present
            if not resource:
                logger.error("Port-forward live display requires a resource name.")
                return Error(error="Missing resource name for port-forward.")

            # Call the live display handler directly
            return await handle_port_forward_with_live_display(
                resource=resource,
                args=pf_args,
                output_flags=output_flags,
                summary_prompt_func=summary_prompt_func,
            )
        else:
            # Confirm and execute the plan using a helper function
            return await _confirm_and_execute_plan(
                kubectl_verb,
                kubectl_args,
                response.yaml_manifest,
                response.explanation,
                command,  # Pass original command verb
                semiauto,
                yes,
                autonomous_mode,
                live_display,
                output_flags,
                summary_prompt_func,
            )

    else:  # Default case (Unknown ActionType)
        logger.error(f"Internal error: Unknown ActionType: {response.action_type}")
        return Error(
            error=f"Internal error: Unknown ActionType received from "
            f"LLM: {response.action_type}"
        )


async def _confirm_and_execute_plan(
    kubectl_verb: str,
    kubectl_args: list[str],
    yaml_content: str | None,
    explanation: str | None,
    original_command_verb: str,  # Add original_command_verb
    semiauto: bool,
    yes: bool,
    autonomous_mode: bool,
    live_display: bool,
    output_flags: OutputFlags,
    summary_prompt_func: SummaryPromptFragmentFunc,
) -> Result:
    """Confirm and execute the kubectl command plan."""
    # Determine if YAML content is present for display formatting
    has_yaml_content = yaml_content is not None and yaml_content.strip() != ""

    # Create the display command using the helper function
    display_cmd = _create_display_command(kubectl_verb, kubectl_args, has_yaml_content)

    needs_conf = _needs_confirmation(
        original_command_verb, semiauto
    )  # Use original_command_verb
    logger.debug(
        f"Confirmation check: command='{display_cmd}', verb='{original_command_verb}', "
        f"semiauto={semiauto}, needs_confirmation={needs_conf}, yes_flag={yes}"
    )

    if needs_conf:
        confirmation_result = _handle_command_confirmation(
            display_cmd=display_cmd,
            semiauto=semiauto,
            model_name=output_flags.model_name,
            explanation=explanation,
            yes=yes,
        )
        if confirmation_result is not None:
            return confirmation_result
    elif yes:
        logger.info(
            f"Proceeding without prompt (confirmation not needed, yes=True) "
            f"for command: {display_cmd}"
        )

    # Display the command being run if show_kubectl is true, before execution
    if output_flags.show_kubectl:
        console_manager.print_processing(f"Running: {display_cmd}")

    # Execute the command
    logger.info(f"'{kubectl_verb}' command dispatched to standard handler.")
    result = _execute_command(kubectl_verb, kubectl_args, yaml_content)

    logger.debug(
        f"Result type={type(result)}, result.data='{getattr(result, 'data', None)}'"
    )

    # Extract output/error for memory update
    if isinstance(result, Success):
        command_output_str = str(result.data) if result.data is not None else ""
    elif isinstance(result, Error):
        command_output_str = str(result.error) if result.error is not None else ""
    else:
        command_output_str = ""

    vibe_output_str = explanation or f"Executed: {display_cmd}"

    # Update memory
    memory_update_metrics: LLMMetrics | None = None
    try:
        memory_update_metrics = update_memory(
            command=display_cmd,
            command_output=command_output_str,
            vibe_output=vibe_output_str,
            model_name=output_flags.model_name,
        )
        logger.info("Memory updated after command execution.")
        # Display main LLM output processing metrics if available and requested
        if memory_update_metrics and output_flags.show_metrics:
            console_manager.print_metrics(
                latency_ms=memory_update_metrics.latency_ms,
                tokens_in=memory_update_metrics.token_input,
                tokens_out=memory_update_metrics.token_output,
                source="LLM Memory Update (Execution Record)",
                total_duration=memory_update_metrics.total_processing_duration_ms,
            )
    except Exception as mem_e:
        logger.error(f"Failed to update memory after command execution: {mem_e}")

    # Handle output display
    try:
        return handle_command_output(
            result,
            output_flags,
            summary_prompt_func,
            command=kubectl_verb,
        )
    except RecoverableApiError as api_err:
        logger.warning(
            f"Recoverable API error during command handling: {api_err}", exc_info=True
        )
        console_manager.print_error(f"API Error: {api_err}")
        return create_api_error(f"API Error: {api_err}", api_err)
    except Exception as e:
        logger.error(f"Error handling command output: {e}", exc_info=True)
        return Error(error=f"Error handling command output: {e}", exception=e)


def _handle_command_confirmation(
    display_cmd: str,
    semiauto: bool,
    model_name: str,
    explanation: str | None = None,
    yes: bool = False,  # Added yes flag
) -> Result | None:
    """Handle command confirmation with enhanced options.

    Args:
        display_cmd: The command string (used for logging/memory).
        semiauto: Whether this is operating in semiauto mode.
        model_name: The model name used.
        explanation: Optional explanation from the AI.
        yes: If True, bypass prompt and default to yes.

    Returns:
        Result if the command was cancelled or memory update failed,
        None if the command should proceed.
    """
    # If yes is True, bypass the prompt and proceed
    if yes:
        logger.info(
            "Confirmation bypassed due to 'yes' flag for command: %s", display_cmd
        )
        return None  # Proceed with command execution

    # Enhanced confirmation dialog with options: yes, no, and, but, memory, [exit]
    options_base = "[Y]es, [N]o, yes [A]nd, no [B]ut, or [M]emory?"
    options_exit = " or [E]xit?"
    prompt_options = f"{options_base}{options_exit if semiauto else ''}"
    choice_list = ["y", "n", "a", "b", "m"] + (["e"] if semiauto else [])
    prompt_suffix = f" ({'/'.join(choice_list)})"

    if explanation:
        console_manager.print_note(f"AI Explanation: {explanation}")

    while True:
        # Use lowercased prompt for consistency
        # Print the prompt using console_manager which handles Rich markup
        # Print the command line first
        prompt_command_line = f"Execute: [bold]{display_cmd}[/bold]?"
        console_manager.print(prompt_command_line, style="info")
        # Print the options on a new line
        prompt_options_line = f"{prompt_options}{prompt_suffix}"
        console_manager.print(prompt_options_line, style="info")

        # Use click.prompt just to get the input character
        choice = click.prompt(
            ">",  # Minimal prompt marker
            type=click.Choice(choice_list, case_sensitive=False),
            default="n",
            show_choices=False,  # Options are printed above
            show_default=False,  # Default not shown explicitly
            prompt_suffix="",  # Avoid adding extra colon
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
            # Re-print options before looping
            console_manager.print(f"\n{prompt_options}{prompt_suffix}", style="info")
            continue

        if choice in ["n", "b"]:
            # No or No But - don't execute the command
            logger.info(
                f"User cancelled execution of planned command: kubectl {display_cmd}"
            )
            console_manager.print_cancelled()

            # If "but" is chosen, do a fuzzy memory update
            if choice == "b":
                memory_result = _handle_fuzzy_memory_update("no but", model_name)
                if isinstance(memory_result, Error):
                    return memory_result  # Propagate memory update error
            return Success(message="Command execution cancelled by user")

        # Handle the Exit option if in semiauto mode
        elif choice == "e" and semiauto:
            logger.info("User chose to exit the semiauto loop")
            console_manager.print_note("Exiting semiauto session")
            # Return a Success with continue_execution=False to signal exit
            return Success(
                message="User requested exit from semiauto loop",
                continue_execution=False,
            )

        elif choice in ["y", "a"]:
            # Yes or Yes And - execute the command
            logger.info("User approved execution of planned command")

            # If "and" is chosen, do a fuzzy memory update *before* proceeding
            if choice == "a":
                memory_result = _handle_fuzzy_memory_update("yes and", model_name)
                if isinstance(memory_result, Error):
                    return memory_result  # Propagate memory update error

            # Proceed with command execution
            return None  # Indicates proceed


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
        current_memory = get_memory(cfg)  # Get current memory

        # Get the model
        model_adapter = get_model_adapter(cfg)  # Pass cfg
        model = model_adapter.get_model(model_name)

        # Create a prompt for the fuzzy memory update
        # Pass current_memory explicitly
        system_fragments, user_fragments = memory_fuzzy_update_prompt(
            current_memory=current_memory,  # Pass fetched memory
            update_text=update_text,
            config=cfg,  # Pass config if needed by the prompt function
        )

        # Get the response
        console_manager.print_processing("Updating memory...")
        # Get text and metrics
        updated_memory_text, metrics = model_adapter.execute_and_log_metrics(
            model,
            system_fragments=system_fragments,
            user_fragments=user_fragments,
        )

        # Set the updated memory
        set_memory(updated_memory_text, cfg)
        console_manager.print_success("Memory updated")

        # Display the updated memory (only text)
        console_manager.safe_print(
            console_manager.console,
            Panel(
                updated_memory_text,  # Display only text
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


def _quote_args(args: list[str]) -> list[str]:
    """Quote arguments containing spaces or special characters."""
    quoted_args = []
    for arg in args:
        if " " in arg or "<" in arg or ">" in arg or "|" in arg:
            quoted_args.append(f'"{arg}"')  # Quote complex args
        else:
            quoted_args.append(arg)
    return quoted_args


def _create_display_command(verb: str, args: list[str], has_yaml: bool) -> str:
    """Create a display-friendly command string.

    Args:
        verb: The kubectl command verb.
        args: List of command arguments.
        has_yaml: Whether YAML content is being provided separately.

    Returns:
        Display-friendly command string.
    """
    # Quote arguments appropriately
    display_args = _quote_args(args)
    base_cmd = f"kubectl {verb} {' '.join(display_args)}"

    if has_yaml:
        return f"{base_cmd} (with YAML content)"
    else:
        return base_cmd


def _needs_confirmation(verb: str, semiauto: bool) -> bool:
    """Check if a command needs confirmation based on its type.

    Args:
        verb: Command verb (e.g., get, delete)
        semiauto: Whether the command is running in semiauto mode
            (always requires confirmation)

    Returns:
        Whether the command needs confirmation
    """
    dangerous_commands = [
        "delete",
        "scale",
        "rollout",
        "patch",
        "apply",
        "replace",
        "create",
    ]
    is_dangerous = verb in dangerous_commands  # Check against the verb
    needs_conf = semiauto or is_dangerous
    logger.debug(
        f"Checking confirmation for verb '{verb}': "
        f"semiauto={semiauto}, is_dangerous={is_dangerous}, "
        f"needs_confirmation={needs_conf}"
    )
    return needs_conf


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
        full_args = [command, *args] if command else args

        if yaml_content:
            # Dispatch to the YAML handling function in k8s_utils
            # Pass the combined args (command + original args)
            # Instantiate Config to pass to run_kubectl_with_yaml
            cfg = Config()
            return run_kubectl_with_yaml(full_args, yaml_content, config=cfg)
        else:
            return run_kubectl(full_args, capture=True)
    except Exception as e:
        logger.error("Error dispatching command execution: %s", e, exc_info=True)
        return create_kubectl_error(f"Error executing command: {e}", exception=e)


def configure_output_flags(
    show_raw_output: bool | None = None,
    vibe: bool | None = None,
    show_vibe: bool | None = None,
    model: str | None = None,
    show_kubectl: bool | None = None,
    show_metrics: bool | None = None,
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
        show_metrics: Optional override for showing metrics

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

    # Get show_metrics setting - default to True
    show_metrics_output = (
        show_metrics
        if show_metrics is not None
        else config.get("show_metrics", DEFAULT_CONFIG["show_metrics"])
    )

    return OutputFlags(
        show_raw=show_raw,
        show_vibe=show_vibe_output,
        warn_no_output=warn_no_output,
        model_name=model_name,
        show_kubectl=show_kubectl_commands,
        warn_no_proxy=warn_no_proxy,
        show_metrics=show_metrics_output,
    )


# Wrapper for wait command live display
async def handle_wait_with_live_display(
    resource: str,
    args: tuple[str, ...],
    output_flags: OutputFlags,
    summary_prompt_func: SummaryPromptFragmentFunc,
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
    wait_result = await _execute_wait_with_live_display(
        resource=resource,
        args=args,
        output_flags=output_flags,
        condition=condition,
        display_text=display_text,
        summary_prompt_func=summary_prompt_func,
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
async def handle_port_forward_with_live_display(
    resource: str,
    args: tuple[str, ...],
    output_flags: OutputFlags,
    summary_prompt_func: SummaryPromptFragmentFunc,
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
    pf_result = await _execute_port_forward_with_live_display(
        resource=resource,
        args=args,
        output_flags=output_flags,
        port_mapping=port_mapping,
        local_port=local_port,
        remote_port=remote_port,
        display_text=display_text,
        summary_prompt_func=summary_prompt_func,
    )

    command_str = f"port-forward {resource} {' '.join(args)}"
    return handle_command_output(
        output=pf_result,
        output_flags=output_flags,
        summary_prompt_func=summary_prompt_func,
        command=command_str,
    )


# Wrapper for watch command live display
async def handle_watch_with_live_display(
    command: str,  # e.g., 'get'
    resource: str,
    args: tuple[str, ...],
    output_flags: OutputFlags,
    summary_prompt_func: SummaryPromptFragmentFunc,
) -> Result:
    """Handles commands with `--watch` by invoking the live display worker.

    Args:
        command: The kubectl command verb (e.g., 'get', 'describe').
        resource: The resource type (e.g., pod, deployment).
        args: Command arguments including resource name and conditions.
        output_flags: Flags controlling output format.

    Returns:
        Result from the live display worker function.
    """
    logger.info(
        f"Handling '{command} {resource} --watch' with live display. Args: {args}"
    )

    # Create the command description for the display
    display_args = [arg for arg in args if arg not in ("--watch", "-w")]
    cmd_for_display = _create_display_command(command, display_args, False)
    console_manager.print_processing(f"Watching {cmd_for_display}...")

    # Call the worker function in live_display_watch.py (corrected module name)
    watch_result = await _execute_watch_with_live_display(
        command=command,
        resource=resource,
        args=args,
        output_flags=output_flags,
        summary_prompt_func=summary_prompt_func,
    )

    # Process the result from the worker using handle_command_output
    # Create the command string for context
    command_str = f"{command} {resource} {' '.join(args)}"
    return handle_command_output(
        output=watch_result,  # Pass the Result object directly
        output_flags=output_flags,
        summary_prompt_func=summary_prompt_func,
        command=command_str,
    )


# Helper function for Vibe planning
def _get_llm_plan(
    model_name: str,
    plan_system_fragments: SystemFragments,
    plan_user_fragments: UserFragments,
    response_model_type: type[LLMCommandResponse],
) -> Result:
    """Calls the LLM to get a command plan and validates the response."""
    model_adapter = get_model_adapter()

    try:
        model = model_adapter.get_model(model_name)
    except Exception as e:
        error_msg = f"Failed to get model '{model_name}': {e}"
        logger.error(error_msg, exc_info=True)
        error_memory_metrics = update_memory(
            command="system",
            command_output=error_msg,
            vibe_output=f"System Error: Failed to get model '{model_name}'.",
            model_name=model_name,
        )
        # Use create_api_error to allow potential recovery if config changes
        return create_api_error(error_msg, e, error_memory_metrics)

    console_manager.print_processing(f"Consulting {model_name} for a plan...")
    logger.debug(
        f"Final planning prompt:\\n{plan_system_fragments} {plan_user_fragments}"
    )

    try:
        # Get response text and metrics using fragments
        llm_response_text, metrics = model_adapter.execute_and_log_metrics(
            model=model,
            system_fragments=plan_system_fragments,
            user_fragments=plan_user_fragments,
            response_model=response_model_type,
        )
        logger.info(f"Raw LLM response text:\n{llm_response_text}")

        if not llm_response_text or llm_response_text.strip() == "":
            logger.error("LLM returned an empty response.")
            update_memory(
                command="system",
                command_output="LLM Error: Empty response.",
                vibe_output="LLM Error: Empty response.",
                model_name=model_name,
            )
            return Error("LLM returned an empty response.")

        response = LLMCommandResponse.model_validate_json(llm_response_text)
        logger.debug(f"Parsed LLM response object: {response}")
        logger.info(f"Validated ActionType: {response.action_type}")
        # Attach metrics to the Success result
        return Success(data=response, metrics=metrics)

    except (JSONDecodeError, ValidationError) as e:
        logger.warning(
            f"Failed to parse LLM response as JSON ({type(e).__name__}). "
            f"Response Text: {llm_response_text[:500]}..."
        )
        error_msg = f"Failed to parse LLM response as expected JSON: {e}"
        truncated_llm_response = output_processor.process_auto(
            llm_response_text, budget=100
        ).truncated
        memory_update_metrics = update_memory(  # Capture metrics
            command="system",
            command_output=error_msg,
            vibe_output=(
                f"System Error: Failed to parse LLM response: "
                f"{truncated_llm_response}... Check model or prompt."
            ),
            model_name=model_name,
        )
        return create_api_error(error_msg, e, metrics=memory_update_metrics)
    except (
        RecoverableApiError
    ) as api_err:  # Catch recoverable API errors during execute
        logger.warning(
            f"Recoverable API error during Vibe planning: {api_err}", exc_info=True
        )
        # Print API error before returning
        console_manager.print_error(f"API Error: {api_err}")
        return create_api_error(str(api_err), exception=api_err)
    except Exception as e:  # Catch other errors during execute
        logger.error(f"Error during LLM planning interaction: {e}", exc_info=True)
        error_str = str(e)
        # Print generic error before returning
        console_manager.print_error(f"Error executing vibe request: {error_str}")
        return Error(error=error_str, exception=e)


def _extract_verb_args(
    original_command: str, raw_llm_commands: list[str]
) -> tuple[str | None, list[str]]:
    """
    Determines the kubectl verb and arguments from the LLM's raw command list.
    Assumes the LLM ALWAYS provides the verb as the first element.
    """
    if not raw_llm_commands:
        logger.error("LLM failed to provide any command parts.")
        return None, []

    if original_command == "vibe":
        kubectl_verb = raw_llm_commands[0]
        kubectl_args = raw_llm_commands[1:]
    else:
        kubectl_verb = original_command
        kubectl_args = raw_llm_commands

    # Check for heredoc separator '---' and adjust args
    # The YAML content itself comes from response.yaml_manifest
    if "---" in kubectl_args:
        try:
            separator_index = kubectl_args.index("---")
            kubectl_args = kubectl_args[:separator_index]
            logger.debug(f"Adjusted kubectl_args for heredoc: {kubectl_args}")
        except ValueError:
            # Should not happen if '---' is in the list, but handle defensively
            logger.warning("'---' detected but index not found in kubectl_args.")

    # Safety check: Ensure determined verb is not empty
    if not kubectl_verb:
        logger.error("Internal error: LLM provided an empty verb.")
        return None, []  # Indicate error

    return kubectl_verb, kubectl_args
