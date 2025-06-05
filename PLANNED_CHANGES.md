# Planned Changes for feature/tls-proxy-support

## Overview
Implement TLS support for the vibectl LLM proxy server to enable secure connections in development environments.

## Analysis Summary
- **Current State**: Client-side TLS is fully implemented and working
- **Missing**: Server-side TLS binding (currently only uses `add_insecure_port()`)
- **Effort**: 1-2 days (Medium effort) - we're 80% done
- **Scope**: Development path only (self-signed certificates, automatic generation)

## Detailed Tasks

### 1. Server TLS Configuration (4-6 hours)
- [ ] Add TLS parameters to `GRPCServer.__init__()`
  - `use_tls: bool = False`
  - `cert_file: str | None = None` 
  - `key_file: str | None = None`
- [ ] Modify `GRPCServer.start()` method to use `add_secure_port()` when TLS enabled
- [ ] Implement certificate loading and gRPC SSL server credentials setup
- [ ] Add proper error handling for certificate loading issues

### 2. Configuration Management (2-3 hours)
- [ ] Extend server configuration schema to include TLS settings:
  ```yaml
  server:
    use_tls: true
    cert_file: "/path/to/server.crt"
    key_file: "/path/to/server.key"
  ```
- [ ] Update configuration loading in `main.py` and `jwt_auth.py`
- [ ] Add environment variable support for TLS configuration

### 3. Certificate Management (2-4 hours)
- [ ] Implement self-signed certificate generation for development
- [ ] Create certificate utility functions for:
  - Generating CA and server certificates
  - Writing certificates to appropriate locations
  - Validating certificate files exist and are readable
- [ ] Add certificate lifecycle management (auto-generation if missing)

### 4. CLI Integration (1-2 hours)
- [ ] Add TLS-related CLI options to `vibectl-server serve`:
  - `--tls / --no-tls`
  - `--cert-file PATH`
  - `--key-file PATH`
  - `--generate-certs` (for development)
- [ ] Update help text and documentation

### 5. Testing (2-3 hours)
- [ ] Unit tests for TLS configuration handling
- [ ] Integration tests with self-signed certificates
- [ ] Error handling tests (missing certs, invalid certs, etc.)
- [ ] Update existing server tests to cover both TLS and non-TLS scenarios

### 6. Documentation Updates (1 hour)
- [ ] Update `docs/llm-proxy-server.md` with TLS setup instructions
- [ ] Add development TLS workflow examples
- [ ] Document certificate generation process

## Implementation Strategy

### Phase 1: Core TLS Binding
1. Extend `GRPCServer` class with TLS parameters
2. Implement certificate loading logic
3. Add conditional `add_secure_port()` vs `add_insecure_port()` logic

### Phase 2: Certificate Generation
1. Create certificate utility module
2. Implement self-signed certificate generation
3. Add automatic certificate generation for development

### Phase 3: CLI and Configuration
1. Add CLI options for TLS configuration
2. Extend configuration file support
3. Add environment variable support

### Phase 4: Testing and Documentation
1. Comprehensive test coverage
2. Update documentation
3. Add usage examples

## Expected Outcomes

After implementation:
- `vibectl-server://` URLs will work with proper TLS
- Development workflow supports automatic certificate generation
- Secure proxy connections work end-to-end
- Clear error messages for certificate issues
- Seamless fallback to insecure mode when TLS disabled

## Success Criteria

- [ ] `vibectl-server serve --tls` starts server with TLS enabled
- [ ] Client can connect using `vibectl-server://token@localhost:50051`
- [ ] Self-signed certificates generated automatically for development
- [ ] All existing functionality continues to work with `--no-tls`
- [ ] Comprehensive test coverage for TLS scenarios
- [ ] Clear documentation and examples 