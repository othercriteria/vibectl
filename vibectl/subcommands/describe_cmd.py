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
from vibectl.types import Error, Result


async def run_describe_command(
    resource: str,
    args: tuple[str, ...],
    show_vibe: bool | None = None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
) -> Result:
    """Executes the describe command logic."""

    logger.info(
        f"Invoking 'describe' subcommand with resource: {resource}, args: {args}"
    )

    output_flags = configure_output_flags(
        show_vibe=show_vibe,
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
