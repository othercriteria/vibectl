# Planned Changes for Kafka Throughput Demo

## Core Goal

Use `vibectl` to automatically optimize a Kafka cluster running in K3d to maximize producer throughput while minimizing consumer P99 latency.

## Outstanding Work

1.  **Observe & Refine `vibectl` Optimization:**
    *   Run the complete demo for an extended period.
    *   Verify the `vibectl` agent loop correctly identifies bottlenecks (e.g., low Kafka threads/heap) and applies appropriate patches (`kubectl patch`). Check `vibectl_agent.log` for details.
    *   Observe if the optimizations move towards the goal (max producer throughput, min consumer p99 latency).
    *   Evaluate if the current `vibectl_instructions.txt` provides sufficient guidance or needs refinement based on observed behavior.

2.  **Monitor Adaptive Producer Load:**
    *   Observe whether the producer increases load (target rate) when consumer latency is below the threshold.
    *   Check if the actual producer rate tracks the target rate reasonably well.

3.  **Finalize Documentation:**
    *   Update `README.md` in the demo directory (`examples/k8s-sandbox/kafka-throughput/README.md`) with final details, usage instructions, observed behavior during the test run, and any relevant tuning parameters discovered.

4.  **Code Cleanup/Polish (Optional):**
    *   Review code across components (`producer`, `consumer`, `k8s-sandbox`, `kafka-demo-ui`) for potential refactoring, improved error handling, or clearer comments.
