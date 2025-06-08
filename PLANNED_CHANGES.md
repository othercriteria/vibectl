# Planned Changes for feature/tls-proxy-support

## Status
**Phase 1 Complete ✅** - Production-grade TLS infrastructure with CA management and init container architecture is fully implemented and working.

End-to-end demo successfully demonstrates:
- Private CA generation and certificate management
- Init container architecture with zero host filesystem modifications
- Secure TLS connections with proper certificate verification
- JWT authentication and proxy configuration

## Remaining Work

### Phase 2: CLI Command Refactoring (Est. 4 hours)

#### Problem Statement
The current `vibectl-server serve` command has significant incidental complexity with 14+ CLI options that can conflict:
- `--tls/--no-tls` vs `--acme/--no-acme`
- `--cert-file`/`--key-file` vs `--generate-certs`
- ACME options when TLS is disabled
- CA certificates vs ACME certificates
- Multiple certificate generation strategies

This creates user confusion and potential configuration conflicts.

#### Proposed Solution: Specialized Commands
Break the monolithic `serve` command into focused subcommands:

1. **`vibectl-server serve-insecure`** - Plain HTTP, no TLS
   - Minimal options: `--host`, `--port`, `--model`, `--max-workers`, `--log-level`
   - Clear intent: development/internal networks only
   - No certificate-related options

2. **`vibectl-server serve-ca`** - TLS with Private CA
   - CA-focused options: `--ca-dir`, `--hostname`, `--san`
   - Automatic certificate generation from existing CA
   - Clear intent: internal/enterprise deployments

3. **`vibectl-server serve-acme`** - TLS with Let's Encrypt/ACME
   - ACME-focused options: `--email`, `--domain`, `--staging`
   - Automatic certificate provisioning and renewal
   - Clear intent: public internet deployments

4. **`vibectl-server serve-custom`** - Advanced/Custom TLS
   - All current options for expert users
   - Explicit certificate file paths
   - Manual certificate management

5. **`vibectl-server serve`** - Intelligent Routing (Default)
   - Analyzes configuration and routes to appropriate specialized command
   - Provides helpful error messages about conflicting options
   - Maintains backward compatibility

#### Benefits
- **Reduced Complexity**: Each command has 3-5 focused options instead of 14+
- **Clear Intent**: Command name indicates deployment scenario
- **Fewer Conflicts**: Options within each command are compatible
- **Better UX**: Users pick the command that matches their use case
- **Maintainability**: Easier to test and document each mode separately

#### Implementation Strategy
1. Extract shared server logic into `_create_and_start_server_common()`
2. Create specialized configuration builders for each mode
3. Implement focused CLI commands with relevant options
4. Add smart routing logic to main `serve` command
5. Update documentation with clear use case guidance

#### Detailed Command Specifications

**1. `vibectl-server serve-insecure`**
```bash
# Development/testing only - no TLS
vibectl-server serve-insecure [OPTIONS]

Options:
  --host TEXT              Host to bind to (default: 0.0.0.0)
  --port INTEGER          Port to bind to (default: 50051)
  --model TEXT            Default LLM model
  --max-workers INTEGER   Maximum worker threads (default: 10)
  --log-level LEVEL       Logging level (default: INFO)
  --require-auth          Enable JWT authentication
  --config PATH           Configuration file path
```

**2. `vibectl-server serve-ca`**
```bash
# TLS with private CA certificates
vibectl-server serve-ca [OPTIONS]

Options:
  --host TEXT              Host to bind to (default: 0.0.0.0)
  --port INTEGER          Port to bind to (default: 50051)
  --model TEXT            Default LLM model
  --max-workers INTEGER   Maximum worker threads (default: 10)
  --log-level LEVEL       Logging level (default: INFO)
  --require-auth          Enable JWT authentication
  --ca-dir PATH           CA directory (default: ~/.config/vibectl/server/ca)
  --hostname TEXT         Certificate hostname (default: localhost)
  --san TEXT              Subject Alternative Name (multiple allowed)
  --validity-days INTEGER Certificate validity (default: 90)
  --config PATH           Configuration file path
```

