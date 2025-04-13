"""
Command handler module for vibectl.

Provides reusable patterns for command handling and execution
to reduce duplication across CLI commands.
"""

import subprocess
import sys
from collections.abc import Callable

from .config import Config
from .console import console_manager
from .memory import update_memory
from .model_adapter import get_model_adapter
from .output_processor import OutputProcessor
from .prompt import recovery_prompt
from .types import OutputFlags
from .utils import handle_exception

# Constants for output flags
DEFAULT_MODEL = "claude-3.7-sonnet"
DEFAULT_SHOW_RAW_OUTPUT = False
DEFAULT_SHOW_VIBE = True
DEFAULT_WARN_NO_OUTPUT = True
DEFAULT_SHOW_KUBECTL = False

# Initialize output processor
output_processor = OutputProcessor()


def run_kubectl(
    cmd: list[str], capture: bool = False, config: Config | None = None
) -> str | None:
    """Run kubectl command with configured kubeconfig.

    Args:
        cmd: The kubectl command arguments
        capture: Whether to capture and return output
        config: Optional Config instance to use (for testing)
    """
    # Use provided config or create new one
    cfg = config or Config()

    # Start with base command
    full_cmd = ["kubectl"]

    # Add kubeconfig if set
    kubeconfig = cfg.get("kubeconfig")
    if kubeconfig:
        full_cmd.extend(["--kubeconfig", str(kubeconfig)])

    # Add the rest of the command
    full_cmd.extend(cmd)

    # Run command
    try:
        result = subprocess.run(full_cmd, capture_output=True, text=True, check=True)
        if capture:
            return result.stdout
        return None
    except subprocess.CalledProcessError as e:
        if e.stderr:
            print(e.stderr, file=sys.stderr)
        if capture:
            # Return the error message as part of the output so it can be processed
            # by command handlers and included in memory
            return (
                f"Error: {e.stderr}"
                if e.stderr
                else f"Error: Command failed with exit code {e.returncode}"
            )
        return None


def handle_standard_command(
    command: str,
    resource: str,
    args: tuple,
    output_flags: OutputFlags,
    summary_prompt_func: Callable[[], str],
) -> None:
    """Handle a standard kubectl command with both raw and vibe output."""
    try:
        # Build command list
        cmd_args = [command, resource]
        if args:
            cmd_args.extend(args)

        output = run_kubectl(cmd_args, capture=True)

        if not output:
            return

        # Handle the output display based on the configured flags
        handle_command_output(
            output=output,
            output_flags=output_flags,
            summary_prompt_func=summary_prompt_func,
            command=f"{command} {resource} {' '.join(args)}",
        )
    except Exception as e:
        # Use centralized error handling
        handle_exception(e)


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
    # Show warning if no output will be shown and warning is enabled
    if (
        not output_flags.show_raw
        and not output_flags.show_vibe
        and output_flags.warn_no_output
    ):
        console_manager.print_no_output_warning()

    # Show raw output if requested
    if output_flags.show_raw:
        console_manager.print_raw(output)

    # Show vibe output if requested
    vibe_output = ""
    if output_flags.show_vibe:
        try:
            # Process output to avoid token limits
            processed_output, was_truncated = output_processor.process_auto(output)

            # Show truncation warning if needed
            if was_truncated:
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
            vibe_output = model_adapter.execute(model, prompt)

            # Update memory if we have a command, regardless of vibe output
            if command:
                update_memory(command, output, vibe_output, output_flags.model_name)

            # Check for empty response
            if not vibe_output:
                console_manager.print_empty_output_message()
                return

            # Check for error response
            if vibe_output.startswith("ERROR:"):
                error_message = vibe_output[7:].strip()  # Remove "ERROR: " prefix
                raise ValueError(error_message)

            # If raw output was also shown, add a newline to separate
            if output_flags.show_raw:
                console_manager.console.print()

            # Display the summary
            console_manager.print_vibe(vibe_output)
        except Exception as e:
            handle_exception(e, exit_on_error=False)


