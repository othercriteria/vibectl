# Kafka Throughput Optimization Demo

**Status: Mostly Operational** (Undergoing final debugging for full reliability)

This demo showcases using `vibectl` to automatically optimize a Kafka cluster for a specific goal: maximizing producer throughput while minimizing consumer latency.

## Overview

The demo environment consists of:

1.  **k8s-sandbox**: A container running K3d to create a lightweight Kubernetes cluster. It also hosts the `vibectl` agent.
2.  **Kafka**: A single-node KRaft Kafka cluster deployed within K3d using basic Kubernetes manifests.
3.  **vibectl Agent**: An instance of `vibectl` running within the `k8s-sandbox` container, configured with custom instructions to interact with the Kafka cluster and optimize its performance based on observed metrics.
4.  **Producer**: A Python application sending messages to Kafka. Its target send rate adaptively increases when consumer latency is low and decreases if latency is high.
5.  **Consumer**: A Python application consuming messages, calculating end-to-end p99 latency and its own consumption rate. These metrics are written to the shared status volume.
6.  **Kafka Demo UI**: A Flask/SocketIO web application that displays key metrics (latency, producer/consumer rates), container health, status file freshness, and the latest `vibectl` agent logs.
7.  **Shared Volume (`./status-volume/`)**: A host directory bind-mounted into relevant containers at `/tmp/status`. This is used for sharing metrics, logs, and status signals (like `kafka_ready`) between the host script (`run.sh`) and the containers.

`vibectl`, running in the `k8s-sandbox`, monitors metrics (primarily from the `kafka-latency-metrics` ConfigMap, which is updated by other components) and attempts to achieve its goal by modifying Kafka broker configurations (via `kubectl patch`), guided by its custom instructions file (`vibectl_instructions.txt`).

## Prerequisites

-   **Docker**: Ensure Docker Desktop or Docker Engine is installed and running.
-   **Docker Compose**: Ensure Docker Compose (v1 `docker-compose` or v2 `docker compose`) is installed.
-   **Anthropic API Key**: You need an Anthropic API key (starting with `sk-ant-`) for `vibectl` to function. The `run.sh` script will prompt you if the `VIBECTL_ANTHROPIC_API_KEY` environment variable is not set.
-   **Resources**: Ensure your system has sufficient resources (recommend ~4GB+ RAM available for Docker).

## How to Run

1.  **Navigate to the demo directory:**
    ```bash
    cd examples/k8s-sandbox/kafka-throughput
    ```

2.  **Make the run script executable (if not already):**
    ```bash
    chmod +x run.sh
    ```

3.  **Build and Start the Demo:**
    ```bash
    make up
    ```
    -   This command uses the `Makefile` to execute `./run.sh`.
    -   `run.sh` prepares environment variables (detecting Docker GID, prompting for API key if needed, generating a Kafka Cluster ID), builds Docker images (if not already built or if `--build` is passed to `run.sh`), and starts all services in detached mode using `docker compose up -d`.
    -   You can view the combined logs using `make logs`.

4.  **Wait for Startup:**
    -   `run.sh` will wait for the `k8s-sandbox` to signal Kafka readiness (via the `./status-volume/kafka_ready` file) before exiting successfully.
    -   Monitor progress using `make logs` or `make ps`.
    -   Once `run.sh` completes, the services are running, and the UI should be accessible.

## How it Works - Key Components & Logic

-   **`run.sh` (Host Script):**
    -   Handles initial setup: API key check/prompt, Docker GID detection for container permissions, Kafka Cluster ID generation (saved to `./status-volume/kafka_cluster_id.txt`).
    -   Builds images via `docker compose build`.
    -   Starts services via `docker compose up -d`.
    -   Waits for the `k8s-sandbox` to create `./status-volume/kafka_ready` as a signal that Kafka is up and port-forwarded, before allowing producer/consumer to fully start (via `depends_on: service_healthy`).

-   **`k8s-sandbox/entrypoint.sh` (Inside `k8s-sandbox` container):**
    -   **Phase 1 (K8s & Kafka):**
        -   Robustly sets up (or recreates) a K3d cluster.
        -   Patches the `kubeconfig` to be accessible from within the container (using the Docker host's gateway IP).
        -   Copies the patched `kubeconfig` to `/tmp/status/k3d_kubeconfig` for the UI service.
        -   Deploys Kafka (using `kafka-kraft.yaml` and the generated cluster ID).
        -   Waits for Kafka pods to be ready.
        -   Sets up a resilient port-forwarding mechanism for Kafka using `port_forward_manager.py` to expose Kafka on `localhost:9092` within the container (which maps to `k8s-sandbox:9092` on the Docker network for other containers).
        -   Touches `/tmp/status/kafka_ready` to signal `run.sh`.
    -   **Phase 2 (Vibectl):**
        -   Installs `vibectl` from the mounted source code.
        -   Configures `vibectl` (API key, model, paths).
        -   Loads custom instructions from `/home/sandbox/vibectl_instructions.txt`, substituting environment variables like `${TARGET_LATENCY_MS}` and `${K8S_SANDBOX_CPU_LIMIT}` using `sed`.
        -   Starts the `latency-reporter.py` script in the background.
        -   Initiates the main `vibectl auto` loop, which runs continuously, logging its actions to `/tmp/status/vibectl_agent.log`.

-   **`vibectl_instructions.txt`:**
    -   Provides the operational goals and context to the `vibectl` agent.
    -   Key environment variables are substituted into this file at runtime by `entrypoint.sh` to provide dynamic configuration details (e.g., resource limits, target latency).

## Makefile Targets

A `Makefile` is provided for convenience:

-   `make help`: Show available targets.
-   `make build`: Build all Docker images.
-   `make up`: Run `./run.sh` to build (if needed) and start all services detached. Waits for Kafka readiness.
-   `make ps`: Show the status of the running services.
-   `make logs`: Follow logs for all services.
-   `make logs-<service>`: Follow logs for a specific service (e.g., `make logs-producer`, `make logs-k8s-sandbox`).
-   `make shell-<service>`: Open a shell (`bash` or `sh`) inside a running service container (e.g., `make shell-consumer`).
-   `make down`: Stop and remove all containers, networks. The `./status-volume` directory on the host is not removed by this command.

## Monitoring the Demo

-   **Web UI**: Access the live dashboard by navigating to `http://localhost:8081` in your browser.
-   **Container Logs**: View the logs using `make logs` or `make logs-<service>`.
-   **Vibectl Agent Logs**: The primary log for `vibectl auto` operations is `./status-volume/vibectl_agent.log` on the host, which is also displayed in the Web UI. You can also tail it directly:
    ```bash
    tail -f examples/k8s-sandbox/kafka-throughput/status-volume/vibectl_agent.log
    ```
-   **Status Files (for debugging)**: Check the shared status files in `./status-volume/` on your host, or `/tmp/status/` inside any of the service containers.

## Stopping the Demo

-   Run `make down` to stop and remove containers and networks:
    ```bash
    make down && make clean-cluster
    ```

## Troubleshooting & Past Issues

If issues persist, check the logs from `make logs` and the `vibectl_agent.log` first.
