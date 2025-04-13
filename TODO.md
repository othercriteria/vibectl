# TODO: Remaining Model Key Management Work

## Model Selection Improvements
- Implement robust fallback logic for model selection when a preferred model is unavailable
- Add configurable model preference order for automatic fallback
- Create CLI command to test different models and measure performance

## Documentation Updates
- Add user documentation for the new key management features
- Document best practices for API key security
- Update configuration examples with new key management options
- Include migration guide for users coming from older versions

## Configuration System Improvements
- Fix config system to properly handle nested keys (e.g., `model_keys.anthropic`) in the `set` command
- Add validation and helpful error messages for nested config operations
- Ensure CLI experience matches documented interface in MODEL_KEYS.md
- Implement proper escaping for special characters in config values

## Performance Optimization
- Profile key loading performance in different environments
- Identify and optimize any remaining slow paths
- Add benchmarking tests for model loading times
- Implement metrics collection for model usage and performance

## Future MCP Integration
While full [Model Context Protocol](https://github.com/modelcontextprotocol/python-sdk) implementation is out of scope currently, future work should:

1. Fully adopt MCP interface concepts (tools, resources, prompts)
2. Migrate existing adapter pattern to MCP compatibility layer
3. Leverage MCP's built-in key management features

## Technical Debt
- Add additional validation for key formats across all providers
- Implement comprehensive logging for key operations to aid debugging
- Consider adding support for additional model providers (e.g., Mistral, Gemini)
