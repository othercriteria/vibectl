#!/usr/bin/env python3
# Copyright (c) 2025 Daniel Klein
# Part of the vibectl project: https://github.com/othercriteria/vibectl
"""
Chaos Monkey Overseer

Monitors service availability and agent activities:
- Scrapes poller data to track service health over time
- Follows logs from red and blue agents
- Provides real-time dashboard via web interface
- Displays Kubernetes cluster status and resource usage
"""

import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import docker
from apscheduler.schedulers.background import BackgroundScheduler  # type: ignore
from flask import Flask, Response, jsonify, render_template, send_from_directory
from flask_socketio import SocketIO
from rich.console import Console

# Configuration from environment variables
METRICS_INTERVAL = int(os.environ.get("METRICS_INTERVAL", "15"))
SESSION_DURATION = int(os.environ.get("SESSION_DURATION", "30"))
VERBOSE = os.environ.get("VERBOSE", "false").lower() == "true"
POLLER_STATUS_DIR = "/tmp/status"  # Path inside the poller container
DATA_DIR = os.environ.get("DATA_DIR", "/app/data")

# Application setup
app = Flask(__name__, static_folder="static", template_folder="templates")
socketio = SocketIO(app, cors_allowed_origins="*")
scheduler = BackgroundScheduler()
console = Console()

# Global state
service_history: list[dict[str, Any]] = []
latest_status: dict[str, Any] = {}
cluster_status: dict[str, Any] = {}
agent_logs: dict[str, dict[str, Any]] = {
    "blue": {
        "entries": [],
        "cursor": 0,
    },
    "red": {
        "entries": [],
        "cursor": 0,
    },
}

# Set up logging
logging.basicConfig(
    level=logging.INFO if VERBOSE else logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("overseer")

# Docker client for container operations
docker_client = docker.from_env()


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


def get_poller_status() -> dict[str, Any]:
    """Get the latest status from the poller service."""
    try:
        # Locate the poller container
        poller_container = None
        for container in docker_client.containers.list():
            if container.name == "chaos-monkey-poller":
                poller_container = container
                break

        if not poller_container:
            logger.warning("Poller container not found - normal during startup")
            return {
                "status": "PENDING",
                "message": "Poller container not found - waiting for startup",
                "timestamp": datetime.now().isoformat(),
            }

        # Get the status file contents
        exit_code, output = poller_container.exec_run(
            f"cat {POLLER_STATUS_DIR}/app-status.json"
        )

        if exit_code != 0:
            logger.error(f"Error reading status file: {output}")

            # Try the old status file name as fallback
            fallback_exit_code, fallback_output = poller_container.exec_run(
                f"cat {POLLER_STATUS_DIR}/frontend-status.json"
            )

            if fallback_exit_code == 0:
                logger.info("Found status using fallback filename")
                output = fallback_output
            else:
                return {
                    "status": "ERROR",
                    "message": "Failed to read status file",
                    "timestamp": datetime.now().isoformat(),
                }

        # Parse the JSON
        try:
            status: dict[str, Any] = json.loads(output)
            return status
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing status JSON: {e}")
            return {
                "status": "ERROR",
                "message": f"Failed to parse status JSON: {e}",
                "timestamp": datetime.now().isoformat(),
            }

    except Exception as e:
        logger.error(f"Error getting poller status: {e}")
        return {
            "status": "ERROR",
            "message": f"Error: {e!s}",
            "timestamp": datetime.now().isoformat(),
        }


def get_agent_logs(agent_role: str, max_lines: int = 100) -> list[dict[str, str]]:
    """Get the latest logs from the specified agent."""
    try:
        container_name = f"chaos-monkey-{agent_role}-agent"
        container = None

        for c in docker_client.containers.list():
            if c.name == container_name:
                container = c
                break

        if not container:
            logger.warning(
                f"{agent_role.capitalize()} agent container not found - "
                "this is normal during startup"
            )
            return [
                {
                    "timestamp": datetime.now().isoformat(),
                    "message": (
                        f"{agent_role.capitalize()} agent container not found - "
                        "waiting for startup to complete"
                    ),
                    "level": "INFO",
                }
            ]

        # Get logs since the last cursor position
        logs = container.logs(timestamps=True, tail=max_lines, stream=False).decode(
            "utf-8"
        )

        # Process the logs
        log_entries = []
        for line in logs.strip().split("\n"):
            if not line:
                continue

            # Extract timestamp and message
            match = re.match(
                r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z) (.*)$", line
            )
            if match:
                timestamp, message = match.groups()
            else:
                timestamp = datetime.now().isoformat()
                message = line

            # Strip ANSI color codes
            # This regex matches ANSI escape sequences like [34m, [0m, etc.
            message = re.sub(r"\x1B\[\d+(?:;\d+)*m", "", message)

            # Strip timestamps like [6:20:05 PM]
            message = re.sub(r"\[\d+:\d+:\d+ (?:AM|PM)\] ", "", message)

            # TODO: Add timestamp styling via CSS rather than including in log content

            # Determine log level based on content
            if re.search(r"error|exception|fail|critical", message, re.IGNORECASE):
                level = "ERROR"
            elif re.search(r"warn", message, re.IGNORECASE):
                level = "WARNING"
            elif re.search(r"debug", message, re.IGNORECASE):
                level = "DEBUG"
            else:
                level = "INFO"

            log_entries.append(
                {
                    "timestamp": timestamp,
                    "message": message,
                    "level": level,
                }
            )

        return log_entries

    except Exception as e:
        logger.error(f"Error getting {agent_role} agent logs: {e}")
        return [
            {
                "timestamp": datetime.now().isoformat(),
                "message": f"Error getting logs: {e!s}",
                "level": "ERROR",
            }
        ]


