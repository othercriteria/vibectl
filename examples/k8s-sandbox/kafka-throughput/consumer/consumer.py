import json
import logging
import os
import statistics
import time
from collections import deque

from kafka import KafkaConsumer
from kafka.errors import NoBrokersAvailable

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Configuration from environment variables
KAFKA_BROKER = os.environ.get("KAFKA_BROKER", "kafka:9092")
KAFKA_TOPIC = os.environ.get("KAFKA_TOPIC", "throughput-topic")
CONSUMER_GROUP_ID = os.environ.get(
    "CONSUMER_GROUP_ID", "kafka-throughput-consumer-group"
)
CONSUMER_CLIENT_ID = os.environ.get("CONSUMER_CLIENT_ID", "kafka-throughput-consumer")
LATENCY_OUTPUT_FILE = os.environ.get("LATENCY_OUTPUT_FILE", "/tmp/status/latency.txt")
STATUS_DIR = os.path.dirname(LATENCY_OUTPUT_FILE)  # Infer status dir
CONSUMER_STATS_FILE = os.path.join(STATUS_DIR, "consumer_stats.txt")  # New stats file
LATENCY_WINDOW_SECONDS = int(
    os.environ.get("LATENCY_WINDOW_SECONDS", "10")
)  # Calculate p99 over this window
REPORTING_INTERVAL_SECONDS = int(
    os.environ.get("REPORTING_INTERVAL_SECONDS", "5")
)  # Write to file this often
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "5"))
INITIAL_RETRY_DELAY_S = int(os.environ.get("INITIAL_RETRY_DELAY_S", "5"))

# Use a deque to efficiently store recent latencies for percentile calculation
# Stores tuples of (timestamp, latency_ms)
recent_latencies: deque[tuple[float, float]] = deque()
last_report_time = time.time()
message_count_since_last_report = 0  # Counter for consumption rate


def calculate_latency(message_value: bytes) -> float | None:
    """Parses the message and calculates end-to-end latency in milliseconds."""
    try:
        payload = json.loads(message_value.decode("utf-8"))
        producer_timestamp = payload.get("timestamp")
        if producer_timestamp:
            current_time = time.time()
            latency_seconds = current_time - float(producer_timestamp)
            return latency_seconds * 1000  # Convert to milliseconds
        else:
            logging.warning("Message missing 'timestamp' field.")
            return None
    except json.JSONDecodeError:
        logging.warning("Failed to decode JSON message.")
        return None
    except Exception as e:
        logging.error(f"Error calculating latency: {e}")
        return None


def write_latency_to_file(latency_ms: float) -> None:
    """Writes the calculated latency to the specified output file."""
    try:
        # Ensure the directory exists
        output_dir = os.path.dirname(LATENCY_OUTPUT_FILE)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        # Write the latency value (simple overwrite)
        with open(LATENCY_OUTPUT_FILE, "w") as f:
            f.write(f"{latency_ms:.2f}")
        # logging.debug(
        #    f"Wrote p99 latency {latency_ms:.2f}ms to {LATENCY_OUTPUT_FILE}"
        # )
    except Exception as e:
        logging.error(f"Failed to write latency to {LATENCY_OUTPUT_FILE}: {e}")


def write_consumer_stats(rate: float) -> None:
    """Writes consumer stats (consumption rate) to a file."""
    stats_str = f"rate={rate:.2f}"
    try:
        # Directory should exist from write_latency_to_file
        with open(CONSUMER_STATS_FILE, "w") as f:
            f.write(stats_str)
    except Exception as e:
        logging.error(f"Error writing consumer stats to {CONSUMER_STATS_FILE}: {e}")


