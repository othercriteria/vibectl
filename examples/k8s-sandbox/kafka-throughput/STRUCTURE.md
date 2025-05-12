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
│   ├── entrypoint.sh       # Script run inside container: sets up K3d, Kafka, vibectl, creates topic, runs agent loop.
│   ├── vibectl_instructions.txt # Initial instructions/goal for the vibectl agent.
│   ├── latency-reporter.py # Script to read status files and update kafka-latency-metrics ConfigMap.
│   ├── port_forward_manager.py # Python script to manage resilient kubectl port-forwarding.
│   └── manifests/            # Kubernetes manifests.
│       ├── kafka-kraft.yaml    # Kubernetes manifest for deploying a single-node KRaft Kafka cluster.
│       ├── kafka-latency-cm.yaml # ConfigMap for Kafka latency metrics.
│       └── latency-reporter-rbac.yaml # RBAC for the latency reporter.
├── producer/               # Contains files for the Kafka producer service.
│   ├── Dockerfile          # Builds the producer container image.
│   ├── producer.py         # Python script that produces messages to Kafka.
│   └── healthcheck.py      # Simple healthcheck script for the producer.
├── consumer/               # Contains files for the Kafka consumer service.
│   ├── Dockerfile          # Builds the consumer container image.
│   ├── consumer.py         # Python script to consume messages, calculate P99 latency, report consumption rate.
│   └── healthcheck.py      # Simple healthcheck script for the consumer.
├── kafka-demo-ui/          # Contains files for the web monitoring UI service.
│   ├── Dockerfile          # Builds the kafka-demo-ui container image.
│   ├── app.py              # Flask/SocketIO application serving the UI.
│   ├── requirements.txt    # Python dependencies for the UI app.
│   └── templates/
│       └── index.html      # HTML template for the UI.
```

## Key Components

- **`run.sh`**: The entry point for starting and stopping the demo. Handles API key input, Docker GID detection, Kafka cluster ID generation, and Docker Compose orchestration.
- **`compose.yml`**: Defines the services (`k8s-sandbox`, `producer`, `consumer`, `kafka-demo-ui`, `kminion`), network, shared `status-volume` (host bind mount `./status-volume/`), resource limits, and healthchecks.
- **`k8s-sandbox/`**: Manages the Kubernetes environment, Kafka deployment, and runs the `vibectl` agent.
  - **`entrypoint.sh`**: Orchestrates K3d setup, Kafka deployment via `manifests/kafka-kraft.yaml`, resilient port-forwarding using `port_forward_manager.py`, `vibectl` installation/configuration, deployment of the metrics reporter (`latency-reporter.py`), and runs the main loop executing `vibectl auto` periodically.
  - **`latency-reporter.py`**: Runs inside the `k8s-sandbox` container, periodically reads `producer_stats.txt` from the shared volume (`/tmp/status`), gets target latency from env var, and updates the `kafka-latency-metrics` ConfigMap in Kubernetes using `kubectl patch`.
- **`producer/`**: Runs `producer.py` to generate configurable and adaptive load (based on Benford-like distribution) for the Kafka cluster, reporting its target/actual rate and message size to `/tmp/status/producer_stats.txt`.
- **`consumer/`**: Runs `consumer.py` to read messages, calculate P99 latency, calculate consumption rate, and write the consumption rate to `/tmp/status/consumer_stats.txt`.
- **`kafka-demo-ui/`**: Runs a Flask/SocketIO web application (`app.py`) that monitors the status files in `/tmp/status` and Docker container health, providing a simple web UI (`templates/index.html`) to display metrics and logs.
- **`kminion/`**: (Added via `compose.yml`) A Kafka monitoring tool (KMinion by Redpanda) that provides a web UI for Kafka metrics, exposed on port 8088 on the host. It depends on `k8s-sandbox` being healthy.
