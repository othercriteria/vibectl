from vibectl.command_handler import (
    configure_output_flags,
    handle_command_output,
    run_kubectl,
)
from vibectl.console import console_manager
from vibectl.execution.vibe import handle_vibe_request
from vibectl.logutil import logger
from vibectl.memory import configure_memory_flags
from vibectl.prompts.create import create_plan_prompt, create_resource_prompt
from vibectl.types import Error, Result, Success


async def run_create_command(
    resource: str,
    args: tuple[str, ...],
    show_vibe: bool | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
) -> Result:
    """
    Implements the 'create' subcommand logic, including vibe handling and
    error handling. Returns a Result (Success or Error).
    """
    logger.info(f"Invoking 'create' subcommand with resource: {resource}, args: {args}")
    try:
        # Configure outputs
        output_flags = configure_output_flags(
            show_vibe=show_vibe,
        )
        # Configure memory flags
        configure_memory_flags(freeze_memory, unfreeze_memory)

        # Handle vibe command
        if resource == "vibe":
            if not args:
                console_manager.print_error(
                    "Missing request after 'vibe'. Usage: vibectl create vibe <request>"
                )
                return Error(
                    error="Missing request after 'vibe'. "
                    "Usage: vibectl create vibe <request>"
                )

            request = " ".join(args)
            logger.info("Planning how to: create %s", request)
            try:
                result = await handle_vibe_request(
                    request=request,
                    command="create",
                    plan_prompt_func=create_plan_prompt,
                    summary_prompt_func=create_resource_prompt,
                    output_flags=output_flags,
                )
                return result
            except Exception as e:
                logger.error("Error in handle_vibe_request: %s", e, exc_info=True)
                return Error(error="Exception in handle_vibe_request", exception=e)

        # Regular create command
        output = run_kubectl(["create", resource, *list(args)])

        if isinstance(output, Error):
            return output

        if output.data is None:
            return Success(message="No output from kubectl create command.")

        try:
            # Ensure handle_command_output is called with the Result object directly
            await handle_command_output(
                output=output,
                output_flags=output_flags,
                summary_prompt_func=create_resource_prompt,
            )
        except Exception as e:
            logger.error("Exception in handle_command_output: %s", e, exc_info=True)
            return Error(error="Exception in handle_command_output", exception=e)

        return Success(
            message=f"Completed 'create' subcommand for resource: {resource}"
        )

    except Exception as e:
        logger.error("Exception running kubectl: %s", e, exc_info=True)
        return Error(error="Exception running kubectl", exception=e)
