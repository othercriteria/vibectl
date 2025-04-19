#!/usr/bin/env python3
"""
Chaos Monkey Service Poller

Monitors the health of the app service in the Kubernetes cluster.
"""

import json
import logging
import os
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
SESSION_DURATION = int(os.environ.get("SESSION_DURATION", "30"))
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
    # Try with exact name
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

    # Try pattern matching for control-plane container
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
        # Look for containers with 'chaos-monkey' and 'control-plane'
        for container in containers:
            if "chaos-monkey" in container and "control-plane" in container:
                return container

    console.log("[red]No kubernetes control-plane container found[/red]")
    return None


def check_kubernetes_status(container_name: str) -> bool:
    """Check if Kubernetes cluster is running properly."""
    # Check if the container is running
    command = ["docker", "inspect", "-f", "{{.State.Running}}", container_name]
    exit_code, stdout, stderr = run_command(command)

    if exit_code != 0 or stdout.strip() != "true":
        return False

    # Try to get services namespace
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
        return False

    return True


def create_curl_pod_if_needed(container_name: str) -> bool:
    """Create a persistent curl pod for health checks if it doesn't exist."""
    # Use the system-monitoring namespace which agents cannot modify
    namespace = "system-monitoring"

    # Check if the curl pod exists
    command = [
        "docker",
        "exec",
        container_name,
        "kubectl",
        "--kubeconfig",
        "/etc/kubernetes/admin.conf",
        "get",
        "pod",
        "health-checker",
        "-n",
        namespace,
        "--ignore-not-found",
    ]
    exit_code, stdout, stderr = run_command(command)

    # If pod exists, we're good
    if exit_code == 0 and "health-checker" in stdout:
        return True

    # Create the curl pod
    create_command = (
        "kubectl --kubeconfig=/etc/kubernetes/admin.conf "
        f"run health-checker --image=curlimages/curl -n {namespace} "
        "--command -- sleep infinity"
    )

    command = ["docker", "exec", container_name, "bash", "-c", create_command]
    exit_code, stdout, stderr = run_command(command, timeout=30)

    if exit_code != 0:
        logger.error(f"Failed to create health-checker pod: {stderr}")
        return False

    # Wait for pod to be ready
    wait_command = (
        "kubectl --kubeconfig=/etc/kubernetes/admin.conf "
        f"wait --for=condition=ready pod/health-checker -n {namespace} --timeout=30s"
    )

    command = ["docker", "exec", container_name, "bash", "-c", wait_command]
    exit_code, stdout, stderr = run_command(command, timeout=35)

    if exit_code != 0:
        logger.error(f"Failed to wait for health-checker pod: {stderr}")
        return False

    return True


