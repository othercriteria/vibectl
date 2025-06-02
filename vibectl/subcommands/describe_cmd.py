from vibectl.command_handler import (
    configure_output_flags,
    handle_standard_command,
)
from vibectl.execution.vibe import handle_vibe_request
from vibectl.logutil import logger
from vibectl.memory import configure_memory_flags
from vibectl.prompts.describe import (
    describe_plan_prompt,
    describe_resource_prompt,
)
from vibectl.types import Error, MetricsDisplayMode, Result


async def run_describe_command(
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
    """Executes the describe command logic."""

    logger.info(
        f"Invoking 'describe' subcommand with resource: {resource}, args: {args}"
    )

    output_flags = configure_output_flags(
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        model=model,
        show_kubectl=show_kubectl,
        show_metrics=show_metrics,
        show_streaming=show_streaming,
    )
    configure_memory_flags(freeze_memory, unfreeze_memory)

    # Handle vibe request for natural language describe descriptions
    if resource == "vibe":
        if not args:
            return Error(
                error="Missing request after 'vibe' command. "
                "Please provide a natural language request, e.g.: "
                'vibectl describe vibe "the nginx pod in default"'
            )

        request = " ".join(args)
        logger.info(f"Planning how to describe: {request}")

        result = await handle_vibe_request(
            request=request,
            command="describe",
            plan_prompt_func=describe_plan_prompt,
            output_flags=output_flags,
            summary_prompt_func=describe_resource_prompt,
            semiauto=False,
            config=None,
        )
        logger.info("Completed 'describe' command for vibe request.")
        return result

    # Standard kubectl describe
    logger.info("Handling standard 'describe' command.")
    result = await handle_standard_command(
        command="describe",
        resource=resource,
        args=args,
        output_flags=output_flags,
        summary_prompt_func=describe_resource_prompt,
    )
    logger.info(f"Completed 'describe' command for resource: {resource}")
    return result
