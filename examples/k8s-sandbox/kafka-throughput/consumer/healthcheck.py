#!/usr/bin/env python3
"""
Simple healthcheck script to verify Kafka connectivity for container healthchecks.
Exits with code 0 if healthy, non-zero otherwise.
"""

import logging
import os
import sys

from kafka import KafkaAdminClient  # type: ignore
from kafka.errors import NoBrokersAvailable  # type: ignore

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Configuration
KAFKA_BROKER = os.environ.get("KAFKA_BROKER", "kafka:9092")
CONFIGMAP_NAME = os.environ.get("CONFIGMAP_NAME", "kafka-latency-metrics")
CONFIGMAP_NAMESPACE = os.environ.get("CONFIGMAP_NAMESPACE", "kafka")
LATENCY_CM_KEY = os.environ.get("LATENCY_CM_KEY", "actual_latency_ms")
TARGET_LATENCY_CM_KEY = os.environ.get("TARGET_LATENCY_CM_KEY", "target_latency_ms")
MAX_LATENCY_THRESHOLD_FACTOR = float(
    os.environ.get("MAX_LATENCY_THRESHOLD_FACTOR", "5.0")
)
KUBECTL_CMD = os.environ.get("KUBECTL_CMD", "kubectl")
TIMEOUT = int(os.environ.get("HEALTHCHECK_TIMEOUT", "10"))


def check_kafka_connection() -> bool:
    """Checks if a connection can be established to the Kafka broker."""
    try:
        admin_client = KafkaAdminClient(
            bootstrap_servers=KAFKA_BROKER,
            client_id="healthcheck-consumer",
            request_timeout_ms=TIMEOUT * 1000,
            api_version_auto_timeout_ms=TIMEOUT * 1000,
            reconnect_backoff_ms=500,
        )
        admin_client.list_topics(timeout=TIMEOUT)
        admin_client.close()
        return True
    except NoBrokersAvailable:
        print(f"Healthcheck failed: Could not connect to broker at {KAFKA_BROKER}")
        sys.exit(1)  # Exit directly on connection failure
    except Exception as e:
        print(f"Healthcheck failed: Unexpected error during Kafka check - {e}")
        sys.exit(1)  # Exit directly on other errors


def main() -> None:
    if check_kafka_connection():
        print("Healthcheck passed: Kafka connection successful.")
        sys.exit(0)
    # If check_kafka_connection returns, it must have succeeded.
    # If it failed, it would have already exited.


if __name__ == "__main__":
    main()
