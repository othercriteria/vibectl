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
  vibectl-server://$(cat dev.jwt)@localhost

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

## TLS Certificate Management

vibectl-server supports two primary approaches for TLS certificate management, each suited to different deployment scenarios:

### Certificate Management Approaches

| Feature | Private CA | ACME (Let's Encrypt) |
|---------|------------|----------------------|
| **Certificate Source** | Private Certificate Authority | ACME Server (Let's Encrypt/Pebble) |
| **Internet Dependency** | None | Required for real Let's Encrypt |
| **Trust Model** | Custom CA bundle | Public/ACME CA |
| **Renewal Process** | Manual regeneration | Automatic ACME renewal |
| **Complexity** | Lower | Higher (ACME protocol) |
| **Best For** | Internal/Private networks | Public internet deployments |
| **Domain Validation** | Not required | Required |
| **Certificate Expiry** | Long-lived (configurable) | Short-lived (90 days) |
| **Network Security** | Air-gap friendly | Internet dependent |
| **Production Ready** | Yes (internal) | Yes (public) |

### Private Certificate Authority

**Best for**: Internal networks, air-gapped environments, corporate PKI

Enable TLS with `--tls` or by setting `server.use_tls: true`. If `cert_file` and `key_file` are missing the server will generate self‑signed certificates. Use `vibectl-server generate-certs` to generate them manually.

**Use Cases:**
- Corporate environments with existing PKI infrastructure
- Air-gapped or restricted network environments  
- Internal services where you control certificate trust
- Development environments with full certificate control
- High-security environments requiring custom CA validation

**Client Configuration:**
```bash
# Requires custom CA bundle for certificate verification
vibectl setup-proxy configure \
  vibectl-server://TOKEN@internal-server:443 \
  --ca-bundle /path/to/ca-bundle.crt
```

Client URLs determine whether TLS is used:
- `vibectl-server://host:port` → TLS
- `vibectl-server-insecure://host:port` → plain text

## ACME / Let's Encrypt Integration

vibectl-server includes built in support for obtaining TLS certificates from Let's Encrypt or any other ACME compatible certificate authority. This is useful for public deployments where you want trusted certificates without manually managing them.

**Best for**: Internet-facing deployments, automatic certificate renewal

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

### ACME Use Cases

- Internet-facing services with public domain names
- Production deployments requiring automatic certificate renewal
- Services that need publicly trusted certificates
- Multi-domain certificate management
- Integration with Let's Encrypt or other ACME providers

### ACME Workflow

Automatic certificate provisioning works like this:

```bash
# 1. (Optional) Create a default configuration
vibectl-server init-config

# 2. Start the server in ACME mode
vibectl-server serve-acme \
  --email admin@company.com \
  --domain vibectl.company.com

# For local testing you can override the directory URL to use a Pebble instance:
# vibectl-server serve-acme \
#   --email admin@company.com \
#   --domain vibectl.test \
#   --directory-url http://pebble.pebble.svc.cluster.local:14000/dir \
#   --challenge-dir /tmp/acme-challenges

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

For local experiments there is also a `pebble.yaml` manifest in
`examples/manifests/vibectl-server/` which launches a Pebble ACME test server.
Point `--directory-url` at the Pebble service when running `serve-acme` to
exercise the full workflow end-to-end.

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

This approach provides the **security of private CAs** for internal deployments and the **convenience of public CAs** for internet-facing services.

## Kubernetes example

For comprehensive demonstration setups see the manifests under `examples/manifests/vibectl-server/`. They provide two complete scenarios:

### CA Management Demo
- Private Certificate Authority setup  
- Self-contained deployment for internal networks
- Complete certificate lifecycle management
- Run with: `./examples/manifests/vibectl-server/demo-ca.sh`

### ACME Management Demo  
- Pebble ACME test server integration
- Let's Encrypt-compatible certificate workflow
- Automatic domain validation and renewal
- Run with: `./examples/manifests/vibectl-server/demo-acme.sh`

Both demos install a `Deployment`, `Service`, `ConfigMap` and `Secret` suitable for local testing. The interactive demo selector at `./examples/manifests/vibectl-server/demo.sh` helps choose the appropriate approach for your use case.

## Checking the server

Run `vibectl setup-proxy test` to confirm connectivity. The command prints the server version and available models.

Use `--log-level DEBUG` on the server for verbose output when troubleshooting.

## More information

- [docs/CONFIG.md](CONFIG.md) lists all configuration options.
- [vibectl/server/STRUCTURE.md](../vibectl/server/STRUCTURE.md) describes the server architecture.
