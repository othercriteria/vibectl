# Kafka Throughput Demo Structure

This document outlines the structure of the Kafka Throughput Optimization demo.

## Overview

The demo uses Docker Compose to set up a K3d Kubernetes cluster running Kafka, along with producer/consumer applications and the `vibectl` agent. The goal is for `vibectl` to optimize Kafka broker configurations to maximize producer throughput while minimizing consumer latency.

## Directory Layout

```
examples/k8s-sandbox/kafka-throughput/
├── compose.yml             # Docker Compose file defining the services.
├── Dockerfile              # (Not used directly, components have their own)
├── Makefile                # For managing common tasks (build, up, down, logs, etc.).
├── k8s-sandbox/            # Contains files for the K3d + Kafka + vibectl service.
│   ├── Dockerfile          # Builds the k8s-sandbox container image.
│   ├── entrypoint.sh       # Script run inside the container to set up K3d, Kafka, and vibectl.
│   └── kafka-kraft.yaml    # Kubernetes manifest for deploying a single-node KRaft Kafka cluster.
├── producer/               # Contains files for the Kafka producer service.
│   ├── Dockerfile          # Builds the producer container image.
│   └── producer.py         # Python script that produces messages to Kafka.
├── consumer/               # (Placeholder) Contains files for the Kafka consumer service.
│   └── Dockerfile          # Placeholder Dockerfile.
│   └── consumer.py         # (Placeholder) Python script to consume messages and report latency.
├── overseer/               # (Placeholder) Contains files for the monitoring/control service.
│   └── Dockerfile          # Placeholder Dockerfile.
│   └── overseer.py         # (Placeholder) Script to observe latency and potentially adjust producer.
├── run.sh                  # Main script to launch, manage, and clean up the demo.
├── README.md               # This file: explains the demo, setup, and usage.
├── STRUCTURE.md            # This file: describes the directory layout.
└── status-volume/          # (Created at runtime) Shared volume for status/metric files.
    ├── kafka_ready         # (Created by k8s-sandbox) Signals Kafka broker is ready.
    └── latency.txt         # (Created by consumer) Contains latest consumer latency.
```

## Key Components

- **`run.sh`**: The entry point for starting and stopping the demo.
- **`compose.yml`**: Defines the services (`k8s-sandbox`, `producer`, `consumer`, `overseer`), network, and shared volume.
- **`k8s-sandbox/`**: Manages the Kubernetes environment, Kafka deployment, and runs the `vibectl` agent.
  - **`entrypoint.sh`**: Orchestrates K3d setup, Kafka deployment via `kafka-kraft.yaml`, port-forwarding, `vibectl` installation/configuration, and the main loop reading `latency.txt` and running `vibectl auto`.
- **`producer/`**: Runs `producer.py` to generate load for the Kafka cluster.
- **`consumer/`**: (To be implemented) Runs `consumer.py` to read messages, calculate latency, and write it to `status-volume/latency.txt`.
- **`overseer/`**: (To be implemented) Monitors the system state (e.g., reads `latency.txt`).
- **`status-volume/`**: A Docker volume shared between containers for simple communication (e.g., Kafka readiness, latency metrics).