**3. `vibectl-server serve-acme`**
```bash
# TLS with Let's Encrypt/ACME certificates
vibectl-server serve-acme [OPTIONS]

Options:
  --host TEXT              Host to bind to (default: 0.0.0.0)
  --port INTEGER          Port to bind to (default: 443)
  --model TEXT            Default LLM model
  --max-workers INTEGER   Maximum worker threads (default: 10)
  --log-level LEVEL       Logging level (default: INFO)
  --require-auth          Enable JWT authentication
  --email TEXT            ACME account email (required)
  --domain TEXT           Certificate domain (multiple allowed, required)
  --staging               Use Let's Encrypt staging environment
  --challenge-type TEXT   Challenge type: http-01 or dns-01 (default: http-01)
  --config PATH           Configuration file path
```

**4. `vibectl-server serve-custom`**
```bash
# Advanced/custom TLS configuration
vibectl-server serve-custom [OPTIONS]

Options:
  --host TEXT              Host to bind to (default: 0.0.0.0)
  --port INTEGER          Port to bind to (default: 50051)
  --model TEXT            Default LLM model
  --max-workers INTEGER   Maximum worker threads (default: 10)
  --log-level LEVEL       Logging level (default: INFO)
  --require-auth          Enable JWT authentication
  --cert-file PATH        TLS certificate file path (required)
  --key-file PATH         TLS private key file path (required)
  --ca-bundle-file PATH   CA bundle for client verification
  --config PATH           Configuration file path
```

**5. `vibectl-server serve` (Smart Routing)**
```bash
# Intelligent routing based on configuration
vibectl-server serve [OPTIONS]

Options:
  --config PATH           Configuration file path

Behavior:
- Analyzes configuration to determine appropriate mode
- Routes to serve-insecure, serve-ca, serve-acme, or serve-custom
- Provides clear error messages for conflicting configurations
- Maintains full backward compatibility with existing deployments
```

#### Configuration-Based Routing Logic
```python
def determine_serve_mode(config: dict) -> str:
    """Determine which specialized serve command to use based on configuration."""
    tls_enabled = config.get("tls", {}).get("enabled", False)
    acme_enabled = config.get("acme", {}).get("enabled", False)

    if not tls_enabled:
        return "serve-insecure"
    elif acme_enabled:
        return "serve-acme"
    elif config.get("tls", {}).get("cert_file") and config.get("tls", {}).get("key_file"):
        return "serve-custom"
    else:
        # Default to CA mode for TLS without explicit cert files
        return "serve-ca"
```

#### Migration Path
1. **Phase 2.1**: Implement new specialized commands alongside existing `serve`
2. **Phase 2.2**: Add smart routing to main `serve` command
3. **Phase 2.3**: Update documentation and examples to use specialized commands
4. **Phase 2.4**: Deprecation notice for complex `serve` usage (future release)

#### Backward Compatibility
- Existing `vibectl-server serve` usage continues to work unchanged
- Configuration files remain compatible
- Gradual migration path for users
- Clear upgrade guidance in documentation