def check_app_service(container_name: str) -> dict[str, Any]:
    """Check the status of the app service."""
    # Check if the app service exists
    command = [
        "docker",
        "exec",
        container_name,
        "kubectl",
        "--kubeconfig",
        "/etc/kubernetes/admin.conf",
        "get",
        "service",
        "app",
        "-n",
        "services",
    ]
    exit_code, stdout, stderr = run_command(command)

    if exit_code != 0:
        return {
            "status": STATUS_DOWN,
            "response_time": "N/A",
            "message": "App service not found",
            "endpoint": "app.services:80",
        }

    # Check pod status
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
        "app=app",
        "-o",
        "jsonpath='{.items[*].status.phase}'",
    ]
    exit_code, stdout, stderr = run_command(command)

    if exit_code != 0:
        pod_status = {"ready": 0, "total": 0}
    else:
        phases = stdout.strip("'\"").split()
        running_pods = phases.count("Running")
        total_pods = len(phases)
        pod_status = {"ready": running_pods, "total": total_pods}

    # If no pods running, service is down
    if pod_status["ready"] == 0:
        return {
            "status": STATUS_DOWN,
            "response_time": "N/A",
            "message": "No running pods found for app service",
            "endpoint": "app.services:80",
            "pods": pod_status,
        }

    # Ensure our persistent curl pod exists
    if not create_curl_pod_if_needed(container_name):
        return {
            "status": STATUS_DEGRADED,
            "response_time": "N/A",
            "message": "Could not create health check pod",
            "endpoint": "app.services:80",
            "pods": pod_status,
        }

    # Check if we can connect to the service using our persistent curl pod
    # Only measure the time for the curl command itself
    check_command = (
        "KUBECONFIG=/etc/kubernetes/admin.conf "
        "kubectl --kubeconfig=/etc/kubernetes/admin.conf "
        "exec health-checker -n system-monitoring -- "
        "/bin/sh -c 'time -p curl -s http://app/health'"
    )

    command = ["docker", "exec", container_name, "bash", "-c", check_command]
    start_time = time.time()
    exit_code, stdout, stderr = run_command(command, timeout=10)
    end_time = time.time()

    # Parse the real request time from stderr if available
    response_time = "N/A"
    if "real" in stderr:
        # Try to extract the real time from the time command output
        for line in stderr.splitlines():
            if line.startswith("real"):
                try:
                    real_time = float(line.split()[1])
                    response_time = f"{real_time:.2f}s"
                    break
                except (ValueError, IndexError):
                    pass

    # Fallback to our own timing if we couldn't parse the time output
    if response_time == "N/A":
        response_time = f"{(end_time - start_time):.2f}s"

    # If we couldn't reach the health endpoint
    if exit_code != 0 or not stdout.strip():
        return {
            "status": STATUS_DOWN,
            "response_time": response_time,
            "message": "App service is not responding",
            "endpoint": "app.services:80",
            "pods": pod_status,
        }

    # Parse health response
    try:
        health_data = json.loads(stdout)
        status = health_data.get("status", "")
        db_status = health_data.get("db", "unknown")

        if status == "degraded" or db_status == "down":
            return {
                "status": STATUS_DEGRADED,
                "response_time": response_time,
                "message": f"Service is degraded. Database status: {db_status}",
                "endpoint": "app.services:80",
                "pods": pod_status,
                "db_status": db_status,
            }
    except json.JSONDecodeError:
        return {
            "status": STATUS_DEGRADED,
            "response_time": response_time,
            "message": "Invalid health response from service",
            "endpoint": "app.services:80",
            "pods": pod_status,
        }

    # If all pods aren't running, service is degraded
    if pod_status["ready"] < pod_status["total"]:
        msg = (
            f"Service is up but only {pod_status['ready']}/{pod_status['total']} "
            "pods are running"
        )
        return {
            "status": STATUS_DEGRADED,
            "response_time": response_time,
            "message": msg,
            "endpoint": "app.services:80",
            "pods": pod_status,
            "db_status": db_status,
        }

    # All checks passed - service is healthy
    return {
        "status": STATUS_HEALTHY,
        "response_time": response_time,
        "message": "Service is healthy and database is connected",
        "endpoint": "app.services:80",
        "pods": pod_status,
        "db_status": db_status,
    }


def update_status_file(status: dict[str, Any]) -> None:
    """Update the status file with the current status."""
    status_file = Path(STATUS_DIR) / "app-status.json"
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
    status_style = status_style_map(status_text)

    # Create a table for the status details
    table = Table(show_header=False, box=None)
    table.add_column("Key", style="bold")
    table.add_column("Value")

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

    # Add database status if available
    if "db_status" in status:
        db_status = status["db_status"]
        db_style = "green" if db_status == "ok" else "yellow"
        table.add_row("DB Status", f"[{db_style}]{db_status}[/{db_style}]")

    # Create a panel with the status info
    panel_title = "APP SERVICE STATUS"
    console.print()
    console.print(
        Panel(
            table,
            title=f"[bold white]{panel_title}[/bold white]",
            border_style=status_style,
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
                "[bold blue]Chaos Monkey App Service Poller[/bold blue]\n"
                "[italic]Monitoring app service health[/italic]",
                border_style="blue",
            )
        )

        # Create status directory
        Path(STATUS_DIR).mkdir(parents=True, exist_ok=True)

        console.log("[green]Starting to monitor app service...[/green]")

        # Calculate end time based on session duration
        end_time = time.time() + (SESSION_DURATION * 60)
        check_count = 0

        while True:
            # Check if session duration has elapsed
            current_time = time.time()
            if current_time >= end_time:
                console.log(
                    f"[green]Session duration ({SESSION_DURATION} min) elapsed.[/green]"
                )
                sys.exit(0)

            console.log(f"[blue]Running service check #{check_count}...[/blue]")

            # Find the sandbox container
            sandbox_container = find_sandbox_container()
            if not sandbox_container:
                status = {
                    "status": STATUS_DOWN,
                    "response_time": "N/A",
                    "message": "Kubernetes sandbox container not found",
                    "endpoint": "app.services:80",
                }
                update_status_file(status)
                print_status(status)
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            # Check if Kubernetes cluster is running
            if not check_kubernetes_status(sandbox_container):
                status = {
                    "status": STATUS_DOWN,
                    "response_time": "N/A",
                    "message": "Kubernetes cluster unavailable",
                    "endpoint": "app.services:80",
                }
                update_status_file(status)
                print_status(status)
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            # Check app service
            status = check_app_service(sandbox_container)

            # Print status
            print_status(status)

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
