import asyncio

from vibectl.command_handler import (
    configure_output_flags,
    handle_command_output,
    handle_watch_with_live_display,
    run_kubectl,
)
from vibectl.console import console_manager
from vibectl.execution.vibe import handle_vibe_request
from vibectl.logutil import logger
from vibectl.memory import (
    configure_memory_flags,
)
from vibectl.prompt import (
    PLAN_EVENTS_PROMPT,
    events_prompt,
)
from vibectl.types import Error, Result, Success


async def run_events_command(
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    show_kubectl: bool | None,
    model: str | None,
    freeze_memory: bool,
    unfreeze_memory: bool,
    show_metrics: bool | None,
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
            show_metrics=show_metrics,
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
                result_vibe = await handle_vibe_request(
                    request=request,
                    command="events",
                    plan_prompt_func=lambda: PLAN_EVENTS_PROMPT,
                    summary_prompt_func=events_prompt,
                    output_flags=output_flags,
                )
                logger.info("Completed 'events' subcommand for vibe request.")
                return result_vibe
            except Exception as e:
                logger.error("Error in handle_vibe_request: %s", e, exc_info=True)
                return Error(error="Exception in handle_vibe_request", exception=e)

        # Check for --watch flag
        watch_flag_present = "--watch" in args or "-w" in args

        if watch_flag_present:
            logger.info(
                "Handling 'events' command with --watch flag using live display."
            )
            # For 'events', the 'resource' argument to handle_watch_with_live_display
            # isn't directly applicable like in 'get <resource>'.
            result = await handle_watch_with_live_display(
                command="events",
                resource="",  # kubectl events doesn't take a resource like 'get'
                args=args,
                output_flags=output_flags,
                summary_prompt_func=events_prompt,
            )
            # Forward the Result from the handler
            if isinstance(result, Error):
                logger.error(
                    f"Error from handle_watch_with_live_display: {result.error}"
                )
                return result
            logger.info("Completed 'events --watch' subcommand.")
            return result

        # Original logic for non-watch 'kubectl events'
        logger.info("Handling standard 'events' command.")
        try:
            cmd = ["events", *args]
            logger.info(f"Running kubectl command: {' '.join(cmd)}")
            kubectl_result = await asyncio.to_thread(run_kubectl, cmd)

            if isinstance(kubectl_result, Error):
                logger.error(f"Error running kubectl: {kubectl_result.error}")
                return kubectl_result

            output_data = kubectl_result.data
            if not output_data:
                console_manager.print_empty_output_message()
                logger.info("No output from kubectl events command.")
                return Success(message="No output from kubectl events command.")

            # Use asyncio.to_thread for sync output handler
            await asyncio.to_thread(
                handle_command_output,
                output=output_data,
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
