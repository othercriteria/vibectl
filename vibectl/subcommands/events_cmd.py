from vibectl.command_handler import (
    configure_output_flags,
    handle_standard_command,
    handle_watch_with_live_display,
)
from vibectl.execution.vibe import handle_vibe_request
from vibectl.logutil import logger
from vibectl.memory import (
    configure_memory_flags,
)
from vibectl.prompts.events import (
    events_plan_prompt,
    events_prompt,
)
from vibectl.types import MetricsDisplayMode, Result


async def run_events_command(
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    show_kubectl: bool | None = None,
    show_metrics: MetricsDisplayMode | None = None,
    show_streaming: bool | None = None,
) -> Result:
    """
    Implements the 'events' subcommand logic, including logging and error handling.
    """
    logger.info(f"Invoking 'events' subcommand with args: {args}")

    output_flags = configure_output_flags(
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        model=model,
        show_kubectl=show_kubectl,
        show_metrics=show_metrics,
        show_streaming=show_streaming,
    )
    configure_memory_flags(freeze_memory, unfreeze_memory)

    if args and args[0] == "vibe":
        request = " ".join(args[1:])
        logger.info(f"Planning how to: get events for '{request}'")
        result = await handle_vibe_request(
            request=request,
            command="events",
            plan_prompt_func=events_plan_prompt,
            summary_prompt_func=events_prompt,
            output_flags=output_flags,
        )
        logger.info("Completed 'events' subcommand for vibe request.")

    elif "--watch" in args or "-w" in args:
        logger.info("Handling 'events' command with --watch flag using live display.")
        result = await handle_watch_with_live_display(
            command="events",
            resource="",  # events command doesn't take a resource
            args=args,
            output_flags=output_flags,
            summary_prompt_func=events_prompt,
        )
        logger.info("Completed 'events --watch' subcommand.")

    else:
        logger.info("Handling standard 'events' command.")
        result = await handle_standard_command(
            command="events",
            resource="",  # events command doesn't take a resource
            args=args,
            output_flags=output_flags,
            summary_prompt_func=events_prompt,
        )
        logger.info("Completed 'events' subcommand.")

    return result
