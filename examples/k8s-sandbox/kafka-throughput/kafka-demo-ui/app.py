import logging
import os
import subprocess
import time
from typing import Any  # Import Any

import docker  # type: ignore
import urllib3  # Import urllib3
from apscheduler.schedulers.background import (  # type: ignore
    BackgroundScheduler,
)
from docker.errors import APIError, NotFound  # type: ignore
from flask import Flask, Response, jsonify, render_template, request  # Import request
from flask_socketio import SocketIO, emit  # type: ignore
from kubernetes import client, config
from kubernetes.client.rest import ApiException

# Disable insecure request warnings for K8s client
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
# Secret key is needed for Flask sessions potentially used by SocketIO
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key")
socketio = SocketIO(app, cors_allowed_origins="*")
scheduler = BackgroundScheduler()

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

STATUS_DIR = os.environ.get("STATUS_DIR", "/tmp/status")
PRODUCER_STATS_FILE = os.path.join(STATUS_DIR, "producer_stats.txt")
VIBECTL_LOG_FILE = os.path.join(STATUS_DIR, "vibectl_agent.log")

# New file paths from latency-reporter.py
E2E_LATENCY_FILE_PATH = os.path.join(STATUS_DIR, "e2e_latency_ms.txt")
UI_PRODUCER_TARGET_RATE_FILE_PATH = os.path.join(
    STATUS_DIR, "producer_target_rate_value.txt"
)
UI_PRODUCER_ACTUAL_RATE_FILE_PATH = os.path.join(
    STATUS_DIR, "producer_actual_rate_value.txt"
)
UI_CONSUMER_ACTUAL_RATE_FILE_PATH = os.path.join(
    STATUS_DIR, "consumer_actual_rate_value.txt"
)
TARGET_LATENCY_FILE_PATH = os.path.join(STATUS_DIR, "target_latency_ms.txt")

CHECK_INTERVAL_S = 5  # Interval for scheduler checks

# Define staleness threshold (e.g., 3 times the check interval)
STALENESS_THRESHOLD_S = CHECK_INTERVAL_S * 3

# Add variable for number of log lines to display
VIBECTL_LOG_LINES = 50

# --- Global State ---
# Store the latest fetched data here
latest_data = {
    "latency": "N/A",
    "producer_target_rate": "N/A",
    "producer_actual_rate": "N/A",
    "producer_size": "N/A",
    "consumer_actual_rate": "N/A",
    "target_latency_ms": "N/A",
    "kafka_health": "N/A",
    "producer_health": "N/A",
    "consumer_health": "N/A",
    "cluster_status": "N/A",
    "vibectl_logs": "N/A",
    "last_updated": time.time(),
}

# --- Kubernetes Client Setup ---
k8s_client_v1: client.CoreV1Api | None = None
k8s_client_apps_v1: client.AppsV1Api | None = None  # Add AppsV1Api client

# --- Docker Client Setup ---
docker_client: docker.DockerClient | None = None


def initialize_k8s_client() -> bool:
    """Tries to initialize the Kubernetes client."""
    global k8s_client_v1, k8s_client_apps_v1  # Include AppsV1Api
    if k8s_client_v1 and k8s_client_apps_v1:  # Check both clients
        return True
    try:
        config.load_incluster_config()
        logger.info("Loaded in-cluster Kubernetes config.")
        k8s_client_v1 = client.CoreV1Api()
        k8s_client_apps_v1 = client.AppsV1Api()  # Initialize AppsV1Api
        return True
    except config.ConfigException:
        logger.warning("Failed to load in-cluster config, trying local kubeconfig...")
        try:
            # Explicitly load kubeconfig provided by k8s-sandbox via the shared volume
            kubeconfig_path = "/tmp/status/k3d_kubeconfig"
            if not os.path.exists(kubeconfig_path):
                logger.warning(
                    f"Kubeconfig {kubeconfig_path} not found yet. Will retry later."
                )
                return False  # Indicate failure, but it might appear later

            config.load_kube_config(config_file=kubeconfig_path)
            logger.info(f"Loaded Kubernetes config from {kubeconfig_path}.")
            k8s_client_v1 = client.CoreV1Api()
            k8s_client_apps_v1 = client.AppsV1Api()  # Initialize AppsV1Api
            return True
        except config.ConfigException as ce:
            logger.exception(f"Error loading kubeconfig from {kubeconfig_path}: {ce}")
        except Exception as e:
            logger.error(
                f"Unexpected error loading kubeconfig from {kubeconfig_path}: {e}"
            )

    k8s_client_v1 = None  # Ensure it's None if all attempts fail
    k8s_client_apps_v1 = None
    return False


