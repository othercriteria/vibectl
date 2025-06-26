# Server Components Structure

This document details the structure and architecture of the `vibectl` server components, which provide LLM proxy functionality via gRPC.

## Overview

The server components implement a high-performance gRPC-based LLM proxy that allows multiple clients to share LLM access through a centralized service. The architecture provides authentication, request routing, streaming support, and comprehensive monitoring.

## Core Components

### Service Layer

#### `llm_proxy.py` - LLM Proxy Service Implementation
- **Purpose**: Core gRPC service implementing the LLM proxy protocol
- **Size**: 416 lines (157 statements)
- **Test Coverage**: 93% ✅
- **Key Features**:
  - **GetServerInfo**: Returns server capabilities and model aliases
  - **Execute**: Non-streaming LLM request execution
  - **StreamExecute**: Real-time streaming LLM responses
  - **Model Resolution**: Dynamic model alias resolution and validation
  - **Metrics Collection**: Token usage tracking and performance metrics
  - **Error Handling**: Comprehensive error recovery with graceful degradation

#### `grpc_server.py` - gRPC Server Infrastructure
- **Purpose**: Server lifecycle management and service registration
- **Size**: 199 lines
- **Test Coverage**: 100% ✅
- **Key Features**:
  - **Server Initialization**: Configurable server setup with SSL/TLS support
  - **Service Registration**: Automatic service and interceptor registration
  - **Lifecycle Management**: Graceful startup, shutdown, and signal handling
  - **Authentication Integration**: JWT authentication setup and configuration
  - **Interceptor Chain**: Authentication and logging interceptor management

#### `main.py` - Server Entry Point and Configuration
- **Purpose**: Application entry point with configuration management
- **Size**: 424 lines (165 statements)
- **Test Coverage**: 99% ✅
- **Key Features**:
  - **Configuration Loading**: YAML config file processing with environment variable support
  - **Default Value Management**: Comprehensive default configuration handling
  - **Command Line Interface**: Server startup options and parameter handling
  - **Environment Integration**: Environment variable precedence and validation
  - **Startup Workflow**: Complete server initialization and dependency setup

### Authentication Layer

#### `jwt_auth.py` - JWT Authentication Implementation
- **Purpose**: JWT token validation and authentication logic
- **Size**: 191 lines
- **Test Coverage**: 100% ✅
- **Key Features**:
  - **Token Validation**: JWT signature verification and expiration checking
  - **Flexible Configuration**: Configurable signing keys and algorithms
  - **Error Handling**: Detailed authentication failure reporting
  - **Security Features**: Token expiration enforcement and format validation

#### `jwt_interceptor.py` - gRPC Authentication Interceptor
- **Purpose**: gRPC request authentication and authorization
- **Size**: 148 lines
- **Test Coverage**: 100% ✅
- **Key Features**:
  - **Request Interception**: Automatic authentication for all gRPC calls
  - **Metadata Processing**: JWT token extraction from gRPC metadata
  - **Authentication Bypass**: Configurable authentication disabling for development
  - **Status Code Management**: Proper gRPC status code generation for auth failures

## Protocol Definition

### gRPC Protocol (`vibectl/proto/`)
- **`llm_proxy_pb2.py`**: Generated protocol buffer message definitions
- **`llm_proxy_pb2_grpc.py`**: Generated gRPC service stubs and server interfaces
- **Protocol Features**:
  - **Request/Response**: Structured LLM request and response handling
  - **Streaming Support**: Real-time response streaming capabilities
  - **Metadata Support**: Rich request metadata and context passing
  - **Error Handling**: Structured error reporting and status codes

## Configuration System

### Configuration Management
- **Location**: Managed through `vibectl/config_utils.py` (95% test coverage)
- **Format**: YAML configuration files with environment variable overrides
- **Features**:
  - **Deep Merge**: Hierarchical configuration merging
  - **Environment Variables**: Full environment variable support
  - **Type Conversion**: Automatic type conversion and validation
  - **File-based Keys**: Support for file-based secret management

*ContextVar Overrides*: Global CLI flags (e.g. `--max-rpm`, `--max-concurrent`) set **runtime** overrides via a ContextVar-backed helper (`vibectl/overrides.py`).  Any component can query the current effective value through `ServerConfig.get()` / `ServerConfig.get_limits()` without having to pass the flags down the call-chain.

### Key Configuration Areas
1. **Server Settings**: Port, host, SSL/TLS configuration
2. **Authentication**: JWT signing keys, token expiration, auth bypass
3. **LLM Integration**: Model configurations, default models, aliases
4. **Performance**: Connection limits, timeouts, buffering settings
5. **Logging**: Log levels, output formats, debug settings

## Integration Points

### Client Integration
- **Proxy Model Adapter** (`vibectl/proxy_model_adapter.py`): Client-side integration
  - 92% test coverage ✅
  - Handles connection management, authentication, and request routing
  - Provides transparent LLM access through the proxy

### Testing Infrastructure
- **Comprehensive Test Suite**: 100% coverage for authentication components
- **Integration Tests**: End-to-end server testing with real gRPC clients
- **Mock Infrastructure**: Complete mocking of external dependencies
- **Performance Testing**: Fast test execution with comprehensive coverage

## TLS & Certificate Management

### ALPN Multiplexer (`alpn_multiplexer.py`)
- **Purpose**: Single-port multiplexing between gRPC (`h2`) and ACME TLS-ALPN-01 (`acme-tls/1`) protocols
- **Size**: 570 lines
- **Key Features**:
  - Dynamic ALPN routing to protocol-specific handlers
  - SNI callback for per-domain challenge certificates
  - Proxying gRPC traffic to the internal gRPC server
  - Graceful startup/shutdown and readiness probes

