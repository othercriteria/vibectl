"""
Execution logic for the 'vibectl check' subcommand.
"""

from json import JSONDecodeError

from pydantic import ValidationError

from vibectl.command_handler import configure_output_flags
from vibectl.config import Config
from vibectl.logutil import logger
from vibectl.memory import configure_memory_flags, get_memory
from vibectl.model_adapter import (
    RecoverableApiError,
    get_model_adapter,
)
from vibectl.prompt import (
    PLAN_CHECK_PROMPT,
    Fragment,
    SystemFragments,
    UserFragments,
)
from vibectl.schema import (
    CommandAction,
    DoneAction,
    ErrorAction,
    FeedbackAction,
    LLMPlannerResponse,
    ThoughtAction,
    WaitAction,
)
from vibectl.types import (
    Error,
    LLMMetrics,
    Result,
    Success,
)
from vibectl.utils import console_manager


def _get_check_llm_plan(
    model_name: str,
    plan_system_fragments: SystemFragments,
    plan_user_fragments: UserFragments,
    config: Config,
) -> Result:
    """Calls the LLM to get a command plan for 'check' and validates the response."""
    model_adapter = get_model_adapter(config=config)

    try:
        model = model_adapter.get_model(model_name)
    except Exception as e:
        error_msg = f"Failed to get model '{model_name}': {e}"
        logger.error(error_msg, exc_info=True)
        # metrics = update_memory(
        #     command_message="system",
        #     command_output=error_msg,
        #     vibe_output=f"System Error: Failed to get model '{model_name}'.",
        #     model_name=model_name,
        #     config=config,
        # )
        # For check, memory update on model failure might be less critical than for auto
        return Error(
            error=error_msg, exception=e, halt_auto_loop=False
        )  # halt_auto_loop might not be relevant for check

    console_manager.print_processing(
        f"Consulting {model_name} to evaluate predicate..."
    )
    logger.debug(
        f"Final 'check' planning prompt:\n{plan_system_fragments} {plan_user_fragments}"
    )

    try:
        llm_response_text, metrics = model_adapter.execute_and_log_metrics(
            model=model,
            system_fragments=plan_system_fragments,
            user_fragments=plan_user_fragments,
            response_model=LLMPlannerResponse,
        )
        logger.info(f"Raw LLM response text for 'check':\n{llm_response_text}")

        if not llm_response_text or llm_response_text.strip() == "":
            logger.error("LLM returned an empty response for 'check'.")
            # update_memory(...) # Optional memory update
            return Error("LLM returned an empty response.")

        response = LLMPlannerResponse.model_validate_json(llm_response_text)
        logger.debug(f"Parsed LLM response object for 'check': {response}")

        if not hasattr(response, "action") or response.action is None:
            logger.error(
                "LLMPlannerResponse for 'check' has no action or action is None."
            )
            # update_memory(...) # Optional memory update
            return Error("LLM Error: Planner response for 'check' contained no action.")

        logger.info(f"Validated ActionType for 'check': {response.action.action_type}")
        return Success(data=response, metrics=metrics)

    except (JSONDecodeError, ValidationError) as e:
        logger.warning(
            f"Failed to parse LLM response for 'check' as JSON ({type(e).__name__}). "
            f"Response Text: {llm_response_text[:500]}..."
        )
        error_msg = f"Failed to parse LLM response for 'check' as expected JSON: {e}"
        # memory_update_metrics = update_memory(...) # Optional
        return Error(
            error=error_msg, exception=e
        )  # Potentially non-halting for API errors
    except RecoverableApiError as api_err:
        logger.warning(
            f"Recoverable API error during 'check' planning: {api_err}", exc_info=True
        )
        console_manager.print_error(f"API Error: {api_err}")
        return Error(str(api_err), exception=api_err, halt_auto_loop=False)
    except Exception as e:
        logger.error(
            f"Error during LLM 'check' planning interaction: {e}", exc_info=True
        )
        console_manager.print_error(f"Error evaluating predicate: {e!s}")
        return Error(str(e), exception=e)


