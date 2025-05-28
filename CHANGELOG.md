# Changelog

All notable changes to the vibectl project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Added
- **Complete Plugin System Implementation**: Comprehensive system for customizing vibectl behavior through installable prompt plugins
  - **Plugin Management Commands**: Full CLI interface for plugin operations
    - `vibectl install plugin <file>` - install plugins from JSON files with validation
    - `vibectl plugin list` - view installed plugins with metadata
    - `vibectl plugin uninstall <name>` - remove installed plugins
    - `vibectl plugin update <name> <file>` - update existing plugins
    - Support for `--precedence first|last|<position>` during installation
  - **Plugin Precedence System**: Configurable plugin precedence with fallback chains
    - `vibectl plugin precedence list` - view current precedence order
    - `vibectl plugin precedence set <plugin1> <plugin2> ...` - set explicit order
    - `vibectl plugin precedence add <plugin> [--position N]` - insert plugin at position
    - `vibectl plugin precedence remove <plugin>` - remove from precedence list
    - Integration with vibectl config system for persistent storage
  - **Version Compatibility System**: Robust semantic versioning support
    - Install-time version compatibility checking prevents incompatible plugins
    - Runtime version validation with graceful fallback to defaults
    - Support for complex version constraints (>=, <=, >, <, ==, !=, ranges)
    - Comprehensive test coverage with 19 test scenarios
  - **Plugin File-Based Storage**: Efficient plugin management in `~/.config/vibectl/plugins/`
    - JSON-based plugin format with metadata and prompt mappings
    - Automatic validation during installation
    - Plugin discovery and loading with caching
  - **Error Handling and Attribution**: Production-ready error management
    - WARNING level logging for custom prompt failures with attribution
    - Graceful fallback to default prompts on plugin errors
    - Version incompatibility prevents plugin usage without breaking core functionality
    - Zero performance overhead for non-plugin users
- **Command Plugin Integration**: Successfully converted commands to use plugin system
  - **Patch Command Integration**: Full plugin support with 2 prompt override points
    - `patch_plan` - planning prompt for kubectl patch command generation
    - `patch_resource_summary` - summary prompt for patch operation results
    - Established plugin decorator pattern with `@with_plugin_override()`
    - Complete test coverage with legacy constant removal
  - **Apply Command Integration**: Most comprehensive plugin integration with 6 prompt override points
    - `apply_plan` - main planning prompt (standard workflow)
    - `apply_resource_summary` - output summarization prompt (standard workflow)
    - `apply_filescope` - file scoping analysis prompt (intelligent workflow)
    - `apply_manifest_summary` - manifest summarization prompt (intelligent workflow)
    - `apply_manifest_correction` - manifest correction/generation prompt (intelligent workflow)
    - `apply_final_planning` - final command planning prompt (intelligent workflow)
    - Demonstrates plugin system support for complex multi-stage workflows
    - Advanced plugin capabilities for sophisticated orchestration patterns
- **Comprehensive Plugin Examples**: Rich set of example plugins in `examples/plugins/`
  - Security-focused plugins (paranoid-security-vibe-v1.json)
  - Workflow customization plugins (enhanced/minimal output styles)
  - Educational plugins (verbose-explainer, annotating operations)
  - Advanced workflow plugins (organizational, minimalist, security-hardened)
  - Documentation and usage examples for plugin development
- **Plugin System Documentation**: Complete documentation suite
  - `docs/plugin_system.md` - comprehensive plugin system documentation
  - `examples/plugins/README.md` - plugin development guide and examples
  - Integration examples in main README.md

