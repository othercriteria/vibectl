"""
Command handler module for vibectl.

Provides reusable patterns for command handling and execution
to reduce duplication across CLI commands.
"""

import subprocess
import sys
from typing import Callable, List, Optional, Tuple

import llm

from .config import Config
from .console import console_manager


def run_kubectl(args: List[str], capture: bool = False) -> Optional[str]:
    """Run kubectl with the given arguments.

    Args:
        args: List of arguments to pass to kubectl
        capture: Whether to capture and return the output (True) or print it (False)

    Returns:
        The command output if capture=True, None otherwise

    Raises:
        subprocess.CalledProcessError: If kubectl returns an error
        FileNotFoundError: If kubectl is not found
    """
    try:
        cmd = ["kubectl"]

        # Add kubeconfig if configured
        cfg = Config()
        kubeconfig = cfg.get("kubeconfig")
        if kubeconfig:
            cmd.extend(["--kubeconfig", kubeconfig])

        # Ensure all arguments are strings
        cmd.extend(str(arg) for arg in args)

        result = subprocess.run(cmd, check=True, text=True, capture_output=True)
        if result.stdout:
            if capture:
                return result.stdout
            # Disable markup and highlighting for kubectl output
            console_manager.print_raw(result.stdout)
        return None
    except subprocess.CalledProcessError as e:
        # Show error directly without "Error:" prefix since kubectl already includes it
        if e.stderr:
            console_manager.error_console.print(e.stderr, end="")
        else:
            console_manager.print_error(f"Command failed with exit code {e.returncode}")
        raise  # Re-raise the original error
    except FileNotFoundError:
        console_manager.print_error("kubectl not found in PATH")
        raise


def handle_standard_command(
    command: str,
    resource: str,
    args: tuple,
    show_raw_output: bool,
    show_vibe: bool,
    model_name: str,
    summary_prompt_func: Callable[[], str],
    namespace: Optional[str] = None,
    container: Optional[str] = None,
    additional_args: Optional[List[str]] = None,
) -> None:
    """Handle a standard kubectl command.

    Args:
        command: The kubectl command (get, describe, logs, etc.)
        resource: The resource type to operate on
        args: Additional arguments for the command
        show_raw_output: Whether to display raw kubectl output
        show_vibe: Whether to display the vibe check summary
        model_name: The LLM model to use
        summary_prompt_func: Function that returns the prompt template for summarizing
        namespace: Optional namespace argument
        container: Optional container argument
        additional_args: Optional list of additional arguments to include
    """
    cmd = [command, resource]

    # Add namespace if provided
    if namespace:
        cmd.extend(["-n", namespace])

    # Add container if provided (for logs command)
    if container:
        cmd.extend(["-c", container])

    # Add any additional arguments
    if additional_args:
        cmd.extend(additional_args)

    # Add remaining arguments
    cmd.extend(args)

    try:
        output = run_kubectl(cmd, capture=True)

        if not output:
            return

        # Handle the output display based on the configured flags
        handle_command_output(
            output=output,
            show_raw_output=show_raw_output,
            show_vibe=show_vibe,
            model_name=model_name,
            summary_prompt_func=summary_prompt_func,
        )
    except subprocess.CalledProcessError:
        # Error is already displayed by run_kubectl
        sys.exit(1)


def handle_command_output(
    output: str,
    show_raw_output: bool,
    show_vibe: bool,
    model_name: str,
    summary_prompt_func: Callable[[], str],
    max_token_limit: int = 10000,
    truncation_ratio: int = 3,
) -> None:
    """Handle displaying command output and optional vibe check.

    Args:
        output: The command output to process
        show_raw_output: Whether to display raw output
        show_vibe: Whether to display the vibe check
        model_name: LLM model to use for vibe check
        summary_prompt_func: Function that returns the prompt template
        max_token_limit: Maximum token limit for LLM input
        truncation_ratio: Ratio for truncating output
    """
    if show_raw_output:
        console_manager.print_raw(output)

    if show_vibe:
        # Process the output to stay within token limits
        llm_output, was_truncated = console_manager.process_output_for_vibe(
            output, max_token_limit, truncation_ratio
        )

        try:
            # Get LLM model
            llm_model = llm.get_model(model_name)

            # Generate the prompt with the processed output
            prompt = summary_prompt_func().format(output=llm_output)

            # Get vibe summary from LLM
            response = llm_model.prompt(prompt)
            summary = response.text() if hasattr(response, "text") else str(response)

            # Add a newline before vibe check if raw output was shown
            if show_raw_output:
                console_manager.console.print()

            # Display the vibe check
            console_manager.print_vibe(summary)
        except Exception as e:
            if "No key found" in str(e):
                console_manager.print_missing_api_key_error()
                sys.exit(1)
            else:
                console_manager.print_note("Could not get vibe check", error=e)