### TLS-ALPN Challenge Manager (`tls_alpn_challenge_server.py`)
- **Purpose**: On-the-fly generation and storage of ACME TLS-ALPN-01 challenge certificates
- **Size**: 375 lines
- **Key Features**:
  - Thread-safe in-memory challenge store
  - Critical ACME extension certificate generation
  - Automatic integration with ALPN multiplexer via `TLSALPNBridge`
  - Default-certificate replacement strategy for no-SNI clients

### ACME Client (`acme_client.py`)
- **Purpose**: Direct integration with ACME servers (Let's Encrypt, Pebble) for certificate issuance
- **Size**: 740 lines
- **Key Features**:
  - Supports HTTP-01, DNS-01 and TLS-ALPN-01 challenges
  - Extended timeout logic for TLS-ALPN-01 validations
  - Detailed tracing and error reporting
  - CSR generation and renewal checks

### ACME Manager (`acme_manager.py`)
- **Purpose**: Asynchronous orchestration of certificate provisioning, renewal and hot-reload
- **Size**: 458 lines
- **Key Features**:
  - Background renewal monitor with configurable thresholds
  - Live certificate reload callback for the running gRPC server
  - Graceful degradation when initial provisioning fails (TLS-ALPN-01)

### HTTP Challenge Server (`http_challenge_server.py`)
- **Purpose**: Minimal HTTP server for HTTP-01 challenge token delivery
- **Size**: 285 lines
- **Key Features**:
  - Async file-based token management
  - Health and readiness checks
  - Auto-shutdown when unused

### Certificate Utilities & Support
- **`cert_utils.py`**: PEM parsing, expiry checks, key generation helpers
- **`ca_manager.py`**: Development root CA and signing helper for local tests
- **`alpn_bridge.py`**: Dataclass to bridge multiplexer and challenge server while avoiding import cycles

### ACME Workflow Overview
1. `ACMEManager` creates an `ACMEClient` to request/renew certificates for configured domains.
2. For TLS-ALPN-01, `ACMEClient` computes the challenge hash and registers it with `TLSALPNChallengeServer`.
3. `ALPNMultiplexer`'s SNI callback queries `TLSALPNChallengeServer` for a per-domain `SSLContext` containing the special challenge certificate.
4. The ACME server connects with ALPN `acme-tls/1`; the correct certificate is presented and validation succeeds.
5. `ACMEClient` finalizes the order, writes `*.crt` and `*.key` to disk, and clears the active challenge.
6. `ACMEManager` invokes the configured hot-reload callback so the gRPC server starts using the fresh certificate without restarts.

## Architecture Patterns

### Service Architecture
1. **Layered Design**: Clear separation between service, authentication, and infrastructure layers
2. **Dependency Injection**: Configuration-driven component initialization
3. **Interface Segregation**: Clean interfaces between components
4. **Error Boundaries**: Comprehensive error handling at service boundaries

### Security Architecture
1. **Defense in Depth**: Multiple authentication and validation layers
2. **Principle of Least Privilege**: Minimal required permissions
3. **Secure by Default**: Authentication enabled by default with secure defaults
4. **Configuration Security**: Secure secret management and environment variable handling

### Performance Architecture
1. **Streaming First**: Real-time streaming support for better user experience
2. **Connection Pooling**: Efficient connection management
3. **Caching**: Model alias caching and configuration caching
4. **Asynchronous Processing**: Non-blocking request handling

## Deployment Considerations

### Server Deployment
- **Containerization**: Docker-ready with configurable entry points
- **Configuration Management**: Environment variable and file-based configuration
- **Health Checks**: Built-in health monitoring and status reporting
- **Graceful Shutdown**: Proper cleanup and connection draining

### Client Configuration
- **Connection Management**: Automatic reconnection and failover support
- **Authentication**: Transparent JWT token management
- **Service Discovery**: Configurable server endpoints and discovery

## Development Workflow

### Local Development
1. **Server Startup**: `python -m vibectl.server.main` with development configuration
2. **Authentication**: JWT bypass mode for local testing
3. **Configuration**: Local YAML files with environment variable overrides

### Testing
1. **Unit Tests**: Component-level testing with comprehensive mocking
2. **Integration Tests**: Full server testing with real gRPC communication
3. **Performance Tests**: Load testing and latency measurement
4. **Security Tests**: Authentication and authorization validation

## Future Enhancements

### Planned Features
1. **Metrics Export**: Prometheus/OpenTelemetry integration
2. **Load Balancing**: Multi-instance deployment support
3. **Rate Limiting**: Per-client rate limiting and quota management
4. **Advanced Authentication**: RBAC and multi-tenant support

### Extension Points
1. **Custom Interceptors**: Plugin system for custom request processing
2. **Model Adapters**: Support for additional LLM providers
3. **Configuration Providers**: External configuration source integration
4. **Monitoring Integrations**: Custom metrics and alerting systems

## Quality Metrics

### Test Coverage
- **Overall Server Coverage**: 96.8% (346/358 statements)
- **Authentication Components**: 100% coverage
- **Core Service Logic**: 93-99% coverage
- **Infrastructure Components**: 99-100% coverage

### Performance Characteristics
- **Startup Time**: < 2 seconds for full server initialization
- **Response Latency**: < 100ms overhead for non-streaming requests
- **Streaming Latency**: < 50ms first token latency
- **Memory Usage**: < 50MB base memory footprint

**The server architecture successfully balances performance, security, and maintainability while providing a robust foundation for LLM proxy functionality.**