### Changed
- **Major `prompt.py` Refactoring**: Successfully decomposed the massive 2134-line `vibectl/prompt.py` monolith into 20+ specialized modules for dramatically improved maintainability and organization
  - Reduced main `prompt.py` from 2134 lines to 332 lines (84% reduction)
  - Created well-organized `vibectl/prompts/` directory with subcommand-specific prompt modules
  - Extracted prompt functionality into dedicated modules: `apply.py`, `check.py`, `diff.py`, `edit.py`, `explain.py`, `get.py`, `logs.py`, `patch.py`, `top.py`, and more
  - Maintained 100% backward compatibility - all existing functionality preserved
  - All tests continue passing, ensuring no regressions introduced
  - Significantly improved code discoverability, testability, and ease of future maintenance
  - **Plugin System Foundation**: Refactoring enabled clean plugin integration patterns
    - Converted prompt constants to decorated functions for plugin override capability
    - Established standard naming conventions for plugin keys
    - Created reusable plugin integration patterns for future command conversions
- **Enhanced Config System**: Fixed critical bugs in configuration handling
  - Fixed config system list handling bug where list values were stored as individual characters
  - Improved type conversion with proper list parsing from string values
  - Enhanced config validation and error handling for nested operations

## [0.8.7] - 2025-05-26

### Fixed

- **Improved Error UX and Logging**:
  - Fixed duplicate error output that was causing multiple `[ERROR]` messages with repeated tracebacks
  - Fixed warnings being completely filtered out - now properly displayed to users (e.g., validation failures, retry attempts)
  - Implemented centralized exception handling at CLI entry point following logging best practices
  - Updated CLI entry point in `pyproject.toml` to use `main()` wrapper function for proper error handling
  - Simplified logging setup to prevent handler duplication and inconsistent output
  - ERROR messages now handled centrally with user-friendly output and tracebacks only when `VIBECTL_TRACEBACK=1` is set
  - Updated tests to match new centralized exception handling behavior

## [0.8.6] - 2025-05-26

### Changed

- Refactored `vibectl apply` implementation to match `vibectl edit` structure
  - Extracted execution logic to dedicated `vibectl/execution/apply.py` module (875 lines)
  - Extracted prompts to dedicated `vibectl/prompts/apply.py` module
  - Improved testability and consistency with edit implementation patterns
  - Enhanced prompt examples for better Claude 4 compatibility and multi-namespace fan-out behavior
  - Fixed critical async-related bugs in apply workflow (variable scope, namespace contamination)
  - Achieved 100% test coverage for apply command handler and comprehensive coverage for execution/prompts modules
  - Maintained all existing functionality while enabling better separation of concerns

## [0.8.5] - 2025-05-25

### Fixed

- Fixed kubectl kubeconfig placement in commands with trailing arguments after `--` separator
  - `--kubeconfig` flag now correctly placed immediately after `kubectl` instead of at command end
  - Resolves issue where commands like `kubectl exec deployment/nginx -- curl http://localhost` would fail with "curl: option --kubeconfig: is unknown"
  - Affects both `run_kubectl()` and `run_kubectl_with_yaml()` functions

## [0.8.4] - 2025-05-25

### Added

- `vibectl edit` command with intelligent editing capabilities
  - Standard kubectl edit functionality when `intelligent_edit` config is disabled
  - Intelligent editing workflow when enabled: fetch resource → summarize to natural language → user edits text → LLM generates patch → apply patch
  - Integration with existing vibe mode and patch command logic
  - Support for both standard usage and natural language editing via `click.edit()` interface

## [0.8.3] - 2025-05-23

### Added

- **`vibectl patch` Command**: Complete implementation of intelligent Kubernetes resource patching with natural language support.
  - Supports strategic merge patches, JSON merge patches, and JSON patches
  - Can patch resources by file or by type/name
  - Includes "vibe mode" for natural language patch descriptions (e.g., "scale the frontend deployment to 3 replicas", "add label environment=prod to the frontend service")
  - Comprehensive test coverage with 13 tests achieving 100% code coverage
  - Full integration with existing vibectl CLI options and output formatting

### Fixed

