from vibectl.command_handler import (
    configure_output_flags,
    handle_standard_command,
)
from vibectl.config import Config
from vibectl.execution.vibe import handle_vibe_request
from vibectl.logutil import logger
from vibectl.memory import configure_memory_flags
from vibectl.prompts.edit import (
    PLAN_EDIT_PROMPT,
    edit_resource_prompt,
)
from vibectl.types import Error, Result


async def run_edit_command(
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
    """Executes the edit command logic."""

    logger.info(f"Invoking 'edit' subcommand with resource: {resource}, args: {args}")

    output_flags = configure_output_flags(
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        model=model,
        show_kubectl=show_kubectl,
        show_metrics=show_metrics,
        show_streaming=show_streaming,
    )
    configure_memory_flags(freeze_memory, unfreeze_memory)

    # Check intelligent_edit config
    cfg = Config()
    intelligent_edit_enabled = cfg.get_typed("intelligent_edit", True)

    # Handle vibe request for natural language edit descriptions
    if resource == "vibe":
        if not args:
            return Error(
                error="Missing request after 'vibe' command. "
                "Please provide a natural language edit description, e.g.: "
                'vibectl edit vibe "nginx deployment liveness and readiness config"'
            )

        request = " ".join(args)
        logger.info(f"Planning edit operation: {request}")

        if intelligent_edit_enabled:
            # TODO: Implement intelligent edit workflow
            logger.info("Intelligent edit enabled - using intelligent workflow")
            # For now, fall back to basic vibe handling
            result = await handle_vibe_request(
                request=request,
                command="edit",
                plan_prompt_func=lambda: PLAN_EDIT_PROMPT,
                output_flags=output_flags,
                summary_prompt_func=edit_resource_prompt,
                semiauto=False,
                config=cfg,
            )
        else:
            # Basic vibe handling without intelligent features
            logger.info("Intelligent edit disabled - using basic vibe workflow")
            result = await handle_vibe_request(
                request=request,
                command="edit",
                plan_prompt_func=lambda: PLAN_EDIT_PROMPT,
                output_flags=output_flags,
                summary_prompt_func=edit_resource_prompt,
                semiauto=False,
                config=cfg,
            )

        logger.info("Completed 'edit' command for vibe request.")
        return result

    # Standard kubectl edit or intelligent edit workflow
    if intelligent_edit_enabled:
        # TODO: Implement intelligent edit workflow for standard resources
        logger.info(
            "Intelligent edit enabled for standard resource - "
            "using intelligent workflow"
        )
        # For now, fall back to standard kubectl edit
        logger.info("Falling back to standard 'edit' command.")
        result = await handle_standard_command(
            command="edit",
            resource=resource,
            args=args,
            output_flags=output_flags,
            summary_prompt_func=edit_resource_prompt,
        )
    else:
        # Standard kubectl edit
        logger.info("Handling standard 'edit' command.")
        result = await handle_standard_command(
            command="edit",
            resource=resource,
            args=args,
            output_flags=output_flags,
            summary_prompt_func=edit_resource_prompt,
        )

    logger.info(f"Completed 'edit' command for resource: {resource}")
    return result
