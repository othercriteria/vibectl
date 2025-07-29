# Changelog

All notable changes to the vibectl project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

## [0.11.4] - 2025-07-28

### Added
- Introduce uv-based dependency locking workflow

### Changed
- Robust async-testing refactor completed:
  - Added shared async-test helpers (`fast_sleep`, `background_tasks`) for
    event-loop-friendly sleep replacement and task management.
  - Removed global `asyncio` monkey-patches; migrated existing stubs to
    `AsyncMock` or lightweight async wrappers.
  - Eliminated all `RuntimeWarning: coroutine ... was never awaited` messages
    (17 → 0) across the entire suite.

### Fixed
- Stabilised `ServerConfig` auto-reload tests:
  - Ensures watcher thread is active before file modifications, eliminating
    intermittent flakiness in `test_config_auto_reload_*`.
  - Atomic config file writes via `ServerConfig.save()` to prevent partially-written
    files and eliminate CI race-condition flakes; expanded unit tests for
    configuration I/O paths improve coverage.

* Fixed missing `pre-commit` dev dependency which caused Git pre-commit hooks to be skipped; restored the dependency in `pyproject.toml` and Nix `devShell` to ensure hooks run automatically again.

## [0.11.3] - 2025-06-27

### Added
- ContextVar override CLI flags `--max-rpm` and `--max-concurrent` for all `serve-*` commands, providing global runtime rate-limit controls without additional plumbing
- Refactor: removed redundant per-command kwargs; rate-limit flags now set overrides via callbacks (developer-experience only, no behaviour change for operators)
- **Server-side rate limiting & metrics for vibectl-server**:
  - Typed `Limits` model, validation helpers, and hot-reload watcher in `ServerConfig`
  - `RateLimitInterceptor` with in-process fixed-window RPM counter and concurrency semaphore
  - Prometheus metrics exporter (`/metrics`) behind `--enable-metrics` / `--metrics-port` flags
  - Global & per-token limit support via `server.limits.*` config keys and ContextVar overrides
  - Structured throttle logs and `RESOURCE_EXHAUSTED` gRPC responses with `retry-after-ms` metadata
  - Updated Kubernetes demo manifests to expose port 9095 and include Prometheus scrape annotations

### Fixed
* Handled `DONE` action in Vibe execution path, allowing autonomous and semiauto sessions to terminate gracefully instead of raising unexpected errors.
* Relaxed console test regex to accommodate line wrapping differences, eliminating flaky failures in parallel test runs.

## [0.11.2] - 2025-06-21

### Added
- Consistent prompt injection mechanism for custom instructions and memory across all prompt types
- Unit tests covering defensive branches in LLM adapter helpers (`is_valid_llm_model_name`, API-key message formatters) improving coverage.

### Changed
- **Developer Experience Improvements**: Dramatically improved development workflow performance through parallel execution and daemon optimization
  - **Parallel Test Execution by Default**: `make test` now runs tests in parallel (~4 seconds vs ~80 seconds, 20x faster)
    - Renamed serial execution to `make test-serial` for compatibility scenarios
    - Updated `make check` to use parallel tests by default for faster CI/development feedback
    - Added `make check-coverage` for detailed coverage analysis when needed
    - Updated pre-commit hooks to use parallel test execution, reducing commit-time test execution from ~80s to ~4s
    - Enhanced `tests/TESTING.md` documentation with updated usage patterns and performance comparisons
  - **dmypy Integration for Fast Type Checking**: Implemented mypy daemon for significantly faster type checking
    - **42x Performance Improvement**: Type checking now completes in ~0.15 seconds vs ~6.5 seconds with standard mypy
    - Added daemon management targets: `make dmypy-status`, `make dmypy-start`, `make dmypy-stop`, `make dmypy-restart`
    - Updated `make typecheck` to use dmypy daemon by default
    - Updated pre-commit hooks to use dmypy instead of standard mypy for faster commit-time checks
    - Added `.dmypy.json` to `.gitignore` and `make clean` target
    - Maintained full compatibility with existing mypy configuration and type checking standards
