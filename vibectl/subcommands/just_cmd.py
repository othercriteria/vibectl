import subprocess

from vibectl.config import Config
from vibectl.console import console_manager
from vibectl.logutil import logger
from vibectl.types import Error, Result, Success


def run_just_command(args: tuple) -> Result:
    """
    Pass commands directly to kubectl. Returns Success or Error.
    Handles kubeconfig and errors on no arguments.
    """
    logger.info(f"Invoking 'just' subcommand with args: {args}")
    if not args:
        msg = "Usage: vibectl just <kubectl commands>"
        console_manager.print_error(msg)
        logger.error("No arguments provided to 'just' subcommand.")
        return Error(error=msg)
    try:
        cmd = ["kubectl"]
        cfg = Config()
        kubeconfig = cfg.get("kubeconfig")
        if kubeconfig:
            cmd.extend(["--kubeconfig", str(kubeconfig)])
        cmd.extend(args)
        logger.info(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=True, text=True, capture_output=True)
        if result.stdout:
            console_manager.print_raw(result.stdout)
        if result.stderr:
            console_manager.print_error(result.stderr)
        logger.info("'just' subcommand completed successfully.")
        return Success(message="kubectl command executed successfully.")
    except FileNotFoundError:
        msg = "kubectl not found in PATH"
        console_manager.print_error(msg)
        logger.error(msg)
        return Error(error=msg)
    except subprocess.CalledProcessError as e:
        if e.stderr:
            console_manager.print_error(f"Error: {e.stderr}")
            logger.error(f"kubectl error: {e.stderr}")
        else:
            console_manager.print_error(
                f"Error: Command failed with exit code {e.returncode}"
            )
            logger.error(f"kubectl failed with exit code {e.returncode}")
        return Error(
            error=(
                f"kubectl failed with exit code {getattr(e, 'returncode', 'unknown')}"
            )
        )
    except Exception as e:
        console_manager.print_error(f"Error: {e!s}")
        logger.error(f"Unexpected error in 'just' subcommand: {e!s}")
        return Error(error="Exception in 'just' subcommand", exception=e)
