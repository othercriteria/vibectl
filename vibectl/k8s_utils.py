import logging
import os
import re
import subprocess
import tempfile
from subprocess import TimeoutExpired

# Assuming these imports are needed based on the function content
from .config import Config
from .types import Error, Result, Success

logger = logging.getLogger(__name__)


# Moved from command_handler.py
def create_kubectl_error(
    error_message: str | bytes, exception: Exception | None = None
) -> Error:
    """Create an Error object for kubectl failures, marking certain errors as
    non-halting for auto loops.

    Args:
        error_message: The error message (string or bytes)
        exception: Optional exception that caused the error

    Returns:
        Error object with appropriate halt_auto_loop flag set
    """
    error_str = ""
    if isinstance(error_message, bytes):
        try:
            # Attempt decoding
            error_str = error_message.decode(
                "utf-8", errors="strict"
            )  # Use strict first
        except UnicodeDecodeError as decode_err:  # Catch specific error
            logger.warning(f"Failed to decode error message bytes: {decode_err}")
            # Assign specific fallback message on decoding error
            error_str = "Failed to decode error message from kubectl."
        except Exception as decode_err:
            # Catch other potential exceptions during decode/strip
            logger.warning(
                f"Unexpected error processing error message bytes: {decode_err}"
            )
            error_str = "Unexpected error processing error message from kubectl."
    elif isinstance(error_message, str):
        error_str = error_message.strip()
    else:
        logger.warning(f"Unexpected error message type: {type(error_message)}")
        # Handle non-str/bytes input - treat as halting
        error_type_name = type(error_message).__name__
        error_str = f"Unexpected error message type: {error_type_name}"
        # Directly return halting error for unexpected input types
        return Error(error=error_str, exception=exception, halt_auto_loop=True)

    # Define patterns for recoverable client-side errors
    recoverable_patterns = [
        "error from server",  # Server-side errors (NotFound, etc.)
        "unknown command",  # Completely wrong command
        "unknown flag",  # Invalid flag used
        "invalid argument",  # Invalid argument value or format
        "is invalid:",  # Catch server-side validation errors (like immutable fields)
    ]

    # Check if the error message matches any recoverable pattern (case-insensitive)
    error_lower = error_str.lower()
    is_recoverable = any(pattern in error_lower for pattern in recoverable_patterns)

    if is_recoverable:
        logger.debug(f"Kubectl error identified as recoverable: {error_str}")
        return Error(error=error_str, exception=exception, halt_auto_loop=False)
    else:
        # For other errors, use the default (halt_auto_loop=True)
        logger.debug(f"Kubectl error treated as halting: {error_str}")
        return Error(error=error_str, exception=exception)


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


def run_kubectl_with_complex_args(args: list[str]) -> Result:
    """Execute a kubectl command with complex arguments that need special handling.

    Args:
        args: List of command arguments

    Returns:
        Result with Success containing command output or Error with error information
    """
    try:
        # Build the full command to preserve argument structure
        cmd = ["kubectl"]
        # Add each argument, preserving structure with possible spaces or special chars
        for arg in args:
            cmd.append(arg)

        logger.info(f"Running kubectl command with complex args: {' '.join(cmd)}")
        # Run the command, preserving the argument structure
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return Success(data=result.stdout.strip())
    except subprocess.CalledProcessError as e:
        error_message = (
            e.stderr.strip()
            if e.stderr
            else f"Command failed with exit code {e.returncode}"
        )
        # Use create_kubectl_error for consistent error handling
        return create_kubectl_error(error_message, exception=e)
    except Exception as e:
        logger.error("Error executing command with complex args: %s", e, exc_info=True)
        # General exception, return standard Error
        return Error(error=f"Error executing command: {e}", exception=e)


def run_kubectl_with_yaml(args: list[str], yaml_content: str) -> Result:
    """Execute a kubectl command with YAML content via stdin or temp file.

    Args:
        args: List of command arguments (e.g., ['apply', '-f', '-'])
        yaml_content: YAML content string

    Returns:
        Result with Success containing command output or Error with error information
    """
    try:
        # Fix multi-document YAML formatting issues for robustness
        yaml_content = re.sub(r"^(\s+)---\s*$", "---", yaml_content, flags=re.MULTILINE)
        if not yaml_content.lstrip().startswith("---"):
            yaml_content = "---\n" + yaml_content

        # Check if using stdin ('-f -')
        is_stdin_command = any(
            arg == "-f" and i + 1 < len(args) and args[i + 1] == "-"
            for i, arg in enumerate(args)
        )

        full_cmd_list = ["kubectl", *args]  # Use splat operator
        logger.info(f"Running kubectl command with YAML: {' '.join(full_cmd_list)}")

        if is_stdin_command:
            # Use Popen with stdin pipe
            process = subprocess.Popen(
                full_cmd_list,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,  # Use bytes mode for reliable encoding
            )
            yaml_bytes = yaml_content.encode("utf-8")
            try:
                stdout_bytes, stderr_bytes = process.communicate(
                    input=yaml_bytes, timeout=30
                )
            except TimeoutExpired as e:  # Capture the original exception
                process.kill()
                stdout_bytes, stderr_bytes = process.communicate()
                return Error(
                    error="Command timed out after 30 seconds",
                    exception=e,  # Pass the original TimeoutExpired exception
                )

            stdout = stdout_bytes.decode("utf-8").strip()
            stderr = stderr_bytes.decode("utf-8").strip()

            if process.returncode != 0:
                error_msg = (
                    stderr or f"Command failed with exit code {process.returncode}"
                )
                return create_kubectl_error(error_msg)
            return Success(data=stdout)
        else:
            # Use a temporary file
            temp_path = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".yaml", delete=False
                ) as temp:
                    temp.write(yaml_content)
                    temp_path = temp.name

                # Add -f <temp_path> only if -f is not already present
                cmd_to_run = list(full_cmd_list)  # Create a copy
                if not any(arg == "-f" or arg.startswith("-f=") for arg in cmd_to_run):
                    cmd_to_run.extend(["-f", temp_path])

                proc = subprocess.run(
                    cmd_to_run, capture_output=True, text=True, check=False
                )

                if proc.returncode != 0:
                    error_msg = (
                        proc.stderr.strip()
                        or f"Command failed with exit code {proc.returncode}"
                    )
                    return create_kubectl_error(error_msg)
                return Success(data=proc.stdout.strip())
            finally:
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.unlink(temp_path)
                    except Exception as cleanup_error:
                        logger.warning(
                            f"Failed to clean up temporary file: {cleanup_error}"
                        )
    except Exception as e:
        logger.error("Error executing YAML command: %s", e, exc_info=True)
        return Error(error=f"Error executing YAML command: {e}", exception=e)
