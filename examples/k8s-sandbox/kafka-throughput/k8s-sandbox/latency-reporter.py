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
LATENCY_FILE_PATH = os.environ.get("LATENCY_FILE_PATH", "/tmp/status/latency.txt")
CONFIGMAP_NAME = os.environ.get("CONFIGMAP_NAME", "kafka-latency-metrics")
CONFIGMAP_NAMESPACE = os.environ.get("CONFIGMAP_NAMESPACE", "kafka")
CONFIGMAP_KEY = os.environ.get("CONFIGMAP_KEY", "p99_latency_ms")
CHECK_INTERVAL_S = int(os.environ.get("CHECK_INTERVAL_S", "5"))
KUBECTL_CMD = os.environ.get("KUBECTL_CMD", "kubectl")  # Allow overriding kubectl path

last_known_latency = None


def update_configmap_with_kubectl(latency_value: str) -> None:
    """Updates the ConfigMap using kubectl patch."""
    global last_known_latency
    if latency_value == last_known_latency:
        logging.debug(
            "Latency unchanged (%s). Skipping ConfigMap update.", latency_value
        )
        return

    logging.info(
        "Latency changed to %s. Updating ConfigMap %s/%s via kubectl...",
        latency_value,
        CONFIGMAP_NAMESPACE,
        CONFIGMAP_NAME,
    )

    # Prepare the patch data as a JSON string
    patch_data = {"data": {CONFIGMAP_KEY: latency_value}}
    patch_str = json.dumps(patch_data)

    # Construct the kubectl command
    cmd = [
        KUBECTL_CMD,
        "patch",
        "configmap",
        CONFIGMAP_NAME,
        "-n",
        CONFIGMAP_NAMESPACE,
        "--type=merge",  # Use merge patch for simplicity
        "-p",
        patch_str,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        logging.info("kubectl patch successful: %s", result.stdout.strip())
        last_known_latency = latency_value
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


def main() -> None:
    logging.info("--- Latency Reporter (via kubectl) --- ")
    logging.info(f"Monitoring file: {LATENCY_FILE_PATH}")
    logging.info(
        f"Updating ConfigMap: {CONFIGMAP_NAMESPACE}/{CONFIGMAP_NAME}[{CONFIGMAP_KEY}]"
    )
    logging.info(f"Check interval: {CHECK_INTERVAL_S}s")
    logging.info(f"Using kubectl command: {KUBECTL_CMD}")

    while True:
        current_latency = "N/A"
        try:
            if os.path.exists(LATENCY_FILE_PATH):
                with open(LATENCY_FILE_PATH) as f:
                    content = f.read().strip()
                    if content:
                        try:
                            # Basic validation
                            float(content)
                            current_latency = content
                        except ValueError:
                            logging.warning(
                                "Invalid numeric content in latency file: %s", content
                            )
                    else:
                        logging.debug("Latency file is empty.")
            else:
                logging.debug("Latency file not found: %s", LATENCY_FILE_PATH)

            update_configmap_with_kubectl(current_latency)

        except Exception as e:
            logging.error("An error occurred in the main loop: %s", e)

        time.sleep(CHECK_INTERVAL_S)


if __name__ == "__main__":
    main()
