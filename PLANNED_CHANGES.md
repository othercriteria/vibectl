# Planned Changes for feature/tls-proxy-support

(See `docs/llm-proxy-server.md` for additional context.)

## Status

**Core Implementation Complete ✅** - All TLS infrastructure, ACME protocol support, security hardening, and testing are implemented and working.

## Outstanding Work

### cert-manager Integration Examples (Est. 2-3 hours)

- [ ] ClusterIssuer configuration for Let's Encrypt
- [ ] Certificate CRD for automatic certificate management
- [ ] Integration with ingress controllers
- [ ] Certificate monitoring and alerting

### Production Documentation (Est. 2-3 hours)

- [ ] Step-by-step production setup with cert-manager
- [ ] Public CA vs. private CA decision tree
- [ ] Security best practices and hardening guide
- [ ] Troubleshooting guide for certificate issues

### Final Security Hardening (Est. 1-2 hours)

- [ ] Strong cipher suite configuration
- [ ] Certificate transparency monitoring

### Recently Completed (Security)

- [x] HSTS header support

## Success Criteria

- [ ] cert-manager integration provides seamless K8s certificate management
- [ ] Documentation covers all major deployment scenarios
- [ ] Security scanning shows no TLS vulnerabilities
- [ ] Performance impact is negligible (< 5% overhead)

*Additional server-specific enhancements moved to [TODO-SERVER.md](TODO-SERVER.md)*

## Recently Completed

- **Core TLS Infrastructure**: Private CA, certificate generation, TLS 1.3+ hardening
- **ACME Protocol**: Full client/server implementation with TLS-ALPN-01 and HTTP-01 challenges
- **Security Fixes**: Secure file permissions, debug log redaction, race condition resolution
- **CLI Integration**: Complete `vibectl-server ca` command suite and serve modes
- **Testing & Demos**: Comprehensive test coverage and demo scripts

## Notes

- JWT tokens use HS256 with no revocation mechanism - consider asymmetric signing for production
- CA bundles should be distributed through trusted channels for client verification
- Document secure token handling to prevent leakage in shell history/logs
