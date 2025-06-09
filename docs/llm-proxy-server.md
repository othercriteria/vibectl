# LLM Proxy Server Documentation

## Overview

The LLM Proxy Server feature enables vibectl to act as a proxy for Large Language Model (LLM) requests, providing centralized authentication, request routing, and streaming capabilities. This feature allows multiple clients to connect to a single vibectl server instance that manages LLM interactions.

## Current Status

The proxy server is functional but still under active development. Core features
like JWT authentication and gRPC streaming are stable and have accompanying test
coverage. Some CLI commands described in this document (for example the
`vibectl-server config` helpers) remain TODO, so configuration is currently
performed by editing the YAML file directly or by using environment variables.
TLS is supported and can be enabled manually or via the ACME workflow described
below.  See `examples/manifests/vibectl-server/` for a complete example that
obtains certificates using a local ACME test server.

## Architecture

### Core Components

#### Server Components

- **LLM Proxy Server** (`vibectl/server/llm_proxy.py`): Main gRPC server handling LLM requests
- **JWT Authentication** (`vibectl/server/jwt_auth.py`): JWT token validation and authentication logic
- **JWT Interceptor** (`vibectl/server/jwt_interceptor.py`): gRPC authentication middleware
- **gRPC Server** (`vibectl/server/grpc_server.py`): Server infrastructure and lifecycle management
- **Server Main** (`vibectl/server/main.py`): Configuration management and entry point

#### Client Components

- **Proxy Model Adapter** (`vibectl/proxy_model_adapter.py`): Client-side adapter for proxy communication
- **Setup Commands** (`vibectl/subcommands/setup_proxy_cmd.py`): Configuration and setup utilities

#### Protocol Components

- **Protocol Buffers** (`vibectl/proto/llm_proxy_pb2.py`): Generated message definitions
- **gRPC Stubs** (`vibectl/proto/llm_proxy_pb2_grpc.py`): Generated service interfaces
- **Configuration Utils** (`vibectl/config_utils.py`): YAML config and environment variable support

### Communication Flow

1. **Client Request**: Client sends LLM request via gRPC to proxy server
2. **Authentication**: JWT token validated by server interceptor
3. **Version Compatibility**: Client and server versions checked for compatibility
4. **Model Resolution**: Server resolves model aliases to actual model names
5. **LLM Execution**: Server executes LLM request using configured model
6. **Streaming Response**: Server streams response back to client (real or simulated)
7. **Metrics Collection**: Request metrics logged for monitoring

## Version Compatibility

### Client-Server Version Checking

The proxy system includes automatic version compatibility checking to ensure clients and servers can communicate properly:

#### Server Information Response

The `GetServerInfo` endpoint returns comprehensive server details:

- **Server Name**: `vibectl-llm-proxy` (identifies the service type)
- **Server Version**: Package version (e.g., `0.9.1`)
- **Supported Models**: List of available models and their capabilities
- **Model Aliases**: Mapping of friendly names to full model identifiers
- **Server Limits**: Request size, concurrency, and timeout constraints

#### Version Compatibility Logic

- **Compatible Versions**: Same major version, compatible minor versions
- **Version Skew Detection**: Automatic detection of incompatible client/server combinations
- **Graceful Degradation**: Clear error messages when versions are incompatible
- **Upgrade Guidance**: Specific instructions for resolving version mismatches

```bash
# Example server info output showing proper separation of name and version
vibectl setup-proxy test
# ✓ Connection successful!
# Server Name:      vibectl-llm-proxy
# Version:          0.9.1
# Supported Models: gpt-4o, claude-3-5-sonnet-latest, ...
```

## Authentication System

### JWT Token-Based Authentication

The proxy server uses JWT (JSON Web Tokens) for secure authentication with flexible configuration options:

#### JWT Configuration Precedence

The server follows a consistent precedence pattern for JWT secret key configuration (same pattern used for API keys in the client):

1. **Environment Variable** (highest precedence): `VIBECTL_JWT_SECRET`
2. **Environment Key File**: `VIBECTL_JWT_SECRET_FILE` pointing to a file containing the secret
3. **Config Setting**: `jwt.secret_key` in server configuration file
4. **Config Key File**: `jwt.secret_key_file` pointing to a file containing the secret
5. **Generated Key** (lowest precedence): Automatically generated and saved to config file for reuse

