# vibectl LLM Proxy Server

The optional *vibectl-server* lets multiple vibectl clients share a single set of LLM credentials through a high-performance gRPC proxy.  It supports **JWT authentication**, **TLS (private CA or ACME)**, **streaming responses**, and integrates cleanly with the vibectl CLI.

---
## 📑 Table of Contents
1. Quick-start (local development)
2. Production overview
3. Authentication
4. TLS certificate management
   1. Private CA workflow
   2. ACME / Let's Encrypt workflow
5. Demo scripts (Kubernetes)
6. Checking the server
7. Strict-Transport-Security (HSTS)
8. More information
9. Rate limiting & metrics

---
## 1  Quick Start – Local Development

```bash
# 1. Create a default configuration
vibectl-server init-config

# 2. Start the server with TLS (self-signed certs are generated on first run)
vibectl-server serve --tls

# 3. Generate a client token
vibectl-server generate-token dev-user --expires-in 30d --output dev.jwt

# 4. Point vibectl at the proxy
vibectl setup-proxy configure \
  vibectl-server://localhost:50051 \
  --jwt-path dev.jwt \
  --ca-bundle ~/.config/vibectl/server/certs/ca-bundle.crt

# 5. Use vibectl as normal
vibectl vibe "explain kubernetes pods"
```

Without the `--ca-bundle` flag the client will fail TLS verification and you
may be tempted to use the insecure scheme. Always provide the bundle when using
self‑signed certificates.

Self-signed certificates are stored under `~/.config/vibectl/server/certs/`.

---
## 2  Production Overview

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
  vibectl-server://llm-proxy.company.com:443 \
  --jwt-path ./client-token.jwt
```

---
## 3  Authentication

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

---
## 4  TLS Certificate Management

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
  vibectl-server://internal-server:443 \
  --jwt-path ./client-token.jwt \
  --ca-bundle /path/to/ca-bundle.crt
```

Client URLs determine whether TLS is used:

- `vibectl-server://host:port` → TLS
- `vibectl-server-insecure://host:port` → plain text

### ACME / Let's Encrypt Integration

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
- Certificate Transparency logging for enhanced security monitoring (implementation roadmap in `TODO-SERVER.md`)

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
  vibectl-server://vibectl.company.com:443 \
  --jwt-path ./client-token.jwt
```

**Certificate Lifecycle:**

- Initial provisioning: ~30 seconds for HTTP-01 validation
- Automatic renewal: 30 days before expiration
- Zero-downtime certificate updates via graceful reload
- Fallback to self-signed certificates if ACME fails

This approach provides the **security of private CAs** for internal deployments and the **convenience of public CAs** for internet-facing services.

---
## 5  Demo scripts (Kubernetes)

For comprehensive demonstration setups see the manifests under `examples/manifests/vibectl-server/`. **Three ready-to-run scripts are provided:**

| Script | What it shows | Notes |
|--------|---------------|-------|
| `demo-ca.sh` | Private-CA certificate workflow (no internet required) | Uses an init-container to generate a root CA and sign the server certificate. |
| `demo-acme.sh` | ACME via **TLS-ALPN-01** (port 443 only) | Pebble test CA by default; can be pointed at Let's Encrypt staging/production. |
| `demo-acme-http.sh` | ACME via **HTTP-01** (requires port 80 + LoadBalancer) | Automatically uses `nip.io` for dynamic DNS; needs MetalLB on kind/k3s. |

Each script builds the `vibectl-server:local` image, creates its own namespace, waits for certificates, prints connection info, and stores a demo JWT + CA bundle in `/tmp`.

---
## 6  Checking the server

Run `vibectl setup-proxy test` to confirm connectivity. The command prints the server version and available models.

Use `--log-level DEBUG` on the server for verbose output when troubleshooting.

---
## 7  Strict Transport Security (HSTS)

vibectl-server can emit the HTTP Strict Transport Security (HSTS) header to ensure that compliant clients always upgrade to HTTPS and prevent protocol-downgrade attacks.  The feature is enabled in all example manifests (CA, ACME TLS-ALPN-01, HTTP-01).

### Why enable HSTS?

• Forces browsers and HTTP/2 clients to use TLS for every future request after the first successful connection.
• Protects JWT tokens and gRPC traffic from accidental plain-text exposure.
• Mitigates SSL-strip and cookie-hijacking attacks.

### Configuration

Add an `hsts` subsection under `tls` in `config.yaml`:

```yaml
tls:
  enabled: true
  hsts:
    enabled: true          # Turn HSTS on/off
    max_age: 31536000      # Seconds – 1 year is typical
    include_subdomains: true  # Also protect *.example.com (optional)
    preload: false         # Only set true after submitting the domain to the preload list