def initialize_docker_client() -> bool:
    """Initializes the Docker client."""
    global docker_client
    if docker_client:
        return True
    try:
        # Assumes docker socket is mounted at /var/run/docker.sock
        docker_client = docker.from_env()
        # Test connection
        docker_client.ping()
        logger.info("Docker client initialized successfully.")
        return True
    except APIError as e:
        logger.error(f"Error connecting to Docker API: {e}. Socket mounted/accessible?")
    except Exception as e:
        logger.error(f"Unexpected error initializing Docker client: {e}")
    docker_client = None
    return False


# Try initial clients setup
initialize_k8s_client()
initialize_docker_client()

# --- Data Fetching Functions ---


def read_log_tail(file_path: str, lines: int) -> str:
    """Reads the last N lines of a file using the 'tail' command."""
    if not os.path.exists(file_path):
        return "Log file not found"
    try:
        # Use subprocess to call tail, more robust for large files
        result = subprocess.run(
            ["tail", "-n", str(lines), file_path],
            capture_output=True,
            text=True,
            check=False,  # Don't throw error if tail fails (e.g., empty file)
            timeout=2,
        )
        if result.returncode != 0:
            # Handle cases like empty file or read errors
            if "file is empty" in result.stderr.lower():
                return "Log file is empty"
            logger.error(f"Error reading log tail for {file_path}: {result.stderr}")
            return f"Error reading log (Code: {result.returncode})"
        return result.stdout.strip()

    except subprocess.TimeoutExpired:
        logger.error(f"Timeout reading log tail for {file_path}")
        return "Error reading log (Timeout)"
    except Exception as e:
        logger.error(f"Unexpected error reading log tail for {file_path}: {e}")
        return "Error reading log"


def get_container_health(container_name: str) -> str:
    """Gets the health status of a Docker container by name."""
    if not docker_client:
        if not initialize_docker_client():
            return "Docker Client Error"
        if not docker_client:  # Still None after re-init attempt
            return "Docker Client Unavailable"

    try:
        container = docker_client.containers.get(container_name)
        status = container.status
        status_map = {
            "running": "Running",
            "restarting": "Restarting",
            "paused": "Paused",
        }
        return status_map.get(status, f"Exited ({status})")

    except NotFound:
        logger.warning(f"Container '{container_name}' not found.")
        return "Not Found"
    except APIError as e:
        logger.error(f"Docker API error getting container {container_name}: {e}")
        return "API Error"
    except Exception as e:
        logger.error(f"Unexpected error getting container {container_name}: {e}")
        return "Error"


def check_file_freshness(file_path: str, max_age_seconds: float) -> str:
    """Checks if a file exists and was modified recently."""
    if not os.path.exists(file_path):
        return "Not Found"
    try:
        mtime = os.path.getmtime(file_path)
        age = time.time() - mtime
        if age > max_age_seconds:
            return f"Stale (Updated {age:.0f}s ago)"
        else:
            return "Healthy"
    except Exception as e:
        logger.error(f"Error checking freshness of {file_path}: {e}")
        return "Error Checking"


def read_file_content(file_path: str, default_value: str = "N/A") -> str:
    """Safely reads content from a file."""
    try:
        if os.path.exists(file_path):
            with open(file_path) as f:
                content = f.read().strip()
                return content if content else default_value
        return default_value
    except Exception as e:
        logger.error(f"Error reading {file_path}: {e}")
        return default_value