- **Internal Refactor**: Unified all non-streaming LLM invocations under the shared `run_llm` helper
  - Removed obsolete `get_adapter=` parameter from `run_llm`; helper now always resolves the adapter internally.
  - Updated tests to patch `vibectl.model_adapter.get_model_adapter` dynamically; eliminated redundant imports in production code.
  - Added temporary compatibility shim in `tests/conftest.py`, later earmarked for removal.
  - Removed duplicate boilerplate for adapter look-up and metrics aggregation
  - Enables consistent testing via easier mocking of `get_model_adapter`
  - Paves the way for future instrumentation and behaviour tweaks in a single location
  - Fixed Ruff F811 by removing duplicate `output_processor` import in `execution/vibe.py`.
- Memory update prompts no longer duplicate user custom instructions, reducing redundant context and improving memory quality.

## [0.11.1] - 2025-06-20

### Added
- **Client-side Proxy Security Hardening (V1)**
  • Named proxy profiles with per-profile security settings (sanitize requests, audit logging, confirmation modes)
  • Request sanitization framework detecting Kubernetes secrets, Base-64 blobs, and PEM certificates with redaction and confidence scoring
  • Structured audit logging with per-profile log files and new CLI commands:
    – `vibectl audit show`, `export`, `info`
  • Root-level `--proxy` / `--no-proxy` flags and confirmation-flow groundwork (`is_destructive_kubectl_command`, `should_confirm_action`)
  • 100 % test coverage for sanitizer and audit logger; extensive coverage for proxy workflow
- **Documentation**
  • New `docs/proxy-client-security.md` – companion to `docs/llm-proxy-server.md` covering all V1 client-side security features
  • `PLANNED_CHANGES.md` trimmed to track only remaining V1 validation tasks and post-V1 roadmap

### Changed
- **Proxy Configuration Migration**: Removed legacy proxy configuration format in favor of named profiles
  - Eliminated legacy `proxy.enabled`, `proxy.server_url` flat configuration keys
  - All proxy configuration now uses profile-based system for consistency and security
  - Updated `ProxyModelAdapter` to use profile-based JWT token and CA bundle resolution
  - Updated setup-proxy commands to work exclusively with named profiles
- **Configuration System**: Enhanced profile management capabilities
  - Added `get_effective_proxy_config()`, `list_proxy_profiles()`, `set_active_proxy_profile()` methods
  - Profile-based CA bundle and JWT token path resolution
  - Improved proxy status display with profile information and security settings
  - **CLI Options Cleanup**: Removed obsolete `--ca-bundle` root option; certificate bundle is now determined via proxy profile configuration.

### Fixed
- **Rich Streaming Display Issues**: Fixed multiple display rendering bugs in the live streaming vibe panel system
  - Fixed duplicate "top of the box" artifact where initial "(streaming...)" panel appeared alongside final result
  - Fixed missing Rich markup rendering in final display - `[bold]`, `[green]`, etc. are now properly rendered instead of shown as raw text
  - Improved Live display initialization to prevent premature rendering during stream setup
  - Enhanced test coverage with proper mock configurations for streaming scenarios
- Configuration system bug where string "none" was incorrectly converted to None value
  - Removed magic string-to-None conversion that caused validation errors
  - String "none" is now treated as a literal string value for config fields
  - Added helpful error messages suggesting `vibectl config unset` for clearing values
  - Improved user experience with clearer validation messages
- ProxyModelAdapter JWT token and CA bundle resolution bugs
  - Fixed missing method errors in proxy adapter when using profile-based configuration
  - Updated token resolution to use new profile-based configuration system
  - Enhanced connection testing with proper CA bundle and JWT token handling
  - Prevented tests and runtime code from creating `./.well-known/` directories by relocating the default ACME HTTP-01 challenge directory to `~/.config/vibectl/server/acme-challenges/` and updating tests accordingly.
  - Resolved linter warning about mutable default values in `vibectl/overrides.py`.

### Removed
- Legacy proxy configuration format support
  - Removed `proxy.enabled`, `proxy.server_url` and related flat configuration keys
  - Cleaned up legacy configuration handling code for simpler, more secure profile system
  - Updated tests to use new profile-based configuration exclusively

## [0.11.0] - 2025-06-17

