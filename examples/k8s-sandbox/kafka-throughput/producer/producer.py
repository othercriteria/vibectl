import json
import logging
import os
import random
import time

from kafka import KafkaProducer
from kafka.errors import KafkaTimeoutError, NoBrokersAvailable

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Configuration from environment variables
KAFKA_BROKER = os.environ.get("KAFKA_BROKER", "kafka:9092")
KAFKA_TOPIC = os.environ.get("KAFKA_TOPIC", "throughput-topic")
# Store initial rate, allow it to be modified
INITIAL_MESSAGE_RATE = int(os.environ.get("MESSAGE_RATE_PER_SECOND", "10"))
MESSAGE_SIZE_BYTES = int(os.environ.get("MESSAGE_SIZE_BYTES", "1024"))
PRODUCER_CLIENT_ID = os.environ.get("PRODUCER_CLIENT_ID", "kafka-throughput-producer")
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "30"))
INITIAL_RETRY_DELAY_S = int(os.environ.get("INITIAL_RETRY_DELAY_S", "10"))
STATUS_DIR = os.environ.get("STATUS_DIR", "/tmp/status")
PRODUCER_STATS_FILE = os.path.join(STATUS_DIR, "producer_stats.txt")
LATENCY_FILE = os.path.join(STATUS_DIR, "latency.txt")  # Need latency file path

# Adaptive Load Parameters
ADAPTIVE_CHECK_INTERVAL_S = int(os.environ.get("ADAPTIVE_CHECK_INTERVAL_S", "30"))
LOW_LATENCY_THRESHOLD_MS = float(os.environ.get("LOW_LATENCY_THRESHOLD_MS", "10.0"))
MAX_MESSAGE_RATE = int(os.environ.get("MAX_MESSAGE_RATE", "10000"))
RATE_INCREASE_FACTOR = float(os.environ.get("RATE_INCREASE_FACTOR", "1.20"))


def create_message(sequence_number: int, size_bytes: int) -> bytes:
    """Creates a JSON message with a sequence number and padding."""
    payload = {
        "sequence": sequence_number,
        "timestamp": time.time(),
        "data": "",
    }
    # Calculate initial size (approximate)
    base_payload_str = json.dumps(payload, separators=(",", ":"))
    current_size = len(base_payload_str.encode("utf-8"))

    # Add padding to reach target size
    padding_needed = size_bytes - current_size
    if padding_needed > 0:
        payload["data"] = "x" * padding_needed

    # Final encoding
    message_str = json.dumps(payload, separators=(",", ":"))
    return message_str.encode("utf-8")


def write_producer_stats(target_rate: int, actual_rate: int, size: int) -> None:
    """Writes producer stats (target rate and actual achieved rate) to a file."""
    # Report both the target rate and the actual achieved rate
    stats_str = f"target_rate={target_rate}, actual_rate={actual_rate}, size={size}"
    try:
        os.makedirs(STATUS_DIR, exist_ok=True)
        with open(PRODUCER_STATS_FILE, "w") as f:
            f.write(stats_str)
    except Exception as e:
        logging.error(f"Error writing producer stats to {PRODUCER_STATS_FILE}: {e}")


def read_latency() -> float | None:
    """Reads the latency value from the shared file."""
    try:
        if os.path.exists(LATENCY_FILE):
            with open(LATENCY_FILE) as f:
                content = f.read().strip()
                if content:
                    return float(content)
    except ValueError:
        logging.warning(f"Could not parse float from latency file: {LATENCY_FILE}")
    except Exception as e:
        logging.error(f"Error reading latency file {LATENCY_FILE}: {e}")
    return None


def adjust_message_rate(
    current_rate: int,
    latency_ms: float | None,
    latency_threshold: float,
    max_rate: int,
    increase_factor: float,
) -> int:
    """Adjusts the message rate based on latency."""
    # Early return if no latency data
    if latency_ms is None:
        logging.info(
            f"Could not read latency. Holding target rate at {current_rate}/s."
        )
        return current_rate

    # Early return if latency is too high
    if latency_ms >= latency_threshold:
        logging.info(
            f"Latency ({latency_ms:.2f}ms) >= threshold ({latency_threshold}ms). "
            f"Holding target rate at {current_rate}/s."
        )
        return current_rate

    # Early return if already at max rate
    if current_rate >= max_rate:
        logging.info(
            f"Latency low ({latency_ms:.2f}ms), but already at max rate "
            f"({current_rate}/s). Holding."
        )
        return current_rate

    # Calculate new rate
    calculated_new_rate = current_rate * increase_factor
    new_rate = min(int(calculated_new_rate), max_rate)

    # Return new rate if increased, otherwise current rate
    if new_rate > current_rate:
        logging.info(
            f"Low latency ({latency_ms:.2f}ms < {latency_threshold}ms). "
            f"Increasing target rate by factor {increase_factor}: "
            f"{current_rate} -> {new_rate}/s"
        )
        return new_rate
    else:
        logging.info(
            f"Latency low ({latency_ms:.2f}ms), but already at/near max rate "
            f"({current_rate}/s). Holding."
        )
        return current_rate  # Return current rate if no change


