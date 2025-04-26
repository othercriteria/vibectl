# Planned Changes

## Core Components

- **Kubernetes Sandbox (k8s):**
    - Use K3d (simpler networking via internal port-forwarding pattern from Bootstrap demo).
    - Run Kafka cluster using basic Kubernetes manifests (StatefulSet, Service, ConfigMap) aiming for KRaft mode (no Zookeeper) for simplicity.
    - Run `vibectl` agent within the cluster.

### Changed
- Use a file on the shared volume (e.g., `/tmp/status/latency.txt`) for latency feedback. Overseer writes to it, `k8s-sandbox` entrypoint reads it, injects into `vibectl` memory (e.g., `vibectl memory update "Latest consumer p99 latency: X ms"`), then runs `vibectl auto`.

## `vibectl` Integration

- Define the `vibectl` agent's goal: Minimize consumer latency while maximizing producer throughput by tuning Kafka broker configurations (e.g., `num.io.threads`, `num.network.threads`, JVM heap size/GC settings) via direct modification of Kafka ConfigMaps/StatefulSet.
- Develop mechanism for injecting latency metrics into `vibectl`'s memory or observation space via the shared volume file (`/tmp/status/latency.txt`).

## Demo Infrastructure & Documentation

- Create `examples/kafka-throughput-demo` directory.
- Develop Dockerfiles for each container (Producer, Consumer, Overseer, k8s-sandbox).
    - k8s-sandbox Dockerfile should include K3d, kubectl.
    - Reuse Docker GID detection logic from CTF `run.sh` (`lines 102-112`) for k8s-sandbox container.
- Develop entrypoint script(s) for containers, especially k8s-sandbox.
    - Use modular functions (Bootstrap `bootstrap-entrypoint.sh`).
    - Implement K3d setup and kubeconfig patching (Bootstrap `bootstrap-entrypoint.sh` `lines 20-51`).
    - Deploy Kafka using basic manifests (apply YAML).
    - Implement loop to check shared volume file (`/tmp/status/latency.txt`), update `vibectl` memory, and run `vibectl auto`.
    - Use `kubectl port-forward` in background with `trap` for cleanup to expose internal K8s services (e.g., Kafka broker endpoint 9092) to other containers (Bootstrap `bootstrap-entrypoint.sh` `lines 163-165`).
    - Use phased execution with status files for idempotency (Bootstrap `bootstrap-entrypoint.sh` `lines 290-316`).
    - End k8s-sandbox entrypoint with keep-alive loop (Bootstrap `bootstrap-entrypoint.sh` `lines 319-325`).
- Create `compose.yml` defining services and dependencies.
    - Use `depends_on` with `condition: service_healthy` for startup order (Kafka -> Producer/Consumer -> Overseer) (CTF `compose.yml` `lines 33-36`, `79-82`).
    - Implement service `healthcheck`s (Kafka brokers, producer/consumer readiness) (CTF `compose.yml` `lines 25-30`, `68-74`).
    - Consider shared volume (`tmpfs`) for metric/status passing or simple HTTP endpoints (CTF `compose.yml` `lines 22-23`, `64-65`, `89-90`, `105-109`).
    - Define a dedicated Docker network (CTF `compose.yml` `lines 101-103`).
- Develop `run.sh` script to orchestrate setup and cleanup.
    - Adapt argument parsing for Kafka-specific parameters (CTF `run.sh` `lines 5-29`).
    - Handle required configuration/secrets via environment variables (prompt if missing) (CTF `run.sh` `lines 59-69`).
    - Add prerequisite checks (Docker, compose, memory?) (Bootstrap `launch.sh` `lines 61-98`).
    - Consider generating a temporary Compose file if complex runtime config is needed (Bootstrap `launch.sh` `lines 107-145`).
    - Implement robust `cleanup()` function and `trap` (CTF `run.sh` `lines 71-99`, `line 118`). Separate `cleanup.sh` (Bootstrap) is also an option.
    - Use explicit `build` then `up` steps (Bootstrap `launch.sh` `lines 148-149`).
    - Implement application-level status checks (e.g., waiting for status files) for better startup coordination (Bootstrap `launch.sh` `lines 152-177`).
    - Provide clear user feedback on progress and next steps (Bootstrap `launch.sh` `lines 179-195`).
- Write `examples/kafka-throughput-demo/README.md` detailing setup, prerequisites, and how to run the demo.
- Add `examples/kafka-throughput-demo/STRUCTURE.md` documenting the demo's layout.
- Update root `README.md` and `STRUCTURE.md` to reference the new example.

## Workflow

- Track progress via a dedicated feature worktree and PR.
- Iterate on components, ensuring clear interfaces between them.