Other JWT settings follow the same precedence pattern:

- Algorithm: `VIBECTL_JWT_ALGORITHM` → `jwt.algorithm` → `"HS256"`
- Issuer: `VIBECTL_JWT_ISSUER` → `jwt.issuer` → `"vibectl-server"`
- Expiration: `VIBECTL_JWT_EXPIRATION_DAYS` → `jwt.expiration_days` → `30`

#### JWT Configuration Examples

**Environment Variables** (recommended for containers/CI):

```bash
export VIBECTL_JWT_SECRET="your-secret-key-here"
export VIBECTL_JWT_ALGORITHM="HS256"
export VIBECTL_JWT_ISSUER="my-company-proxy"
export VIBECTL_JWT_EXPIRATION_DAYS="90"
```

**Environment Key File** (recommended for secure file-based secrets):

```bash
# Store secret in a file
echo "your-secret-key-here" > ~/.vibectl-jwt-secret
chmod 600 ~/.vibectl-jwt-secret
export VIBECTL_JWT_SECRET_FILE="~/.vibectl-jwt-secret"
```

**Server Configuration File** (recommended for persistent setups):

```yaml
# ~/.config/vibectl/server/config.yaml
server:
  host: "0.0.0.0"
  port: 50051
  require_auth: true
  log_level: "INFO"

jwt:
  secret_key: "your-secret-key-here"
  algorithm: "HS256"
  issuer: "my-company-proxy"
  expiration_days: 90
```

**Server Configuration with Key File**:

```yaml
# ~/.config/vibectl/server/config.yaml
jwt:
  secret_key_file: "~/.config/vibectl/server/jwt-secret"
  algorithm: "HS256"
  issuer: "my-company-proxy"
  expiration_days: 90
```

#### Token Generation

```bash
# Generate a new JWT token (server command interface)
vibectl-server generate-token <subject> --expires-in <duration> [--output <file>]

# Examples
vibectl-server generate-token my-client --expires-in 30d --output token.jwt

# Note: If no JWT secret was configured above, the first token generation
# will automatically create and save a secret key to your config file
```

#### Token Format

- **Structure**: `header.payload.signature` (standard JWT format)
- **Claims**: subject, expiration, issuer, unique JWT ID (jti)
- **Signature**: HMAC-SHA256 with server secret key

#### Security Properties

- **Confidentiality**: TLS encryption protects tokens in transit
- **Integrity**: JWT signature prevents token modification
- **Authenticity**: Server verifies token was issued by trusted source
- **Expiration**: Built-in token lifecycle management

### Configuration

#### Server Configuration

The server uses a single configuration file with comprehensive settings:

```yaml
# ~/.config/vibectl/server/config.yaml
server:
  host: "0.0.0.0"
  port: 50051
  require_auth: false
  log_level: "INFO"
  default_model: "anthropic/claude-3-7-sonnet-latest"
  max_workers: 10

jwt:
  secret_key: null  # Use environment or file-based configuration (recommended)
  secret_key_file: null  # Path to file containing the secret key
  algorithm: "HS256"
  issuer: "vibectl-server"
  expiration_days: 30
```

**Configuration Options**:

- `server.host`: Server bind address (default: 0.0.0.0)
- `server.port`: Server port (default: 50051)
- `server.require_auth`: Enable JWT authentication (default: false)
- `server.log_level`: Logging verbosity (default: INFO)
- `server.default_model`: Default LLM model when not specified by client
- `server.max_workers`: Maximum concurrent request handlers
- `jwt.secret_key`: Direct secret key value (not recommended for production)
- `jwt.secret_key_file`: Path to file containing the secret key (recommended)
- `jwt.algorithm`: JWT signing algorithm (default: HS256)
- `jwt.issuer`: JWT issuer claim (default: vibectl-server)
- `jwt.expiration_days`: Default token expiration in days (default: 30)

#### Client Configuration

