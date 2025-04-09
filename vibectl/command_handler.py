"""
Command handler module for vibectl.

Provides reusable patterns for command handling and execution
to reduce duplication across CLI commands.
"""

import os
import subprocess
import sys
from collections.abc import Callable

import llm

from .config import Config
from .console import console_manager
from .memory import include_memory_in_prompt, update_memory
from .output_processor import OutputProcessor
from .utils import handle_exception

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
    show_raw_output: bool,
    show_vibe: bool,
    model_name: str,
    summary_prompt_func: Callable[[], str],
    warn_no_output: bool = True,
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
            show_raw_output=show_raw_output,
            show_vibe=show_vibe,
            model_name=model_name,
            summary_prompt_func=summary_prompt_func,
            command=f"{command} {resource} {' '.join(args)}",
            warn_no_output=warn_no_output,
        )
    except Exception as e:
        # Use centralized error handling
        handle_exception(e)


def handle_command_output(
    output: str,
    show_raw_output: bool,
    show_vibe: bool,
    model_name: str,
    summary_prompt_func: Callable[[], str],
    max_token_limit: int = 10000,
    truncation_ratio: int = 3,
    command: str | None = None,
    warn_no_output: bool = True,
) -> None:
    """Handle displaying command output in both raw and vibe formats."""
    # Show warning if no output will be shown and warning is enabled
    if not show_raw_output and not show_vibe and warn_no_output:
        console_manager.print_no_output_warning()

    # Show raw output if requested
    if show_raw_output:
        console_manager.print_raw(output)

    # Show vibe output if requested
    vibe_output = ""
    if show_vibe:
        try:
            # Process output to avoid token limits
            processed_output, was_truncated = output_processor.process_auto(output)

            # Show truncation warning if needed
            if was_truncated:
                console_manager.print_truncation_warning()

            # Get summary from LLM with processed output
            llm_model = llm.get_model(model_name)
            summary_prompt = summary_prompt_func()
            prompt = summary_prompt.format(output=processed_output)
            response = llm_model.prompt(prompt)
            summary = response.text() if hasattr(response, "text") else str(response)
            vibe_output = summary

            # If raw output was also shown, add a newline to separate
            if show_raw_output:
                console_manager.console.print()

            # Display the summary
            console_manager.print_vibe(vibe_output)

            # Update memory if we have a command and vibe output
            if command and vibe_output:
                update_memory(command, output, vibe_output, model_name)
        except Exception as e:
            handle_exception(e, exit_on_error=False)