### Added
- **Documentation / Planning**: Outstanding TLS-proxy work has been consolidated – `PLANNED_CHANGES.md` is now merged into `TODO-SERVER.md`, which also contains a detailed plan for **Certificate Transparency monitoring**.
- **TLS Support for vibectl LLM Proxy Server**: Complete implementation enabling secure connections for development environments
  - **Server-side TLS Integration**: Full TLS certificate handling and secure port binding in gRPC server
  - **Self-signed Certificate Generation**: Automatic certificate generation for development with cryptography library
  - **Comprehensive CLI Options**: TLS configuration options (--tls, --cert-file, --key-file, --generate-certs)
  - **Certificate Lifecycle Management**: Automatic certificate generation, validation, and error handling
  - **Complete vibectl-server:// URL Scheme**: Full TLS encryption support with proper certificate validation
  - **Development-friendly Workflow**: Seamless certificate auto-generation with graceful fallbacks
  - **ACME Protocol Support**: Complete ACME client/server implementation with TLS-ALPN-01 and HTTP-01 challenge support
  - **HTTP-01 Challenge Demo**: End-to-end testing with `demo-acme-http.sh` script
  - **Security Hardening**: TLS 1.3+ enforcement, secure file permissions, debug log redaction, race condition fixes
  - **Extensive Test Coverage**: Comprehensive test suite for certificate utilities, TLS integration, and ACME functionality

## [0.10.0] - 2025-06-05

### Added
- **LLM Proxy Server Architecture**: Complete client/server delegation system for centralized LLM management
  - **Centralized LLM Management**: Allow vibectl CLI instances to delegate LLM calls to a centralized server
  - **Simplified Client Setup**: Users no longer need to manage API keys, model selection, or provider authentication
  - **gRPC Protocol**: Modern, type-safe communication protocol suitable for Kubernetes ecosystem
  - **Flexible Configuration**: Hierarchical config structure supporting both client and server configurations
  - **ProxyModelAdapter**: New adapter implementing existing ModelAdapter interface for transparent LLM proxying
  - **JWT Authentication System**: Secure shared secrets with expiration times and JWT token support
  - **Server Features**: Model management, rate limiting, usage controls, and multi-client support
  - **Setup Tooling**: `vibectl setup-proxy` command for easy client configuration and connection validation
  - **Backward Compatibility**: Coexists with direct LLM usage without requiring migration
  - **Comprehensive Documentation**: Complete docs in `docs/llm-proxy-server.md` with setup and usage guides
  - **Full Test Coverage**: Extensive test suite with 100% coverage for all proxy components
- **Configuration System Restructuring**: Major reorganization of configuration settings for improved maintainability and clarity
  - **Hierarchical Configuration**: Restructured config using dotted notation (e.g., `display.theme`, `llm.model`, `features.intelligent_edit`)
  - **Logical Grouping**: Organized settings into logical categories: `core`, `display`, `llm`, `providers`, `memory`, `warnings`, `live_display`, `features`, `networking`, `plugins`, `proxy`, `system`
  - **Backward Compatibility**: Legacy flat keys continue to work alongside new hierarchical structure
  - **Enhanced Type Safety**: Improved validation and type conversion for nested configuration operations
  - **Server Configuration**: Separate server-specific configuration section for vibectl-server settings
  - **Documentation**: Complete configuration reference in `docs/CONFIG.md` with all available options

## [0.9.1] - 2025-06-02

### Added
- **Enhanced LLM Metrics Recording and Reporting System**: Comprehensive system for tracking and displaying LLM operation metrics
  - **Configurable Display Modes**: Four distinct metrics display options via `MetricsDisplayMode` enum (NONE/TOTAL/SUB/ALL)
    - NONE: No metrics display
    - TOTAL: Show only final aggregated metrics for command completion
    - SUB: Show individual LLM call metrics in real-time
    - ALL: Show both individual call metrics and final aggregated totals
  - **Rich Metrics Infrastructure**: New `model_adapter.py` module (1,534 lines) providing streaming metrics collection
    - `LLMMetrics` dataclass for tracking tokens (input/output), latency, and call counts
    - `LLMMetricsAccumulator` for aggregating metrics across multiple LLM operations
    - Consistent instrumentation across all LLM call sites
  - **Async Streaming Support**: Modern `ModelResponse` protocol enabling real-time metrics streaming
    - Support for streaming token counts and latency measurements
    - Non-blocking metrics collection during LLM response generation
  - **Enhanced Type System**: Updated `types.py` with comprehensive metrics types
    - Backward-compatible integration with existing interfaces
    - Type-safe metrics handling and accumulation patterns
  - **DRY Boilerplate Reduction**: Centralized LLM call patterns with built-in metrics collection
    - Simplified integration for new LLM-powered features
    - Consistent error handling and metrics recording across all call sites

