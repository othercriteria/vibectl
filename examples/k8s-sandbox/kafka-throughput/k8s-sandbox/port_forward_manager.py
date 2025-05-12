import logging
import os
import signal
import subprocess
import sys
import time
from typing import Any

# --- Configuration ---
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
KUBECTL_CMD = os.environ.get("KUBECTL_CMD", "kubectl")
TARGET_NAMESPACE = os.environ.get("TARGET_NAMESPACE", "kafka")
TARGET_SERVICE = os.environ.get("TARGET_SERVICE", "kafka-service")
LOCAL_PORT = os.environ.get("LOCAL_PORT", "9092")
REMOTE_PORT = os.environ.get("REMOTE_PORT", "9092")
KUBECTL_LOG_FILE = os.environ.get("KUBECTL_LOG_FILE", "/tmp/kubectl-port-forward.log")
RETRY_DELAY_SECONDS = int(os.environ.get("RETRY_DELAY_SECONDS", "10"))
PKILL_PATTERN = (
    f"kubectl port-forward.*-n "
    f"{TARGET_NAMESPACE}.*svc/{TARGET_SERVICE}.*{LOCAL_PORT}:{REMOTE_PORT}"
)

# --- Logging Setup ---
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("PortForwardManager")

# --- Global variable for the child process ---
kubectl_process: subprocess.Popen[Any] | None = None


def signal_handler(signum: int, frame: Any) -> None:
    """Gracefully terminate the kubectl port-forward process."""
    logger.info(f"Signal {signum} received. Terminating port-forward process...")
    if kubectl_process and kubectl_process.poll() is None:
        logger.info(
            f"Sending SIGTERM to kubectl process (PID: {kubectl_process.pid})..."
        )
        kubectl_process.terminate()
        try:
            kubectl_process.wait(timeout=5)  # Wait for termination
            logger.info("kubectl process terminated gracefully.")
        except subprocess.TimeoutExpired:
            logger.warning(
                "kubectl process did not terminate in time. Sending SIGKILL..."
            )
            kubectl_process.kill()
            logger.warning("kubectl process killed.")
    sys.exit(0)


def kill_existing_port_forwards() -> None:
    """Attempt to kill any existing port-forward processes matching the pattern."""
    logger.info(f"Attempting to kill existing port-forwards matching: {PKILL_PATTERN}")
    try:
        # Use pkill -f to match against the full command line
        # We need to be careful not to kill ourself if script is run with similar args
        # However, pkill usually targets other processes.
        kill_cmd = ["pkill", "-f", PKILL_PATTERN]
        result = subprocess.run(kill_cmd, capture_output=True, text=True)
        if result.returncode == 0:
            logger.info("Successfully sent kill signal to matching processes.")
        elif result.returncode == 1:  # pkill returns 1 if no processes matched
            logger.info(
                "No existing port-forward processes found matching the pattern."
            )
        else:  # Other error
            logger.warning(
                f"pkill command finished with exit code {result.returncode}. "
                f"Stderr: {result.stderr.strip()}"
            )
    except FileNotFoundError:
        logger.error("pkill command not found. Cannot kill existing port-forwards.")
    except Exception as e:
        logger.error(f"Error trying to kill existing port-forwards: {e}")
    time.sleep(1)  # Give a moment for processes to terminate


def start_port_forward() -> bool:
    """Starts the kubectl port-forward command as a subprocess."""
    global kubectl_process

    cmd = [
        KUBECTL_CMD,
        "port-forward",
        "-v=7",  # Keep high verbosity for kubectl logs
        "-n",
        TARGET_NAMESPACE,
        f"svc/{TARGET_SERVICE}",
        f"{LOCAL_PORT}:{REMOTE_PORT}",
        "--address=0.0.0.0",
    ]
    logger.info(f"Starting kubectl port-forward: {' '.join(cmd)}")
    logger.info(f"kubectl output will be logged to: {KUBECTL_LOG_FILE}")

    try:
        with open(KUBECTL_LOG_FILE, "ab") as klogf:  # Append binary mode
            # Start the process
            kubectl_process = subprocess.Popen(cmd, stdout=klogf, stderr=klogf)
        logger.info(
            f"kubectl port-forward process started with PID: {kubectl_process.pid}"
        )
        return True
    except FileNotFoundError:
        logger.error(
            f"'{KUBECTL_CMD}' command not found. Please ensure "
            "it is installed and in PATH."
        )
        return False
    except Exception as e:
        logger.error(f"Failed to start kubectl port-forward: {e}")
        return False


def main_loop() -> None:
    """Main loop to manage the port-forwarding process."""
    global kubectl_process

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info("Port Forward Manager started.")
    logger.info(
        f"  Target: {TARGET_NAMESPACE}/svc/{TARGET_SERVICE}:{REMOTE_PORT} -> "
        f"localhost:{LOCAL_PORT}"
    )
    logger.info(f"  Retry Delay: {RETRY_DELAY_SECONDS}s")

    while True:
        kill_existing_port_forwards()  # Clean up before starting

        if not start_port_forward():
            logger.error(
                "Failed to start port-forward. Retrying in {RETRY_DELAY_SECONDS}s..."
            )
            time.sleep(RETRY_DELAY_SECONDS)
            continue

        # Monitor the process
        if kubectl_process:
            while kubectl_process.poll() is None:  # While process is running
                try:
                    time.sleep(1)  # Check status every second
                except KeyboardInterrupt:  # Allow Ctrl+C to trigger signal handler
                    logger.info("KeyboardInterrupt received, initiating shutdown...")
                    signal_handler(signal.SIGINT, None)  # type: ignore

            # If we reach here, kubectl_process.poll() is not None, meaning terminated
            exit_code = kubectl_process.returncode
            logger.warning(
                f"kubectl port-forward process (PID: {kubectl_process.pid}) "
                f"terminated with exit code: {exit_code}."
            )
        else:  # Should not happen if start_port_forward returned True
            logger.error(
                "kubectl_process is None after a successful start attempt. "
                "This is unexpected."
            )

        logger.info(f"Restarting port-forward in {RETRY_DELAY_SECONDS} seconds...")
        time.sleep(RETRY_DELAY_SECONDS)


if __name__ == "__main__":
    # Basic check for essential env vars (can be expanded)
    if not all([TARGET_NAMESPACE, TARGET_SERVICE, LOCAL_PORT, REMOTE_PORT]):
        logger.error(
            "One or more required environment variables "
            "(TARGET_NAMESPACE, TARGET_SERVICE, LOCAL_PORT, REMOTE_PORT) "
            "are not set."
        )
        sys.exit(1)

    main_loop()
