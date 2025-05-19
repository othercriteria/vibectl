import asyncio

from vibectl.command_handler import (
    configure_output_flags,
    handle_command_output,
)
from vibectl.execution.vibe import handle_vibe_request
from vibectl.k8s_utils import run_kubectl
from vibectl.logutil import logger
from vibectl.memory import configure_memory_flags
from vibectl.prompt import PLAN_CLUSTER_INFO_PROMPT, cluster_info_prompt
from vibectl.types import Error, Result, Success


async def run_cluster_info_command(
    args: tuple,
    show_raw_output: bool | None = None,
    show_vibe: bool | None = None,
    model: str | None = None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    show_kubectl: bool | None = None,
    show_metrics: bool | None = None,
) -> Result:
    """
    Implements the 'cluster-info' subcommand logic, including logging and error
    handling.
    Returns a Result (Success or Error).
    All config compatibility flags are accepted for future-proofing.
    """
    logger.info(f"Invoking 'cluster-info' subcommand with args: {args}")
    try:
        # Configure output flags
        output_flags = configure_output_flags(
            show_raw_output=show_raw_output,
            show_vibe=show_vibe,
            model=model,
            show_kubectl=show_kubectl,
            show_metrics=show_metrics,
        )
        # Configure memory flags (for consistency, even if not used)
        configure_memory_flags(freeze_memory, unfreeze_memory)

        # Special case for vibe command
        if args and args[0] == "vibe":
            if len(args) < 2:
                msg = (
                    "Missing request after 'vibe' command. "
                    "Please provide a natural language request, e.g.: "
                    'vibectl cluster-info vibe "show all cluster info"'
                )
                return Error(error=msg)
            request = " ".join(args[1:])
            logger.info("Planning how to: get cluster info %s", request)
            try:
                # Capture and return the result of handle_vibe_request
                vibe_result = await handle_vibe_request(
                    request=request,
                    command="cluster-info",
                    plan_prompt_func=lambda: PLAN_CLUSTER_INFO_PROMPT,
                    summary_prompt_func=cluster_info_prompt,
                    output_flags=output_flags,
                )
                return vibe_result  # Return the actual result
            except Exception as e:
                logger.error("Error in handle_vibe_request: %s", e, exc_info=True)
                return Error(error="Exception in handle_vibe_request", exception=e)

        # For standard cluster-info command
        try:
            # Build command list
            cmd_list = ["cluster-info", *args]
            logger.info(f"Running kubectl command: {' '.join(cmd_list)}")

            # Run kubectl and get result (capture is always True in run_kubectl now)
            output = await asyncio.to_thread(run_kubectl, cmd_list)

            # Handle errors from kubectl
            if isinstance(output, Error):
                return output

            # Handle output display based on flags
            await asyncio.to_thread(
                handle_command_output,
                output=output,
                output_flags=output_flags,
                summary_prompt_func=cluster_info_prompt,
            )
        except Exception as e:
            logger.error("Error running kubectl cluster-info: %s", e, exc_info=True)
            return Error(error="Exception running kubectl cluster-info", exception=e)
        logger.info("Completed 'cluster-info' subcommand.")
        return Success(message="Completed 'cluster-info' subcommand.")
    except Exception as e:
        logger.error("Error in 'cluster-info' subcommand: %s", e, exc_info=True)
        return Error(error="Exception in 'cluster-info' subcommand", exception=e)
