#!/usr/bin/env python3
"""
Chaos Monkey Service Poller

Monitors the health of the frontend service in the Kubernetes cluster.
The overseer will be responsible for tracking historical state.
"""

import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Configuration from environment variables
POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "15"))
DELAY_SECONDS = int(os.environ.get("DELAY_SECONDS", "15"))
SESSION_DURATION = int(os.environ.get("SESSION_DURATION", "30"))
KUBECONFIG = os.environ.get("KUBECONFIG", "/config/kube/config")
STATUS_DIR = os.environ.get("STATUS_DIR", "/tmp/status")
KIND_CONTAINER = os.environ.get("KIND_CONTAINER", "chaos-monkey-control-plane")
VERBOSE = os.environ.get("VERBOSE", "false").lower() == "true"

# Status codes
STATUS_HEALTHY = "HEALTHY"
STATUS_DEGRADED = "DEGRADED"
STATUS_DOWN = "DOWN"

# Set up logging
logging.basicConfig(
    level=logging.INFO if VERBOSE else logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("poller")

# Set up Rich console
console = Console()


def status_style_map(status: str) -> str:
    """Return the appropriate style based on status."""
    return {
        STATUS_HEALTHY: "green",
        STATUS_DEGRADED: "yellow",
        STATUS_DOWN: "red",
    }.get(status, "white")


def wait_for_kubeconfig() -> None:
    """Wait for the kubeconfig file to become available."""
    kubeconfig_path = Path(KUBECONFIG)

    if kubeconfig_path.exists():
        console.log(f"[green]Kubeconfig found at {KUBECONFIG}[/green]")
        return

    console.log(f"[yellow]Kubeconfig not found at {KUBECONFIG}. Waiting...[/yellow]")

    # Wait for kubeconfig to appear before failing
    retries = 30

    for i in range(retries):
        if kubeconfig_path.exists():
            console.log("[green]Kubeconfig found after waiting![/green]")
            return

        # Simple text-based waiting indicator compatible with Docker logs
        if i % 5 == 0:  # Show message every 5 iterations
            msg = f"[yellow]Still waiting for kubeconfig... ({i}/{retries})[/yellow]"
            console.log(msg)
        time.sleep(5)

    # If we get here, the kubeconfig never appeared
    msg = "[red]ERROR: Kubeconfig still not available after waiting. Exiting.[/red]"
    console.log(msg)
    sys.exit(1)


def run_command(
    command: list[str], capture_output: bool = True, timeout: int = 30
) -> tuple[int, str, str]:
    """Run a shell command and return exit code, stdout, and stderr."""
    try:
        if VERBOSE:
            logger.info(f"Running command: {' '.join(command)}")

        result = subprocess.run(
            command,
            capture_output=capture_output,
            text=True,
            timeout=timeout,
            check=False,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "Command timed out"
    except Exception as e:
        return 1, "", f"Error running command: {e!s}"


def find_sandbox_container() -> str | None:
    """Find the Kind sandbox container name."""
    # First try searching based on the KIND_CONTAINER value with exact name
    command = [
        "docker",
        "ps",
        "--filter",
        f"name={KIND_CONTAINER}",
        "--format",
        "{{.Names}}",
    ]
    exit_code, stdout, stderr = run_command(command)

    if exit_code == 0 and stdout.strip():
        containers = stdout.strip().split("\n")
        if containers and containers[0]:
            return containers[0]

    # If exact match fails, try with pattern matching for control-plane container
    command = [
        "docker",
        "ps",
        "--format",
        "{{.Names}}",
        "--filter",
        "name=control-plane",
    ]
    exit_code, stdout, stderr = run_command(command)

    if exit_code == 0 and stdout.strip():
        containers = stdout.strip().split("\n")
        # Look for containers that contain both 'chaos-monkey' and 'control-plane'
        for container in containers:
            if "chaos-monkey" in container and "control-plane" in container:
                console.log(f"[green]Found Kind container: {container}[/green]")
                return container

    # Last resort: look for any chaos-monkey container
    command = [
        "docker",
        "ps",
        "--format",
        "{{.Names}}",
        "--filter",
        "name=chaos-monkey",
    ]
    exit_code, stdout, stderr = run_command(command)

    if exit_code == 0 and stdout.strip():
        containers = stdout.strip().split("\n")
        # Filter for containers likely to be the k8s control plane
        for container in containers:
            if (
                "control-plane" in container
                or "k8s" in container
                or "kind" in container
            ):
                console.log(
                    f"[yellow]Found possible Kind container: {container}[/yellow]"
                )
                return container

    console.log(
        "[red]No container matching '"
        f"{KIND_CONTAINER}' or any control-plane container found[/red]"
    )
    return None


def check_kubernetes_status(container_name: str) -> bool:
    """Check if Kubernetes cluster is running properly."""
    # Check if the container is running
    command = ["docker", "inspect", "-f", "{{.State.Running}}", container_name]
    exit_code, stdout, stderr = run_command(command)

    if exit_code != 0 or stdout.strip() != "true":
        console.log(f"[red]Sandbox container is not running: {stderr}[/red]")
        return False

    # Try to get nodes from the Kubernetes cluster
    command = [
        "docker",
        "exec",
        container_name,
        "kubectl",
        "--kubeconfig",
        "/etc/kubernetes/admin.conf",
        "get",
        "nodes",
    ]
    exit_code, stdout, stderr = run_command(command)

    if exit_code != 0:
        console.log(f"[red]Kubernetes API server is not responding: {stderr}[/red]")
        return False

    # Check if any nodes are in Ready state
    if not re.search(r"Ready", stdout):
        console.log("[red]No ready nodes found in the cluster[/red]")
        return False

    # Check if the services namespace exists and is active
    command = [
        "docker",
        "exec",
        container_name,
        "kubectl",
        "--kubeconfig",
        "/etc/kubernetes/admin.conf",
        "get",
        "namespace",
        "services",
        "-o",
        "jsonpath={.status.phase}",
    ]
    exit_code, stdout, stderr = run_command(command)

    if exit_code != 0 or stdout.strip() != "Active":
        console.log(
            "[red]Services namespace is not active: "
            f"{stderr or 'Not found or not active'}[/red]"
        )
        return False

    logger.info("Kubernetes cluster is running properly")
    return True


def check_frontend_service(container_name: str) -> dict[str, Any]:
    """Check the status of the frontend service."""
    # Default NodePort - will try to detect the actual port below
    node_port = "30001"
    local_endpoint = f"http://localhost:{node_port}"
    service_endpoint = f"http://{container_name}:{node_port}"

    # First, check if the frontend service exists and get its NodePort
    command = [
        "docker",
        "exec",
        container_name,
        "kubectl",
        "--kubeconfig",
        "/etc/kubernetes/admin.conf",
        "get",
        "service",
        "frontend",
        "-n",
        "services",
        "-o",
        "jsonpath={.spec.ports[0].nodePort}",
    ]
    exit_code, stdout, stderr = run_command(command)

    # If we got a NodePort, update the endpoints
    if exit_code == 0 and stdout.strip():
        node_port = stdout.strip()
        local_endpoint = f"http://localhost:{node_port}"
        service_endpoint = f"http://{container_name}:{node_port}"
        logger.info(f"Detected NodePort for frontend service: {node_port}")
    else:
        # Try to get the service type at least
        type_command = [
            "docker",
            "exec",
            container_name,
            "kubectl",
            "--kubeconfig",
            "/etc/kubernetes/admin.conf",
            "get",
            "service",
            "frontend",
            "-n",
            "services",
            "-o",
            "jsonpath={.spec.type}",
        ]
        exit_code, stdout, stderr = run_command(type_command)

    # Check if service exists
    if exit_code != 0 or not stdout:
        # Try to get more diagnostic info about the services namespace
        namespace_command = [
            "docker",
            "exec",
            container_name,
            "kubectl",
            "--kubeconfig",
            "/etc/kubernetes/admin.conf",
            "get",
            "namespace",
            "services",
            "--no-headers",
        ]
        ns_exit_code, ns_stdout, ns_stderr = run_command(namespace_command)

        if ns_exit_code != 0:
            error_message = f"Services namespace not found: {ns_stderr}"
            logger.error(error_message)
        else:
            # List all services to see what's available
            all_services_command = [
                "docker",
                "exec",
                container_name,
                "kubectl",
                "--kubeconfig",
                "/etc/kubernetes/admin.conf",
                "get",
                "services",
                "-n",
                "services",
                "--no-headers",
            ]
            svc_exit_code, svc_stdout, svc_stderr = run_command(all_services_command)

            if svc_exit_code == 0 and svc_stdout:
                error_message = (
                    "Frontend service not found, but other services exist: "
                    f"{svc_stdout}"
                )
            else:
                error_message = (
                    f"No services found in namespace: {svc_stderr or 'Empty namespace'}"
                )

            logger.error(error_message)

        return {
            "status": STATUS_DOWN,
            "response_time": "N/A",
            "message": "Frontend service not found",
            "endpoint": service_endpoint,
        }

    # Now check if pods are running
    command = [
        "docker",
        "exec",
        container_name,
        "kubectl",
        "--kubeconfig",
        "/etc/kubernetes/admin.conf",
        "get",
        "pods",
        "-n",
        "services",
        "-l",
        "app=frontend",
        "-o",
        "jsonpath='{.items[*].status.phase}'",
    ]
    exit_code, stdout, stderr = run_command(command)

    if exit_code != 0:
        logger.error(f"Error checking frontend pods: {stderr}")
        pod_status = {"ready": 0, "total": 0}
    else:
        phases = stdout.strip("'\"").split()
        running_pods = phases.count("Running")
        total_pods = len(phases)
        pod_status = {"ready": running_pods, "total": total_pods}

    # If no pods are running, service is down
    if pod_status["ready"] == 0:
        return {
            "status": STATUS_DOWN,
            "response_time": "N/A",
            "message": "No running pods found for frontend service",
            "endpoint": service_endpoint,
            "pods": pod_status,
        }

    # Now check if we can connect to the service
    start_time = time.time()
    # Use curl command inside the container to access the service via localhost
    command = [
        "docker",
        "exec",
        container_name,
        "curl",
        "-s",
        "-v",  # Add verbose output for better diagnostics
        "-o",
        "/dev/null",
        "-w",
        "%{http_code}",
        "-m",
        "5",  # 5 second timeout
        "--fail",  # Fail silently on server errors
        local_endpoint,  # Access via localhost inside the container
    ]
    exit_code, stdout, stderr = run_command(command, timeout=10)

    end_time = time.time()
    response_time = f"{(end_time - start_time):.2f}s"

    # For debugging, check if the port is actually listening
    port_check_command = [
        "docker",
        "exec",
        container_name,
        "ss",
        "-tuln",
        "sport = :" + node_port,
    ]
    port_check_exit_code, port_check_stdout, port_check_stderr = run_command(
        port_check_command
    )
    if port_check_exit_code == 0 and port_check_stdout:
        logger.info(f"Port {node_port} is listening: {port_check_stdout}")
    else:
        logger.warning(f"Port {node_port} doesn't appear to be listening in container")

    # Check HTTP status code
    if exit_code != 0:
        logger.error(f"Error connecting to frontend service: {stderr}")
        # Try to check if the port is even listening
        check_port_command = [
            "docker",
            "exec",
            container_name,
            "nc",
            "-zv",
            "localhost",
            node_port,
        ]
        port_exit_code, port_stdout, port_stderr = run_command(check_port_command)

        error_message = (
            f"Connection error: Port {node_port} not listening on "
            f"{container_name} - {port_stderr}"
        )
        if port_exit_code != 0:
            error_message = f"Connection error: {error_message}"
        elif "Connection refused" in stderr:
            error_message = (
                "Connection error: Connection refused - Service port not listening"
            )
        elif "timed out" in stderr:
            error_message = (
                "Connection error: Connection timed out - Service may be starting"
            )

        return {
            "status": STATUS_DOWN,
            "response_time": response_time,
            "message": error_message,
            "endpoint": service_endpoint,
            "pods": pod_status,
        }

    http_code = stdout.strip()
    if http_code != "200":
        return {
            "status": STATUS_DEGRADED,
            "response_time": response_time,
            "message": f"Service returned HTTP {http_code}",
            "endpoint": service_endpoint,
            "pods": pod_status,
        }

    # If we got a 200 OK but not all pods are running, service is degraded
    if pod_status["ready"] < pod_status["total"]:
        msg = (
            f"Service is up but only {pod_status['ready']}/{pod_status['total']} "
            "pods are running"
        )
        return {
            "status": STATUS_DEGRADED,
            "response_time": response_time,
            "message": msg,
            "endpoint": service_endpoint,
            "pods": pod_status,
        }

    # Check content to verify we got expected content
    content_check_retries = 2
    content_valid = False

    while content_check_retries > 0 and not content_valid:
        command = [
            "docker",
            "exec",
            container_name,
            "curl",
            "-s",
            "-v",  # Add verbose output for better diagnostics
            "-m",
            "5",  # 5 second timeout
            local_endpoint,  # Access via localhost inside the container
        ]
        exit_code, stdout, stderr = run_command(command, timeout=10)

        if exit_code != 0:
            content_check_retries -= 1
            if content_check_retries > 0:
                # Wait briefly and retry
                time.sleep(1)
                continue

            logger.error(f"Content validation failed with error: {stderr}")

            # Try a different approach - sometimes nc works better
            # than curl for checking connectivity
            conn_check_command = [
                "docker",
                "exec",
                container_name,
                "bash",
                "-c",
                (
                    f"echo 'GET / HTTP/1.1\r\nHost: localhost\r\n\r\n' | "
                    f"nc -w 5 localhost {node_port}"
                ),
            ]
            conn_exit_code, conn_stdout, conn_stderr = run_command(conn_check_command)

            if conn_exit_code == 0 and conn_stdout:
                logger.info(
                    f"Alternative connection check succeeded: {conn_stdout[:100]}..."
                )
                return {
                    "status": STATUS_DEGRADED,
                    "response_time": response_time,
                    "message": (
                        "Content validation unclear: curl failed but nc succeeded"
                    ),
                    "endpoint": service_endpoint,
                    "pods": pod_status,
                }

            return {
                "status": STATUS_DEGRADED,
                "response_time": response_time,
                "message": f"Content validation error: {stderr}",
                "endpoint": service_endpoint,
                "pods": pod_status,
            }

        # Check for expected content (should contain "Service Status: Online")
        if "Service Status: Online" in stdout:
            content_valid = True
        else:
            content_check_retries -= 1
            if content_check_retries > 0:
                # Wait briefly and retry
                time.sleep(1)
                continue

            # Log the actual content for diagnostic purposes
            truncated_content = stdout[:200] + "..." if len(stdout) > 200 else stdout
            logger.info(f"Unexpected content from service: {truncated_content}")
            return {
                "status": STATUS_DEGRADED,
                "response_time": response_time,
                "message": "Content validation failed: Expected text not found",
                "endpoint": service_endpoint,
                "pods": pod_status,
            }

    # All checks passed - service is healthy
    return {
        "status": STATUS_HEALTHY,
        "response_time": response_time,
        "message": "Service is healthy and returning expected content",
        "endpoint": service_endpoint,
        "pods": pod_status,
    }


def update_status_file(status: dict[str, Any]) -> None:
    """Update the status file with the current status."""
    status_file = Path(STATUS_DIR) / "frontend-status.json"
    status_with_timestamp = {
        **status,
        "timestamp": datetime.now().isoformat(),
    }

    try:
        # Ensure the directory exists
        status_file.parent.mkdir(parents=True, exist_ok=True)

        # Write the status file
        status_file.write_text(json.dumps(status_with_timestamp, indent=2))
        logger.info(f"Updated status file: {status_file}")
    except Exception as e:
        logger.error(f"Error updating status file: {e!s}")


def print_status(status: dict[str, Any]) -> None:
    """Print a formatted status report using Rich."""
    status_text = status["status"]

    # Create a table for the status details
    table = Table(show_header=False, box=None)
    table.add_column("Key", style="bold")
    table.add_column("Value")

    # Add status with appropriate color
    status_style = status_style_map(status_text)

    table.add_row("Status", f"[{status_style}]{status_text}[/{status_style}]")
    table.add_row("Response Time", status["response_time"])
    table.add_row("Message", status["message"])
    table.add_row("Endpoint", status["endpoint"])

    # Add pod information if available
    if "pods" in status:
        pod_status = status["pods"]
        pod_ratio = f"{pod_status['ready']}/{pod_status['total']}"
        pod_style = "green" if pod_status["ready"] == pod_status["total"] else "yellow"
        table.add_row("Pods Ready", f"[{pod_style}]{pod_ratio}[/{pod_style}]")

    # Create a panel with the status info
    panel_title = "FRONTEND SERVICE STATUS"
    panel_style = status_style_map(status_text)

    console.print()
    console.print(
        Panel(
            table,
            title=f"[bold white]{panel_title}[/bold white]",
            border_style=panel_style,
            expand=False,
        )
    )
    console.print()


def main() -> None:
    """Main function to run the poller."""
    try:
        # Create a nice header
        console.print(
            Panel.fit(
                "[bold blue]Chaos Monkey Frontend Service Poller[/bold blue]\n"
                "[italic]Monitoring frontend service health[/italic]",
                border_style="blue",
            )
        )

        # Create status directory
        Path(STATUS_DIR).mkdir(parents=True, exist_ok=True)

        # Wait for kubeconfig to be available
        wait_for_kubeconfig()

        # Wait for initial delay before starting
        msg = f"[yellow]Waiting for delay of {DELAY_SECONDS} seconds...[/yellow]"
        console.log(msg)
        time.sleep(DELAY_SECONDS)

        console.log("[green]Starting to monitor frontend service...[/green]")

        # Calculate end time based on session duration
        end_time = time.time() + (SESSION_DURATION * 60)
        check_count = 0
        container_retry_count = 0
        max_container_retries = 10

        while True:
            # Check if session duration has elapsed
            current_time = time.time()
            if current_time >= end_time:
                msg = (
                    f"[green]Session duration of {SESSION_DURATION} minutes "
                    "has elapsed.[/green]"
                )
                console.log(msg)
                sys.exit(0)

            console.log(f"[blue]Running service check #{check_count}...[/blue]")

            # Find the sandbox container
            sandbox_container = find_sandbox_container()
            if not sandbox_container:
                container_retry_count += 1
                retry_wait = min(
                    10 * container_retry_count, 60
                )  # Exponential backoff up to 60 seconds

                msg = (
                    f"[red]Could not find sandbox container "
                    f"(attempt {container_retry_count}/{max_container_retries}). "
                    f"Retrying in {retry_wait} seconds...[/red]"
                )
                console.log(msg)

                # After multiple retries, provide additional diagnostic information
                if container_retry_count >= 3:
                    console.log(
                        "[yellow]Running docker ps to debug "
                        "container visibility:[/yellow]"
                    )
                    debug_command = ["docker", "ps", "--format", "{{.Names}}"]
                    exit_code, stdout, stderr = run_command(debug_command)
                    if exit_code == 0 and stdout:
                        console.log(f"[yellow]Available containers: {stdout}[/yellow]")
                    else:
                        console.log(f"[red]Error running docker ps: {stderr}[/red]")

                if container_retry_count >= max_container_retries:
                    console.log(
                        "[red]Maximum container retry attempts reached. "
                        "Will continue checking periodically.[/red]"
                    )
                    container_retry_count = (
                        0  # Reset to keep trying but less frequently
                    )

                # Update status as down due to container not found
                status = {
                    "status": STATUS_DOWN,
                    "response_time": "N/A",
                    "message": "Kubernetes sandbox container not found",
                    "endpoint": "unknown",
                }
                update_status_file(status)
                print_status(status)
                time.sleep(retry_wait)
                continue
            else:
                # Reset retry counter when container is found
                container_retry_count = 0

            # Check if Kubernetes cluster is running
            if not check_kubernetes_status(sandbox_container):
                # If cluster is not running, update status as down and continue
                status = {
                    "status": STATUS_DOWN,
                    "response_time": "N/A",
                    "message": "Kubernetes cluster unavailable",
                    "endpoint": "unknown",
                }
                update_status_file(status)
                print_status(status)
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            # Check frontend service
            status = check_frontend_service(sandbox_container)

            # Print status (full every 3 checks to reduce verbosity)
            if check_count == 0 or check_count % 3 == 0:
                print_status(status)
            else:
                status_style = status_style_map(status["status"])
                log_msg = (
                    f"Service check #{check_count} completed. "
                    f"Status: [{status_style}]{status['status']}[/{status_style}]"
                )
                console.log(log_msg)
                console.log("Use 'make poller-logs' to see full details.")

            # Update status file
            update_status_file(status)

            # Increment check counter
            check_count += 1

            # Wait before next check
            console.log(f"Waiting {POLL_INTERVAL_SECONDS} seconds until next check...")
            time.sleep(POLL_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        console.log("[yellow]Poller interrupted by user. Exiting gracefully.[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.log(f"[red]Unexpected error: {e}[/red]")
        console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()