def main() -> None:
    logging.info("--- Kafka Throughput Demo Producer --- ")
    logging.info(f"Target Kafka Broker: {KAFKA_BROKER}")
    logging.info(f"Target Kafka Topic: {KAFKA_TOPIC}")
    # Use mutable variable for rate
    current_message_rate = INITIAL_MESSAGE_RATE
    logging.info(
        f"Initial Message Rate: {current_message_rate}/s (Max: {MAX_MESSAGE_RATE}/s)"
    )
    logging.info(f"Message Size: {MESSAGE_SIZE_BYTES} bytes")
    logging.info(f"Client ID: {PRODUCER_CLIENT_ID}")
    logging.info(
        f"Adaptive Load: Check={ADAPTIVE_CHECK_INTERVAL_S}s, "
        f"Threshold=<{LOW_LATENCY_THRESHOLD_MS}ms, Factor=x{RATE_INCREASE_FACTOR}"
    )

    producer = None
    retries = 0
    while retries < MAX_RETRIES:
        try:
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BROKER,
                client_id=PRODUCER_CLIENT_ID,
                acks=1,  # Acknowledge after leader write (Changed to integer)
                retries=3,  # Internal retries within kafka-python
            )
            logging.info("KafkaProducer initialized successfully.")
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
                f"An unexpected error occurred during KafkaProducer initialization: {e}"
            )
            exit(1)

    if not producer:
        logging.error("Failed to initialize Kafka producer after multiple retries.")
        exit(1)

    # Write initial status file (report target rate)
    logging.info("Writing initial producer stats...")
    write_producer_stats(
        target_rate=current_message_rate, actual_rate=0, size=MESSAGE_SIZE_BYTES
    )

    sequence_number = 0
    messages_sent_this_second = 0
    start_time_current_second = time.time()
    last_adaptive_check_time = time.time()

    try:
        while True:
            now = time.time()

            # --- Adaptive Load Adjustment --- Check periodically
            if now - last_adaptive_check_time >= ADAPTIVE_CHECK_INTERVAL_S:
                last_adaptive_check_time = now
                latency_ms = read_latency()
                current_message_rate = adjust_message_rate(
                    current_rate=current_message_rate,
                    latency_ms=latency_ms,
                    latency_threshold=LOW_LATENCY_THRESHOLD_MS,
                    max_rate=MAX_MESSAGE_RATE,
                    increase_factor=RATE_INCREASE_FACTOR,
                )

            # --- Rate limiting & Stats Reporting --- (Per second)
            elapsed_in_second = now - start_time_current_second

            if elapsed_in_second >= 1.0:
                # Report stats for the completed second
                actual_rate_this_second = messages_sent_this_second
                # Report current target rate and actual achieved rate
                write_producer_stats(
                    target_rate=current_message_rate,
                    actual_rate=actual_rate_this_second,
                    size=MESSAGE_SIZE_BYTES,
                )

                # Reset counter and timer for the new second
                messages_sent_this_second = 0
                start_time_current_second = now  # Reset timer precisely
                elapsed_in_second = 0  # Reset elapsed time for the new second

            # --- Message Sending --- (Uses current_message_rate)
            if messages_sent_this_second < current_message_rate:
                message_bytes = create_message(sequence_number, MESSAGE_SIZE_BYTES)

                # Generate partition key based on leading digit of a log-normally
                # distributed variable. This provides a distribution closer to
                # Benford's Law.
                lognorm_value = random.lognormvariate(
                    5, 3
                )  # mu=5, sigma=3 as suggested
                # Convert to integer (at least 1) to get the leading digit
                random_int = max(1, int(lognorm_value))
                leading_digit_str = str(random_int)[0]
                partition_key_bytes = leading_digit_str.encode("utf-8")

                try:
                    # Send message with the calculated partition key
                    producer.send(
                        KAFKA_TOPIC, value=message_bytes, key=partition_key_bytes
                    )
                    logging.debug(
                        f"Sent msg {sequence_number} key='{leading_digit_str}' "
                        f"(from {lognorm_value:.2f})"
                    )
                    sequence_number += 1
                    messages_sent_this_second += 1
                except KafkaTimeoutError:
                    logging.warning(
                        "Timeout sending message. Retrying might happen internally."
                    )
                except Exception as e:
                    logging.error(f"Error sending message: {e}")
                    # Consider a delay or break here depending on the error
                    time.sleep(1)  # Simple delay

            # --- Sleep Logic --- (Calculated based on current_message_rate)
            if messages_sent_this_second >= current_message_rate:
                time_to_next_second = start_time_current_second + 1.0 - time.time()
                if time_to_next_second > 0:
                    time.sleep(time_to_next_second)
            else:
                target_interval = (
                    1.0 / current_message_rate if current_message_rate > 0 else 1.0
                )
                time.sleep(max(0, target_interval / 10))

    except KeyboardInterrupt:
        logging.info("Producer interrupted. Shutting down...")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
    finally:
        if producer:
            logging.info("Flushing remaining messages...")
            producer.flush()  # Ensure all buffered messages are sent
            logging.info("Closing Kafka producer...")
            producer.close()
            logging.info("Producer closed.")
            # Write final stats on clean exit
            write_producer_stats(
                target_rate=current_message_rate, actual_rate=0, size=MESSAGE_SIZE_BYTES
            )


if __name__ == "__main__":
    main()
