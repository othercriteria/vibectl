import asyncio
import logging
import random
import time
from collections.abc import Callable, Coroutine
from contextlib import suppress
from typing import TypeVar

import yaml
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich.text import Text

from .config import Config
from .k8s_utils import create_async_kubectl_process, run_kubectl
from .memory import update_memory
from .model_adapter import get_model_adapter
from .proxy import TcpProxy, start_proxy_server, stop_proxy_server
from .types import Error, OutputFlags, Result, StatsProtocol, Success
from .utils import console_manager

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
    port_mapping: str,  # Added parameter
    local_port: str,  # Added parameter
    remote_port: str,  # Added parameter
    display_text: str,  # Added parameter
    summary_prompt_func: Callable[[], str],
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
                    if process.returncode != 0:
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
                return Success(data=(process, final_status))

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
                    and process.returncode != 0
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

            # Prepare context for the prompt
            watch_context = {
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
                watch_context, default_flow_style=False, sort_keys=False
            )

            # Get and format the prompt
            summary_prompt_template = summary_prompt_func()
            prompt = summary_prompt_template.format(
                output=context_yaml, command=command_str
            )

            logger.debug(f"Vibe Watch Summary Prompt:\n{prompt}")
            vibe_output = model_adapter.execute(model, prompt)

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
        return Success(
            message=success_message,
            data=vibe_output,
        )


