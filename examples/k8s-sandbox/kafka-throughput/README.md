# Kafka Throughput Optimization Demo

**Status: Work In Progress**

This demo showcases using `vibectl` to automatically optimize a Kafka cluster for a specific goal: maximizing producer throughput while minimizing consumer latency.

## Overview

The demo environment consists of:

1.  **k8s-sandbox**: A container running K3d to create a lightweight Kubernetes cluster.
2.  **Kafka**: A single-node KRaft Kafka cluster deployed within K3d using basic Kubernetes manifests.
3.  **vibectl**: An agent running within the `k8s-sandbox` container, configured to interact with the Kafka cluster.
4.  **Producer**: A Python application sending messages to Kafka at a configurable rate and size.
5.  **Consumer**: (WIP) A Python application consuming messages, calculating end-to-end latency, and writing it to a shared file.
6.  **Overseer**: (WIP) A potential monitoring or control component.

`vibectl` monitors the consumer latency (read from `/tmp/status/latency.txt` inside the `k8s-sandbox`) and attempts to achieve its goal by modifying Kafka broker configurations (via `kubectl patch` or similar mechanisms).

## Prerequisites

-   **Docker**: Ensure Docker Desktop or Docker Engine is installed and running.
-   **Docker Compose**: Ensure Docker Compose (v1 `docker-compose` or v2 `docker compose`) is installed.
-   **Anthropic API Key**: You need an Anthropic API key (starting with `sk-ant-`) for `vibectl` to function. The script will prompt you if the `VIBECTL_ANTHROPIC_API_KEY` environment variable is not set.
-   **Resources**: Ensure your system has sufficient resources (recommend ~4GB+ RAM available for Docker).

## How to Run

1.  **Navigate to the demo directory:**
    ```bash
    cd examples/k8s-sandbox/kafka-throughput
    ```

2.  **Make the run script executable:**
    ```bash
    chmod +x run.sh
    ```

3.  **Build and Start the Demo:**
    ```bash
    make up
    ```
    -   This command uses the `Makefile` to build the necessary Docker images (if not already built) and start all services in detached mode.
    -   It handles prerequisite checks implicitly through the Docker build process and `run.sh` helper logic.
    -   It will prompt for your Anthropic API key if `VIBECTL_ANTHROPIC_API_KEY` is not set in your environment (handled by `run.sh` internally).

4.  **Wait for Kafka:**
    -   The `make up` command implicitly waits for the `k8s-sandbox` healthcheck to pass, which depends on the `kafka_ready` status file.
    -   You can monitor the startup progress using `make logs` or `make logs-k8s-sandbox`.

## Makefile Targets

A `Makefile` is provided for convenience:

-   `make help`: Show available targets.
-   `make build`: Build all Docker images.
-   `make up`: Build (if needed) and start all services detached.
-   `make ps`: Show the status of the running services.
-   `make logs`: Follow logs for all services.
-   `make logs-<service>`: Follow logs for a specific service (e.g., `make logs-producer`, `make logs-k8s-sandbox`).
-   `make shell-<service>`: Open a shell (`bash` or `sh`) inside a running service container (e.g., `make shell-consumer`).
-   `make check-latency`: Display the current content of the latency file (`./status-volume/latency.txt`).
-   `make down`: Stop and remove all containers, networks, and volumes associated with the demo.

## Monitoring the Demo

-   **Container Logs**: View the logs using make:
    ```bash
    # Follow logs for all services
    make logs

    # Follow logs for a specific service
    make logs-k8s-sandbox
    make logs-producer
    make logs-consumer
    ```
-   **Vibectl Actions**: Look for logs from the `vibectl auto` command within the `k8s-sandbox` logs:
    ```bash
    make logs-k8s-sandbox | grep 'vibectl auto'
    # Or follow live:
    make logs-k8s-sandbox | grep --line-buffered 'vibectl auto'
    ```
-   **Latency File**: Check the latency reported by the consumer:
    ```bash
    make check-latency
    # Or watch the file directly:
    watch cat ./status-volume/latency.txt
    ```

## Stopping the Demo

-   Run the following command:
    ```bash
    make down
    ```
-   This will stop and remove containers, networks, and the shared volume.

## Current Status & Next Steps

-   **Implemented**: `run.sh` orchestration (used by Makefile), `Makefile` for common tasks, `k8s-sandbox` setup (K3d, Kafka deployment, `vibectl` agent loop with goal/constraints), `producer` application, `consumer` application (reporting p99 latency), basic `overseer`, healthchecks, initial documentation, de-optimized Kafka defaults, resource limits in `compose.yml`, `vibectl setup` in entrypoint.
-   **TODO**: Thorough testing and debugging, refine documentation, add more sophisticated overseer logic (optional).
