# Kafka Throughput Demo Structure

This document outlines the structure of the Kafka Throughput Optimization demo.

## Overview

The demo uses Docker Compose to set up a K3d Kubernetes cluster running Kafka, along with producer/consumer applications and the `vibectl` agent. The goal is for `vibectl` to optimize Kafka broker configurations (heap, network/IO threads) to maximize producer throughput while minimizing consumer P99 latency.

## Directory Layout

```
examples/k8s-sandbox/kafka-throughput/
├── compose.yml             # Docker Compose file defining the services.
├── Makefile                # For managing common tasks (build, up, down, logs, etc.).
├── run.sh                  # Main script to launch, manage, and clean up the demo.
├── README.md               # Explains the demo, setup, and usage.
├── STRUCTURE.md            # This file: describes the directory layout.
├── .gitignore              # Specifies intentionally untracked files.
├── .env.generated          # (Created by run.sh) Holds runtime env vars for compose.
├── k8s-sandbox/            # Contains files for the K3d + Kafka + vibectl service.
│   ├── Dockerfile          # Builds the k8s-sandbox container image.
│   ├── entrypoint.sh       # Script run inside the container to set up K3d, Kafka, vibectl, and the main agent loop.
│   ├── kafka-kraft.yaml    # Kubernetes manifest for deploying a single-node KRaft Kafka cluster.
│   ├── vibectl_instructions.txt # Initial instructions/goal for the vibectl agent.
│   ├── latency-reporter.py # Script to periodically read latency from ConfigMap and write to status file.
│   ├── kafka-latency-cm.yaml # Manifest for the ConfigMap where consumer writes latency.
│   └── latency-reporter-rbac.yaml # RBAC permissions for the latency reporter.
├── producer/               # Contains files for the Kafka producer service.
│   ├── Dockerfile          # Builds the producer container image.
│   ├── producer.py         # Python script that produces messages to Kafka.
│   └── healthcheck.py      # Simple healthcheck script for the producer.
├── consumer/               # Contains files for the Kafka consumer service.
│   ├── Dockerfile          # Builds the consumer container image.
│   ├── consumer.py         # Python script to consume messages, calculate P99 latency, and update the ConfigMap.
│   └── healthcheck.py      # Simple healthcheck script for the consumer.
├── kafka-demo-ui/          # Renamed from overseer - Contains files for the simple monitoring/UI service.
│   ├── Dockerfile          # Builds the kafka-demo-ui container image.
│   └── kafka_demo_ui.py    # Renamed from overseer.py - Python script (currently logs latency, intended for UI).
└── status-volume/          # (Created at runtime via Docker tmpfs volume) Shared volume for status files.
    ├── kafka_ready         # (Created by k8s-sandbox) Signals Kafka broker is ready for clients.
    ├── latency.txt         # (Created by latency-reporter.py) Contains latest consumer P99 latency (ms).
    └── kafka_cluster_id.txt # (Created by run.sh) Stores the generated Kafka cluster ID.
```

## Key Components

- **`run.sh`**: The entry point for starting and stopping the demo. Handles API key input, Docker GID detection, Kafka cluster ID generation, and Docker Compose orchestration.
- **`compose.yml`**: Defines the services (`k8s-sandbox`, `producer`, `consumer`, `kafka-demo-ui`), network, shared `status-volume`, resource limits, and healthchecks.
- **`k8s-sandbox/`**: Manages the Kubernetes environment, Kafka deployment, and runs the `vibectl` agent.
  - **`entrypoint.sh`**: Orchestrates K3d setup, Kafka deployment via `kafka-kraft.yaml`, port-forwarding, `vibectl` installation/configuration (including LLM plugins and API key setup), deploys the latency reporter, and runs the main loop reading `latency.txt` and executing `vibectl auto`.
  - **`latency-reporter.py`**: Runs inside the `k8s-sandbox` container, periodically reads the P99 latency from the `kafka-latency-metrics` ConfigMap (updated by the consumer) and writes it to `/tmp/status/latency.txt` for the main `vibectl` loop to read.
- **`producer/`**: Runs `producer.py` to generate configurable load for the Kafka cluster.
- **`consumer/`**: Runs `consumer.py` to read messages, calculate P99 latency, and update the `kafka-latency-metrics` ConfigMap in the Kubernetes cluster.
- **`kafka-demo-ui/`**: Runs `kafka_demo_ui.py` to monitor latency (future: provide a simple web UI).
- **`status-volume/`**: A Docker tmpfs volume mounted to `/tmp/status` in relevant containers for simple file-based communication (Kafka readiness signal, latest processed latency).