## [0.9.0] - 2025-05-28

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
    - `STRUCTURE.md`: Added `k8s-sandbox/port_forward_manager.py` and the `k8s-sandbox/manifests/` directory. Updated descriptions for `compose.yml` (reflecting `status-volume` as a host bind mount and adding the `kminion` service) and `k8s-sandbox/entrypoint.sh` (mentioning `port_forward_manager.py` for Kafka port-forwarding).
  - Standardized `TARGET_LATENCY_MS` usage across components. This environment variable is now consistently used for latency thresholds and is propagated from the host to the producer.
  - Improved producer's adaptive rate logic: it now holds or adjusts its target send rate based on a comparison of actual consumer p99 latency against the `TARGET_LATENCY_MS`.
- **[Demo]** Refined Chaos Monkey agent RBAC permissions for Blue and Red agents:
  - Restricted Red Agent's ability to create/delete Deployments/ReplicaSets.
  - Scoped Red Agent's pod creation to the `services` namespace.
  - Hardened Blue and Red agent access to the `system-monitoring` namespace (no access to common resources).
  - Granted Blue Agent explicit read-only access to the `protected` namespace.
  - Ensured Blue Agent retains necessary defensive capabilities in the `services` namespace via a dedicated Role, while its ClusterRole is now primarily read-only cluster-wide.
  - Stabilized ServiceAccount (SA) handling in Chaos Monkey demo to ensure reliable token authentication:
    - Agent SAs (blue-agent, red-agent) are now created once via a dedicated manifest (`agent-serviceaccounts.yaml`).
    - SA definitions were removed from passive and active RBAC YAML files.
    - `k8s-entrypoint.sh` updated to apply the standalone SA manifest early.
    - Kubeconfig regeneration during the passive-to-active RBAC switch is now skipped, as the SA token remains valid.
    - This resolves intermittent "Unauthorized" errors previously faced by agents post-RBAC switch.

## [0.6.2] - 2025-05-08

### Fixed
- Update example Dockerfiles (bootstrap, ctf) to use Python 3.11+.
- Fix `TypeError` in `vibectl auto` command when `--yes` flag is used.
- Fix `click.Abort` error in non-interactive `auto` mode by correctly handling the `yes` flag during command confirmation for dangerous commands.
- Fix `No module named pip` error in bootstrap example Dockerfile by adding `ensurepip` step.

## [0.6.1] - 2025-05-07

### Added
- Interactive live display for commands using `--watch` (`get`, `events`) or `--follow` (`logs`), replacing simple pass-through. Includes keybindings for Exit (E), Pause (P), Wrap (W), Save (S), and Filter (F).
- Status bar for live display showing elapsed time, line count, and spinner.
- Live display feature for `vibectl get --watch` using Rich Live.
- Planned: Enhanced watch/follow functionality for relevant vibectl commands (WIP)

### Changed
- Refactored tests for `get` subcommand into `tests/subcommands/test_get_cmd.py`.
- Improved test coverage for `vibectl/subcommands/get_cmd.py`.
- Refactored watch/follow logic from `command_handler.py` into new `live_display_watch.py` module.
- Vibe summarization for watched/followed commands now occurs after the live display is exited, using the captured output.

## [0.6.0] - 2025-05-04

