# TODO - vibectl-server

Server-specific development tasks and enhancements for vibectl-server.

## Certificate Management & TLS

### Certificate Renewal Enhancement
- [ ] Implement certificate renewal background task (currently manual)
- [ ] Add renewal monitoring and alerting
- [ ] Zero-downtime certificate rotation
- [ ] Certificate expiry notifications
- [ ] Automatic certificate rollover testing

### Security Hardening
- [x] **Modern TLS protocol support** - TLS 1.3 enforced for gRPC, TLS 1.2+ for ACME compatibility
- [ ] Strong cipher suite configuration
- [ ] Certificate transparency monitoring
- [ ] HSTS header support
- [ ] Certificate pinning for client connections
- [ ] Mutual TLS (mTLS) support for enhanced security

#### Certificate Transparency Monitoring Details
Certificate Transparency (CT) monitoring acts as an early-warning system that watches public CT logs for certificates issued for any vibectl-controlled domains.

1. **Purpose**
   - Detect rogue or mis-issued certificates (typos, unauthorized wildcards, etc.)
   - Provide an auditable record of all public certificates
   - Meet compliance requirements that mandate CT monitoring

2. **Data Source**
   - Public CT logs such as Google Argon, Cloudflare Nimbus, Let's Encrypt Oak, Sectigo Sabre, etc.

3. **Workflow**
   1. Enumerate domain patterns (`*.example.com`, `*.svc.cluster.local`, etc.)
   2. Subscribe to a CT feed (e.g., `certstream`) or poll logs via API
   3. For each matching log entry:
      - Download the leaf certificate
      - Parse Subject, SANs, issuer, validity, SCTs
      - Classify as *expected* or *unexpected* based on an allow-list of issuers and SAN patterns
   4. Emit alerts (Slack / PagerDuty) for unexpected certificates

4. **MVP Implementation**
   - Lightweight Go or Python Deployment named **`ct-watcher`**
   - ConfigMap-driven allow-list (domains & issuers)
   - Export Prometheus metric `certificate_transparency_events{status="unexpected"}`
   - Alert rule: `unexpected > 0 for 5m`

5. **Hardening & Next Steps**
   - Merge CT alerts into central SIEM
   - Add playbook for incident response (revoke, rotate, preload HSTS)
   - Periodic job to verify SCTs are embedded in vibectl-served leaf certificates

### ACME Enhancements
- [ ] Switch from Pebble to production Let's Encrypt
- [ ] Support for DNS-01 challenge (in addition to TLS-ALPN-01)
- [ ] Multi-domain certificate support
- [ ] External Account Binding (EAB) support for restricted ACME CAs
- [ ] Rate limiting compliance and backoff strategies

## Production Deployment

### Cloud Provider Examples
- [ ] AWS EKS with ALB and ACM certificates
- [ ] GKE with Google-managed certificates
- [ ] Azure AKS with Key Vault certificates
- [ ] On-premises deployment with private CA
- [ ] Multi-cluster certificate distribution

### cert-manager Integration
- [ ] ClusterIssuer configuration for Let's Encrypt
- [ ] Certificate CRD for automatic certificate management
- [ ] Integration with ingress controllers
- [ ] Certificate monitoring and alerting
- [ ] Custom resource validation webhooks

### Production Documentation
- [ ] Step-by-step production setup with cert-manager
- [ ] Public CA vs. private CA decision tree
- [ ] Security best practices and hardening guide
- [ ] Troubleshooting guide for certificate issues
- [ ] Performance tuning and capacity planning
- [ ] Disaster recovery procedures

## CLI Enhancements

### Configuration Management
- [ ] `vibectl-server config show [--section <name>] [--format yaml|json]`
- [ ] `vibectl-server config set <key> <value>`
- [ ] `vibectl-server config get <key>`
- [ ] `vibectl-server config validate [--config-file path]`
- [ ] `vibectl-server config reset [--section <name>]`
- [ ] `vibectl-server config precedence`

