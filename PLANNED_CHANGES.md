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

## V1 Implementation Status

### ✅ Phase 1: Core Infrastructure (COMPLETED with fixes)

**Named Proxy Configurations** - Successfully implemented with clean profile-only design.

**🎯 Key Plan Adjustment: Removed Legacy Compatibility**
- **Decision**: Removed legacy `proxy.enabled`, `proxy.server_url`, etc. fields entirely
- **Rationale**: Minimal deployed usage + preference for simplicity over complex migration
- **Result**: Clean profile-only system with no confusion or legacy baggage

**🐛 Bug Fixes Applied (Dec 2024)**:
- **Fixed ProxyModelAdapter JWT token resolution**: Updated to use new profile-based `get_effective_proxy_config()` instead of non-existent `get_jwt_token()` method
- **Fixed ProxyModelAdapter CA bundle resolution**: Updated to use profile-based config instead of non-existent `get_ca_bundle_path()` method
- **Enhanced configure command**: Added `--activate` flag with security validation (blocks activation with `--no-test`)

**✅ Implemented Configuration Structure**:
```yaml
proxy:
  # Active profile (None = proxy disabled, no legacy enabled field)
  active: "corporate-llm"

  # Global proxy defaults (can be overridden by individual profiles)
  timeout_seconds: 30
  retry_attempts: 3

  # Named profiles with individual settings
  profiles:
    corporate-llm:
      server_url: "vibectl-server://llm.corp.com:443"
      jwt_path: "~/.config/vibectl/corp.jwt"
      ca_bundle_path: "~/.config/vibectl/corp-ca.pem"
      timeout_seconds: 45  # Override global setting
      security:
        sanitize_requests: true
        audit_logging: true
        confirmation_mode: "per-command"

    public-demo:
      server_url: "vibectl-server://demo.example.com:443"
      jwt_path: "~/.config/vibectl/demo.jwt"
      security:
        sanitize_requests: true
        confirmation_mode: "per-command"
        audit_logging: false  # Less sensitive

    local-dev:
      server_url: "vibectl-server://localhost:50051"
      jwt_path: "~/.config/vibectl/dev.jwt"
      security:
        sanitize_requests: false  # Trust local server
        confirmation_mode: "none"
```

**✅ Completed CLI Implementation**:
```bash
# Setup named proxy (creates profile + activates it by default)
vibectl setup-proxy configure corporate-llm \
  vibectl-server://llm.corp.com:443 \
  --jwt-path corp.jwt \
  --enable-sanitization \
  --enable-audit-logging

# Setup profile without activating it
vibectl setup-proxy configure staging-llm \
  vibectl-server://staging.example.com:443 \
  --jwt-path staging.jwt \
  --no-activate

# Setup profile and explicitly activate (with connection test)
vibectl setup-proxy configure prod-llm \
  vibectl-server://prod.example.com:443 \
  --jwt-path prod.jwt \
  --activate  # Requires connection test (--no-test blocked for security)

# List all configured profiles
vibectl setup-proxy list

# Set active profile
vibectl setup-proxy set-active corporate-llm

# Remove profile
vibectl setup-proxy remove corporate-llm

# Disable proxy (set active to null)
vibectl setup-proxy disable

# Use specific proxy profile (temporary override - TODO: needs --proxy flag)
vibectl --proxy corporate-llm vibe "show me all pods"
```

**✅ Completed Infrastructure Components**:
- `vibectl/security/` module structure created
- `SecurityConfig` and `ProxyProfile` classes implemented
- Config class extended with proxy profile management methods
- Model adapter updated to use new profile system (no more legacy fallbacks)
- All setup-proxy commands updated to work with profiles

---

### ✅ Phase 2: Request Sanitization (COMPLETED)

**✅ Full Implementation Completed**: `vibectl/security/sanitizer.py`
**✅ Status**: Complete pattern detection logic implemented with comprehensive secret detection

**✅ Implemented Kubernetes secrets detection patterns**:
- ✅ Base64 encoded data (with length/pattern heuristics and entropy analysis)
- ✅ Bearer tokens (`Authorization: Bearer ...`)
- ✅ Kubernetes service account tokens (JWT pattern detection)
- ✅ API server URLs with embedded tokens
- ✅ Certificate data (PEM format detection)
- 📋 Docker registry credentials (TODO: future enhancement)

**✅ Completed Implementation**:
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

**✅ Completed Features**:
- ✅ Complete secret detection with confidence scoring
- ✅ Multiple detection methods (K8s patterns, base64 analysis, certificates)
- ✅ Entropy-based analysis for base64 secret likelihood
- ✅ Configurable sanitization through SecurityConfig
- ✅ Redaction with informative placeholders showing secret type and length
- 🚧 TODO: User interaction flow for detected secrets (integration pending)
- 🚧 TODO: Integration with ProxyModelAdapter for request sanitization

---

### 📋 Phase 3: Audit Logging (PLANNED)

**Target implementation location**: `vibectl/security/audit.py`

**Planned log format** (structured JSON):
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

**Planned log location**: `~/.config/vibectl/audit.log` (configurable per proxy profile)

---

### 📋 Phase 4: Basic Response Validation & Confirmation (PLANNED)

**Per-command confirmation** (V1 approach):
```bash
$ vibectl vibe "delete all failed pods"
🤖 AI Response: I'll delete failed pods in the current namespace.

Generated command: kubectl delete pods --field-selector=status.phase=Failed
⚠️  This command will DELETE resources. Continue? [y/N]: y
Executing: kubectl delete pods --field-selector=status.phase=Failed
```