```bash
# Configure proxy connection
vibectl setup-proxy configure vibectl-server://jwt-token@server.example.com:443
```

## Streaming Implementation

### Real Streaming Support

The server implements a three-tier streaming approach:

1. **Tier 1: Real Streaming**: Attempt live token streaming via response iteration
2. **Tier 2: Simulated Streaming**: Fallback to chunk-based simulation
3. **Tier 3: Complete Fallback**: Fresh prompt call if streaming fails

```python
# Real streaming implementation
try:
    for chunk in response:  # Live tokens as they arrive
        yield StreamChunk(request_id=request_id, text_chunk=chunk)
except TypeError:
    # Fallback to simulated streaming
    response_text = response.text()
    # Simulate streaming by chunking
```

### Streaming Detection

The server automatically detects whether the underlying LLM supports streaming:

- **Streaming Models**: Tokens appear progressively as generated
- **Non-Streaming Models**: Server logs fallback to simulated streaming
- **Error Cases**: Graceful fallback with complete error recovery

## URL Formats

### Supported Schemes

#### Insecure Connection (Development)

```
vibectl-server-insecure://localhost:50051
```

#### Secure Connection with JWT Authentication

```
vibectl-server://jwt-token@server.example.com:443
```

### URL Parsing

The proxy URL parser supports:

- Scheme detection (`vibectl-server://` vs `vibectl-server-insecure://`)
- JWT token extraction from URL username
- Host and port resolution
- TLS configuration based on scheme

## Model Alias Resolution

### Alias Mapping

The proxy server supports friendly model aliases:

- `claude-4-sonnet` → `anthropic/claude-sonnet-4-0`
- `gpt-4` → `openai/gpt-4`
- `gpt-3.5-turbo` → `openai/gpt-3.5-turbo`

### Resolution Process

1. Client specifies model alias (e.g., `claude-4-sonnet`)
2. Proxy adapter resolves alias to full model name
3. Server uses resolved name for LLM execution
4. Fallback to original name if no alias found

## Error Handling

### Authentication Errors

- Invalid JWT format: Specific validation error with format guidance
- Expired tokens: Clear expiration message with renewal instructions
- Missing authentication: Guidance to generate tokens

### Connection Errors

- Invalid URL format: Examples of correct formats
- Server unreachable: Network troubleshooting guidance
- TLS certificate issues: Certificate validation guidance

### LLM Errors

- Model not found: Available models list and alias suggestions
- Rate limiting: Retry guidance and rate limit information
- Streaming failures: Automatic fallback with error logging

## Usage Examples

### Basic Setup

```bash
# 1. Initialize server configuration
vibectl-server init-config

# 2. Configure JWT secret (choose one method)
# Method A: Environment variable (recommended for development)
export VIBECTL_JWT_SECRET="your-secret-key"

# Method B: Environment key file (recommended for production)
echo "your-secret-key" > ~/.vibectl-jwt-secret
chmod 600 ~/.vibectl-jwt-secret
export VIBECTL_JWT_SECRET_FILE="~/.vibectl-jwt-secret"

# Method C: Config file setting (TODO: implement config commands)
# vibectl-server config set jwt.secret_key "your-secret-key"

# Method D: Config key file (TODO: implement config commands)
# echo "your-secret-key" > ~/.config/vibectl/server/jwt-secret
# chmod 600 ~/.config/vibectl/server/jwt-secret
# vibectl-server config set jwt.secret_key_file "~/.config/vibectl/server/jwt-secret"

# 3. Enable authentication and start server
vibectl-server config set server.require_auth true
vibectl-server serve

# 4. Generate client token
vibectl-server generate-token my-client --expires-in 30d --output token.jwt

# Note: If no JWT secret was configured above, the first token generation
# will automatically create and save a secret key to your config file

# 5. Configure client proxy
vibectl setup-proxy configure vibectl-server-insecure://$(cat token.jwt)@localhost:50051

# 6. Use proxy for LLM requests
vibectl vibe "explain kubernetes pods"
```

### Production Deployment

