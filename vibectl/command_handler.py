"""
Command handler module for vibectl.

Provides reusable patterns for command handling and execution
to reduce duplication across CLI commands.

Note: All exceptions should propagate to the CLI entry point for centralized error
handling. Do not print or log user-facing errors here; use logging for diagnostics only.
"""

from json import JSONDecodeError

from pydantic import ValidationError
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
from .memory import get_memory, update_memory
from .model_adapter import RecoverableApiError, get_model_adapter
from .output_processor import OutputProcessor
from .prompt import (
    recovery_prompt,
)
from .schema import (
    FeedbackAction,
    LLMPlannerResponse,
)
from .types import (
    Error,
    Fragment,
    LLMMetrics,
    OutputFlags,
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
output_processor = OutputProcessor(max_chars=5000, llm_max_chars=5000)


async def handle_standard_command(
    command: str,
    resource: str,
    args: tuple,
    output_flags: OutputFlags,
    summary_prompt_func: SummaryPromptFragmentFunc,
    allowed_exit_codes: tuple[int, ...] = (0,),
) -> Result:
    """Handle standard kubectl commands (get, describe, etc.)."""
    result = _run_standard_kubectl_command(
        command,
        resource,
        args,
        allowed_exit_codes=allowed_exit_codes,
    )

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
            return result

    try:
        return await handle_command_output(
            result,
            output_flags,
            summary_prompt_func,
            command=command,
        )
    except Exception as e:
        # If handle_command_output raises an unexpected error, handle it
        return _handle_standard_command_error(command, resource, args, e)


def _run_standard_kubectl_command(
    command: str,
    resource: str,
    args: tuple,
    allowed_exit_codes: tuple[int, ...] = (0,),
) -> Result:
    """Run a standard kubectl command and handle basic error cases.

    Args:
        command: The kubectl command to run
        resource: The resource to act on
        args: Additional command arguments

    Returns:
        Result with Success or Error information
    """
    # Build command list
    cmd_args = [command]
    if resource:  # Only add resource if it's not empty
        cmd_args.append(resource)
    if args:
        cmd_args.extend(args)

    # Run kubectl and get result
    kubectl_result = run_kubectl(cmd_args, allowed_exit_codes=allowed_exit_codes)

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


async def handle_command_output(
    output: Result,
    output_flags: OutputFlags,
    summary_prompt_func: SummaryPromptFragmentFunc,
    command: str | None = None,
) -> Result:
    """Handle the output of a kubectl command.

    Processes and displays raw output, vibe output, or summaries based on flags.

    Args:
        output: The command output Result object.
        output_flags: Flags controlling the output format.
        command: The original kubectl command type (e.g., get, describe).

    Returns:
        Result object containing the processed output or original error.
    """
    _check_output_visibility(output_flags)

    output_data: str | None = None  # Initialize output_data here
    output_message: str = ""  # Initialize output_message here
    original_error_object: Error | None = None
    result_metrics: LLMMetrics | None = (
        None  # Metrics from this result (summary/recovery)
    )
    result_original_exit_code: int | None = None

    if isinstance(output, Error):
        original_error_object = output
        console_manager.print_error(original_error_object.error)
        output_data = original_error_object.error  # error is a string
        result_metrics = original_error_object.metrics  # Get metrics from Error
    elif isinstance(output, Success):
        output_message = (
            output.message or ""
        )  # output_message seems unused before vibe processing
        output_data = output.data or ""  # data is a string or empty string
        result_metrics = output.metrics
        result_original_exit_code = output.original_exit_code

    _display_kubectl_command(output_flags, command)

    # This check should now always have output_data defined if logic above is correct
    if output_data is not None:
        _display_raw_output(output_flags, output_data)
    else:
        # This case should ideally not be reached if the above logic is exhaustive
        # for setting output_data. Log a warning if it is.
        logger.warning(
            "output_data was None before vibe processing, which is unexpected."
        )
        # If output_data is None here, and show_vibe is false, we
        # might return None implicitly later if not careful.
        # Ensure we return the original_error_object if it exists from the 'else' block.

    vibe_result: Result | None = None
    if output_flags.show_vibe:
        if output_data is not None:
            try:
                if original_error_object:
                    # If we started with an error, generate a recovery prompt
                    # recovery_prompt now returns fragments
                    recovery_system_fragments, recovery_user_fragments = (
                        recovery_prompt(
                            failed_command=command or "Unknown Command",
                            error_output=output_data,
                            original_explanation=None,
                            current_memory=get_memory(),
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
                        (
                            vibe_output_text,
                            recovery_metrics,
                        ) = await model_adapter.execute_and_log_metrics(
                            model,
                            system_fragments=SystemFragments(recovery_system_fragments),
                            user_fragments=UserFragments(recovery_user_fragments),
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
                    if original_error_object:
                        logger.info(f"LLM recovery suggestion: {vibe_output_text}")
                        # Try to parse the recovery suggestion as LLMPlannerResponse
                        try:
                            parsed_recovery_response = (
                                LLMPlannerResponse.model_validate_json(vibe_output_text)
                            )
                            if (
                                isinstance(
                                    parsed_recovery_response.action, FeedbackAction
                                )
                                and parsed_recovery_response.action.message
                            ):
                                original_error_object.recovery_suggestions = (
                                    parsed_recovery_response.action.message
                                )
                            else:
                                # If not FeedbackAction or no message, use raw
                                # response as fallback
                                original_error_object.recovery_suggestions = (
                                    vibe_output_text
                                )
                        except (JSONDecodeError, ValidationError):
                            # If parsing fails, use raw response
                            logger.warning(
                                "Could not parse recovery suggestion as "
                                f"LLMPlannerResponse: {vibe_output_text}"
                            )
                            original_error_object.recovery_suggestions = (
                                vibe_output_text
                            )

                        original_error_object.metrics = (
                            recovery_metrics  # Add metrics from recovery
                        )

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
                        memory_update_metrics_error = await update_memory(
                            command_message=output_message or command or "Unknown",
                            command_output=output_data,
                            vibe_output=vibe_output_text,
                            model_name=output_flags.model_name,
                            config=Config(),
                        )
                        if memory_update_metrics_error and output_flags.show_vibe:
                            console_manager.print_metrics(
                                latency_ms=memory_update_metrics_error.latency_ms,
                                tokens_in=memory_update_metrics_error.token_input,
                                tokens_out=memory_update_metrics_error.token_output,
                                source="LLM Memory Update (Recovery)",
                                total_duration=memory_update_metrics_error.total_processing_duration_ms,
                            )

                    except Exception as mem_err:
                        logger.error(
                            f"Failed to update memory during error recovery: {mem_err}"
                        )

                    # The recovery path returns the modified original_error_object
                    # which now contains recovery_metrics in its .metrics field.
                    # We use result_metrics extracted earlier.
                    vibe_result = original_error_object
                    # If recovery was attempted and vibe_result is set, return it.
                    return vibe_result
                else:
                    # If we started with success, generate a summary prompt
                    # Call with config
                    cfg = Config()  # Instantiate config
                    current_memory_text = get_memory(cfg)  # Fetch memory here
                    # Call WITH config argument as required by the type hint
                    summary_system_fragments, summary_user_fragments = (
                        summary_prompt_func(
                            cfg,  # Pass config as positional
                            current_memory_text,  # Pass current_memory as positional
                        )
                    )
                    # _process_vibe_output returns Success with summary_metrics
                    # _process_vibe_output is now async
                    vibe_result = await _process_vibe_output(
                        output_message=output_message,
                        output_data=output_data,
                        output_flags=output_flags,
                        summary_system_fragments=summary_system_fragments,
                        summary_user_fragments=summary_user_fragments,
                        command=command,
                        original_error_object=original_error_object,
                    )
                    if isinstance(vibe_result, Success):
                        result_metrics = vibe_result.metrics  # Get metrics from summary
                        vibe_result.original_exit_code = result_original_exit_code
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
                    return combined_error
                else:
                    # If there was no original error, just return the Vibe error
                    return vibe_error
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
        logger.debug(
            f"Vibe output processing complete. Result type: {type(vibe_result)}"
        )
        return vibe_result
    elif original_error_object:
        # Return original error if vibe wasn't shown or only recovery happened
        return original_error_object
    else:
        # Return Success with the original output string if no vibe processing
        return Success(
            message=output_data if output_data is not None else "",
            original_exit_code=result_original_exit_code,
        )


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


async def _process_vibe_output(
    output_message: str,
    output_data: str,
    output_flags: OutputFlags,
    summary_system_fragments: SystemFragments,
    summary_user_fragments: UserFragments,
    command: str | None = None,
    original_error_object: Error | None = None,
) -> Result:
    """Helper to process Vibe output, potentially stream, and update memory."""
    # Truncate output if necessary
    processed_output = output_processor.process_auto(output_data).truncated

    try:
        formatted_user_fragments: UserFragments = UserFragments([])
        for frag_template in summary_user_fragments:
            try:
                formatted_user_fragments.append(
                    Fragment(frag_template.format(output=processed_output))
                )
            except KeyError:
                formatted_user_fragments.append(frag_template)

        model_adapter = get_model_adapter()
        model = model_adapter.get_model(output_flags.model_name)

        should_stream_live = (
            not original_error_object
            and output_flags.show_vibe
            and output_flags.show_streaming  # User wants to see live streaming
        )

        vibe_output_text = ""
        metrics: LLMMetrics | None = None

        if should_stream_live:
            logger.info("Streaming Vibe output live...")
            console_manager.start_live_vibe_panel()
            full_vibe_response_text = ""
            try:
                async for chunk in model_adapter.stream_execute(
                    model=model,
                    system_fragments=summary_system_fragments,
                    user_fragments=UserFragments(formatted_user_fragments),
                ):
                    console_manager.update_live_vibe_panel(chunk)
                    full_vibe_response_text += chunk
                vibe_output_text = full_vibe_response_text
                # Metrics are typically not available or hard to get accurately
                # for pure streaming
            finally:
                # stop_live_vibe_panel will display the final accumulated content
                # in the panel
                console_manager.stop_live_vibe_panel()
            # vibe_output_text is already set, metrics is None for streaming path
            # Explicitly print the final panel if streaming occurred and Vibe should
            # be shown
            if output_flags.show_vibe:
                console_manager.print_vibe(vibe_output_text, use_panel=True)

        elif (
            not original_error_object and output_flags.show_vibe
        ):  # Not live streaming, but show_vibe is true
            logger.info(
                "Fetching Vibe output (non-streaming or streaming suppressed)..."
            )
            # This path is taken if show_streaming is False OR if it's an
            # error recovery.
            # For error recovery (original_error_object is not None), we always
            # fetch non-streamed.
            vibe_output_text, metrics = await model_adapter.execute_and_log_metrics(
                model=model,
                system_fragments=summary_system_fragments,
                user_fragments=UserFragments(formatted_user_fragments),
            )
            # Display the fetched output. If show_streaming was false, print
            # without panel.
            # If it was an error recovery, print with panel.
            use_panel_for_final_display = True  # Default to panel for recovery
            if (
                not original_error_object and not output_flags.show_streaming
            ):  # Normal summary, streaming off
                use_panel_for_final_display = False

            if vibe_output_text.startswith("ERROR:"):
                error_message = vibe_output_text[7:].strip()
                logger.error(f"LLM summary error: {error_message}")
                console_manager.print_error(vibe_output_text)  # Show raw error
            elif vibe_output_text and vibe_output_text.strip():
                console_manager.print_vibe(
                    vibe_output_text, use_panel=use_panel_for_final_display
                )
            else:
                logger.debug("Vibe output is empty, not displaying.")

        # --- Post-fetching/streaming Vibe output processing ---

        if original_error_object:  # This means we were in recovery mode
            # The vibe_output_text here is the recovery suggestion from
            # non-streaming path
            logger.info(f"LLM recovery suggestion: {vibe_output_text}")
            parsed_suggestion = vibe_output_text
            try:
                parsed_recovery_response = LLMPlannerResponse.model_validate_json(
                    vibe_output_text
                )
                if (
                    isinstance(parsed_recovery_response.action, FeedbackAction)
                    and parsed_recovery_response.action.message is not None
                ):
                    parsed_suggestion = parsed_recovery_response.action.message
            except (JSONDecodeError, ValidationError) as parse_error:
                logger.warning(
                    f"Could not parse recovery suggestion '{vibe_output_text}' "
                    f"as LLMPlannerResponse: {parse_error}"
                )
            original_error_object.recovery_suggestions = parsed_suggestion
            original_error_object.metrics = (
                metrics  # Metrics from non-streaming recovery call
            )
            logger.info(
                "Marking error as non-halting due to successful recovery suggestion."
            )
            original_error_object.halt_auto_loop = False
            return original_error_object

        # If not original_error_object, it was a normal summary attempt
        if vibe_output_text.startswith("ERROR:"):
            error_message = vibe_output_text[7:].strip()
            # console_manager.print_error(vibe_output_text) already done if
            # not should_stream_live
            # If it was streamed live, the error would be part of the stream.
            # For non-streamed that resulted in error, it was printed above.
            # What's important is to return an Error object.

            memory_update_metrics_err = await update_memory(
                command_message=command
                if command
                else (output_message or "Unknown"),  # Prioritize command
                command_output=output_data,
                vibe_output=vibe_output_text,  # The error message from LLM
                model_name=output_flags.model_name,
                config=Config(),
            )
            if memory_update_metrics_err and output_flags.show_metrics:
                console_manager.print_metrics(
                    latency_ms=memory_update_metrics_err.latency_ms,
                    tokens_in=memory_update_metrics_err.token_input,
                    tokens_out=memory_update_metrics_err.token_output,
                    source="LLM Memory Update (Summary Error)",
                    total_duration=memory_update_metrics_err.total_processing_duration_ms,
                )
            return create_api_error(error_message, metrics=metrics)

        # If we reached here, Vibe summary was successful (not an "ERROR:" string)
        # and not an original_error_object path.
        # The display was handled either by stop_live_vibe_panel() or by the
        # console_manager.print_vibe(..., use_panel=...) call.

        memory_update_metrics_ok = await update_memory(
            command_message=command
            if command
            else (output_message or "Unknown"),  # Prioritize command
            command_output=output_data,
            vibe_output=vibe_output_text,  # Successful Vibe summary
            model_name=output_flags.model_name,
            config=Config(),
        )
        if memory_update_metrics_ok and output_flags.show_metrics:
            console_manager.print_metrics(
                latency_ms=memory_update_metrics_ok.latency_ms,
                tokens_in=memory_update_metrics_ok.token_input,
                tokens_out=memory_update_metrics_ok.token_output,
                source="LLM Memory Update (Summary)",
                total_duration=memory_update_metrics_ok.total_processing_duration_ms,
            )
        return Success(message=vibe_output_text, metrics=metrics)

    except RecoverableApiError as api_err:
        logger.warning(
            f"Recoverable API error during Vibe processing: {api_err}", exc_info=True
        )
        console_manager.print_error(f"API Error: {api_err}")
        return create_api_error(
            f"Recoverable API error during Vibe processing: {api_err}", api_err
        )
    except Exception as e:
        logger.error(f"Error getting Vibe summary: {e}", exc_info=True)
        error_str = str(e)
        formatted_error_msg = f"Error getting Vibe summary: {error_str}"
        console_manager.print_error(formatted_error_msg)
        vibe_error = Error(error=formatted_error_msg, exception=e)
        if original_error_object:
            combined_error_msg = (
                f"Original Error: {original_error_object.error}\\n"
                f"Vibe Failure: {vibe_error.error}"
            )
            exc = original_error_object.exception or vibe_error.exception
            return Error(error=combined_error_msg, exception=exc)
        return vibe_error


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


def _execute_command(
    command: str,
    args: list[str],
    yaml_content: str | None,
    allowed_exit_codes: tuple[int, ...],
) -> Result:
    """Execute the kubectl command by dispatching to the appropriate utility function.

    Args:
        command: The kubectl command verb (e.g., 'get', 'delete')
        args: List of command arguments (e.g., ['pods', '-n', 'default'])
        yaml_content: YAML content if present
        allowed_exit_codes: Tuple of exit codes that should be treated as success
    Returns:
        Result with Success containing command output or Error with error information
    """
    try:
        # Prepend the command verb to the arguments list for execution
        full_args = [command, *args] if command else args

        if yaml_content:
            cfg = Config()
            return run_kubectl_with_yaml(
                full_args,
                yaml_content,
                allowed_exit_codes=allowed_exit_codes,
                config=cfg,
            )
        else:
            return run_kubectl(full_args, allowed_exit_codes=allowed_exit_codes)
    except Exception as e:
        logger.error("Error dispatching command execution: %s", e, exc_info=True)
        return create_kubectl_error(f"Error executing command: {e}", exception=e)


def configure_output_flags(
    show_raw_output: bool | None = None,
    show_vibe: bool | None = None,
    model: str | None = None,
    show_kubectl: bool | None = None,
    show_metrics: bool | None = None,
    show_streaming: bool | None = None,
) -> OutputFlags:
    """Configure output flags based on config."""
    config = Config()

    show_raw_output_flag = (
        show_raw_output
        if show_raw_output is not None
        else config.get("show_raw_output", DEFAULT_CONFIG["show_raw_output"])
    )

    show_vibe_flag = (
        show_vibe
        if show_vibe is not None
        else config.get("show_vibe", DEFAULT_CONFIG["show_vibe"])
    )

    warn_no_output_flag = config.get("warn_no_output", DEFAULT_CONFIG["warn_no_output"])

    warn_no_proxy_flag = config.get("warn_no_proxy", True)

    model_name = model if model else config.get("model", DEFAULT_CONFIG["model"])

    show_kubectl_flag = (
        show_kubectl
        if show_kubectl is not None
        else config.get("show_kubectl", DEFAULT_CONFIG["show_kubectl"])
    )

    show_metrics_flag = (
        show_metrics
        if show_metrics is not None
        else config.get("show_metrics", DEFAULT_CONFIG["show_metrics"])
    )

    show_streaming_flag = (
        show_streaming
        if show_streaming is not None
        else config.get("show_streaming", DEFAULT_CONFIG["show_streaming"])
    )

    return OutputFlags(
        show_raw=show_raw_output_flag,
        show_vibe=show_vibe_flag,
        warn_no_output=warn_no_output_flag,
        model_name=model_name,
        show_metrics=show_metrics_flag,
        show_kubectl=show_kubectl_flag,
        warn_no_proxy=warn_no_proxy_flag,
        show_streaming=show_streaming_flag,
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
    return await handle_command_output(
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
    allowed_exit_codes: tuple[int, ...] = (0,),
) -> Result:
    """Handles `kubectl port-forward` by preparing args and invoking live display.

    Args:
        resource: The resource type (e.g., pod, service).
        args: Command arguments including resource name and port mappings.
        output_flags: Flags controlling output format.
        allowed_exit_codes: Tuple of exit codes that should be treated as success
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
        allowed_exit_codes=allowed_exit_codes,
    )

    command_str = f"port-forward {resource} {' '.join(args)}"
    return await handle_command_output(
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
    return await handle_command_output(
        output=watch_result,  # Pass the Result object directly
        output_flags=output_flags,
        summary_prompt_func=summary_prompt_func,
        command=command_str,
    )
