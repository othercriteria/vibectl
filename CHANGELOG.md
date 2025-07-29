# Changelog

All notable changes to the vibectl project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Changed
- Dependency lock strategy updated: `uv.lock` is once again the canonical lock file. `pylock.toml` is still generated automatically for compatibility and tooling has been updated accordingly.

## [0.11.6] - 2025-07-29

### Changed
- Dependency lock file renamed from `uv.lock` to `pylock.toml` and updated build tooling (`make lock`, CI) to generate/consume TOML v1 format.

## [0.11.5] - 2025-07-29

### Changed
- Completed Make-Only Release workflow: unified Makefile targets, simplified flake.nix, refreshed documentation, and removed the now-obsolete `PLANNED_CHANGES.md`.

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

- Major refactor of prompt generation and handling (`vibectl/prompt.py`, `
