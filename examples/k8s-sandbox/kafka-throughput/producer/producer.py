import json
import logging
import os
import random
import time
from math import floor
from functools import lru_cache

from kafka import KafkaProducer  # type: ignore[import-not-found]
from kafka.errors import (  # type: ignore[import-not-found]
    KafkaTimeoutError,
    NoBrokersAvailable,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Configuration from environment variables
KAFKA_BROKER = os.environ.get(
    "KAFKA_BROKER", "kafka-service.kafka.svc.cluster.local:9092"
)
KAFKA_TOPIC = os.environ.get("KAFKA_TOPIC", "throughput-topic")
INITIAL_MESSAGE_RATE = int(os.environ.get("PRODUCER_TARGET_RATE", "1000"))
MESSAGE_SIZE_BYTES = int(os.environ.get("MESSAGE_SIZE_BYTES", "1024"))
PRODUCER_CLIENT_ID = os.environ.get("PRODUCER_CLIENT_ID", "kafka-throughput-producer")
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "30"))
INITIAL_RETRY_DELAY_S = int(os.environ.get("INITIAL_RETRY_DELAY_S", "5"))
STATUS_DIR = os.environ.get("STATUS_DIR", "/tmp/status")
PRODUCER_STATS_FILE = os.path.join(STATUS_DIR, "producer_stats.txt")
LATENCY_FILE = os.path.join(STATUS_DIR, "e2e_latency_ms.txt")
KMINION_PRODUCER_ACTUAL_RATE_FILE = os.path.join(
    STATUS_DIR, "producer_actual_rate_value.txt"
)

# Adaptive Load Parameters
ADAPTIVE_CHECK_INTERVAL_S = int(os.environ.get("ADAPTIVE_CHECK_INTERVAL_S", "10"))
TARGET_LATENCY_MS = float(os.environ.get("TARGET_LATENCY_MS", "5.0"))
MAX_MESSAGE_RATE = int(os.environ.get("MAX_MESSAGE_RATE", "50000"))
RATE_INCREASE_FACTOR = float(os.environ.get("RATE_INCREASE_FACTOR", "1.03"))
ACTUAL_VS_TARGET_THRESHOLD_PERCENT = float(
    os.environ.get("ACTUAL_VS_TARGET_THRESHOLD_PERCENT", "0.95")
)


# Memoized helper for creating padding string
@lru_cache(maxsize=128)
def _get_padding_string(length: int) -> str:
    if length <= 0:
        return ""
    return "x" * length


def create_message(sequence_number: int, size_bytes: int) -> bytes:
    """Creates a JSON message with a sequence number and padding."""
    payload = {
        "sequence": sequence_number,
        "timestamp": time.time(),
        "data": "",  # Placeholder for padding
    }
    # First serialization to determine the exact size of other fields
    base_payload_str = json.dumps(payload, separators=(",", ":"))
    current_encoded_size = len(base_payload_str.encode("utf-8"))

    padding_needed = size_bytes - current_encoded_size

    # Get padding string using the memoized helper
    payload["data"] = _get_padding_string(padding_needed)

    # Second serialization with the actual padding
    message_str = json.dumps(payload, separators=(",", ":"))
    return message_str.encode("utf-8")


def send_message(
    producer: KafkaProducer,
    topic: str,
    sequence_number: int,
    message_size_bytes: int,
) -> bool:
    """
    Creates a message, determines partition, sends it, and handles errors.
    Returns True if successful, False otherwise.
    """
    message_bytes = create_message(sequence_number, message_size_bytes)

    # Partition key logic (Benford's Law like distribution)
    # This attempts to create a non-uniform distribution of messages across partitions
    # for more realistic load.
    lognorm_value = random.lognormvariate(5, 3)
    random_int = floor(lognorm_value)
    partition_key = int(str(random_int)[0])

    try:
        producer.send(topic, value=message_bytes, partition=partition_key)
        logging.debug(f"Sent msg {sequence_number} to partition '{partition_key}'")
        return True
    except KafkaTimeoutError:
        logging.warning("Timeout sending message. Kafka busy or unavailable?")
        return False
    except Exception as e:
        logging.error(f"Error sending message: {e}")
        return False


def write_producer_stats(target_rate: int, size: int) -> None:
    """Writes producer target rate and message size to a file."""
    stats_str = f"target_rate={target_rate},size={size}"
    try:
        os.makedirs(STATUS_DIR, exist_ok=True)
        with open(PRODUCER_STATS_FILE, "w") as f:
            f.write(stats_str)
        logging.debug(f"Producer stats written: {stats_str}")
    except Exception as e:
        logging.error(f"Error writing producer stats to {PRODUCER_STATS_FILE}: {e}")


