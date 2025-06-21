"""
Execution module for Vibe-specific LLM planning and command handling.
"""

import asyncio
from collections.abc import Callable
from json import JSONDecodeError

import click
from pydantic import ValidationError
from rich.panel import Panel

from vibectl.command_handler import (
    _create_display_command,
    _execute_command,
    # We need create_api_error if it was used by moved functions directly
    # but it seems it was used by handle_command_output or others not moving.
    handle_command_output,
    handle_port_forward_with_live_display,
)
from vibectl.config import Config

# Import console utility functions for metrics display
from vibectl.k8s_utils import is_kubectl_command_read_only
from vibectl.llm_utils import run_llm
from vibectl.logutil import logger as _logger
from vibectl.memory import (
    get_memory,
    set_memory,
    update_memory,
)
from vibectl.model_adapter import (
    RecoverableApiError,
)
from vibectl.output_processor import OutputProcessor
from vibectl.prompts.memory import memory_fuzzy_update_prompt
from vibectl.schema import (
    ActionType,
    LLMPlannerResponse,
)
from vibectl.security.response_validation import ValidationOutcome, validate_action
from vibectl.types import (
    Error,
    ExecutionMode,
    Fragment,
    LLMMetricsAccumulator,
    OutputFlags,
    PredicateCheckExitCode,
    PromptFragments,
    Result,
    Success,
    SummaryPromptFragmentFunc,
    SystemFragments,
    UserFragments,
    determine_execution_mode,
)
from vibectl.utils import console_manager

logger = _logger
output_processor = OutputProcessor(max_chars=2000, llm_max_chars=2000)


