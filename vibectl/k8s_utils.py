import logging
import subprocess

# Assuming these imports are needed based on the function content
from .config import Config
from .types import Error, Result, Success

logger = logging.getLogger(__name__)


# Moved from command_handler.py
def create_kubectl_error(
    error_message: str, exception: Exception | None = None
) -> Error:
    """Create an Error object for kubectl failures, marking certain errors as
    non-halting for auto loops.

    Args:
        error_message: The error message
        exception: Optional exception that caused the error

    Returns:
        Error object with appropriate halt_auto_loop flag set
    """
    # For kubectl server errors (like NotFound, Forbidden, etc.),
    # set halt_auto_loop=False so auto loops can continue
    if "Error from server" in error_message:
        return Error(error=error_message, exception=exception, halt_auto_loop=False)

    # For unknown command errors (usually from malformed LLM output),
    # set halt_auto_loop=False so the auto loop can continue and the LLM can
    # correct itself
    if "unknown command" in error_message.lower():
        return Error(error=error_message, exception=exception, halt_auto_loop=False)

    # For other errors, use the default (halt_auto_loop=True)
    return Error(error=error_message, exception=exception)


def run_kubectl(
    cmd: list[str], capture: bool = False, config: Config | None = None
) -> Result:
    """Run kubectl command and capture output.

    Args:
        cmd: List of command arguments
        capture: Whether to capture and return output
        config: Optional Config instance to use

    Returns:
        Success with command output if capture=True, or None otherwise
        Error with error message on failure
    """
    try:
        # Get a Config instance if not provided
        cfg = config or Config()

        # Get the kubeconfig path from config
        kubeconfig = cfg.get("kubeconfig")

        # Build the full command
        kubectl_cmd = ["kubectl"]

        # Add the command arguments first, to ensure kubeconfig is AFTER the main
        # command
        kubectl_cmd.extend(cmd)

        # Add kubeconfig AFTER the main command to avoid errors
        if kubeconfig:
            kubectl_cmd.extend(["--kubeconfig", str(kubeconfig)])

        logger.info(f"Running kubectl command: {' '.join(kubectl_cmd)}")

        # Execute the command
        result = subprocess.run(
            kubectl_cmd,
            capture_output=capture,
            check=False,
            text=True,
            encoding="utf-8",
        )

        # Check for errors
        if result.returncode != 0:
            error_message = result.stderr.strip() if capture else "Command failed"
            if not error_message:
                error_message = f"Command failed with exit code {result.returncode}"
            logger.debug(f"kubectl command failed: {error_message}")

            # Create error result, potentially marking some as non-halting
            # TODO: Consider moving the actual create_kubectl_error logic here
            return create_kubectl_error(error_message)

        # Return output if capturing
        if capture:
            output = result.stdout.strip()
            logger.debug(f"kubectl command output: {output}")
            return Success(data=output)
        return Success()
    except FileNotFoundError:
        error_msg = "kubectl not found. Please install it and try again."
        logger.debug(error_msg)
        return Error(error=error_msg)
    except Exception as e:
        logger.debug(f"Exception running kubectl: {e}", exc_info=True)
        return Error(error=str(e), exception=e)