```bash
# Server setup with persistent configuration
vibectl-server init-config

# Store JWT secret securely
echo "production-secret-key-$(openssl rand -hex 32)" > /etc/vibectl/jwt-secret
chmod 600 /etc/vibectl/jwt-secret
chown vibectl:vibectl /etc/vibectl/jwt-secret

# Configure server for production
vibectl-server config set server.host "0.0.0.0"
vibectl-server config set server.port 443
vibectl-server config set server.require_auth true
vibectl-server config set server.log_level "INFO"
vibectl-server config set jwt.secret_key_file "/etc/vibectl/jwt-secret"
vibectl-server config set jwt.issuer "company-llm-proxy"
vibectl-server config set jwt.expiration_days 90

# Start server
vibectl-server serve

# Client setup with secure connection
vibectl setup-proxy configure vibectl-server://production-token@llm-proxy.company.com:443
```

### ACME / Let's Encrypt Certificate Workflow

The repository includes Kubernetes manifests under
`examples/manifests/vibectl-server/` (see the `README.md` in that directory)
demonstrating how to obtain a trusted certificate using a local ACME server.
The workflow mirrors a real Let's&nbsp;Encrypt flow but runs entirely inside the
cluster so it can be tested without Internet access.

1. Deploy the ACME test infrastructure:

   ```bash
   kubectl apply -f examples/manifests/vibectl-server/pebble.yaml
   kubectl apply -f examples/manifests/vibectl-server/cluster-issuer.yaml
   ```

   The `pebble.yaml` file starts a lightweight ACME test server and the
   `cluster-issuer.yaml` configures cert-manager to use it.

2. Deploy the server manifests which reference the `ClusterIssuer` created in
   the previous step.  This manifest defines a `Certificate` that cert-manager
   will reconcile automatically:

   ```bash
   kubectl apply -f examples/manifests/vibectl-server/deployment-tls.yaml
   kubectl wait --for=condition=available deployment/vibectl-server
   ```

3. Wait for cert-manager to perform the HTTP-01 challenge against the Pebble
   server and issue the certificate.  You can check progress with:

   ```bash
   kubectl describe certificate vibectl-server-cert -n vibectl-demo
   kubectl get secrets -n vibectl-demo vibectl-server-tls
   ```

   Once the secret exists, the deployment will mount it so the gRPC server can
   start with TLS enabled automatically.

4. Verify the certificate and server by running:

   ```bash
   openssl s_client -connect vibectl-server.vibectl-demo.svc.cluster.local:443
   ```

   or point the proxy client at the service URL.  Successful TLS negotiation
   confirms the ACME workflow completed correctly.

These manifests act as a complete end‑to‑end test of certificate generation and
renewal. They are intentionally self‑contained so you can reproduce the process
on any local cluster.

### Container/Docker Deployment

```bash
# Using environment variables for container deployment
docker run -d \
  -e VIBECTL_JWT_SECRET="container-secret-key" \
  -e VIBECTL_JWT_ISSUER="docker-proxy" \
  -e VIBECTL_JWT_EXPIRATION_DAYS="60" \
  -p 50051:50051 \
  vibectl-server --require-auth

# Using mounted secret file
echo "docker-secret-key" > /host/secrets/jwt-secret
docker run -d \
  -e VIBECTL_JWT_SECRET_FILE="/secrets/jwt-secret" \
  -v /host/secrets:/secrets:ro \
  -p 50051:50051 \
  vibectl-server --require-auth
```

### Development Testing

```bash
# Option 1: Simple development setup (no authentication)
vibectl-server serve
# In another terminal:
vibectl setup-proxy configure vibectl-server-insecure://localhost:50051
vibectl vibe "test the proxy connection"

# Option 2: Development with authentication (for testing auth features)
export VIBECTL_JWT_SECRET="dev-secret-key"
vibectl-server config set server.require_auth true
vibectl-server serve --log-level DEBUG
# In another terminal:
vibectl-server generate-token dev-client --output /tmp/dev-token.jwt
vibectl setup-proxy configure vibectl-server-insecure://$(cat /tmp/dev-token.jwt)@localhost:50051
vibectl vibe "test authenticated proxy connection"
```

## Monitoring and Metrics

### Server Metrics