```

With HSTS enabled, vibectl-server adds the header to all HTTP/2 (gRPC) and HTTP responses it serves:

```text
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

### Deployment tips

• **Test on a staging domain** before enabling `preload`. Preload entries are effectively permanent.
• Ensure certificates auto-renew reliably (ACME or CA mode) before enforcing long `max_age` values.
• In Kubernetes ingress setups you can let the ingress controller add HSTS, but keeping it in vibectl-server ensures consistent behaviour elsewhere.
• If you serve ACME HTTP-01 challenges on port 80, make sure the challenge handler **exempts** those paths from the HTTP-to-HTTPS redirect so certificate provisioning still works.

---
## 8  More information

• [docs/CONFIG.md](CONFIG.md) – full configuration reference.
• [vibectl/server/STRUCTURE.md](../vibectl/server/STRUCTURE.md) – detailed server architecture.
• Roadmap for advanced hardening (CT monitoring, mTLS, etc.) lives in [`TODO-SERVER.md`](../TODO-SERVER.md).

---
## 9  Rate limiting & metrics

vibectl-server now supports **server-side rate limiting** (RPM, concurrency, input size, and request timeout) and a built-in **Prometheus metrics** endpoint.

### Enabling rate limits

```yaml
server:
  limits:
    global:
      max_requests_per_minute: 120   # Optional – omit for unlimited
      max_concurrent_requests: 10    # Optional – omit for unlimited
      max_input_length: 32000        # Optional – characters
      request_timeout_seconds: 30    # Optional
    # Optional per-token overrides (by JWT `sub` or `kid`)
    per_token:
      "demo-user":
        max_requests_per_minute: 5
```

Hot-reload is supported – edit the config file and the server picks up changes automatically without restart.

### Metrics endpoint

Run the server with:

```bash
vibectl-server serve --enable-metrics --metrics-port 9095
```

This starts an HTTP endpoint at `http://<host>:9095/metrics` that exposes Prometheus counters such as:

* `vibectl_requests_total{sub="demo-user"}`
* `vibectl_rate_limited_total{sub="demo-user",limit_type="rpm"}`
* `vibectl_concurrent_in_flight{sub="demo-user"}`

Add a scrape config in Prometheus or add annotations in K8s manifests (see example deployments) to collect these metrics.

### Throttling behaviour

When a limit is exceeded the server returns `grpc.StatusCode.RESOURCE_EXHAUSTED` with metadata:

```
limit-type: rpm | concurrency | token
retry-after-ms: <milliseconds>
```

Clients can inspect these values to implement back-off logic.

For multi-instance or distributed deployments, see the **Rate Limiting & Quota Enforcement** section in [`TODO-SERVER.md`](../TODO-SERVER.md) for planned Redis backend and quota tracking.

---
## 10  Security Notes & Best Practices

The server's **default configuration is insecure**: it binds to `0.0.0.0` without TLS or authentication. For anything beyond isolated testing you should:

* Enable TLS (`--tls` or `server.use_tls: true`) and supply a CA bundle when using self-signed certificates.
* Require authentication (`server.require_auth: true`) and issue short-lived JWT tokens. Revocation tooling is still TODO.
* Bind only to `localhost` during development to avoid accidental exposure.
* Enable the HSTS header (`tls.hsts.enabled: true`) to guard against downgrade attacks.
* Restrict or firewall the Prometheus metrics port; it is HTTP-only and unauthenticated.
* Server-side TLS version is governed by gRPC defaults; enforcing a minimum version is planned.
