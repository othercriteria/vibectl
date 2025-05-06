import asyncio
import subprocess

from vibectl.config import Config
from vibectl.console import console_manager
from vibectl.logutil import logger
from vibectl.types import Error, Result, Success


async def run_just_command(args: tuple) -> Result:
    """
    Pass commands directly to kubectl. Returns Success or Error.
    Handles kubeconfig and errors on no arguments.
    """
    logger.info(f"Invoking 'just' subcommand with args: {args}")
    if not args:
        msg = "Usage: vibectl just <kubectl commands>"
        logger.error("No arguments provided to 'just' subcommand.", exc_info=True)
        return Error(error=msg)
    try:
        cmd = ["kubectl"]
        cfg = Config()
        kubeconfig = cfg.get("kubeconfig")
        if kubeconfig:
            cmd.extend(["--kubeconfig", str(kubeconfig)])
        cmd.extend(args)
        logger.info(f"Running command: {' '.join(cmd)}")
        try:
            result = await asyncio.to_thread(
                subprocess.run, cmd, check=True, text=True, capture_output=True
            )
        except FileNotFoundError as e:
            msg = "kubectl not found in PATH"
            logger.error(msg, exc_info=True)
            return Error(error=msg, exception=e)
        except subprocess.CalledProcessError as e:
            if e.stderr:
                logger.error(f"kubectl error: {e.stderr}", exc_info=True)
            else:
                logger.error(
                    f"kubectl failed with exit code {e.returncode}", exc_info=True
                )
            return Error(
                error=(
                    f"kubectl failed with exit code "
                    f"{getattr(e, 'returncode', 'unknown')}"
                ),
                exception=e,
            )
        except Exception as e:
            logger.error(f"Unexpected error in 'just' subcommand: {e!s}", exc_info=True)
            return Error(error="Exception in 'just' subcommand", exception=e)
        if result.stdout:
            console_manager.print_raw(result.stdout)
        if result.stderr:
            console_manager.print_error(result.stderr)
        logger.info("'just' subcommand completed successfully.")
        return Success(
            message="kubectl command executed successfully.", data=result.stdout
        )
    except Exception as e:
        logger.error(f"Unexpected error in 'just' subcommand: {e!s}", exc_info=True)
        return Error(error="Exception in 'just' subcommand", exception=e)