async def handle_vibe_request(
    request: str,
    command: str,
    plan_prompt_func: Callable[..., PromptFragments],
    summary_prompt_func: SummaryPromptFragmentFunc,
    output_flags: OutputFlags,
    *,
    # semiauto flag indicates confirmation-once loop
    semiauto: bool = False,
    live_display: bool = True,
    execution_mode: ExecutionMode | None = None,
    config: Config | None = None,
) -> Result:
    """Handle a request that requires LLM interaction for command planning."""
    cfg = config or Config()
    model_name = output_flags.model_name

    # Create metrics accumulator for this request
    llm_metrics_accumulator = LLMMetricsAccumulator(output_flags)

    memory_context_str = get_memory(cfg)

    exec_mode: ExecutionMode = (
        execution_mode
        if execution_mode is not None
        else determine_execution_mode(semiauto=semiauto)
    )

    plan_system_fragments, plan_user_fragments_base = plan_prompt_func()

    final_user_fragments = list(plan_user_fragments_base)
    final_user_fragments.insert(0, Fragment(f"Memory Context:\n{memory_context_str}"))
    final_user_fragments.append(Fragment(request))

    # Get and validate the LLM plan using the fragments
    plan_result = await _get_llm_plan(
        model_name,
        plan_system_fragments,
        UserFragments(final_user_fragments),
        LLMPlannerResponse,
        config=cfg,
    )

    if isinstance(plan_result, Error):
        return plan_result

    # Accumulate planning metrics
    llm_metrics_accumulator.add_metrics(plan_result.metrics, "LLM Vibe Planning")

    llm_planner_response = plan_result.data

    if (
        llm_planner_response is None
        or not hasattr(llm_planner_response, "action")
        or llm_planner_response.action is None
    ):
        logger.error(
            "Internal Error: _get_llm_plan returned Success "
            "but response or action is None."
        )
        return Error("Internal error: Failed to get a valid action from LLM.")

    response_action = llm_planner_response.action

    logger.debug(
        f"Matching action_type: {response_action.action_type} "
        f"(Type: {type(response_action.action_type)})"
    )

    validation_result = validate_action(response_action, exec_mode)

    if validation_result.outcome is ValidationOutcome.REJECT:
        logger.warning(
            "Response action rejected by validator: %s", validation_result.message
        )
        return Error(
            error=f"Action rejected by safety validator: {validation_result.message}",
            recovery_suggestions="Revise request or run in manual mode for details.",
        )

    # Force confirmation by downgrading execution mode when validator requests it.
    if validation_result.outcome is ValidationOutcome.CONFIRM and exec_mode in (
        ExecutionMode.AUTO,
        ExecutionMode.SEMIAUTO,
    ):
        logger.debug(
            "Validator requires confirmation - overriding execution_mode %s -> MANUAL",
            exec_mode,
        )
        exec_mode = ExecutionMode.MANUAL

    action = response_action.action_type
    if action == ActionType.ERROR:
        error_message = response_action.message
        logger.info(f"LLM returned planning error: {error_message}")

        memory_update_metrics = await update_memory(
            command_message=f"command: {command} request: {request}",
            command_output=error_message,
            vibe_output="",
            model_name=output_flags.model_name,
        )
        llm_metrics_accumulator.add_metrics(
            memory_update_metrics, "LLM Memory Update (Error)"
        )

        logger.info("Planning error added to memory context")
        console_manager.print_error(f"LLM Planning Error: {error_message}")

        # Display total metrics and return
        llm_metrics_accumulator.print_total_if_enabled("Total LLM Vibe Processing")

        return Error(
            error=f"LLM planning error: {error_message}",
            recovery_suggestions=error_message,
            metrics=llm_metrics_accumulator.get_metrics(),
        )

    elif action == ActionType.DONE:
        # TODO: Handle DONE action for commands other than 'check' or remove from
        # schema so that it's not returned.

        # DONE action received for a command other than 'check', or wrong type
        logger.warning(
            f"Received DONE action for command '{command}' or mismatched type. "
            "This is currently unhandled."
        )
        # For now, treat as an error or unexpected situation
        return Error(
            error=f"Unexpected DONE action for command '{command}'.",
            original_exit_code=PredicateCheckExitCode.CANNOT_DETERMINE.value,
        )

    elif action == ActionType.WAIT:
        duration = response_action.duration_seconds
        logger.info(f"LLM requested WAIT for {duration} seconds.")

        memory_update_metrics = await update_memory(
            command_message=f"command: {command} request: {request}",
            command_output=f"AI requested wait for {duration}s.",
            vibe_output="",
            model_name=output_flags.model_name,
        )
        llm_metrics_accumulator.add_metrics(
            memory_update_metrics, "LLM Memory Update (Wait)"
        )

        console_manager.print_processing(
            f"Waiting for {duration} seconds as requested by AI..."
        )
        await asyncio.sleep(duration)
        console_manager.print_note(f"Waited for {duration} seconds.")

        # Display total metrics and return
        llm_metrics_accumulator.print_total_if_enabled("Total LLM Vibe Processing")

        return Success(
            message=f"Waited for {duration} seconds.",
            metrics=llm_metrics_accumulator.get_metrics(),
        )

    elif action == ActionType.THOUGHT:
        thought_text = response_action.text
        logger.info(f"LLM Thought: {thought_text}")

        console_manager.print_vibe(f"AI Thought: {thought_text}")

        memory_update_metrics = await update_memory(
            command_message=f"command: {command} request: {request}",
            command_output=f"AI Thought: {thought_text}",
            vibe_output="",
            model_name=output_flags.model_name,
        )
        llm_metrics_accumulator.add_metrics(
            memory_update_metrics, "LLM Memory Update (Thought)"
        )

        # Display total metrics and return
        llm_metrics_accumulator.print_total_if_enabled("Total LLM Vibe Processing")

        return Success(
            message=f"Processed AI thought: {thought_text}",
            metrics=llm_metrics_accumulator.get_metrics(),
        )

    elif action == ActionType.FEEDBACK:
        feedback_message = response_action.message
        feedback_explanation = response_action.explanation or ""
        feedback_suggestion = response_action.suggestion or ""
        logger.info(f"LLM issued FEEDBACK. Message: {feedback_message}")
        logger.info(f"LLM issued FEEDBACK. Explanation: {feedback_explanation}")
        logger.info(f"LLM issued FEEDBACK. Suggestion: {feedback_suggestion}")

        if feedback_message:
            console_manager.print_vibe(feedback_message)

        if not feedback_explanation:
            feedback_explanation = "AI suggests reviewing memory."
        if not feedback_suggestion:
            logger.warning("AI returned FEEDBACK with no suggestion.")
            console_manager.print_warning("AI unable to provide a specific suggestion.")
            feedback_suggestion = "AI unable to provide a specific suggestion."

        console_manager.print_proposal(
            f"Suggested memory update: {feedback_suggestion}"
        )

        confirmation_result = await _handle_command_confirmation(
            display_cmd="Use suggested memory update?",
            execution_mode=exec_mode,
            model_name=output_flags.model_name,
            explanation=feedback_explanation,
        )

        if isinstance(confirmation_result, Error):
            # Display total metrics and return
            llm_metrics_accumulator.print_total_if_enabled("Total LLM Vibe Processing")
            return confirmation_result

        # If confirmed, update memory
        memory_update_metrics = await update_memory(
            command_message=f"command: {command} request: {request}",
            command_output=feedback_message,
            vibe_output=feedback_suggestion,
            model_name=output_flags.model_name,
        )
        llm_metrics_accumulator.add_metrics(
            memory_update_metrics, "LLM Memory Update (Feedback)"
        )

        # Display total metrics and return
        llm_metrics_accumulator.print_total_if_enabled("Total LLM Vibe Processing")

        return Success(
            message=f"Applied AI feedback: {feedback_suggestion}",
            metrics=llm_metrics_accumulator.get_metrics(),
        )

    elif action == ActionType.COMMAND:
        commands_to_run = response_action.commands or []
        kubectl_verb, kubectl_args = _extract_verb_args(command, commands_to_run)

        allowed_exit_codes_list = response_action.allowed_exit_codes or [0]

        if not kubectl_verb:
            return Error(error="LLM planning failed: Could not determine command verb.")

        if kubectl_verb == "port-forward" and live_display:
            logger.info("Dispatching 'port-forward' command to live display handler.")
            resource = kubectl_args[0] if kubectl_args else ""
            pf_args = tuple(kubectl_args[1:]) if len(kubectl_args) > 1 else ()

            if not resource:
                logger.error("Port-forward live display requires a resource name.")
                return Error(error="Missing resource name for port-forward.")

            # Call the live display handler directly
            return await handle_port_forward_with_live_display(
                resource=resource,
                args=pf_args,
                output_flags=output_flags,
                summary_prompt_func=summary_prompt_func,
                allowed_exit_codes=tuple(allowed_exit_codes_list),
                presentation_hints=llm_planner_response.presentation_hints,
            )
        else:
            # Pass through any presentation hints from the planner so that summary
            # prompts can leverage them when building their context fragments.
            result = await _confirm_and_execute_plan(
                kubectl_verb=kubectl_verb,
                kubectl_args=kubectl_args,
                yaml_content=response_action.yaml_manifest,
                plan_explanation=response_action.explanation,
                original_command_verb=command,
                execution_mode=exec_mode,
                live_display=live_display,
                output_flags=output_flags,
                summary_prompt_func=summary_prompt_func,
                allowed_exit_codes=tuple(allowed_exit_codes_list),
                presentation_hints=llm_planner_response.presentation_hints,
                llm_metrics_accumulator=llm_metrics_accumulator,
            )

            # Print total metrics for the entire vibe operation
            llm_metrics_accumulator.print_total_if_enabled(
                "Total LLM Command Processing"
            )

            return result

    else:  # Default case (Unknown ActionType)
        logger.error(
            f"Internal error: Unknown ActionType: {response_action.action_type}"
        )
        return Error(
            error=f"Internal error: Unknown ActionType received from "
            f"LLM: {response_action.action_type}"
        )


