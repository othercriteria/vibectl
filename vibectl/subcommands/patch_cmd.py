import asyncio

from vibectl.command_handler import (
    configure_output_flags,
    handle_command_output,
)
from vibectl.execution.vibe import handle_vibe_request
from vibectl.k8s_utils import run_kubectl
from vibectl.logutil import logger
from vibectl.memory import configure_memory_flags
from vibectl.prompt import (
    PLAN_PATCH_PROMPT,
    patch_resource_prompt,
)
from vibectl.types import Error, Result, Success


async def run_patch_command(
    resource: str,
    args: tuple[str, ...],
    show_raw_output: bool | None,
    show_vibe: bool | None,
    show_kubectl: bool | None,
    model: str | None,
    freeze_memory: bool,
    unfreeze_memory: bool,
    show_metrics: bool | None,
    show_streaming: bool | None,
) -> Result:
    """Executes the patch command logic."""

    logger.info(f"Invoking 'patch' subcommand with resource: {resource}, args: {args}")

    try:
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
            if not args or not isinstance(args[0], str):
                return Error(
                    "Missing request after 'vibe' command. "
                    "Please provide a natural language patch description, e.g.: "
                    'vibectl patch vibe "scale nginx deployment to 5 replicas"'
                )

            request = " ".join(args)
            logger.info(f"Planning patch operation: {request}")

            try:
                vibe_result = await handle_vibe_request(
                    request=request,
                    command="patch",
                    plan_prompt_func=lambda: PLAN_PATCH_PROMPT,
                    output_flags=output_flags,
                    summary_prompt_func=patch_resource_prompt,
                    semiauto=False,
                    config=None,
                )
                logger.info("Completed 'patch' command for vibe request.")
                return vibe_result
            except Exception as e:
                logger.error(
                    "Exception in handle_vibe_request for patch: %s", e, exc_info=True
                )
                return Error(
                    error="Exception processing vibe request for patch", exception=e
                )

        # Standard kubectl patch
        try:
            # Build command list for kubectl patch
            cmd_list = ["patch", resource, *args]
            logger.info(f"Running kubectl command: {' '.join(cmd_list)}")

            # Run kubectl and get result
            output = await asyncio.to_thread(run_kubectl, cmd_list)

            # Handle errors from kubectl
            if isinstance(output, Error):
                return output

            if output.data:
                try:
                    # Process and summarize the output
                    _ = await handle_command_output(
                        output=output,
                        command="patch",
                        output_flags=output_flags,
                        summary_prompt_func=patch_resource_prompt,
                    )
                except Exception as e:
                    logger.error(
                        "Error processing kubectl patch output: %s", e, exc_info=True
                    )
                    return Error(error="Exception processing patch output", exception=e)
            else:
                logger.info("No output from kubectl patch command.")
                return Success(message="No output from kubectl patch command.")

            logger.info(f"Completed 'patch' command for resource: {resource}")
            return Success(
                message=f"Successfully processed patch command for {resource}"
            )

        except Exception as e:
            logger.error("Error running kubectl patch: %s", e, exc_info=True)
            return Error(error="Exception running kubectl patch", exception=e)

    except Exception as e:
        logger.error("Error in 'patch' subcommand: %s", e, exc_info=True)
        return Error(
            error="Exception in 'patch' subcommand",
            exception=e,
        )
