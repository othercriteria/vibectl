from vibectl.command_handler import (
    configure_output_flags,
    handle_command_output,
    handle_vibe_request,
    run_kubectl,
)
from vibectl.console import console_manager
from vibectl.logutil import logger
from vibectl.memory import (
    configure_memory_flags,
    get_memory,
)
from vibectl.prompt import (
    PLAN_EVENTS_PROMPT,
    events_prompt,
)
from vibectl.types import Error, Result, Success


def run_events_command(
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    show_kubectl: bool | None,
    model: str | None,
    freeze_memory: bool,
    unfreeze_memory: bool,
) -> Result:
    """
    Implements the 'events' subcommand logic, including logging and error handling.
    Returns a Result (Success or Error).
    """
    logger.info(f"Invoking 'events' subcommand with args: {args}")
    try:
        output_flags = configure_output_flags(
            show_raw_output=show_raw_output,
            show_vibe=show_vibe,
            model=model,
            show_kubectl=show_kubectl,
        )
        configure_memory_flags(freeze_memory, unfreeze_memory)

        # Special case for 'vibe' command
        if args and args[0] == "vibe":
            if len(args) < 2:
                msg = (
                    "Missing request after 'vibe' command. "
                    "Please provide a natural language request, e.g.: "
                    'vibectl events vibe "all events in kube-system"'
                )
                return Error(error=msg)
            request = " ".join(args[1:])
            logger.info("Planning how to: get events for %s", request)
            try:
                handle_vibe_request(
                    request=request,
                    command="events",
                    plan_prompt=PLAN_EVENTS_PROMPT,
                    summary_prompt_func=events_prompt,
                    output_flags=output_flags,
                    memory_context=get_memory() or "",
                )
            except Exception as e:
                logger.error("Error in handle_vibe_request: %s", e, exc_info=True)
                return Error(error="Exception in handle_vibe_request", exception=e)
            logger.info("Completed 'events' subcommand for vibe request.")
            return Success(message="Completed 'events' subcommand for vibe request.")

        # Always use 'kubectl events' (never 'kubectl get events')
        try:
            cmd = ["events", *args]
            logger.info(f"Running kubectl command: {' '.join(cmd)}")
            output = run_kubectl(cmd, capture=True)
            if not output:
                console_manager.print_empty_output_message()
                logger.info("No output from kubectl events command.")
                return Success(message="No output from kubectl events command.")
            handle_command_output(
                output=output,
                output_flags=output_flags,
                summary_prompt_func=events_prompt,
            )
        except Exception as e:
            logger.error("Error running kubectl for events: %s", e, exc_info=True)
            return Error(error="Exception running kubectl for events", exception=e)
        logger.info("Completed 'events' subcommand.")
        return Success(message="Completed 'events' subcommand.")
    except Exception as e:
        logger.error("Error in 'events' subcommand: %s", e, exc_info=True)
        return Error(error="Exception in 'events' subcommand", exception=e)
