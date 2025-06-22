# Planned Changes: Server-Side Rate Limiting & Quota Enforcement

## Goals

1. Allow operators to cap resource usage (RPM, concurrency, input length, request timeout, optional monthly token quotas).
2. Keep vibectl-server stateless: limits are supplied via config, not tied to user accounts or plans.
3. Provide clear gRPC errors (`RESOURCE_EXHAUSTED`) and structured metrics/logs when limits are hit.
4. Design code so that a Redis (or other) backend can be plugged in later without breaking API/stability.

## Non-Goals

* No concept of pricing tiers, balances, or plan names inside vibectl.
* No persistence layer in this PR – in-memory counters only.
* No UI/CLI for editing limits; operators manage config files/helm values externally.

## Configuration Surface (operator-supplied)

```
server:
  limits:
    global:
      max_requests_per_minute: 120       # optional
      max_concurrent_requests: 10        # optional
      max_input_length: 32000            # optional, chars
      request_timeout_seconds: 30        # optional

    # keyed by JWT `sub` or `kid`
    per_token:
      "demo-user":
        max_requests_per_minute: 5
      "svc-backend":
        max_concurrent_requests: 2
```

* Any field omitted → unlimited.
* If a token has no entry in `per_token`, the `global` block applies.
* Config reload strategy: watch file + SIGHUP; first version may require restart – hot-reload to follow.

## Enforcement Design

1. **Interceptor chain**
   * `RateLimitInterceptor` checks RPM + concurrency **before** calling the servicer.
   * Optional `QuotaInterceptor` (token quotas) executed **after** request to account for token usage (draft API only).
2. **Limit backend abstraction**

```python
a = LimitBackend()
current = a.incr(key="user:rpm", window_s=60, amount=1)
```

* Default impl: in-process token bucket + semaphore.
* Future: Redis impl satisfying same interface (see TODO-SERVER.md).

3. **Keying strategy**
   * `<sub>:rpm`   – ~fixed 60-second window counter (MVP); sliding window or token-bucket may replace this in future
   * `<sub>:conc`  – in-flight counter (increment on request start, decrement on completion)
   * `<sub>:tokens_YYYY_MM` – monthly quota (future)
4. **Throttling response**
   * Exceed → `grpc.StatusCode.RESOURCE_EXHAUSTED` with metadata: `retry-after-ms=<ms>` and `limit-type=<rpm|concurrency|token>`.

## Observability

* Prometheus metrics via `prometheus_client` (behind `--enable-metrics` flag)
  * `vibectl_requests_total{sub="demo-user"}`
  * `vibectl_rate_limited_total{sub="demo-user",limit_type="rpm"}`
  * `vibectl_concurrent_in_flight{sub="demo-user"}`
* Structured JSON logs for each throttle event: `{sub, limit_type, current, allowed, path}`
* `GetServerInfo` populates `ServerLimits` with **global** limits so clients can self-throttle.

## Configuration Layer Prep Work

Before wiring the interceptors we will beef up the config subsystem so that limit data is strongly typed, validated and reloadable:

1. **Typed model for limits**

   ```python
   @dataclass
   class Limits:
       max_requests_per_minute: int | None = None
       max_concurrent_requests: int | None = None
       max_input_length: int | None = None
       request_timeout_seconds: int | None = None
   ```

   `ServerConfig.get_limits(token_sub: str | None) -> Limits` returns the effective limits (global + per-token overrides).
2. **Validation helpers**
   * Ensure integers ≥1 and within sensible maxima.
   * Pydantic 2 adoption **deferred**; stick to lightweight custom validation for MVP to avoid new runtime deps.
3. **Hot-reload MVP**
   * File-watch thread using `watchdog`; on change → re-validate → swap in-memory cache → fire `config_changed` callbacks.
   * Fail-open strategy: on invalid update keep previous config and log error.
4. **CLI quality-of-life**
   * Extend `vibectl-server config` with `show / set / validate` sub-commands for server config (mirrors client CLI).
   * New CLI flags `--max-rpm`, `--max-concurrent` as shortcuts that patch overrides.
5. **Unit tests**
   * `tests/server/test_config_limits.py` – merge precedence & validation.
   * `tests/server/test_config_reload.py` – verify watcher behaviour.
6. **Runtime integration**
   * Pass a live `ServerConfig` reference to interceptors; they subscribe to `on_config_change` to refresh limits without restart.

## Demo Manifests Impact

The ACME demo ( `examples/manifests/vibectl-server/demo-acme-http.sh`  + related YAML) needs only *manifest* tweaks to exercise rate-limiting & metrics:

* **`configmap-acme-http.yaml`** – add a `server.limits` block under `server:` to define global limits (and any per-token overrides).
* **`deployment-acme-http.yaml`** – expose a new `metrics` container port (e.g. 9095) and add Prometheus scrape annotations.
* **`service-acme-http.yaml`** – list the `metrics` port in the internal ClusterIP service (LB service untouched).
* **Script logic** – no changes; it already builds/apply-s manifests. JWT generation, ACME, Pebble, MetalLB steps remain valid.

Thus the demo will automatically showcase limit enforcement and live Prometheus counters once the new code lands.

## Incremental Delivery (within this feature branch)

1. Expand `server/config.py` + CLI flags to parse `server.limits.*` blocks.
2. Populate `ServerLimits` from config (read-only) – **no enforcement yet**.
3. Add `RateLimitInterceptor` with in-memory backend (fixed 60-s window, per-request semaphore); unit-tests for RPM & concurrency.
4. Start internal `/metrics` server (default 9095) and wire basic Prometheus counters + structured logs.
5. Hot-reload support (file-watch) – nice-to-have; may slip to follow-up PR.

## Future Work (tracked in TODO-SERVER.md)

* Redis limit backend for multi-instance deployments.
* Token quota accounting (`QuotaInterceptor`) using metrics from `ExecutionMetrics`.
* Operator tooling for live limit changes (K8s operator, Helm charts, etc.).

## Open Questions

* Sliding-window vs fixed-window RPM counter – prototype will start with fixed window (simpler) unless operator feedback prefers sliding.
* Where to surface Prometheus metrics → **decision: built-in HTTP endpoint on configurable port (default 9095)**.

---
*This document guides the scope of the current PR. Items marked as "Future Work" will **not** be implemented here, only designed for.*