- Request count and duration
- Authentication success/failure rates
- Streaming vs non-streaming requests
- Error rates by category

### Logging

- Authentication events for audit trails
- Streaming mode detection and fallbacks
- Error details for troubleshooting
- Performance metrics for optimization

## Security Considerations

### Best Practices

- Use TLS in production environments
- Rotate JWT secrets regularly
- Set appropriate token expiration times
- Monitor authentication failures
- Use least-privilege token subjects

### Threat Model

- **Man-in-the-Middle**: Mitigated by TLS encryption
- **Token Replay**: Mitigated by JWT expiration
- **Token Modification**: Mitigated by JWT signatures
- **Unauthorized Access**: Mitigated by authentication requirement

## Troubleshooting

### Common Issues

#### Authentication Failures

```
Error: JWT token validation failed
Solution: Check token format and expiration
```

#### Configuration Issues

```
Warning: No JWT secret key found in environment, config, or files
Solution: Configure secret using one of the supported methods:
  1. export VIBECTL_JWT_SECRET="your-key"
  2. export VIBECTL_JWT_SECRET_FILE="path/to/secret"
  3. Set jwt.secret_key in server config
  4. Set jwt.secret_key_file in server config

Note: If no key is configured, the system will automatically generate
and save one to your config file for future use.
```

#### Permission Issues with Key Files

```
Error: Failed to read JWT secret from file
Solution: Check file permissions and path:
  chmod 600 /path/to/secret-file
  chown your-user:your-group /path/to/secret-file
```

### Debug Mode

```bash
# Enable debug logging to see configuration precedence
vibectl-server --log-level DEBUG

# Check which JWT configuration method is being used
# Look for log messages like:
# "Using JWT secret from environment variable"
# "Loaded JWT secret from config key file: /path/to/file"
# "Using JWT secret from server configuration"

# TODO: Implement `vibectl-server config show` command
# Check current server configuration
vibectl-server config show

# TODO: Implement `vibectl-server config validate` command
# Validate server configuration
vibectl-server config validate

# Check client configuration
vibectl setup-proxy status

# Test specific server
vibectl setup-proxy test vibectl-server://token@server:443 --timeout 30
```

## Architecture References

For detailed technical architecture documentation, see:

- **[Server Components](../vibectl/server/STRUCTURE.md)**: Detailed server architecture and component documentation
- **[Main Project Structure](../STRUCTURE.md)**: Overall project organization including proxy components

## Future Enhancements

### Planned Features

- Server-side model alias configuration
- Enhanced metrics and monitoring (Prometheus/OpenTelemetry)
- Load balancing for multiple server instances
- Client certificate authentication
- Request caching and optimization
- Rate limiting and quota management

### Configuration Improvements

- Dynamic configuration reloading
- Enhanced environment variable support
- Configuration validation improvements
- Multi-tenant support

### Missing CLI Functionality (TODOs)

The following CLI commands are referenced in this documentation but not yet implemented:

#### Configuration Management Commands

```bash
# TODO: Implement these vibectl-server config subcommands:

# Show current configuration (with resolved values and precedence info)
vibectl-server config show [--section jwt|server] [--format yaml|json]

# Set configuration values
vibectl-server config set <key> <value>
vibectl-server config set jwt.secret_key "secret"
vibectl-server config set jwt.secret_key_file "/path/to/file"
vibectl-server config set server.port 50051

# Get configuration values
vibectl-server config get <key>
vibectl-server config get jwt.algorithm

# Validate configuration file and settings
vibectl-server config validate [--config-file path]

# Generate secure random secret keys
vibectl-server config generate-secret [--output-file path]

# Reset configuration to defaults
vibectl-server config reset [--section jwt|server]
```

#### Enhanced Debugging Commands

```bash
# TODO: Implement these debugging/status commands:

# Show detailed server status and configuration sources
vibectl-server status [--include-secrets]

# Test JWT configuration without starting server
vibectl-server test-jwt [--generate-token subject]

# Show configuration precedence and sources
vibectl-server config precedence
```

These commands would provide a complete CLI interface for server configuration management, making the server easier to deploy and maintain in production environments.
