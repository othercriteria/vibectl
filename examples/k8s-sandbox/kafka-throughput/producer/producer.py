import json
import logging
import os
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
MESSAGE_RATE_PER_SECOND = int(os.environ.get("MESSAGE_RATE_PER_SECOND", "10"))
MESSAGE_SIZE_BYTES = int(os.environ.get("MESSAGE_SIZE_BYTES", "1024"))
PRODUCER_CLIENT_ID = os.environ.get("PRODUCER_CLIENT_ID", "kafka-throughput-producer")
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "30"))
INITIAL_RETRY_DELAY_S = int(os.environ.get("INITIAL_RETRY_DELAY_S", "10"))
STATUS_DIR = os.environ.get("STATUS_DIR", "/tmp/status")
PRODUCER_STATS_FILE = os.path.join(STATUS_DIR, "producer_stats.txt")


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


def write_producer_stats(rate: int, size: int) -> None:
    """Writes producer stats to a file."""
    stats_str = f"rate={rate}, size={size}"
    try:
        os.makedirs(STATUS_DIR, exist_ok=True)
        with open(PRODUCER_STATS_FILE, "w") as f:
            f.write(stats_str)
    except Exception as e:
        logging.error(f"Error writing producer stats to {PRODUCER_STATS_FILE}: {e}")


def main() -> None:
    logging.info("--- Kafka Throughput Demo Producer --- ")
    logging.info(f"Target Kafka Broker: {KAFKA_BROKER}")
    logging.info(f"Target Kafka Topic: {KAFKA_TOPIC}")
    logging.info(f"Message Rate: {MESSAGE_RATE_PER_SECOND}/s")
    logging.info(f"Message Size: {MESSAGE_SIZE_BYTES} bytes")
    logging.info(f"Client ID: {PRODUCER_CLIENT_ID}")

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
                "An unexpected error occurred during KafkaProducer initialization: "
                f"{e}"
            )
            exit(1)

    if not producer:
        logging.error("Failed to initialize Kafka producer after multiple retries.")
        exit(1)

    sequence_number = 0
    messages_sent_this_second = 0
    start_time_current_second = time.time()
    last_reported_rate = 0

    try:
        while True:
            # Rate limiting & Stats Reporting
            now = time.time()
            elapsed_in_second = now - start_time_current_second

            if elapsed_in_second >= 1.0:
                # Report stats for the completed second
                current_rate = messages_sent_this_second
                if current_rate != last_reported_rate:
                    write_producer_stats(rate=current_rate, size=MESSAGE_SIZE_BYTES)
                    last_reported_rate = current_rate

                # Reset counter and timer for the new second
                messages_sent_this_second = 0
                start_time_current_second = now  # Reset timer precisely
                elapsed_in_second = 0  # Reset elapsed time for the new second

            if messages_sent_this_second < MESSAGE_RATE_PER_SECOND:
                message_bytes = create_message(sequence_number, MESSAGE_SIZE_BYTES)
                try:
                    # future = producer.send(KAFKA_TOPIC, value=message_bytes)
                    producer.send(KAFKA_TOPIC, value=message_bytes)
                    # Optional: Block until message is sent or timeout
                    # record_metadata = future.get(timeout=10)
                    # logging.debug(
                    #    f"Sent message {sequence_number} to topic "
                    #    f"{record_metadata.topic} partition "
                    #    f"{record_metadata.partition} offset {record_metadata.offset}"
                    # )
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

            # Calculate sleep time to maintain rate accurately
            # Avoid busy-waiting if rate is low
            if messages_sent_this_second >= MESSAGE_RATE_PER_SECOND:
                time_to_next_second = start_time_current_second + 1.0 - time.time()
                if time_to_next_second > 0:
                    time.sleep(time_to_next_second)
            else:
                # If we haven't hit the rate limit, sleep minimally or based on
                # target interval
                target_interval = 1.0 / MESSAGE_RATE_PER_SECOND
                # Small sleep to prevent tight loop
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
            # Write final zero rate on clean exit
            write_producer_stats(rate=0, size=MESSAGE_SIZE_BYTES)


if __name__ == "__main__":
    main()