async def _confirm_and_execute_plan(
    kubectl_verb: str,
    kubectl_args: list[str],
    yaml_content: str | None,
    plan_explanation: str | None,
    original_command_verb: str,
    execution_mode: ExecutionMode,
    live_display: bool,
    output_flags: OutputFlags,
    summary_prompt_func: SummaryPromptFragmentFunc,
    allowed_exit_codes: tuple[int, ...],
    presentation_hints: str | None = None,
    llm_metrics_accumulator: LLMMetricsAccumulator | None = None,
) -> Result:
    """Confirm and execute the kubectl command plan."""
    # Determine if YAML content is present for display formatting
    has_yaml_content = yaml_content is not None and yaml_content.strip() != ""

    # Create the display command using the helper function
    display_cmd = _create_display_command(kubectl_verb, kubectl_args, has_yaml_content)

    # Determine if confirmation is needed
    command_is_read_only = is_kubectl_command_read_only([kubectl_verb, *kubectl_args])
    confirmation_is_required = (
        not command_is_read_only and execution_mode is not ExecutionMode.AUTO
    )

    logger.debug(
        f"Confirmation check: command='{display_cmd}', verb='{original_command_verb}', "
        f"is_read_only={command_is_read_only}, execution_mode={execution_mode}, "
        f"confirmation_required={confirmation_is_required}"
    )

    if confirmation_is_required:
        confirmation_result = await _handle_command_confirmation(
            display_cmd=display_cmd,
            execution_mode=execution_mode,
            model_name=output_flags.model_name,
            explanation=plan_explanation,
        )
        if confirmation_result is not None:
            return confirmation_result
    elif not command_is_read_only and execution_mode is ExecutionMode.AUTO:
        logger.info(
            "Proceeding with potentially dangerous command in autonomous mode "
            f"(not read-only): {display_cmd}"
        )
    elif command_is_read_only:
        logger.info(
            f"Proceeding with read-only command without confirmation: {display_cmd}"
        )

    # Display the command being run if show_kubectl is true, before execution
    if output_flags.show_kubectl:
        console_manager.print_processing(f"Running: {display_cmd}")

    # Execute the command
    logger.info(f"'{kubectl_verb}' command dispatched to standard handler.")
    result = _execute_command(
        kubectl_verb,
        kubectl_args,
        yaml_content,
        allowed_exit_codes=allowed_exit_codes,
    )

    logger.debug(
        f"Result type={type(result)}, result.data='{getattr(result, 'data', None)}'"
    )

    # Extract output/error for memory update
    if isinstance(result, Success):
        command_output_str = str(result.data) if result.data is not None else ""
    elif isinstance(result, Error):
        command_output_str = str(result.error) if result.error is not None else ""
    else:
        # This should be impossible given Result = Union[Success, Error]
        raise RuntimeError(
            f"_execute_command returned an unexpected type: {type(result)}"
        )

    vibe_output_str = plan_explanation or f"Executed: {display_cmd}"

    try:
        memory_update_metrics = await update_memory(
            command_message=f"command: {display_cmd} original: {original_command_verb}",
            command_output=command_output_str,
            vibe_output=vibe_output_str,
            model_name=output_flags.model_name,
        )
        logger.info("Memory updated after command execution.")
        if llm_metrics_accumulator:
            llm_metrics_accumulator.add_metrics(
                memory_update_metrics, "LLM Memory Update (Execution Record)"
            )
    except Exception as mem_e:
        logger.error(f"Failed to update memory after command execution: {mem_e}")
        return Error(
            error=f"Failed to update memory after command execution: {mem_e}",
            exception=mem_e,
        )

    try:
        return await handle_command_output(
            result,
            output_flags,
            summary_prompt_func,
            command=kubectl_verb,
            presentation_hints=presentation_hints,
            llm_metrics_accumulator=llm_metrics_accumulator,
            suppress_total_metrics=True,
        )
    except RecoverableApiError as api_err:
        logger.warning(
            f"Recoverable API error during command handling: {api_err}", exc_info=True
        )
        console_manager.print_error(f"API Error: {api_err}")
        # create_api_error is in command_handler, so we need to import it or
        # replicate logic
        return Error(
            error=f"API Error: {api_err}",
            exception=api_err,
            halt_auto_loop=False,
            # metrics=api_err.metrics # If RecoverableApiError carries metrics
        )
    except Exception as e:
        logger.error(f"Error handling command output: {e}", exc_info=True)
        error_str = str(e)

        # Persist error to memory for future context
        await update_memory(
            command_message="system",
            command_output=f"Error handling command output: {error_str}",
            vibe_output=f"Error handling command output: {error_str}",
            model_name=output_flags.model_name,
        )

        console_manager.print_error(f"Error handling command output: {error_str}")
        return Error(error=f"Error handling command output: {error_str}", exception=e)


