"""
Command handler module for vibectl.

Provides reusable patterns for command handling and execution
to reduce duplication across CLI commands.
"""

import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass

from .config import Config
from .console import console_manager
from .memory import update_memory
from .model_adapter import get_model_adapter
from .output_processor import OutputProcessor
from .utils import handle_exception


@dataclass
class OutputFlags:
    """Configuration for output display flags."""

    show_raw: bool
    show_vibe: bool
    warn_no_output: bool
    model_name: str


# Constants for output flags
DEFAULT_MODEL = "claude-3.7-sonnet"
DEFAULT_SHOW_RAW_OUTPUT = False
DEFAULT_SHOW_VIBE = True
DEFAULT_WARN_NO_OUTPUT = True

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

        # Check for YAML content separated by --- (common in kubectl manifests)
        # If present, split on the delimiter and use only the part before for
        # command arguments
        cmd_parts = kubectl_cmd.split("---", 1)
        cmd_args = cmd_parts[0].strip()
        yaml_content = None
        if len(cmd_parts) > 1:
            yaml_content = "---" + cmd_parts[1]

        # Format the command with the correct namespace if not specified
        args = cmd_args.split()

        # Remove 'kubectl' prefix if the model included it
        if args and args[0].lower() == "kubectl":
            args = args[1:]

        # If first arg doesn't include the command type (create, get, etc) and we
        # know the command, insert it at the beginning
        if args and command == "create" and args[0] != "create":
            args.insert(0, "create")

        # If we have YAML content, append it to the command for display
        display_cmd = " ".join(args)
        if yaml_content:
            display_cmd = f"{display_cmd} {yaml_content}"

        # Show the planned command to user
        console_manager.print_note(f"Planning to run: kubectl {display_cmd}")

        # Determine if this is a dangerous command that requires confirmation
        dangerous_commands = [
            "delete",
            "scale",
            "rollout",
            "patch",
            "apply",
            "replace",
            "create",
        ]
        is_dangerous = command in dangerous_commands or (
            autonomous_mode and command != "get"
        )

        # Confirm with user for dangerous commands or in autonomous mode
        # (except get) if not bypassed with --yes
        if is_dangerous and not yes:
            import click

            if not click.confirm("Execute this command?"):
                console_manager.print_cancelled()
                return

        # Execute the command, adding the YAML content if present
        if yaml_content:
            # For commands that accept YAML from stdin, use a proper process
            import subprocess
            import tempfile

            # Create a temporary file with the YAML content
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", delete=False
            ) as temp:
                temp.write(yaml_content)
                temp_path = temp.name

            try:
                # Run kubectl with the file as input
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
                        proc.stderr
                        or f"Command failed with exit code {proc.returncode}"
                    )
            finally:
                # Clean up the temporary file
                import os

                os.unlink(temp_path)
        else:
            # Regular command without YAML
            cmd_output = run_kubectl(args, capture=True)
            output = "" if cmd_output is None else cmd_output

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


def configure_output_flags(
    show_raw_output: bool | None = None,
    yaml: bool | None = None,
    json: bool | None = None,
    vibe: bool | None = None,
    show_vibe: bool | None = None,
    model: str | None = None,
) -> OutputFlags:
    """Configure output flags based on config.

    Args:
        show_raw_output: Optional override for showing raw output
        yaml: Optional override for showing YAML output
        json: Optional override for showing JSON output
        vibe: Optional override for showing vibe output
        show_vibe: Optional override for showing vibe output
        model: Optional override for LLM model

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

    return OutputFlags(
        show_raw=show_raw,
        show_vibe=show_vibe_output,
        warn_no_output=warn_no_output,
        model_name=model_name,
    )


def handle_command_with_options(
    cmd: list[str],
    show_raw_output: bool | None = None,
    yaml: bool | None = None,
    json: bool | None = None,
    vibe: bool | None = None,
    show_vibe: bool | None = None,
    model: str | None = None,
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
        config: Config object

    Returns:
        Tuple of output and vibe status
    """
    # Configure output flags
    output_flags = configure_output_flags(
        show_raw_output, yaml, json, vibe, show_vibe, model
    )

    # Run the command
    output = run_kubectl(cmd, capture=True, config=config)

    # Ensure we have a string
    if output is None:
        output = ""

    return output, output_flags.show_vibe
