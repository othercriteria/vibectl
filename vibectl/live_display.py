import asyncio
import logging
import random
import re
import time
from collections.abc import Callable
from contextlib import suppress

import yaml
from rich.progress import (
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from .config import Config

# Assuming these imports are correct based on project structure
from .k8s_utils import run_kubectl
from .memory import update_memory
from .model_adapter import get_model_adapter
from .proxy import TcpProxy, start_proxy_server, stop_proxy_server
from .types import Error, OutputFlags, Result, StatsProtocol, Success
from .utils import console_manager

logger = logging.getLogger(__name__)


# Worker function for handle_wait_with_live_display
def _execute_wait_with_live_display(
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

                # Return an error result
                return Error(error=str(e), exception=e)

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
            wait_success = isinstance(
                result, Success
            )  # Success if we got a Success result

        except asyncio.CancelledError:
            # Handle user interrupts (like Ctrl+C)
            console_manager.print_note("Wait operation cancelled")
            return Error(error="Wait operation cancelled by user")

        finally:
            # Clean up the progress display
            progress.stop()

            # If we created a new loop, close it to prevent asyncio warnings
            if created_new_loop and loop is not None:
                loop.close()

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
        # output_result = handle_command_output(
        #     output=result.data or "",
        #     output_flags=output_flags,
        #     command=f"wait {resource} {' '.join(args)}",
        # )
        # return output_result
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


# Moved from command_handler.py
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
def _execute_port_forward_with_live_display(
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
            return Error(error="Port-forward cancelled by user")

        except asyncio.CancelledError:
            # Handle cancellation
            stats.current_status = "Cancelled"
            console_manager.print_note("\nPort-forward cancelled")
            return Error(error="Port-forward cancelled")

        except Exception as e:
            # Handle other errors
            stats.current_status = "Error"
            stats.error_messages.append(str(e))
            console_manager.print_error(f"\nPort-forward error: {e!s}")
            return Error(error=f"Port-forward error: {e}", exception=e)

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
    has_error = bool(stats.error_messages)

    if output_flags.show_vibe:
        try:
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

            # Format stats as YAML for the prompt content
            detailed_yaml = yaml.safe_dump(detailed_info, default_flow_style=False)

            # Get the prompt template and format it with the YAML content
            summary_prompt_template = summary_prompt_func()
            # Assuming the prompt template uses {output} for the main content
            # and {command} for the command string.
            prompt = summary_prompt_template.format(
                output=detailed_yaml, command=command_str
            )

            # Execute the prompt to get a summary
            vibe_output = model_adapter.execute(model, prompt)

            # Display the vibe output
            if vibe_output:
                console_manager.print_vibe(vibe_output)

        except Exception as e:
            # Don't let errors in vibe generation break the command
            console_manager.print_error(f"Error generating summary: {e}")
            logger.error(f"Error generating port-forward summary: {e}", exc_info=True)

    # Update memory with the port-forward information
    update_memory(
        command_str,
        forward_info,
        vibe_output,  # Now using the generated vibe output
        output_flags.model_name,
    )

    # Return appropriate result
    if has_error:
        return Error(
            error="\n".join(stats.error_messages)
            or "Port-forward completed with errors",
        )
    else:
        return Success(
            message=(
                f"Port-forward {resource} {port_mapping} completed "
                f"successfully ({elapsed_time:.1f}s)"
            ),
            data=vibe_output,
        )
