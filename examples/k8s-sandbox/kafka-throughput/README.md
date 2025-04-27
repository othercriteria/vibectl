# Kafka Throughput Optimization Demo

**Status: Operational**

This demo showcases using `vibectl` to automatically optimize a Kafka cluster for a specific goal: maximizing producer throughput while minimizing consumer latency.

## Overview

The demo environment consists of:

1.  **k8s-sandbox**: A container running K3d to create a lightweight Kubernetes cluster.
2.  **Kafka**: A single-node KRaft Kafka cluster deployed within K3d using basic Kubernetes manifests.
3.  **vibectl**: An agent running within the `k8s-sandbox` container, configured to interact with the Kafka cluster.
4.  **Producer**: A Python application sending messages to Kafka at a configurable rate and size. It adaptively increases its target rate when consumer latency is low.
5.  **Consumer**: A Python application consuming messages, calculating end-to-end p99 latency and its own consumption rate, and writing these metrics to shared files.
6.  **Kafka Demo UI**: A Flask/SocketIO web application that displays key metrics (latency, producer rates, consumer rate), container health status, status file freshness, and the latest `vibectl` agent logs.
7.  **Shared Volume (`status-volume`)**: A Docker named volume (using tmpfs) shared into relevant containers at `/tmp/status` for metrics and log files.

`vibectl`, running in the `k8s-sandbox`, monitors metrics from the `kafka-latency-metrics` ConfigMap (which is updated by other components) and attempts to achieve its goal by modifying Kafka broker configurations (via `kubectl patch`), guided by its instructions.

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
    -   This command uses the `Makefile` to execute `./run.sh`.
    -   `run.sh` prepares environment variables (prompting for API key if needed), builds Docker images (if not already built), and starts all services using `docker compose up --build`.
    -   The services will run in the **foreground**. Press `Ctrl+C` in the terminal where you ran `make up` to stop them.

4.  **Wait for Startup:**
    -   The script will show logs as services start.
    -   Wait for the `k8s-sandbox`, `producer`, and `consumer` healthchecks to pass and for the UI to become accessible.
    -   You can monitor the startup progress in the foreground logs or use `make logs` / `make ps` in another terminal.

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
    # Follow logs for all services (if not running in foreground)
    make logs

    # Follow logs for a specific service
    make logs-k8s-sandbox
    make logs-producer
    make logs-consumer
    make logs-kafka-demo-ui
    ```
-   **Vibectl Agent Logs**: You can see these directly in the Web UI or via container logs:
    ```bash
    # Follow k8s-sandbox logs where vibectl runs
    make logs-k8s-sandbox
    # Or grep specifically for vibectl output
    docker compose -f examples/k8s-sandbox/kafka-throughput/compose.yml logs k8s-sandbox | grep 'vibectl auto'
    ```
-   **Status Files (for debugging)**: Check the raw status files inside a running container (e.g., the UI container):
    ```bash
    # Shell into the UI container
    make shell-kafka-demo-ui
    # Then view files inside the container
    ls -l /tmp/status/
    cat /tmp/status/producer_stats.txt
    cat /tmp/status/consumer_stats.txt
    tail /tmp/status/vibectl_agent.log
    exit
    ```

## Stopping the Demo

-   If running in the foreground (via `make up`), press `Ctrl+C` in the terminal.
-   Run `make down` afterwards to ensure containers and the network are removed:
    ```bash
    make down
    ```
-   This will stop and remove containers, networks, and the named volume `status-volume`.
