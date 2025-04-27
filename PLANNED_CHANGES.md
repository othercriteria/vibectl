# Planned Changes for Kafka Throughput Demo

## Core Goal

Use `vibectl` to automatically optimize a Kafka cluster running in K3d to maximize producer throughput while minimizing consumer P99 latency.

## Key Components & Setup

-   **Kubernetes Sandbox:** K3d cluster running KRaft Kafka (single-node) via manifests (`k8s-sandbox/`).
-   **`vibectl` Integration:** Agent runs in the sandbox, reads latency from `/tmp/status/latency.txt`, tunes Kafka broker settings (`KAFKA_HEAP_OPTS`, `KAFKA_NUM_NETWORK_THREADS`, `KAFKA_NUM_IO_THREADS`) via `kubectl patch`.
-   **Producer/Consumer:** Python apps sending/receiving messages, consumer reports P99 latency to a ConfigMap (`producer/`, `consumer/`).
-   **Kafka Demo UI:** Simple Python app monitoring latency file (future: web UI) (`kafka-demo-ui/`).
-   **Infrastructure:** Docker Compose (`compose.yml`), Makefile for management, `run.sh` helper script.
-   **Shared Volume:** `/tmp/status/` (tmpfs volume `status-volume`) for status/latency communication.

## Optimization Strategy & Constraints

-   **De-optimization:** Kafka starts with intentionally low resource settings (`-Xms256m -Xmx256m`, 1 network thread, 2 IO threads) for clear optimization headroom.
-   **Resource Limits:** `k8s-sandbox` container limited (default: 4 CPUs, 4Gi RAM) to create a constrained environment.
-   **Inform `vibectl`:** Resource limits passed to `vibectl setup` in `k8s-sandbox/entrypoint.sh`. (Note: `vibectl setup` is no longer used; instructions are loaded manually in entrypoint).

## Current Status

**Completed:**

1.  **Initial Implementation:** All core components (`k8s-sandbox` with K3d/Kafka/vibectl agent, `producer`, `consumer`, basic `overseer`) implemented.
2.  **Orchestration:** `compose.yml`, `Makefile`, and `run.sh` helper setup.
3.  **Configuration:** De-optimized Kafka defaults, resource limits, healthchecks defined.
4.  **Documentation:** Initial `README.md` and `STRUCTURE.md` created.
5.  **Orchestration Fixes:** Resolved issues with GID/ClusterID generation and environment variable passing between Makefile, run.sh, and Docker Compose.
6.  **Startup Reliability:** Improved K3d startup logic to reuse existing clusters, preventing frequent deletion/creation errors.
7.  **Connectivity & Setup:** Resolved network connectivity issues between producer/consumer and Kafka broker.
8.  **Producer Errors:** Fixed `acks` parameter type mismatch (`str` vs `int`) in `producer.py`.
9.  **Vibectl Configuration:** Fixed `vibectl` model loading issue in `k8s-sandbox` by ensuring `llm` and `llm-anthropic` are installed and the API key is configured correctly via `llm keys path`.
10. **Latency Reporting:** Consumer now correctly reports P99 latency to a ConfigMap.
11. **Vibectl Loop:** `k8s-sandbox` entrypoint now successfully reads latency and triggers `vibectl auto` in a loop.
12. **Cleanup:** Renamed `overseer` component to `kafka-demo-ui`.

**Next Steps:**

1.  **Observe & Refine:** Run the demo for an extended period to observe `vibectl`'s optimization behavior. Refine the `vibectl_instructions.txt` or agent logic if needed to achieve the desired throughput/latency balance.
2.  **Documentation Finalization:** Update `README.md` and `STRUCTURE.md` with final details, usage instructions, and observations from testing (this current update addresses most of this).
3.  **Kafka Demo UI Enhancement (Optional):** Develop the `kafka-demo-ui` component to provide a simple web interface for visualizing latency and potentially system status.
4.  **Commit Changes:** Create a commit to save the current functional state.
