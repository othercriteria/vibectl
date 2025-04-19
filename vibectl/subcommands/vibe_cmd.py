from vibectl.command_handler import (
    configure_output_flags,
    handle_vibe_request,
)
from vibectl.console import console_manager
from vibectl.logutil import logger
from vibectl.memory import configure_memory_flags, get_memory
from vibectl.prompt import PLAN_VIBE_PROMPT, vibe_autonomous_prompt
from vibectl.types import Error, Result, Success


def run_vibe_command(
    request: str | None,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    show_kubectl: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    yes: bool = False,
    exit_on_error: bool = True,
) -> Result:
    """
    Implements the 'vibe' subcommand logic, including logging and error handling.
    Returns a Result (Success or Error).

    Args:
        ...
        exit_on_error: If True (default), errors will terminate the process.
            If False, errors are returned as Error objects for programmatic handling
            (e.g., in tests).
    """
    logger.info(f"Invoking 'vibe' subcommand with request: {request!r}")
    try:
        output_flags = configure_output_flags(
            show_raw_output=show_raw_output,
            show_vibe=show_vibe,
            model=model,
            show_kubectl=show_kubectl,
        )
        configure_memory_flags(freeze_memory, unfreeze_memory)

        memory_context = get_memory() or ""

        # Handle empty request case
        if not request:
            logger.info("No request provided; using memory context for planning.")
            request = ""
            console_manager.print_processing(
                "Planning next steps based on memory context..."
            )
        else:
            logger.info(f"Planning how to: {request}")
            console_manager.print_processing(f"Planning how to: {request}")

        try:
            handle_vibe_request(
                request=request,
                command="vibe",
                plan_prompt=PLAN_VIBE_PROMPT,
                summary_prompt_func=vibe_autonomous_prompt,
                output_flags=output_flags,
                yes=yes,
                autonomous_mode=True,
                memory_context=memory_context,
            )
        except Exception as e:
            logger.error("Error in handle_vibe_request: %s", e, exc_info=True)
            if exit_on_error:
                raise
            return Error(error="Exception in handle_vibe_request", exception=e)
        logger.info("Completed 'vibe' subcommand.")
        return Success(message="Completed 'vibe' subcommand.")
    except Exception as e:
        logger.error("Error in 'vibe' subcommand: %s", e, exc_info=True)
        if exit_on_error:
            raise
        return Error(error="Exception in 'vibe' subcommand", exception=e)
