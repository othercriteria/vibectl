import logging
import os
import time
from typing import Any  # Import Any

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, Response, jsonify, render_template, request  # Import request
from flask_socketio import SocketIO, emit
from kubernetes import client, config
from kubernetes.client.rest import ApiException

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
VIBECTL_LOG_FILE = os.path.join(
    STATUS_DIR, "vibectl_agent.log"
)  # Added for potential future use
NAMESPACE = "default"  # Assuming default namespace for now
CHECK_INTERVAL_S = 5  # Interval for scheduler checks

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


# Try initial client setup
initialize_k8s_client()

# --- Data Fetching Functions ---


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

    latency = read_file_content(LATENCY_FILE)
    producer_stats_raw = read_file_content(PRODUCER_STATS_FILE)
    # vibectl_logs = read_file_content(VIBECTL_LOG_FILE)

    # Parse producer stats
    producer_rate = "N/A"
    producer_size = "N/A"
    if producer_stats_raw not in ["N/A", "Error"]:
        try:
            stats = dict(item.split("=") for item in producer_stats_raw.split(", "))
            producer_rate = stats.get("rate", "N/A")
            producer_size = stats.get("size", "N/A")
        except Exception as e:
            logger.error(f"Error parsing producer stats '{producer_stats_raw}': {e}")
            producer_rate = "Parse Error"
            producer_size = "Parse Error"

    # Get status from Kubernetes (use actual selectors)
    # Determine actual label selectors by inspecting the deployments/statefulsets
    # For now, using placeholder selectors
    kafka_health = get_statefulset_status(name="kafka-controller", namespace="kafka")
    # TODO: Implement health check for producer container (e.g., using Docker API)
    producer_health = "N/A - TODO"
    # TODO: Implement health check for consumer container (e.g., using Docker API)
    consumer_health = "N/A - TODO"
    cluster_status = get_cluster_status()

    new_data = {
        "latency": latency,
        "producer_rate": producer_rate,
        "producer_size": producer_size,
        "kafka_health": kafka_health,
        "producer_health": producer_health,
        "consumer_health": consumer_health,
        "cluster_status": cluster_status,
        # 'vibectl_logs': vibectl_logs,
        "last_updated": time.time(),
    }

    # TODO: Only emit if data has changed significantly (optional, reduces noise)
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
    logger.info(f"Client connected: {request.sid}")
    # Send the most recent data immediately
    emit("status_update", latest_data)


@socketio.on("disconnect")
def handle_disconnect() -> None:
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
