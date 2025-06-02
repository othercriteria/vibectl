from vibectl.command_handler import (
    configure_output_flags,
    handle_standard_command,
)
from vibectl.execution.vibe import handle_vibe_request
from vibectl.logutil import logger
from vibectl.memory import configure_memory_flags
from vibectl.prompts.patch import (
    patch_plan_prompt,
    patch_resource_prompt,
)
from vibectl.types import Error, MetricsDisplayMode, Result


async def run_patch_command(
    resource: str,
    args: tuple[str, ...],
    show_raw_output: bool | None,
    show_vibe: bool | None,
    show_kubectl: bool | None,
    model: str | None,
    freeze_memory: bool,
    unfreeze_memory: bool,
    show_metrics: MetricsDisplayMode | None,
    show_streaming: bool | None,
) -> Result:
    """Executes the patch command logic."""

    logger.info(f"Invoking 'patch' subcommand with resource: {resource}, args: {args}")

    output_flags = configure_output_flags(
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        model=model,
        show_kubectl=show_kubectl,
        show_metrics=show_metrics,
        show_streaming=show_streaming,
    )
    configure_memory_flags(freeze_memory, unfreeze_memory)

    # Handle vibe request for natural language patch descriptions
    if resource == "vibe":
        if not args:
            return Error(
                error="Missing request after 'vibe' command. "
                "Please provide a natural language patch description, e.g.: "
                'vibectl patch vibe "scale nginx deployment to 5 replicas"'
            )

        request = " ".join(args)
        logger.info(f"Planning patch operation: {request}")

        result = await handle_vibe_request(
            request=request,
            command="patch",
            plan_prompt_func=patch_plan_prompt,
            output_flags=output_flags,
            summary_prompt_func=patch_resource_prompt,
        )
        logger.info("Completed 'patch' command for vibe request.")
        return result

    # Standard kubectl patch
    logger.info("Handling standard 'patch' command.")
    result = await handle_standard_command(
        command="patch",
        resource=resource,
        args=args,
        output_flags=output_flags,
        summary_prompt_func=patch_resource_prompt,
    )
    logger.info(f"Completed 'patch' command for resource: {resource}")
    return result
