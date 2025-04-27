import json
import logging
import os
import subprocess
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Configuration
STATUS_DIR = os.environ.get("STATUS_DIR", "/tmp/status")
LATENCY_FILE_PATH = os.path.join(STATUS_DIR, os.environ.get("LATENCY_FILE_NAME", "latency.txt"))
PRODUCER_STATS_FILE_PATH = os.path.join(STATUS_DIR, os.environ.get("PRODUCER_STATS_FILE_NAME", "producer_stats.txt"))
TARGET_LATENCY_MS = os.environ.get("TARGET_LATENCY_MS", "10.0") # Get target latency from env
CONFIGMAP_NAME = os.environ.get("CONFIGMAP_NAME", "kafka-latency-metrics")
CONFIGMAP_NAMESPACE = os.environ.get("CONFIGMAP_NAMESPACE", "kafka")
# Define keys for ConfigMap
LATENCY_CM_KEY = os.environ.get("LATENCY_CM_KEY", "p99_latency_ms")
TARGET_LATENCY_CM_KEY = os.environ.get("TARGET_LATENCY_CM_KEY", "target_latency_ms")
PRODUCER_TARGET_RATE_CM_KEY = os.environ.get("PRODUCER_TARGET_RATE_CM_KEY", "producer_target_rate")
CHECK_INTERVAL_S = int(os.environ.get("CHECK_INTERVAL_S", "5"))
KUBECTL_CMD = os.environ.get("KUBECTL_CMD", "kubectl")  # Allow overriding kubectl path

last_known_data: dict[str, str] = {}


def update_configmap_with_kubectl(data_to_update: dict) -> None:
    """Updates the ConfigMap using kubectl patch with the provided data."""
    global last_known_data

    # Check if data has actually changed
    if data_to_update == last_known_data:
        logging.debug("Metrics unchanged (%s). Skipping ConfigMap update.", data_to_update)
        return

    logging.info(
        "Metrics changed to %s. Updating ConfigMap %s/%s via kubectl...",
        data_to_update,
        CONFIGMAP_NAMESPACE,
        CONFIGMAP_NAME,
    )

    # Prepare the patch data as a JSON string - update only changed keys?
    # For simplicity, patch the whole data structure for now.
    patch_data = {"data": data_to_update}
    patch_str = json.dumps(patch_data)

    # Construct the kubectl command
    cmd = [
        KUBECTL_CMD,
        "patch",
        "configmap",
        CONFIGMAP_NAME,
        "-n",
        CONFIGMAP_NAMESPACE,
        "--type=merge",
        "-p",
        patch_str,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        logging.info("kubectl patch successful: %s", result.stdout.strip())
        last_known_data = data_to_update.copy() # Store the updated data
    except subprocess.CalledProcessError as e:
        logging.error(
            "kubectl patch failed (Exit code: %d): %s", e.returncode, e.stderr.strip()
        )
    except FileNotFoundError:
        logging.error(
            "kubectl command ('%s') not found. Ensure it is in PATH.", KUBECTL_CMD
        )
    except Exception as e:
        logging.error("An unexpected error occurred running kubectl: %s", e)

def parse_producer_stats(file_path: str) -> str:
    """Reads producer stats file and extracts target rate."""
    target_rate = "N/A"
    try:
        if os.path.exists(file_path):
            with open(file_path) as f:
                content = f.read().strip()
                if content:
                    # Expected format: target_rate=X, actual_rate=Y, size=Z
                    stats = {}
                    for item in content.split(","):
                        parts = item.strip().split("=", 1)
                        if len(parts) == 2:
                            stats[parts[0].strip()] = parts[1].strip()
                    target_rate = stats.get("target_rate", "Parse Error")
                else:
                    target_rate = "Empty File"
        else:
            target_rate = "Not Found"
    except Exception as e:
        logging.error(f"Error reading/parsing producer stats {file_path}: {e}")
        target_rate = "Read Error"
    return target_rate


def read_latency(file_path: str) -> str:
    """Reads and validates latency from the file."""
    latency = "N/A"
    try:
        if os.path.exists(file_path):
            with open(file_path) as f:
                content = f.read().strip()
                if content:
                    try:
                        # Basic validation
                        float(content)
                        latency = content
                    except ValueError:
                        logging.warning(
                            "Invalid numeric content in latency file: %s", content
                        )
                        latency = "Invalid Data"
                else:
                    latency = "Empty File"
        else:
            latency = "Not Found"
    except Exception as e:
        logging.error(f"Error reading latency file {file_path}: {e}")
        latency = "Read Error"
    return latency

def main() -> None:
    logging.info("--- Metrics Reporter (via kubectl) --- ")
    logging.info(f"Monitoring Latency File: {LATENCY_FILE_PATH}")
    logging.info(f"Monitoring Producer Stats File: {PRODUCER_STATS_FILE_PATH}")
    logging.info(
        f"Updating ConfigMap: {CONFIGMAP_NAMESPACE}/{CONFIGMAP_NAME}"
    )
    logging.info(f"  Keys: {LATENCY_CM_KEY}, {TARGET_LATENCY_CM_KEY}, {PRODUCER_TARGET_RATE_CM_KEY}")
    logging.info(f"Target Latency: {TARGET_LATENCY_MS} ms")
    logging.info(f"Check interval: {CHECK_INTERVAL_S}s")
    logging.info(f"Using kubectl command: {KUBECTL_CMD}")

    while True:
        try:
            # Read current metrics
            current_p99_latency = read_latency(LATENCY_FILE_PATH)
            current_producer_target_rate = parse_producer_stats(PRODUCER_STATS_FILE_PATH)

            # Prepare data payload for ConfigMap
            data_payload = {
                LATENCY_CM_KEY: current_p99_latency,
                TARGET_LATENCY_CM_KEY: TARGET_LATENCY_MS, # Use value from env
                PRODUCER_TARGET_RATE_CM_KEY: current_producer_target_rate
            }

            # Update ConfigMap if data changed
            update_configmap_with_kubectl(data_payload)

        except Exception as e:
            logging.error("An error occurred in the main loop: %s", e)

        time.sleep(CHECK_INTERVAL_S)


if __name__ == "__main__":
    main()