def handle_vibe_request(
    request: str,
    command: str,
    plan_prompt: str,
    summary_prompt_func: Callable[[], str],
    show_raw_output: bool,
    show_vibe: bool,
    model_name: str,
    suppress_output_warning: bool = False,
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
        suppress_output_warning: Whether to suppress output warning
    """
    try:
        # Show warning if no output will be shown and warning is not suppressed
        if not show_raw_output and not show_vibe and not suppress_output_warning:
            console_manager.print_no_output_warning()

        # Get the plan from LLM
        llm_model = llm.get_model(model_name)

        # Format prompt with request
        prompt = plan_prompt.format(request=request)
        response = llm_model.prompt(prompt)
        plan = response.text() if hasattr(response, "text") else str(response)

        # Check for error responses from planner
        if isinstance(plan, str) and plan.startswith("ERROR:"):
            console_manager.print_error(plan[7:])
            sys.exit(1)

        # Extract kubectl command from plan
        kubectl_args = []
        for line in plan.split("\n"):
            if line == "---":
                break
            kubectl_args.append(line)

        # Validate plan format
        if not kubectl_args:
            console_manager.print_error("Invalid response format from planner")
            sys.exit(1)

        # Run kubectl command
        try:
            output = run_kubectl([command, *kubectl_args], capture=True)
        except subprocess.CalledProcessError:
            # Error is already shown by run_kubectl
            sys.exit(1)

        # If no output, nothing to do
        if not output:
            return

        # Handle the output display based on the configured flags
        handle_command_output(
            output=output,
            show_raw_output=show_raw_output,
            show_vibe=show_vibe,
            model_name=model_name,
            summary_prompt_func=summary_prompt_func,
        )
    except Exception as e:
        if "No key found" in str(e):
            console_manager.print_missing_api_key_error()
            sys.exit(1)
        else:
            console_manager.print_error(str(e))
            sys.exit(1)


def configure_output_flags(
    raw: Optional[bool] = None,
    show_raw_output: Optional[bool] = None,
    show_vibe: Optional[bool] = None,
    model: Optional[str] = None,
) -> Tuple[bool, bool, bool, str]:
    """Configure output flags based on user input and defaults.

    Args:
        raw: Legacy raw flag
        show_raw_output: Whether to show raw output
        show_vibe: Whether to show vibe check
        model: LLM model to use

    Returns:
        Tuple of (show_raw_output, show_vibe, suppress_output_warning, model_name)
    """
    # Get config for defaults
    cfg = Config()

    # Configure show_raw_output (--raw takes precedence)
    configured_raw_output = cfg.get("show_raw_output", None)
    if raw is not None:
        show_raw_output = raw
    elif show_raw_output is None and configured_raw_output is not None:
        show_raw_output = configured_raw_output
    elif show_raw_output is None:
        show_raw_output = False  # Default value

    # Configure show_vibe
    configured_vibe = cfg.get("show_vibe", None)
    if show_vibe is None and configured_vibe is not None:
        show_vibe = configured_vibe
    elif show_vibe is None:
        show_vibe = True  # Default value

    # Determine if output warning should be suppressed
    suppress_output_warning = cfg.get("suppress_output_warning", False)

    # Configure model
    configured_model = cfg.get("model", None)
    if model is None and configured_model is not None:
        model_name = configured_model
    elif model is not None:
        model_name = model
    else:
        model_name = "claude-3.7-sonnet"  # Default value

    return (show_raw_output, show_vibe, suppress_output_warning, model_name)
