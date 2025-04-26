# Planned Changes for Kafka Throughput Demo

## Core Goal

Use `vibectl` to automatically optimize a Kafka cluster running in K3d to maximize producer throughput while minimizing consumer P99 latency.

## Key Components & Setup

-   **Kubernetes Sandbox:** K3d cluster running KRaft Kafka (single-node) via manifests (`k8s-sandbox/`).
-   **`vibectl` Integration:** Agent runs in the sandbox, reads latency from `/tmp/status/latency.txt`, tunes Kafka broker settings (`KAFKA_HEAP_OPTS`, `KAFKA_NUM_NETWORK_THREADS`, `KAFKA_NUM_IO_THREADS`) via `kubectl patch`.
-   **Producer/Consumer:** Python apps sending/receiving messages, consumer reports P99 latency to `/tmp/status/latency.txt` (`producer/`, `consumer/`).
-   **Overseer:** Simple Python app monitoring latency file (`overseer/`).
-   **Infrastructure:** Docker Compose (`compose.yml`), Makefile for management, `run.sh` helper script.
-   **Shared Volume:** `/tmp/status/` (tmpfs volume `status-volume`) for status/latency communication.

## Optimization Strategy & Constraints

-   **De-optimization:** Kafka starts with intentionally low resource settings (`-Xms256m -Xmx256m`, 1 network thread, 2 IO threads) for clear optimization headroom.
-   **Resource Limits:** `k8s-sandbox` container limited (default: 4 CPUs, 4Gi RAM) to create a constrained environment.
-   **Inform `vibectl`:** Resource limits passed to `vibectl setup` in `k8s-sandbox/entrypoint.sh`.

## Current Status

**Completed:**

1.  **Initial Implementation:** All core components (`k8s-sandbox` with K3d/Kafka/vibectl agent, `producer`, `consumer`, basic `overseer`) implemented.
2.  **Orchestration:** `compose.yml`, `Makefile`, and `run.sh` helper setup.
3.  **Configuration:** De-optimized Kafka defaults, resource limits, healthchecks, `vibectl setup` goal/constraints defined.
4.  **Documentation:** Initial `README.md` and `STRUCTURE.md` created.

**Next Steps:**

1.  **Testing & Iteration:** Run the demo (`make up`), observe behavior, debug issues, and refine components.
2.  **Documentation Refinement:** Update `README.md` and `STRUCTURE.md` with final details and observations from testing.
3.  **Overseer Enhancement (Optional):** Add logic to potentially adjust producer rate based on latency or `vibectl` status.
