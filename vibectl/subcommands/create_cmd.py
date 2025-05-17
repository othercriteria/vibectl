from vibectl.command_handler import (
    configure_output_flags,
    handle_command_output,
    run_kubectl,
)
from vibectl.logutil import logger
from vibectl.memory import (
    configure_memory_flags,
)
from vibectl.prompt import (
    create_resource_prompt,
)
from vibectl.types import Error, Result, Success


def run_create_command(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    show_kubectl: bool | None,
    model: str | None,
    freeze_memory: bool,
    unfreeze_memory: bool,
    show_metrics: bool | None,
) -> Result:
    """
    Implements the 'create' subcommand logic, including logging and error handling.
    Returns a Result (Success or Error).
    """
    logger.info(f"Invoking 'create' subcommand with resource: {resource}, args: {args}")
    try:
        output_flags = configure_output_flags(
            show_raw_output=show_raw_output,
            show_vibe=show_vibe,
            model=model,
            show_kubectl=show_kubectl,
            show_metrics=show_metrics,
        )
        configure_memory_flags(freeze_memory, unfreeze_memory)

        # Regular create command
        cmd = ["create", resource, *args]
        logger.info(f"Running kubectl command: {' '.join(cmd)}")
        try:
            output = run_kubectl(cmd)
        except Exception as e:
            logger.error("Error running kubectl: %s", e, exc_info=True)
            return Error(error="Exception running kubectl", exception=e)

        if isinstance(output, Success) and not output.data:
            logger.info("No output from kubectl create command.")
            return Success(message="No output from kubectl create command.")

        try:
            # Ensure handle_command_output is called with the Result object directly
            handle_command_output(
                output=output,
                output_flags=output_flags,
                summary_prompt_func=create_resource_prompt,
            )
        except Exception as e:
            logger.error("Error in handle_command_output: %s", e, exc_info=True)
            return Error(error="Exception in handle_command_output", exception=e)

        logger.info(f"Completed 'create' subcommand for resource: {resource}")
        return Success(
            message=f"Completed 'create' subcommand for resource: {resource}"
        )
    except Exception as e:
        logger.error("Error in 'create' subcommand: %s", e, exc_info=True)
        return Error(error="Exception in 'create' subcommand", exception=e)