def handle_vibe_request(
    request: str,
    command: str,
    plan_prompt: str,
    summary_prompt_func: Callable[[], str],
    output_flags: OutputFlags,
    yes: bool = False,  # Add parameter to control confirmation bypass
    autonomous_mode: bool = False,  # Add parameter for autonomous mode
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

    Returns:
        None
    """
    try:
        # Plan the kubectl command based on the request
        model_adapter = get_model_adapter()
        model = model_adapter.get_model(output_flags.model_name)
        kubectl_cmd = model_adapter.execute(
            model, plan_prompt.format(request=request, command=command)
        )

        # Strip any backticks that might be around the command
        kubectl_cmd = kubectl_cmd.strip().strip("`").strip()

        # If no command was generated, inform the user and exit
        if not kubectl_cmd:
            console_manager.print_error("No kubectl command could be generated.")
            return

        # Check if the response is an error message
        if kubectl_cmd.startswith("ERROR:"):
            # Don't try to run the error as a command
            console_manager.print_note(f"Planning to run: kubectl {kubectl_cmd}")
            return

        try:
            # Process the command to extract YAML content and command arguments
            cmd_args, yaml_content = _process_command_string(kubectl_cmd)

            # Convert command string to a list of arguments
            args = _parse_command_args(cmd_args)

            # Create a display command for user feedback
            display_cmd = _create_display_command(args, yaml_content)

            # Check if we need confirmation or if show_kubectl is enabled
            needs_confirm = _needs_confirmation(command, autonomous_mode) and not yes

            # Show command if show_kubectl is True or confirmation needed
            if output_flags.show_kubectl or needs_confirm:
                console_manager.print_note(f"Planning to run: kubectl {display_cmd}")

            # If confirmation needed, ask now
            if needs_confirm:
                import click

                if not click.confirm("Execute this command?"):
                    console_manager.print_cancelled()
                    return

            # Execute the command and get output
            try:
                output = _execute_command(args, yaml_content)
            except Exception as cmd_error:
                # Provide a more helpful error message and recovery suggestions
                error_message = f"Command execution error: {cmd_error}"
                console_manager.print_error(error_message)

                # Capture error for memory update
                output = f"Error: {cmd_error}"

                # Generate recovery suggestions from the model
                try:
                    # Use the recovery_prompt from prompt.py
                    prompt = recovery_prompt(display_cmd, str(cmd_error))
                    recovery_suggestions = model_adapter.execute(model, prompt)
                    console_manager.print_vibe(recovery_suggestions)

                    # Include recovery suggestions in output for memory
                    output += f"\n\nRecovery suggestions:\n{recovery_suggestions}"
                except Exception:
                    # If even the recovery suggestions fail, at least don't crash
                    pass

                # Process the output for memory update (don't return early)
                handle_command_output(
                    output=output,
                    output_flags=output_flags,
                    summary_prompt_func=summary_prompt_func,
                    command=display_cmd,
                )
                return
        except ValueError as ve:
            # Handle command parsing/processing errors explicitly
            console_manager.print_error(f"Command parsing error: {ve}")
            return

        # Handle response - might be empty
        if not output:
            console_manager.print_note("Command returned no output")

        # Process the output regardless
        handle_command_output(
            output=output or "No resources found.",
            output_flags=output_flags,
            summary_prompt_func=summary_prompt_func,
            command=display_cmd,
        )
    except Exception as e:
        # Print error but don't exit the process for non-critical errors
        console_manager.print_error(f"Error: {e}")

        # If this seems to be a command execution error, add more context
        if "kubectl" in str(e).lower() or "command" in str(e).lower():
            console_manager.print_note(
                "This appears to be a kubectl command error. "
                "You can try rephrasing your request or using 'vibectl just' "
                "to run raw kubectl commands directly."
            )

        # Don't call handle_exception which would exit the process


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

    # Remove 'kubectl' prefix if the model included it
    if args and args[0].lower() == "kubectl":
        args = args[1:]

    # Filter out any kubeconfig flags that might be present
    # as they should be handled by run_kubectl, not included directly
    return _filter_kubeconfig_flags(args)


def _filter_kubeconfig_flags(args: list[str]) -> list[str]:
    """Filter out kubeconfig flags from the command arguments.

    Args:
        args: List of command arguments

    Returns:
        Filtered list of arguments without kubeconfig flags
    """
    filtered_args = []
    i = 0
    while i < len(args):
        arg = args[i]
        # Skip --kubeconfig and its value
        if arg == "--kubeconfig" and i < len(args) - 1:
            i += 2  # Skip this flag and its value
            continue
        # Skip --kubeconfig=value style
        if arg.startswith("--kubeconfig="):
            i += 1
            continue
        filtered_args.append(arg)
        i += 1

    return filtered_args


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
            print(e.stderr, file=sys.stderr)
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
    import subprocess
    import tempfile

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
            raise Exception(
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
                raise Exception(
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
        else config.get("show_raw_output", DEFAULT_SHOW_RAW_OUTPUT)
    )

    show_vibe_output = (
        show_vibe
        if show_vibe is not None
        else vibe
        if vibe is not None
        else config.get("show_vibe", DEFAULT_SHOW_VIBE)
    )

    # Get warn_no_output setting - default to True (do warn when no output)
    warn_no_output = config.get("warn_no_output", DEFAULT_WARN_NO_OUTPUT)

    model_name = model if model is not None else config.get("model", DEFAULT_MODEL)

    # Get show_kubectl setting - default to False
    show_kubectl_commands = (
        show_kubectl
        if show_kubectl is not None
        else config.get("show_kubectl", DEFAULT_SHOW_KUBECTL)
    )

    return OutputFlags(
        show_raw=show_raw,
        show_vibe=show_vibe_output,
        warn_no_output=warn_no_output,
        model_name=model_name,
        show_kubectl=show_kubectl_commands,
    )