def update_service_status() -> None:
    """Update the service status from the poller and track history."""
    global latest_status, service_history

    new_status = get_poller_status()
    if not new_status:
        logger.warning("Failed to get poller status")
        return

    # Update the latest status
    latest_status = new_status

    # Add to history with timestamp if not already there
    if "timestamp" not in new_status:
        new_status["timestamp"] = datetime.now().isoformat()

    service_history.append(new_status)

    # Keep only the last 100 entries to avoid memory issues
    if len(service_history) > 100:
        service_history = service_history[-100:]

    # Emit update to connected clients
    socketio.emit("status_update", new_status)

    # Save history to file
    try:
        history_file = Path(DATA_DIR) / "service_history.json"
        history_file.parent.mkdir(parents=True, exist_ok=True)
        history_file.write_text(json.dumps(service_history, indent=2))
    except Exception as e:
        logger.error(f"Error saving history file: {e}")


def update_agent_logs() -> None:
    """Update the agent logs from both agents."""
    for agent_role in ["blue", "red"]:
        try:
            new_logs = get_agent_logs(agent_role)
            if not new_logs:
                continue

            # Find new logs (not already in our history)
            current_entries = cast(
                list[dict[str, str]], agent_logs[agent_role]["entries"]
            )

            # Simple deduplication by comparing the last entry
            if (
                current_entries
                and new_logs
                and current_entries[-1]["message"] == new_logs[-1]["message"]
            ):
                # No new logs
                continue

            # Add new logs
            current_entries.extend(new_logs)

            # Keep only the last 200 entries to avoid memory issues
            if len(current_entries) > 200:
                agent_logs[agent_role]["entries"] = current_entries[-200:]

            # Update cursor position
            agent_logs[agent_role]["cursor"] = len(current_entries)

            # Emit update to connected clients
            socketio.emit(f"{agent_role}_log_update", new_logs)

            # Save logs to file
            try:
                log_file = Path(DATA_DIR) / f"{agent_role}_agent_logs.json"
                log_file.parent.mkdir(parents=True, exist_ok=True)
                log_file.write_text(json.dumps(current_entries, indent=2))
            except Exception as e:
                logger.error(f"Error saving {agent_role} agent logs: {e}")

        except Exception as e:
            logger.error(f"Error updating {agent_role} agent logs: {e}")


