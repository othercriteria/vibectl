from vibectl.command_handler import (
    configure_output_flags,
    handle_standard_command,
    handle_watch_with_live_display,
)
from vibectl.execution.vibe import handle_vibe_request
from vibectl.logutil import logger
from vibectl.memory import configure_memory_flags
from vibectl.prompts.logs import logs_plan_prompt, logs_prompt
from vibectl.types import Error, Result


async def run_logs_command(
    resource: str,
    args: tuple[str, ...],
    *,
    show_vibe: bool | None = None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    live_display: bool = True,
) -> Result:
    """Entry-point for the `vibectl logs` subcommand."""
    logger.info(
        "Invoking 'logs' subcommand with resource=%s, args=%s, live_display=%s",
        resource,
        args,
        live_display,
    )

    output_flags = configure_output_flags(
        show_vibe=show_vibe,
    )
    configure_memory_flags(freeze_memory, unfreeze_memory)

    if resource == "vibe":
        if not args:
            return Error(
                error=(
                    "Missing request after 'vibe'. "
                    'Example: vibectl logs vibe "the nginx pod in default"'
                )
            )

        request = " ".join(args)
        logger.info("Planning logs vibe request: %s", request)

        return await handle_vibe_request(
            request=request,
            command="logs",
            plan_prompt_func=logs_plan_prompt,
            summary_prompt_func=logs_prompt,
            output_flags=output_flags,
        )

    # Detect streaming mode (kubectl --follow / -f)
    follow_flag_present = "--follow" in args or "-f" in args

    if follow_flag_present and live_display:
        logger.info("Dispatching logs --follow to live display handler.")
        return await handle_watch_with_live_display(
            command="logs",
            resource=resource,
            args=args,
            output_flags=output_flags,
            summary_prompt_func=logs_prompt,
        )

    logger.info("Handling standard 'logs' command (non-streaming).")
    return await handle_standard_command(
        command="logs",
        resource=resource,
        args=args,
        output_flags=output_flags,
        summary_prompt_func=logs_prompt,
    )