async def _handle_command_confirmation(
    display_cmd: str,
    execution_mode: ExecutionMode,
    model_name: str,
    explanation: str | None = None,
) -> Result | None:
    """Handle command confirmation with enhanced options.

    Args:
        display_cmd: The command string (used for logging/memory).
        execution_mode: Execution mode for the command.
        model_name: The model name used.
        explanation: Optional explanation from the AI.

    Returns:
        Result if the command was cancelled or memory update failed,
        None if the command should proceed.
    """
    # AUTO mode bypasses confirmation entirely
    if execution_mode is ExecutionMode.AUTO:
        logger.info("Confirmation bypassed (auto mode) for command: %s", display_cmd)
        return None  # Proceed with command execution

    semiauto = execution_mode is ExecutionMode.SEMIAUTO

    options_base = "[Y]es, [N]o, yes [A]nd, no [B]ut, or [M]emory?"
    options_exit = " or [E]xit?"
    prompt_options_str = f"{options_base}{options_exit if semiauto else ''}"
    choice_list = ["y", "n", "a", "b", "m"] + (["e"] if semiauto else [])
    prompt_suffix = f" ({' / '.join(choice_list)})"

    if explanation:
        console_manager.print_note(f"AI Explanation: {explanation}")

    while True:
        # Print the prompt using console_manager which handles Rich markup
        # Print the command line first
        prompt_command_line = (
            f"{display_cmd}"  # display_cmd is now the question itself for feedback
        )
        console_manager.print(prompt_command_line, style="info")
        # Print the options on a new line
        prompt_options_line = f"{prompt_options_str}{prompt_suffix}"
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
            # from vibectl.memory import get_memory # Already imported
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
            console_manager.print(
                f"\n{prompt_options_str}{prompt_suffix}", style="info"
            )
            continue

        if choice in ["n", "b"]:
            # No or No But - don't execute the command
            logger.info(
                f"User cancelled execution of planned command: kubectl {display_cmd}"
            )
            console_manager.print_cancelled()

            # If "but" is chosen, do a fuzzy memory update
            if choice == "b":
                memory_result = await _handle_fuzzy_memory_update("no but", model_name)
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
                memory_result = await _handle_fuzzy_memory_update("yes and", model_name)
                if isinstance(memory_result, Error):
                    return memory_result  # Propagate memory update error

            # Proceed with command execution
            return None  # Indicates proceed