- **[Demo]** Chaos Monkey configuration and model selection:
  - Fixed inconsistent `VIBECTL_MODEL` defaults across files (unified to `claude-3.7-sonnet`)
  - Simplified configuration flow by removing redundant defaults in docker-compose.yaml
  - Fixed documentation gaps by adding missing `--vibectl-model` flag to README
  - Fixed library version pinning that was blocking claude-4-sonnet support
  - Resolved over-engineered configuration system that was preventing proper model selection

### Changed

## [0.8.2] - 2025-05-23

### Added

- Implemented streaming for LLM responses in Vibe commands, providing real-time output and a `show_streaming` flag (configurable globally and via `OutputFlags`) to control live display of intermediate Vibe output streams.
- Added test coverage for LLM response streaming, including scenarios where streaming display is suppressed (`show_streaming=False`).

### Changed

- Enabled Vibe summarization and memory updates even when the underlying `kubectl` command returns empty output. This allows for contextual memory updates (e.g., "No PVCs found in namespace X") where previously summaries were suppressed.
- Refactored `vibectl events` command to use `handle_standard_command` and `handle_watch_with_live_display` for better consistency and simplified logic.
- Modified `configure_output_flags` to include `show_streaming` and updated all subcommand call sites.
- Updated `ConsoleManager.print_vibe` to handle `use_panel` argument for controlling panel display, especially for streamed vs. non-streamed Vibe output.

## [0.8.1] - 2025-05-21

### Added

- **`vibectl check <predicate>` Subcommand**:
  - Implemented a new subcommand for autonomous, read-only evaluation of Kubernetes cluster state predicates.
  - Returns specific exit codes: `0` for TRUE, `1` for FALSE, `2` for poorly posed/ambiguous predicate, `3` for cannot determine/timeout.
  - Employs an iterative LLM-based planning loop:
    - Gathers information using read-only `kubectl` commands.
    - Feeds results back into LLM memory.
    - Continues until the predicate is resolved or max iterations/timeout is reached.
  - Includes utility functions to strictly enforce read-only `kubectl` operations.
  - Added `docs/predicate_evaluation.md` with a worked example.

### Changed

- **LLM Planner Schema & Prompting**:
  - Introduced a `DONE` action to the LLM planner schema, allowing the planner to signify completion of predicate evaluation and provide an `explanation` and `exit_code`.
  - Added an `explanation` field to the `CommandAction` and `explanation`/`suggestion` fields to `FeedbackAction` in the schema.
  - Revised system prompts and few-shot examples (using a new `MLExampleItem` structure) for the `vibectl check` planner to be more precise, emphasizing read-only operations and clear action usage.
  - Updated general planner prompts to leverage new schema fields for improved clarity.
- **Core Logic & Error Handling**:
  - Refactored core `check` logic into `vibectl.execution.check.py`.
  - Refactored `handle_vibe_request` into `vibectl.execution.vibe.py`.
  - Improved error handling for unhandled LLM actions, max iteration limits, malformed LLM commands, and improperly formed predicates.
  - Standardized exit codes for the `check` command using a `PredicateCheckExitCode` enum.
- **Command Confirmation**:
  - Consolidated command confirmation logic, centralizing the decision based on whether a command is read-only using `is_kubectl_command_read_only`.
- **Testing**:
  - Added extensive tests for `vibectl check` logic and subcommand, including iterative evaluation, exit codes, and various predicate scenarios.
  - Improved test coverage for `vibectl.execution.check`.

## [0.8.0] - 2025-05-17

### Added

- `vibectl apply vibe` intelligent workflow: an LLM-powered feature that understands user requests for applying manifests, discovers and validates specified files (local or remote), builds an operational context by summarizing valid manifests, attempts to correct or generate manifests for invalid/incomplete sources, plans the final `kubectl apply` command(s) based on all inputs and context, and executes the plan. Includes cleanup of temporary files.
- `vibectl diff` subcommand to compare local configurations (files or stdin) or planned configurations against the live cluster state, with optional summarization of changes.
- Added comprehensive tests for the `vibectl diff` subcommand, achieving 100% code coverage for `vibectl/subcommands/diff_cmd.py`.

