#!/usr/bin/env python3
# Copyright (c) 2025 Daniel Klein
# Part of the vibectl project: https://github.com/othercriteria/vibectl
"""
Chaos Monkey Overseer

Monitors service availability and agent activities:
- Scrapes poller data to track service health over time
- Follows logs from red and blue agents
- Provides real-time dashboard via web interface
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
from typing import Any, cast

import docker
from apscheduler.schedulers.background import BackgroundScheduler
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
            logger.error("Poller container not found")
            return {
                "status": "ERROR",
                "message": "Poller container not found",
                "timestamp": datetime.now().isoformat(),
            }

        # Get the status file contents
        exit_code, output = poller_container.exec_run(
            f"cat {POLLER_STATUS_DIR}/frontend-status.json"
        )

        if exit_code != 0:
            logger.error(f"Error reading status file: {output.decode('utf-8')}")
            return {
                "status": "ERROR",
                "message": "Failed to read status file",
                "timestamp": datetime.now().isoformat(),
            }

        # Parse the JSON
        try:
            status_text = output.decode("utf-8")
            status: dict[str, Any] = json.loads(status_text)
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
            logger.error(f"{agent_role.capitalize()} agent container not found")
            return [
                {
                    "timestamp": datetime.now().isoformat(),
                    "message": f"{agent_role.capitalize()} agent container not found",
                    "level": "ERROR",
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


def check_container_readiness() -> bool:
    """Check if all necessary containers are running."""
    required_containers = [
        "chaos-monkey-poller",
        "chaos-monkey-blue-agent",
        "chaos-monkey-red-agent",
    ]

    running_containers = [c.name for c in docker_client.containers.list()]

    missing = [c for c in required_containers if c not in running_containers]
    if missing:
        logger.warning(f"Missing containers: {', '.join(missing)}")
        return False

    return True


def start_monitoring() -> None:
    """Start the monitoring threads and schedulers."""
    # Add jobs to the scheduler
    scheduler.add_job(update_service_status, "interval", seconds=METRICS_INTERVAL)
    scheduler.add_job(update_agent_logs, "interval", seconds=METRICS_INTERVAL)

    # Start the scheduler
    scheduler.start()
    logger.info("Started background monitoring")


@app.route("/")
def index() -> Response:
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

    overview = {
        "status_counts": status_counts,
        "uptime_percentage": uptime_percentage,
        "total_checks": total_checks,
        "latest_status": latest_status,
        "blue_agent_logs_count": len(blue_entries),
        "red_agent_logs_count": len(red_entries),
    }

    return jsonify(overview)


@socketio.on("connect")
def handle_connect() -> None:
    """Handle client connection."""
    logger.info("Client connected")
    # Send initial data to the client
    socketio.emit("status_update", latest_status)
    socketio.emit("history_update", service_history)

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

        # Wait for containers to be ready
        retry_count = 0
        while not check_container_readiness() and retry_count < 10:
            logger.info("Waiting for containers to be ready...")
            time.sleep(5)
            retry_count += 1

        if retry_count >= 10:
            logger.warning("Not all containers are ready, but starting anyway")

        # Initialize with current data
        update_service_status()
        update_agent_logs()

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