# Worker function for handle_watch_with_live_display
async def _execute_watch_with_live_display(
    command: str,  # e.g., 'get'
    resource: str,
    args: tuple[str, ...],
    output_flags: OutputFlags,
    display_text: str,  # Pre-formatted text for the display header
    summary_prompt_func: Callable[[], str],
) -> Result:
    """Executes the core logic for commands with `--watch` using a live display.

    Runs `kubectl <command> <resource> <args...>` (which includes --watch),
    streams the output to a rich.live display, and provides a summary via Vibe
    after the user cancels (Ctrl+C).

    Args:
        command: The kubectl command verb (e.g., 'get').
        resource: The resource type (e.g., pod, deployment).
        args: Command arguments including resource name and --watch flag.
        output_flags: Flags controlling output format and Vibe interaction.
        display_text: Header text for the live display.
        summary_prompt_func: Function to get the Vibe summary prompt template.

    Returns:
        Result object indicating success or failure, usually containing Vibe summary.
    """
    start_time = time.time()
    accumulated_output_lines: list[str] = []
    error_message: str | None = None
    cfg = Config()

    # Use rich.live for displaying streaming output
    live_display_content = Text("")

    async def run_watch_command() -> asyncio.subprocess.Process:
        """Run the kubectl watch command and capture output."""
        # Build command list
        cmd_list = [command, resource]
        cmd_list.extend(args)

        # Full kubectl command
        kubectl_cmd = ["kubectl"]
        kubeconfig = cfg.get("kubeconfig")
        if kubeconfig:
            kubectl_cmd.extend(["--kubeconfig", str(kubeconfig)])
        kubectl_cmd.extend(cmd_list)

        logger.debug(f"Executing watch command: {' '.join(kubectl_cmd)}")
        process = await asyncio.create_subprocess_exec(
            *kubectl_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        return process

    async def stream_output(process: asyncio.subprocess.Process, live: Live) -> None:
        """Read stdout/stderr and update the live display."""
        nonlocal error_message
        stdout_task = None
        stderr_task = None
        pending_tasks = set()

        if process.stdout:

            async def read_stdout() -> bytes:
                if process.stdout is None:
                    return b""
                while True:
                    line = await process.stdout.readline()
                    if not line:
                        break
                    return line
                return b""

            stdout_task = asyncio.create_task(read_stdout(), name="stdout_reader")
            pending_tasks.add(stdout_task)

        if process.stderr:

            async def read_stderr() -> bytes:
                if process.stderr is None:
                    return b""
                while True:
                    line = await process.stderr.readline()
                    if not line:
                        break
                    return line
                return b""

            stderr_task = asyncio.create_task(read_stderr(), name="stderr_reader")
            pending_tasks.add(stderr_task)

        if not pending_tasks:
            logger.warning("Watch command has no stdout or stderr stream.")
            return

        try:
            while pending_tasks:
                done, pending_tasks = await asyncio.wait(
                    pending_tasks, return_when=asyncio.FIRST_COMPLETED
                )

                for task in done:
                    task_name = task.get_name()
                    try:
                        line_bytes = task.result()
                        if not line_bytes:
                            continue

                        line_str = line_bytes.decode("utf-8", errors="replace").strip()
                        accumulated_output_lines.append(line_str)

                        if task is stderr_task:
                            logger.warning(f"Watch STDERR: {line_str}")
                            if error_message is None:
                                error_message = line_str
                        elif task is stdout_task:
                            # Update live display only for stdout
                            current_text = live_display_content.plain
                            lines_to_show = 50
                            # Use list unpacking as suggested by RUF005
                            all_lines = [*current_text.splitlines(), line_str]
                            new_text = "\n".join(all_lines[-lines_to_show:])
                            live_display_content.plain = new_text
                            live.update(Panel(live_display_content, title=display_text))

                        # Re-submit the reader task to read the next line
                        if task is stdout_task and process.stdout:
                            new_stdout_task = asyncio.create_task(
                                read_stdout(), name="stdout_reader"
                            )
                            pending_tasks.add(new_stdout_task)
                            stdout_task = new_stdout_task
                        elif task is stderr_task and process.stderr:
                            new_stderr_task = asyncio.create_task(
                                read_stderr(), name="stderr_reader"
                            )
                            pending_tasks.add(new_stderr_task)
                            stderr_task = new_stderr_task

                    except Exception as e:
                        # Handle exceptions during reading or processing a line
                        logger.error(
                            f"Error processing stream {task_name}: {e}", exc_info=True
                        )
                        error_message = error_message or f"Error reading stream: {e}"
                        # Attempt to cancel remaining tasks and exit loop
                        for t in pending_tasks:
                            t.cancel()
                        pending_tasks.clear()
                        break

        except asyncio.CancelledError:
            logger.info("Output streaming task cancelled.")
            # Ensure all child tasks are cancelled
            if stdout_task and not stdout_task.done():
                stdout_task.cancel()
            if stderr_task and not stderr_task.done():
                stderr_task.cancel()
        finally:
            # Ensure cancellation propagates if necessary
            if stdout_task and not stdout_task.done():
                stdout_task.cancel()
            if stderr_task and not stderr_task.done():
                stderr_task.cancel()
            pass

    # Main execution block
    live_panel = Panel(live_display_content, title=display_text)
    with Live(
        live_panel,  # Use variable to shorten line
        console=console_manager.console,
        refresh_per_second=10,
        transient=False,
        vertical_overflow="visible",
    ) as live:
        # --- Modified main async routine ---
        async def main_watch_task() -> Result:
            """Runs watch command and streams output. The returns Result object."""
            nonlocal error_message  # Allow modification
            process: asyncio.subprocess.Process | None = None
            stream_task = None
            final_status = "Unknown"
            run_error: Error | None = None

            try:
                # Create process using new helper
                cmd_list = [command, resource]
                cmd_list.extend(args)
                process = await create_async_kubectl_process(cmd_list, config=cfg)

                stream_task = asyncio.create_task(stream_output(process, live))

                try:
                    await process.wait()  # Wait for kubectl to finish
                    # Determine status based on exit code and captured errors
                    if process.returncode == 0 and error_message is None:
                        final_status = "Completed"
                    elif process.returncode != 0:
                        final_status = "Error (kubectl)"
                        # Read stderr if not already captured by stream_output
                        if error_message is None:
                            stderr_bytes = (
                                await process.stderr.read() if process.stderr else b""
                            )
                            error_message = stderr_bytes.decode(
                                "utf-8", errors="replace"
                            ).strip()
                            error_message = (
                                error_message
                                or f"kubectl exited code {process.returncode}"
                            )
                        logger.error(f"Watch command error: {error_message}")
                        run_error = Error(
                            error=error_message
                            or f"kubectl exited code {process.returncode}"
                        )
                    else:  # returncode 0 but error_message is set (from stderr stream)
                        final_status = "Completed with errors"
                        logger.warning(
                            f"Watch completed but stderr detected: {error_message}"
                        )
                        # Treat as non-halting error, but capture for return
                        run_error = Error(
                            error=f"Watch completed with stderr: {error_message}"
                        )

                except asyncio.CancelledError:
                    # This is now handled by _run_async_main
                    final_status = "Cancelled (Internal)"
                    raise  # Re-raise for outer handler
                except Exception as wait_err:
                    logger.error(
                        f"Unexpected error waiting for watch process: {wait_err}",
                        exc_info=True,
                    )
                    final_status = "Error (Internal Wait)"
                    run_error = Error(
                        error=f"Error waiting for process: {wait_err}",
                        exception=wait_err,
                    )

                finally:
                    # Ensure stream task is awaited/cancelled cleanly
                    if stream_task and not stream_task.done():
                        try:
                            stream_task.cancel()
                            # Replace wait_for with timeout
                            async with asyncio.timeout(1.0):
                                await stream_task
                        except (TimeoutError, asyncio.CancelledError):
                            logger.warning("Stream output task did not finish cleanly.")
                            pass  # Suppress errors during cleanup

            except FileNotFoundError as e:
                # Handle kubectl not found during create_async_kubectl_process
                final_status = "Error (Setup)"
                run_error = Error(error=str(e), exception=e)
            except Exception as setup_err:
                # Handle other errors during setup
                logger.error(
                    f"Error setting up watch process: {setup_err}", exc_info=True
                )
                final_status = "Error (Setup)"
                run_error = Error(
                    error=f"Error during setup: {setup_err}", exception=setup_err
                )
            finally:
                # Ensure process is terminated if still running (e.g., setup error)
                if process and process.returncode is None:
                    try:
                        process.terminate()
                        # Replace wait_for with timeout
                        async with asyncio.timeout(1.0):
                            await process.wait()
                    except (TimeoutError, ProcessLookupError, Exception) as term_e:
                        logger.warning(
                            f"Error terminating watch process on cleanup: {term_e}"
                        )

            # Return Success containing the tuple, or the captured Error
            if run_error:
                return run_error
            else:
                return Success(data=(process, final_status))

        # --- Use the new runner ---
        loop_result = await _run_async_main(
            main_watch_task(),
            cancel_message="Watch cancelled by user",
            error_message_prefix="Watch execution",
        )

        # Process results
        process: asyncio.subprocess.Process | None = None
        final_status = "Unknown Exit"  # Default
        has_error = True  # Assume error unless proven otherwise

        if isinstance(loop_result, Error):
            # Error occurred during setup or was caught by _run_async_main
            if not error_message:
                error_message = loop_result.error
            final_status = (
                "Error (Setup)" if "setup" in loop_result.error.lower() else "Error"
            )
            if "cancelled" in loop_result.error.lower():
                final_status = "Cancelled by user"
                has_error = False  # User cancel is not an error state
        elif isinstance(loop_result, tuple) and len(loop_result) == 2:
            # Main coroutine completed successfully
            process, reported_status = loop_result
            final_status = reported_status  # Status from main_watch_task

            # Determine error state based on final status
            if final_status == "Completed":
                has_error = False
            elif final_status == "Completed with errors":
                # Treat as success for summary purposes, but log warning
                has_error = False
                logger.warning(f"Watch finished with errors: {error_message}")
            elif "Cancelled" in final_status:
                has_error = False  # User cancel is not an error state
            else:  # Includes "Error (kubectl)" or other issues
                has_error = True
                if (
                    process
                    and process.returncode is not None
                    and process.returncode != 0
                    and not error_message
                ):
                    error_message = (
                        error_message or f"kubectl exited code {process.returncode}"
                    )
        else:
            # Should not happen
            logger.error(
                f"Unexpected result type from _run_async_main for "
                f"watch: {type(loop_result)}"
            )
            if not error_message:
                error_message = "Unknown internal error during watch execution."
            # Keep final_status as "Unknown Exit" and has_error=True

    # --- Post-Watch Processing ---
    elapsed_time = time.time() - start_time
    accumulated_output_str = "\n".join(accumulated_output_lines)
    command_str = f"{command} {resource} {' '.join(args)}"

    # Display summary table (optional, can be enhanced)
    summary_table = Table(title=f"Watch Summary: {command} {resource}")
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", style="green")
    summary_table.add_row("Status", final_status)
    summary_table.add_row("Duration", f"{elapsed_time:.1f}s")
    summary_table.add_row("Lines Received", str(len(accumulated_output_lines)))
    if error_message:
        summary_table.add_row("Error", error_message, style="red")
    console_manager.console.print(summary_table)

    # Prepare Vibe summary
    vibe_output = ""
    if output_flags.show_vibe and final_status != "Error":
        try:
            model_adapter = get_model_adapter()
            model = model_adapter.get_model(output_flags.model_name)

            # Prepare context for the prompt
            watch_context = {
                "command": command_str,
                "duration": f"{elapsed_time:.1f}s",
                "status": final_status,
                "lines_received": len(accumulated_output_lines),
                "output_preview": "\n".join(accumulated_output_lines[:10]),
                "full_output": accumulated_output_str,
            }
            if error_message and final_status != "Error":
                watch_context["error_info"] = error_message

            # Format context as YAML for the prompt
            context_yaml = yaml.safe_dump(
                watch_context, default_flow_style=False, sort_keys=False
            )

            # Get and format the prompt
            summary_prompt_template = summary_prompt_func()
            prompt = summary_prompt_template.format(
                output=context_yaml, command=command_str
            )

            logger.debug(f"Vibe Watch Summary Prompt:\n{prompt}")
            vibe_output = model_adapter.execute(model, prompt)

            if vibe_output:
                console_manager.print_vibe(vibe_output)
            else:
                logger.warning("Received empty summary from Vibe.")

        except Exception as e:
            console_manager.print_error(f"Error generating summary: {e}")
            logger.error(f"Error generating watch summary: {e}", exc_info=True)

    # Update memory
    try:
        update_memory(
            command=command_str,
            command_output=accumulated_output_str,
            vibe_output=vibe_output,
            model_name=output_flags.model_name,
        )
        logger.info("Memory updated after watch session.")
    except Exception as mem_e:
        logger.error(f"Failed to update memory after watch session: {mem_e}")

    # Return final result
    if has_error:  # Use the determined error flag
        return Error(error=error_message or f"Watch command failed ({final_status}).")
    else:
        # Return success, including Vibe summary if generated
        success_msg = f"Watch session '{command_str}' {final_status.lower()} "
        success_msg += f"after {elapsed_time:.1f}s."
        return Success(
            message=success_msg,
            data=vibe_output,
        )
