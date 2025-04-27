import logging
import os
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Configuration
STATUS_DIR = os.environ.get("STATUS_DIR", "/tmp/status")
LATENCY_FILE_NAME = os.environ.get("LATENCY_FILE_NAME", "latency.txt")
CHECK_INTERVAL_S = int(os.environ.get("CHECK_INTERVAL_S", "5"))

LATENCY_FILE_PATH = os.path.join(STATUS_DIR, LATENCY_FILE_NAME)


def main() -> None:
    logging.info("--- Kafka Demo UI (Latency Monitor) --- ")
    logging.info(f"Monitoring latency file: {LATENCY_FILE_PATH}")
    logging.info(f"Check interval: {CHECK_INTERVAL_S}s")

    last_latency = "N/A"

    while True:
        current_latency = "N/A"
        try:
            if os.path.exists(LATENCY_FILE_PATH):
                with open(LATENCY_FILE_PATH) as f:
                    content = f.read().strip()
                    if content:
                        # Basic validation - just check if it's numeric-like
                        try:
                            float(content)
                            current_latency = content
                        except ValueError:
                            logging.warning(
                                "Invalid content in latency file: '%s'", content
                            )
                    else:
                        logging.debug("Latency file is empty.")
            else:
                logging.debug("Latency file not found at %s", LATENCY_FILE_PATH)

            # Log only if latency changed
            if current_latency != last_latency:
                logging.info("Observed p99 Consumer Latency: %s ms", current_latency)
                last_latency = current_latency
            else:
                logging.debug("Latency unchanged: %s ms", current_latency)

        except Exception as e:
            logging.error("An error occurred in the monitor loop: %s", e)

        time.sleep(CHECK_INTERVAL_S)


if __name__ == "__main__":
    main()
