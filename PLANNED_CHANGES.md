# Planned Changes for feature/tls-proxy-support

(See `docs/llm-proxy-server.md` for additional context.)

## Status
**Phase 1 Complete ✅** - Production-grade TLS infrastructure with CA management and init container architecture is fully implemented and working.

**Phase 2 Complete ✅** - CLI command refactoring with proper enumeration and specialized subcommands is fully implemented.

**Phase 3 Complete ✅** - ACME client implementation with comprehensive testing, improved test coverage, and bug fixes is fully complete.

End-to-end demo successfully demonstrates:
- Private CA generation and certificate management
- Init container architecture with zero host filesystem modifications
- Secure TLS connections with proper certificate verification
- JWT authentication and proxy configuration
- Specialized CLI commands (serve-insecure, serve-ca, serve-acme, serve-custom) with intelligent routing
- Type-safe ServeMode enumeration replacing string-based mode handling
- **Comprehensive test coverage** for ACME client, certificate utilities, and server main functionality
- **CLI refactoring improvements** with DRY principle implementation for server options

## Remaining Work

### Phase 4: ACME Integration & Production Features (Est. 6 hours)

#### ACME Server Integration
- [ ] Integrate ACME client with `vibectl-server serve-acme` mode
- [ ] Add ACME certificate provisioning to server startup
- [ ] Implement certificate renewal background task
- [ ] Add ACME client configuration options (staging/production, email, challenge type)

#### Production Integration & Documentation (Est. 8 hours)

##### cert-manager Integration Examples
- [ ] ClusterIssuer configuration for Let's Encrypt
- [ ] Certificate CRD for automatic certificate management
- [ ] Integration with ingress controllers
- [ ] Certificate monitoring and alerting

##### Security Hardening
- [ ] Modern TLS protocol support (TLS 1.2 minimum, TLS 1.3 preferred)
- [ ] Strong cipher suite configuration
- [ ] Certificate transparency monitoring
- [ ] HSTS header support

##### Production Deployment Guide
- [ ] Step-by-step production setup with cert-manager
- [ ] Public CA vs. private CA decision tree
- [ ] Security best practices and hardening guide
- [ ] Troubleshooting guide for certificate issues

##### Cloud Provider Examples
- [ ] AWS EKS with ALB and ACM certificates
- [ ] GKE with Google-managed certificates
- [ ] Azure AKS with Key Vault certificates
- [ ] On-premises deployment with private CA

## Implementation Priority

**Next Steps:**
1. **ACME Server Integration** - Connect the ACME client to serve-acme mode
2. **Let's Encrypt Integration** - Enable automatic public CA certificates
3. **Client Trust Store Management** - Support custom CA bundles
4. **cert-manager Examples** - Production Kubernetes patterns
5. **Complete Documentation** - Production deployment guides

## Success Criteria (Remaining)
- [x] **CLI commands are intuitive and focused on specific use cases**
- [x] **ACME client is fully implemented with comprehensive tests**
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
- **Demo Environment**: End-to-end working demo with proper TLS verification
- **ACME Client**: Complete ACME protocol implementation

## ACME Client Implementation ✅ COMPLETE

### Implementation Summary
- **File**: `vibectl/server/acme_client.py` (162 statements, 437 lines)
- **Test Suite**: 37 comprehensive tests in `tests/test_acme_client.py`
- **Key Features**: Account registration, HTTP-01/DNS-01 challenges, certificate request/renewal

### ACME Functionality Implemented
- ✅ **Account Management**: Registration with ACME server, handles existing accounts
- ✅ **Challenge Support**: HTTP-01 (automated) and DNS-01 (manual) challenge types
- ✅ **Certificate Lifecycle**: Request, validation, issuance, and renewal checking
- ✅ **Error Handling**: Custom exceptions `ACMECertificateError` and `ACMEValidationError`
- ✅ **CSR Generation**: Certificate Signing Request creation for single/multiple domains
- ✅ **Certificate Management**: Expiry checking and renewal logic

### Test Coverage Details
- **Error scenarios**: ACME errors, validation failures, timeouts, file operations
- **Challenge validation**: Both HTTP-01 and DNS-01 challenge flows
- **Certificate management**: Expiry checking, renewal decisions
- **Edge cases**: Unsupported challenges, cleanup errors, authorization failures

### Integration Ready
The ACME client is ready for integration with the main server in `serve-acme` mode.

## Security Audit Findings
- TLS and JWT-based authentication are implemented and generally follow best practices.
- The server generates self-signed certificates and a JWT secret if none are provided. Persist these secrets to avoid accidental rotation and invalidating existing tokens.
- Authentication uses HS256 tokens with no revocation mechanism. Consider supporting asymmetric signing (RS256/ES256) and token revocation/rotation policies.
- Clients embed tokens in the proxy URL which may leak via shell history or logs. Document secure handling and encourage environment variables or files.
- Insecure mode (`vibectl-server-insecure://`) should only be used for local testing. Add clear warnings in docs and CLI output.
- Ensure CA bundles are distributed out‑of‑band through a trusted channel so clients can verify the server certificate.
- Future hardening should enforce TLS 1.2+, strong cipher suites and optionally support mTLS for environments that require it.
- Operators can build trust by publishing CA fingerprints and demonstrating certificate status via `vibectl-server ca status` or `openssl verify` against the distributed bundle.
