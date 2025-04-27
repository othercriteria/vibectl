#!/usr/bin/env python3
"""
Simple healthcheck script to verify Kafka connectivity for container healthchecks.
Exits with code 0 if healthy, non-zero otherwise.
"""

import os
import sys

from kafka import KafkaAdminClient
from kafka.errors import NoBrokersAvailable

# Configuration
KAFKA_BROKER = os.environ.get("KAFKA_BROKER", "kafka:9092")
TIMEOUT = int(os.environ.get("HEALTHCHECK_TIMEOUT", "10"))


def check_kafka_connection() -> bool:
    """Checks if a connection can be established to the Kafka broker."""
    try:
        admin_client = KafkaAdminClient(
            bootstrap_servers=KAFKA_BROKER,
            client_id="healthcheck-producer",
            request_timeout_ms=TIMEOUT * 1000,  # Convert seconds to ms
            api_version_auto_timeout_ms=TIMEOUT
            * 1000,  # Timeout for initial connection
            reconnect_backoff_ms=500,  # Faster retry backoff
        )
        # A simple operation to verify connectivity
        _topics = admin_client.list_topics(timeout=TIMEOUT)
        admin_client.close()
        return True
    except NoBrokersAvailable:
        print(f"Healthcheck failed: Could not connect to broker at {KAFKA_BROKER}")
        sys.exit(1)
    except Exception as e:
        print(f"Healthcheck failed: Unexpected error - {e}")
        sys.exit(1)


def main() -> None:
    if check_kafka_connection():
        print("Healthcheck passed: Kafka connection successful.")
        sys.exit(0)
    else:
        # check_kafka_connection already exits on failure, but for clarity:
        sys.exit(1)


if __name__ == "__main__":
    main()