### Added
- Define `RecoverableApiError` exception and `RECOVERABLE_API_ERROR_KEYWORDS` for better handling of transient API issues (rate limits, etc.).
- New `yaml_manifest` field to `LLMCommandResponse` schema to handle YAML input for commands like `create -f -`.
- Implement JSON schema (`LLMCommandResponse`) for structured LLM command planning responses.
- Update command planning prompts (get, describe, logs, version, etc.) to request JSON output conforming to the schema.
- Update `ModelAdapter` to support passing JSON schemas to compatible LLM models.
- Update `handle_vibe_request` to generate schema, parse JSON response, and dispatch based on `action_type`.
- Add basic schema validation via Pydantic model and handler checks.
- Correct prompt formatting in `semiauto` mode to properly include memory context, preventing incorrect LLM requests.
- Resolved `AttributeError` related to asyncio patching in tests.
- Corrected assertions for error string handling in `command_handler` memory tests.
- Fixed `IndexError` and lint warnings in `port-forward` keyboard interrupt tests.
- Added missing `summary_prompt_func` arguments to internal subcommand calls.

### Changed
- Refactor `PLAN_VIBE_PROMPT` to use the JSON schema approach for planning.
- Update `model_adapter.py` to use `schema=` parameter for `llm` library compatibility.
- Update error handling in `command_handler` to use `RecoverableApiError` and improve error reporting during Vibe processing.
- Refine logic for determining `kubectl` verb/args in `handle_vibe_request` based on original command context.
- Improve prompt display in `_handle_command_confirmation`.
- Adjust `autonomous_mode` logic in `vibe_cmd.py`.
- Refactor exception handling in `auto_cmd.py` loop.
- Remove automatic confirmation bypass for `semiauto` mode.
- Refactored `create_planning_prompt` to assume command verb is implied by context.
  - Prompt now focuses LLM on extracting target resource(s) and arguments.
  - Updated prompt instructions and structure.
- Updated most `PLAN_*_PROMPT` constants (get, describe, delete, logs, scale, rollout, wait, port-forward, version, cluster-info, events) to use the refactored prompt structure.
  - Examples now focus on target description, removing action verbs.
- Updated `PLAN_CREATE_PROMPT` examples to include a mix of implicit and explicit creation requests.
- Updated `handle_vibe_request` and `_execute_command` to process `yaml_manifest` from LLM response.
- Refined `_handle_command_confirmation` to restore full option handling (`a`, `e`) and improve prompt clarity.
- Simplified `port-forward` handler tests for improved stability and clarity.
- **[Demo]** Update `examples/k8s-sandbox/ctf` demo to install `vibectl` from local source via `pip install -e .`.
- **[Demo]** Major enhancements to Chaos Monkey demo:
  - Improved overseer dashboard with real-time cluster resource data (nodes, pods, namespaces, resource quotas), pod age/restarts, and better formatting.
  - Enhanced poller with more robust Kubernetes checks, deployment readiness waits, and `PENDING` status.
  - Refined monitoring intervals and background task handling in overseer.
  - Added UI staleness detection and warning banner.
  - Updated README with detailed component descriptions, configuration, and troubleshooting.
  - Switched demo phases from session duration to distinct passive/active phases.
  - Updated `run.sh` script with new duration parameters and stable version definitions.
  - **[Demo]** Refined Chaos Monkey demo components:
    - Added `chaos-monkey-system` namespace for agents, poller, overseer.
    - Agents, Poller, Overseer now use dedicated kubeconfigs generated by sandbox entrypoint.
    - Updated RBAC rules and sandbox entrypoint logic for phased permissions.
    - Updated Kind version and added `jq` dependency.
    - Adjusted resource quotas and agent instructions.
    - Removed redundant `OVERSEER_HOST`/`PORT` env vars from non-Overseer components.
    - Added new Overseer configuration variables (`METRICS_INTERVAL`, etc.).
    - Updated Docker health check for the sandbox.
    - Updated README to reflect new setup, configuration, and troubleshooting details.

### Fixed
- Fix test failures related to `schema=` parameter change in `model_adapter`.
- Correct `execute` method signatures in test mock adapters to align with base class and resolve mypy errors.
- Correct `BaseModel` imports in test files (`pydantic` vs `typing`).
- Updated numerous tests (`test_prompt.py`, `test_command_handler_edge_cases.py`) to align with prompt refactoring and confirmation logic changes.
- Fixed redundant AI explanation print during command confirmation flow.
- Replaced debug `print` statement with `logger.debug` in `handle_vibe_request`.
- Fixed `AttributeError` for `print_command_info` by using `print_processing`.
- Resolved persistent Mypy assignment errors in `command_handler.py`.
- Removed unused `flags` parameter from `create_planning_prompt`.
- Resolve prompt formatting issues when embedding JSON schema definition.
- Ensure correct command verb is used when executing LLM-planned commands.
- Correct `update_memory` calls within `handle_vibe_request` for errors and autonomous mode.
- Handle potential JSON parsing (`JSONDecodeError`) and validation (`ValidationError`) errors from LLM responses.
- Fix various test failures related to schema integration, error handling, and mock interactions.
- Correct type hints and resolve linter errors in related modules and tests.
- Refactor command confirmation logic for clarity.

