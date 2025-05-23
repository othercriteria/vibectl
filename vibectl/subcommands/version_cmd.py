import asyncio

from vibectl.command_handler import (
    configure_output_flags,
    handle_command_output,
)
from vibectl.config import Config
from vibectl.console import console_manager
from vibectl.execution.vibe import handle_vibe_request
from vibectl.k8s_utils import run_kubectl
from vibectl.logutil import logger
from vibectl.memory import configure_memory_flags
from vibectl.prompt import PLAN_VERSION_PROMPT, version_prompt
from vibectl.types import Error, Result, Success


async def run_version_command(
    args: tuple[str, ...],
    show_raw_output: bool | None,
    show_vibe: bool | None,
    model: str | None,
    freeze_memory: bool,
    unfreeze_memory: bool,
    show_kubectl: bool | None,
    show_metrics: bool | None,
    show_streaming: bool | None,
) -> Result:
    """
    Implements the 'version' subcommand logic, including logging and error handling.
    Returns a Result (Success or Error).
    Aligns with patterns from diff_cmd.py.
    """
    logger.info(f"Invoking 'version' subcommand with args: {args}")

    # Restore local flag configuration and Config instantiation
    configure_memory_flags(freeze_memory, unfreeze_memory)
    output_flags = configure_output_flags(
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        model=model,
        show_kubectl=show_kubectl,
        show_metrics=show_metrics,
        show_streaming=show_streaming,
    )
    config = Config()  # Restored Config instantiation

    result: Result

    if args and args[0] == "vibe":
        if len(args) < 2:
            logger.debug("[Vibe Path] Missing request after 'vibe' command.")
            result = Error(error="Missing request after 'vibe' command.")
        else:
            request = " ".join(args[1:])
            logger.info(f"[Vibe Path] Planning how to get version info for: {request}")
            console_manager.print_processing(
                f"Vibing on how to get version info for: {request}..."
            )
            try:
                result = await handle_vibe_request(
                    request=request,
                    command="version",
                    plan_prompt_func=lambda: PLAN_VERSION_PROMPT,
                    summary_prompt_func=version_prompt,
                    output_flags=output_flags,
                )
                logger.info(
                    "[Vibe Path] Completed 'version' subcommand for vibe request."
                )
            except Exception as e:
                logger.error(
                    "[Vibe Path] Error in handle_vibe_request: %s", e, exc_info=True
                )
                result = Error(error="Exception in handle_vibe_request", exception=e)
    else:
        # Standard version command
        cmd = ["version", *args]
        if "--output=json" not in args:  # Keep this specific logic for version
            cmd.append("--output=json")
        logger.info(f"[Standard Path] Running kubectl command: {' '.join(cmd)}")

        try:
            # Run kubectl version
            kubectl_result = await asyncio.to_thread(
                run_kubectl,
                cmd,
                config=config,  # Use locally defined config
            )

            if isinstance(kubectl_result, Error):
                logger.error(
                    f"[Standard Path] Error from run_kubectl: {kubectl_result.error}"
                )
                result = kubectl_result  # Propagate the Error object
            elif not kubectl_result.data:
                logger.info("[Standard Path] No output from kubectl version.")
                result = Success(message="No output from kubectl version.")
            else:
                logger.debug(
                    "[Standard Path] run_kubectl returned Success, data: "
                    f"{kubectl_result.data!r}"
                )
                result = await handle_command_output(
                    output=kubectl_result,
                    output_flags=output_flags,
                    summary_prompt_func=version_prompt,
                    command="version",
                )
            logger.info(
                "[Standard Path] Completed direct 'version' subcommand execution."
            )
        except Exception as e:
            logger.error(
                "[Standard Path] Error processing kubectl version: %s", e, exc_info=True
            )
            result = Error(error="Exception processing kubectl version", exception=e)

    return result