async def run_check_command(
    predicate: str,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    show_kubectl: bool | None,
    model: str | None,
    freeze_memory: bool,
    unfreeze_memory: bool,
    show_metrics: bool | None,
) -> Result:
    """
    Implements the 'check <predicate>' subcommand logic.
    For Phase 1 (one-shot evaluation):
    - LLM `DoneAction` with exit_code 0, 1, 2, 3 -> vibectl exits with that code.
    - LLM `ErrorAction` -> vibectl exits with 2 or 3.
    - LLM `CommandAction` or `WaitAction` -> vibectl exits with 3.
    - LLM `FeedbackAction` -> vibectl exits with 2 or 3.
    """
    logger.info(f"Invoking 'check' subcommand with predicate: {predicate}")
    configure_memory_flags(freeze_memory, unfreeze_memory)

    output_flags = configure_output_flags(
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        model=model,
        show_kubectl=show_kubectl,
        show_metrics=show_metrics,
    )

    cfg = Config()
    exit_code_to_set = 3  # Default to 'cannot determine'
    llm_metrics: LLMMetrics | None = None
    result_to_return: Result  # Explicitly type result_to_return

    logger.info(f"Evaluating predicate: {predicate}")

    # Prepare prompt fragments
    memory_context_str = get_memory(cfg)
    plan_system_fragments, plan_user_fragments_base = PLAN_CHECK_PROMPT

    final_user_fragments_list = list(plan_user_fragments_base)
    if memory_context_str:
        final_user_fragments_list.insert(
            0, Fragment(f"Memory Context:\n{memory_context_str}")
        )
    final_user_fragments_list.append(Fragment(f"Request (Predicate): {predicate}"))
    final_user_fragments = UserFragments(final_user_fragments_list)

    # Get the LLM plan directly
    plan_result = _get_check_llm_plan(
        output_flags.model_name,
        plan_system_fragments,
        final_user_fragments,
        cfg,
    )

    if isinstance(plan_result, Error):
        logger.error(f"Error from LLM planning for 'check': {plan_result.error}")
        console_manager.print_error(f"Error evaluating predicate: {plan_result.error}")
        exit_code_to_set = 3  # Cannot determine due to system/planning error
        result_to_return = (
            plan_result  # Assign plan_result (which is an Error) directly
        )
    elif isinstance(plan_result, Success):
        # Type check for plan_result.data before assignment
        if not isinstance(plan_result.data, LLMPlannerResponse):
            logger.error(
                "Unexpected data type in Success object from _get_check_llm_plan: "
                f"{type(plan_result.data)}"
            )
            exit_code_to_set = 3  # Cannot determine due to internal error
            result_to_return = Error(
                error="Internal error: Unexpected data type from LLM plan for 'check'.",
                original_exit_code=exit_code_to_set,
            )
        else:
            llm_planner_response: LLMPlannerResponse = plan_result.data
            llm_metrics = (
                plan_result.metrics
            )  # Capture metrics from successful planning
            action = llm_planner_response.action
            action_type_str = action.action_type.value  # Get string value of enum

            logger.info(f"LLM planned action for 'check': {action_type_str}")
            vibe_message = f"LLM Action: {action_type_str}"

            if isinstance(action, DoneAction):
                exit_code_to_set = (
                    action.exit_code if action.exit_code is not None else 3
                )
                vibe_message += f", Exit Code: {exit_code_to_set}"
                logger.info(
                    f"DoneAction received with exit_code: {action.exit_code} -> "
                    f"using {exit_code_to_set}"
                )
            elif isinstance(action, ErrorAction):
                vibe_message += f", Message: {action.message}"
                logger.warning(f"ErrorAction received: {action.message}")
                # Map ErrorAction to exit code 2 (ambiguous/error) or
                # 3 (cannot determine)
                # For simplicity, let's use 2 for now, assuming it's an issue
                # with the predicate itself.
                exit_code_to_set = 2
            elif isinstance(action, CommandAction):
                vibe_message += f", Commands: {action.commands}"
                logger.info(
                    "CommandAction received. For Phase 1, this means "
                    f"'cannot determine'. Intended commands: {action.commands}"
                )
                exit_code_to_set = 3
            elif isinstance(action, WaitAction):
                vibe_message += f", Duration: {action.duration_seconds}s"
                logger.info(
                    "WaitAction received. For Phase 1, this means "
                    f"'cannot determine'. Duration: {action.duration_seconds}"
                )
                exit_code_to_set = 3
            elif isinstance(action, FeedbackAction):
                vibe_message += f", Message: {action.message}"
                logger.info(
                    f"FeedbackAction received: {action.message}. Interpreting as "
                    "'cannot determine' or 'ambiguous'."
                )
                exit_code_to_set = (
                    2  # Or 3, depending on how feedback should be treated
                )
            elif isinstance(action, ThoughtAction):
                vibe_message += f", Text: {action.text}"
                logger.info(
                    f"ThoughtAction received: {action.text}. Interpreting as "
                    "'cannot determine'."
                )
                exit_code_to_set = 3
            else:
                logger.warning(
                    f"Unhandled action type from LLM for 'check': {action_type_str}"
                )
                exit_code_to_set = 3  # Default for unhandled actions

            if output_flags.show_vibe:
                console_manager.print_vibe(vibe_message)

            result_to_return = Success(message=vibe_message, metrics=llm_metrics)
    else:
        # Should not happen if plan_result is always Error or Success
        logger.error("Unexpected result type from _get_check_llm_plan")
        exit_code_to_set = 3
        result_to_return = Error("Internal error: Unexpected planning result type")

    # Store the determined exit code in the Result object
    result_to_return.original_exit_code = exit_code_to_set

    # Display metrics if requested and available
    if llm_metrics and output_flags.show_metrics:
        console_manager.print_metrics(
            latency_ms=llm_metrics.latency_ms,
            tokens_in=llm_metrics.token_input,
            tokens_out=llm_metrics.token_output,
            source="LLM Predicate Evaluation",
            total_duration=llm_metrics.total_processing_duration_ms,
        )

    logger.info(f"'check' subcommand determined exit code: {exit_code_to_set}")
    return result_to_return