### Changed

- Refactored `allowed_exit_codes` handling throughout the application:
  - `LLMCommandResponse` schema now supports an optional `allowed_exit_codes` field, allowing Vibe.AI to specify which exit codes are considered successful for a planned command.
  - `run_kubectl` (in `vibectl/k8s_utils.py`) now consistently uses the `allowed_exit_codes` parameter.
  - `Success` result objects now include `original_exit_code` to preserve the actual exit code of the command.
  - Command handlers (`command_handler.py`, `live_display.py`, `live_display_watch.py`) now propagate `allowed_exit_codes` to `run_kubectl` and `run_kubectl_with_yaml`.
- Refactored `run_kubectl` (in `vibectl/k8s_utils.py`):
  - Now always captures stdout/stderr.
  - Accepts `allowed_exit_codes` parameter to treat specific non-zero exit codes as success (e.g., for `kubectl diff`).
  - `Success` result objects now include `original_exit_code`.
- Updated numerous tests and subcommand implementations to align with the `run_kubectl` refactoring and `allowed_exit_codes` propagation.

### Removed

- Removed `capture` parameter from `run_kubectl` and its call sites, as output is now always captured.

## [0.7.0] - 2025-05-14

### Added

- **LLM Interaction Optimization & Observability:**
  - Refactored prompt construction to use a fragment-based system (`PromptFragments` in `vibectl/prompt.py`, `vibectl/types.py`) for better structure, potential caching by the underlying `llm` library, and improved maintainability.
  - Enhanced LLM call instrumentation in `model_adapter.py` and `command_handler.py` to record and display metrics for token usage (input/output) and latency, including total processing duration for LLM-related operations.
  - Added `--show-metrics`/`--no-show-metrics` flag and corresponding configuration (`show_metrics`) to control the display of these LLM metrics.
  - Introduced `TimedOperation` context manager in `model_adapter.py` for standardized internal timing.

### Changed

- Major refactor of prompt generation and handling (`vibectl/prompt.py`, `vibectl/command_handler.py`):
  - Introduced `PromptFragments` (SystemFragments, UserFragments) for more structured and flexible prompt construction.
  - Updated most planning and summarization prompts to use this new fragment-based system (e.g., `plan_vibe_fragments`, `memory_update_prompt`, `vibe_autonomous_prompt`).
  - Replaced static `plan_prompt` strings in subcommand handlers with `plan_prompt_func` that return `PromptFragments`.
  - Removed `memory_context` as a direct argument to `handle_vibe_request`; memory is now incorporated into prompt fragments by the caller or within specific prompt functions.
  - Consolidated and clarified prompt examples and instructions.
- Improved consistency in passing `Config` objects for prompt generation and other configurations.
- Refactored `LLMModelAdapter.execute` in `vibectl/model_adapter.py` for improved robustness, error handling, and internal timing:
  - Implemented `_handle_prompt_execution_with_adaptation` for adaptive retries on `AttributeError` (e.g., schema/fragment issues).
  - Introduced `LLMAdaptationError` for exhausted adaptation attempts.
  - Enhanced error logging with more context (attempt counts, latencies).
  - Made `_determine_provider_from_model` more robust for Ollama models.
- Updated `LLMMetrics` in `vibectl/types.py` (removed `cache_hit`, added `total_processing_duration_ms`) and adjusted `command_handler.py` and `console.py` for consistent metrics display.

## [0.6.3] - 2025-05-12

### Changed

- **[Demo]** Kafka Throughput Demo:
  - Updated `README.md` and `STRUCTURE.md` to reflect the current implementation:
    - `README.md`: Removed outdated Makefile targets (e.g., `check-latency`) and the "Troubleshooting & Past Issues" section. Updated demo stop command to `make down && make clean-cluster`.
    - `STRUCTURE.md`: Added `k8s-sandbox/port_forward_manager.py` and the `k8s-sandbox/manifests/` directory. Updated descriptions for `compose.yml`