## [0.5.3] - 2025-04-27

### Added
- Added initial Kafka throughput optimization demo (`examples/k8s-sandbox/kafka-throughput/`) featuring:
  - K3d Kubernetes cluster running a single-node KRaft Kafka instance.
  - Python producer/consumer applications generating load and reporting P99 latency.
  - A `vibectl` agent configured with the goal to maximize throughput and minimize latency by tuning Kafka broker environment variables (`KAFKA_HEAP_OPTS`, `KAFKA_NUM_NETWORK_THREADS`, `KAFKA_NUM_IO_THREADS`).
  - Resource limits on the sandbox container and de-optimized Kafka defaults to create a clear optimization scenario.
  - Makefile for easy management (`make up`, `make down`, `make logs`, etc.).
- Added basic Flask web UI (`kafka-demo-ui`) to the Kafka throughput demo, displaying key metrics (latency, producer stats, component health) using SocketIO for real-time updates.

### Changed
- Updated root `STRUCTURE.md` to include Kafka demo.

## [0.5.2] - 2025-04-26

### Changed
- Refactored output processing and truncation logic for better modularity and testability (`output_processor.py`, `truncation_logic.py`).
- Implemented budget-aware YAML truncation, distributing character limits across top-level sections.
- Improved log truncation to iteratively adjust lines kept based on character budget.
- Enhanced YAML output processing (`OutputProcessor`) with budget-based secondary truncation for better LLM context management.
- Improved robustness of `extract_yaml_sections` for various YAML structures, including multi-document files.
- Refined iterative log truncation logic (`_truncate_logs_by_lines`) for improved character budget adherence.

### Added
- Increased test coverage for output processing, YAML section handling, and log truncation edge cases.
- Extensive new unit tests for `OutputProcessor` focusing on YAML section extraction, budget calculation, and multi-document handling.
- Additional test coverage for `truncation_logic` edge cases.

### Fixed
- Addressed previously failing/skipped tests related to output processing.

## [0.5.1] - 2025-04-25

### Added
- New bootstrap demo in examples/k8s-sandbox featuring:
  - Self-contained k3d (K3s in Docker) cluster with Ollama LLM
  - Single-container setup with Docker-in-Docker
  - Vibectl configured to use local Ollama instance via kubectl port-forward
  - Support for installing from local source or stable PyPI packages
  - Automated demonstration of vibectl K8s analysis capabilities
  - Single-command unattended setup and execution

### Changed
- Improved feature-worktrees rule to prevent branch conflicts and enforce correct worktree-based feature development workflow

### Fixed
- Fixed handling of unknown model names with proper error messages
- Fixed potential KeyError when prompt contains {memory_context} placeholder but memory_context is empty
- Improved string format handling to handle malformed format strings in memory context

## [0.5.0] - 2025-04-25

### Added
- New `vibectl auto` subcommand to reify the looping `vibectl vibe --yes` pattern
- New `vibectl semiauto` subcommand as sugar for `auto` with negated `--yes` behavior
- Enhanced confirmation dialog with new options:
  - `yes [A]nd` for accepting with fuzzy memory update
  - `no [B]ut` for rejecting with fuzzy memory update
  - `[E]xit` option (in semiauto mode) to exit the loop cleanly

### Changed
- Updated `chaos-monkey` example to use the new `vibectl auto` subcommand
- Improved interactive-commands rule to clarify the proper usage of `--no-pager` with git commands

### Fixed
- Fixed error messages shown when a user selects [E]xit in semiauto mode
  - Updated exception handling to properly handle normal exits without displaying error messages
  - Improves user experience by ensuring clean exit behavior
