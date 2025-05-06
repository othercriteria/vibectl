import asyncio

from vibectl.command_handler import (
    configure_output_flags,
    handle_command_output,
    handle_vibe_request,
    run_kubectl,
)
from vibectl.console import console_manager
from vibectl.logutil import logger
from vibectl.memory import configure_memory_flags
from vibectl.prompt import PLAN_VERSION_PROMPT, version_prompt
from vibectl.types import Error, Result, Success


async def run_version_command(
    args: tuple,
    show_raw_output: bool | None = None,
    show_vibe: bool | None = None,
    model: str | None = None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    show_kubectl: bool | None = None,
) -> Result:
    """
    Implements the 'version' subcommand logic, including logging and error handling.
    Returns a Result (Success or Error).
    All config compatibility flags are accepted for future-proofing.
    """
    logger.info(f"Invoking 'version' subcommand with args: {args}")
    try:
        # Configure output flags
        output_flags = configure_output_flags(
            show_raw_output=show_raw_output,
            show_vibe=show_vibe,
            model=model,
            show_kubectl=show_kubectl,
        )
        # Configure memory flags (for consistency, even if not used)
        configure_memory_flags(freeze_memory, unfreeze_memory)

        # Check for vibe command
        if args and args[0] == "vibe":
            if len(args) < 2:
                return Error(error="Missing request after 'vibe' command.")
            request = " ".join(args[1:])
            logger.info("Planning how to get version info for: %s", request)
            console_manager.print_processing(
                f"Vibing on how to get version info for: {request}..."
            )
            try:
                # Await the potentially async vibe handler
                result_vibe = await handle_vibe_request(
                    request=request,
                    command="version",
                    plan_prompt=PLAN_VERSION_PROMPT,
                    summary_prompt_func=version_prompt,
                    output_flags=output_flags,
                )
                # Return the result from the handler
                logger.info("Completed 'version' subcommand for vibe request.")
                return result_vibe

            except Exception as e:
                logger.error("Error in handle_vibe_request: %s", e, exc_info=True)
                return Error(error="Exception in handle_vibe_request", exception=e)

        # Standard version command
        cmd = ["version", "--output=json", *args]  # Prefer json for structured output
        logger.info(f"Running kubectl command: {' '.join(cmd)}")

        try:
            # Use asyncio.to_thread for the sync kubectl call
            # run_kubectl returns Result (Success or Error)
            kubectl_result = await asyncio.to_thread(run_kubectl, cmd, capture=True)

            # Handle Error from run_kubectl
            if isinstance(kubectl_result, Error):
                logger.error(f"Error running kubectl: {kubectl_result.error}")
                # Propagate the error object
                return kubectl_result

            # Handle Success from run_kubectl
            output_data = kubectl_result.data

            if not output_data:
                logger.info("No output from kubectl version.")
                # Print note to console as well
                console_manager.print_note("No output from kubectl version.")
                return Success(message="No output from kubectl version.")

            # If we have output_data, process it
            await asyncio.to_thread(
                handle_command_output,
                output=output_data,
                output_flags=output_flags,
                summary_prompt_func=version_prompt,
            )
            logger.info("Completed 'version' subcommand.")
            return Success(message="Completed 'version' subcommand.")
        except Exception as e:
            logger.error("Error running kubectl version: %s", e, exc_info=True)
            return Error(error="Exception running kubectl version", exception=e)
    except Exception as e:
        logger.error("Error in 'version' subcommand: %s", e, exc_info=True)
        return Error(error="Exception in 'version' subcommand", exception=e)