async def _handle_fuzzy_memory_update(
    option: str,
    model_name: str,
) -> Result:
    """Handle fuzzy memory updates.

    Args:
        option: The option chosen ("yes and" or "no but")
        model_name: The model name to use

    Returns:
        Result
    """
    logger.info(f"User requested fuzzy memory update with '{option}' option")
    console_manager.print_note("Enter additional information for memory:")
    update_text = click.prompt("Memory update")

    try:
        cfg = Config()
        current_memory = get_memory(cfg)

        system_fragments, user_fragments = memory_fuzzy_update_prompt(
            current_memory=current_memory,
            update_text=update_text,
            config=cfg,
        )

        console_manager.print_processing("Updating memory...")
        updated_memory_text, metrics = await run_llm(
            system_fragments,
            user_fragments,
            model_name=model_name,
            config=cfg,
        )

        set_memory(updated_memory_text, cfg)
        console_manager.print_success("Memory updated")

        console_manager.safe_print(
            console_manager.console,
            Panel(
                updated_memory_text,
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


# Helper function for Vibe planning
async def _get_llm_plan(
    model_name: str,
    plan_system_fragments: SystemFragments,
    plan_user_fragments: UserFragments,
    response_model_type: type[LLMPlannerResponse],
    *,
    config: Config,
) -> Result:
    """Calls the LLM to get a command plan and validates the response."""
    console_manager.print_processing(f"Consulting {model_name} for a plan...")
    logger.debug(
        f"Final planning prompt:\n{plan_system_fragments} {plan_user_fragments}"
    )

    try:
        # Run the LLM via the shared helper (captures metrics and centralises behaviour)
        llm_response_text, metrics = await run_llm(
            plan_system_fragments,
            plan_user_fragments,
            model_name=model_name,
            config=config,
            response_model=response_model_type,
        )
        logger.info(f"Raw LLM response text:\n{llm_response_text}")

        if not llm_response_text or llm_response_text.strip() == "":
            logger.error("LLM returned an empty response.")
            await update_memory(
                command_message="system",
                command_output="LLM Error: Empty response.",
                vibe_output="LLM Error: Empty response.",
                model_name=model_name,
            )
            return Error("LLM returned an empty response.")

        # Validate against LLMPlannerResponse
        response = LLMPlannerResponse.model_validate_json(llm_response_text)
        logger.debug(f"Parsed LLM response object: {response}")

        if not hasattr(response, "action") or response.action is None:
            logger.error("LLMPlannerResponse has no action or action is None.")
            await update_memory(
                command_message="system",
                command_output="LLM Error: No action in planner response.",
                vibe_output="LLM Error: No action in planner response.",
                model_name=model_name,
            )
            return Error("LLM Error: Planner response contained no action.")

        logger.info(f"Validated ActionType: {response.action.action_type}")
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
        memory_update_metrics = await update_memory(  # Capture metrics
            command_message="system",
            command_output=error_msg,
            vibe_output=(
                f"System Error: Failed to parse LLM response: "
                f"{truncated_llm_response}... Check model or prompt."
            ),
            model_name=model_name,
        )
        # create_api_error is in command_handler, needs import or replication
        return Error(
            error=error_msg,
            exception=e,
            halt_auto_loop=False,
            metrics=memory_update_metrics,
        )
    except (
        RecoverableApiError
    ) as api_err:  # Catch recoverable API errors during execute
        logger.warning(
            f"Recoverable API error during Vibe planning: {api_err}", exc_info=True
        )
        # Print API error before returning
        console_manager.print_error(f"API Error: {api_err}")
        # create_api_error is in command_handler, needs import or replication
        return Error(error=str(api_err), exception=api_err, halt_auto_loop=False)
    except Exception as e:  # Catch other errors during execute
        logger.error(f"Error during LLM planning interaction: {e}", exc_info=True)
        error_str = str(e)
        # Persist error to memory for future context
        await update_memory(
            command_message="system",
            command_output=f"LLM planning error: {error_str}",
            vibe_output=f"System Error: {error_str}",
            model_name=model_name,
        )

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
