import asyncio  # Added asyncio import
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
            ).strip()  # Use strict first and strip result
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
    cmd: list[str],
    allowed_exit_codes: tuple[int, ...] = (0,),
    config: Config | None = None,
) -> Result:
    """Run kubectl command and capture output.

    Args:
        cmd: List of command arguments (does not include "kubectl" itself)
        config: Optional Config instance to use.
        allowed_exit_codes: Tuple of exit codes that should be treated as success.

    Returns:
        Success with command output (stdout) and original_exit_code.
        Error with error message on failure (if exit code not in allowed_exit_codes).
    """
    try:
        cfg = config or Config()
        kubeconfig = cfg.get("kubeconfig")
        kubectl_full_cmd = ["kubectl"]  # Renamed to avoid conflict with cmd parameter
        kubectl_full_cmd.extend(cmd)  # cmd is the list of args for kubectl
        if kubeconfig:
            kubectl_full_cmd.extend(["--kubeconfig", str(kubeconfig)])

        display_cmd = " ".join(kubectl_full_cmd)

        logger.info(f"Running kubectl command: {display_cmd}")

        process_result = subprocess.run(
            kubectl_full_cmd,
            capture_output=True,
            check=False,  # We handle exit codes manually
            text=True,
            encoding="utf-8",
        )

        stdout_data = process_result.stdout.strip() if process_result.stdout else ""
        stderr_data = process_result.stderr.strip() if process_result.stderr else ""

        logger.debug(
            f"kubectl command (exit code {process_result.returncode}) "
            f"produced stdout: '{stdout_data[:200]}...'"
            f"produced stderr: '{stderr_data[:200]}...'"
        )

        if process_result.returncode in allowed_exit_codes:
            success_message = (
                f"Command {display_cmd} completed with "
                f"exit code {process_result.returncode}."
            )

            return Success(
                data=stdout_data,
                message=success_message,
                original_exit_code=process_result.returncode,
            )
        else:
            error_content = (
                stderr_data or stdout_data or "Unknown error (no stdout/stderr)"
            )
            error_message = (
                f"Command failed with exit code {process_result.returncode}: "
                f"{error_content}"
            )

            return create_kubectl_error(error_message)

    except FileNotFoundError as e:
        logger.error("kubectl command failed: executable not found.", exc_info=False)
        return Error(
            error="kubectl not found. Please install it and try again.",
            exception=e,
            halt_auto_loop=True,
        )
    except (
        subprocess.CalledProcessError
    ) as e:  # Should not be reached due to check=False
        logger.error(
            f"kubectl command failed unexpectedly (CalledProcessError) "
            f"with exit code {e.returncode}: {e.stderr}",
            exc_info=True,
        )
        return create_kubectl_error(e.stderr or f"CalledProcessError: {e.returncode}")
    except Exception as e:
        logger.error(f"Exception running kubectl: {e}", exc_info=True)
        return Error(error=str(e), exception=e)


def run_kubectl_with_yaml(
    args: list[str],
    yaml_content: str,
    allowed_exit_codes: tuple[int, ...] = (0,),
    config: Config | None = None,
) -> Result:
    """Execute a kubectl command with YAML content via stdin or temp file.

    Args:
        args: List of command arguments (e.g., ['apply', '-f', '-'])
        yaml_content: YAML content string
        allowed_exit_codes: Tuple of exit codes that should be treated as success.
        config: Optional Config instance to use

    Returns:
        Result with Success containing command output or Error with error information
    """
    try:
        # Get a Config instance if not provided
        cfg = config or Config()
        kubeconfig_path = cfg.get("kubeconfig")
        kubectl_executable = cfg.get_typed("kubectl_path", "kubectl")

        # Fix multi-document YAML formatting issues for robustness
        yaml_content = re.sub(r"^(\s+)---\s*$", "---", yaml_content, flags=re.MULTILINE)
        if not yaml_content.lstrip().startswith("---"):
            yaml_content = "---\n" + yaml_content

        # Check if using stdin ('-f -')
        is_stdin_command = any(
            arg == "-f" and i + 1 < len(args) and args[i + 1] == "-"
            for i, arg in enumerate(args)
        )

        full_cmd_list = [kubectl_executable, *args]
        if kubeconfig_path:
            # For consistency with run_kubectl, append it.
            full_cmd_list.extend(["--kubeconfig", str(kubeconfig_path)])

        display_cmd = " ".join(full_cmd_list)

        logger.info(f"Running kubectl command with YAML: {display_cmd}")

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

            if process.returncode not in allowed_exit_codes:
                error_msg = (
                    stderr or f"Command failed with exit code {process.returncode}"
                )
                return create_kubectl_error(error_msg)
            return Success(data=stdout, original_exit_code=process.returncode)
        else:
            # If not using stdin, check if -f <file> was provided alongside YAML content
            if any(arg == "-f" or arg.startswith("-f=") for arg in args):
                return Error(
                    error="Cannot provide both YAML content and a file via -f.",
                    halt_auto_loop=False,  # User input error, likely recoverable
                )

            # Use a temporary file
            temp_path = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".yaml", delete=False
                ) as temp:
                    temp.write(yaml_content)
                    temp_path = temp.name

                # By earlier check, -f <file> isn't present if we reach here,
                # sowe can always add -f <temp_path>
                cmd_to_run = list(
                    full_cmd_list
                )  # Create a copy, already contains kubectl_executable
                cmd_to_run.extend(["-f", temp_path])
                # Note: if kubeconfig_path was added to full_cmd_list,
                # it's already in cmd_to_run here.

                proc = subprocess.run(
                    cmd_to_run, capture_output=True, text=True, check=False
                )

                if proc.returncode not in allowed_exit_codes:
                    error_msg = (
                        proc.stderr.strip()
                        or f"Command failed with exit code {proc.returncode}"
                    )
                    return create_kubectl_error(error_msg)
                return Success(
                    message=f"Ran {display_cmd} with YAML content via {temp_path}.",
                    data=proc.stdout.strip(),
                    original_exit_code=proc.returncode,
                )
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


