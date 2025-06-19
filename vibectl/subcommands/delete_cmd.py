from vibectl.command_handler import (
    configure_output_flags,
    handle_standard_command,
)
from vibectl.execution.vibe import handle_vibe_request
from vibectl.logutil import logger
from vibectl.memory import configure_memory_flags
from vibectl.prompts.delete import delete_plan_prompt, delete_resource_prompt
from vibectl.types import Error, Result


async def run_delete_command(
    resource: str,
    args: tuple,
    show_vibe: bool | None = None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
) -> Result:
    """
    Implements the 'delete' subcommand logic, including vibe handling, confirmation,
    and error handling. Returns a Result (Success or Error).
    """
    logger.info(
        f"Invoking 'delete' subcommand for resource: {resource} with args: {args}"
    )
    try:
        # Configure output flags
        output_flags = configure_output_flags(
            show_vibe=show_vibe,
        )
        # Configure memory flags
        configure_memory_flags(freeze_memory, unfreeze_memory)

        # Handle vibe command
        if resource == "vibe":
            if not args:
                msg = (
                    "Missing request after 'vibe' command. "
                    "Please provide a natural language request, e.g.: "
                    'vibectl delete vibe "the nginx deployment in default"'
                )
                return Error(error=msg)
            request = " ".join(args)
            logger.info("Planning how to: delete %s", request)
            try:
                result = await handle_vibe_request(
                    request=request,
                    command="delete",
                    plan_prompt_func=delete_plan_prompt,
                    summary_prompt_func=delete_resource_prompt,
                    output_flags=output_flags,
                )
                return result
            except Exception as e:
                logger.error("Error in handle_vibe_request: %s", e, exc_info=True)
                return Error(error="Exception in handle_vibe_request", exception=e)

        # Handle standard command: run sync function in thread
        try:
            # Use asyncio.to_thread to run the sync function
            result = await handle_standard_command(
                command="delete",
                resource=resource,
                args=args,
                output_flags=output_flags,
                summary_prompt_func=delete_resource_prompt,
            )
        except Exception as e:
            logger.error("Error running standard delete command: %s", e, exc_info=True)
            return Error(error="Exception running standard delete command", exception=e)
        logger.info("Completed 'delete' subcommand.")
        return result
    except Exception as e:
        logger.error("Error in 'delete' subcommand: %s", e, exc_info=True)
        return Error(error="Exception in 'delete' subcommand", exception=e)
