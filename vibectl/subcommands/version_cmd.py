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
from vibectl.utils import handle_exception


def run_version_command(
    args: tuple,
    show_raw_output: bool | None = None,
    show_vibe: bool | None = None,
    model: str | None = None,
    freeze_memory: bool = False,  # Accept for decorator compatibility
    unfreeze_memory: bool = False,  # Accept for decorator compatibility
    show_kubectl: bool | None = None,  # Accept for decorator compatibility
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

        # Special case for vibe command
        if args and args[0] == "vibe":
            if len(args) < 2:
                msg = "Missing request after 'vibe'"
                console_manager.print_error(msg)
                logger.error(msg + " in version subcommand.")
                return Error(error=msg)
            request = " ".join(args[1:])
            try:
                handle_vibe_request(
                    request=request,
                    command="version",
                    plan_prompt=PLAN_VERSION_PROMPT,
                    summary_prompt_func=version_prompt,
                    output_flags=output_flags,
                )
            except Exception as e:
                logger.error(f"Error in handle_vibe_request: {e}")
                handle_exception(e)
                return Error(error="Exception in handle_vibe_request", exception=e)
            logger.info("Completed 'version' subcommand for vibe request.")
            return Success(message="Completed 'version' subcommand for vibe request.")

        # For standard version command with no args, run kubectl version
        try:
            output = run_kubectl(["version", "--output=json"], capture=True)

            if not output:
                console_manager.print_note("kubectl version information not available")
                logger.info("No output from kubectl version.")
                return Success(message="No output from kubectl version.")

            # Handle output display based on flags
            handle_command_output(
                output=output,
                output_flags=output_flags,
                summary_prompt_func=version_prompt,
            )
        except Exception as e:
            logger.error(f"Error running kubectl version: {e}")
            handle_exception(e)
            return Error(error="Exception running kubectl version", exception=e)
        logger.info("Completed 'version' subcommand.")
        return Success(message="Completed 'version' subcommand.")
    except Exception as e:
        logger.error(f"Error in 'version' subcommand: {e}")
        handle_exception(e)
        return Error(error="Exception in 'version' subcommand", exception=e)