def get_cluster_status() -> dict[str, Any]:
    """Get the current status of the Kubernetes cluster."""
    try:
        # Initialize result dictionary
        cluster_data: dict[str, Any] = {
            "nodes": [],
            "pods": [],
            "services": [],
            "deployments": [],
            "events": [],
            "timestamp": datetime.now().isoformat(),
        }

        # Get node status
        returncode, output, stderr = run_command(
            [
                "kubectl",
                "get",
                "nodes",
                "-o",
                "json",
            ]
        )
        if returncode != 0:
            logger.error(f"Error getting node status: {stderr}")
            return {
                "status": "ERROR",
                "message": "Failed to get node status",
                "timestamp": datetime.now().isoformat(),
            }

        try:
            node_data = json.loads(output)
            for item in node_data.get("items", []):
                node_name = item.get("metadata", {}).get("name", "unknown")
                conditions = item.get("status", {}).get("conditions", [])
                node_ready = False
                for condition in conditions:
                    if condition.get("type") == "Ready":
                        node_ready = condition.get("status") == "True"
                        break

                resources = item.get("status", {}).get("capacity", {})
                cpu = resources.get("cpu", "unknown")
                memory = resources.get("memory", "unknown")

                node_info = {
                    "name": node_name,
                    "ready": node_ready,
                    "cpu": cpu,
                    "memory": memory,
                }

                # Add node to the result
                cluster_data["nodes"].append(node_info)
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing node data: {e}")
            cluster_data["nodes"] = []

        # Get pod status for all namespaces
        returncode, output, stderr = run_command(
            [
                "kubectl",
                "get",
                "pods",
                "--all-namespaces",
                "-o",
                "json",
            ]
        )
        if returncode != 0:
            logger.error(f"Error getting pod status: {stderr}")
            return {
                "status": "ERROR",
                "message": "Failed to get pod status",
                "timestamp": datetime.now().isoformat(),
                "nodes": cluster_data["nodes"],
            }

        try:
            pod_data = json.loads(output)
            namespaces: dict[str, list[dict[str, Any]]] = {}
            for item in pod_data.get("items", []):
                pod_name = item.get("metadata", {}).get("name", "unknown")
                namespace = item.get("metadata", {}).get("namespace", "unknown")

                # Get pod status
                pod_status = item.get("status", {})
                phase = pod_status.get("phase", "Unknown")

                # Get container statuses
                container_statuses = pod_status.get("containerStatuses", [])
                ready_containers = 0
                total_containers = len(container_statuses)

                for container in container_statuses:
                    if container.get("ready", False):
                        ready_containers += 1

                # Get resource usage (this is estimated from requests/limits)
                resource_requests = {}
                containers = item.get("spec", {}).get("containers", [])
                for container in containers:
                    requests = container.get("resources", {}).get("requests", {})
                    if "cpu" in requests:
                        resource_requests["cpu"] = requests["cpu"]
                    if "memory" in requests:
                        resource_requests["memory"] = requests["memory"]

                pod_info = {
                    "name": pod_name,
                    "phase": phase,
                    "ready": f"{ready_containers}/{total_containers}",
                    "resources": resource_requests,
                }

                # Add to namespace grouping
                if namespace not in namespaces:
                    namespaces[namespace] = []
                namespaces[namespace].append(pod_info)
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing pod data: {e}")
            namespaces = {}

        # Get namespace information
        returncode, output, stderr = run_command(
            [
                "kubectl",
                "get",
                "namespaces",
                "-o",
                "json",
            ]
        )
        if returncode != 0:
            logger.error(f"Error getting namespace info: {stderr}")
            namespace_status: dict[str, str] = {}
        else:
            try:
                namespace_data = json.loads(output)
                namespace_status = {}
                for item in namespace_data.get("items", []):
                    ns_name = item.get("metadata", {}).get("name", "unknown")
                    ns_status = item.get("status", {}).get("phase", "Unknown")
                    namespace_status[ns_name] = ns_status
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing namespace data: {e}")
                namespace_status = {}

        # Process pods by namespace
        for namespace, pods in namespaces.items():
            ns_data = {
                "namespace": namespace,
                "status": namespace_status.get(namespace, "Unknown"),
                "pods": pods,
            }
            cluster_data["pods"].append(ns_data)

        return cluster_data

    except Exception as e:
        logger.error(f"Error getting cluster status: {e}")
        return {
            "status": "ERROR",
            "message": f"Error: {e!s}",
            "timestamp": datetime.now().isoformat(),
        }


def update_cluster_status() -> None:
    """Update the cluster status."""
    global cluster_status

    new_status = get_cluster_status()
    if not new_status:
        logger.warning("Failed to get cluster status")
        return

    # Update the cluster status
    cluster_status = new_status

    # Emit update via WebSocket
    socketio.emit("cluster_update", cluster_status)


