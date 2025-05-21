import asyncio

from vibectl.command_handler import (
    configure_output_flags,
    handle_command_output,
    handle_watch_with_live_display,
    run_kubectl,
)
from vibectl.console import console_manager
from vibectl.execution.vibe import handle_vibe_request
from vibectl.logutil import logger
from vibectl.memory import configure_memory_flags
from vibectl.prompt import PLAN_LOGS_PROMPT, logs_prompt
from vibectl.types import Error, Result, Success


async def run_logs_command(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    show_kubectl: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    show_metrics: bool | None = None,
) -> Result:
    """
    Implements the 'logs' subcommand logic, including logging and error handling.
    Returns a Result (Success or Error).
    """
    logger.info(f"Invoking 'logs' subcommand with resource: {resource}, args: {args}")
    try:
        output_flags = configure_output_flags(
            show_raw_output=show_raw_output,
            show_vibe=show_vibe,
            model=model,
            show_kubectl=show_kubectl,
            show_metrics=show_metrics,
        )
        configure_memory_flags(freeze_memory, unfreeze_memory)

        # Special case for vibe command
        if resource == "vibe":
            if not args:
                msg = (
                    "Missing request after 'vibe' command. "
                    "Please provide a natural language request, e.g.: "
                    'vibectl logs vibe "the nginx pod in default"'
                )
                return Error(error=msg)
            request = " ".join(args)
            logger.info("Planning how to: logs %s", request)
            try:
                # Await the potentially async vibe handler
                result_vibe = await handle_vibe_request(
                    request=request,
                    command="logs",
                    plan_prompt_func=lambda: PLAN_LOGS_PROMPT,
                    summary_prompt_func=logs_prompt,
                    output_flags=output_flags,
                )
                # Return result directly if handle_vibe_request provides one
                if isinstance(result_vibe, Error):
                    logger.error(f"Error from handle_vibe_request: {result_vibe.error}")
                    return result_vibe
                # Assuming Success means completion, potentially with message/data
                # Let's return the result from handle_vibe_request
                logger.info("Completed 'logs' subcommand for vibe request.")
                return result_vibe  # Return the actual result

            except Exception as e:
                logger.error("Error in handle_vibe_request: %s", e, exc_info=True)
                return Error(error="Exception in handle_vibe_request", exception=e)

        # Check for --follow or -f flag
        follow_flag_present = "--follow" in args or "-f" in args

        if follow_flag_present:
            logger.info(
                f"Handling 'logs' command for resource '{resource}' with "
                f"--follow flag using live display."
            )
            result = await handle_watch_with_live_display(
                command="logs",
                resource=resource,  # Pod name or resource/name for logs
                args=args,
                output_flags=output_flags,
                summary_prompt_func=logs_prompt,
            )
            if isinstance(result, Error):
                logger.error(
                    f"Error from handle_watch_with_live_display: {result.error}"
                )
                return result
            logger.info(
                f"Completed 'logs --follow' subcommand for resource: {resource}."
            )
            return result

        # Regular logs command (non-streaming)
        logger.info(f"Handling standard 'logs' command for resource: {resource}.")
        cmd = ["logs", resource, *args]
        logger.info(f"Running kubectl command: {' '.join(cmd)}")

        # Run kubectl logs in a separate thread
        result = await asyncio.to_thread(run_kubectl, cmd)

        if isinstance(result, Error):
            error_msg = f"Error running kubectl: {result.error}"
            logger.error(error_msg)
            console_manager.print_error(error_msg)
            return result

        # Extract output from Success result
        output = result.data

        if not output:
            logger.info("No output from kubectl logs command.")
            # Use console_manager if available, otherwise print
            if "console_manager" in globals():
                console_manager.print_note("No output from kubectl logs command.")
            else:
                print("[NOTE] No output from kubectl logs command.")
            return Success(message="No output from kubectl logs command.")

        # handle_command_output will handle truncation warnings and output display
        # Assume handle_command_output might be sync or async
        await asyncio.to_thread(
            handle_command_output,
            output=output,
            output_flags=output_flags,
            summary_prompt_func=logs_prompt,
        )
        logger.info("Completed 'logs' subcommand for resource: %s", resource)
        return Success(message=f"Completed 'logs' subcommand for resource: {resource}")
    except Exception as e:
        logger.error("Error in 'logs' subcommand: %s", e, exc_info=True)
        return Error(error="Exception in 'logs' subcommand", exception=e)