def get_statefulset_status(name: str, namespace: str) -> str:
    """Gets the ready status of a StatefulSet (e.g., 'Ready: 1/1')."""
    if not k8s_client_apps_v1:
        if not initialize_k8s_client():
            return "K8s Client Not Initialized"
        if not k8s_client_apps_v1:
            return "K8s Client Error"
    try:
        sts = k8s_client_apps_v1.read_namespaced_stateful_set(
            name=name, namespace=namespace, _request_timeout=5
        )
        desired_replicas = sts.spec.replicas if sts.spec else 0
        # Use status.ready_replicas if available, otherwise default to 0
        ready_replicas = (
            sts.status.ready_replicas
            if sts.status and sts.status.ready_replicas is not None
            else 0
        )
        # Use status.current_replicas for total running pods
        current_replicas = (
            sts.status.current_replicas
            if sts.status and sts.status.current_replicas is not None
            else 0
        )

        if ready_replicas == desired_replicas and desired_replicas > 0:
            return f"Ready ({ready_replicas}/{desired_replicas})"
        elif current_replicas < desired_replicas:
            return f"Scaling ({current_replicas}/{desired_replicas})"
        elif ready_replicas < current_replicas:
            return f"Unhealthy ({ready_replicas}/{current_replicas} Ready)"
        else:
            return f"Running ({ready_replicas}/{desired_replicas})"

    except ApiException as e:
        if e.status == 404:
            logger.warning(
                f"StatefulSet '{name}' not found in namespace '{namespace}'."
            )
            return "Not Found"
        else:
            logger.error(
                f"API Error getting StatefulSet {name} in ns {namespace}: "
                f"{e.status} {e.reason}"
            )
            return "API Error"
    except Exception as e:
        logger.error(
            f"Unexpected error getting StatefulSet {name} in ns {namespace}: {e}"
        )
        return "Request Error"


def get_cluster_status() -> Any:
    """Gets a summary status of the Kubernetes cluster nodes and components."""
    if not k8s_client_v1:
        if not initialize_k8s_client():
            return "K8s Client Not Initialized"
        if not k8s_client_v1:
            return "K8s Client Error"

    node_summary = "Nodes: Error"
    component_summary = "Components: Error"

    try:
        # Node Status
        nodes = k8s_client_v1.list_node(timeout_seconds=5)
        ready_nodes = 0
        total_nodes = len(nodes.items)
        for node in nodes.items:
            if node.status and node.status.conditions:
                for condition in node.status.conditions:
                    if condition.type == "Ready" and condition.status == "True":
                        ready_nodes += 1
                        break
        node_summary = f"Nodes: {ready_nodes}/{total_nodes} Ready"
    except ApiException as e:
        logger.error(f"API Error getting node status: {e.status} {e.reason}")
        node_summary = "Nodes: API Error"
    except Exception as e:
        logger.error(f"Unexpected error getting node status: {e}")
        node_summary = "Nodes: Request Error"

    try:
        # Component Status (may not work on all clusters like k3d, handle gracefully)
        components = k8s_client_v1.list_component_status(timeout_seconds=5)
        healthy_components = 0
        total_components = 0
        if components.items:
            total_components = len(components.items)
            for component in components.items:
                if component.conditions:
                    for condition in component.conditions:
                        if (
                            condition.type in ["Healthy", "OK"]
                            and condition.status == "True"
                        ):
                            healthy_components += 1
                            break
        component_summary = (
            f"Components: {healthy_components}/{total_components} Healthy"
        )
    except ApiException as ae:
        if ae.status == 403:
            component_summary = "Components: Forbidden"
        elif ae.status == 404:
            component_summary = "Components: N/A"
            logger.info(
                "ComponentStatus API endpoint not found (common in k3d/minikube)."
            )
        else:
            component_summary = "Components: API Error"
            logger.warning(
                f"API Error getting component status: {ae.status} {ae.reason}"
            )
    except Exception as e:
        component_summary = "Components: Request Error"
        logger.error(f"Unexpected error getting component status: {e}")

    # Explicitly cast to string to satisfy mypy
    return str(f"{node_summary}, {component_summary}")


def get_producer_size_from_stats() -> str:
    """Reads producer_stats.txt for size only."""
    size = "N/A"
    try:
        if os.path.exists(PRODUCER_STATS_FILE):
            with open(PRODUCER_STATS_FILE) as f:
                content = f.read().strip()
                if content:
                    stats: dict[str, str] = {}
                    for item in content.split(","):
                        parts = item.strip().split("=", 1)
                        if len(parts) == 2:
                            stats[parts[0].strip()] = parts[1].strip()
                    size = stats.get("size", "Parse Error")
                else:
                    size = "Empty File"
        else:
            size = "Not Found"
    except Exception as e:
        logger.error(
            f"Error reading/parsing producer stats {PRODUCER_STATS_FILE} for size: {e}"
        )
        size = "Read Error"
    return size