def start_monitoring() -> None:
    """Start background monitoring tasks."""
    scheduler.add_job(update_service_status, "interval", seconds=METRICS_INTERVAL)
    scheduler.add_job(update_agent_logs, "interval", seconds=5)
    scheduler.add_job(update_cluster_status, "interval", seconds=METRICS_INTERVAL)
    scheduler.start()
    logger.info(f"Monitoring started with {METRICS_INTERVAL}s interval")


@app.route("/")
def index() -> str | Response:
    """Render the main dashboard page."""
    return render_template("index.html")


@app.route("/static/<path:path>")
def send_static(path: str) -> Response:
    """Serve static files."""
    return send_from_directory("static", path)


@app.route("/api/status")
def api_status() -> Any:
    """API endpoint for the current service status."""
    return jsonify(latest_status)


@app.route("/api/history")
def api_history() -> Any:
    """API endpoint for the service history."""
    return jsonify(service_history)


@app.route("/api/logs/<agent_role>")
def api_logs(agent_role: str) -> Any:
    """API endpoint for agent logs."""
    if agent_role not in ["blue", "red"]:
        return jsonify({"error": "Invalid agent role"}), 400

    return jsonify(agent_logs[agent_role]["entries"])


@app.route("/api/overview")
def api_overview() -> Any:
    """API endpoint for an overview of the system status."""
    status_counts = {"HEALTHY": 0, "DEGRADED": 0, "DOWN": 0, "ERROR": 0}

    # Count statuses in history
    for entry in service_history:
        status = entry.get("status", "ERROR")
        if status in status_counts:
            status_counts[status] += 1

    # Calculate uptime percentage
    total_checks = sum(status_counts.values())
    uptime_percentage = 0
    if total_checks > 0:
        healthy_count = status_counts["HEALTHY"]
        degraded_count = status_counts["DEGRADED"]
        # Include ERROR states in uptime calculation
        error_count = status_counts["ERROR"]
        uptime_calc = (
            (healthy_count + degraded_count + error_count) * 100
        ) // total_checks
        uptime_percentage = int(uptime_calc)

    # Get entries counts safely
    blue_entries = cast(list[dict[str, str]], agent_logs["blue"]["entries"])
    red_entries = cast(list[dict[str, str]], agent_logs["red"]["entries"])

    # Add database status if available
    db_status = latest_status.get("db_status", "unknown")

    overview = {
        "status_counts": status_counts,
        "uptime_percentage": uptime_percentage,
        "total_checks": total_checks,
        "latest_status": latest_status,
        "db_status": db_status,
        "blue_agent_logs_count": len(blue_entries),
        "red_agent_logs_count": len(red_entries),
    }

    return jsonify(overview)


@app.route("/api/cluster")
def api_cluster() -> Any:
    """API endpoint for the cluster status."""
    return jsonify(cluster_status)


@app.route("/cluster-status")
def cluster_status_page() -> str | Response:
    """Cluster status page."""
    return render_template("index.html", view="cluster")


@socketio.on("connect")
def handle_connect() -> None:
    """Handle client connection."""
    logger.info("Client connected")
    # Send initial data to the client
    socketio.emit("status_update", latest_status)
    socketio.emit("history_update", service_history)
    socketio.emit("cluster_update", cluster_status)

    blue_entries = cast(list[dict[str, str]], agent_logs["blue"]["entries"])
    red_entries = cast(list[dict[str, str]], agent_logs["red"]["entries"])

    socketio.emit("blue_log_update", blue_entries[-50:] if blue_entries else [])
    socketio.emit("red_log_update", red_entries[-50:] if red_entries else [])


def main() -> None:
    """Main function to run the overseer."""
    try:
        logger.info("Starting the Chaos Monkey Overseer")

        # Create data directory
        Path(DATA_DIR).mkdir(parents=True, exist_ok=True)

        # Initialize with current data
        update_service_status()
        update_agent_logs()
        update_cluster_status()

        # Start background monitoring
        start_monitoring()

        # Start the web server
        port = int(os.environ.get("PORT", "8080"))
        host = os.environ.get("HOST", "0.0.0.0")
        logger.info(f"Starting web server on {host}:{port}")
        socketio.run(app, host=host, port=port, debug=False, allow_unsafe_werkzeug=True)

    except KeyboardInterrupt:
        logger.info("Overseer interrupted. Shutting down gracefully.")
        scheduler.shutdown()
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
