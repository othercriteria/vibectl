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

## Port-Forward Enhanced Functionality

Implement enhanced functionality for port-forward command in the future:

- Add a proxy layer between kubectl port-forward and local connections to:
  - Monitor and log all traffic passing through the forwarded connection
  - Classify traffic patterns for inclusion in vibe output
  - Detect and report connection issues or errors
  - Provide statistics on connection usage over time
  - Allow traffic manipulation or inspection on demand

- Add convenience options beyond standard kubectl:
  - Support for forwarding multiple ports in a single command
  - Automatic service discovery based on app labels
  - Automatic selection of available local ports
  - Integration with memory to remember commonly used forwards
  - Background mode with daemon capabilities

## Port-Forward Observability and Debugging

- Capture metrics during port-forward sessions:
  - Response times
  - Connection latency
  - Data transfer rates
  - Error patterns
  - Connection attempts

- Provide enhanced debugging for port-forwarding:
  - Connection lifecycle visualization
  - Protocol-aware traffic summaries
  - Detection of common issues (timeouts, connection resets)
  - Correlation with pod events and container status

- Integrate all captured information into the vibe output to provide context about:
  - Service performance characteristics
  - Potential issues detected
  - Usage patterns
  - Suggestions for troubleshooting or optimization

## Port-Forward Display Improvements
- Implement display of amount of data transferred in both directions
- Add visualization of current active connections
- Create visual indication of traffic activity in real-time

## Documentation and Examples
- Add comprehensive documentation and examples for port-forward and wait commands

## Future Rich Display Improvements for Wait Command
Consider implementing rich progress displays for the wait command in the future:
- Add animated waiting indicators with elapsed time tracking
- Show live status updates as resources are checked
- Integrate with logs to provide context during waiting
- Support multi-resource dependencies and detailed progress tracking
- Ensure proper unit testing strategy for complex terminal UI elements

## Future MCP Integration
While full [Model Context Protocol](https://github.com/modelcontextprotocol/python-sdk) implementation is out of scope currently, future work should:

1. Fully adopt MCP interface concepts (tools, resources, prompts)
2. Migrate existing adapter pattern to MCP compatibility layer
3. Leverage MCP's built-in key management features

## Technical Debt
- Add additional validation for key formats across all providers
- Implement comprehensive logging for key operations to aid debugging
- Consider adding support for additional model providers (e.g., Mistral, Gemini)

## LLM Error Handling and Transient Failures
- Transient LLM/model errors such as `overloaded_error` (e.g., service overloaded or temporarily unavailable) are now characterized in tests.
- Memory updates in these cases preserve the error type and message, so downstream logic and future model runs can distinguish between transient service issues and genuine model logic errors.
- Consider future improvements:
  - More user-friendly messaging or UI feedback for transient LLM errors
  - Retry logic or exponential backoff for overloaded errors
  - More nuanced memory/context handling to avoid penalizing the model for service-side issues

## Logging Improvements and Future Work
- All subcommands now use structured logging and error handling via the new logger and console_manager pattern.
- Update documentation (README, CLI help) to describe logging usage and configuration options.
- Ensure all error and exception paths consistently use logging (continue to review as code evolves).
- Consider additional shared logging utilities or patterns (e.g., context-aware log formatting, per-command loggers, file/JSON logging) for future extensibility.
- Plan for future extensibility: file logging, JSON logs, and advanced log configuration.

### Logging Test Pattern (reference)
When testing logging output in command handler or other modules:
- Use the `mock_command_handler_logger` fixture (from conftest.py) to patch and assert on log output.
- This ensures fast, reliable, and consistent logging assertions.
- For new modules, add a similar fixture to conftest.py and use it in tests.

Example usage:
```python
# In your test function signature:
def test_something(..., mock_command_handler_logger: Mock):
    ...
    # After running code
    assert any("expected log message" in str(call) for call in mock_command_handler_logger.info.call_args_list)
```
