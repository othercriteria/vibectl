# Planned Changes for LLM Proxy Server Feature

## Overview

Implement a client/server architecture that allows vibectl CLI instances to delegate LLM calls to a centralized vibectl server. This decouples clients from needing to manage model choice, provider authentication, and API key management.

## Motivation

- **Simplified client setup**: Users don't need to configure API keys or choose models
- **Centralized management**: Server handles model selection, rate limiting, cost control
- **Enterprise scenarios**: Central LLM proxy with usage controls and observability
- **Consistent behavior**: All clients use the same model configuration

## Architecture

### Client/Server Split

- **Client**: Delegates LLM calls to server, receives responses
- **Server**: Manages models, API keys, usage limits, and actual LLM execution
- **Protocol**: gRPC for strong typing, streaming support, and k8s ecosystem fit

### Configuration Structure

Move from flat config to structured approach:

```
~/.config/vibectl/
├── client/
│   ├── config.yaml          # client-specific config
│   └── server-secrets/      # server connection secrets
│       └── prod-server.key
└── server/
    ├── config.yaml          # server config (models, limits, etc.)
    └── client-secrets/      # issued client secrets
        ├── user1.key
        └── user2.key
```

### Model Adapter Architecture

Implement `ProxyModelAdapter` that:
- Implements existing `ModelAdapter` interface
- Forwards `execute()` and `execute_and_log_metrics()` calls to server via gRPC
- Maintains same error handling and metrics collection patterns
- Coexists with direct LLM usage (no fallback - explicit choice)

## Protocol Design

### gRPC Service Definition

```protobuf
service VibectlLLMProxy {
  rpc Execute(ExecuteRequest) returns (ExecuteResponse);
  rpc StreamExecute(ExecuteRequest) returns (stream StreamChunk);
  rpc GetServerInfo(GetServerInfoRequest) returns (GetServerInfoResponse);
}
```

### Key Message Types

- `ExecuteRequest`: system_fragments, user_fragments, model_name (optional), response_model_schema
- `ExecuteResponse`: success/error union with response_text, metrics, actual_model_used
- `GetServerInfoResponse`: available_models, default_model, server limits

### Authentication

- **Shared secrets** with expiration times (months/years for typical usage)
- **URL format**: `vibectl-server://secret@llm-server.company.com:443`
- **JWT tokens** for transparent secret passing
- **Out-of-band distribution** initially (copy-paste friendly)

## Implementation Plan

### Phase 1: Core Infrastructure

1. **gRPC Protocol Definition**
   - Define .proto files for service interface
   - Generate Python gRPC stubs
   - Add grpcio dependencies to pyproject.toml

2. **Configuration Refactoring**
   - Restructure config from flat to hierarchical
   - Implement client/server config separation
   - Maintain backward compatibility for existing configs

3. **ProxyModelAdapter Implementation**
   - Implement ModelAdapter interface for proxy calls
   - Handle gRPC client lifecycle and connection management
   - Error mapping from gRPC errors to existing error types

### Phase 2: Server Implementation

4. **Server Core**
   - gRPC server with ExecuteRequest handling
   - Integration with existing LLMModelAdapter for actual LLM calls
   - Secret validation and client authentication

5. **Client Management**
   - Secret generation and distribution mechanism
   - Client authentication and authorization
   - Basic rate limiting and usage tracking

### Phase 3: Client Integration

6. **Client Detection and Configuration**
   - Auto-detection of proxy vs direct mode based on config
   - `vibectl setup-proxy` command for connection setup
   - Validation and testing of proxy connections

7. **Model Selection Logic**
   - Decouple proxy and direct LLM model selection
   - Server-side model selection and client model requests
   - Clear precedence rules for model selection

### Phase 4: Advanced Features

8. **Streaming Support**
   - Implement StreamExecute for streaming responses
   - Maintain compatibility with existing streaming interfaces

9. **Server Features**
   - Multiple model support and routing
   - Advanced rate limiting and usage controls
   - Observability and metrics collection

10. **Setup and Tooling**
    - Enhanced setup commands for server deployment
    - Connection testing and diagnostic tools
    - Documentation and examples

## Files to be Created/Modified

### New Files
- `vibectl/proto/llm_proxy.proto` - gRPC service definition
- `vibectl/proto/llm_proxy_pb2.py` - Generated protobuf classes
- `vibectl/proto/llm_proxy_pb2_grpc.py` - Generated gRPC stubs
- `vibectl/proxy_model_adapter.py` - ProxyModelAdapter implementation
- `vibectl/server/` - Server implementation directory
- `vibectl/server/main.py` - Server entry point
- `vibectl/server/auth.py` - Authentication and secret management
- `vibectl/subcommands/setup_proxy.py` - Setup command implementation

### Modified Files
- `vibectl/config.py` - Restructure from flat to hierarchical config
- `vibectl/model_adapter.py` - Integration points for proxy adapter
- `vibectl/cli.py` - Add setup-proxy command
- `pyproject.toml` - Add gRPC dependencies
- `STRUCTURE.md` - Document new architecture

## Testing Strategy

- **Unit tests**: ProxyModelAdapter with mocked gRPC calls
- **Integration tests**: End-to-end client/server communication
- **Configuration tests**: Config migration and validation
- **Error handling tests**: Network failures, authentication errors
- **Performance tests**: Latency comparison with direct LLM calls

## Migration Strategy

- **Backward compatibility**: Existing direct LLM usage continues unchanged
- **Opt-in**: Proxy mode enabled only when explicitly configured
- **Gradual adoption**: Users can migrate individual commands/workflows
- **Clear errors**: Helpful messages when proxy is misconfigured

## Success Criteria

1. **Functional**: Client can successfully delegate LLM calls to server
2. **Transparent**: Same user experience as direct LLM calls
3. **Performant**: Minimal latency overhead from proxying
4. **Secure**: Proper authentication and secret management
5. **Maintainable**: Clean separation of concerns and testable code
6. **Documented**: Clear setup and usage documentation

## Open Questions

1. **Connection lifecycle**: Persistent connections vs per-request?
2. **Error retry logic**: How should transient network errors be handled?
3. **Server discovery**: Auto-discovery vs explicit configuration?
4. **Model caching**: Should server cache model instances?
5. **Metrics aggregation**: How to aggregate metrics across multiple clients?

## Dependencies

- `grpcio` and `grpcio-tools` for gRPC support
- Potential JWT library for token handling
- Configuration migration utilities
- Enhanced testing infrastructure for client/server scenarios
