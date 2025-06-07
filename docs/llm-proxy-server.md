# vibectl LLM Proxy Server

The optional *vibectl-server* lets multiple vibectl clients share a single set of LLM credentials. It speaks gRPC and supports JWT authentication, TLS encryption and streaming responses.

Use it when you want a central service to handle LLM access for a team or to test vibectl in a controlled environment.

## Quick start (development)

```bash
# 1. Create a default configuration
vibectl-server init-config

# 2. Start the server with TLS (self-signed certs are generated on first run)
vibectl-server serve --tls

# 3. Generate a client token
vibectl-server generate-token dev-user --expires-in 30d --output dev.jwt

# 4. Point vibectl at the proxy
vibectl setup-proxy configure \
  vibectl-server://$(cat dev.jwt)@localhost:50051

# 5. Use vibectl as normal
vibectl vibe "explain kubernetes pods"
```

Self-signed certificates are stored under `~/.config/vibectl/server/certs/`.

## Production overview

Edit `~/.config/vibectl/server/config.yaml` and set:

```yaml
server:
  host: 0.0.0.0
  port: 443
  require_auth: true
  use_tls: true
  cert_file: /etc/ssl/certs/vibectl-server.crt
  key_file: /etc/ssl/private/vibectl-server.key
jwt:
  secret_key_file: /etc/vibectl/jwt-secret
  issuer: company-llm-proxy
  expiration_days: 90
```

Then run `vibectl-server serve`. Clients connect with a URL like:

```bash
vibectl setup-proxy configure \
  vibectl-server://TOKEN@llm-proxy.company.com:443
```

## Authentication

Authentication uses JWT tokens. The secret key is looked up in this order:

1. `VIBECTL_JWT_SECRET` environment variable
2. `VIBECTL_JWT_SECRET_FILE` pointing to a file
3. `jwt.secret_key` in the config file
4. `jwt.secret_key_file` in the config file
5. Auto-generated and saved to the config file

Create tokens with:

```bash
vibectl-server generate-token <subject> --expires-in <duration>
```

## TLS

Enable TLS with `--tls` or by setting `server.use_tls: true`. If `cert_file` and `key_file` are missing the server will generate self‑signed certificates. Use `vibectl-server generate-certs` to generate them manually.

Client URLs determine whether TLS is used:

- `vibectl-server://host:port` → TLS
- `vibectl-server-insecure://host:port` → plain text

## Let's Encrypt Integration (Planned)

For production deployments with public hostnames, vibectl-server will support automatic certificate provisioning via Let's Encrypt and other ACME-compatible certificate authorities.

### Why Let's Encrypt?

**Eliminates Certificate Management Overhead:**
- No manual certificate purchasing, renewal, or deployment
- Automatic 90-day renewal cycle prevents expiration outages
- Trusted by all major browsers and clients by default

**Production-Grade Security:**
- Industry-standard certificates with full browser trust
- Modern TLS protocols (TLS 1.2+) with strong cipher suites
- Certificate Transparency logging for enhanced security monitoring

**Cost-Effective:**
- Free certificates for public domains
- Reduces operational complexity compared to traditional CAs
- Integrates seamlessly with Kubernetes cert-manager

### Planned Workflow

Once implemented, automatic certificate provisioning will work like this:

```bash
# 1. Configure server for ACME with domain validation
vibectl-server init-config --acme-domain vibectl.company.com \
  --acme-email admin@company.com

# 2. Start server with automatic certificate provisioning
vibectl-server serve --acme

# 3. Server automatically:
#    - Requests certificates from Let's Encrypt
#    - Handles domain validation (HTTP-01 or DNS-01)
#    - Renews certificates before expiration
#    - Serves traffic with valid public certificates
```

**Kubernetes Integration:**
```yaml
# Automatic certificate management via cert-manager
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: vibectl-server-tls
spec:
  secretName: vibectl-server-tls
  issuerRef:
    name: letsencrypt-prod
    kind: ClusterIssuer
  dnsNames:
  - vibectl.company.com
```

**Client Configuration:**
```bash
# No custom CA bundle needed - uses system trust store
vibectl setup-proxy configure \
  vibectl-server://TOKEN@vibectl.company.com:443
```

**Certificate Lifecycle:**
- Initial provisioning: ~30 seconds for HTTP-01 validation
- Automatic renewal: 30 days before expiration
- Zero-downtime certificate updates via graceful reload
- Fallback to self-signed certificates if ACME fails

This approach provides the **security of private CAs** (from Phase 1) for internal deployments and the **convenience of public CAs** for internet-facing services.

## Kubernetes example

For a minimal single-replica deployment see the manifests under
`examples/manifests/vibectl-server/`.  They install a `Deployment`,
`Service`, `ConfigMap` and `Secret` suitable for local demos.  After
applying them you can generate a token from the running pod and point
`vibectl` at the exposed NodePort service.

## Checking the server

Run `vibectl setup-proxy test` to confirm connectivity. The command prints the server version and available models.

Use `--log-level DEBUG` on the server for verbose output when troubleshooting.

## More information

- [docs/CONFIG.md](CONFIG.md) lists all configuration options.
- [vibectl/server/STRUCTURE.md](../vibectl/server/STRUCTURE.md) describes the server architecture.
