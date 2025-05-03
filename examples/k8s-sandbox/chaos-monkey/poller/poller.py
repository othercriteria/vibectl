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
KUBECONFIG = os.environ.get("KUBECONFIG", None)
POLLER_INTERVAL = float(os.environ.get("POLLER_INTERVAL", "1"))
POLLER_HISTORY = int(os.environ.get("POLLER_HISTORY", "1000"))
PASSIVE_DURATION = int(os.environ.get("PASSIVE_DURATION", "5"))
ACTIVE_DURATION = int(os.environ.get("ACTIVE_DURATION", "25"))
TOTAL_DURATION_MINUTES = PASSIVE_DURATION + ACTIVE_DURATION
VERBOSE = os.environ.get("VERBOSE", "false").lower() == "true"
KIND_CONTAINER = os.environ.get("KIND_CONTAINER", "chaos-monkey-control-plane")
OVERSEER_HOST = os.environ.get("OVERSEER_HOST", "overseer")
STATUS_DIR = os.environ.get("STATUS_DIR", "/tmp/status")

# Status codes
STATUS_HEALTHY = "HEALTHY"
STATUS_DEGRADED = "DEGRADED"
STATUS_DOWN = "DOWN"
STATUS_PENDING = "PENDING"

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
        STATUS_PENDING: "cyan",
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

    return not (exit_code != 0 or stdout.strip() != "Active")


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
        "/bin/sh -c 'time -p curl -s http://app.services.svc.cluster.local/health'"
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
    """Main poller function."""
    console.log("[yellow]Poller starting...[/yellow]")

    sandbox_container = find_sandbox_container()
    if not sandbox_container:
        console.log(
            "[bold red]Error: Could not find sandbox container. Exiting.[/bold red]"
        )
        sys.exit(1)

    console.log(f"[cyan]Found sandbox container: {sandbox_container}[/cyan]")

    # Check if Kubernetes cluster is running
    if not check_kubernetes_status(sandbox_container):
        console.log(
            "[bold red]Error: Kubernetes cluster is not ready. Exiting.[/bold red]"
        )
        sys.exit(1)

    console.log("[green]Kubernetes cluster is running.[/green]")

    # Create status directory if it doesn't exist
    Path(STATUS_DIR).mkdir(parents=True, exist_ok=True)
    console.log(f"[cyan]Status directory: {STATUS_DIR}[/cyan]")

    # --- Wait for target services to be deployed ---
    target_deployments = ["app", "demo-db"]
    namespace = "services"
    max_wait_seconds = 180  # 3 minutes timeout
    wait_interval = 5  # Check every 5 seconds
    wait_start_time = time.time()

    console.log(
        f"[yellow]Waiting up to {max_wait_seconds}s for deployments "
        f"{', '.join(target_deployments)} in namespace '{namespace}'...[/yellow]"
    )
    while True:
        found_all = True
        missing_deployments = []
        for deployment_name in target_deployments:
            check_cmd = [
                "docker",
                "exec",
                sandbox_container,
                "kubectl",
                "--kubeconfig",
                "/etc/kubernetes/admin.conf",
                "get",
                "deployment",
                deployment_name,
                "-n",
                namespace,
                "--ignore-not-found",
                "-o",
                "name",
            ]
            exit_code, stdout, _ = run_command(check_cmd)
            if exit_code != 0 or not stdout.strip():
                found_all = False
                missing_deployments.append(deployment_name)
                break  # No need to check others if one is missing

        if found_all:
            console.log(
                f"[green]All target deployments {target_deployments} found.[/green]"
            )
            break

        if time.time() - wait_start_time > max_wait_seconds:
            console.log(
                f"[bold red]Error: Timed out waiting for deployments: "
                f"{missing_deployments}. Exiting.[/bold red]"
            )
            sys.exit(1)

        console.log(
            f"[yellow]Deployments not yet ready ({missing_deployments} missing), "
            f"waiting {wait_interval}s...[/yellow]"
        )
        time.sleep(wait_interval)
    # --- End wait for target services ---

    # Create curl pod for health checks
    if not create_curl_pod_if_needed(sandbox_container):
        console.log(
            "[bold red]Error: Could not create health checker pod. Exiting.[/bold red]"
        )
        sys.exit(1)
    console.log("[green]Health checker pod is ready.[/green]")

    effective_status = STATUS_PENDING  # Track the reported state
    history: list[dict[str, Any]] = []

    while True:
        current_time = datetime.now()
        console.clear()

        # Get the current actual status
        current_check = check_app_service(sandbox_container)

        # Determine what status to report based on the effective_status
        status_to_report: dict[str, Any]
        if effective_status == STATUS_PENDING:
            if current_check.get("status") == STATUS_HEALTHY:
                console.log(
                    "[bold green]Service reported HEALTHY for the first "
                    "time.[/bold green]"
                )
                effective_status = STATUS_HEALTHY
                status_to_report = current_check
            else:
                # Stay in PENDING until the first HEALTHY check
                status_to_report = {
                    "status": STATUS_PENDING,
                    "message": "Waiting for service to become healthy...",
                    "response_time": "N/A",
                    "endpoint": current_check.get("endpoint", "app.services:80"),
                }
        else:
            # Once out of PENDING, report the actual current status
            effective_status = current_check.get("status", STATUS_DOWN)
            # Update effective status
            status_to_report = current_check

        # Add timestamp and update history/file/display with the status_to_report
        status_to_report["timestamp"] = current_time.isoformat()

        # Update history
        history.append(status_to_report)
        if len(history) > POLLER_HISTORY:
            history.pop(0)

        # Update status file
        update_status_file(status_to_report)

        # Print status
        print_status(status_to_report)

        time.sleep(POLLER_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.log("Poller stopped by user.")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"Poller encountered an unexpected error: {e}")
        console.print_exception(show_locals=True)
        sys.exit(1)