async def create_async_kubectl_process(
    cmd_args: list[str],
    capture_stdout: bool = True,
    capture_stderr: bool = True,
    config: Config | None = None,
) -> asyncio.subprocess.Process:
    """Creates an asyncio subprocess for a kubectl command.

    Args:
        cmd_args: List of kubectl command arguments (e.g., ['get', 'pods', '--watch']).
        capture_stdout: Whether to capture stdout (defaults to True).
        capture_stderr: Whether to capture stderr (defaults to True).
        config: Optional Config instance to use.

    Returns:
        An asyncio.subprocess.Process instance.

    Raises:
        FileNotFoundError: If kubectl is not found.
        Exception: For other errors during process creation.
    """
    cfg = config or Config()
    kubeconfig = cfg.get("kubeconfig")

    kubectl_cmd = ["kubectl"]
    if kubeconfig:
        # Prepend kubeconfig args if they exist, as they often need to come early
        kubectl_cmd.extend(["--kubeconfig", str(kubeconfig)])

    kubectl_cmd.extend(cmd_args)

    logger.info(f"Creating async kubectl process: {' '.join(kubectl_cmd)}")

    try:
        process = await asyncio.create_subprocess_exec(
            *kubectl_cmd,
            stdout=asyncio.subprocess.PIPE if capture_stdout else None,
            stderr=asyncio.subprocess.PIPE if capture_stderr else None,
        )
        return process
    except FileNotFoundError as e:
        logger.error("kubectl command not found.")
        # Re-raise specific error for clarity
        raise FileNotFoundError("kubectl not found. Please install it.") from e
    except Exception as e:
        logger.error(f"Error creating async kubectl process: {e}", exc_info=True)
        # Re-raise other exceptions
        raise e


READ_ONLY_KUBECTL_VERBS = (
    "get",
    "describe",
    "logs",
    "api-versions",
    "api-resources",
    "top",
    "cluster-info",
    "diff",  # diff is read-only, though it might contact the server for live state.
    "explain",
    "auth",  # Specifically "auth can-i" is read-only.
    "version",
    "proxy",  # proxy itself doesn't change state, but what's done *through* it can.
    # For planner, assume LLM won't plan to start a proxy and
    # then do mutations through it.
)


def is_kubectl_command_read_only(command_parts: list[str]) -> bool:
    """
    Checks if the given kubectl command (verb + args) is read-only.
    This is a basic check based on the verb.

    Args:
        command_parts: The kubectl command split into parts (e.g.,
        ["get", "pods", "-n", "default"])

    Returns:
        True if the command is considered read-only, False otherwise.
    """
    if not command_parts:
        return False  # Or raise error, an empty command is not valid.

    verb = command_parts[0].lower()

    if verb in READ_ONLY_KUBECTL_VERBS:
        # Special case for "auth": only "auth can-i" is truly read-only by default.
        # Other "auth" subcommands might not be.
        if verb == "auth":
            if len(command_parts) > 1 and command_parts[1].lower() == "can-i":
                return True
            # "auth whoami" could also be considered read-only, but "can-i"
            # is the primary safe one.
            # For now, be conservative for other "auth" subcommands.
            logger.warning(
                f"Allowing 'auth' verb without 'can-i': {command_parts}. "
                "Review for safety."
            )
            return True  # Temporarily allowing other 'auth' for now, should be refined.
        return True

    return False
