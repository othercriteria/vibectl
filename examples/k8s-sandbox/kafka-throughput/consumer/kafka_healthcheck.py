import logging
import os
import sys

from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable

# Minimal logging for healthcheck
logging.basicConfig(
    level=logging.WARNING, format="%(asctime)s - %(levelname)s - %(message)s"
)

KAFKA_BROKER = os.environ.get("KAFKA_BROKER", "kafka:9092")
TIMEOUT_S = 5

try:
    producer = KafkaProducer(
        bootstrap_servers=KAFKA_BROKER,
        client_id="healthcheck-producer",
        request_timeout_ms=TIMEOUT_S * 1000,
        retries=0,  # Don't retry in healthcheck
    )
    # Check if connection is actually alive (optional, but good)
    producer.partitions_for(
        "__dummy_topic_for_healthcheck"
    )  # Non-blocking metadata fetch
    producer.close()
    # print("Healthcheck: Kafka connection successful.")
    sys.exit(0)
except NoBrokersAvailable:
    logging.warning(f"Healthcheck: Kafka broker {KAFKA_BROKER} not available.")
    sys.exit(1)
except Exception as e:
    logging.error(f"Healthcheck: Unexpected error connecting to Kafka: {e}")
    sys.exit(1)
