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
        request: The natural language request
        command: The kubectl command type (get, describe, etc.)
        plan_prompt: The prompt template for planning
        summary_prompt_func: Function that provides the prompt for summarizing output
        output_flags: Configuration for output display
        yes: Whether to bypass confirmation prompts
        autonomous_mode: Whether we're in autonomous mode
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

        # Process the command to extract YAML content and command arguments
        cmd_args, yaml_content = _process_command_string(kubectl_cmd)

        # Process the arguments into a properly structured command
        args = _process_command_args(cmd_args, command)

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
        output = _execute_command(args, yaml_content)

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
        handle_exception(e)


def _process_command_string(kubectl_cmd: str) -> tuple[str, str | None]:
    """Process the command string to extract YAML content and command arguments.

    Args:
        kubectl_cmd: The command string from the model

    Returns:
        Tuple of (command arguments, YAML content or None)
    """
    # Check for YAML content separated by --- (common in kubectl manifests)
    cmd_parts = kubectl_cmd.split("---", 1)
    cmd_args = cmd_parts[0].strip()
    yaml_content = None
    if len(cmd_parts) > 1:
        yaml_content = "---" + cmd_parts[1]

    return cmd_args, yaml_content


def _process_command_args(cmd_args: str, command: str) -> list[str]:
    """Process command arguments into a properly structured list.

    Args:
        cmd_args: The command arguments string
        command: The kubectl command type (get, describe, etc.)

    Returns:
        List of command arguments with kubectl prefix removed and filtered
    """
    # Split into individual arguments
    args = cmd_args.split()

    # Remove 'kubectl' prefix if the model included it
    if args and args[0].lower() == "kubectl":
        args = args[1:]

    # For certain commands, we want to make sure the command verb is the first argument
    # This ensures correct kubectl command structure
    commands_to_normalize = ["get", "describe", "logs", "delete", "scale"]

    # Check if we need to normalize the command and it's not already normalized
    if command in commands_to_normalize and (
        not any(arg == command for arg in args) or args[0] != command
    ):
        # Remove the command if it's somewhere else in the args list
        args = [arg for arg in args if arg != command]
        # Add it at the beginning
        args.insert(0, command)

    # Special case for create command
    if command == "create" and args and args[0] != "create":
        args.insert(0, "create")

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
        Command string for display
    """
    display_cmd = " ".join(args)
    if yaml_content:
        display_cmd = f"{display_cmd} {yaml_content}"
    return display_cmd


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
        # Regular command without YAML
        cmd_output = run_kubectl(args, capture=True)
        return "" if cmd_output is None else cmd_output


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

    # Create a temporary file with the YAML content
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as temp:
        temp.write(yaml_content)
        temp_path = temp.name

    try:
        # For create commands, we need to use the -f flag correctly
        if args[0] == "create":
            # Include args except the command, which is at index [0]
            # Add -f flag for the YAML file
            cmd = ["kubectl", "create"]
            # Add any other args that might have been provided
            if len(args) > 1:
                cmd.extend(args[1:])
            cmd.extend(["-f", temp_path])
        else:
            # For other commands that accept YAML, keep the original args
            # but ensure they don't include -f which will be added separately
            filtered_args = [
                arg for arg in args if arg != "-f" and not arg.startswith("-f=")
            ]
            cmd = ["kubectl", *filtered_args, "-f", temp_path]

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


def handle_command_with_options(
    cmd: list[str],
    show_raw_output: bool | None = None,
    yaml: bool | None = None,
    json: bool | None = None,
    vibe: bool | None = None,
    show_vibe: bool | None = None,
    model: str | None = None,
    show_kubectl: bool | None = None,
    config: Config | None = None,
) -> tuple[str, bool]:
    """Handle command with output options.

    Args:
        cmd: Command to run
        show_raw_output: Whether to show raw output
        yaml: Whether to use yaml output
        json: Whether to use json output
        vibe: Whether to vibe the output
        show_vibe: Whether to show vibe output
        model: Model to use for vibe
        show_kubectl: Whether to show kubectl commands
        config: Config object

    Returns:
        Tuple of output and vibe status
    """
    # Configure output flags
    output_flags = configure_output_flags(
        show_raw_output, yaml, json, vibe, show_vibe, model, show_kubectl
    )

    # Run the command
    output = run_kubectl(cmd, capture=True, config=config)

    # Ensure we have a string
    if output is None:
        output = ""

    return output, output_flags.show_vibe
