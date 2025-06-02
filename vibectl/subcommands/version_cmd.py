from vibectl.command_handler import (
    configure_output_flags,
    handle_standard_command,
)
from vibectl.execution.vibe import handle_vibe_request
from vibectl.logutil import logger
from vibectl.memory import configure_memory_flags
from vibectl.prompts.version import version_plan_prompt, version_prompt
from vibectl.types import Error, MetricsDisplayMode, Result


async def run_version_command(
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool,
    unfreeze_memory: bool,
    show_kubectl: bool | None,
    show_metrics: MetricsDisplayMode | None,
    show_streaming: bool | None,
) -> Result:
    """Executes the version command logic."""

    logger.info(f"Invoking 'version' subcommand with args: {args}")

    output_flags = configure_output_flags(
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        model=model,
        show_kubectl=show_kubectl,
        show_metrics=show_metrics,
        show_streaming=show_streaming,
    )
    configure_memory_flags(freeze_memory, unfreeze_memory)

    # Handle vibe request for natural language version queries
    if args and args[0] == "vibe":
        if len(args) < 2:
            return Error(
                error="Missing request after 'vibe' command. "
                "Please provide a natural language version query, e.g.: "
                'vibectl version vibe "what version of kubernetes am I running?"'
            )

        request = " ".join(args[1:])
        logger.info(f"Planning version query: {request}")

        result = await handle_vibe_request(
            request=request,
            command="version",
            plan_prompt_func=version_plan_prompt,
            output_flags=output_flags,
            summary_prompt_func=version_prompt,
        )
        logger.info("Completed 'version' command for vibe request.")
        return result

    # Standard kubectl version - add --output=json if not present
    version_args = list(args)
    if "--output=json" not in version_args:
        version_args.append("--output=json")

    logger.info("Handling standard 'version' command.")
    result = await handle_standard_command(
        command="version",
        resource="",  # version doesn't take a resource parameter
        args=tuple(version_args),
        output_flags=output_flags,
        summary_prompt_func=version_prompt,
    )
    logger.info("Completed 'version' command.")
    return result
