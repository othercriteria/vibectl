# Planned Changes

## Core Components

- **Kubernetes Sandbox (k8s):**
    - Evaluate Kind vs. k3d for setup (consider ease of port-forwarding/networking vs. startup time).
    - Run Kafka cluster (e.g., using Strimzi operator or Helm chart).
    - Run `vibectl` agent within the cluster.
- **Producer Container:**
    - Develop Python script to generate configurable Kafka messages (rate, size).
    - Implement topic distribution logic.
    - Use acknowledgements (`acks=all`) for reliable production.
    - Include a timestamp and potentially a hash payload for latency/integrity check.
- **Consumer Container:**
    - Develop Python script to consume messages from Kafka topics.
    - Verify message integrity (e.g., hash check using a shared secret unknown to `vibectl`).
    - Calculate end-to-end latency based on producer timestamp.
    - Expose latency metrics (e.g., via a simple HTTP endpoint).
- **Overseer Container:**
    - Develop a simple web UI (e.g., Flask/FastAPI + basic HTML/JS) or CLI tool.
    - Display key metrics: producer rate, consumer latency (p50, p99), `vibectl` actions/logs.
    - Implement logic to adjust producer rate based on observed latency thresholds.
    - Inject latency feedback into the k8s sandbox container (mechanism TBD: e.g., write to a file mount, exec into `vibectl` pod, custom endpoint).
    - Trigger periodic `vibectl auto --limit 5` runs within the k8s container after injecting feedback.

## `vibectl` Integration

- Define the `vibectl` agent's goal: Minimize consumer latency while maximizing producer throughput by tuning Kafka broker configurations (e.g., `num.io.threads`, `num.network.threads`, JVM heap).
- Develop mechanism for injecting latency metrics into `vibectl`'s memory or observation space.

## Demo Infrastructure & Documentation

- Create `examples/kafka-throughput-demo` directory.
- Develop Dockerfiles for each container.
- Create configuration/orchestration files (docker-compose, Kubernetes manifests, Kind/k3d config).
- Write `examples/kafka-throughput-demo/README.md` detailing setup, prerequisites, and how to run the demo.
- Add `examples/kafka-throughput-demo/STRUCTURE.md` documenting the demo's layout.
- Update root `README.md` and `STRUCTURE.md` to reference the new example.

## Workflow

- Track progress via a dedicated feature worktree and PR.
- Iterate on components, ensuring clear interfaces between them.