def update_status_data() -> None:
    """Scheduled job to fetch all status data and update global state."""
    global latest_data
    logger.info("Updating status data...")
    start_time = time.time()

    e2e_latency_raw = read_file_content(E2E_LATENCY_FILE_PATH)
    producer_target_rate_raw = read_file_content(UI_PRODUCER_TARGET_RATE_FILE_PATH)
    # Producer actual rate is now read from its own dedicated file
    producer_actual_rate_from_file = read_file_content(
        UI_PRODUCER_ACTUAL_RATE_FILE_PATH
    )
    # Producer size is read by its own function
    producer_size_from_stats_file = get_producer_size_from_stats()
    consumer_actual_rate_from_file = read_file_content(
        UI_CONSUMER_ACTUAL_RATE_FILE_PATH
    )

    vibectl_logs = read_log_tail(VIBECTL_LOG_FILE, VIBECTL_LOG_LINES)

    # Process E2E latency from KMinion (via latency-reporter.py)
    latency = e2e_latency_raw  # Directly use the value (it handles N/A)

    # Process producer target rate (from latency-reporter.py)
    producer_target_rate = producer_target_rate_raw  # Directly use the value

    # Producer actual rate is now directly from its file (KMinion sourced)
    producer_actual_rate = producer_actual_rate_from_file  # Directly use the value

    # Producer size is from its dedicated function
    producer_size = producer_size_from_stats_file  # Directly use the value

    # Consumer actual rate is from its dedicated file (KMinion sourced)
    consumer_actual_rate = consumer_actual_rate_from_file  # Directly use the value

    # Get health status based on Docker container status
    producer_container_health = get_container_health("kafka-producer")
    consumer_container_health = get_container_health("kafka-consumer")

    # Get status from Kubernetes
    kafka_health = get_statefulset_status(name="kafka-controller", namespace="kafka")
    cluster_status = get_cluster_status()

    try:
        latest_data = {
            "latency": latency,
            "producer_target_rate": producer_target_rate,
            "producer_actual_rate": producer_actual_rate,
            "producer_size": producer_size,
            "consumer_actual_rate": consumer_actual_rate,
            "target_latency_ms": read_file_content(TARGET_LATENCY_FILE_PATH),
            "kafka_health": kafka_health,
            "producer_health": producer_container_health,
            "consumer_health": consumer_container_health,
            "cluster_status": cluster_status,
            "vibectl_logs": vibectl_logs,
            "last_updated": time.time(),
        }

        socketio.emit("status_update", latest_data)
        logger.info(
            f"Status update emitted. Fetch took {time.time() - start_time:.2f}s"
        )

    except Exception as e:
        logger.error(f"Error in update_status_data: {e}", exc_info=True)


# --- Flask Routes ---


@app.route("/")
def index() -> str:  # Explicitly str for render_template
    """Serves the main UI page."""
    # Renders the template, which will connect via SocketIO
    return render_template("index.html")


# Optional: Keep API endpoint for direct access/debugging
@app.route("/status")
def get_status_api() -> Response:  # Use Response type hint
    """API endpoint to provide latest status data."""
    return jsonify(latest_data)


# --- SocketIO Event Handlers ---


@socketio.on("connect")
def handle_connect() -> None:
    """Send current state to newly connected client."""
    # request.sid is available in the SocketIO context
    logger.info(f"Client connected: {request.sid}")  # type: ignore
    emit("status_update", latest_data)


@socketio.on("disconnect")
def handle_disconnect() -> None:
    # request.sid is available in the SocketIO context
    logger.info(f"Client disconnected: {request.sid}")  # type: ignore


# --- Main Execution ---

if __name__ == "__main__":
    scheduler.add_job(
        update_status_data, "interval", seconds=CHECK_INTERVAL_S, id="status_update_job"
    )
    scheduler.start()
    logger.info(f"Scheduler started. Updating status every {CHECK_INTERVAL_S} seconds.")

    # Start the Flask-SocketIO server
    # Use 0.0.0.0 to be accessible externally
    # Allow unsafe Werkzeug for compatibility if needed, but prefer Gunicorn/Eventlet
    # for production
    logger.info("Starting Flask-SocketIO server...")
    socketio.run(
        app, host="0.0.0.0", port=8081, debug=False, allow_unsafe_werkzeug=True
    )

    scheduler.shutdown()
