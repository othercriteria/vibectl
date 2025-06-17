# Planned Changes for vibectl Proxy Security Hardening

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

## V1 Implementation (High Priority)

### 1. Named Proxy Configurations

**New concept**: Instead of single global proxy setting, support named proxy profiles with different security settings.

**Configuration structure**:
```yaml
# ~/.config/vibectl/proxy-configs.yaml
profiles:
  corporate-llm:
    url: vibectl-server://llm.corp.com:443
    jwt_path: ~/.config/vibectl/corp.jwt
    ca_bundle: ~/.config/vibectl/corp-ca.pem
    security:
      sanitize_requests: true
      audit_logging: true
      confirmation_mode: per-command

  public-demo:
    url: vibectl-server://demo.example.com:443
    jwt_path: ~/.config/vibectl/demo.jwt
    security:
      sanitize_requests: true
      confirmation_mode: per-command
      audit_logging: false  # Less sensitive

  local-dev:
    url: vibectl-server://localhost:50051
    jwt_path: ~/.config/vibectl/dev.jwt
    security:
      sanitize_requests: false  # Trust local server
      confirmation_mode: none
```

**CLI changes**:
```bash
# Setup named proxy
vibectl setup-proxy configure corporate-llm \
  vibectl-server://llm.corp.com:443 \
  --jwt-path corp.jwt \
  --enable-sanitization \
  --enable-audit-logging

# Use named proxy
vibectl --proxy corporate-llm vibe "show me all pods"

# List/manage proxy configs
vibectl setup-proxy list
vibectl setup-proxy remove corporate-llm
vibectl setup-proxy set-default corporate-llm
```

### 2. Request Sanitization (V1 Core Feature)

**Implementation location**: `vibectl/security/sanitizer.py`

**Kubernetes secrets detection patterns**:
- Base64 encoded data (with length/pattern heuristics)
- Bearer tokens (`Authorization: Bearer ...`)
- Kubernetes service account tokens
- kubectl config contexts and cluster info
- Certificate data (PEM format)
- Docker registry credentials

**Detection approach**:
```python
class RequestSanitizer:
    """Client-side request sanitization before proxy transmission."""

    def __init__(self, config: SecurityConfig):
        self.patterns = self._load_patterns(config)
        self.enabled = config.sanitize_requests

    def sanitize_request(self, request: str) -> tuple[str, list[DetectedSecret]]:
        """Sanitize request and return cleaned version + detected secrets."""

    def _detect_k8s_secrets(self, text: str) -> list[DetectedSecret]:
        """Detect Kubernetes-specific secret patterns."""

    def _detect_base64_secrets(self, text: str) -> list[DetectedSecret]:
        """Detect base64 patterns that might be secrets."""
```

**User interaction**:
```bash
$ vibectl vibe "debug the pod with token abc123def456..."
⚠️  WARNING: Potentially sensitive information detected:
   • Possible API token: "abc123def456..." (characters 34-48)

Continue sending request to proxy server? [y/N]: n
Request cancelled by user.
```

### 3. Audit Logging (V1 Core Feature)

**Implementation location**: `vibectl/security/audit.py`

**Log format** (structured JSON):
```json
{
  "timestamp": "2024-01-15T10:30:45Z",
  "proxy_profile": "corporate-llm",
  "request_id": "uuid-here",
  "event_type": "llm_request",
  "request_hash": "sha256-of-sanitized-request",
  "response_hash": "sha256-of-response",
  "secrets_detected": 2,
  "secrets_types": ["k8s-token", "base64-data"],
  "command_generated": "kubectl get pods -n production",
  "user_approved": true,
  "model_used": "claude-3-sonnet"
}
```

**Log location**: `~/.config/vibectl/audit.log` (configurable per proxy profile)

### 4. Basic Response Validation & Confirmation

**Per-command confirmation** (V1 approach):
```bash
$ vibectl vibe "delete all failed pods"
🤖 AI Response: I'll delete failed pods in the current namespace.

Generated command: kubectl delete pods --field-selector=status.phase=Failed
⚠️  This command will DELETE resources. Continue? [y/N]: y
Executing: kubectl delete pods --field-selector=status.phase=Failed
```

**Command risk assessment**:
- **Safe operations**: `get`, `describe`, `logs` (no confirmation needed with `--yes`)
- **Moderate operations**: `apply`, `patch`, `scale` (confirm once per session in semiauto)
- **Destructive operations**: `delete`, `drain` (always confirm unless `--yes`)

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
vibectl setup-proxy set-default <profile-name>

# Security options
vibectl --proxy <profile> --security-mode <mode> vibe "..."
vibectl audit show [--proxy <profile>] [--since <time>]
vibectl audit export [--format json|csv] [--output file]

# Testing/validation
vibectl setup-proxy test <profile-name>
vibectl security test-patterns [--input-file file]
```

## Implementation Plan

### Phase 1: Core Infrastructure
1. Create `vibectl/security/` module structure
2. Implement named proxy configuration system
3. Extend `setup-proxy` commands for named profiles
4. Basic configuration loading/validation

### Phase 2: Request Sanitization
1. Implement `RequestSanitizer` with K8s secret detection
2. Integration with `ProxyModelAdapter`
3. User interaction flows for detected secrets
4. Unit tests for pattern detection

### Phase 3: Audit Logging
1. Implement structured audit logging
2. Request/response hashing and storage
3. CLI commands for audit log viewing
4. Log rotation and cleanup

### Phase 4: Response Validation
1. Basic command parsing and risk assessment
2. Per-command confirmation flows
3. Integration with existing `--yes`/semiauto logic
4. Safe operation allowlisting

### Phase 5: Polish & Documentation
1. Comprehensive testing
2. Documentation updates
3. Example configurations
4. Security best practices guide

## Files to Create/Modify

### New Files
- `vibectl/security/__init__.py`
- `vibectl/security/sanitizer.py`
- `vibectl/security/audit.py`
- `vibectl/security/config.py`
- `vibectl/security/patterns.py`
- `tests/security/test_sanitizer.py`
- `tests/security/test_audit.py`
- `docs/security-hardening.md`

### Modified Files
- `vibectl/proxy_model_adapter.py` - Integration hooks
- `vibectl/config.py` - Named proxy configuration
- `vibectl/cli.py` - New `--proxy` flag
- `vibectl/subcommands/setup_proxy.py` - Named profile support
- `pyproject.toml` - New dependencies if needed

## Success Criteria

### V1 Success Metrics
- [ ] Named proxy configurations working
- [ ] K8s secret detection with >95% accuracy, <5% false positives
- [ ] Request sanitization integrated into proxy flow
- [ ] Audit logging capturing all proxy interactions
- [ ] Per-command confirmation for destructive operations
- [ ] Existing `--yes`/semiauto behavior preserved
- [ ] Comprehensive test coverage (>90%)
- [ ] Security documentation complete

### Future Success Metrics
- [ ] Plugin system for custom pattern detection
- [ ] Advanced security profiles implemented
- [ ] Response analysis and validation
- [ ] Integration with monitoring systems
- [ ] Zero false positives for common workflows
- [ ] Sub-100ms latency impact on request processing
