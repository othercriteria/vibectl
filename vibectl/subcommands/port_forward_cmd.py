from vibectl.command_handler import (
    configure_output_flags,
    handle_port_forward_with_live_display,
    handle_standard_command,
)
from vibectl.execution.vibe import handle_vibe_request
from vibectl.logutil import logger
from vibectl.memory import configure_memory_flags
from vibectl.prompt import PLAN_PORT_FORWARD_PROMPT, port_forward_prompt
from vibectl.types import Error, Result


async def run_port_forward_command(
    resource: str,
    args: tuple,
    show_raw_output: bool | None = None,
    show_vibe: bool | None = None,
    show_kubectl: bool | None = None,
    model: str | None = None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    live_display: bool = True,
    show_metrics: bool | None = None,
    exit_on_error: bool = True,
) -> Result:
    """
    Implements the 'port-forward' subcommand logic, including logging and
    error handling.
    Returns a Result (Success or Error).
    """
    logger.info(
        f"Invoking 'port-forward' subcommand with resource: {resource}, args: {args}, "
        f"live_display: {live_display}"
    )
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
            if len(args) < 1:
                msg = "Missing request after 'vibe'"
                return Error(error=msg)
            request = " ".join(args)
            logger.info("Planning how to: port-forward %s", request)

            # Use the Result returned from handle_vibe_request
            result = await handle_vibe_request(
                request=request,
                command="port-forward",
                plan_prompt_func=lambda: PLAN_PORT_FORWARD_PROMPT,
                summary_prompt_func=port_forward_prompt,
                output_flags=output_flags,
                live_display=live_display,
            )
            logger.info("Completed 'port-forward' subcommand for vibe request.")
            return result

        # Handle command with live display
        if live_display:
            logger.info(
                f"Handling port-forward with live display for resource: {resource}"
            )
            result = await handle_port_forward_with_live_display(
                resource=resource,
                args=args,
                output_flags=output_flags,
                summary_prompt_func=port_forward_prompt,
            )
            logger.info(
                f"Completed port-forward with live display for resource: {resource}"
            )
            return result
        else:
            # Standard command without live display
            logger.info(
                f"Handling standard port-forward command for resource: {resource}"
            )
            result = handle_standard_command(
                command="port-forward",
                resource=resource,
                args=args,
                output_flags=output_flags,
                summary_prompt_func=port_forward_prompt,
            )
            logger.info(
                f"Completed standard port-forward command for resource: {resource}"
            )
            return result
    except Exception as e:
        logger.error("Error in 'port-forward' subcommand: %s", e, exc_info=True)
        return Error(error="Exception in 'port-forward' subcommand", exception=e)
