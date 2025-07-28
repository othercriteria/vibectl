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
    show_raw_output: bool | None = None,
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

    # Build kwargs for configure_output_flags dynamically to avoid passing
    # show_raw_output when it wasn't explicitly provided. Tests expect the
    # sub-command to forward **only** parameters with concrete values.
    cfg_kwargs: dict[str, object] = {"show_vibe": show_vibe}
    if show_raw_output is not None:
        cfg_kwargs["show_raw_output"] = show_raw_output

    output_flags = configure_output_flags(**cfg_kwargs)  # type: ignore[arg-type]
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
