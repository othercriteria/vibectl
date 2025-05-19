from vibectl.command_handler import (
    configure_output_flags,
)
from vibectl.execution.vibe import handle_vibe_request
from vibectl.logutil import logger
from vibectl.memory import configure_memory_flags
from vibectl.prompt import PLAN_CHECK_PROMPT
from vibectl.types import (
    Error,
    PromptFragments,
    Result,
    Success,
    SystemFragments,
    UserFragments,
)


async def run_check_command(
    predicate: str,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    show_kubectl: bool | None,
    model: str | None,
    freeze_memory: bool,
    unfreeze_memory: bool,
    show_metrics: bool | None,
    # Add other relevant parameters from PLANNED_CHANGES.md if needed,
    # e.g., max_iterations, timeout
    # For now, keeping it similar to diff_cmd.py
) -> Result:
    """
    Implements the 'check' subcommand logic, including logging and error handling.
    Returns a Result (Success or Error).
    """
    logger.info(f"Invoking 'check' subcommand with predicate: \"{predicate}\"")
    configure_memory_flags(freeze_memory, unfreeze_memory)

    output_flags = configure_output_flags(
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        model=model,
        show_kubectl=show_kubectl,
        show_metrics=show_metrics,
    )

    # Config object might be needed by handle_vibe_request or other utilities
    # cfg = Config() # Keep if necessary, remove if not used by handle_vibe_request path

    if not predicate:
        msg = (
            "Missing predicate for 'check' command. "
            "Please provide a natural language predicate, e.g.: "
            'vibectl check "are there any pods in a CrashLoopBackOff state?"'
        )
        logger.error(msg)
        error_result = Error(error=msg)
        error_result.original_exit_code = (
            2  # Use original_exit_code, exit code 2 for poorly posed
        )
        return error_result

    logger.info(f'Planning how to check predicate: "{predicate}"')

    # vibectl check always uses the LLM-based planning approach
    result = await handle_vibe_request(
        request=predicate,
        command="check",
        plan_prompt_func=lambda: PLAN_CHECK_PROMPT,  # Placeholder
        summary_prompt_func=lambda _config, _memory_context: PromptFragments(
            (SystemFragments([]), UserFragments([]))
        ),
        output_flags=output_flags,
        yes=True,  # For 'check', actions are read-only, so auto-proceed.
        # PLANNED_CHANGES.md implies autonomous loop.
        # This was False in diff_cmd.py, but True seems more appropriate for 'check'
    )

    if isinstance(result, Error):
        logger.error(f"Error from handle_vibe_request: {result.error}")
        # The exit_code from handle_vibe_request (e.g. via DONE action)
        # should be preserved.
        # If handle_vibe_request itself fails before LLM provides DONE,
        # it might set its own.
        return result

    logger.info(f"Completed 'check' subcommand for predicate: \"{predicate}\"")

    # Ensure that 'check' command signals the CLI runner to exit based on
    # its specific logic.
    # The actual exit code (0, 1, 2, 3) should be determined by the LLM's DONE action
    # and populated into the Result object by handle_vibe_request.
    if isinstance(result, Success):
        # For 'check', continue_execution should typically be False,
        # as it's a self-contained operation providing an exit status.
        result.continue_execution = False
        # The original_exit_code in result.original_exit_code should already
        # be set by handle_vibe_request based on the LLM's DONE action.

    return result