def _read_metric_from_file(file_path: str, metric_name: str) -> float | None:
    """Helper function to read a metric value from a given file."""
    try:
        if os.path.exists(file_path):
            with open(file_path) as f:
                content = f.read().strip()
                if content and content != "N/A":
                    logging.debug(f"{metric_name} from {file_path}: '{content}'")
                    return float(content)
                elif content == "N/A":
                    logging.debug(f"{metric_name} file {file_path} reported N/A.")
                    return None  # Treat N/A as no data
        else:
            logging.warning(f"{metric_name} file {file_path} not found.")
    except ValueError:
        logging.warning(f"Could not parse float from {metric_name} file: {file_path}")
    except Exception as e:
        logging.error(f"Error reading {metric_name} file {file_path}: {e}")
    return None


def adjust_message_rate_autonomously(
    actual_rate: float | None,
    target_rate: int,
    actual_latency_ms: float | None,
    target_latency_ms: float,
    max_rate_cap: int,
    increase_factor: float,
    actual_vs_target_ratio_threshold: float,
) -> int:
    """Producer will adjust rate upwards if conditions are good."""

    if actual_rate is None:
        logging.info(
            "No KMinion-observed actual rate data available. "
            f"Holding current target rate: {target_rate}/s."
        )
        return target_rate

    if actual_latency_ms is None:
        logging.info(f"No latency data. Holding current target rate: {target_rate}/s.")
        return target_rate

    if actual_latency_ms >= target_latency_ms:
        logging.info(
            f"Latency ({actual_latency_ms:.2f}ms) >= threshold ({target_latency_ms}ms). "
            f"Holding current target rate: {target_rate}/s."
        )
        return target_rate

    if target_rate >= max_rate_cap:
        logging.info(
            f"Latency low ({actual_latency_ms:.2f}ms), but already at max rate cap "
            f"({target_rate}/s). Holding."
        )
        return target_rate

    if actual_rate < (target_rate * actual_vs_target_ratio_threshold):
        logging.info(
            f"Latency low ({actual_latency_ms:.2f}ms < {target_latency_ms}ms), "
            f"but local actual rate ({actual_rate:.2f}/s) is below threshold "
            f"({actual_vs_target_ratio_threshold * 100:.0f}%) of current target "
            f"({target_rate}/s). Holding current target rate."
        )
        return target_rate

    calculated_new_rate = target_rate * increase_factor
    new_rate = min(int(calculated_new_rate), max_rate_cap)

    if new_rate > target_rate:
        logging.info(
            "Conditions good. Increasing target rate from "
            f"{target_rate} to {new_rate}/s."
        )
        return new_rate
    else:
        logging.info(
            f"Conditions good, but proposed new rate {new_rate}/s "
            f"not > current {target_rate}/s. Holding."
        )
        return target_rate