**Planned command risk assessment**:
- **Safe operations**: `get`, `describe`, `logs` (no confirmation needed with `--yes`)
- **Moderate operations**: `apply`, `patch`, `scale` (confirm once per session in semiauto)
- **Destructive operations**: `delete`, `drain` (always confirm unless `--yes`)

---

## 🎯 Immediate Next Steps

### Priority 1: Validate Current Implementation
1. **✅ FIXED: Core infrastructure bugs**:
   - ✅ Fixed `setup-proxy list` error (get_jwt_token method missing)
   - ✅ Fixed ProxyModelAdapter JWT token resolution using profiles
   - ✅ Fixed ProxyModelAdapter CA bundle path resolution using profiles
   - ✅ Added `--activate` flag with security validation

2. **⚠️ NEEDS TESTING: End-to-end proxy functionality**:
   - Test that profile configuration works with actual vibe requests
   - Verify JWT token is correctly loaded from profile config
   - Confirm CA bundle path resolution works in real connections

### ✅ Priority 2: Request Sanitization (COMPLETED)
1. **✅ COMPLETED: Pattern detection in RequestSanitizer**:
   - ✅ Implemented robust K8s secret detection patterns
   - ✅ Added base64 validation with entropy analysis
   - ✅ Added comprehensive certificate detection
   - ✅ Added confidence scoring for detected secrets
   - 📋 TODO: Test against real kubectl outputs and configs

2. **🚧 TODO: Integrate sanitization into ProxyModelAdapter**:
   - Call sanitizer before sending requests to proxy
   - Handle detected secrets (user confirmation flow)
   - Pass sanitized requests to proxy server

3. **📋 TODO: Add `--proxy` flag support to main CLI**:
   - Allow temporary profile override: `vibectl --proxy profile-name vibe "..."`
   - Update argument parsing in main CLI entry point

### Priority 2: Basic Testing & Validation
1. **Create integration tests** for new proxy profile system
2. **Test end-to-end flow**: configure profile → activate → use with vibe command
3. **Validate security settings** are properly passed through the system

### Priority 3: Audit Logging Implementation (Phase 3)
1. **Create audit.py module** with structured logging
2. **Integrate with ProxyModelAdapter** to log requests/responses
3. **Add audit log viewing commands** (`vibectl audit show`, etc.)

---

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

# Testing/validation
vibectl setup-proxy test <profile-name>
vibectl security test-patterns [--input-file file]
```

## Implementation Plan

### ✅ Phase 1: Core Infrastructure (COMPLETED)
1. ✅ Create `vibectl/security/` module structure
2. ✅ Implement named proxy configuration system (clean profile-only design)
3. ✅ Extend `setup-proxy` commands for named profiles
4. ✅ Basic configuration loading/validation
5. ✅ Remove legacy proxy fields entirely

### 🚧 Phase 2: Request Sanitization (IN PROGRESS)
1. ⚠️ Implement `RequestSanitizer` with K8s secret detection (stub completed)
2. 🚧 Integration with `ProxyModelAdapter`
3. 🚧 User interaction flows for detected secrets
4. 📋 Unit tests for pattern detection

### 📋 Phase 3: Audit Logging (PLANNED)
1. 📋 Implement structured audit logging
2. 📋 Request/response hashing and storage
3. 📋 CLI commands for audit log viewing
4. 📋 Log rotation and cleanup

### 📋 Phase 4: Response Validation (PLANNED)
1. 📋 Basic command parsing and risk assessment
2. 📋 Per-command confirmation flows
3. 📋 Integration with existing `--yes`/semiauto logic
4. 📋 Safe operation allowlisting

### 📋 Phase 5: Polish & Documentation (PLANNED)
1. 📋 Comprehensive testing
2. 📋 Documentation updates
3. 📋 Example configurations
4. 📋 Security best practices guide

## Files Created/Modified Status

### ✅ New Files Created
- ✅ `vibectl/security/__init__.py` - Security module exports
- ✅ `vibectl/security/config.py` - SecurityConfig and ProxyProfile classes with full implementation
- ✅ `vibectl/security/sanitizer.py` - Complete RequestSanitizer implementation with pattern detection
- 📋 `vibectl/security/audit.py` - TODO: Audit logging implementation
- 📋 `tests/security/test_sanitizer.py` - TODO: Sanitizer tests
- 📋 `tests/security/test_audit.py` - TODO: Audit tests
- 📋 `docs/security-hardening.md` - TODO: Documentation

### ✅ Modified Files Completed
- ✅ `vibectl/config.py` - Complete proxy profile configuration system with profile management methods
- ✅ `vibectl/model_adapter.py` - Updated to use proxy profiles (legacy support completely removed)
- ✅ `vibectl/subcommands/setup_proxy_cmd.py` - Complete redesign with named profile management, security flags, and enhanced commands
- ✅ `vibectl/proxy_model_adapter.py` - Fixed JWT token and CA bundle resolution for profiles
- ✅ All test files - Updated to use new profile-based configuration system

### 🚧 Modified Files TODO
- 🚧 `vibectl/cli.py` - TODO: Add `--proxy` flag for temporary profile override
- 📋 `pyproject.toml` - TODO: New dependencies if needed for sanitization patterns

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
