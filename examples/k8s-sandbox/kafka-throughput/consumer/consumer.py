import logging
import os
import time

from kafka import KafkaConsumer  # type: ignore
from kafka.errors import NoBrokersAvailable  # type: ignore

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
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "5"))
INITIAL_RETRY_DELAY_S = int(os.environ.get("INITIAL_RETRY_DELAY_S", "5"))


def main() -> None:
    logging.info("--- Kafka Throughput Demo Consumer (Simplified) --- ")
    logging.info(f"Target Kafka Broker: {KAFKA_BROKER}")
    logging.info(f"Target Kafka Topic: {KAFKA_TOPIC}")
    logging.info(f"Consumer Group ID: {CONSUMER_GROUP_ID}")
    logging.info(f"Client ID: {CONSUMER_CLIENT_ID}")

    consumer = None
    retries = 0
    while retries < MAX_RETRIES:
        try:
            consumer = KafkaConsumer(
                KAFKA_TOPIC,
                bootstrap_servers=KAFKA_BROKER,
                group_id=CONSUMER_GROUP_ID,
                client_id=CONSUMER_CLIENT_ID,
                auto_offset_reset="latest",
            )
            logging.info(
                "KafkaConsumer initialized successfully. Waiting for messages..."
            )
            break
        except NoBrokersAvailable as e:
            retries += 1
            logging.warning(
                f"Attempt {retries}/{MAX_RETRIES}: Could not connect to Kafka broker "
                f"at {KAFKA_BROKER}. Error: {e}"
            )
            if retries >= MAX_RETRIES:
                logging.error("Maximum connection attempts reached. Exiting.")
                exit(1)
            delay = INITIAL_RETRY_DELAY_S * (2 ** (retries - 1))
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

    message_counter = 0
    log_interval = 1000  # Log every 1000 messages for example

    try:
        for message in consumer:
            message_counter += 1
            if message_counter % log_interval == 0:
                logging.info(
                    f"Consumed {message_counter} messages. "
                    f"Last offset: {message.offset}"
                )

    except KeyboardInterrupt:
        logging.info("Consumer interrupted. Shutting down...")
    except Exception as e:
        logging.error(f"An unexpected error occurred during consumption: {e}")
    finally:
        if consumer:
            logging.info("Closing Kafka consumer...")
            consumer.close()
            logging.info("Consumer closed.")
        logging.info(f"Total messages processed by this instance: {message_counter}")


if __name__ == "__main__":
    main()