- Fixed `vibectl auto` breaking on API errors like "overloaded_error"
  - Added detection of API-related errors and marked them as non-halting
  - Auto loop now continues despite transient API issues like rate limiting or service overload
  - Improved resilience for automated/scheduled usage of vibectl
- Fixed recovery suggestions not being integrated into memory state
  - Added update_memory call when recovery suggestions are generated
  - Ensures that suggestions from one command are available for subsequent commands in auto mode
  - Improves the continuity of error recovery in multi-step workflows

## [0.4.1] - 2025-04-22

### Added
- New chaos-monkey demo in examples/k8s-sandbox featuring:
  - Red team vs. blue team competitive scenario
  - Blue agent for maintaining system stability
  - Red agent for simulating service disruptions
  - Metrics collection and performance evaluation
  - Containerized vibectl agents interacting with K8s cluster

### Fixed
- Fixed KeyError when prompts contain format placeholders like `{spec}` that conflict with formatting operations
  - Added fallback string replacement method for robust prompt handling
  - Prevents crash in chaos-monkey agent when generating Kubernetes YAML templates
- Resolved linting issues in chaos-monkey overseer component
  - Fixed line length violations for improved code quality
  - Ensured code adheres to project's style standards

## [0.4.0] - 2025-04-18

### Added
- Basic structured logging to vibectl for improved observability and debugging
  - Configurable log levels for different verbosity needs
  - Console and file output support
  - Structured logging for machine-readable output
- Configurable log level via config or VIBECTL_LOG_LEVEL environment variable
- User-facing warnings and errors are surfaced via the console
- Logging test pattern and fixtures for reliable assertions on log output

## [0.3.2] - 2025-04-15

### Added
- New `port-forward` command for Kubernetes service port forwarding
  - Supports standard kubectl port-forward functionality
  - Features rich progress display with connection status
  - Includes vibe-based natural language request support
  - Provides configurable proxy monitoring warnings
- New `wait` command for Kubernetes condition monitoring
  - Supports standard kubectl wait functionality
  - Includes vibe-based natural language request support

### Changed
- Implemented asyncio for `wait` and `port-forward` commands
  - Enables non-blocking progress displays and improves scalability
- Updated PLAN_VIBE_PROMPT to generate cleaner output
- Simplified command handling by removing prefix stripping logic

### Fixed
- Fixed `wait` command test suite for live display features
- Improved `port-forward vibe` command to show proper connection status
- Resolved `vibectl vibe` execution to prevent "unknown command" errors

## [0.3.1] - 2025-04-14

### Added
- K8s-sandbox example with challenge-based learning for Kubernetes
- Parameterizable difficulty levels for the K8s-sandbox demo
- Verbose mode option for the K8s-sandbox demo
- Heredoc handling for complex command processing

### Changed
- Bumped version from 0.3.0 to 0.3.1
- Improved K8s-sandbox architecture with overseer component
- Simplified command handling and argument parsing
- Enhanced test coverage for memory and output processor modules

### Fixed
- Improved K8s-sandbox challenge detection with direct Kind container access
- Resolved K8s-sandbox demo issues with API keys and poller detection
- Optimized slow tests in test_vibe_delete_confirm.py
- Fixed mock console handling in handle_vibe_request test
- Improved command processing for complex arguments with spaces
- Resolved line length errors in command handling
- Added tests/__init__.py to fix MyPy module detection

## [0.3.0] - 2025-04-12

### Added
- `show-kubectl` flag for controlling kubectl command display
- Model adapter pattern for more flexible LLM integrations
- Initial implementation for improved model selection and key management

### Fixed
- Handle kubeconfig flags and command structure correctly in handle_vibe_request
- Fix slow tests by properly mocking LLM calls
- Improve feature worktree rule to prevent file creation in main workspace
- Properly handle kubectl command output and error cases

### Changed
- Refactor code to use model adapter instead of direct LLM calls
- Extract API key message formatting into helper functions
- Update tests to work with OutputFlags object and new validation

## [0.2.2] - 2025-04-09

### Added
- Package distribution and versioning tools
- Complete PyPI distribution support
- Version management with `bump_version.py` script
- Makefile targets for release management

### Changed
- Bumped version from 0.2.1 to 0.2.2
- Aligned version numbers between pyproject.toml and __init__.py