def handle_vibe_request(
    request: str,
    command: str,
    plan_prompt: str,
    summary_prompt_func: Callable[[], str],
    show_raw_output: bool = False,
    show_vibe: bool = True,
    model_name: str = "claude-3.7-sonnet",
    warn_no_output: bool = True,
    yes: bool = False,  # Add parameter to control confirmation bypass
    autonomous_mode: bool = False,  # Add parameter for autonomous mode
) -> None:
    """Handle a vibe request by planning and executing a kubectl command.

    Args:
        request: The natural language request to process
        command: The kubectl command (get, describe, logs, etc.)
        plan_prompt: The prompt template for planning the command
        summary_prompt_func: Function that returns the prompt template for summarizing
        show_raw_output: Whether to display raw kubectl output
        show_vibe: Whether to display the vibe check summary
        model_name: The LLM model to use
        warn_no_output: Whether to warn when no output will be shown
        yes: Whether to skip confirmation prompt (for non-interactive use)
        autonomous_mode: Whether operating in autonomous vibe mode
    """
    try:
        # Track if we've already shown a no-output warning
        already_warned = False

        # Get the plan from LLM
        llm_model = llm.get_model(model_name)

        # Format prompt with request, including memory if available
        if autonomous_mode:
            # Plan prompt is already fully formatted for autonomous mode
            prompt_with_memory = plan_prompt
        else:
            # Format prompt with request for standard commands
            prompt_with_memory = include_memory_in_prompt(
                lambda: plan_prompt.format(request=request)
            )

        response = llm_model.prompt(prompt_with_memory)
        plan = response.text() if hasattr(response, "text") else str(response)

        # Check for error responses from planner
        if not plan or len(plan.strip()) == 0:
            handle_exception(Exception("Invalid response format from planner"))
            return

        # Check for error prefix in the response
        if plan.startswith("ERROR:"):
            error_message = plan[7:].strip()  # Remove "ERROR: " prefix
            handle_exception(Exception(error_message))
            return

        # For autonomous mode, handle direct kubectl commands
        if autonomous_mode:
            lines = plan.split("\n")
            kubectl_cmd = lines[0].strip()

            # Check if it starts with kubectl
            if not kubectl_cmd.startswith("kubectl "):
                handle_exception(
                    Exception("Invalid command format, expected kubectl command")
                )
                return

            # Extract note if provided
            note = None
            if len(lines) > 1 and lines[1].strip().startswith("NOTE:"):
                note = lines[1].strip()[5:].strip()  # Remove "NOTE: " prefix

            # Remove "kubectl" from the command
            kubectl_args = kubectl_cmd.split()[1:]

            # Show the plan and note if available
            console_manager.print("[bold blue]Planned action:[/bold blue]")
            console_manager.print(f"[bold]{kubectl_cmd}[/bold]")
            if note:
                console_manager.print(f"[italic]{note}[/italic]")

            # For all commands, ask for confirmation unless yes flag is provided
            if not yes:
                import click

                if not click.confirm(
                    "Do you want to execute this command?", default=True
                ):
                    console_manager.print_cancelled()
                    return

            # Execute the command
            console_manager.print_processing("Executing command...")
            output = run_kubectl(kubectl_args, capture=True)

            # Check if output contains error information
            is_error = output and output.startswith("Error:")

            if not output:
                # Create special message for empty output
                empty_output_message = "No resources found."
                console_manager.print_note(
                    "Command executed successfully with no output"
                )

                # Update memory with the empty output information
                if show_vibe:
                    try:
                        # Generate interpretation for empty output
                        llm_model = llm.get_model(model_name)
                        summary_prompt = summary_prompt_func()
                        prompt = summary_prompt.format(
                            output=f"Command returned no output: {kubectl_cmd}"
                        )
                        response = llm_model.prompt(prompt)
                        vibe_output = (
                            response.text()
                            if hasattr(response, "text")
                            else str(response)
                        )

                        # Update memory with empty result context
                        update_memory(
                            kubectl_cmd, empty_output_message, vibe_output, model_name
                        )
                    except Exception as e:
                        handle_exception(e, exit_on_error=False)
                return

            # For error outputs in autonomous mode, ensure they're displayed
            if is_error and show_raw_output is False:
                console_manager.print_raw(output)

            # Handle the output display
            handle_command_output(
                output=output,
                show_raw_output=show_raw_output,
                show_vibe=show_vibe,
                model_name=model_name,
                summary_prompt_func=summary_prompt_func,
                command=kubectl_cmd,
                warn_no_output=warn_no_output and not already_warned,
            )
            return

        # Standard (non-autonomous) mode handling below:
        # Extract kubectl command from plan
        kubectl_args = []
        yaml_content = ""
        has_yaml_section = False
        found_delimiter = False

        # Parse the output from the LLM, handling both arguments and YAML manifest
        # if present
        for line in plan.split("\n"):
            if line == "---":
                found_delimiter = True
                has_yaml_section = True
                continue

            if found_delimiter:
                yaml_content += line + "\n"
            else:
                kubectl_args.append(line)

        # Validate plan format
        if not kubectl_args and not has_yaml_section:
            handle_exception(Exception("Invalid response format from planner"))
            return

        # Show warning only if we're not going to execute a command that produces output
        # (which would trigger handle_command_output later)
        if not show_raw_output and not show_vibe and warn_no_output:
            console_manager.print_no_output_warning()
            already_warned = True

        # For delete commands, ask for confirmation unless yes flag is provided
        if command == "delete" and not yes:
            import click

            # Show what will be executed
            cmd_str = f"kubectl {command} {' '.join(kubectl_args)}"
            console_manager.print("[bold yellow]About to execute:[/bold yellow]")
            console_manager.print(f"[bold]{cmd_str}[/bold]")

            # NOTE: We use a separate styled warning message before the plain text
            # confirmation prompt because click.confirm() displays formatting tags
            # as raw text when trying to use Rich formatting directly. A better
            # solution would be to use the Rich library's prompt features or to
            # create a custom click confirmation handler
            if not click.confirm(
                "Do you want to execute this delete command?", default=False
            ):
                console_manager.print_cancelled()
                return

        # Check if we have a YAML input creation
        if has_yaml_section and command == "create":
            # Create a temporary file for YAML content
            import tempfile

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", delete=False
            ) as f:
                f.write(yaml_content)
                yaml_file = f.name

            try:
                # Build kubectl command with -f flag and additional args
                cmd = [command, "-f", yaml_file]
                if kubectl_args:
                    cmd.extend(kubectl_args)

                # Execute the command
                output = run_kubectl(cmd, capture=True)

                # Remove the temporary file
                os.unlink(yaml_file)

                if not output:
                    return

                # Check for errors
                is_error = output and output.startswith("Error:")
                if is_error and show_raw_output is False:
                    # Force showing raw output for errors to ensure visibility
                    console_manager.print_raw(output)

                # Handle the output display based on the configured flags
                handle_command_output(
                    output=output,
                    show_raw_output=show_raw_output,
                    show_vibe=show_vibe,
                    model_name=model_name,
                    summary_prompt_func=summary_prompt_func,
                    command=f"{command} -f yaml_content {''.join(kubectl_args)}",
                    warn_no_output=warn_no_output and not already_warned,
                )
            except Exception as e:
                # Make sure to clean up the temp file in case of an error
                os.unlink(yaml_file)
                raise e
        else:
            # Standard command handling (not create with YAML)
            try:
                output = run_kubectl([command, *kubectl_args], capture=True)
            except Exception as e:
                handle_exception(e)
                return

            # If no output, nothing to do
            if not output:
                return

            # Check if output contains error information and ensure it's displayed
            is_error = output.startswith("Error:")
            if is_error and show_raw_output is False:
                # Force showing raw output for errors to ensure visibility
                console_manager.print_raw(output)

            # Handle the output display based on the configured flags
            try:
                handle_command_output(
                    output=output,
                    show_raw_output=show_raw_output,
                    show_vibe=show_vibe,
                    model_name=model_name,
                    summary_prompt_func=summary_prompt_func,
                    command=f"{command} {' '.join(kubectl_args)}",
                    warn_no_output=warn_no_output and not already_warned,
                )
            except (
                Exception
            ) as e:  # pragma: no cover - error handling for command output processing
                handle_exception(e, exit_on_error=False)
    except Exception as e:
        handle_exception(e)


def configure_output_flags(
    show_raw_output: bool | None = None,
    yaml: bool | None = None,
    json: bool | None = None,
    vibe: bool | None = None,
    show_vibe: bool | None = None,
    model: str | None = None,
) -> tuple[bool, bool, bool, str]:
    """Configure output flags based on config.

    Args:
        show_raw_output: Optional override for showing raw output
        yaml: Optional override for showing YAML output
        json: Optional override for showing JSON output
        vibe: Optional override for showing vibe output
        show_vibe: Optional override for showing vibe output
        model: Optional override for LLM model

    Returns:
        Tuple of (show_raw, show_vibe, warn_no_output, model_name)
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

    return show_raw, show_vibe_output, warn_no_output, model_name


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
    show_raw, show_vibe_output, warn_no_output, model_name = configure_output_flags(
        show_raw_output, yaml, json, vibe, show_vibe, model
    )

    # Run the command
    output = run_kubectl(cmd, capture=True, config=config)

    # Ensure we have a string
    if output is None:
        output = ""

    return output, show_vibe_output
