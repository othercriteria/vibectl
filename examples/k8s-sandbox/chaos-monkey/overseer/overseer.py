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
import os.path
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import docker
from apscheduler.schedulers.background import BackgroundScheduler  # type: ignore
from flask import Flask, Response, jsonify, send_file
from flask_socketio import SocketIO
from rich.console import Console

# Configuration from environment variables
METRICS_INTERVAL = 1
SESSION_DURATION = int(os.environ.get("SESSION_DURATION", "30"))
VERBOSE = os.environ.get("VERBOSE", "false").lower() == "true"
POLLER_STATUS_DIR = "/tmp/status"  # Path inside the poller container
DATA_DIR = os.environ.get("DATA_DIR", "/app/data")

# Application setup - set static folder to /app/static
# where js and css files are located
app = Flask(__name__, static_url_path="/static", static_folder="/app/static")
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
    },
    "red": {
        "entries": [],
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
        # Explicitly cast stdout and stderr to string to avoid type issues
        stdout = result.stdout if result.stdout is not None else ""
        stderr = result.stderr if result.stderr is not None else ""
        return result.returncode, stdout, stderr
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


# Function to clean problematic ANSI codes while preserving colors
def clean_ansi(text: str) -> str:
    """Clean problematic ANSI control codes from text while preserving colors.

    This function allows color codes to pass through but removes other
    control sequences that might cause issues in the frontend.

    Args:
        text: The text containing ANSI control codes

    Returns:
        Cleaned text with only safe ANSI codes
    """
    if not text:
        return ""

    # Regular expression to match ANSI escape sequences
    ansi_escape = re.compile(
        r"""
        \x1B            # ESC character
        (?:             # followed by...
            [@-Z\\-_]   # single character from these ranges
        |               # OR
            \[          # CSI sequence
            [0-?]*      # Parameter bytes
            [ -/]*      # Intermediate bytes
            [@-~]       # Final byte
        )
    """,
        re.VERBOSE,
    )

    # Strip all control sequences except color codes
    # This keeps only the basic color codes (30-37, 40-47, 90-97, 100-107)
    return ansi_escape.sub("", text)


def get_agent_logs(agent_role: str, max_lines: int = 100) -> list[dict[str, Any]]:
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
            # Return an overseer message without timestamp
            agent_msg = f"[OVERSEER] {agent_role.capitalize()} agent"
            return [
                {
                    "timestamp": "",  # Empty timestamp for overseer messages
                    "message": (
                        f"{agent_msg} container not found - waiting for startup"
                    ),
                    "level": "INFO",
                    "is_overseer": "true",  # Flag as string to match expected type
                }
            ]

        # Get logs from the container
        logs = container.logs(timestamps=True, tail=max_lines, stream=False).decode(
            "utf-8", errors="replace"
        )

        # Process the logs - clean ANSI codes before sending to frontend
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

            # Clean the message to remove problematic ANSI codes
            message = clean_ansi(message)

            # Normalize box-drawing characters to ensure proper rendering
            # Replace known problematic Unicode box drawing chars with standard forms
            message = message.replace("\u2500", "─")  # HORIZONTAL LINE
            message = message.replace("\u2502", "│")  # VERTICAL LINE
            message = message.replace("\u250c", "┌")  # TOP-LEFT CORNER
            message = message.replace("\u2510", "┐")  # TOP-RIGHT CORNER
            message = message.replace("\u2514", "└")  # BOTTOM-LEFT CORNER
            message = message.replace("\u2518", "┘")  # BOTTOM-RIGHT CORNER
            message = message.replace("\u251c", "├")  # LEFT TEE
            message = message.replace("\u2524", "┤")  # RIGHT TEE
            message = message.replace("\u252c", "┬")  # TOP TEE
            message = message.replace("\u2534", "┴")  # BOTTOM TEE
            message = message.replace("\u253c", "┼")  # CROSS
            message = message.replace("\u2550", "═")  # DOUBLE HORIZONTAL LINE
            message = message.replace("\u2551", "║")  # DOUBLE VERTICAL LINE
            message = message.replace("\u2554", "╔")  # DOUBLE TOP-LEFT CORNER
            message = message.replace("\u2557", "╗")  # DOUBLE TOP-RIGHT CORNER
            # Double bottom corners
            message = message.replace("\u255a", "╚")  # DOUBLE BOTTOM-LEFT CORNER
            message = message.replace("\u255d", "╝")  # DOUBLE BOTTOM-RIGHT CORNER

            # All logs are treated as INFO level to avoid false positives
            log_entries.append(
                {
                    "timestamp": timestamp,
                    "message": message,
                    "level": "INFO",  # Default all to INFO level
                    "is_overseer": "false",  # Regular agent logs as string
                }
            )

        return log_entries

    except Exception as e:
        logger.error(f"Error getting {agent_role} agent logs: {e}")
        # Return an overseer error message without timestamp
        return [
            {
                "timestamp": "",  # Empty timestamp for overseer messages
                "message": f"[OVERSEER] Error getting logs: {e!s}",
                "level": "ERROR",  # Keep error messages as ERROR
                "is_overseer": "true",  # Flag as string to match expected type
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

    # Add last_updated timestamp to help track freshness
    update_timestamp = datetime.now().isoformat()
    new_status["last_updated"] = update_timestamp

    # Calculate service overview information for dashboard
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
    blue_entries = agent_logs["blue"]["entries"]
    red_entries = agent_logs["red"]["entries"]

    # Add database status if available
    db_status = latest_status.get("db_status", "unknown")

    # Emit updates to connected clients
    socketio.emit("status_update", new_status)

    # Emit a specific dashboard update with timestamp to help track updates
    dashboard_update = {
        "status": new_status.get("status", "UNKNOWN"),
        "message": new_status.get("message", ""),
        "db_status": new_status.get("db_status", "unknown"),
        "last_updated": update_timestamp,
    }
    socketio.emit("dashboard_update", dashboard_update)

    # Emit a specific service overview update with all dashboard data
    service_overview_update = {
        "status_counts": status_counts,
        "uptime_percentage": uptime_percentage,
        "total_checks": total_checks,
        "latest_status": latest_status,
        "db_status": db_status,
        "blue_agent_logs_count": len(blue_entries),
        "red_agent_logs_count": len(red_entries),
        "last_updated": update_timestamp,
    }
    socketio.emit("service_overview_update", service_overview_update)

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

            # Add new logs to our history
            current_entries = agent_logs[agent_role]["entries"]

            # Skip if no new logs
            if (
                current_entries
                and new_logs
                and current_entries[-1]["message"] == new_logs[-1]["message"]
            ):
                continue

            # Add the new logs
            current_entries.extend(new_logs)

            # Keep only the last 200 entries
            if len(current_entries) > 200:
                agent_logs[agent_role]["entries"] = current_entries[-200:]

            # Emit update to connected clients
            socketio.emit(f"{agent_role}_log_update", new_logs)

            # We don't need to save logs to disk as frequently
            # Only write logs to disk if we have 20+ new log entries
            # or if it's the first update
            if len(new_logs) > 20 or len(current_entries) <= len(new_logs):
                try:
                    log_file = Path(DATA_DIR) / f"{agent_role}_agent_logs.json"
                    log_file.parent.mkdir(parents=True, exist_ok=True)
                    log_file.write_text(json.dumps(current_entries[-200:], indent=2))
                except Exception as e:
                    logger.error(f"Error saving {agent_role} agent logs: {e}")

        except Exception as e:
            logger.error(f"Error updating {agent_role} agent logs: {e}")


def find_sandbox_container() -> str:
    """Find the Kind sandbox container name."""
    try:
        # Try with exact name for control-plane container
        for container in docker_client.containers.list():
            if (
                container.name
                and "chaos-monkey" in container.name
                and "control-plane" in container.name
            ):
                return str(container.name)

        logger.warning("No kubernetes control-plane container found")
        # Return a sensible default instead of None
        return "chaos-monkey-control-plane"
    except Exception as e:
        logger.error(f"Error finding sandbox container: {e}")
        # Return a sensible default instead of None
        return "chaos-monkey-control-plane"


def get_cluster_status() -> dict[str, Any]:
    """Get the current status of the Kubernetes cluster."""
    try:
        # Initialize result dictionary with simplified fields
        cluster_data: dict[str, Any] = {
            "nodes": [],
            "pods": [],
            "timestamp": datetime.now().isoformat(),
        }

        # Find the sandbox container
        container_name = find_sandbox_container()

        # Get node status by executing kubectl in the container
        command = [
            "docker",
            "exec",
            container_name,
            "kubectl",
            "--kubeconfig",
            "/etc/kubernetes/admin.conf",
            "get",
            "nodes",
            "-o",
            "json",
        ]

        returncode, output, stderr = run_command(command)
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

                # Just check if node is ready
                node_ready = False
                for condition in conditions:
                    if condition.get("type") == "Ready":
                        node_ready = condition.get("status") == "True"
                        break

                # Simplified node info
                node_info = {
                    "name": node_name,
                    "ready": node_ready,
                    "status": "Ready" if node_ready else "NotReady",
                }

                # Add node to the result
                cluster_data["nodes"].append(node_info)
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing node data: {e}")
            cluster_data["nodes"] = []

        # Get pod status for all namespaces
        command = [
            "docker",
            "exec",
            container_name,
            "kubectl",
            "--kubeconfig",
            "/etc/kubernetes/admin.conf",
            "get",
            "pods",
            "--all-namespaces",
            "-o",
            "json",
        ]

        returncode, output, stderr = run_command(command)
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

            # Track total pod counts
            total_pods = 0
            ready_pods = 0

            for item in pod_data.get("items", []):
                total_pods += 1
                pod_name = item.get("metadata", {}).get("name", "unknown")
                namespace = item.get("metadata", {}).get("namespace", "unknown")

                # Get pod status - simplified
                pod_status = item.get("status", {})
                phase = pod_status.get("phase", "Unknown")

                # Simple ready check
                is_ready = False
                for condition in pod_status.get("conditions", []):
                    if (
                        condition.get("type") == "Ready"
                        and condition.get("status") == "True"
                    ):
                        is_ready = True
                        ready_pods += 1
                        break

                # Container readiness count
                container_statuses = pod_status.get("containerStatuses", [])
                ready_containers = 0
                total_containers = len(container_statuses)

                for container in container_statuses:
                    if container.get("ready", False):
                        ready_containers += 1

                # Simplified pod info
                pod_info = {
                    "name": pod_name,
                    "phase": phase,
                    "ready": f"{ready_containers}/{total_containers}",
                    "status": "Ready" if is_ready else phase,
                }

                # Add to namespace grouping
                if namespace not in namespaces:
                    namespaces[namespace] = []
                namespaces[namespace].append(pod_info)

            # Add summary info
            cluster_data["summary"] = {
                "total_pods": total_pods,
                "ready_pods": ready_pods,
                "readiness_percentage": int(
                    (ready_pods / total_pods * 100) if total_pods > 0 else 0
                ),
            }

        except json.JSONDecodeError as e:
            logger.error(f"Error parsing pod data: {e}")
            namespaces = {}
            cluster_data["summary"] = {
                "total_pods": 0,
                "ready_pods": 0,
                "readiness_percentage": 0,
            }

        # Process pods by namespace - simplified
        for namespace, pods in namespaces.items():
            ns_data = {
                "namespace": namespace,
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

    # Add last_updated timestamp if not present
    if "last_updated" not in new_status:
        new_status["last_updated"] = datetime.now().isoformat()

    # Update the cluster status
    cluster_status = new_status

    # Find pods related to chaos-monkey specifically
    chaos_pod_count = 0
    chaos_ready_count = 0
    chaos_pods = []

    for ns_data in cluster_status.get("pods", []):
        for pod in ns_data.get("pods", []):
            if "chaos-monkey" in pod.get("name", ""):
                chaos_pod_count += 1
                if pod.get("status") == "Ready":
                    chaos_ready_count += 1
                chaos_pods.append(pod)

    # Determine an overall readiness status based on chaos-monkey pods
    chaos_status = "Not Ready"
    if chaos_pod_count > 0 and chaos_ready_count == chaos_pod_count:
        chaos_status = "Ready"
    elif chaos_pod_count > 0 and chaos_ready_count > 0:
        chaos_status = f"Partially Ready ({chaos_ready_count}/{chaos_pod_count})"
    elif chaos_pod_count == 0:
        chaos_status = "Not Found"

    # Create a chaos-monkey status update for the frontend
    chaos_update = {
        "status": chaos_status,
        "total_pods": chaos_pod_count,
        "ready_pods": chaos_ready_count,
        "last_updated": datetime.now().isoformat(),
    }

    # Emit updates via WebSocket
    socketio.emit("cluster_update", cluster_status)
    socketio.emit("chaos_status_update", chaos_update)


def start_monitoring() -> None:
    """Start background monitoring tasks."""
    scheduler.add_job(update_service_status, "interval", seconds=METRICS_INTERVAL)
    scheduler.add_job(update_agent_logs, "interval", seconds=5)

    # Set shorter interval for cluster status to keep chaos-monkey status more current
    scheduler.add_job(update_cluster_status, "interval", seconds=3)

    # Add dedicated service overview update task to ensure it refreshes
    # even if no new data from poller
    def refresh_service_overview() -> None:
        """Force a service overview refresh even without new data."""
        # Calculate service overview information for dashboard
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
        blue_entries = agent_logs["blue"]["entries"]
        red_entries = agent_logs["red"]["entries"]

        # Add database status if available
        db_status = latest_status.get("db_status", "unknown")

        # Add last_updated timestamp
        update_timestamp = datetime.now().isoformat()

        # Emit a service overview update
        service_overview_update = {
            "status_counts": status_counts,
            "uptime_percentage": uptime_percentage,
            "total_checks": total_checks,
            "latest_status": latest_status,
            "db_status": db_status,
            "blue_agent_logs_count": len(blue_entries),
            "red_agent_logs_count": len(red_entries),
            "last_updated": update_timestamp,
        }
        socketio.emit("service_overview_update", service_overview_update)

    # Schedule service overview refresh at a faster interval than other updates
    # to ensure the UI stays up-to-date
    scheduler.add_job(refresh_service_overview, "interval", seconds=2)

    scheduler.start()
    logger.info(f"Monitoring started with fixed {METRICS_INTERVAL}s interval")


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_react(path: str) -> Response:
    """Serve the React app for non-API routes."""
    # Let API routes fall through to their handlers
    if path.startswith("api/"):
        return Response("Not found", status=404)

    # For all routes, serve index.html (SPA routing)
    try:
        return send_file("/app/static/index.html")
    except FileNotFoundError as e:
        logger.error(f"index.html not found: {e}")
        return Response(
            "React app not found. Check if the frontend build is correctly copied to "
            "the container.",
            status=500,
        )


@app.route("/manifest.json")
def serve_manifest() -> Response:
    """Serve the manifest.json file with the correct MIME type."""
    try:
        return send_file("/app/static/manifest.json", mimetype="application/json")
    except FileNotFoundError as e:
        logger.error(f"manifest.json not found: {e}")
        return Response(
            "manifest.json not found", status=404, mimetype="application/json"
        )


@app.route("/favicon.ico")
def serve_favicon() -> Response:
    """Serve the favicon.ico file with the correct MIME type."""
    try:
        return send_file("/app/static/favicon.ico", mimetype="image/x-icon")
    except FileNotFoundError as e:
        logger.error(f"favicon.ico not found: {e}")
        return Response("favicon.ico not found", status=404, mimetype="image/x-icon")


@app.route("/asset-manifest.json")
def serve_asset_manifest() -> Response:
    """Serve the asset-manifest.json file with the correct MIME type."""
    try:
        return send_file("/app/static/asset-manifest.json", mimetype="application/json")
    except FileNotFoundError as e:
        logger.error(f"asset-manifest.json not found: {e}")
        return Response(
            "asset-manifest.json not found", status=404, mimetype="application/json"
        )


@app.route("/api/status")
def api_status() -> Any:
    """API endpoint for the current service status."""
    # Ensure status has a last_updated timestamp
    status_data = latest_status.copy()
    if "last_updated" not in status_data:
        status_data["last_updated"] = datetime.now().isoformat()
    return jsonify(status_data)


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
    # Force a fresh status update before returning data
    update_service_status()

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
    blue_entries = agent_logs["blue"]["entries"]
    red_entries = agent_logs["red"]["entries"]

    # Add database status if available
    db_status = latest_status.get("db_status", "unknown")

    # Add a last updated timestamp
    last_updated = datetime.now().isoformat()

    overview = {
        "status_counts": status_counts,
        "uptime_percentage": uptime_percentage,
        "total_checks": total_checks,
        "latest_status": latest_status,
        "db_status": db_status,
        "blue_agent_logs_count": len(blue_entries),
        "red_agent_logs_count": len(red_entries),
        "last_updated": last_updated,
    }

    return jsonify(overview)


@app.route("/api/cluster")
def api_cluster() -> Any:
    """API endpoint for the cluster status."""
    # Force a fresh cluster status update
    update_cluster_status()

    # Find pods related to chaos-monkey specifically
    chaos_pod_count = 0
    chaos_ready_count = 0
    chaos_pods = []

    for ns_data in cluster_status.get("pods", []):
        for pod in ns_data.get("pods", []):
            if "chaos-monkey" in pod.get("name", ""):
                chaos_pod_count += 1
                if pod.get("status") == "Ready":
                    chaos_ready_count += 1
                chaos_pods.append(pod)

    # Count pods in each namespace for quick debugging
    total_pods = 0
    ready_pods = 0
    namespace_counts = {}

    for ns_data in cluster_status.get("pods", []):
        pods = ns_data.get("pods", [])
        namespace = ns_data.get("namespace", "unknown")
        pod_count = len(pods)

        # Count ready pods per namespace
        ready_in_ns = sum(1 for pod in pods if pod.get("status") == "Ready")

        namespace_counts[namespace] = {"total": pod_count, "ready": ready_in_ns}

        total_pods += pod_count
        ready_pods += ready_in_ns

    # Determine an overall readiness status based on chaos-monkey pods
    chaos_status = "Not Ready"
    if chaos_pod_count > 0 and chaos_ready_count == chaos_pod_count:
        chaos_status = "Ready"
    elif chaos_pod_count > 0 and chaos_ready_count > 0:
        chaos_status = f"Partially Ready ({chaos_ready_count}/{chaos_pod_count})"
    elif chaos_pod_count == 0:
        chaos_status = "Not Found"

    # Add debug info to response for troubleshooting
    response_data = cluster_status.copy()
    response_data["debug"] = {
        "total_pods": total_pods,
        "ready_pods": ready_pods,
        "readiness_percentage": int(
            (ready_pods / total_pods * 100) if total_pods > 0 else 0
        ),
        "namespace_counts": namespace_counts,
        "last_fetch_time": datetime.now().isoformat(),
    }

    # Add chaos-monkey specific status
    response_data["chaos_monkey"] = {
        "status": chaos_status,
        "total_pods": chaos_pod_count,
        "ready_pods": chaos_ready_count,
        "pods": chaos_pods,
    }

    # Ensure there's a last_updated timestamp
    response_data["last_updated"] = datetime.now().isoformat()

    # Log summary for debugging
    # Log summary for debugging
    logger.info(
        f"Cluster status: {total_pods} pods ({ready_pods} ready) "
        f"across {len(namespace_counts)} namespaces"
    )
    logger.info(
        f"Chaos-Monkey status: {chaos_status} "
        f"({chaos_ready_count}/{chaos_pod_count} pods ready)"
    )

    return jsonify(response_data)


@socketio.on("connect")
def handle_connect() -> None:
    """Handle client connection."""
    logger.info("Client connected")

    # Force a fresh status update for all data
    update_service_status()
    update_cluster_status()

    # Prepare status data with last_updated timestamp
    status_data = latest_status.copy()
    if "last_updated" not in status_data:
        status_data["last_updated"] = datetime.now().isoformat()

    # Create dashboard update data
    dashboard_update = {
        "status": status_data.get("status", "UNKNOWN"),
        "message": status_data.get("message", ""),
        "db_status": status_data.get("db_status", "unknown"),
        "last_updated": status_data.get("last_updated"),
    }

    # Create service overview update data
    status_counts = {"HEALTHY": 0, "DEGRADED": 0, "DOWN": 0, "ERROR": 0}
    for entry in service_history:
        status = entry.get("status", "ERROR")
        if status in status_counts:
            status_counts[status] += 1

    total_checks = sum(status_counts.values())
    uptime_percentage = 0
    if total_checks > 0:
        healthy_count = status_counts["HEALTHY"]
        degraded_count = status_counts["DEGRADED"]
        error_count = status_counts["ERROR"]
        uptime_calc = (
            (healthy_count + degraded_count + error_count) * 100
        ) // total_checks
        uptime_percentage = int(uptime_calc)

    blue_entries = agent_logs["blue"]["entries"]
    red_entries = agent_logs["red"]["entries"]

    service_overview_update = {
        "status_counts": status_counts,
        "uptime_percentage": uptime_percentage,
        "total_checks": total_checks,
        "latest_status": latest_status,
        "db_status": latest_status.get("db_status", "unknown"),
        "blue_agent_logs_count": len(blue_entries),
        "red_agent_logs_count": len(red_entries),
        "last_updated": status_data.get("last_updated"),
    }

    # Send initial data to the client
    socketio.emit("status_update", status_data)
    socketio.emit("dashboard_update", dashboard_update)
    socketio.emit("service_overview_update", service_overview_update)
    socketio.emit("history_update", service_history)
    socketio.emit("cluster_update", cluster_status)

    # Send the latest 50 log entries to the client
    socketio.emit("blue_log_update", blue_entries[-50:] if blue_entries else [])
    socketio.emit("red_log_update", red_entries[-50:] if red_entries else [])


def main() -> None:
    """Main function to run the overseer."""
    try:
        logger.info("Starting the Chaos Monkey Overseer")

        # Create data directory
        Path(DATA_DIR).mkdir(parents=True, exist_ok=True)

        # Check if React app is available
        react_index = "/app/static/index.html"
        if os.path.exists(react_index):
            logger.info(f"React app found at {react_index}")
        else:
            logger.warning(f"React app not found at {react_index}")

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
