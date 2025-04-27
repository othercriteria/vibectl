import logging
import os
import subprocess
import time
from typing import Any  # Import Any

import docker
import urllib3  # Import urllib3
from apscheduler.schedulers.background import (
    BackgroundScheduler,  # type: ignore[import-untyped]
)
from docker.errors import APIError, NotFound
from flask import Flask, Response, jsonify, render_template, request  # Import request
from flask_socketio import SocketIO, emit
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

STATUS_DIR = "/tmp/status"
LATENCY_FILE = os.path.join(STATUS_DIR, "latency.txt")
PRODUCER_STATS_FILE = os.path.join(STATUS_DIR, "producer_stats.txt")
CONSUMER_STATS_FILE = os.path.join(STATUS_DIR, "consumer_stats.txt")
VIBECTL_LOG_FILE = os.path.join(
    STATUS_DIR, "vibectl_agent.log"
)  # Added for potential future use
NAMESPACE = "default"  # Assuming default namespace for now
CHECK_INTERVAL_S = 5  # Interval for scheduler checks

# Define staleness threshold (e.g., 3 times the check interval)
STALENESS_THRESHOLD_S = CHECK_INTERVAL_S * 3

# Add variable for number of log lines to display
VIBECTL_LOG_LINES = 50

# --- Global State ---
# Store the latest fetched data here
latest_data = {
    "latency": "N/A",
    "producer_rate": "N/A",
    "producer_size": "N/A",
    "kafka_health": "N/A",
    "producer_health": "N/A",
    "consumer_health": "N/A",
    "cluster_status": "N/A",
    "vibectl_logs": "N/A",  # Placeholder for vibectl logs
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
            # Handle specific case where file exists but is invalid/empty
            logger.exception(f"Error loading kubeconfig from {kubeconfig_path}: {ce}")
        except FileNotFoundError:
            # TODO: remove? Case is handled by the os.path.exists check above...
            logger.error(f"Shared kubeconfig {kubeconfig_path} not found.")
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
            timeout=2,  # Add timeout
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
        # Simplified check using a mapping
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


def read_file_content(file_path: str) -> str:
    """Safely reads content from a file."""
    try:
        if os.path.exists(file_path):
            # Limit file read size to prevent large files from causing issues
            with open(file_path) as f:
                content = f.read(1024 * 10)  # Read max 10KB
                if len(content) == 1024 * 10:
                    logger.warning(f"File {file_path} might be truncated (read 10KB).")
                return content.strip()
        else:
            # logger.warning(f"File not found: {file_path}") # Too noisy
            return "N/A"
    except Exception as e:
        logger.error(f"Error reading {file_path}: {e}")
        return "Error"


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


def update_status_data() -> None:
    """Scheduled job to fetch all status data and update global state."""
    global latest_data
    logger.info("Updating status data...")
    start_time = time.time()

    # Read raw data
    latency_raw = read_file_content(LATENCY_FILE)
    producer_stats_raw = read_file_content(PRODUCER_STATS_FILE)
    consumer_stats_raw = read_file_content(CONSUMER_STATS_FILE)
    vibectl_logs = read_log_tail(VIBECTL_LOG_FILE, VIBECTL_LOG_LINES)

    # Initialize values
    producer_target_rate = "N/A"
    producer_actual_rate = "N/A"
    producer_size = "N/A"
    latency = "N/A"
    consumer_rate = "N/A"

    # Process latency
    if latency_raw not in ["N/A", "Error", "Empty File", "No File", "Read Error"]:
        latency = latency_raw  # Keep as string for display
    else:
        latency = latency_raw  # Use the error status directly

    # Process producer stats
    producer_file_status = check_file_freshness(
        PRODUCER_STATS_FILE, STALENESS_THRESHOLD_S
    )
    if producer_file_status == "Healthy":  # Only parse if file is fresh
        if producer_stats_raw and producer_stats_raw not in [
            "N/A",
            "Error",
            "Empty File",
            "Read Error",
        ]:
            try:
                # Expected format: "target_rate=X, actual_rate=Y, size=Z"
                # More robust parsing: split by comma, then find first '='
                stats = {}
                for item in producer_stats_raw.split(","):
                    parts = item.strip().split("=", 1)  # Split only on the first '='
                    if len(parts) == 2:
                        key, value = parts
                        stats[key.strip()] = value.strip()  # Store cleaned key/value
                    else:
                        logger.warning(f"Skipping invalid producer stat item: '{item}'")

                producer_target_rate = stats.get("target_rate", "Parse Error (target)")
                producer_actual_rate = stats.get("actual_rate", "Parse Error (actual)")
                producer_size = stats.get("size", "Parse Error (size)")

                # Check if any keys were missing after successful parse
                if "Parse Error" in [
                    producer_target_rate,
                    producer_actual_rate,
                    producer_size,
                ]:
                    logger.warning(
                        f"Parsed producer stats '{stats}' but some keys were missing."
                    )

            except Exception as e:  # Catches other unexpected errors during parsing
                logger.error(
                    f"Error parsing producer stats '{producer_stats_raw}': {e}"
                )
                producer_target_rate = "Parse Error (Exception)"
                producer_actual_rate = "Parse Error (Exception)"
                producer_size = "Parse Error (Exception)"
        elif producer_stats_raw == "Empty File":
            producer_target_rate = "Empty File"
            producer_actual_rate = "Empty File"
            producer_size = "Empty File"
        elif producer_stats_raw == "Error" or producer_stats_raw == "Read Error":
            producer_target_rate = "Read Error"
            producer_actual_rate = "Read Error"
            producer_size = "Read Error"
        else:  # Includes "N/A" or unexpected content
            producer_target_rate = "No Data"
            producer_actual_rate = "No Data"
            producer_size = "No Data"
    else:  # File is "Not Found", "Stale", or "Error Checking"
        producer_target_rate = producer_file_status
        producer_actual_rate = producer_file_status
        producer_size = producer_file_status

    # Process consumer stats
    consumer_file_status = check_file_freshness(
        CONSUMER_STATS_FILE, STALENESS_THRESHOLD_S
    )
    if consumer_file_status == "Healthy":  # Only parse if file is fresh
        if consumer_stats_raw and consumer_stats_raw not in [
            "N/A",
            "Error",
            "Empty File",
            "Read Error",
        ]:
            try:
                # Expected format: "rate=X.XX"
                if "=" in consumer_stats_raw:
                    key, value = consumer_stats_raw.strip().split("=", 1)
                    if key.strip() == "rate":
                        consumer_rate = value.strip()  # Keep as string for display
                    else:
                        logger.warning(f"Unexpected key in consumer stats: '{key}'")
                        consumer_rate = "Format Error (key)"
                else:
                    consumer_rate = "Format Error (=)"
            except ValueError as ve:
                logger.error(
                    f"Error parsing consumer stats '{consumer_stats_raw}': {ve}"
                )
                consumer_rate = "Format Error (split)"
            except Exception as e:
                logger.error(
                    f"Error parsing consumer stats '{consumer_stats_raw}': {e}"
                )
                consumer_rate = "Parse Error"
        elif consumer_stats_raw == "Empty File":
            consumer_rate = "Empty File"
        elif consumer_stats_raw == "Error" or consumer_stats_raw == "Read Error":
            consumer_rate = "Read Error"
        else:  # Includes "N/A" or unexpected content
            consumer_rate = "No Data"
    else:  # File is "Not Found", "Stale", or "Error Checking"
        consumer_rate = consumer_file_status

    # Get health status based on Docker container status
    producer_container_health = get_container_health("kafka-producer")
    consumer_container_health = get_container_health("kafka-consumer")

    # Get status from Kubernetes
    kafka_health = get_statefulset_status(name="kafka-controller", namespace="kafka")
    cluster_status = get_cluster_status()

    new_data = {
        "latency": latency,  # Use processed latency
        "producer_target_rate": producer_target_rate,
        "producer_actual_rate": producer_actual_rate,
        "producer_size": producer_size,
        "consumer_rate": consumer_rate,  # Use processed consumer rate
        "kafka_health": kafka_health,
        "producer_health": producer_container_health,
        "consumer_health": consumer_container_health,
        "producer_file_status": producer_file_status,  # Keep file status separate
        "consumer_file_status": consumer_file_status,  # Keep file status separate
        "cluster_status": cluster_status,
        "vibectl_logs": vibectl_logs,
        "last_updated": time.time(),
    }

    latest_data = new_data
    socketio.emit("status_update", latest_data)
    logger.info(f"Status update emitted. Fetch took {time.time() - start_time:.2f}s")


# --- Flask Routes ---


@app.route("/")
def index() -> Any:
    """Serves the main UI page."""
    # Renders the template, which will connect via SocketIO
    return render_template("index.html")


# Optional: Keep API endpoint for direct access/debugging
@app.route("/status")
def get_status_api() -> Response:
    """API endpoint to provide latest status data."""
    return jsonify(latest_data)


# --- SocketIO Event Handlers ---


@socketio.on("connect")
def handle_connect() -> None:
    """Send current state to newly connected client."""
    # Use request.sid directly, it's available in the SocketIO context
    logger.info(f"Client connected: {request.sid}")
    # Send the most recent data immediately
    emit("status_update", latest_data)


@socketio.on("disconnect")
def handle_disconnect() -> None:
    # Use request.sid directly, it's available in the SocketIO context
    logger.info(f"Client disconnected: {request.sid}")


# --- Main Execution ---

if __name__ == "__main__":
    # Add the job to the scheduler
    scheduler.add_job(
        update_status_data, "interval", seconds=CHECK_INTERVAL_S, id="status_update_job"
    )
    # Start the scheduler
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

    # Shut down the scheduler when exiting
    scheduler.shutdown()