### Security & Secrets Management
- [ ] `vibectl-server config generate-secret [--output-file path]`
- [ ] `vibectl-server test-jwt [--generate-token subject]`
- [ ] JWT token revocation and rotation commands
- [ ] CA key rotation commands
- [ ] Secret backup and restore commands

### Monitoring & Status
- [ ] `vibectl-server status [--include-secrets]`
- [ ] Certificate expiry status and warnings
- [ ] Connection health checks
- [ ] Performance metrics display
- [ ] Log level configuration commands

## Authentication & Authorization

### JWT Enhancements
- [ ] Support asymmetric signing (RS256/ES256) in addition to HS256
- [ ] Token revocation mechanism and blacklist management
- [ ] Token rotation policies and automated renewal
- [ ] Role-based access control (RBAC) for different server operations
- [ ] Integration with external identity providers (OIDC)

### Security Improvements
- [ ] Document secure token handling best practices
- [ ] Environment variable and file-based token configuration
- [ ] Token scoping and permission levels
- [ ] Audit logging for authentication events
- [ ] Rate limiting for authentication attempts

## Performance & Monitoring

### Metrics and Observability
- [ ] Prometheus metrics export
- [ ] Grafana dashboard templates
- [ ] Health check endpoints
- [ ] Performance profiling endpoints
- [ ] Request tracing and correlation IDs

### Performance Optimization
- [ ] Connection pooling and reuse
- [ ] Certificate caching strategies
- [ ] Load balancing and high availability
- [ ] Resource usage optimization
- [ ] Benchmarking and performance testing

## Rate Limiting & Quota Enforcement (Post-V1)

- [ ] Redis-backed `LimitBackend` for multi-instance deployments
- [ ] `QuotaInterceptor` for monthly token quotas using `ExecutionMetrics`
- [ ] Sliding-window / token-bucket RPM algorithm (optional operator toggle)
- [ ] Live limit configuration tooling (Kubernetes Operator / Helm helpers)
- [ ] CLI & API endpoints for real-time limit inspection
- [ ] Detailed Prometheus metrics for quota consumption
- [ ] Documentation & examples for distributed quota enforcement

## Error Handling & Reliability

### Resilience Features
- [ ] Circuit breaker patterns for external dependencies
- [ ] Graceful shutdown and signal handling
- [ ] Automatic restart and recovery mechanisms
- [ ] Backup and restore procedures
- [ ] Multi-region deployment support

### Logging and Debugging
- [ ] Structured logging with configurable levels
- [ ] Debug mode with enhanced verbosity
- [ ] Log rotation and retention policies
- [ ] Integration with log aggregation systems
- [ ] Error tracking and alerting

## Future Considerations

### Scalability
- [ ] Horizontal scaling support
- [ ] Database backend for certificate storage (beyond file system)
- [ ] Distributed certificate management
- [ ] Load testing and capacity planning
- [ ] Auto-scaling based on demand

### Integration
- [ ] Kubernetes Operator for automated deployment
- [ ] Helm chart for easy installation
- [ ] Integration with service mesh (Istio, Linkerd)
- [ ] Support for external certificate storage (Vault, Cloud KMS)
- [ ] Webhook support for certificate lifecycle events

### Model Context Protocol (MCP) Integration
- [ ] Fully adopt MCP interface concepts (tools, resources, prompts)
- [ ] Migrate existing adapter pattern to MCP compatibility layer
- [ ] Leverage MCP's built-in key management features
- [ ] Implement MCP server capabilities for vibectl-server
- [ ] Support MCP client connections for external tools

### Compliance & Governance
- [ ] Security scanning and vulnerability assessment
- [ ] Compliance reporting (SOC2, ISO 27001)
- [ ] Certificate lifecycle audit trails
- [ ] Policy engine integration
- [ ] Regulatory compliance features (FIPS, Common Criteria)

## Success Criteria

- [ ] cert-manager integration provides **seamless** Kubernetes certificate management
- [ ] Documentation covers **all** major deployment scenarios
- [ ] Security scanning shows **zero** TLS vulnerabilities
- [ ] Performance overhead remains **< 5 %** after TLS+proxy features