def main() -> None:
    logging.info("--- Kafka Throughput Demo Producer (v2 - Autonomous) --- ")
    logging.info(f"Target Kafka Broker: {KAFKA_BROKER}")
    logging.info(f"Target Kafka Topic: {KAFKA_TOPIC}")

    current_message_rate = INITIAL_MESSAGE_RATE
    logging.info(
        f"Initial Message Rate: {current_message_rate}/s (Max Cap for "
        f"Autonomous Adjustments: {MAX_MESSAGE_RATE}/s)"
    )
    logging.info(f"Message Size: {MESSAGE_SIZE_BYTES} bytes")
    logging.info(f"Client ID: {PRODUCER_CLIENT_ID}")
    logging.info(
        f"Autonomous Adaptive Logic: Check Interval={ADAPTIVE_CHECK_INTERVAL_S}s, "
        f"Target Latency=<{TARGET_LATENCY_MS}ms, "
        f"Increase Factor=x{RATE_INCREASE_FACTOR}, "
        f"Min Actual/Target Ratio={ACTUAL_VS_TARGET_THRESHOLD_PERCENT * 100:.0f}%"
    )

    producer = None
    retries = 0
    while retries < MAX_RETRIES:
        try:
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BROKER,
                client_id=PRODUCER_CLIENT_ID,
                acks=1,
                retries=3,
                linger_ms=50,
                batch_size=16384 * 16,
            )
            logging.info("KafkaProducer initialized successfully.")
            break
        except NoBrokersAvailable as e:
            retries += 1
            logging.warning(
                f"Attempt {retries}/{MAX_RETRIES}: Could not connect to Kafka "
                f"broker at {KAFKA_BROKER}. Error: {e}"
            )
            if retries >= MAX_RETRIES:
                logging.error("Maximum connection attempts reached. Exiting.")
                exit(1)
            delay = INITIAL_RETRY_DELAY_S * (2 ** (retries - 1))
            logging.info(f"Retrying in {delay} seconds...")
            time.sleep(delay)
        except Exception as e:
            logging.error(
                f"An unexpected error during KafkaProducer initialization: {e}"
            )
            exit(1)

    if not producer:
        logging.error("Failed to initialize Kafka producer after multiple retries.")
        exit(1)

    logging.info("Writing initial producer stats (target_rate, size)...")
    write_producer_stats(target_rate=current_message_rate, size=MESSAGE_SIZE_BYTES)

    sequence_number = 0
    messages_sent_this_interval = 0  # For calculating local actual rate over 1 second
    interval_start_time = time.time()
    last_autonomous_adjustment_check_time = time.time()

    try:
        while True:
            now = time.time()

            # 1. Autonomous Adaptive Rate Adjustment (periodically)
            if now - last_autonomous_adjustment_check_time >= ADAPTIVE_CHECK_INTERVAL_S:
                last_autonomous_adjustment_check_time = now

                current_e2e_latency_ms = _read_metric_from_file(
                    LATENCY_FILE, "E2E latency"
                )

                # Fetch KMinion's observed producer rate for decision making
                kminion_observed_producer_rate = _read_metric_from_file(
                    KMINION_PRODUCER_ACTUAL_RATE_FILE,
                    "KMinion observed producer rate for decision",
                )

                adjusted_target_rate = adjust_message_rate_autonomously(
                    actual_rate=kminion_observed_producer_rate,
                    target_rate=current_message_rate,
                    actual_latency_ms=current_e2e_latency_ms,
                    target_latency_ms=TARGET_LATENCY_MS,
                    max_rate_cap=MAX_MESSAGE_RATE,
                    increase_factor=RATE_INCREASE_FACTOR,
                    actual_vs_target_ratio_threshold=ACTUAL_VS_TARGET_THRESHOLD_PERCENT,
                )

                if adjusted_target_rate != current_message_rate:
                    logging.info(
                        "Autonomous adjustment: Target rate changed from "
                        f"{current_message_rate} to {adjusted_target_rate}/s."
                    )
                    current_message_rate = adjusted_target_rate
                    # Write new autonomously adjusted target to stats file
                    write_producer_stats(
                        target_rate=current_message_rate, size=MESSAGE_SIZE_BYTES
                    )

            # 2. Message Sending Loop (to meet current_message_rate over 1 second)
            # This loop aims to send `current_message_rate` messages
            # within each 1-second wall-clock interval.
            if messages_sent_this_interval < current_message_rate:
                if send_message(
                    producer, KAFKA_TOPIC, sequence_number, MESSAGE_SIZE_BYTES
                ):
                    sequence_number += 1
                    messages_sent_this_interval += 1
                else:
                    # Prevents a very tight loop if Kafka is temporarily unresponsive.
                    time.sleep(0.1)

            # 3. Stats Reporting & Loop Timing (every 1 second)
            # Also ensures the loop roughly aligns with 1-second iterations.
            if now - interval_start_time >= 1.0:
                elapsed_interval_time = now - interval_start_time
                logging.info(
                    f"Interval: {elapsed_interval_time:.2f}s, "
                    f"Current Target Rate: {current_message_rate}/s, "
                    f"Sent this interval: {messages_sent_this_interval}"
                )

                write_producer_stats(
                    target_rate=current_message_rate, size=MESSAGE_SIZE_BYTES
                )

                # Reset for next 1-second interval
                messages_sent_this_interval = 0
                interval_start_time = now  # Reset interval timer to current time
            else:
                # If we've already sent all messages for this target rate in the
                # current <1s window, sleep briefly to yield CPU and avoid busy-waiting.
                if messages_sent_this_interval >= current_message_rate:
                    # Calculate remaining time in 1-second interval and sleep for that
                    # duration, or a small fixed amount if the calculation is tricky.
                    # This helps maintain the 1-second rhythm more accurately.
                    remaining_time_in_interval = 1.0 - (now - interval_start_time)
                    if (
                        remaining_time_in_interval > 0.001
                    ):  # Only sleep if meaningful time left
                        time.sleep(
                            min(remaining_time_in_interval, 0.1)
                        )  # Sleep up to 0.1s or remaining time
                    else:
                        time.sleep(
                            0.001
                        )  # Minimal sleep if very close to end of interval or overshot

    except KeyboardInterrupt:
        logging.info("Producer interrupted. Shutting down...")
    except Exception as e:
        logging.error(f"An unexpected error occurred in main loop: {e}", exc_info=True)
    finally:
        if producer:
            logging.info("Flushing remaining messages...")
            producer.flush(timeout=10)  # Adding timeout to flush
            logging.info("Closing Kafka producer...")
            producer.close(timeout=10)  # Adding timeout to close
            logging.info("Producer closed.")
            # Write final stats (target_rate, size) on clean exit
            write_producer_stats(
                target_rate=current_message_rate, size=MESSAGE_SIZE_BYTES
            )


if __name__ == "__main__":
    main()
