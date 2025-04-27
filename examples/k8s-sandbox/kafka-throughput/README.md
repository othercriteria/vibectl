# Kafka Throughput Optimization Demo

**Status: Work In Progress**

This demo showcases using `vibectl` to automatically optimize a Kafka cluster for a specific goal: maximizing producer throughput while minimizing consumer latency.

## Overview

The demo environment consists of:

1.  **k8s-sandbox**: A container running K3d to create a lightweight Kubernetes cluster.
2.  **Kafka**: A single-node KRaft Kafka cluster deployed within K3d using basic Kubernetes manifests.
3.  **vibectl**: An agent running within the `k8s-sandbox` container, configured to interact with the Kafka cluster.
4.  **Producer**: A Python application sending messages to Kafka at a configurable rate and size. It adaptively increases its target rate when consumer latency is low.
5.  **Consumer**: A Python application consuming messages, calculating end-to-end p99 latency and its own consumption rate, and writing these metrics to shared files.
6.  **Kafka Demo UI**: A Flask/SocketIO web application that displays key metrics (latency, producer rates, consumer rate), container health status, status file freshness, and the latest `vibectl` agent logs.
7.  **Shared Volume (`status-volume`)**: A host bind mount directory (`./status-volume/`) shared into containers for metrics and log files.

`vibectl` monitors the consumer latency and attempts to achieve its goal (maximize producer throughput, minimize consumer latency) by modifying Kafka broker configurations (via `kubectl patch`).

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

-   **Web UI**: Access the live dashboard by navigating to `http://localhost:8081` in your browser.
-   **Container Logs**: View the logs using make:
    ```bash
    # Follow logs for all services
    make logs

    # Follow logs for a specific service
    make logs-k8s-sandbox
    make logs-producer
    make logs-consumer
    make logs-kafka-demo-ui
    ```
-   **Vibectl Agent Logs**: You can see these directly in the Web UI or via:
    ```bash
    tail -f ./status-volume/vibectl_agent.log
    # Or via container logs
    make logs-k8s-sandbox | grep 'vibectl auto'
    ```
-   **Status Files**: Check the raw status files reported by the components:
    ```bash
    # Watch latency
    watch cat ./status-volume/latency.txt
    # Watch producer stats (target/actual rate, size)
    watch cat ./status-volume/producer_stats.txt
    # Watch consumer stats (rate)
    watch cat ./status-volume/consumer_stats.txt
    ```

## Stopping the Demo

-   Run the following command:
    ```bash
    make down
    ```
-   This will stop and remove containers, networks, and the shared volume.

## Current Status & Next Steps

-   **Implemented**: Core components, orchestration (`run.sh`/`Makefile`/`compose.yml`), K8s/Kafka/Agent setup, producer (adaptive rate), consumer (latency/rate reporting), Web UI (metrics, health, logs), various fixes (volume mounts, readiness signals, producer status).
-   **Next Steps**: Observe the full demo run, refine `vibectl` instructions if needed, finalize demo-specific documentation.
