import asyncio

from vibectl.command_handler import (
    configure_output_flags,
    handle_command_output,
    run_kubectl,
)
from vibectl.console import console_manager
from vibectl.execution.vibe import handle_vibe_request
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
    show_metrics: bool | None = None,
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
            show_metrics=show_metrics,
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
                    plan_prompt_func=lambda: PLAN_VERSION_PROMPT,
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
        cmd = ["version", *args]  # Prefer json for structured output
        if "--output=json" not in args:
            cmd.append("--output=json")
        logger.info(f"Running kubectl command: {' '.join(cmd)}")

        try:
            # Run kubectl version in a separate thread to avoid blocking asyncio loop
            output = await asyncio.to_thread(run_kubectl, cmd)

            if isinstance(output, Error):
                return output

            if not output.data:
                logger.info("No output from kubectl version.")
                return Success(message="No output from kubectl version.")

            await asyncio.to_thread(
                handle_command_output,
                output=output,  # Pass the Success object
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
