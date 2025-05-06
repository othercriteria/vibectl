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

## Command Execution Safety & Confirmation
- **LLM-Assessed Danger:** Explore having the LLM planner assess if a planned command is potentially dangerous (beyond the current hardcoded list in `_needs_confirmation`). This could involve prompting the LLM for a safety rating or flag. Implement with strong guardrails and default to requiring confirmation if unsure.
- **Refine Confirmation UI:** Ensure the confirmation prompt clearly presents the command and its potential impact.

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

## Remaining kubectl Subcommands

Below is a prioritized list of remaining kubectl subcommands to be implemented in vibectl, with consideration for complexity and implementation requirements:

### High Priority

1. **apply** - Critical for declarative configuration management
   - Requires handling file input (YAML/JSON)
   - Needs special handling for stdin redirection with -f -
   - Implementation complexity: Medium-high
   - Considerations: Diff visualization between current and applied state

2. **patch** - Important for making specific changes to resources
   - Requires understanding JSON patch or strategic merge patch formats
   - Implementation complexity: Medium
   - Considerations: Validation of patch syntax, error handling

3. **edit** - Important for interactive resource modification
   - Requires launching an editor and capturing modified content
   - Implementation complexity: Medium-high
   - Considerations: Similar to custom instructions editor implementation

### Medium Priority

4. **diff** - Useful for showing differences before applying
   - Implementation complexity: Medium
   - Considerations: Rich display for diff output with color highlighting

5. **exec** - Execute commands in container
   - Implementation complexity: High
   - Considerations: Requires interactive terminal handling similar to port-forward
   - May require additional asyncio implementation

6. **cp** - Copy files to/from containers
   - Implementation complexity: Medium
   - Considerations: Progress reporting for large files

7. **top** - Resource usage statistics
   - Implementation complexity: Medium
   - Considerations: Could benefit from rich, updating display similar to port-forward

### Lower Priority

8. **explain** - Display documentation for resources
   - Implementation complexity: Low
   - Considerations: Enhanced formatting of output

9. **annotate** and **label** - Update metadata on resources
   - Implementation complexity: Low
   - Considerations: Simple wrappers around kubectl

10. **auth** - Authentication related commands
    - Implementation complexity: Medium
    - Considerations: Security and token handling

11. **cordon**, **uncordon**, **drain** - Node management
    - Implementation complexity: Low-Medium
    - Considerations: Safety checks before node maintenance

12. **api-resources** and **api-versions** - API information commands
    - Implementation complexity: Low
    - Considerations: Enhanced output formatting

### Implementation Considerations

Several of these commands will require substantial new behaviors or patterns:

1. **File Input Commands** (apply, replace)
   - Need a standard approach for handling file inputs
   - Consider supporting directory input with --recursive option
   - May require temporary file handling for generated content

2. **Interactive Commands** (edit, exec)
   - Require terminal manipulation and editor integration
   - Similar to existing patterns in custom instructions handling
   - May need PTY handling for exec

3. **Long-Running Commands** (top, exec, port-forward)
   - Should share the asyncio implementation approach developed for port-forward
   - Need consistent patterns for display updating
   - Proper handling of SIGINT and graceful termination
   - Consideration for background operation modes

4. **Rich Output Formatting**
   - Several commands (diff, explain, api-resources) would benefit from enhanced output formatting
   - Consider a standard approach for syntax highlighting and structured display

5. **Safety Considerations**
   - Particularly important for node management commands (drain, cordon)
   - Consider requiring confirmation for potentially destructive operations
   - Add "dry-run" capabilities with clear previews of changes

Implementation should prioritize commands that provide the most value to users while building reusable patterns that can accelerate development of subsequent commands.

## Ollama Model String Handling and Error Messaging
- Improve error handling in vibectl/model_adapter.py to distinguish between 'unknown model' and 'missing API key' errors. If llm.UnknownModelError is raised, surface a message suggesting to check llm models for available names/aliases, rather than defaulting to an API key error.
- Consider normalizing model names: if user sets ollama:<model>, try ollama:<model>:latest if the first fails.
- Add tests for these behaviors.

## Model Value Validation
- Revisit model value validation: consider stricter validation or a more robust alias/provider detection system.
- Document the current workaround: providerless model aliases (like 'tinyllama') are accepted for compatibility with llm-ollama, but this may change in the future.

## Output Truncation Future Enhancements
- **Refine Budget Truncation Heuristics:** Implement more sophisticated YAML budget allocation (e.g., prioritizing `status`, `spec`) and smarter, section-specific truncation methods (e.g., summarizing lists in `status.conditions`, `items`) instead of simple string truncation for over-budget sections.
- **Improve JSON Budgeting:** Apply a per-section budget approach (similar to the current YAML implementation) to JSON output for more balanced truncation, instead of relying solely on depth/list limits followed by string truncation.
- **Context-Aware Truncation:** Use the `vibe` command's intent (if available/passed) to dynamically prioritize sections during truncation, preserving information most relevant to the user's query.
- **User Configuration:** Add user configuration options (via `vibectl config`) for truncation parameters (e.g., depth, list length, log line counts, budget ratios, priority sections).

## Test Structure Cleanup
- Flattened `tests/coverage/` into `tests/` for now.
- Revisit test organization and structure comprehensively later.
  - Systematically move subcommand-specific CLI tests from `tests/` or `tests/test_cli*.py` into `tests/subcommands/test_<subcommand>_cmd.py` (e.g., `logs` tests moved).

## Prompt Templating
- Consider using a dedicated templating library (e.g., Jinja2) for prompt
  construction to avoid manual string formatting issues like brace escaping.

## Enhanced --watch Future Work

- **Richer Interaction:**
    - Investigate filtering live watch output.
    - Investigate saving live watch output stream to a local file.
    - Investigate pause/resume functionality for the *display* of watch output (ensure clear language differentiating from pausing the underlying operation).
- **`vibe` Integration:**
    - Investigate triggering `vibe` summary on-demand during an active watch session.
- **Custom Watch Logic:**
    - Explore using direct Kubernetes API watches (instead of polling `kubectl get`) for custom implementations like `delete --watch`.
- **Output Format:**
    - Investigate supporting alternative `--output` formats (e.g., JSON events) alongside `--watch` and integrate with the live display.
- **Verb Expansion:**
    - Evaluate adding enhanced `--watch` to other verbs like `apply`, `patch`, `cordon`, `uncordon`, `drain`, `top`.
    - Revisit adding enhanced `--watch` to `vibectl just` once the core feature is stable.
    - **Custom Watch Logic for Specific Commands (Moved from PLANNED_CHANGES.md):**
        - `delete --watch`: Implement custom watch logic (polling `kubectl get` for deletion) and pipe status updates to live display.
        - `create --watch`: Implement custom watch logic (polling `kubectl get` for readiness/status) and pipe status updates to live display.
        - `apply --watch`: Implement custom watch logic (polling `kubectl get` for readiness/status) and pipe status updates to live display.
        - `patch --watch`: Implement custom watch logic (polling `kubectl get` for readiness/status) and pipe status updates to live display.

## LLM Interaction and Mocking

- [ ] The current mocking for LLM interactions in `tests/test_cli_vibe.py` is complex due to the multiple layers of calls (`get_model_adapter` -> `adapter_instance.get_model` -> `model_instance.prompt` -> `response.text`). Simplify this if possible.
- [ ] Investigate if `LLMModelAdapter` instances (or the underlying model objects) can be passed into functions like `update_memory` to avoid them re-fetching the adapter/model via `get_model_adapter`. This would simplify mocking by reducing the number of patch points.

## Kubeconfig Handling
