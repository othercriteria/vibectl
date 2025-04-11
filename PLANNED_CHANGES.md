# Planned Changes: Improved LLM Model Selection and Key Management

This branch aims to enhance how `vibectl` manages model selection and API key handling, addressing several issues identified in current usage. The goal is to provide a more robust, flexible, and user-friendly LLM integration system.

## Background

Currently, `vibectl` relies on the `llm` package for model access, which has several limitations:

1. Key management is isolated within the `llm` package, leading to conflicts with other tools using the same LLM APIs
2. Model selection is limited to a fixed set of options in config
3. Slow performance when accessing keys through the `llm` CLI
4. Lack of proper isolation between vibectl and other llm users
5. No direct support for key rotation and updates
6. Current "workable" solutions involve complex wrapper scripts with hacky workarounds

## Proposed Changes

### 1. Direct Model Integration

- Implement direct model API clients for key LLM providers
  - Anthropic (Claude models)
  - OpenAI (GPT models)
  - Local models via LM Studio integration
- Create model adapter interface for consistent interactions
- Keep `llm` package as a fallback for additional providers

### 2. Flexible Key Management

- Create dedicated `vibectl` key management system
  - Store keys in a dedicated config section
  - Support environment variables for CI/CD and containerized usage
  - Add key file support for secure deployment in production
- Implement secure key storage with proper permission handling
- Add key validation on startup to ensure API keys work

### 3. Model Configuration Improvements

- Extend model configuration options
  - Allow setting default model by provider or specific model
  - Define fallback order for models
  - Configure model parameters (temperature, max tokens)
- Support model-specific prompt templates
- Add prompt compression for large inputs

### 4. Performance Optimizations

- Cache model instances for faster reuse
- Optimize API key loading to avoid slow CLI calls
- Add support for asynchronous model calls for concurrent operations
- Implement efficient token counting without requiring API calls

### 5. Enhanced Error Handling

- Graceful handling of API rate limits and quotas
- Better error messages for authorization issues
- Automatic fallback to alternative models on failure
- Retry logic with backoff for transient errors

### 6. Integration Testing Framework

- Add integration test suite for model providers
- Mock responses for standard test cases
- Optional live API testing with test keys
- Coverage for all error conditions and edge cases

## Implementation Plan

1. Create model adapter interface with standardized methods
2. Implement direct clients for Anthropic and OpenAI
3. Develop key management system with multiple sources
4. Update configuration system to support new options
5. Integrate with existing command handler flow
6. Add comprehensive tests for new components
7. Update documentation and usage examples

## Technical Considerations

- Maintain backward compatibility with existing configs
- Keep Python 3.10+ support
- Follow existing type safety practices
- Ensure clean separation of concerns between API client, key management, and model selection
- Update integration tests to verify proper key handling

## Security Considerations

- Secure storage of API keys with proper file permissions
- No logging of key values
- Clear error messages without leaking sensitive information
- Safe handling of keys in environment variables
