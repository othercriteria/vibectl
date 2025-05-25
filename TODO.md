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
- **Systematic LLM Call Instrumentation & Storage:**
  - Expand current LLM call instrumentation to explicitly log all relevant parameters (e.g., model options like temperature, full prompt/fragment details).
  - Implement a system for storing this detailed instrumentation data persistently (e.g., local SQLite DB, structured logs) to enable comprehensive analysis beyond real-time console output.
- **LLM Metrics Analysis & Visualization:**
  - Develop methods or tools to analyze the stored LLM call data to identify performance bottlenecks (high token/time cost), frequently/infrequently used prompts/fragments, and overall usage patterns.
  - Explore and define a strategy for visualizing these collected metrics to aid in optimization efforts.
- **(Future Consideration) Explicit LLM Caching Layers:**
  - If `llm` library's fragment-based caching proves insufficient after further investigation, explore the feasibility and benefits of implementing an explicit caching layer for LLM responses.

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

- **LLM-Assessed Danger:** For commands identified as non-read-only by `is_kubectl_command_read_only`, explore having the LLM planner further assess if a planned *write* command is potentially dangerous in the given context. This could involve prompting the LLM for a safety rating or specific warnings. Implement with strong guardrails and default to requiring confirmation if the LLM is unsure or flags a potential risk.
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

*No high priority commands remaining - edit command has been implemented.*

### Medium Priority

1. **debug** - Debug pods and containers
   - Implementation complexity: Medium-high
   - Considerations: Requires interactive terminal handling and container troubleshooting capabilities
   - May require custom debugging workflows and enhanced output formatting

1. **exec** - Execute commands in container
   - Implementation complexity: High
   - Considerations: Requires interactive terminal handling similar to port-forward
   - May require additional asyncio implementation

1. **cp** - Copy files to/from containers
   - Implementation complexity: Medium
   - Considerations: Progress reporting for large files

1. **top** - Resource usage statistics
   - Implementation complexity: Medium
   - Considerations: Could benefit from rich, updating display similar to port-forward

### Lower Priority

1. **explain** - Display documentation for resources
   - Implementation complexity: Low
   - Considerations: Enhanced formatting of output

1. **annotate** and **label** - Update metadata on resources
   - Implementation complexity: Low
   - Considerations: Simple wrappers around kubectl

1. **auth** - Authentication related commands
   - Implementation complexity: Medium
   - Considerations: Security and token handling

1. **cordon**, **uncordon**, **drain** - Node management
    - Implementation complexity: Low-Medium
    - Considerations: Safety checks before node maintenance

1. **api-resources** and **api-versions** - API information commands
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

## Apply Command Future Enhancements

- **Interactive Confirmation:** Option for users to review a diff and confirm changes before applying LLM-corrected or generated manifests.
- **Enhanced Kustomize Support:** Deeper integration with Kustomize, especially when manifests are being generated or modified as part of a kustomization.
- **Progress Visibility:** Show progress during file discovery and correction steps so large directories don't appear to hang.
- **Short-Circuit Valid Sets:** Skip LLM correction entirely if all selected manifests pass validation.
- **Audit Output:** Optionally save a combined summary of what was applied (including corrected files) for later review.
- **Show Corrections Diff:** Provide a diff of AI-corrected manifests against their originals so users can easily review changes.

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
- **Error Handling:**
  - Ensure clear display of errors from the underlying `kubectl` command or the custom watch/poll logic during the live session.

## LLM Interaction and Mocking

- [ ] The current mocking for LLM interactions in `tests/test_cli_vibe.py` is complex due to the multiple layers of calls (`get_model_adapter` -> `adapter_instance.get_model` -> `model_instance.prompt` -> `response.text`). Simplify this if possible.
- [ ] Investigate if `LLMModelAdapter` instances (or the underlying model objects) can be passed into functions like `update_memory` to avoid them re-fetching the adapter/model via `get_model_adapter`. This would simplify mocking by reducing the number of patch points.

