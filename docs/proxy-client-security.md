# vibectl Client-Side Proxy Security (V1)

> Companion to `docs/llm-proxy-server.md`. This document focuses on the **client-side** protections now built into vibectl when it is configured to use an LLM proxy server.

## 📑 Table of Contents
1. Overview & Threat Model
2. Feature Summary
   1. Named Proxy Profiles
   2. Request Sanitization
   3. Audit Logging
   4. Response Validation & Confirmation
3. Configuration Reference
4. CLI Usage Examples
5. Developer Notes (Code Locations & Extensibility)
6. Roadmap & Future Work

---

## 1 Overview & Threat Model

The **vibectl proxy security hardening (V1)** protects users who route their LLM traffic through a *semi-trusted* proxy (for example, a shared corporate proxy or a staging environment).  The design assumes that the proxy operator is generally trustworthy **but might be compromised now or in the future**.

### Threats addressed

* **Secret exfiltration** – Kubernetes service-account tokens, bearer tokens, certificates, …
* **Malicious responses** – LLM output that tries to execute destructive `kubectl` commands
* **Long-term profiling** – Proxy collecting request/response data over time
* **TLS mis-configuration** – Man-in-the-middle attacks if certificates are wrong

The following sections describe how vibectl mitigates each threat in V1.

---

## 2 Feature Summary

### 2 · 1 Named Proxy Profiles

* **Declarative config** under `proxy.profiles.<name>` in `~/.config/vibectl/config.yaml`.
* Each profile stores: `server_url`, `jwt_path`, `ca_bundle_path`, timeouts, **and a dedicated `security` block**.
* **Activation** is controlled by the single top-level key `proxy.active`.  Setting it to `null` disables all proxy usage.
* The legacy boolean flags (`proxy.enabled`, `proxy.server_url`, …) were **removed** for clarity.

Example excerpt:

```yaml
proxy:
  active: "corporate-llm"
  timeout_seconds: 30
  retry_attempts: 3
  profiles:
    corporate-llm:
      server_url: "vibectl-server://llm.corp.com:443"
      jwt_path: "~/.config/vibectl/corp.jwt"
      ca_bundle_path: "~/.config/vibectl/corp-ca.pem"
      security:
        sanitize_requests: true
        audit_logging: true
        confirmation_mode: "per-command"
```

### 2 · 2 Request Sanitization

Module: `vibectl/security/sanitizer.py`

* **Detects & redacts secrets** before they leave the workstation.
* Patterns implemented (100 % test coverage):
  * Kubernetes tokens & API URLs
  * Bearer tokens & JWTs
  * PEM-encoded certificates / keys
  * High-entropy base-64 blobs
* Redactions keep context while hiding sensitive bytes, e.g.

```text
"Authorization: Bearer {{redacted:k8s-token:256b}}"
```

* Configurable per-profile with `security.sanitize_requests` and `warn_sanitization`.
* Users can suppress the per-request warning banner with `--no-sanitization-warnings`.

### 2 · 3 Audit Logging

Module: `vibectl/security/audit.py`

* Structured JSON logs (one event per line) written **per proxy profile**.
* Captures:
  * request / response hashes (SHA-256)
  * secret types & counts
  * generated kubectl command & user approval
  * basic timing & connection metadata
* Log files live at `~/.config/vibectl/audit-<profile>.log` (configurable).
* Companion CLI commands:
  * `vibectl audit show`  – human-readable table view
  * `vibectl audit export` – raw JSON/CSV for pipelines
  * `vibectl audit info`  – size, path & rotation info

### 2 · 4 Response Validation & Confirmation

* CLI subcommands now annotate generated kubectl ops with *risk metadata*.
* Helper `is_destructive_kubectl_command()` detects operations like `delete`, `drain`, `cordon`, …
* Confirmation policy determined by `security.confirmation_mode`:
  * `none` – never ask (scripts/Bot usage)
  * `per-session` – ask once per CLI invocation
  * `per-command` – ask every destructive action (default)
* Global `--yes` flag (or *semiauto* mode) still bypasses all confirmations.

---

## 3 Configuration Reference (Security-Related Keys)

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `proxy.active` | string \| null | `null` | Name of the active proxy profile. `null` disables proxy |
| `proxy.profiles.*.security.sanitize_requests` | bool | `true` | Enable secret detection & redaction |
| `proxy.profiles.*.security.audit_logging` | bool | `true` | Write structured audit logs |
| `proxy.profiles.*.security.confirmation_mode` | `none`\|`per-session`\|`per-command` | `per-command` | Confirmation policy for destructive kubectl |
| `proxy.timeout_seconds` | int | 30 | Global request timeout (overridable per profile) |
| `proxy.retry_attempts` | int | 3 | Retry count on transient network failures |

Additional detailed schema lives in `vibectl/security/config.py` docstrings.

---

## 4 CLI Usage Examples

```bash
# 1. Configure & immediately activate a profile (connection test enforced)
vibectl setup-proxy configure corp-llm \
  vibectl-server://llm.corp.com:443 \
  --jwt-path ~/.config/vibectl/corp.jwt \
  --enable-sanitization \
  --enable-audit-logging \
  --activate

# 2. Disable proxy entirely
vibectl setup-proxy disable

# 3. Temporary override for a single command
vibectl --proxy local-dev vibe "explain deployment"

# 4. Show last 20 audit events for current profile
vibectl audit show --tail 20
```

---

## 5 Developer Notes

| Concern | Implementation |
|---------|----------------|
| **Sanitization** | `vibectl/security/sanitizer.py` – `RequestSanitizer` (100 % tests) |
| **Audit Logging** | `vibectl/security/audit.py` – `AuditLogger` (99 % tests) |
| **Config Schema** | `vibectl/security/config.py` & `vibectl/config.py` |
| **Proxy Adapter** | `vibectl/proxy_model_adapter.py` integrates sanitizer & logger |
| **CLI Surface** | `vibectl/subcommands/setup_proxy_cmd.py`, `vibectl/cli.py` |

### Extensibility Hooks

* **Custom secret detectors** – subclass `SanitizerPlugin` (upcoming plugin system).
* **Alternate log sinks** – point `AuditLogger` at a FIFO or GELF socket.
* **Risk policies** – extend `is_destructive_kubectl_command` heuristics.

---

## 6 Roadmap & Future Work

The following items are *not* in V1 and remain tracked in **`PLANNED_CHANGES.md`**:

1. **Advanced pattern detection** – cloud provider keys, custom regexes
2. **Security profiles & paranoia levels** – easy preset switching
3. **Plugin system** – user-defined sanitizers & validators
4. **Response analysis** – deeper semantic validation of LLM output
5. **Metrics & monitoring** – Prometheus / OpenTelemetry export
6. **Integrity & anti-tampering** – request/response signing, mTLS fallback

---

*Last updated: 2025-06-20 (Commit: V1 client-side hardening)*
