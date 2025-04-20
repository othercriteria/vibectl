"""
Command handler module for vibectl.

Provides reusable patterns for command handling and execution
to reduce duplication across CLI commands.

Note: All exceptions should propagate to the CLI entry point for centralized error
handling. Do not print or log user-facing errors here; use logging for diagnostics only.
"""

import asyncio
import random
import re
import subprocess
import time
from collections.abc import Callable
from contextlib import suppress

import click
import yaml
from rich.progress import (
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from .config import (
    DEFAULT_CONFIG,
    Config,
)
from .console import console_manager
from .logutil import logger as _logger
from .memory import update_memory
from .model_adapter import get_model_adapter
from .output_processor import OutputProcessor
from .prompt import (
    port_forward_prompt,
    recovery_prompt,
    wait_resource_prompt,
)
from .proxy import (
    StatsProtocol,
    TcpProxy,
    start_proxy_server,
    stop_proxy_server,
)
from .types import OutputFlags

logger = _logger

# Export Table for testing
__all__ = ["Table"]

# Constants for output flags
# (DEFAULT_MODEL, DEFAULT_SHOW_RAW_OUTPUT, DEFAULT_SHOW_VIBE,
#  DEFAULT_WARN_NO_OUTPUT, DEFAULT_SHOW_KUBECTL)
# Use values from config.py's DEFAULT_CONFIG instead

# Initialize output processor
output_processor = OutputProcessor()


def run_kubectl(
    cmd: list[str], capture: bool = False, config: Config | None = None
) -> str | None:
    """Run kubectl command and capture output.

    Args:
        cmd: List of command arguments
        capture: Whether to capture and return output
        config: Optional Config instance to use

    Returns:
        Command output if capture=True, None otherwise
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
            raise RuntimeError(error_message)

        # Return output if capturing
        if capture:
            logger.debug(f"kubectl command output: {result.stdout.strip()}")
            return result.stdout.strip()
        return None
    except FileNotFoundError:
        logger.debug("kubectl not found. Please install it and try again.")
        raise FileNotFoundError(
            "kubectl not found. Please install it and try again."
        ) from None
    except Exception as e:
        logger.debug(f"Exception running kubectl: {e}", exc_info=True)
        raise e from None


def handle_standard_command(
    command: str,
    resource: str,
    args: tuple,
    output_flags: OutputFlags,
    summary_prompt_func: Callable[[], str],
) -> None:
    """Handle a standard kubectl command with both raw and vibe output."""
    try:
        logger.info(f"Handling standard command: {command} {resource} {' '.join(args)}")
        # Build command list
        cmd_args = [command, resource]
        if args:
            cmd_args.extend(args)

        output = run_kubectl(cmd_args, capture=True)

        if not output:
            logger.info(
                f"No output from command: {command} {resource} {' '.join(args)}"
            )
            return

        # Handle the output display based on the configured flags
        handle_command_output(
            output=output,
            output_flags=output_flags,
            summary_prompt_func=summary_prompt_func,
            command=f"{command} {resource} {' '.join(args)}",
        )
        logger.info(
            f"Completed standard command: {command} {resource} {' '.join(args)}"
        )
    except Exception as e:
        logger.error(
            "Error handling standard command: %s %s %s: %s",
            command,
            resource,
            " ".join(args),
            e,
        )
        # Let exception propagate to CLI entry point for centralized handling
        raise


def handle_command_output(
    output: str,
    output_flags: OutputFlags,
    summary_prompt_func: Callable[[], str],
    max_token_limit: int = 10000,
    truncation_ratio: int = 3,
    command: str | None = None,
) -> None:
    """Handle displaying command output in both raw and vibe formats.

    Args:
        output: The command output to display
        output_flags: Configuration for output display
        summary_prompt_func: Function returning the prompt template for summarizing
        max_token_limit: Maximum number of tokens for the prompt
        truncation_ratio: Ratio for truncating the output
        command: Optional command string that generated the output
    """
    logger.debug(f"Handling command output for: {command}")
    # Show the kubectl command if requested
    if output_flags.show_kubectl and command:
        console_manager.print_note(f"[kubectl] {command}")
    # Show warning if no output will be shown and warning is enabled
    if (
        not output_flags.show_raw
        and not output_flags.show_vibe
        and output_flags.warn_no_output
    ):
        logger.warning("No output will be shown due to output flags.")
        console_manager.print_no_output_warning()

    # Show raw output if requested
    if output_flags.show_raw:
        logger.debug("Showing raw output.")
        console_manager.print_raw(output)

    # Show vibe output if requested
    vibe_output = ""
    if output_flags.show_vibe:
        try:
            logger.debug("Processing output for vibe summary.")
            # Process output to avoid token limits
            processed_output, was_truncated = output_processor.process_auto(output)

            # Show truncation warning if needed
            if was_truncated:
                logger.warning("Output was truncated for processing.")
                console_manager.print_truncation_warning()

            # Get summary from LLM with processed output using model adapter
            model_adapter = get_model_adapter()
            model = model_adapter.get_model(output_flags.model_name)
            summary_prompt = summary_prompt_func()
            prompt = (
                summary_prompt.format(output=processed_output, command=command)
                if command
                else summary_prompt.format(output=processed_output)
            )
            logger.debug(f"Sending prompt to model: {prompt[:100]}...")
            vibe_output = model_adapter.execute(model, prompt)

            # Update memory if we have a command, regardless of vibe output
            if command:
                update_memory(command, output, vibe_output, output_flags.model_name)

            # Check for empty response
            if not vibe_output:
                logger.info("Vibe output is empty.")
                console_manager.print_empty_output_message()
                return

            # Check for error response
            if vibe_output.startswith("ERROR:"):
                error_message = vibe_output[7:].strip()  # Remove "ERROR: " prefix
                logger.error(f"Vibe model returned error: {error_message}")
                raise ValueError(error_message)

            # If raw output was also shown, add a newline to separate
            if output_flags.show_raw:
                console_manager.console.print()

            # Display the summary
            logger.debug("Displaying vibe summary output.")
            console_manager.print_vibe(vibe_output)
        except Exception as e:
            logger.error(f"Error in vibe output processing: {e}")
            # Let exception propagate to CLI entry point for centralized handling
            raise


def handle_vibe_request(
    request: str,
    command: str,
    plan_prompt: str,
    summary_prompt_func: Callable[[], str],
    output_flags: OutputFlags,
    yes: bool = False,  # Add parameter to control confirmation bypass
    autonomous_mode: bool = False,  # Add parameter for autonomous mode
    live_display: bool = True,  # Add parameter for live display
    memory_context: str = "",  # Add parameter for memory context
) -> None:
    """Handle a request to execute a kubectl command based on a natural language query.

    Args:
        request: Natural language request from the user
        command: Command type (get, describe, etc.)
        plan_prompt: LLM prompt template for planning the kubectl command
        summary_prompt_func: Function that returns the LLM prompt for summarizing
        output_flags: Output configuration flags
        yes: Whether to bypass confirmation prompts
        autonomous_mode: Whether this is operating in autonomous mode
        live_display: Whether to use live display for commands like port-forward
        memory_context: Memory context to include in the prompt (for vibe mode)

    Returns:
        None
    """
    try:
        logger.info(
            f"Planning kubectl command for request: '{request}' (command: {command})"
        )
        model_adapter = get_model_adapter()
        model = model_adapter.get_model(output_flags.model_name)

        # Prepare the format parameters
        format_params = {"request": request, "command": command}
        if memory_context:
            format_params["memory_context"] = memory_context

        # Use a more robust way to format the prompt that handles both
        # positional and named formats
        try:
            # First, check if there are any positional format specifiers in the prompt
            import re

            positional_formats = re.findall(r"{(\d+)}", plan_prompt)

            if positional_formats:
                # If positional formats exist, we need to use string replacement
                # for all parameters
                # to avoid the "Replacement index X out of range" error
                logger.info(
                    "Detected positional format specifiers in prompt, "
                    "using string replacement"
                )
                formatted_prompt = plan_prompt

                # First replace all named parameters
                if "memory_context" in plan_prompt:
                    formatted_prompt = formatted_prompt.replace(
                        "{memory_context}", memory_context
                    )
                formatted_prompt = formatted_prompt.replace("{request}", request)
                formatted_prompt = formatted_prompt.replace("{command}", command)

                # Then handle any remaining positional parameters by replacing
                # them with empty strings
                # This ensures the prompt is usable even with positional parameters
                for pos in positional_formats:
                    formatted_prompt = formatted_prompt.replace(f"{{{pos}}}", "")
            else:
                # No positional formats, use normal keyword formatting
                formatted_prompt = plan_prompt.format(**format_params)

        except (KeyError, IndexError) as e:
            # Fallback to string replacement as a last resort
            logger.warning(
                f"Format error ({e}) in prompt. Using fallback formatting method."
            )
            # Use string replacement as a fallback to avoid format conflicts
            formatted_prompt = plan_prompt
            if "memory_context" in plan_prompt:
                formatted_prompt = formatted_prompt.replace(
                    "{memory_context}", memory_context
                )
            formatted_prompt = formatted_prompt.replace("{request}", request).replace(
                "{command}", command
            )

            # Replace any remaining format specifiers with empty strings
            import re

            formatted_prompt = re.sub(r"{(\d+)}", "", formatted_prompt)

        kubectl_cmd = model_adapter.execute(model, formatted_prompt)

        if not kubectl_cmd:
            logger.error(
                "No kubectl command could be generated for request: '%s'", request
            )
            console_manager.print_error("No kubectl command could be generated.")
            return

        if kubectl_cmd.startswith("ERROR:"):
            error_message = kubectl_cmd[7:].strip()
            logger.error("LLM planning error: %s", error_message)
            command_for_output = f"{command} vibe {request}"
            error_output = f"Error: {error_message}"
            update_memory(
                command=command_for_output,
                command_output=error_output,
                vibe_output=kubectl_cmd,
                model_name=output_flags.model_name,
            )
            console_manager.print_note("Planning error added to memory context")
            console_manager.print_error(kubectl_cmd)
            return

        # Rest of the function remains unchanged
        logger.debug(f"Processing planned command string: {kubectl_cmd}")
        try:
            cmd_args, yaml_content = _process_command_string(kubectl_cmd)
            args = _parse_command_args(cmd_args)
            display_cmd = _create_display_command(args, yaml_content)
        except ValueError as ve:
            logger.error("Command parsing error: %s", ve, exc_info=True)
            console_manager.print_error(f"Command parsing error: {ve}")
            return

        needs_confirm = _needs_confirmation(command, autonomous_mode) and not yes
        should_strip_command = autonomous_mode and command == "vibe"
        cmd_for_display = command if not should_strip_command else ""

        if output_flags.show_kubectl or needs_confirm:
            logger.info(f"Planned kubectl command: {cmd_for_display} {display_cmd}")
            if should_strip_command:
                console_manager.print_note(f"Planning to run: kubectl {display_cmd}")
            else:
                console_manager.print_note(
                    f"Planning to run: kubectl {cmd_for_display} {display_cmd}"
                )

        if needs_confirm and not click.confirm("Execute this command?"):
            logger.info(
                "User cancelled execution of planned command: %s %s",
                cmd_for_display,
                display_cmd,
            )
            console_manager.print_cancelled()
            return

        if command == "port-forward" and live_display and len(args) >= 1:
            logger.info(f"Handling port-forward with live display: {args}")
            resource = args[0]
            port_args = args[1:] if len(args) > 1 else ()
            handle_port_forward_with_live_display(
                resource=resource,
                args=tuple(port_args),
                output_flags=output_flags,
            )
            return

        cmd_to_execute = [command, *args] if not should_strip_command else args
        logger.info(
            f"Executing kubectl command: {cmd_to_execute} (yaml: {bool(yaml_content)})"
        )
        try:
            output = _execute_command(cmd_to_execute, yaml_content)
        except Exception as cmd_error:
            logger.error("Command execution error: %s", cmd_error, exc_info=True)
            error_message = f"Command execution error: {cmd_error}"
            console_manager.print_error(error_message)
            output = f"Error: {cmd_error}"
            try:
                prompt = recovery_prompt(display_cmd, str(cmd_error))
                recovery_suggestions = model_adapter.execute(model, prompt)
                logger.info(
                    "Recovery suggestions added to memory context for error: %s",
                    cmd_error,
                )
                console_manager.print_note(
                    "Recovery suggestions added to memory context"
                )
                output += f"\n\nRecovery suggestions:\n{recovery_suggestions}"
            except Exception as rec_e:
                logger.warning(
                    "Failed to generate recovery suggestions: %s",
                    rec_e,
                    exc_info=True,
                )
            command_for_output = (
                f"{cmd_for_display} {display_cmd}" if cmd_for_display else display_cmd
            )
            handle_command_output(
                output=output,
                output_flags=output_flags,
                summary_prompt_func=summary_prompt_func,
                command=command_for_output,
            )
            return

        if not output:
            logger.info(
                "Command returned no output: %s %s", cmd_for_display, display_cmd
            )
            console_manager.print_note("Command returned no output")

        command_for_output = (
            f"{cmd_for_display} {display_cmd}" if cmd_for_display else display_cmd
        )
        handle_command_output(
            output=output or "No resources found.",
            output_flags=output_flags,
            summary_prompt_func=summary_prompt_func,
            command=command_for_output,
        )
    except Exception as e:
        logger.error("Unexpected error in handle_vibe_request: %s", e, exc_info=True)
        console_manager.print_error(f"Error: {e}")
        if "kubectl" in str(e).lower() or "command" in str(e).lower():
            logger.info(
                "Likely kubectl command error, suggesting user try raw command."
            )
            console_manager.print_note(
                "This appears to be a kubectl command error. "
                "You can try rephrasing your request or using 'vibectl just' "
                "to run raw kubectl commands directly."
            )
        # Let exception propagate to CLI entry point for centralized handling
        raise


def _process_command_string(kubectl_cmd: str) -> tuple[str, str | None]:
    """Process the command string to extract YAML content and command arguments.

    Args:
        kubectl_cmd: The command string from the model

    Returns:
        Tuple of (command arguments, YAML content or None)
    """
    # Check for heredoc syntax (create -f - << EOF)
    if " << EOF" in kubectl_cmd or " <<EOF" in kubectl_cmd:
        # Find the start of the heredoc
        if " << EOF" in kubectl_cmd:
            cmd_parts = kubectl_cmd.split(" << EOF", 1)
        else:
            cmd_parts = kubectl_cmd.split(" <<EOF", 1)

        cmd_args = cmd_parts[0].strip()
        yaml_content = None

        # If there's content after the heredoc marker, treat it as YAML
        if len(cmd_parts) > 1:
            yaml_content = cmd_parts[1].strip()
            # Remove trailing EOF if present
            if yaml_content.endswith("EOF"):
                yaml_content = yaml_content[:-3].strip()

        return cmd_args, yaml_content

    # Check for YAML content separated by --- (common in kubectl manifests)
    cmd_parts = kubectl_cmd.split("---", 1)
    cmd_args = cmd_parts[0].strip()
    yaml_content = None
    if len(cmd_parts) > 1:
        yaml_content = "---" + cmd_parts[1]

    return cmd_args, yaml_content


def _parse_command_args(cmd_args: str) -> list[str]:
    """Parse command arguments into a list.

    Args:
        cmd_args: The command arguments string

    Returns:
        List of command arguments
    """
    import shlex

    # Use shlex to properly handle quoted arguments
    try:
        # This preserves quotes and handles spaces in arguments properly
        args = shlex.split(cmd_args)
    except ValueError:
        # Fall back to simple splitting if shlex fails (e.g., unbalanced quotes)
        args = cmd_args.split()

    return args


def _filter_kubeconfig_flags(args: list[str]) -> list[str]:
    """Filter out kubeconfig flags from the command arguments.

    This is a stub function left for backward compatibility.

    Args:
        args: List of command arguments

    Returns:
        The same list of arguments unchanged
    """
    return args


def _create_display_command(args: list[str], yaml_content: str | None) -> str:
    """Create a display-friendly command string.

    Args:
        args: List of command arguments
        yaml_content: YAML content if present

    Returns:
        Display-friendly command string
    """
    import shlex

    # Reconstruct the command for display
    if yaml_content:
        # For commands with YAML, show a simplified version
        if args and args[0] == "create":
            # For create, we show that it's using a YAML file
            return f"{' '.join(args)} (with YAML content)"
        else:
            # For other commands, standard format with YAML note
            return f"{' '.join(args)} -f (YAML content)"
    else:
        # For standard commands without YAML, quote arguments with spaces/chars
        display_args = []
        for arg in args:
            # Check if the argument needs quoting
            chars = "\"'<>|&;()"
            has_space = " " in arg
            has_special = any(c in arg for c in chars)
            if has_space or has_special:
                # Use shlex.quote to properly quote the argument
                display_args.append(shlex.quote(arg))
            else:
                display_args.append(arg)
        return " ".join(display_args)


def _needs_confirmation(command: str, autonomous_mode: bool) -> bool:
    """Determine if this command requires confirmation.

    Args:
        command: The kubectl command type
        autonomous_mode: Whether we're in autonomous mode

    Returns:
        True if confirmation is needed, False otherwise
    """
    dangerous_commands = [
        "delete",
        "scale",
        "rollout",
        "patch",
        "apply",
        "replace",
        "create",
    ]
    return command in dangerous_commands or (autonomous_mode and command != "get")


def _execute_command(args: list[str], yaml_content: str | None) -> str:
    """Execute the kubectl command with the given arguments.

    Args:
        args: List of command arguments
        yaml_content: YAML content if present

    Returns:
        Output of the command
    """
    if yaml_content:
        return _execute_yaml_command(args, yaml_content)
    else:
        # Check if any arguments contain spaces or special characters
        has_complex_args = any(" " in arg or "<" in arg or ">" in arg for arg in args)

        if has_complex_args:
            # Use direct subprocess execution with preserved argument structure
            return _execute_command_with_complex_args(args)
        else:
            # Regular command without complex arguments
            cmd_output = run_kubectl(args, capture=True)
            return "" if cmd_output is None else cmd_output


def _execute_command_with_complex_args(args: list[str]) -> str:
    """Execute a kubectl command with complex arguments that need special handling.

    Args:
        args: List of command arguments

    Returns:
        Output of the command
    """
    import subprocess

    # Build the full command to preserve argument structure
    cmd = ["kubectl"]

    # Add each argument, preserving structure that might have spaces or special chars
    for arg in args:
        cmd.append(arg)

    console_manager.print_processing(f"Running: {' '.join(cmd)}")

    # Run the command, preserving the argument structure
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        if e.stderr:
            console_manager.print_error(e.stderr)
            return f"Error: {e.stderr}"
        return f"Error: Command failed with exit code {e.returncode}"


def _execute_yaml_command(args: list[str], yaml_content: str) -> str:
    """Execute a kubectl command with YAML content.

    Args:
        args: List of command arguments
        yaml_content: YAML content to be written to a file

    Returns:
        Output of the command
    """
    import re
    import subprocess
    import tempfile

    # Fix multi-document YAML formatting issues
    # Ensure document separators are at the beginning of lines with no indentation
    # This addresses "mapping values are not allowed in this context" errors
    yaml_content = re.sub(r"^(\s+)---\s*$", "---", yaml_content, flags=re.MULTILINE)

    # Ensure each document starts with --- including the first one if it doesn't already
    if not yaml_content.lstrip().startswith("---"):
        yaml_content = "---\n" + yaml_content

    # Check if this is a stdin pipe command (kubectl ... -f -)
    is_stdin_command = False
    for i, arg in enumerate(args):
        if arg == "-f" and i + 1 < len(args) and args[i + 1] == "-":
            is_stdin_command = True
            break

    if is_stdin_command:
        # For commands like kubectl create -f -, use Popen with stdin
        cmd = ["kubectl", *args]
        console_manager.print_processing(f"Running: {' '.join(cmd)}")

        # Use bytes mode for Popen to avoid encoding issues
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,  # Use bytes mode
        )

        # Encode the YAML content to bytes
        yaml_bytes = yaml_content.encode("utf-8")
        stdout_bytes, stderr_bytes = process.communicate(input=yaml_bytes)

        # Decode the output back to strings
        stdout = stdout_bytes.decode("utf-8")
        stderr = stderr_bytes.decode("utf-8")

        if process.returncode != 0:
            raise RuntimeError(
                stderr or f"Command failed with exit code {process.returncode}"
            )

        return stdout
    else:
        # For other commands, use a temporary file as before
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as temp:
            temp.write(yaml_content)
            temp_path = temp.name

        try:
            # For create commands that might be using --from-literal or similar flags
            # just pass the arguments as is and add the -f flag
            cmd = ["kubectl", *args]

            # Only add -f if we have YAML content and it's not already in the args
            if yaml_content and not any(
                arg == "-f" or arg.startswith("-f=") for arg in args
            ):
                cmd.extend(["-f", temp_path])

            console_manager.print_processing(f"Running: {' '.join(cmd)}")
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
            output = proc.stdout
            if proc.returncode != 0:
                raise RuntimeError(
                    proc.stderr or f"Command failed with exit code {proc.returncode}"
                )
            return output
        finally:
            # Clean up the temporary file
            import os

            os.unlink(temp_path)


def configure_output_flags(
    show_raw_output: bool | None = None,
    yaml: bool | None = None,
    json: bool | None = None,
    vibe: bool | None = None,
    show_vibe: bool | None = None,
    model: str | None = None,
    show_kubectl: bool | None = None,
) -> OutputFlags:
    """Configure output flags based on config.

    Args:
        show_raw_output: Optional override for showing raw output
        yaml: Optional override for showing YAML output
        json: Optional override for showing JSON output
        vibe: Optional override for showing vibe output
        show_vibe: Optional override for showing vibe output
        model: Optional override for LLM model
        show_kubectl: Optional override for showing kubectl commands

    Returns:
        OutputFlags instance containing the configured flags
    """
    config = Config()

    # Use provided values or get from config with defaults
    show_raw = (
        show_raw_output
        if show_raw_output is not None
        else config.get("show_raw_output", DEFAULT_CONFIG["show_raw_output"])
    )

    show_vibe_output = (
        show_vibe
        if show_vibe is not None
        else vibe
        if vibe is not None
        else config.get("show_vibe", DEFAULT_CONFIG["show_vibe"])
    )

    # Get warn_no_output setting - default to True (do warn when no output)
    warn_no_output = config.get("warn_no_output", DEFAULT_CONFIG["warn_no_output"])

    # Get warn_no_proxy setting - default to True (do warn when proxy not configured)
    warn_no_proxy = config.get("warn_no_proxy", True)

    model_name = (
        model if model is not None else config.get("model", DEFAULT_CONFIG["model"])
    )

    # Get show_kubectl setting - default to False
    show_kubectl_commands = (
        show_kubectl
        if show_kubectl is not None
        else config.get("show_kubectl", DEFAULT_CONFIG["show_kubectl"])
    )

    return OutputFlags(
        show_raw=show_raw,
        show_vibe=show_vibe_output,
        warn_no_output=warn_no_output,
        model_name=model_name,
        show_kubectl=show_kubectl_commands,
        warn_no_proxy=warn_no_proxy,
    )


def handle_wait_with_live_display(
    resource: str,
    args: tuple[str, ...],
    output_flags: OutputFlags,
) -> None:
    """Handle wait command with a live spinner and elapsed time display.

    Args:
        resource: Resource to wait for
        args: Command line arguments
        output_flags: Output configuration flags
    """
    # Extract the condition from args for display
    condition = "condition"
    for arg in args:
        if arg.startswith("--for="):
            condition = arg[6:]
            break

    # Create the command for display
    display_text = f"Waiting for {resource} to meet {condition}"

    # Track start time to calculate total duration
    start_time = time.time()

    # This is our async function to run the kubectl wait command
    async def async_run_wait_command() -> str | None:
        """Run kubectl wait command asynchronously."""
        # Build command list
        cmd_args = ["wait", resource]
        if args:
            cmd_args.extend(args)

        # Execute the command in a separate thread to avoid blocking the event loop
        # We use asyncio.to_thread to run the blocking kubectl call in a thread pool
        return await asyncio.to_thread(run_kubectl, cmd_args, capture=True)

    # Create a coroutine to update the progress display continuously
    async def update_progress(task_id: TaskID, progress: Progress) -> None:
        """Update the progress display regularly."""
        try:
            # Keep updating at a frequent interval until cancelled
            while True:
                progress.update(task_id)
                # Very small sleep interval for smoother animation
                # (20-30 updates per second)
                await asyncio.sleep(0.03)
        except asyncio.CancelledError:
            # Handle cancellation gracefully by doing a final update
            progress.update(task_id)
            return

    # Create a more visually appealing progress display
    with Progress(
        SpinnerColumn(),
        TimeElapsedColumn(),
        TextColumn("[bold blue]{task.description}"),
        console=console_manager.console,
        transient=True,
        refresh_per_second=30,  # Higher refresh rate for smoother animation
    ) as progress:
        # Add a wait task
        task_id = progress.add_task(description=display_text, total=None)

        # Define the async main routine that coordinates the wait operation
        async def main() -> str | None:
            """Main async routine that runs the wait command and updates progress."""
            # Start updating the progress display in a separate task
            progress_task = asyncio.create_task(update_progress(task_id, progress))

            # Force at least one update to ensure spinner visibility
            await asyncio.sleep(0.1)

            try:
                # Run the wait command
                result = await async_run_wait_command()

                # Give the progress display time to show completion
                # (avoids abrupt disappearance)
                await asyncio.sleep(0.5)

                # Cancel the progress update task
                if not progress_task.done():
                    progress_task.cancel()
                    # Wait for the task to actually cancel
                    with suppress(asyncio.TimeoutError, asyncio.CancelledError):
                        await asyncio.wait_for(progress_task, timeout=0.5)

                return result
            except Exception as e:
                # Ensure we cancel the progress task on errors
                if not progress_task.done():
                    progress_task.cancel()
                    with suppress(asyncio.TimeoutError, asyncio.CancelledError):
                        await asyncio.wait_for(progress_task, timeout=0.5)

                # Propagate the exception
                raise e

        # Set up loop and run the async code
        result = None
        created_new_loop = False
        loop = None
        wait_success = False  # Track if wait completed successfully

        try:
            # Get or create an event loop in a resilient way
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If we're in a running loop context, create a new one
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    created_new_loop = True
            except RuntimeError:
                # If we can't get a loop, create a new one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                created_new_loop = True

            # Run our main coroutine in the event loop
            result = loop.run_until_complete(main())
            wait_success = True  # Mark as successful if we get here

        except asyncio.CancelledError:
            # Handle user interrupts (like Ctrl+C)
            console_manager.print_note("Wait operation cancelled")
            return

        finally:
            # Clean up the progress display
            progress.stop()

            # If we created a new loop, close it to prevent asyncio warnings
            if created_new_loop and loop is not None:
                loop.close()

    # Calculate elapsed time regardless of output
    elapsed_time = time.time() - start_time

    # Handle the command output if any
    if result:
        # Display success message with duration
        console_manager.console.print(
            f"[bold green]✓[/] Wait completed in [bold]{elapsed_time:.2f}s[/]"
        )

        # Add a small visual separator before the output
        if output_flags.show_raw or output_flags.show_vibe:
            console_manager.console.print()

        handle_command_output(
            output=result,
            output_flags=output_flags,
            summary_prompt_func=wait_resource_prompt,
            command=f"wait {resource} {' '.join(args)}",
        )
    elif wait_success:
        # If wait completed successfully but there's no output to display
        success_message = (
            f"[bold green]✓[/] {resource} now meets condition '[bold]{condition}[/]' "
            f"(completed in [bold]{elapsed_time:.2f}s[/])"
        )
        console_manager.console.print(success_message)

        # Add a small note if no output will be shown
        if not output_flags.show_raw and not output_flags.show_vibe:
            message = (
                "\nNo output display enabled. Use --show-raw-output or "
                "--show-vibe to see details."
            )
            console_manager.console.print(message)
    else:
        # If there was an issue but we didn't raise an exception
        message = (
            f"[bold yellow]![/] Wait operation completed with no result "
            f"after [bold]{elapsed_time:.2f}s[/]"
        )
        console_manager.console.print(message)


class ConnectionStats(StatsProtocol):
    """Track connection statistics for port-forward sessions."""

    def __init__(self) -> None:
        """Initialize connection statistics."""
        self.current_status = "Connecting"  # Current connection status
        self.connections_attempted = 0  # Number of connection attempts
        self.successful_connections = 0  # Number of successful connections
        self.bytes_sent = 0  # Bytes sent through connection
        self.bytes_received = 0  # Bytes received through connection
        self.elapsed_connected_time = 0.0  # Time in seconds connection was active
        self.traffic_monitoring_enabled = False  # Whether traffic stats are available
        self.using_proxy = False  # Whether connection is going through proxy
        self.error_messages: list[str] = []  # List of error messages encountered
        self._last_activity_time = time.time()  # Timestamp of last activity

    @property
    def last_activity(self) -> float:
        """Get the timestamp of the last activity."""
        return self._last_activity_time

    @last_activity.setter
    def last_activity(self, value: float) -> None:
        """Set the timestamp of the last activity."""
        self._last_activity_time = value


def has_port_mapping(port_mapping: str) -> bool:
    """Check if a valid port mapping is provided.

    Args:
        port_mapping: The port mapping string to check

    Returns:
        True if a valid port mapping with format "local:remote" is provided
    """
    return ":" in port_mapping and all(
        part.isdigit() for part in port_mapping.split(":")
    )


def handle_port_forward_with_live_display(
    resource: str,
    args: tuple[str, ...],
    output_flags: OutputFlags,
) -> None:
    """Handle port-forward command with a live display showing connection status
    and ports.

    Args:
        resource: Resource to forward ports for
        args: Command line arguments including port specifications
        output_flags: Output configuration flags
    """
    # Extract port mapping from args for display
    port_mapping = "port"
    for arg in args:
        if ":" in arg and all(part.isdigit() for part in arg.split(":")):
            port_mapping = arg
            break

    # Format local and remote ports for display
    local_port, remote_port = (
        port_mapping.split(":") if ":" in port_mapping else (port_mapping, port_mapping)
    )

    # Create the command for display
    display_text = (
        f"Forwarding {resource} port [bold]{remote_port}[/] "
        f"to localhost:[bold]{local_port}[/]"
    )

    # Track start time for elapsed time display
    start_time = time.time()

    # Create a stats object to track connection information
    stats = ConnectionStats()

    # Check if traffic monitoring is enabled via intermediate port range
    cfg = Config()
    intermediate_port_range = cfg.get("intermediate_port_range")
    use_proxy = False
    proxy_port = None

    # Check if a port mapping was provided (required for proxy)
    has_valid_port_mapping = has_port_mapping(port_mapping)

    if intermediate_port_range and has_valid_port_mapping:
        try:
            # Parse the port range
            min_port, max_port = map(int, intermediate_port_range.split("-"))

            # Get a random port in the range
            proxy_port = random.randint(min_port, max_port)

            # Enable proxy mode
            use_proxy = True
            stats.using_proxy = True
            stats.traffic_monitoring_enabled = True

            console_manager.print_note(
                f"Traffic monitoring enabled via proxy on port {proxy_port}"
            )
        except (ValueError, AttributeError) as e:
            console_manager.print_error(
                f"Invalid intermediate_port_range format: {intermediate_port_range}. "
                f"Expected format: 'min-max'. Error: {e}"
            )
            use_proxy = False
    elif (
        not intermediate_port_range
        and has_valid_port_mapping
        and output_flags.warn_no_proxy
    ):
        # Show warning about missing proxy configuration when port mapping is provided
        console_manager.print_no_proxy_warning()

    # Create a subprocess to run kubectl port-forward
    # We'll use asyncio to manage this process and update the display
    async def run_port_forward() -> asyncio.subprocess.Process:
        """Run the port-forward command and capture output."""
        # Build command list
        cmd_args = ["port-forward", resource]

        # Make sure we have valid args - check for resource pattern first
        args_list = list(args)

        # If using proxy, modify the port mapping argument to use proxy_port
        if use_proxy and proxy_port is not None:
            # Find and replace the port mapping argument
            for i, arg in enumerate(args_list):
                if ":" in arg and all(part.isdigit() for part in arg.split(":")):
                    # Replace with proxy port:remote port
                    args_list[i] = f"{proxy_port}:{remote_port}"
                    break

        # Add remaining arguments
        if args_list:
            cmd_args.extend(args_list)

        # Full kubectl command
        kubectl_cmd = ["kubectl"]

        # Add kubeconfig if set
        kubeconfig = cfg.get("kubeconfig")
        if kubeconfig:
            kubectl_cmd.extend(["--kubeconfig", str(kubeconfig)])

        # Add the port-forward command args
        kubectl_cmd.extend(cmd_args)

        # Create a process to run kubectl port-forward
        # This process will keep running until cancelled
        process = await asyncio.create_subprocess_exec(
            *kubectl_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Increment connection attempts counter
        stats.connections_attempted += 1

        # Return reference to the process
        return process

    # Update the progress display with connection status
    async def update_progress(
        task_id: TaskID,
        progress: Progress,
        process: asyncio.subprocess.Process,
        proxy: TcpProxy | None = None,
    ) -> None:
        """Update the progress display with connection status and data."""
        connected = False
        connection_start_time = None

        try:
            # Keep updating until cancelled
            while True:
                # Check if process has output ready
                if process.stdout:
                    line = await process.stdout.readline()
                    if line:
                        # Got output, update connection status
                        line_str = line.decode("utf-8").strip()
                        if "Forwarding from" in line_str:
                            connected = True
                            stats.current_status = "Connected"
                            stats.successful_connections += 1
                            if connection_start_time is None:
                                connection_start_time = time.time()

                            # Attempt to parse traffic information if available
                            if "traffic" in line_str.lower():
                                stats.traffic_monitoring_enabled = True
                                # Extract bytes sent/received if available
                                # Parsing depends on the output format
                                if "sent" in line_str.lower():
                                    sent_match = re.search(
                                        r"sent (\d+)", line_str.lower()
                                    )
                                    if sent_match:
                                        stats.bytes_sent += int(sent_match.group(1))
                                if "received" in line_str.lower():
                                    received_match = re.search(
                                        r"received (\d+)", line_str.lower()
                                    )
                                    if received_match:
                                        stats.bytes_received += int(
                                            received_match.group(1)
                                        )

                # Update stats from proxy if enabled
                if proxy and connected:
                    # Update stats from the proxy server
                    stats.bytes_sent = proxy.stats.bytes_sent
                    stats.bytes_received = proxy.stats.bytes_received
                    stats.traffic_monitoring_enabled = True

                # Update connection time if connected
                if connected and connection_start_time is not None:
                    stats.elapsed_connected_time = time.time() - connection_start_time

                # Update the description based on connection status
                if connected:
                    if proxy:
                        # Show traffic stats in the description when using proxy
                        bytes_sent = stats.bytes_sent
                        bytes_received = stats.bytes_received
                        progress.update(
                            task_id,
                            description=(
                                f"{display_text} - [green]Connected[/green] "
                                f"([cyan]↑{bytes_sent}B[/] "
                                f"[magenta]↓{bytes_received}B[/])"
                            ),
                        )
                    else:
                        progress.update(
                            task_id,
                            description=f"{display_text} - [green]Connected[/green]",
                        )
                else:
                    # Check if the process is still running
                    if process.returncode is not None:
                        stats.current_status = "Disconnected"
                        progress.update(
                            task_id,
                            description=f"{display_text} - [red]Disconnected[/red]",
                        )
                        break

                    # Still establishing connection
                    progress.update(
                        task_id,
                        description=f"{display_text} - Connecting...",
                    )

                # Small sleep for smooth updates
                await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            # Final update before cancellation
            stats.current_status = "Cancelled"
            progress.update(
                task_id,
                description=f"{display_text} - [yellow]Cancelled[/yellow]",
            )

    # Create progress display
    with Progress(
        SpinnerColumn(),
        TimeElapsedColumn(),
        TextColumn("{task.description}"),
        console=console_manager.console,
        transient=False,  # We want to keep this visible
        refresh_per_second=10,
    ) as progress:
        # Add port-forward task
        task_id = progress.add_task(
            description=f"{display_text} - Starting...", total=None
        )

        # Define the main async routine
        async def main() -> None:
            """Main async routine that runs port-forward and updates progress."""
            proxy = None

            try:
                # Start proxy server if traffic monitoring is enabled
                if use_proxy and proxy_port is not None:
                    proxy = await start_proxy_server(
                        local_port=int(local_port), target_port=proxy_port, stats=stats
                    )

                # Start the port-forward process
                process = await run_port_forward()

                # Start updating the progress display
                progress_task = asyncio.create_task(
                    update_progress(task_id, progress, process, proxy)
                )

                try:
                    # Keep running until user interrupts with Ctrl+C
                    await process.wait()

                    # If we get here, the process completed or errored
                    if process.returncode != 0:
                        # Read error output
                        stderr = await process.stderr.read() if process.stderr else b""
                        error_msg = stderr.decode("utf-8").strip()
                        stats.error_messages.append(error_msg)
                        console_manager.print_error(f"Port-forward error: {error_msg}")

                except asyncio.CancelledError:
                    # User cancelled, terminate the process
                    process.terminate()
                    await process.wait()
                    raise

                finally:
                    # Cancel the progress task
                    if not progress_task.done():
                        progress_task.cancel()
                        with suppress(asyncio.CancelledError):
                            await asyncio.wait_for(progress_task, timeout=0.5)

            finally:
                # Clean up proxy server if it was started
                if proxy:
                    await stop_proxy_server(proxy)

        # Set up event loop and run the async code
        created_new_loop = False
        loop = None

        try:
            # Get or create an event loop
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    created_new_loop = True
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                created_new_loop = True

            # Run the main coroutine
            loop.run_until_complete(main())

        except KeyboardInterrupt:
            # Handle Ctrl+C gracefully
            stats.current_status = "Cancelled (User)"
            console_manager.print_note("\nPort-forward cancelled by user")

        except asyncio.CancelledError:
            # Handle cancellation
            stats.current_status = "Cancelled"
            console_manager.print_note("\nPort-forward cancelled")

        except Exception as e:
            # Handle other errors
            stats.current_status = "Error"
            stats.error_messages.append(str(e))
            console_manager.print_error(f"\nPort-forward error: {e!s}")

        finally:
            # Clean up
            if created_new_loop and loop is not None:
                loop.close()

    # Calculate elapsed time
    elapsed_time = time.time() - start_time

    # Show final message with elapsed time
    console_manager.print_note(
        f"\n[bold]Port-forward session ended after "
        f"[italic]{elapsed_time:.1f}s[/italic][/bold]"
    )

    # Create and display a table with connection statistics
    table = Table(title=f"Port-forward {resource} Connection Summary")

    # Add columns
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    # Add rows with connection statistics
    table.add_row("Status", stats.current_status)
    table.add_row("Resource", resource)
    table.add_row("Port Mapping", f"localhost:{local_port} → {remote_port}")
    table.add_row("Duration", f"{elapsed_time:.1f}s")
    table.add_row("Connected Time", f"{stats.elapsed_connected_time:.1f}s")
    table.add_row("Connection Attempts", str(stats.connections_attempted))
    table.add_row("Successful Connections", str(stats.successful_connections))

    # Add proxy information if enabled
    if stats.using_proxy:
        table.add_row("Traffic Monitoring", "Enabled")
        table.add_row("Proxy Mode", "Active")

    # Add traffic information if available
    if stats.traffic_monitoring_enabled:
        table.add_row("Data Sent", f"{stats.bytes_sent} bytes")
        table.add_row("Data Received", f"{stats.bytes_received} bytes")

    # Add any error messages
    if stats.error_messages:
        table.add_row("Errors", "\n".join(stats.error_messages))

    # Display the table
    console_manager.console.print(table)

    # Prepare forward info for memory
    forward_info = f"Port-forward {resource} {port_mapping} ran for {elapsed_time:.1f}s"

    # Create command string for memory
    command_str = f"port-forward {resource} {' '.join(args)}"

    # If vibe output is enabled, generate a summary using the LLM
    vibe_output = ""
    if output_flags.show_vibe:
        try:
            # Get the prompt function
            summary_prompt_func = port_forward_prompt

            # Get LLM summary of the port-forward session
            model_adapter = get_model_adapter()
            model = model_adapter.get_model(output_flags.model_name)

            # Create detailed info for the prompt
            detailed_info = {
                "resource": resource,
                "port_mapping": port_mapping,
                "local_port": local_port,
                "remote_port": remote_port,
                "duration": f"{elapsed_time:.1f}s",
                "command": command_str,
                "status": stats.current_status,
                "connected_time": f"{stats.elapsed_connected_time:.1f}s",
                "connection_attempts": stats.connections_attempted,
                "successful_connections": stats.successful_connections,
                "traffic_monitoring_enabled": stats.traffic_monitoring_enabled,
                "using_proxy": stats.using_proxy,
                "bytes_sent": stats.bytes_sent,
                "bytes_received": stats.bytes_received,
                "errors": stats.error_messages,
            }

            # Format as YAML for the prompt
            detailed_yaml = yaml.safe_dump(detailed_info, default_flow_style=False)

            # Get the prompt template and format it
            summary_prompt = summary_prompt_func()
            prompt = summary_prompt.format(output=detailed_yaml, command=command_str)

            # Execute the prompt to get a summary
            vibe_output = model_adapter.execute(model, prompt)

            # Display the vibe output
            if vibe_output:
                console_manager.print_vibe(vibe_output)

        except Exception as e:
            # Don't let errors in vibe generation break the command
            console_manager.print_error(f"Error generating summary: {e}")

    # Update memory with the port-forward information
    update_memory(
        command_str,
        forward_info,
        vibe_output,  # Now using the generated vibe output
        output_flags.model_name,
    )