## Kubeconfig Handling

## Auto and Semiauto Command Behavior Clarification

- **`vibectl auto`**: Designed for fully non-interactive execution. It implies `yes=True` for all internal command confirmations, regardless of the `--yes` flag passed to `vibectl auto` itself. The `--yes` flag on `vibectl auto` is primarily for future use if `auto` mode itself were to have its own direct interactive prompts (which it currently doesn't).
- **`vibectl semiauto`**: Designed for interactive execution where each step planned by the LLM is presented to the user for confirmation. It implies `yes=False` for internal command confirmations, requiring explicit user input (`y/n/a/b/m/e`).
- **Confirmation Logic**: The `_needs_confirmation` helper in `command_handler.py` determines if a command verb is dangerous. This, combined with the effective `yes` status (always `True` for full auto, always `False` for semiauto initial prompt) dictates whether `_handle_command_confirmation` shows a prompt or bypasses it.
- **Error Handling**: Both modes have mechanisms to continue or halt on errors, with `exit_on_error` controlling the loop's behavior. Non-halting errors allow the loop to proceed, often with recovery suggestions.

## `vibectl check` Future Enhancements

- **Comprehensive Integration Testing**: Develop a comprehensive suite of integration tests for `vibectl check` covering diverse predicates (simple true/false, multi-step, poorly posed, cannot determine outcomes) and verifying exit codes and explanations for semantic fidelity to the original predicate.
- **Semantic Drift Regression Testing**: Design and implement tests specifically to detect and prevent "semantic drift" regressions in `vibectl check`.
- **Schema Clarity**: Rename `CommandAction.commands` to `CommandAction.args` in `vibectl/schema.py` for better clarity.
- **Token Budget**: Implement a token budget for LLM interactions within the `vibectl check` loop to manage costs and prevent overly long interactions.
- **Ongoing Prompt Refinement**: Continuously monitor `vibectl check` behavior with various complex predicates and real-world scenarios, refining system and user prompts as needed to improve clarity, accuracy, and robustness against semantic drift. Ensure the LLM's explanations in `DoneAction` clearly articulate how gathered information relates to the *original user-supplied predicate*.

## Patch Command Future Enhancements

### Vibe Command Validation Framework

The core challenge with patch validation is that vibe commands generate kubectl commands from natural language, but there's no standardized way to preview and confirm operations before execution. Current flow has the LLM generate a command, user confirms, and command executes. But for validation (dry-run), we'd need to show dry-run results, let user confirm, then re-run the LLM (which might generate a different command).

**Proposed Solution - Command Caching with Validation Mode:**
- Add a general `--preview` flag to vibe commands that:
  1. LLM generates kubectl command from natural language
  2. Cache the exact command generated
  3. Run the cached command with `--dry-run=client` or `--dry-run=server`
  4. Display dry-run results to user
  5. Prompt for confirmation showing both the command and its predicted effects
  6. Execute the exact cached command (not re-generating from LLM)
- Implement in `handle_vibe_request` as a new execution mode
- Benefits: Ensures command executed matches command previewed, works across all vibe commands
- Technical considerations: Command caching, dry-run output parsing, confirmation UI integration

**Alternative - Validation-Aware LLM Planning:**
- Extend the LLM action schema to include validation steps
- LLM can plan: "COMMAND with validation" followed by "EXECUTE cached command"
- More complex but gives LLM control over when validation is needed

### Natural Language Batch Patching

Implement custom logic (similar to `check_cmd.py`) for commands like "patch all deployments in namespace X to use image Y" or "scale all services with label app=frontend to 3 replicas".

**Architecture:**
- Create `vibectl batch-patch` command with custom execution logic in `execution/batch_patch.py`
- LLM plans a multi-step approach:
  1. `DISCOVERY`: Identify target resources matching criteria
  2. `PLAN`: Generate patch operations for each resource
  3. `VALIDATE`: Optional dry-run of all planned patches
  4. `EXECUTE`: Apply patches with progress tracking and error handling
  5. `SUMMARY`: Report results across all resources

**Key Features:**
- **Resource Discovery**: Use kubectl with selectors, namespaces, resource types to find targets
- **Patch Generation**: LLM generates appropriate patch for each resource type/state
- **Progress Tracking**: Show live progress across multiple resources with rich display
- **Partial Failure Handling**: Continue on errors, collect failures, show summary
- **Rollback Planning**: Track successful operations for potential rollback
- **Confirmation Batching**: Show all planned operations before executing any

**Implementation Considerations:**
- Follow `check_cmd.py` pattern with custom action types (DISCOVERY, PLAN, EXECUTE, etc.)
- Integrate with existing live display patterns for progress visualization
- Use asyncio for concurrent patch operations with configurable parallelism
- Memory integration to track batch operation context across steps

### General Undo Capability

Rather than patch-specific history, implement a comprehensive undo system that works across all vibectl operations.

**Proposed `vibectl undo` Command:**
- **Operation Tracking**: Store operation history including:
  - Command executed (original vibectl command and generated kubectl commands)
  - Timestamp and user context
  - Resource state before operation (using kubectl get -o yaml)
  - Operation results and any errors
  - Undo strategy for the specific operation type
- **Undo Strategies by Operation Type**:
  - `patch`: Store original resource state, restore with kubectl apply
  - `scale`: Store original replica count, restore with kubectl scale
  - `delete`: Store deleted resource manifests, restore with kubectl apply
  - `apply`: Store previous resource state or use kubectl rollout undo for deployments
  - `create`: Delete created resources
- **Smart Undo Planning**:
  - LLM analyzes operation history and current cluster state
  - Generates appropriate undo commands
  - Handles conflicts (resource changed since original operation)
  - Warns about potential side effects
- **Safety Features**:
  - Dry-run undo operations by default
  - Require confirmation for potentially destructive undos
  - Detect and warn about conflicting changes since original operation
  - Support partial undo (undo specific resources from a batch operation)

**Technical Implementation:**
- Local SQLite database for operation history storage
- Integration with memory system for undo context
- Configurable retention period for undo history
- Export/import capabilities for undo history backup

### Additional Patch Enhancements

**Patch Generation from Resource Diff:**
- `vibectl patch generate <resource>`: Interactively edit resource and generate patch
- Use temporary files and `kubectl edit` workflow
- Generate strategic merge patch, JSON merge patch, or JSON patch automatically
- Show generated patch for review before application

**Patch Templates and Reusable Patterns:**
- `vibectl patch template save <name>`: Save common patch patterns
- `vibectl patch template apply <name> <resource>`: Apply saved template
- Template variables for resource names, namespaces, values
- Share templates across team via git repos or config

**Patch Impact Analysis:**
- Analyze potential impact of patches before application
- Check for breaking changes (image updates, port changes, etc.)
- Identify affected resources (services pointing to patched deployments)
- Integration with admission controllers and policy engines
- Warning system for potentially disruptive patches

**Advanced Patch Validation:**
- Integration with cluster admission controllers
- Policy validation (OPA, Kyverno, etc.) before patch application
- Resource quota impact analysis
- Dependency validation (ensure required configmaps/secrets exist)
- Scheduling feasibility checks (node resources, affinity rules)

**Patch Conflict Resolution:**
- Detect when patches conflict with concurrent changes
- LLM-assisted conflict resolution with suggested merge strategies
- Three-way merge capabilities for complex conflicts
- Automatic retry with conflict resolution for transient issues

**Enhanced Patch Syntax Support:**
- Support for kubectl patch --local for offline patch generation
- Enhanced JSON patch with variables and templating
- Strategic merge patch with array merge strategies
- Server-side apply integration for field management
