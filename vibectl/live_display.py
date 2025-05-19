import asyncio
import logging
import random

# Ensure all necessary imports are present
import time
from collections.abc import Coroutine
from contextlib import suppress
from typing import TypeVar

import yaml
from rich.live import Live
from rich.progress import (
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from .config import Config
from .k8s_utils import run_kubectl
from .memory import get_memory, update_memory
from .model_adapter import get_model_adapter
from .proxy import TcpProxy, start_proxy_server, stop_proxy_server

# Import the updated type hint from types.py
from .types import (
    Error,
    Fragment,
    OutputFlags,
    Result,
    StatsProtocol,
    Success,
    SummaryPromptFragmentFunc,
    UserFragments,
)
from .utils import console_manager

# Removed imports from command_handler to break cycle
# from .command_handler import handle_command_output, create_api_error

logger = logging.getLogger(__name__)

# Type variable for the return type of the async main function
T = TypeVar("T", bound=Result)


async def _run_async_main(
    main_coro: Coroutine[None, None, T],
    cancel_message: str,
    error_message_prefix: str,
) -> T | Error:
    """Generic runner for async main functions with common error/cancel handling."""
    result: T | Error | None = None

    try:
        # Run the main coroutine - asyncio.run() handles the loop
        result = await main_coro

    except KeyboardInterrupt:
        console_manager.print_note(f"\n{cancel_message}")
        return Error(error=cancel_message)
    except asyncio.CancelledError:
        # Handle internal cancellation
        logger.info(f"{error_message_prefix} task cancelled internally.")
        # Return Error only if result wasn't already set (e.g., by inner handler)
        if result is None:
            return Error(error=f"{error_message_prefix} cancelled internally.")
    except FileNotFoundError as e:
        # Specific handling for kubectl not found from create_async_kubectl_process
        console_manager.print_error(f"\n{error_message_prefix} error: {e!s}")
        return Error(error=str(e), exception=e)
    except Exception as e:
        # Handle other unexpected errors during setup/main execution
        console_manager.print_error(f"\n{error_message_prefix} error: {e!s}")
        return Error(error=f"{error_message_prefix} error: {e}", exception=e)

    # Ensure we return something; if result is None after try/finally, it's an error
    if result is None:
        return Error(error=f"Unknown error during {error_message_prefix}.")

    return result


# Worker function for handle_wait_with_live_display
async def _execute_wait_with_live_display(
    resource: str,
    args: tuple[str, ...],
    output_flags: OutputFlags,
    condition: str,  # Added parameter
    display_text: str,  # Added parameter
    summary_prompt_func: SummaryPromptFragmentFunc,  # Updated type hint
    config: Config | None = None,  # Added config
) -> Result:
    """Executes the core logic for `kubectl wait` with live progress display.

    Args:
        resource: The resource type (e.g., pod, deployment).
        args: Command arguments including resource name and conditions.
        output_flags: Flags controlling output format.
        condition: The condition being waited for (extracted by caller).
        display_text: The text to display in the progress bar (created by caller).

    Returns:
        Result with Success containing wait output or Error with error information
    """
    # Track start time to calculate total duration
    start_time = time.time()

    # This is our async function to run the kubectl wait command
    async def async_run_wait_command() -> Result:
        """Run kubectl wait command asynchronously."""
        # Build command list
        cmd_args = ["wait", resource]
        if args:
            cmd_args.extend(args)

        # Execute the command in a separate thread to avoid blocking the event loop
        # We use asyncio.to_thread to run the blocking kubectl call in a thread pool
        return await asyncio.to_thread(run_kubectl, cmd_args)

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
        async def main() -> Result:
            """Main async routine that runs the wait command and updates progress."""
            # Start updating the progress display in a separate task
            progress_task = asyncio.create_task(update_progress(task_id, progress))

            # Force at least one update to ensure spinner visibility
            await asyncio.sleep(0.1)

            inner_result: Result | None = None
            try:
                # Run the wait command
                inner_result = await async_run_wait_command()

                # Give the progress display time to show completion
                await asyncio.sleep(0.5)

            finally:
                # Ensure progress task cancels on any exit path (success, error, cancel)
                if not progress_task.done():
                    progress_task.cancel()
                    with suppress(asyncio.TimeoutError, asyncio.CancelledError):
                        # Replace wait_for with timeout
                        try:
                            async with asyncio.timeout(0.5):
                                await progress_task
                        except TimeoutError:
                            # Break long warning message
                            logger.warning(
                                "Timeout waiting for progress task to cancel."
                            )

            # Return the result or an error if None
            return inner_result or Error(error="Wait command yielded no result.")

        # Use the new runner
        loop_result = await _run_async_main(
            main(),
            cancel_message="Wait operation cancelled by user",
            error_message_prefix="Wait operation",
        )
        # Check if _run_async_main returned an Error
        if isinstance(loop_result, Error):
            result = loop_result
            wait_success = False
        else:
            # If no error from runner, use the result from the main coroutine
            # We know loop_result is Result (Success or Error) here based on main()
            # And if it wasn't an Error from the outer loop, it should be the
            # Success or Error returned by the inner main() coroutine.
            # Cast to Result for type checker.
            result = loop_result  # type: ignore
            wait_success = isinstance(result, Success)

    # Calculate elapsed time regardless of output
    elapsed_time = time.time() - start_time

    # Handle the command output if any
    if wait_success and isinstance(result, Success):
        # Display success message with duration
        console_manager.console.print(
            f"[bold green]✓[/] Wait completed in [bold]{elapsed_time:.2f}s[/]"
        )

        # Add a small visual separator before the output
        # if output_flags.show_raw or output_flags.show_vibe: # Handled by caller
        #     console_manager.console.print()

        # Return the raw Success result for the caller to handle output processing
        return result
    elif wait_success:
        # If wait completed successfully but there's no output to display
        success_message = (
            f"[bold green]✓[/] {resource} now meets condition '[bold]{condition}[/]' "
            f"(completed in [bold]{elapsed_time:.2f}s[/])"
        )
        console_manager.safe_print(console_manager.console, success_message)

        # Add a small note if no output will be shown
        if not output_flags.show_raw and not output_flags.show_vibe:
            message = (
                "\nNo output display enabled. Use --show-raw-output or "
                "--show-vibe to see details."
            )
            console_manager.console.print(message)

        return Success(
            message=(
                f"{resource} now meets condition '{condition}' "
                f"(completed in {elapsed_time:.2f}s)"
            ),
        )
    else:
        # If there was an issue but we didn't raise an exception
        if isinstance(result, Error):
            message = (
                f"[bold red]✗[/] Wait operation failed after "
                f"[bold]{elapsed_time:.2f}s[/]: {result.error}"
            )
            console_manager.safe_print(console_manager.console, message)
            return result
        else:
            message = (
                f"[bold yellow]![/] Wait operation completed with no result "
                f"after [bold]{elapsed_time:.2f}s[/]"
            )
            console_manager.console.print(message)
            return Error(
                error=(
                    f"Wait operation completed with no result after {elapsed_time:.2f}s"
                )
            )

    # Ensure calls to handle_command_output within this func pass the config
    # REMOVED call to handle_command_output
    # final_result = handle_command_output(
    #     full_output_str, # Use the actual variable holding the output
    #     output_flags,
    #     summary_prompt_func,
    #     command="wait",
    #     config=config
    # )

    # Return the raw result object
    return result


class ConnectionStats(StatsProtocol):
    """Track connection statistics for port-forward sessions."""

    def __init__(self) -> None:
        """Initialize connection statistics."""
        self.start_time = time.time()
        self.current_status = "Connecting"  # Current connection status
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


# Moved from command_handler.py
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


# Worker function for handle_port_forward_with_live_display
async def _execute_port_forward_with_live_display(
    resource: str,
    args: tuple[str, ...],
    output_flags: OutputFlags,
    port_mapping: str,
    local_port: str,
    remote_port: str,
    display_text: str,
    summary_prompt_func: SummaryPromptFragmentFunc,
    allowed_exit_codes: tuple[int, ...] = (0,),
    config: Config | None = None,
) -> Result:
    """Executes the core logic for `kubectl port-forward` with live traffic display.

    Args:
        resource: The resource type (e.g., pod, service).
        args: Command arguments including resource name and port mappings.
        output_flags: Flags controlling output format.
        port_mapping: The extracted port mapping string.
        local_port: The extracted local port.
        remote_port: The extracted remote port.
        display_text: The text to display in the progress bar.

    Returns:
        Result object indicating success or failure.
    """
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
            return Error(
                error=(
                    f"Invalid intermediate_port_range format: "
                    f"{intermediate_port_range}. Expected format: 'min-max'."
                ),
                exception=e,
            )
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

        # Wait briefly before checking process exit or starting proxy
        await asyncio.sleep(0.1)

        # Check if the process has already exited (e.g., due to immediate error)
        if process.returncode is not None:
            return process

        # Return reference to the process
        return process

    # Update the progress display with connection status
    async def update_progress(
        task_id: TaskID,
        progress: Progress,
        process: asyncio.subprocess.Process,
        proxy: TcpProxy | None,
        live_updater: Live,  # Added live_updater parameter (was live_manager)
    ) -> None:
        """Update the progress display with connection status and data."""
        connected = False
        connection_start_time = None

        try:
            # Keep updating until cancelled
            while True:
                # Initialize for logger, in case not connected or no proxy
                b_sent = "N/A"
                b_recv = "N/A"

                # Check if process has output ready - with a timeout
                if process.stdout:  # and not process.stdout.at_eof():
                    try:
                        # Try to read a line with a very short timeout
                        line = await asyncio.wait_for(
                            process.stdout.readline(), timeout=0.01
                        )
                        if line:  # Line received
                            line_str = line.decode("utf-8").strip()
                            if "Forwarding from" in line_str:
                                connected = True
                                stats.current_status = "Connected"
                                if connection_start_time is None:
                                    connection_start_time = time.time()
                        elif line == b"":  # Explicitly check for EOF
                            logger.info("kubectl port-forward stdout reached EOF.")
                            # If kubectl's stdout closes, it's a sign the process might
                            # be ending. The main `await process.wait()` in the outer
                            # `main` coroutine will handle the actual process
                            # termination and status.
                            # We can update status here if it helps, but avoid breaking
                            # the loop prematurely, to allow showing final proxy stats.
                            if process.returncode is not None and connected:
                                logger.info(
                                    f"kubectl process likely exited "
                                    f"(rc={process.returncode}) after stdout EOF."
                                )
                                # Let main logic determine 'connected' based on process
                    except TimeoutError:
                        # This is normal, means kubectl has no new output to send.
                        # The loop will continue to update based on proxy stats.
                        pass
                    except Exception as e_stdout:
                        # Handle other readline errors
                        logger.error(
                            f"Error reading kubectl port-forward stdout: {e_stdout}"
                        )
                        if not any(
                            str(e_stdout) in msg for msg in stats.error_messages
                        ):
                            stats.error_messages.append(
                                f"KubeCtlStdoutError: {str(e_stdout)[:100]}"
                            )
                        # Depending on severity, could set connected = False or log

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
                        status_text = "[green]Connected[/green] "
                        b_sent = f"[cyan]↑{bytes_sent}B[/]"
                        b_recv = f"[magenta]↓{bytes_received}B[/]"
                        status_text += f"({b_sent} {b_recv})"
                    else:
                        status_text = "[green]Connected[/green]"
                else:
                    # Check if the process is still running
                    if process.returncode is not None:
                        stats.current_status = "Disconnected"
                        status_text = "[red]Disconnected[/red]"
                        break

                    # Still establishing connection
                    status_text = "Connecting..."

                # Update the entire description
                description = f"{display_text} - {status_text}"
                logger.debug(
                    f"Updating progress: TaskID={task_id}, Sent={b_sent}, "
                    f"Recv={b_recv}, Status='{status_text}', "
                    f"Full Desc='{description}'"
                )
                progress.update(task_id, description=description)
                live_updater.update(progress)  # Explicitly update the Live display

                await asyncio.sleep(0.1)  # Update interval

        except asyncio.CancelledError:
            # Final update before cancellation
            stats.current_status = "Cancelled"
            progress.update(
                task_id,
                description=f"{display_text} - [yellow]Cancelled[/yellow]",
            )

    # Create progress display
    port_forward_progress_bar = Progress(
        SpinnerColumn(),
        TimeElapsedColumn(),
        TextColumn("{task.description}"),
        console=console_manager.console,
        transient=False,  # We want to keep this visible
    )
    with Live(
        port_forward_progress_bar,
        console=console_manager.console,
        refresh_per_second=10,
        transient=False,
    ) as live_manager:
        # Add port-forward task
        task_id = port_forward_progress_bar.add_task(
            description=f"{display_text} - Starting...", total=None
        )

        # Define the main async routine
        async def main() -> Result:
            """Main async routine that runs port-forward and updates progress.
            Returns Success containing (process, final_status) or Error.
            """
            proxy = None
            process: asyncio.subprocess.Process | None = None
            final_status = "Unknown"
            error_detail: str | None = None

            try:
                # Start proxy server if traffic monitoring is enabled
                if use_proxy and proxy_port is not None:
                    proxy = await start_proxy_server(
                        local_port=int(local_port), target_port=proxy_port, stats=stats
                    )

                # Start the port-forward process
                process = await run_port_forward()

                # Start updating the progress display
                # Pass the Progress instance and the Live instance
                progress_task = asyncio.create_task(
                    update_progress(
                        task_id,
                        port_forward_progress_bar,
                        process,
                        proxy,
                        live_manager,  # Pass live_manager to update_progress
                    )
                )

                try:
                    # Keep running until user interrupts with Ctrl+C
                    await process.wait()

                    # If we get here, the process completed or errored
                    if process.returncode not in allowed_exit_codes:
                        # Read error output
                        stderr = await process.stderr.read() if process.stderr else b""
                        error_msg = stderr.decode("utf-8").strip()
                        stats.error_messages.append(error_msg)
                        # Store error for returning Error result later
                        error_detail = f"Port-forward error: {error_msg}"
                        final_status = "Error (kubectl)"
                        logger.error(error_detail)
                    else:
                        final_status = "Completed"

                except asyncio.CancelledError:
                    # User cancelled, terminate the process
                    if process:
                        process.terminate()
                        await process.wait()
                    final_status = "Cancelled (Internal)"
                    # Propagate cancellation to _run_async_main
                    raise

                finally:
                    # Cancel the progress task
                    if not progress_task.done():
                        progress_task.cancel()
                        with suppress(asyncio.CancelledError):
                            # Replace wait_for with timeout
                            async with asyncio.timeout(1.0):
                                await progress_task

            except FileNotFoundError as e:
                # Handle kubectl not found during run_port_forward
                final_status = "Error (Setup)"
                error_detail = str(e)
                # Return Error directly as process wasn't created
                return Error(error=error_detail, exception=e)
            except Exception as e:
                # Handle other potential errors during setup or wait
                logger.error(
                    f"Unexpected error in port-forward main: {e}", exc_info=True
                )
                final_status = "Error (Internal)"
                error_detail = f"Unexpected internal error: {e}"
                # Ensure process is terminated if it exists
                if process and process.returncode is None:
                    try:
                        process.terminate()
                        await process.wait()
                    except Exception as term_e:
                        logger.warning(f"Error terminating process on error: {term_e}")
                # Return Error directly
                return Error(error=error_detail, exception=e)
            finally:
                # Clean up proxy server if it was started
                if proxy:
                    await stop_proxy_server(proxy)

            # Return Success or Error based on outcome
            if error_detail:
                return Error(error=error_detail)
            else:
                return Success(
                    data=(process, final_status),
                    original_exit_code=process.returncode,
                )

        # Use the new runner
        loop_result = await _run_async_main(
            main(),  # Call main without arguments
            cancel_message="Port-forward cancelled by user",
            error_message_prefix="Port-forward operation",
        )

        # Process results
        process: asyncio.subprocess.Process | None = None
        final_status = (
            "Unknown Exit"  # Default if loop_result is Error or unexpected type
        )
        has_error = True  # Assume error unless proven otherwise

        if isinstance(loop_result, Error):
            # Error occurred during setup or was caught by _run_async_main
            if not stats.error_messages:  # Populate error from result if needed
                stats.error_messages.append(loop_result.error)
            final_status = (
                "Error (Setup)" if "setup" in loop_result.error.lower() else "Error"
            )
            if "cancelled" in loop_result.error.lower():
                final_status = "Cancelled (User)"
                has_error = (
                    False  # User cancel is not an error state for Success/Error return
                )
        elif isinstance(loop_result, tuple) and len(loop_result) == 2:
            # Main coroutine completed successfully, unpack results
            process, reported_status = loop_result
            final_status = reported_status  # Status determined within main()

            # Determine error state based on final status and process exit code
            if final_status == "Completed":
                has_error = False
            elif "Cancelled" in final_status:
                has_error = False  # User cancel is not an error state
            else:  # Includes "Error (kubectl)" or other issues
                has_error = True
                if (
                    process
                    and process.returncode is not None
                    and process.returncode not in allowed_exit_codes
                    and not stats.error_messages
                ):
                    # Capture exit code if no stderr message was logged
                    stats.error_messages.append(
                        f"kubectl exited code {process.returncode}"
                    )
        else:
            # Should not happen if _run_async_main works correctly
            logger.error(
                f"Unexpected result type from _run_async_main: {type(loop_result)}"
            )
            if not stats.error_messages:
                stats.error_messages.append("Unknown internal error during execution.")
            # Keep final_status as "Unknown Exit" and has_error=True

        # Update stats object with the final determined status before display
        stats.current_status = final_status

    # Calculate elapsed time
    elapsed_time = time.time() - start_time

    # Show final status message (uses updated stats.current_status)
    final_status_message = (
        f"[bold]Port-forward session ended ({stats.current_status}) after "
        f"[italic]{elapsed_time:.1f}s[/italic][/bold]"
    )
    console_manager.print_note(f"\n{final_status_message}")

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
    forward_info = (
        f"Port-forward {resource} {port_mapping} ran for "
        f"{elapsed_time:.1f}s ({stats.current_status})"
    )

    # Create command string for memory
    command_str = f"port-forward {resource} {' '.join(args)}"

    # Generate Vibe summary (only if no actual error)
    vibe_output = ""
    if output_flags.show_vibe and not has_error:
        try:
            model_adapter = get_model_adapter()
            model = model_adapter.get_model(output_flags.model_name)

            # Prepare context for prompt
            port_forward_context = {
                "command": command_str,
                "duration": f"{elapsed_time:.1f}s",
                "status": stats.current_status,
                "traffic_monitoring_enabled": stats.traffic_monitoring_enabled,
                "using_proxy": stats.using_proxy,
                "bytes_sent": stats.bytes_sent,
                "bytes_received": stats.bytes_received,
                "errors": stats.error_messages,
            }

            # Format context as YAML for the prompt
            context_yaml = yaml.safe_dump(
                port_forward_context, default_flow_style=False, sort_keys=False
            )

            # Get and format the prompt fragments
            cfg = config or Config()
            current_memory_text = get_memory(cfg)
            system_fragments, user_fragments_template = summary_prompt_func(
                cfg, current_memory_text
            )

            filled_user_fragments: list[
                Fragment
            ] = []  # Explicitly type as list[Fragment]
            for frag_template in user_fragments_template:  # frag_template is a Fragment
                if "{output}" in frag_template:
                    try:
                        # Ensure the formatted string is cast to Fragment
                        filled_user_fragments.append(
                            Fragment(frag_template.format(output=context_yaml))
                        )
                    except KeyError as e:
                        logger.error(
                            "Error formatting port-forward summary fragment "
                            f"'{{output}}': {e}. Context was: {context_yaml}"
                        )
                        # Ensure this string is also cast to Fragment
                        filled_user_fragments.append(
                            Fragment(
                                "Error formatting output. Raw context: {context_yaml}"
                            )
                        )
                else:
                    # frag_template is already a Fragment
                    filled_user_fragments.append(frag_template)

            logger.debug(
                "Vibe Port-forward Summary System Fragments: {system_fragments}"
            )
            logger.debug(
                "Vibe Port-forward Summary User Fragments: {filled_user_fragments}"
            )

            response_text, _ = model_adapter.execute(
                model,
                system_fragments=system_fragments,
                user_fragments=UserFragments(
                    filled_user_fragments
                ),  # Wrap with UserFragments()
            )
            vibe_output = response_text

            if vibe_output:
                console_manager.print_vibe(vibe_output)
            else:
                logger.warning("Received empty summary from Vibe.")

        except Exception as e:
            console_manager.print_error(f"Error generating summary: {e}")
            logger.error(f"Error generating port-forward summary: {e}", exc_info=True)

    # Update memory with the port-forward information
    update_memory(
        command_str,
        forward_info,
        vibe_output,
        output_flags.model_name,
        config=config,
    )

    # Return appropriate result based on whether an error occurred
    if has_error:
        # Return Error if kubectl exited non-zero or other errors occurred
        error_detail = "\n".join(stats.error_messages)
        return Error(
            error=error_detail
            or f"Port-forward failed (status: {stats.current_status})",
        )
    else:
        # Return Success for normal completion or user cancellation
        header = f"Port-forward {resource} {port_mapping}"
        success_message = (
            f"{header} {stats.current_status.lower()} ({elapsed_time:.1f}s)"
            if "Cancelled" in stats.current_status
            else f"{header} completed successfully ({elapsed_time:.1f}s)"
        )
        result = Success(
            message=success_message,
            data=vibe_output,
        )
        if process:
            result.original_exit_code = process.returncode
        return result