def calculate_and_report_metrics() -> None:
    """Calculates p99 latency and consumption rate, writes them to files."""
    global last_report_time, message_count_since_last_report  # Need to modify counter
    now = time.time()

    # Remove latencies older than the window
    cutoff_time = now - LATENCY_WINDOW_SECONDS
    while recent_latencies and recent_latencies[0][0] < cutoff_time:
        recent_latencies.popleft()

    # Calculate metrics if enough time has passed since last report
    time_since_last_report = now - last_report_time
    if time_since_last_report >= REPORTING_INTERVAL_SECONDS:
        # --- Latency Calculation ---
        if len(recent_latencies) > 10:  # Require a minimum number of samples
            latencies = [latency for _, latency in recent_latencies]
            p99_latency = statistics.quantiles(latencies, n=100)[98]  # 99th percentile
            logging.info(
                f"p99 latency ({len(latencies)} samples in {LATENCY_WINDOW_SECONDS}s): "
                f"{p99_latency:.2f} ms"
            )
            write_latency_to_file(p99_latency)
        else:
            logging.info(
                f"Not enough samples ({len(recent_latencies)}) in the last "
                f"{LATENCY_WINDOW_SECONDS}s to calculate p99 latency."
            )
            # Optionally write a placeholder or NaN
            # write_latency_to_file(float('nan'))

        # --- Consumption Rate Calculation ---
        consumption_rate = message_count_since_last_report / time_since_last_report
        logging.info(
            f"Consumption rate ({message_count_since_last_report} msgs in "
            f"{time_since_last_report:.2f}s): {consumption_rate:.2f} msg/s"
        )
        write_consumer_stats(consumption_rate)

        # --- Reset for next interval ---
        last_report_time = now
        message_count_since_last_report = 0  # Reset counter


def main() -> None:
    logging.info("--- Kafka Throughput Demo Consumer --- ")
    logging.info(f"Target Kafka Broker: {KAFKA_BROKER}")
    logging.info(f"Target Kafka Topic: {KAFKA_TOPIC}")
    logging.info(f"Consumer Group ID: {CONSUMER_GROUP_ID}")
    logging.info(f"Client ID: {CONSUMER_CLIENT_ID}")
    logging.info(f"Latency Output File: {LATENCY_OUTPUT_FILE}")
    logging.info(f"Consumer Stats Output File: {CONSUMER_STATS_FILE}")
    logging.info(
        f"Latency Window: {LATENCY_WINDOW_SECONDS}s, "
        f"Reporting Interval: {REPORTING_INTERVAL_SECONDS}s"
    )

    consumer = None
    retries = 0
    while retries < MAX_RETRIES:
        try:
            consumer = KafkaConsumer(
                KAFKA_TOPIC,
                bootstrap_servers=KAFKA_BROKER,
                group_id=CONSUMER_GROUP_ID,
                client_id=CONSUMER_CLIENT_ID,
                auto_offset_reset="latest",  # Start consuming from the latest message
                # enable_auto_commit=True, # Auto commit offsets (default)
                # auto_commit_interval_ms=5000 # Default interval
            )
            logging.info(
                "KafkaConsumer initialized successfully. Waiting for messages..."
            )
            break  # Exit loop if connection successful
        except NoBrokersAvailable as e:
            retries += 1
            logging.warning(
                f"Attempt {retries}/{MAX_RETRIES}: Could not connect to Kafka broker "
                f"at {KAFKA_BROKER}. Error: {e}"
            )
            if retries >= MAX_RETRIES:
                logging.error("Maximum connection attempts reached. Exiting.")
                exit(1)
            delay = INITIAL_RETRY_DELAY_S * (2 ** (retries - 1))  # Exponential backoff
            logging.info(f"Retrying in {delay} seconds...")
            time.sleep(delay)
        except Exception as e:
            logging.error(
                f"An unexpected error occurred during KafkaConsumer initialization: {e}"
            )
            exit(1)

    if not consumer:
        logging.error("Failed to initialize Kafka consumer after multiple retries.")
        exit(1)

    try:
        for message in consumer:
            global message_count_since_last_report  # Need to modify counter
            message_count_since_last_report += 1  # Increment counter

            # logging.debug(
            #    f"Received message: {message.topic}:{message.partition}:"
            #    f"{message.offset}: key={message.key} value={message.value[:50]}..."
            # )
            latency = calculate_latency(message.value)
            if latency is not None:
                now = time.time()
                recent_latencies.append((now, latency))

            # Periodically calculate and report metrics
            calculate_and_report_metrics()  # Use renamed function

    except KeyboardInterrupt:
        logging.info("Consumer interrupted. Shutting down...")
    except Exception as e:
        logging.error(f"An unexpected error occurred during consumption: {e}")
    finally:
        if consumer:
            logging.info("Closing Kafka consumer...")
            consumer.close()
            logging.info("Consumer closed.")
        # Final report before exiting
        calculate_and_report_metrics()  # Use renamed function
        logging.info("Final metrics report written.")


if __name__ == "__main__":
    main()
