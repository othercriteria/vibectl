import logging
import os
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Configuration from environment variables
LATENCY_INPUT_FILE = os.environ.get("LATENCY_INPUT_FILE", "/tmp/status/latency.txt")
CHECK_INTERVAL_SECONDS = int(os.environ.get("CHECK_INTERVAL_SECONDS", "5"))


def read_latency(file_path: str) -> float | None:
    """Reads the latency value from the specified file."""
    content = ""  # Initialize content
    try:
        if os.path.exists(file_path):
            with open(file_path) as f:
                content = f.read().strip()
                if content:
                    return float(content)
                else:
                    logging.debug(f"Latency file {file_path} is empty.")
                    return None
        else:
            logging.debug(f"Latency file {file_path} does not exist yet.")
            return None
    except ValueError:
        logging.warning(
            f"Could not parse float from latency file {file_path}. "
            f"Content: '{content}'"
        )
        return None
    except Exception as e:
        logging.error(f"Error reading latency file {file_path}: {e}")
        return None


def main() -> None:
    logging.info("--- Kafka Throughput Demo Overseer --- ")
    logging.info(f"Monitoring latency file: {LATENCY_INPUT_FILE}")
    logging.info(f"Check interval: {CHECK_INTERVAL_SECONDS} seconds")

    try:
        while True:
            latency = read_latency(LATENCY_INPUT_FILE)
            if latency is not None:
                logging.info(f"Observed p99 Consumer Latency: {latency:.2f} ms")
                # TODO: Add logic here to potentially adjust producer rate
                # e.g., write to another file in /tmp/status/ that the producer reads
            else:
                logging.info("Latency data not available yet.")

            time.sleep(CHECK_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        logging.info("Overseer interrupted. Shutting down...")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
    finally:
        logging.info("Overseer stopped.")


if __name__ == "__main__":
    main()