#### Implementation Example
```python
# Shared configuration and server logic
def _load_and_validate_config(config_path: Path | None, overrides: dict) -> dict:
    """Load configuration with CLI overrides and validation."""
    # Existing logic from current serve command
    pass

def _create_and_start_server_common(server_config: dict) -> Result:
    """Common server creation and startup logic for all serve commands."""
    # Existing logic from _create_and_start_server
    pass

# Specialized command implementations
@cli.command(name="serve-insecure")
@click.option("--host", default=None, help="Host to bind to")
@click.option("--port", type=int, default=None, help="Port to bind to")
@click.option("--model", default=None, help="Default LLM model")
@click.option("--max-workers", type=int, default=None, help="Maximum worker threads")
@click.option("--log-level", type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]), help="Logging level")
@click.option("--require-auth", is_flag=True, help="Enable JWT authentication")
@click.option("--config", type=click.Path(), help="Configuration file path")
def serve_insecure(host: str | None, port: int | None, model: str | None,
                  max_workers: int | None, log_level: str | None,
                  require_auth: bool, config: str | None) -> None:
    """Start insecure HTTP server (development only)."""

    # Build configuration overrides
    overrides = {
        "tls": {"enabled": False},  # Force TLS off
        "acme": {"enabled": False}  # Force ACME off
    }
    if host: overrides["server"] = overrides.get("server", {}); overrides["server"]["host"] = host
    if port: overrides["server"] = overrides.get("server", {}); overrides["server"]["port"] = port
    # ... other overrides

    config_path = Path(config) if config else None
    server_config = _load_and_validate_config(config_path, overrides)

    # Security warning for insecure mode
    console_manager.print_warning("⚠️  Running in INSECURE mode - no TLS encryption!")
    console_manager.print_note("This mode should only be used for development or internal networks")

    result = _create_and_start_server_common(server_config)
    handle_result(result)

@cli.command(name="serve-ca")
@click.option("--host", default=None, help="Host to bind to")
@click.option("--port", type=int, default=None, help="Port to bind to")
@click.option("--ca-dir", type=click.Path(), help="CA directory path")
@click.option("--hostname", default="localhost", help="Certificate hostname")
@click.option("--san", multiple=True, help="Subject Alternative Names")
@click.option("--validity-days", type=int, default=90, help="Certificate validity in days")
# ... other common options
def serve_ca(host: str | None, port: int | None, ca_dir: str | None,
            hostname: str, san: tuple[str, ...], validity_days: int, **kwargs) -> None:
    """Start server with private CA certificates."""

    # Ensure CA exists and create server certificate
    if ca_dir is None:
        config_dir = ensure_config_dir("server")
        ca_dir_path = config_dir / "ca"
    else:
        ca_dir_path = Path(ca_dir)

    if not ca_dir_path.exists():
        handle_result(Error(
            error=f"CA directory not found: {ca_dir_path}",
            recovery_suggestions="Initialize CA first with: vibectl-server ca init"
        ))
        return

    # Auto-create server certificate for the specified hostname
    try:
        ca_manager = CAManager(ca_dir_path)
        cert_path, key_path = ca_manager.create_server_certificate(
            hostname=hostname, san_list=list(san), validity_days=validity_days
        )

        overrides = {
            "tls": {
                "enabled": True,
                "cert_file": str(cert_path),
                "key_file": str(key_path)
            },
            "acme": {"enabled": False}
        }

        console_manager.print_success(f"✅ Using CA certificate for {hostname}")

    except Exception as e:
        handle_result(Error(error=f"Failed to create server certificate: {e}"))
        return

    config_path = Path(kwargs.get("config")) if kwargs.get("config") else None
    server_config = _load_and_validate_config(config_path, overrides)

    result = _create_and_start_server_common(server_config)
    handle_result(result)

# Smart routing serve command
@cli.command()
@click.option("--config", type=click.Path(), help="Configuration file path")
@click.pass_context
def serve(ctx: click.Context, config: str | None) -> None:
    """Start the gRPC server with intelligent routing."""

    # Load config to determine routing
    config_path = Path(config) if config else None
    config_result = load_server_config(config_path)

    if isinstance(config_result, Error):
        handle_result(config_result)
        return

    server_config = config_result.data
    mode = determine_serve_mode(server_config)

    console_manager.print_info(f"🔍 Detected configuration mode: {mode}")

    # Route to appropriate specialized command
    if mode == "serve-insecure":
        ctx.invoke(serve_insecure, config=config)
    elif mode == "serve-ca":
        ctx.invoke(serve_ca, config=config)
    elif mode == "serve-acme":
        ctx.invoke(serve_acme, config=config)
    elif mode == "serve-custom":
        ctx.invoke(serve_custom, config=config)
    else:
        handle_result(Error(error=f"Unknown serve mode: {mode}"))

### Phase 3: Let's Encrypt Integration (Est. 4 hours)

#### ACME Client Integration
- [ ] ACME client integration for automatic certificate provisioning
- [ ] DNS-01 and HTTP-01 challenge support
- [ ] Certificate renewal automation
- [ ] Support for other ACME-compatible CAs

### Phase 4: Production Integration & Documentation (Est. 8 hours)

#### cert-manager Integration Examples
- [ ] ClusterIssuer configuration for Let's Encrypt
- [ ] Certificate CRD for automatic certificate management
- [ ] Integration with ingress controllers
- [ ] Certificate monitoring and alerting

#### Security Hardening
- [ ] Modern TLS protocol support (TLS 1.2 minimum, TLS 1.3 preferred)
- [ ] Strong cipher suite configuration
- [ ] Certificate transparency monitoring
- [ ] HSTS header support

#### Production Deployment Guide
- [ ] Step-by-step production setup with cert-manager
- [ ] Public CA vs. private CA decision tree
- [ ] Security best practices and hardening guide
- [ ] Troubleshooting guide for certificate issues

#### Cloud Provider Examples
- [ ] AWS EKS with ALB and ACM certificates
- [ ] GKE with Google-managed certificates
- [ ] Azure AKS with Key Vault certificates
- [ ] On-premises deployment with private CA

## Implementation Priority

**Next Steps:**
1. **CLI Command Refactoring** - Simplify user experience and reduce complexity
2. **Let's Encrypt Integration** - Enable automatic public CA certificates
3. **Client Trust Store Management** - Support custom CA bundles
4. **cert-manager Examples** - Production Kubernetes patterns
5. **Complete Documentation** - Production deployment guides

## Success Criteria (Remaining)
- [ ] CLI commands are intuitive and focused on specific use cases
- [ ] Configuration conflicts are eliminated or clearly diagnosed
- [ ] Production deployments can use public CA certificates (Let's Encrypt)
- [ ] Private CA deployments work with custom trust stores
- [ ] Certificate renewal happens automatically without service interruption
- [ ] cert-manager integration provides seamless K8s certificate management
- [ ] Documentation covers all major deployment scenarios
- [ ] Security scanning shows no TLS vulnerabilities
- [ ] Performance impact is negligible (< 5% overhead)

## Current Architecture (Implemented)

The following foundational components are complete and working:

- **Private CA Infrastructure**: Root/Intermediate CA hierarchy with full lifecycle management
- **Init Container Architecture**: Kubernetes-native certificate generation with container isolation
- **TLS Integration**: Complete server and client TLS with proper certificate verification
- **CLI Management**: Full `vibectl-server ca` command suite for certificate operations
- **Test Coverage**: Comprehensive test suite with 34 CA tests + full TLS coverage
- **Demo Environment**: End-to-end working demo with proper TLS verification
## Security Audit Findings
- TLS and JWT-based authentication are implemented and generally follow best practices.
- The server generates self-signed certificates and a JWT secret if none are provided. Persist these secrets to avoid accidental rotation and invalidating existing tokens.
- Authentication uses HS256 tokens with no revocation mechanism. Consider supporting asymmetric signing (RS256/ES256) and token revocation/rotation policies.
- Clients embed tokens in the proxy URL which may leak via shell history or logs. Document secure handling and encourage environment variables or files.
- Insecure mode (`vibectl-server-insecure://`) should only be used for local testing. Add clear warnings in docs and CLI output.
- Ensure CA bundles are distributed out‑of‑band through a trusted channel so clients can verify the server certificate.
- Future hardening should enforce TLS 1.2+, strong cipher suites and optionally support mTLS for environments that require it.
- Operators can build trust by publishing CA fingerprints and demonstrating certificate status via `vibectl-server ca status` or `openssl verify` against the distributed bundle.
