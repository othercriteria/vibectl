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
    command = [
        "docker",
        "ps",
        "--filter",
        f"name={KIND_CONTAINER}",
        "--format",
        "{{.Names}}",
    ]
    exit_code, stdout, stderr = run_command(command)

    if exit_code != 0:
        console.log(f"[red]Error finding sandbox container: {stderr}[/red]")
        return None

    containers = stdout.strip().split("\n")
    if not containers or not containers[0]:
        console.log(f"[red]No container matching '{KIND_CONTAINER}' found[/red]")
        return None

    return containers[0]


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

    logger.info("Kubernetes cluster is running properly")
    return True


def check_frontend_service(container_name: str) -> dict[str, Any]:
    """Check the status of the frontend service."""
    service_endpoint = "http://localhost:30001"  # Default NodePort for frontend

    # First, check if the frontend service exists
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
        "jsonpath={.spec.type}",
    ]
    exit_code, stdout, stderr = run_command(command)

    # Check if service exists
    if exit_code != 0 or not stdout:
        logger.error(f"Frontend service not found: {stderr or 'No output'}")
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
    command = [
        "docker",
        "exec",
        container_name,
        "curl",
        "-s",
        "-o",
        "/dev/null",
        "-w",
        "%{http_code}",
        "-m",
        "5",  # 5 second timeout
        service_endpoint,
    ]
    exit_code, stdout, stderr = run_command(command, timeout=10)

    end_time = time.time()
    response_time = f"{(end_time - start_time):.2f}s"

    # Check HTTP status code
    if exit_code != 0:
        logger.error(f"Error connecting to frontend service: {stderr}")
        return {
            "status": STATUS_DOWN,
            "response_time": response_time,
            "message": f"Connection error: {stderr}",
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
    command = [
        "docker",
        "exec",
        container_name,
        "curl",
        "-s",
        "-m",
        "5",  # 5 second timeout
        service_endpoint,
    ]
    exit_code, stdout, stderr = run_command(command, timeout=10)

    if exit_code != 0:
        return {
            "status": STATUS_DEGRADED,
            "response_time": response_time,
            "message": f"Content validation error: {stderr}",
            "endpoint": service_endpoint,
            "pods": pod_status,
        }

    # Check for expected content (should contain "Service Status: Online")
    if "Service Status: Online" not in stdout:
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
                msg = (
                    "[red]Could not find sandbox container. "
                    "Retrying in 10 seconds...[/red]"
                )
                console.log(msg)
                time.sleep(10)
                continue

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
