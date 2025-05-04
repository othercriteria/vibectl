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

# Standard library imports
import json
import logging
import os
import os.path
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict

# Third-party imports
import docker  # type: ignore
from apscheduler.schedulers.background import BackgroundScheduler  # type: ignore
from flask import Flask, Response, jsonify, send_file
from flask_socketio import SocketIO  # type: ignore
from rich.console import Console


# Define types for nested structures using class syntax
class ResourceUsage(TypedDict):
    usage: float
    capacity: float


class NodeUsage(TypedDict):
    cpu: ResourceUsage
    memory: ResourceUsage


class QuotaInfo(TypedDict):
    name: str
    cpu_limit: float
    cpu_request: float
    memory_limit: float
    memory_request: float
    cpu_used: float
    memory_used: float


class NamespacePodUsage(TypedDict):
    cpu: float
    memory: float


class ResourceInfoType(TypedDict):
    quotas: dict[str, QuotaInfo]  # Changed Dict to dict
    node_usage: NodeUsage
    pod_usage: dict[str, NamespacePodUsage]  # Changed Dict to dict


# Configuration from environment variables
METRICS_INTERVAL = int(os.environ.get("METRICS_INTERVAL", "1"))
PASSIVE_DURATION = int(os.environ.get("PASSIVE_DURATION", "5"))
ACTIVE_DURATION = int(os.environ.get("ACTIVE_DURATION", "25"))
TOTAL_DURATION_MINUTES = PASSIVE_DURATION + ACTIVE_DURATION
VERBOSE = os.environ.get("VERBOSE", "false").lower() == "true"
POLLER_STATUS_DIR = "/tmp/status"  # Path inside the poller container
DATA_DIR = os.environ.get("DATA_DIR", "/app/data")
AGENT_LOG_INTERVAL = int(os.environ.get("AGENT_LOG_INTERVAL", "2"))
CLUSTER_STATUS_INTERVAL = int(os.environ.get("CLUSTER_STATUS_INTERVAL", "2"))
OVERVIEW_REFRESH_INTERVAL = int(os.environ.get("OVERVIEW_REFRESH_INTERVAL", "1"))
STALE_THRESHOLD_SECONDS = int(
    os.environ.get("STALE_THRESHOLD_SECONDS", "30")
)  # Add staleness threshold

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
last_data_update_time: float = time.monotonic()  # Track last data update
is_stale: bool = False  # Track current staleness state

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
    """Run a shell command with timeout and capture output."""
    try:
        logger.debug(f"Running command: {' '.join(command)}")
        process = subprocess.run(
            command,
            capture_output=capture_output,
            text=True,
            timeout=timeout,
            check=False,  # Don't raise exception on non-zero exit code
        )
        stderr_output = process.stderr.strip() if process.stderr else ""
        stdout_output = process.stdout.strip() if process.stdout else ""
        return process.returncode, stdout_output, stderr_output

    except subprocess.TimeoutExpired:
        logger.error(f"Command timed out after {timeout}s: {' '.join(command)}")
        return 1, "", f"Command timed out after {timeout}s"
    except Exception as e:
        logger.error(f"Error running command {' '.join(command)}: {e}")
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
                "timestamp": datetime.now(timezone.utc).isoformat(),
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
                    "timestamp": datetime.now(timezone.utc).isoformat(),
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
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    except Exception as e:
        logger.error(f"Error getting poller status: {e}")
        return {
            "status": "ERROR",
            "message": f"Error: {e!s}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
                timestamp = datetime.now(timezone.utc).isoformat()
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
    """Fetch latest service status, update history, and emit updates."""
    global service_history, latest_status, last_data_update_time

    logger.info("Updating service status")
    poller_status = get_poller_status()

    if not poller_status or poller_status.get("status") == "ERROR":
        logger.warning("Failed to get valid poller status, skipping update")
        # Do not update last_data_update_time if we failed to get status
        return

    # If we got valid status, update the timestamp
    last_data_update_time = time.monotonic()

    timestamp = datetime.now(timezone.utc).isoformat()
    entry = {
        "status": poller_status.get("status"),
        "message": poller_status.get("message"),
        "timestamp": timestamp,
        "last_updated": timestamp,
    }

    # Update the latest status
    latest_status = entry

    # Add to history with timestamp if not already there
    if "timestamp" not in entry:
        entry["timestamp"] = timestamp

    # Save to history
    service_history.append(entry)

    # Limit history length
    if len(service_history) > 1000:
        service_history = service_history[-1000:]

    # Calculate service overview information for dashboard
    status_counts = {"HEALTHY": 0, "DEGRADED": 0, "DOWN": 0, "ERROR": 0, "PENDING": 0}

    # Count statuses in history
    for entry in service_history:
        status = entry.get("status", "ERROR")
        if status in status_counts:
            status_counts[status] += 1

    # Calculate uptime percentage
    # Denominator should exclude PENDING states
    total_relevant_checks = (
        status_counts["HEALTHY"]
        + status_counts["DEGRADED"]
        + status_counts["DOWN"]
        + status_counts["ERROR"]
    )
    uptime_percentage = 0
    if total_relevant_checks > 0:
        healthy_count = status_counts["HEALTHY"]
        degraded_count = status_counts["DEGRADED"]
        # Include ERROR states in uptime calculation
        error_count = status_counts["ERROR"]
        uptime_calc = (
            (healthy_count + degraded_count + error_count) * 100
        ) // total_relevant_checks  # Use relevant checks for denominator
        uptime_percentage = int(uptime_calc)

    # Get entries counts safely
    blue_entries = agent_logs["blue"]["entries"]
    red_entries = agent_logs["red"]["entries"]

    # Add database status if available
    db_status = latest_status.get("db_status", "unknown")

    # Emit updates to connected clients
    socketio.emit("status_update", entry)

    # Emit a specific dashboard update with timestamp to help track updates
    dashboard_update = {
        "status": entry.get("status", "UNKNOWN"),
        "message": entry.get("message", ""),
        "db_status": entry.get("db_status", "unknown"),
        "last_updated": timestamp,
    }
    socketio.emit("dashboard_update", dashboard_update)

    # Emit a specific service overview update with all dashboard data
    service_overview_update = {
        "status_counts": status_counts,
        "uptime_percentage": uptime_percentage,
        "total_checks": total_relevant_checks,
        "latest_status": latest_status,
        "db_status": db_status,
        "blue_agent_logs_count": len(blue_entries),
        "red_agent_logs_count": len(red_entries),
        "last_updated": timestamp,
    }
    socketio.emit("service_overview_update", service_overview_update)

    # Emit the newly added history entry for live graph updates
    socketio.emit("history_append", entry)

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


# Helper to parse quantity strings (e.g., "500m", "4Gi")
def parse_quantity(quantity_str: str) -> float:
    if not isinstance(quantity_str, str):
        return 0.0
    quantity_str = quantity_str.lower()
    if quantity_str.endswith("m"):  # Milli-CPUs
        return float(quantity_str[:-1]) / 1000.0
    if quantity_str.endswith("gi"):  # GiB Memory
        return float(quantity_str[:-2]) * (1024**3)
    if quantity_str.endswith("mi"):  # MiB Memory
        return float(quantity_str[:-2]) * (1024**2)
    if quantity_str.endswith("ki"):  # KiB Memory
        return float(quantity_str[:-2]) * 1024
    try:
        return float(quantity_str)  # Treat as plain number (CPUs or Bytes)
    except ValueError:
        return 0.0


# Add back the helper function to parse tabular output
def parse_kubectl_top_output(output: str) -> list[dict[str, Any]]:
    """Parse the tabular output of kubectl top nodes/pods."""
    logger.debug(f"Parsing kubectl top output:\n{output}")  # DEBUG
    lines = output.strip().split("\n")
    if len(lines) < 2:  # Header + data
        logger.warning(
            f"parse_kubectl_top_output: Not enough lines ({len(lines)}) to parse."
        )
        return []

    headers_raw = lines[0].lower().split()
    headers = [h.strip() for h in headers_raw if h.strip()]
    data = []
    logger.debug(f"parse_kubectl_top_output: Headers found: {headers}")  # DEBUG

    # Find column indices
    header_indices = {header: lines[0].lower().find(header) for header in headers}
    sorted_headers = sorted(header_indices.items(), key=lambda item: item[1])
    logger.debug(f"parse_kubectl_top_output: Sorted Header Indices: {sorted_headers}")

    for line_num, line in enumerate(lines[1:]):
        if not line.strip():
            continue
        entry = {}
        logger.debug(
            f"parse_kubectl_top_output: Processing line {line_num + 1}: {line}"
        )
        for i, (_, start_index) in enumerate(sorted_headers):
            if i + 1 < len(sorted_headers):
                end_index = sorted_headers[i + 1][1]
            else:
                end_index = len(line)

            value = line[start_index:end_index].strip()
            original_header = lines[0][start_index:end_index].strip()
            entry[original_header] = value
            logger.debug(
                f"parse_kubectl_top_output:   Parsed [{original_header}] = '{value}'"
            )  # DEBUG
        data.append(entry)

    logger.debug(f"parse_kubectl_top_output: Returning parsed data: {data}")  # DEBUG
    return data


def get_resource_data(container_name: str) -> ResourceInfoType:
    """Get resource usage data (quotas, node metrics, pod metrics) from the cluster."""
    resource_info: ResourceInfoType = {
        "quotas": {},
        "node_usage": {
            "cpu": {"usage": 0.0, "capacity": 0.0},  # Added capacity field
            "memory": {"usage": 0.0, "capacity": 0.0},  # Added capacity field
        },
        "pod_usage": {},
    }

    # 1. Get Resource Quotas
    command = [
        "docker",
        "exec",
        container_name,
        "kubectl",
        "get",
        "resourcequotas",
        "--all-namespaces",
        "-o",
        "json",
    ]
    returncode, output, stderr = run_command(command, timeout=10)
    if returncode == 0:
        try:
            quota_data = json.loads(output)
            for item in quota_data.get("items", []):
                namespace = item.get("metadata", {}).get("namespace", "unknown")
                quota_name = item.get("metadata", {}).get("name", "unknown")
                hard_limits = item.get("spec", {}).get("hard", {})
                used = item.get("status", {}).get("used", {})
                resource_info["quotas"][namespace] = {
                    "name": quota_name,
                    "cpu_limit": parse_quantity(hard_limits.get("limits.cpu", "0")),
                    "cpu_request": parse_quantity(hard_limits.get("requests.cpu", "0")),
                    "memory_limit": parse_quantity(
                        hard_limits.get("limits.memory", "0")
                    ),
                    "memory_request": parse_quantity(
                        hard_limits.get("requests.memory", "0")
                    ),
                    "cpu_used": parse_quantity(
                        used.get("limits.cpu", used.get("requests.cpu", "0"))
                    ),
                    "memory_used": parse_quantity(
                        used.get("limits.memory", used.get("requests.memory", "0"))
                    ),
                }
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing resource quota data: {e}")
    else:
        logger.warning(f"Could not get resource quotas: {stderr}")

    command_nodes = [
        "docker",
        "exec",
        container_name,
        "kubectl",
        "get",
        "nodes",
        "-o",
        "json",
    ]
    time.sleep(1)  # Add delay before next command
    returncode_nodes, output_nodes, stderr_nodes = run_command(
        command_nodes, timeout=10
    )
    total_allocatable_cpu = 0.0
    total_allocatable_memory = 0.0
    if returncode_nodes == 0:
        try:
            node_data = json.loads(output_nodes)
            for node in node_data.get("items", []):
                allocatable = node.get("status", {}).get("allocatable", {})
                total_allocatable_cpu += parse_quantity(allocatable.get("cpu", "0"))
                total_allocatable_memory += parse_quantity(
                    allocatable.get("memory", "0")
                )
            resource_info["node_usage"]["cpu"]["capacity"] = total_allocatable_cpu
            resource_info["node_usage"]["memory"]["capacity"] = total_allocatable_memory
            logger.debug(
                f"Total Allocatable Node Resources - CPU: {total_allocatable_cpu}, "
                f"Memory: {total_allocatable_memory}"
            )
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing node allocatable data: {e}")
        except Exception as e:
            logger.error(f"Unexpected error processing node allocatable data: {e}")
    else:
        logger.warning(f"Could not get node allocatable data: {stderr_nodes}")

    # 2. Get Node Metrics (kubectl top nodes - default output)
    command_top_nodes = [
        "docker",
        "exec",
        container_name,
        "kubectl",
        "top",
        "nodes",
    ]
    time.sleep(1)  # Add delay
    returncode_top, output_top, stderr_top = run_command(command_top_nodes, timeout=10)
    if returncode_top == 0:
        try:
            # Use the tabular parser instead of json.loads
            node_metrics = parse_kubectl_top_output(output_top)
            total_cpu_usage = 0.0
            total_mem_usage = 0.0
            for item in node_metrics:
                # Use expected tabular headers (case-sensitive from parser)
                total_cpu_usage += parse_quantity(item.get("CPU(CORES)", "0m"))
                total_mem_usage += parse_quantity(item.get("MEMORY(BYTES)", "0Mi"))
            resource_info["node_usage"]["cpu"]["usage"] = total_cpu_usage
            resource_info["node_usage"]["memory"]["usage"] = total_mem_usage
            logger.debug(
                f"Total Node Usage - CPU: {total_cpu_usage}, Memory: {total_mem_usage}"
            )

        except Exception as e:
            logger.error(f"Error parsing node metrics table: {e}")
    else:
        logger.warning(
            f"Could not get node metrics (is metrics-server running?): {stderr_top}"
        )

    # 3. Get Pod Metrics (kubectl top pods - default output)
    command_top_pods = [
        "docker",
        "exec",
        container_name,
        "kubectl",
        "top",
        "pods",
        "--all-namespaces",
    ]
    time.sleep(1)  # Add delay
    returncode_pods, output_pods, stderr_pods = run_command(
        command_top_pods, timeout=15
    )
    if returncode_pods == 0:
        try:
            # Use the tabular parser instead of json.loads
            pod_metrics = parse_kubectl_top_output(output_pods)
            resource_info["pod_usage"] = {}  # Reset pod usage for fresh calculation
            for item in pod_metrics:
                # Use expected tabular headers (case-sensitive from parser)
                namespace = item.get("NAMESPACE", "unknown")
                if namespace not in resource_info["pod_usage"]:
                    resource_info["pod_usage"][namespace] = {"cpu": 0.0, "memory": 0.0}
                pod_cpu = parse_quantity(item.get("CPU(CORES)", "0m"))
                pod_mem = parse_quantity(item.get("MEMORY(BYTES)", "0Mi"))
                resource_info["pod_usage"][namespace]["cpu"] += pod_cpu
                resource_info["pod_usage"][namespace]["memory"] += pod_mem
            logger.debug(f"Total Pod Usage by Namespace: {resource_info['pod_usage']}")

        except Exception as e:
            logger.error(f"Error parsing pod metrics table: {e}")
    else:
        logger.warning(
            f"Could not get pod metrics (is metrics-server running?): {stderr_pods}"
        )

    # Log the final structure before returning
    logger.debug(f"Final resource_info structure: {resource_info}")
    return resource_info


def get_cluster_status() -> dict[str, Any]:
    """Get the current status of the Kubernetes cluster, including resource data."""
    try:
        # Initialize result dictionary
        cluster_data: dict[str, Any] = {
            "nodes": [],
            "pods": [],
            "resources": {},  # Add placeholder for resource data
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Find the sandbox container
        container_name = find_sandbox_container()

        # Get node status by executing kubectl in the container
        command = [
            "docker",
            "exec",
            container_name,
            "kubectl",
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
                "timestamp": datetime.now(timezone.utc).isoformat(),
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
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "nodes": cluster_data["nodes"],
            }

        try:
            pod_data = json.loads(output)
            namespaces: dict[str, list[dict[str, Any]]] = {}

            # Track total pod counts
            total_pods = 0
            ready_pods = 0

            # Get current time for age calculation
            now = datetime.now(timezone.utc)

            for item in pod_data.get("items", []):
                total_pods += 1
                metadata = item.get("metadata", {})
                pod_name = metadata.get("name", "unknown")
                namespace = metadata.get("namespace", "unknown")
                creation_timestamp_str = metadata.get("creationTimestamp")

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

                # Container readiness count and restarts
                container_statuses = pod_status.get("containerStatuses", [])
                ready_containers = 0
                total_containers = len(container_statuses)
                total_restarts = 0

                for container in container_statuses:
                    if container.get("ready", False):
                        ready_containers += 1
                    # Sum restarts from all containers in the pod
                    total_restarts += container.get("restartCount", 0)

                # Calculate age
                age_str = "N/A"
                if creation_timestamp_str:
                    try:
                        creation_time = datetime.fromisoformat(
                            creation_timestamp_str.replace("Z", "+00:00")
                        )
                        delta = now - creation_time
                        # Simple age formatting (e.g., 2d3h, 5m, 10s)
                        seconds = int(delta.total_seconds())
                        days, remainder = divmod(seconds, 86400)
                        hours, remainder = divmod(remainder, 3600)
                        minutes, seconds = divmod(remainder, 60)
                        if days > 0:
                            age_str = f"{days}d{hours}h"
                        elif hours > 0:
                            age_str = f"{hours}h{minutes}m"
                        elif minutes > 0:
                            age_str = f"{minutes}m{seconds}s"
                        else:
                            age_str = f"{seconds}s"
                    except ValueError:
                        age_str = "Invalid date"

                # Updated pod info with restarts and age
                pod_info = {
                    "name": pod_name,
                    "phase": phase,
                    "ready": f"{ready_containers}/{total_containers}",
                    "status": "Ready" if is_ready else phase,
                    "restarts": total_restarts,  # Added restarts
                    "age": age_str,  # Added calculated age
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

            # --- Get Resource Data ---
            cluster_data["resources"] = get_resource_data(container_name)
            # --- End Resource Data ---

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
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


def update_cluster_status() -> None:
    """Fetch latest cluster status and emit updates."""
    global cluster_status, last_data_update_time
    logger.info("Updating cluster status")
    try:
        sandbox_container_name = find_sandbox_container()
        if not sandbox_container_name:
            logger.warning(
                "Sandbox container not found, skipping cluster status update"
            )
            # Do not update last_data_update_time if container not found
            return

        new_cluster_status = get_cluster_status()

        if new_cluster_status and new_cluster_status != cluster_status:
            cluster_status = new_cluster_status
            socketio.emit("cluster_update", cluster_status)
            logger.info("Cluster status updated and emitted")
            # Update timestamp on successful cluster status retrieval and processing
            last_data_update_time = time.monotonic()
        elif not new_cluster_status:
            logger.warning("Received empty cluster status, not updating")
            # Do not update timestamp if status is empty/invalid

    except Exception as e:
        logger.error(f"Error updating cluster status: {e}", exc_info=True)
        # Do not update timestamp on error


def refresh_service_overview() -> None:
    """Calculate and emit the service overview."""
    global service_history, latest_status
    # Calculate service overview information for dashboard
    status_counts = {"HEALTHY": 0, "DEGRADED": 0, "DOWN": 0, "ERROR": 0, "PENDING": 0}

    # Count statuses in history
    for entry in service_history:
        status = entry.get("status", "ERROR")
        if status in status_counts:
            status_counts[status] += 1

    # Calculate uptime percentage
    # Denominator should exclude PENDING states
    total_relevant_checks = (
        status_counts["HEALTHY"]
        + status_counts["DEGRADED"]
        + status_counts["DOWN"]
        + status_counts["ERROR"]
    )
    uptime_percentage = 0
    if total_relevant_checks > 0:
        healthy_count = status_counts["HEALTHY"]
        degraded_count = status_counts["DEGRADED"]
        # Include ERROR states in uptime calculation
        error_count = status_counts["ERROR"]
        uptime_calc = (
            (healthy_count + degraded_count + error_count) * 100
        ) // total_relevant_checks  # Use relevant checks for denominator
        uptime_percentage = int(uptime_calc)

    # Get entries counts safely
    blue_entries = agent_logs["blue"]["entries"]
    red_entries = agent_logs["red"]["entries"]

    # Add database status if available
    db_status = latest_status.get("db_status", "unknown")

    # Add last_updated timestamp
    update_timestamp = datetime.now(timezone.utc).isoformat()

    # Emit a service overview update
    service_overview_update = {
        "status_counts": status_counts,
        "uptime_percentage": uptime_percentage,
        "total_checks": total_relevant_checks,
        "latest_status": latest_status,
        "db_status": db_status,
        "blue_agent_logs_count": len(blue_entries),
        "red_agent_logs_count": len(red_entries),
        "last_updated": update_timestamp,
    }
    socketio.emit("service_overview_update", service_overview_update)


# Add function to check staleness
def check_staleness() -> None:
    """Check if data is stale and emit updates if status changes."""
    global is_stale, last_data_update_time
    now = time.monotonic()
    time_diff = now - last_data_update_time
    new_is_stale = time_diff > STALE_THRESHOLD_SECONDS

    if new_is_stale != is_stale:
        is_stale = new_is_stale
        logger.info(f"Staleness state changed to: {is_stale}")
        socketio.emit("staleness_update", {"isStale": is_stale})


def start_monitoring() -> None:
    """Initialize and start the monitoring scheduler."""
    logger.info(
        f"Starting monitoring: Service Status={METRICS_INTERVAL}s, "
        f"Agent Logs={AGENT_LOG_INTERVAL}s (max 1 instance), "
        f"Cluster Status={CLUSTER_STATUS_INTERVAL}s (max 1 instance), "
        f"Overview Refresh={OVERVIEW_REFRESH_INTERVAL}s"
    )
    # Use defined intervals and add max_instances where appropriate
    scheduler.add_job(
        update_service_status, "interval", seconds=METRICS_INTERVAL, max_instances=1
    )
    scheduler.add_job(
        update_agent_logs, "interval", seconds=AGENT_LOG_INTERVAL, max_instances=1
    )
    scheduler.add_job(
        update_cluster_status,
        "interval",
        seconds=CLUSTER_STATUS_INTERVAL,
        max_instances=1,
    )
    scheduler.add_job(
        refresh_service_overview,
        "interval",
        seconds=OVERVIEW_REFRESH_INTERVAL,
        max_instances=1,
    )
    # Add job to check staleness
    scheduler.add_job(check_staleness, "interval", seconds=5)  # Check every 5 seconds

    scheduler.start()
    logger.info("Monitoring scheduler started.")


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
        status_data["last_updated"] = datetime.now(timezone.utc).isoformat()
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
    status_counts = {"HEALTHY": 0, "DEGRADED": 0, "DOWN": 0, "ERROR": 0, "PENDING": 0}

    # Count statuses in history
    for entry in service_history:
        status = entry.get("status", "ERROR")
        if status in status_counts:
            status_counts[status] += 1

    # Calculate uptime percentage
    # Denominator should exclude PENDING states
    total_relevant_checks = (
        status_counts["HEALTHY"]
        + status_counts["DEGRADED"]
        + status_counts["DOWN"]
        + status_counts["ERROR"]
    )
    uptime_percentage = 0
    if total_relevant_checks > 0:
        healthy_count = status_counts["HEALTHY"]
        degraded_count = status_counts["DEGRADED"]
        # Include ERROR states in uptime calculation
        error_count = status_counts["ERROR"]
        uptime_calc = (
            (healthy_count + degraded_count + error_count) * 100
        ) // total_relevant_checks  # Use relevant checks for denominator
        uptime_percentage = int(uptime_calc)

    # Get entries counts safely
    blue_entries = agent_logs["blue"]["entries"]
    red_entries = agent_logs["red"]["entries"]

    # Add database status if available
    db_status = latest_status.get("db_status", "unknown")

    # Add a last updated timestamp from latest status if available
    last_updated = latest_status.get(
        "last_updated", datetime.now(timezone.utc).isoformat()
    )

    overview = {
        "status_counts": status_counts,
        "uptime_percentage": uptime_percentage,
        "total_checks": total_relevant_checks,
        "latest_status": latest_status,  # Return current latest_status
        "db_status": db_status,
        "blue_agent_logs_count": len(blue_entries),
        "red_agent_logs_count": len(red_entries),
        "last_updated": last_updated,  # Use timestamp from data if possible
    }

    return jsonify(overview)


@app.route("/api/cluster")
def api_cluster() -> Any:
    """API endpoint for the cluster status."""
    # Find pods related to chaos-monkey specifically
    chaos_pod_count = 0
    chaos_ready_count = 0
    chaos_pods = []

    # Use the globally updated cluster_status
    current_cluster_status = cluster_status.copy()

    for ns_data in current_cluster_status.get("pods", []):
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

    for ns_data in current_cluster_status.get("pods", []):
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
    response_data = current_cluster_status
    response_data["debug"] = {
        "total_pods": total_pods,
        "ready_pods": ready_pods,
        "readiness_percentage": int(
            (ready_pods / total_pods * 100) if total_pods > 0 else 0
        ),
        "namespace_counts": namespace_counts,
        "last_fetch_time": datetime.now(timezone.utc).isoformat(),  # API call time
    }

    # Add chaos-monkey specific status
    response_data["chaos_monkey"] = {
        "status": chaos_status,
        "total_pods": chaos_pod_count,
        "ready_pods": chaos_ready_count,
        "pods": chaos_pods,
    }

    # Ensure there's a last_updated timestamp from the actual data fetch
    response_data["last_updated"] = current_cluster_status.get(
        "last_updated", datetime.now(timezone.utc).isoformat()
    )

    return jsonify(response_data)


@socketio.on("connect")
def handle_connect() -> None:
    """Handle new client connections by sending current state."""
    global latest_status, agent_logs, cluster_status, service_history, is_stale
    logger.info("Client connected")

    # Send current state immediately
    socketio.emit("status_update", latest_status)
    socketio.emit("blue_log_update", agent_logs["blue"]["entries"])
    socketio.emit("red_log_update", agent_logs["red"]["entries"])
    socketio.emit("cluster_update", cluster_status)
    # Prepare overview data to send
    overview_data = {
        "status": latest_status.get("status", "UNKNOWN"),
        "message": latest_status.get("message", "No status yet"),
        "services": latest_status.get("services", {}),
        "service_stats": {
            "total": len(latest_status.get("services", {})),
            "healthy": sum(
                1
                for s in latest_status.get("services", {}).values()
                if s["status"] == "HEALTHY"
            ),
            "unhealthy": sum(
                1
                for s in latest_status.get("services", {}).values()
                if s["status"] == "UNHEALTHY"
            ),
        },
    }
    socketio.emit("service_overview_update", overview_data)
    socketio.emit("history_update", service_history)  # Send initial history too
    # Send initial staleness state
    socketio.emit("staleness_update", {"isStale": is_stale})
    logger.info("Initial state sent to client")


# --- Debug Endpoints --- #


@app.route("/api/debug/force-stale", methods=["POST"])
def debug_force_stale() -> Any:
    """Debug endpoint to force the staleness state to true."""
    global last_data_update_time, STALE_THRESHOLD_SECONDS
    logger.warning("DEBUG: Forcing stale state")
    # Set last update time far enough in the past to trigger staleness
    last_data_update_time = time.monotonic() - (STALE_THRESHOLD_SECONDS + 5)
    # Run the check immediately to update and emit
    check_staleness()
    return jsonify({"status": "success", "message": "Forced stale state"})


@app.route("/api/debug/force-fresh", methods=["POST"])
def debug_force_fresh() -> Any:
    """Debug endpoint to force the staleness state to false."""
    global last_data_update_time
    logger.warning("DEBUG: Forcing fresh state")
    # Set last update time to now
    last_data_update_time = time.monotonic()
    # Run the check immediately to update and emit
    check_staleness()
    return jsonify({"status": "success", "message": "Forced fresh state"})


# --- End Debug Endpoints --- #


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
