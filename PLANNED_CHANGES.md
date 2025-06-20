# Planned Changes for vibectl Proxy Security Hardening

> **Heads-up 📝** – The full description of everything completed in **V1** has been migrated to **`docs/proxy-client-security.md`** (companion to `docs/llm-proxy-server.md`).
>
> This file now focuses on **ongoing work** and **future enhancements**.  Feel free to prune or rewrite sections marked ✅ as they are folded into formal documentation.

## Overview

Implement client-side security protections for vibectl when using proxy servers in "semi-trusted" environments. The threat model assumes the proxy operator has reasonable but not complete trust - they may be compromised now or in the future, TLS may be misconfigured, etc.

## Threat Model

**Semi-trusted proxy scenario**:

- Proxy operator is generally trustworthy but may be compromised
- Risk of credential/secret exfiltration through LLM requests
- Risk of malicious responses leading to destructive actions
- Risk of data collection over time building intelligence profile

**Attack vectors addressed**:

- Secrets leaked in natural language requests to LLM
- Malicious LLM responses containing destructive commands
- Gradual information gathering through request/response analysis
- Man-in-the-middle attacks on misconfigured TLS

## Architecture Overview

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   vibectl CLI   │    │  Proxy Server    │    │   LLM Provider  │
│                 │    │  (semi-trusted)  │    │                 │
│ ┌─────────────┐ │    │                  │    │                 │
│ │ Request     │ │───▶│                  │───▶│                 │
│ │ Sanitizer   │ │    │                  │    │                 │
│ └─────────────┘ │    │                  │    │                 │
│ ┌─────────────┐ │    │                  │    │                 │
│ │ Response    │ │◀───│                  │◀───│                 │
│ │ Validator   │ │    │                  │    │                 │
│ └─────────────┘ │    │                  │    │                 │
│ ┌─────────────┐ │    │                  │    │                 │
│ │ Audit Log   │ │    │                  │    │                 │
│ └─────────────┘ │    └──────────────────┘    └─────────────────┘
└─────────────────┘
```

## V1 Implementation Status
## Remaining V1 Tasks (pre-release)

- ✅ Core infrastructure, sanitization, audit logging, and confirmation flows are implemented and documented (see `docs/proxy-client-security.md`).
- 🚧 **Manual validation**
  * Configure a profile → activate → run a sample proxied `vibe` command.
  * Verify JWT loading, CA bundle resolution, request sanitization, and audit-log entry creation.
- 🧪 **Automated integration tests**
  * Implement high-level tests that spin up a stub proxy and exercise the full round-trip.
  * Wire these into the CI pipeline.

> When these tasks are complete we can tag **V1** and archive this section.

## Future Enhancements (Post-V1)

### 1. Advanced Pattern Detection

- Cloud provider credentials (AWS, GCP, Azure)
- Application-specific secrets (configurable regex patterns)
- Network topology information (IP ranges, hostnames)
- File system paths and sensitive directories

### 2. Security Profiles & Paranoia Levels

```yaml
security_profiles:
  minimal:
    sanitize_requests: false
    confirmation_mode: none

  standard:
    sanitize_requests: true
    confirmation_mode: per-session
    patterns: [k8s-secrets, common-tokens]

  paranoid:
    sanitize_requests: true
    confirmation_mode: per-command
    patterns: [all]
    response_size_limit: 10KB
    request_rate_limit: 10/minute
```

### 3. Plugin System Integration

```python
# Custom sanitizer plugins
class CompanySecretsPlugin(SanitizerPlugin):
    def detect_secrets(self, text: str) -> list[DetectedSecret]:
        # Company-specific secret patterns
        pass
```

### 4. Advanced Response Analysis

- Parse kubectl commands for resource scope analysis
- Detect unusual response patterns (potential data gathering)
- Validate response consistency with request intent

### 5. Enhanced Audit & Monitoring

- Structured metrics export (Prometheus/OpenTelemetry)
- Anomaly detection (unusual request patterns)
- Integration with SIEM systems
- Certificate transparency monitoring

### 6. Integrity & Anti-Tampering

- Request/response signing for integrity verification
- Fallback to direct LLM if proxy behaves suspiciously
- Client-side rate limiting and circuit breaker patterns

## Integration Points

### With Existing Systems

**Preserve current behavior**:

- `--yes` flag bypasses all confirmations (user explicitly trusts)
- `semiauto` mode behavior unchanged (user explicitly chose semi-autonomous)
- Direct LLM usage (non-proxy) unchanged

**Proxy adapter integration**:

- `ProxyModelAdapter` gains sanitization hooks
- Request/response pipeline gains audit logging
- Error handling for sanitization failures

**Configuration integration**:

- Extends existing `Config` system with security settings
- Integrates with current `setup-proxy` commands

### New CLI Surface

```bash
# Proxy management
vibectl setup-proxy configure <profile-name> <url> [options]
vibectl setup-proxy list
vibectl setup-proxy remove <profile-name>
vibectl setup-proxy set-active <profile-name>

# Security options
vibectl --proxy <profile> --security-mode <mode> vibe "..."
vibectl audit show [--proxy <profile>] [--since <time>]
vibectl audit export [--format json|csv] [--output file]
vibectl audit info [--proxy <profile>] [--paths-only] [--format json|table]

# Testing/validation
vibectl setup-proxy test <profile-name>
vibectl security test-patterns [--input-file file]
```

## Implementation Plan
*(obsolete section removed)*
