from vibectl.command_handler import (
    configure_output_flags,
    handle_command_output,
    handle_vibe_request,
    run_kubectl,
)
from vibectl.logutil import logger
from vibectl.memory import (
    configure_memory_flags,
    get_memory,
)
from vibectl.prompt import (
    PLAN_SCALE_PROMPT,
    scale_resource_prompt,
)
from vibectl.types import Error, Result, Success


def run_scale_command(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    show_kubectl: bool | None,
    model: str | None,
    freeze_memory: bool,
    unfreeze_memory: bool,
) -> Result:
    """
    Implements the 'scale' subcommand logic, including logging and error handling.
    Returns a Result (Success or Error).
    """
    logger.info(f"Invoking 'scale' subcommand with resource: {resource}, args: {args}")
    try:
        output_flags = configure_output_flags(
            show_raw_output=show_raw_output,
            show_vibe=show_vibe,
            model=model,
            show_kubectl=show_kubectl,
        )
        configure_memory_flags(freeze_memory, unfreeze_memory)

        if resource == "vibe":
            if len(args) < 1:
                msg = (
                    "Missing request after 'vibe' command. "
                    "Please provide a natural language request, e.g.: "
                    'vibectl scale vibe "the nginx deployment to 3 replicas"'
                )
                return Error(error=msg)
            request = " ".join(args)
            logger.info("Planning how to: scale %s", request)
            try:
                handle_vibe_request(
                    request=request,
                    command="scale",
                    plan_prompt=PLAN_SCALE_PROMPT,
                    summary_prompt_func=scale_resource_prompt,
                    output_flags=output_flags,
                    memory_context=get_memory() or "",
                )
            except Exception as e:
                logger.error("Error in handle_vibe_request: %s", e, exc_info=True)
                return Error(error="Exception in handle_vibe_request", exception=e)
            logger.info("Completed 'scale' subcommand for vibe request.")
            return Success(message="Completed 'scale' subcommand for vibe request.")

        # Regular scale command
        cmd = ["scale", resource, *args]
        logger.info(f"Running kubectl command: {' '.join(cmd)}")
        try:
            output = run_kubectl(cmd, capture=True)
        except Exception as e:
            logger.error("Error running kubectl: %s", e, exc_info=True)
            return Error(error="Exception running kubectl", exception=e)

        if not output:
            logger.info("No output from kubectl scale command.")
            return Success(message="No output from kubectl scale command.")

        try:
            handle_command_output(
                output=output,
                output_flags=output_flags,
                summary_prompt_func=scale_resource_prompt,
            )
        except Exception as e:
            logger.error("Error in handle_command_output: %s", e, exc_info=True)
            return Error(error="Exception in handle_command_output", exception=e)

        logger.info(f"Completed 'scale' subcommand for resource: {resource}")
        return Success(message=f"Completed 'scale' subcommand for resource: {resource}")
    except Exception as e:
        logger.error("Error in 'scale' subcommand: %s", e, exc_info=True)
        return Error(error="Exception in 'scale' subcommand", exception=e)
